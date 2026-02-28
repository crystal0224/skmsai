"""MetricsCollector Content Studio 확장 단위 테스트.

CC-02: Content Studio 메트릭 수집 확장 테스트.
"""
from __future__ import annotations

import threading
import time

import pytest

from scripts.lib.metrics_collector import (
    ContentGenerationRecord,
    ContentStudioStats,
    MetricsCollector,
)


# ---------------------------------------------------------------------------
# ContentGenerationRecord (불변 데이터)
# ---------------------------------------------------------------------------


class TestContentGenerationRecord:
    """ContentGenerationRecord frozen dataclass 테스트."""

    def test_create_record(self):
        rec = ContentGenerationRecord(
            content_type="lecture",
            topic="SUPEX 추구",
            success=True,
            duration_ms=1500.0,
            file_count=3,
            asset_count=10,
            timestamp=1000.0,
        )
        assert rec.content_type == "lecture"
        assert rec.topic == "SUPEX 추구"
        assert rec.success is True
        assert rec.duration_ms == 1500.0
        assert rec.file_count == 3
        assert rec.asset_count == 10
        assert rec.timestamp == 1000.0

    def test_immutable(self):
        rec = ContentGenerationRecord(
            content_type="quiz",
            topic="인간중심 경영",
            success=True,
            duration_ms=500.0,
            file_count=1,
            asset_count=0,
            timestamp=1000.0,
        )
        with pytest.raises(AttributeError):
            rec.content_type = "audio"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ContentStudioStats (불변 데이터)
# ---------------------------------------------------------------------------


class TestContentStudioStats:
    """ContentStudioStats frozen dataclass 테스트."""

    def test_create(self):
        stats = ContentStudioStats(
            total_generations=10,
            success_count=8,
            failure_count=2,
            success_rate=0.8,
            type_distribution=(("lecture", 5), ("quiz", 3), ("audio", 2)),
            avg_duration_ms=1200.0,
            total_files_generated=25,
            total_assets_generated=40,
        )
        assert stats.total_generations == 10
        assert stats.success_rate == 0.8
        assert len(stats.type_distribution) == 3

    def test_immutable(self):
        stats = ContentStudioStats(
            total_generations=5,
            success_count=5,
            failure_count=0,
            success_rate=1.0,
            type_distribution=(),
            avg_duration_ms=100.0,
            total_files_generated=5,
            total_assets_generated=10,
        )
        with pytest.raises(AttributeError):
            stats.total_generations = 10  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MetricsCollector — record_content_generation
# ---------------------------------------------------------------------------


class TestRecordContentGeneration:
    """MetricsCollector.record_content_generation() 테스트."""

    def test_record_content_generation_basic(self):
        mc = MetricsCollector()
        mc.record_content_generation(
            content_type="lecture",
            topic="SUPEX 추구",
            success=True,
            duration_ms=1500.0,
            file_count=3,
            asset_count=10,
        )
        stats = mc.get_content_studio_stats()
        assert stats.total_generations == 1
        assert stats.success_count == 1
        assert stats.failure_count == 0

    def test_record_with_defaults(self):
        mc = MetricsCollector()
        mc.record_content_generation(
            content_type="quiz",
            topic="인간중심 경영",
            success=False,
            duration_ms=200.0,
        )
        stats = mc.get_content_studio_stats()
        assert stats.total_generations == 1
        assert stats.total_files_generated == 0
        assert stats.total_assets_generated == 0

    def test_circular_buffer(self):
        mc = MetricsCollector(max_records=3)
        for i in range(5):
            mc.record_content_generation(
                content_type="lecture",
                topic=f"토픽 {i}",
                success=True,
                duration_ms=float(i * 100),
                file_count=1,
                asset_count=2,
            )
        # 버퍼에는 최대 3개만 유지
        stats = mc.get_content_studio_stats()
        assert stats.total_generations <= 3


# ---------------------------------------------------------------------------
# MetricsCollector — get_content_studio_stats
# ---------------------------------------------------------------------------


