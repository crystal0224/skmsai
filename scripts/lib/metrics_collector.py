"""실시간 메트릭 수집기.

PR-035: 운영 대시보드용 인메모리 메트릭 수집.

Thread-safe하게 요청 메트릭을 수집하고, 시간 윈도우 기반 통계를 제공한다.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Sequence


# ---------------------------------------------------------------------------
# Immutable record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RequestRecord:
    """단일 요청 기록 (불변)."""

    endpoint: str
    method: str
    status_code: int
    duration_ms: float
    timestamp: float


@dataclass(frozen=True)
class ContentGenerationRecord:
    """콘텐츠 생성 기록 (불변).

    Content Studio에서 생성된 콘텐츠의 메트릭을 추적한다.
    """

    content_type: str  # lecture, card_news, workshop, visualization, audio, quiz
    topic: str
    success: bool
    duration_ms: float
    file_count: int
    asset_count: int
    timestamp: float


# ---------------------------------------------------------------------------
# Immutable stats snapshots
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LatencyStats:
    """지연 시간 통계 (불변)."""

    p50: float
    p95: float
    p99: float
    mean: float
    min: float
    max: float
    count: int


@dataclass(frozen=True)
class EndpointStats:
    """엔드포인트별 통계 (불변)."""

    endpoint: str
    method: str
    total_requests: int
    success_count: int
    error_count: int
    error_rate: float
    latency: LatencyStats


@dataclass(frozen=True)
class DashboardMetrics:
    """대시보드 메트릭 스냅샷 (불변)."""

    total_requests: int
    success_count: int
    error_count: int
    error_rate: float
    latency: LatencyStats
    uptime_seconds: float
    window_seconds: float
    endpoints: tuple[EndpointStats, ...]


@dataclass(frozen=True)
class UsageStats:
    """사용 통계 스냅샷 (불변)."""

    total_requests: int
    requests_per_minute: float
    top_endpoints: tuple[tuple[str, int], ...]
    status_code_distribution: tuple[tuple[int, int], ...]
    hourly_counts: tuple[tuple[int, int], ...]  # (hour, count)


@dataclass(frozen=True)
class ContentStudioStats:
    """Content Studio 통계 스냅샷 (불변)."""

    total_generations: int
    success_count: int
    failure_count: int
    success_rate: float
    type_distribution: tuple[tuple[str, int], ...]  # (content_type, count)
    avg_duration_ms: float
    total_files_generated: int
    total_assets_generated: int


# ---------------------------------------------------------------------------
# Metrics Collector
# ---------------------------------------------------------------------------


class MetricsCollector:
    """Thread-safe 인메모리 메트릭 수집기.

    최대 max_records개의 요청 기록을 순환 버퍼로 유지한다.
    """

    def __init__(self, max_records: int = 10_000) -> None:
        self._lock = threading.Lock()
        self._records: list[RequestRecord] = []
        self._content_records: list[ContentGenerationRecord] = []
        self._max_records = max_records
        self._start_time = time.time()
        self._total_requests = 0
        self._total_content_generations = 0

    @property
    def total_requests(self) -> int:
        """누적 총 요청 수."""
        with self._lock:
            return self._total_requests

    def record(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        """요청 메트릭을 기록한다."""
        rec = RequestRecord(
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            duration_ms=duration_ms,
            timestamp=time.time(),
        )
        with self._lock:
            self._total_requests += 1
            self._records.append(rec)
            # 순환 버퍼: 최대 크기 초과 시 오래된 기록 제거
            if len(self._records) > self._max_records:
                overflow = len(self._records) - self._max_records
                self._records = self._records[overflow:]

    def record_content_generation(
        self,
        content_type: str,
        topic: str,
        success: bool,
        duration_ms: float,
        file_count: int = 0,
        asset_count: int = 0,
    ) -> None:
        """콘텐츠 생성 메트릭을 기록한다."""
        rec = ContentGenerationRecord(
            content_type=content_type,
            topic=topic,
            success=success,
            duration_ms=duration_ms,
            file_count=file_count,
            asset_count=asset_count,
            timestamp=time.time(),
        )
        with self._lock:
            self._total_content_generations += 1
            self._content_records.append(rec)
            # 순환 버퍼: 최대 크기 초과 시 오래된 기록 제거
            if len(self._content_records) > self._max_records:
                overflow = len(self._content_records) - self._max_records
                self._content_records = self._content_records[overflow:]

    def get_metrics(self, window_seconds: float = 3600.0) -> DashboardMetrics:
        """시간 윈도우 내 메트릭 스냅샷을 반환한다.

        Args:
            window_seconds: 조회할 시간 윈도우 (기본 1시간).
        """
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            total = self._total_requests
            uptime = now - self._start_time
            windowed = [r for r in self._records if r.timestamp >= cutoff]

        if not windowed:
            empty_latency = LatencyStats(
                p50=0.0, p95=0.0, p99=0.0, mean=0.0, min=0.0, max=0.0, count=0
            )
            return DashboardMetrics(
                total_requests=total,
                success_count=0,
                error_count=0,
                error_rate=0.0,
                latency=empty_latency,
                uptime_seconds=uptime,
                window_seconds=window_seconds,
                endpoints=(),
            )

        durations = [r.duration_ms for r in windowed]
        success = sum(1 for r in windowed if r.status_code < 400)
        errors = len(windowed) - success

        overall_latency = _compute_latency(durations)

        # 엔드포인트별 통계
        groups: dict[tuple[str, str], list[RequestRecord]] = defaultdict(list)
        for r in windowed:
            groups[(r.endpoint, r.method)].append(r)

        endpoint_stats: list[EndpointStats] = []
        for (ep, method), records in sorted(
            groups.items(), key=lambda x: len(x[1]), reverse=True
        ):
            ep_durations = [r.duration_ms for r in records]
            ep_success = sum(1 for r in records if r.status_code < 400)
            ep_errors = len(records) - ep_success
            ep_error_rate = ep_errors / len(records) if records else 0.0

            endpoint_stats.append(
                EndpointStats(
                    endpoint=ep,
                    method=method,
                    total_requests=len(records),
                    success_count=ep_success,
                    error_count=ep_errors,
                    error_rate=round(ep_error_rate, 4),
                    latency=_compute_latency(ep_durations),
                )
            )

        error_rate = errors / len(windowed) if windowed else 0.0

        return DashboardMetrics(
            total_requests=total,
            success_count=success,
            error_count=errors,
            error_rate=round(error_rate, 4),
            latency=overall_latency,
            uptime_seconds=round(uptime, 1),
            window_seconds=window_seconds,
            endpoints=tuple(endpoint_stats),
        )

    def get_usage_stats(self, window_seconds: float = 86400.0) -> UsageStats:
        """사용 통계를 반환한다.

        Args:
            window_seconds: 조회할 시간 윈도우 (기본 24시간).
        """
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            total = self._total_requests
            uptime = now - self._start_time
            windowed = [r for r in self._records if r.timestamp >= cutoff]

        # RPM (Requests Per Minute)
        elapsed_minutes = min(uptime, window_seconds) / 60.0
        rpm = len(windowed) / elapsed_minutes if elapsed_minutes > 0 else 0.0

        # Top endpoints
        ep_counts: dict[str, int] = defaultdict(int)
        for r in windowed:
            ep_counts[r.endpoint] += 1
        top_endpoints = sorted(ep_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        # Status code distribution
        status_counts: dict[int, int] = defaultdict(int)
        for r in windowed:
            status_counts[r.status_code] += 1
        status_dist = sorted(status_counts.items())

        # Hourly counts (last 24h)
        hourly: dict[int, int] = defaultdict(int)
        for r in windowed:
            hour = int((r.timestamp - cutoff) / 3600)
            hourly[hour] += 1
        max_hours = int(window_seconds / 3600)
        hourly_counts = tuple((h, hourly.get(h, 0)) for h in range(max_hours))

        return UsageStats(
            total_requests=total,
            requests_per_minute=round(rpm, 2),
            top_endpoints=tuple(top_endpoints),
            status_code_distribution=tuple(status_dist),
            hourly_counts=hourly_counts,
        )

    def get_content_studio_stats(
        self, window_seconds: float = 86400.0
    ) -> ContentStudioStats:
        """Content Studio 통계를 반환한다.

        Args:
            window_seconds: 조회할 시간 윈도우 (기본 24시간).
        """
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            windowed = [r for r in self._content_records if r.timestamp >= cutoff]

        if not windowed:
            return ContentStudioStats(
                total_generations=0,
                success_count=0,
                failure_count=0,
                success_rate=0.0,
                type_distribution=(),
                avg_duration_ms=0.0,
                total_files_generated=0,
                total_assets_generated=0,
            )

        success_count = sum(1 for r in windowed if r.success)
        failure_count = len(windowed) - success_count
        success_rate = success_count / len(windowed)

        # content_type별 분포
        type_counts: dict[str, int] = defaultdict(int)
        for r in windowed:
            type_counts[r.content_type] += 1
        type_distribution = sorted(
            type_counts.items(), key=lambda x: x[1], reverse=True
        )

        avg_duration = sum(r.duration_ms for r in windowed) / len(windowed)
        total_files = sum(r.file_count for r in windowed)
        total_assets = sum(r.asset_count for r in windowed)

        return ContentStudioStats(
            total_generations=len(windowed),
            success_count=success_count,
            failure_count=failure_count,
            success_rate=round(success_rate, 4),
            type_distribution=tuple(type_distribution),
            avg_duration_ms=round(avg_duration, 2),
            total_files_generated=total_files,
            total_assets_generated=total_assets,
        )

    def reset(self) -> None:
        """메트릭을 초기화한다 (테스트용)."""
        with self._lock:
            self._records.clear()
            self._content_records.clear()
            self._total_requests = 0
            self._total_content_generations = 0
            self._start_time = time.time()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_latency(durations: Sequence[float]) -> LatencyStats:
    """지연 시간 통계를 계산한다."""
    if not durations:
        return LatencyStats(
            p50=0.0, p95=0.0, p99=0.0, mean=0.0, min=0.0, max=0.0, count=0
        )

    sorted_d = sorted(durations)
    n = len(sorted_d)

    return LatencyStats(
        p50=round(_percentile(sorted_d, 50), 2),
        p95=round(_percentile(sorted_d, 95), 2),
        p99=round(_percentile(sorted_d, 99), 2),
        mean=round(sum(sorted_d) / n, 2),
        min=round(sorted_d[0], 2),
        max=round(sorted_d[-1], 2),
        count=n,
    )


def _percentile(sorted_values: list[float], pct: float) -> float:
    """정렬된 값 리스트에서 백분위수를 계산한다."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    idx = (pct / 100.0) * (n - 1)
    lower = int(idx)
    upper = min(lower + 1, n - 1)
    frac = idx - lower
    return sorted_values[lower] + frac * (sorted_values[upper] - sorted_values[lower])
