"""MetricsCollector 단위 테스트.

PR-035: 운영 대시보드 메트릭 수집기 테스트.
"""
from __future__ import annotations

import threading
import time

import pytest

from scripts.lib.metrics_collector import (
    DashboardMetrics,
    EndpointStats,
    LatencyStats,
    MetricsCollector,
    RequestRecord,
    UsageStats,
    _compute_latency,
    _percentile,
)


# ---------------------------------------------------------------------------
# RequestRecord (불변 데이터)
# ---------------------------------------------------------------------------


class TestRequestRecord:
    """RequestRecord frozen dataclass 테스트."""

    def test_create_record(self):
        rec = RequestRecord(
            endpoint="/api/search",
            method="POST",
            status_code=200,
            duration_ms=42.5,
            timestamp=1000.0,
        )
        assert rec.endpoint == "/api/search"
        assert rec.method == "POST"
        assert rec.status_code == 200
        assert rec.duration_ms == 42.5
        assert rec.timestamp == 1000.0

    def test_immutable(self):
        rec = RequestRecord(
            endpoint="/api/health",
            method="GET",
            status_code=200,
            duration_ms=1.0,
            timestamp=1000.0,
        )
        with pytest.raises(AttributeError):
            rec.endpoint = "/api/other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# LatencyStats
# ---------------------------------------------------------------------------


class TestLatencyStats:
    """LatencyStats frozen dataclass 테스트."""

    def test_create(self):
        stats = LatencyStats(
            p50=10.0, p95=50.0, p99=100.0, mean=25.0, min=1.0, max=200.0, count=100
        )
        assert stats.p50 == 10.0
        assert stats.count == 100

    def test_immutable(self):
        stats = LatencyStats(
            p50=10.0, p95=50.0, p99=100.0, mean=25.0, min=1.0, max=200.0, count=100
        )
        with pytest.raises(AttributeError):
            stats.p50 = 20.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# _percentile helper
# ---------------------------------------------------------------------------


class TestPercentile:
    """_percentile 유틸리티 함수 테스트."""

    def test_empty(self):
        assert _percentile([], 50) == 0.0

    def test_single(self):
        assert _percentile([10.0], 50) == 10.0
        assert _percentile([10.0], 99) == 10.0

    def test_basic_percentiles(self):
        values = sorted([1.0, 2.0, 3.0, 4.0, 5.0])
        assert _percentile(values, 0) == 1.0
        assert _percentile(values, 50) == 3.0
        assert _percentile(values, 100) == 5.0

    def test_interpolation(self):
        values = sorted([10.0, 20.0])
        p50 = _percentile(values, 50)
        assert p50 == 15.0  # interpolated midpoint


# ---------------------------------------------------------------------------
# _compute_latency helper
# ---------------------------------------------------------------------------


class TestComputeLatency:
    """_compute_latency 유틸리티 함수 테스트."""

    def test_empty(self):
        stats = _compute_latency([])
        assert stats.count == 0
        assert stats.mean == 0.0

    def test_single_value(self):
        stats = _compute_latency([42.0])
        assert stats.count == 1
        assert stats.mean == 42.0
        assert stats.p50 == 42.0
        assert stats.min == 42.0
        assert stats.max == 42.0

    def test_multiple_values(self):
        durations = [10.0, 20.0, 30.0, 40.0, 50.0]
        stats = _compute_latency(durations)
        assert stats.count == 5
        assert stats.mean == 30.0
        assert stats.min == 10.0
        assert stats.max == 50.0
        assert stats.p50 == 30.0


# ---------------------------------------------------------------------------
# MetricsCollector — record + get_metrics
# ---------------------------------------------------------------------------