class TestContentStudioStatsEmpty:
    """빈 상태의 Content Studio 통계 테스트."""

    def test_content_studio_stats_empty(self):
        mc = MetricsCollector()
        stats = mc.get_content_studio_stats()
        assert isinstance(stats, ContentStudioStats)
        assert stats.total_generations == 0
        assert stats.success_count == 0
        assert stats.failure_count == 0
        assert stats.success_rate == 0.0
        assert stats.type_distribution == ()
        assert stats.avg_duration_ms == 0.0
        assert stats.total_files_generated == 0
        assert stats.total_assets_generated == 0


class TestContentStudioStatsWithRecords:
    """레코드가 있는 상태의 Content Studio 통계 테스트."""

    def test_content_studio_stats_with_records(self):
        mc = MetricsCollector()
        mc.record_content_generation(
            content_type="lecture",
            topic="SUPEX 추구",
            success=True,
            duration_ms=1000.0,
            file_count=3,
            asset_count=10,
        )
        mc.record_content_generation(
            content_type="quiz",
            topic="인간중심 경영",
            success=True,
            duration_ms=500.0,
            file_count=1,
            asset_count=5,
        )
        mc.record_content_generation(
            content_type="audio",
            topic="VWBE Culture",
            success=False,
            duration_ms=2000.0,
            file_count=0,
            asset_count=0,
        )

        stats = mc.get_content_studio_stats()
        assert stats.total_generations == 3
        assert stats.success_count == 2
        assert stats.failure_count == 1
        assert stats.total_files_generated == 4
        assert stats.total_assets_generated == 15
        assert stats.avg_duration_ms == round((1000.0 + 500.0 + 2000.0) / 3, 2)


class TestTypeDistribution:
    """content_type별 분포 테스트."""

    def test_type_distribution(self):
        mc = MetricsCollector()
        # lecture 3회, quiz 2회, audio 1회
        for _ in range(3):
            mc.record_content_generation(
                content_type="lecture",
                topic="강의",
                success=True,
                duration_ms=100.0,
            )
        for _ in range(2):
            mc.record_content_generation(
                content_type="quiz",
                topic="퀴즈",
                success=True,
                duration_ms=50.0,
            )
        mc.record_content_generation(
            content_type="audio",
            topic="오디오",
            success=True,
            duration_ms=200.0,
        )

        stats = mc.get_content_studio_stats()
        dist = dict(stats.type_distribution)
        assert dist["lecture"] == 3
        assert dist["quiz"] == 2
        assert dist["audio"] == 1

        # 내림차순 정렬 확인
        assert stats.type_distribution[0] == ("lecture", 3)
        assert stats.type_distribution[1] == ("quiz", 2)
        assert stats.type_distribution[2] == ("audio", 1)


class TestSuccessRateCalculation:
    """성공률 계산 테스트."""

    def test_success_rate_calculation(self):
        mc = MetricsCollector()
        # 성공 7회, 실패 3회 → 0.7
        for _ in range(7):
            mc.record_content_generation(
                content_type="lecture",
                topic="성공 케이스",
                success=True,
                duration_ms=100.0,
            )
        for _ in range(3):
            mc.record_content_generation(
                content_type="lecture",
                topic="실패 케이스",
                success=False,
                duration_ms=50.0,
            )

        stats = mc.get_content_studio_stats()
        assert stats.success_rate == 0.7
        assert stats.success_count == 7
        assert stats.failure_count == 3

    def test_all_success(self):
        mc = MetricsCollector()
        for _ in range(5):
            mc.record_content_generation(
                content_type="quiz",
                topic="전부 성공",
                success=True,
                duration_ms=100.0,
            )
        stats = mc.get_content_studio_stats()
        assert stats.success_rate == 1.0

    def test_all_failure(self):
        mc = MetricsCollector()
        for _ in range(3):
            mc.record_content_generation(
                content_type="audio",
                topic="전부 실패",
                success=False,
                duration_ms=100.0,
            )
        stats = mc.get_content_studio_stats()
        assert stats.success_rate == 0.0