class TestMetricsCollectorRecord:
    """MetricsCollector.record() 테스트."""

    def test_record_increments_total(self):
        mc = MetricsCollector()
        assert mc.total_requests == 0
        mc.record("/api/search", "POST", 200, 10.0)
        assert mc.total_requests == 1
        mc.record("/api/generate", "POST", 200, 20.0)
        assert mc.total_requests == 2

    def test_circular_buffer(self):
        mc = MetricsCollector(max_records=3)
        for i in range(5):
            mc.record(f"/api/ep{i}", "GET", 200, float(i))
        # total은 5지만 버퍼에는 3개만 유지
        assert mc.total_requests == 5
        metrics = mc.get_metrics(window_seconds=3600)
        # 윈도우 내 요청 수는 버퍼 크기 이하
        assert metrics.latency.count <= 3


class TestMetricsCollectorGetMetrics:
    """MetricsCollector.get_metrics() 테스트."""

    def test_empty_metrics(self):
        mc = MetricsCollector()
        metrics = mc.get_metrics()
        assert isinstance(metrics, DashboardMetrics)
        assert metrics.total_requests == 0
        assert metrics.success_count == 0
        assert metrics.error_count == 0
        assert metrics.error_rate == 0.0
        assert metrics.latency.count == 0
        assert metrics.endpoints == ()

    def test_success_and_error_counts(self):
        mc = MetricsCollector()
        mc.record("/api/search", "POST", 200, 10.0)
        mc.record("/api/search", "POST", 200, 15.0)
        mc.record("/api/search", "POST", 500, 100.0)
        mc.record("/api/generate", "POST", 422, 50.0)

        metrics = mc.get_metrics()
        assert metrics.total_requests == 4
        assert metrics.success_count == 2
        assert metrics.error_count == 2
        assert metrics.error_rate == 0.5

    def test_endpoint_breakdown(self):
        mc = MetricsCollector()
        mc.record("/api/search", "POST", 200, 10.0)
        mc.record("/api/search", "POST", 200, 20.0)
        mc.record("/api/generate", "POST", 200, 30.0)

        metrics = mc.get_metrics()
        assert len(metrics.endpoints) == 2

        # Sorted by total_requests descending
        ep_search = next(ep for ep in metrics.endpoints if ep.endpoint == "/api/search")
        assert isinstance(ep_search, EndpointStats)
        assert ep_search.total_requests == 2
        assert ep_search.error_count == 0

    def test_window_filtering(self):
        mc = MetricsCollector()
        # 기록 삽입
        mc.record("/api/search", "POST", 200, 10.0)

        # 매우 짧은 윈도우 (0.001초) — 방금 기록한 것은 포함됨
        metrics_short = mc.get_metrics(window_seconds=0.001)
        # 기록이 매우 최근이므로 포함될 수도 있지만, 확인 용도:
        assert metrics_short.window_seconds == 0.001

        # 긴 윈도우 — 반드시 포함
        metrics_long = mc.get_metrics(window_seconds=3600)
        assert metrics_long.latency.count >= 1

    def test_latency_stats(self):
        mc = MetricsCollector()
        for d in [10.0, 20.0, 30.0, 40.0, 50.0]:
            mc.record("/api/search", "POST", 200, d)

        metrics = mc.get_metrics()
        assert metrics.latency.mean == 30.0
        assert metrics.latency.min == 10.0
        assert metrics.latency.max == 50.0
        assert metrics.latency.count == 5


# ---------------------------------------------------------------------------
# MetricsCollector — get_usage_stats
# ---------------------------------------------------------------------------


class TestMetricsCollectorUsageStats:
    """MetricsCollector.get_usage_stats() 테스트."""

    def test_empty_usage_stats(self):
        mc = MetricsCollector()
        stats = mc.get_usage_stats()
        assert isinstance(stats, UsageStats)
        assert stats.total_requests == 0
        assert stats.top_endpoints == ()

    def test_top_endpoints(self):
        mc = MetricsCollector()
        for _ in range(5):
            mc.record("/api/search", "POST", 200, 10.0)
        for _ in range(3):
            mc.record("/api/generate", "POST", 200, 20.0)
        mc.record("/api/health", "GET", 200, 1.0)

        stats = mc.get_usage_stats()
        assert stats.total_requests == 9
        # Top endpoint should be /api/search
        assert len(stats.top_endpoints) == 3
        assert stats.top_endpoints[0] == ("/api/search", 5)
        assert stats.top_endpoints[1] == ("/api/generate", 3)

    def test_status_code_distribution(self):
        mc = MetricsCollector()
        mc.record("/api/search", "POST", 200, 10.0)
        mc.record("/api/search", "POST", 200, 10.0)
        mc.record("/api/search", "POST", 500, 10.0)

        stats = mc.get_usage_stats()
        dist = dict(stats.status_code_distribution)
        assert dist[200] == 2
        assert dist[500] == 1

    def test_hourly_counts(self):
        mc = MetricsCollector()
        mc.record("/api/search", "POST", 200, 10.0)

        stats = mc.get_usage_stats(window_seconds=3600)
        # 1시간 윈도우 = hourly_counts에 1개 항목
        assert len(stats.hourly_counts) == 1

    def test_requests_per_minute(self):
        mc = MetricsCollector()
        for _ in range(60):
            mc.record("/api/search", "POST", 200, 10.0)

        stats = mc.get_usage_stats()
        assert stats.requests_per_minute > 0


# ---------------------------------------------------------------------------
# MetricsCollector — reset
# ---------------------------------------------------------------------------


class TestMetricsCollectorReset:
    """MetricsCollector.reset() 테스트."""

    def test_reset(self):
        mc = MetricsCollector()
        mc.record("/api/search", "POST", 200, 10.0)
        assert mc.total_requests == 1
        mc.reset()
        assert mc.total_requests == 0
        metrics = mc.get_metrics()
        assert metrics.latency.count == 0


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestMetricsCollectorThreadSafety:
    """MetricsCollector thread-safety 테스트."""

    def test_concurrent_records(self):
        mc = MetricsCollector()
        n_threads = 4
        n_records_per_thread = 100

        def worker():
            for _ in range(n_records_per_thread):
                mc.record("/api/search", "POST", 200, 10.0)

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert mc.total_requests == n_threads * n_records_per_thread

    def test_concurrent_read_write(self):
        mc = MetricsCollector()
        stop = threading.Event()
        errors: list[str] = []

        def writer():
            for _ in range(200):
                mc.record("/api/search", "POST", 200, 10.0)

        def reader():
            while not stop.is_set():
                try:
                    mc.get_metrics()
                    mc.get_usage_stats()
                except Exception as e:
                    errors.append(str(e))

        reader_thread = threading.Thread(target=reader)
        writer_thread = threading.Thread(target=writer)

        reader_thread.start()
        writer_thread.start()
        writer_thread.join()
        stop.set()
        reader_thread.join()

        assert len(errors) == 0
        assert mc.total_requests == 200


# ---------------------------------------------------------------------------
# DashboardMetrics / UsageStats (불변)
# ---------------------------------------------------------------------------


class TestDashboardMetricsImmutable:
    """DashboardMetrics frozen dataclass 테스트."""

    def test_immutable(self):
        latency = LatencyStats(
            p50=10.0, p95=50.0, p99=100.0, mean=25.0, min=1.0, max=200.0, count=100
        )
        metrics = DashboardMetrics(
            total_requests=100,
            success_count=90,
            error_count=10,
            error_rate=0.1,
            latency=latency,
            uptime_seconds=3600.0,
            window_seconds=3600.0,
            endpoints=(),
        )
        with pytest.raises(AttributeError):
            metrics.total_requests = 200  # type: ignore[misc]


class TestUsageStatsImmutable:
    """UsageStats frozen dataclass 테스트."""

    def test_immutable(self):
        stats = UsageStats(
            total_requests=100,
            requests_per_minute=1.67,
            top_endpoints=(("/api/search", 50),),
            status_code_distribution=((200, 90), (500, 10)),
            hourly_counts=((0, 100),),
        )
        with pytest.raises(AttributeError):
            stats.total_requests = 200  # type: ignore[misc]