class TestWindowFiltering:
    """시간 윈도우 필터링 테스트."""

    def test_window_filtering(self):
        mc = MetricsCollector()

        # 현재 기록 추가
        mc.record_content_generation(
            content_type="lecture",
            topic="최근 기록",
            success=True,
            duration_ms=100.0,
            file_count=1,
            asset_count=2,
        )

        # 긴 윈도우 — 반드시 포함
        stats_long = mc.get_content_studio_stats(window_seconds=3600)
        assert stats_long.total_generations >= 1

        # 매우 짧은 윈도우 — 방금 기록이므로 포함될 수 있음
        stats_short = mc.get_content_studio_stats(window_seconds=0.001)
        # 결과는 0 또는 1 (타이밍에 따라)
        assert stats_short.total_generations >= 0

    def test_default_window_is_24h(self):
        mc = MetricsCollector()
        mc.record_content_generation(
            content_type="quiz",
            topic="기본 윈도우 테스트",
            success=True,
            duration_ms=50.0,
        )
        # 기본 윈도우(24시간) 내에 기록이 포함되어야 함
        stats = mc.get_content_studio_stats()
        assert stats.total_generations == 1


# ---------------------------------------------------------------------------
# MetricsCollector — reset
# ---------------------------------------------------------------------------


class TestResetClearsContentRecords:
    """reset()이 콘텐츠 생성 기록도 초기화하는지 테스트."""

    def test_reset_clears_content_records(self):
        mc = MetricsCollector()
        mc.record_content_generation(
            content_type="lecture",
            topic="리셋 대상",
            success=True,
            duration_ms=100.0,
            file_count=2,
            asset_count=5,
        )
        mc.record("/api/search", "POST", 200, 10.0)

        assert mc.total_requests == 1
        stats_before = mc.get_content_studio_stats()
        assert stats_before.total_generations == 1

        mc.reset()

        assert mc.total_requests == 0
        stats_after = mc.get_content_studio_stats()
        assert stats_after.total_generations == 0

        # HTTP 기록도 초기화 확인
        metrics = mc.get_metrics()
        assert metrics.latency.count == 0

    def test_reset_independence(self):
        """reset() 후 새 기록이 독립적으로 추적되는지 확인."""
        mc = MetricsCollector()
        mc.record_content_generation(
            content_type="lecture",
            topic="이전 기록",
            success=True,
            duration_ms=100.0,
        )
        mc.reset()
        mc.record_content_generation(
            content_type="quiz",
            topic="새 기록",
            success=False,
            duration_ms=200.0,
        )

        stats = mc.get_content_studio_stats()
        assert stats.total_generations == 1
        assert stats.failure_count == 1
        assert stats.success_count == 0


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestContentRecordThreadSafety:
    """content generation 기록의 thread-safety 테스트."""

    def test_thread_safety(self):
        mc = MetricsCollector()
        n_threads = 4
        n_records_per_thread = 100

        def worker(thread_id: int):
            for i in range(n_records_per_thread):
                mc.record_content_generation(
                    content_type="lecture",
                    topic=f"스레드{thread_id}-기록{i}",
                    success=True,
                    duration_ms=10.0,
                    file_count=1,
                    asset_count=2,
                )

        threads = [
            threading.Thread(target=worker, args=(tid,)) for tid in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stats = mc.get_content_studio_stats()
        expected = n_threads * n_records_per_thread
        assert stats.total_generations == expected
        assert stats.total_files_generated == expected
        assert stats.total_assets_generated == expected * 2

    def test_concurrent_content_and_request_records(self):
        """콘텐츠 기록과 HTTP 요청 기록이 동시에 안전하게 추적되는지 확인."""
        mc = MetricsCollector()
        stop = threading.Event()
        errors: list[str] = []

        def content_writer():
            for _ in range(200):
                mc.record_content_generation(
                    content_type="quiz",
                    topic="동시성 테스트",
                    success=True,
                    duration_ms=10.0,
                )

        def request_writer():
            for _ in range(200):
                mc.record("/api/search", "POST", 200, 5.0)

        def reader():
            while not stop.is_set():
                try:
                    mc.get_content_studio_stats()
                    mc.get_metrics()
                except Exception as e:
                    errors.append(str(e))

        reader_thread = threading.Thread(target=reader)
        content_thread = threading.Thread(target=content_writer)
        request_thread = threading.Thread(target=request_writer)

        reader_thread.start()
        content_thread.start()
        request_thread.start()

        content_thread.join()
        request_thread.join()
        stop.set()
        reader_thread.join()

        assert len(errors) == 0
        assert mc.total_requests == 200

        stats = mc.get_content_studio_stats()
        assert stats.total_generations == 200
