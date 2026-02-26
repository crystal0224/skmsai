"""운영 대시보드 API 라우트.

PR-035: 모니터링 + 사용 통계 대시보드.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from scripts.lib.metrics_collector import MetricsCollector
from server.dependencies import AppState
from server.models import (
    DashboardMetricsResponse,
    EndpointStatsResponse,
    LatencyStatsResponse,
    UsageStatsResponse,
)


def create_dashboard_router(
    state: AppState,
    collector: MetricsCollector,
) -> APIRouter:
    """대시보드 라우터를 생성한다."""
    router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

    @router.get("/metrics", response_model=DashboardMetricsResponse)
    async def get_metrics(
        window: float = Query(
            default=3600.0,
            ge=60.0,
            le=86400.0,
            description="조회 시간 윈도우 (초, 기본 1시간)",
        ),
    ) -> DashboardMetricsResponse:
        """실시간 메트릭을 반환한다."""
        metrics = collector.get_metrics(window_seconds=window)

        latency = LatencyStatsResponse(
            p50=metrics.latency.p50,
            p95=metrics.latency.p95,
            p99=metrics.latency.p99,
            mean=metrics.latency.mean,
            min=metrics.latency.min,
            max=metrics.latency.max,
            count=metrics.latency.count,
        )

        endpoints = [
            EndpointStatsResponse(
                endpoint=ep.endpoint,
                method=ep.method,
                total_requests=ep.total_requests,
                success_count=ep.success_count,
                error_count=ep.error_count,
                error_rate=ep.error_rate,
                latency=LatencyStatsResponse(
                    p50=ep.latency.p50,
                    p95=ep.latency.p95,
                    p99=ep.latency.p99,
                    mean=ep.latency.mean,
                    min=ep.latency.min,
                    max=ep.latency.max,
                    count=ep.latency.count,
                ),
            )
            for ep in metrics.endpoints
        ]

        return DashboardMetricsResponse(
            total_requests=metrics.total_requests,
            success_count=metrics.success_count,
            error_count=metrics.error_count,
            error_rate=metrics.error_rate,
            latency=latency,
            uptime_seconds=metrics.uptime_seconds,
            window_seconds=metrics.window_seconds,
            endpoints=endpoints,
        )

    @router.get("/stats", response_model=UsageStatsResponse)
    async def get_usage_stats(
        window: float = Query(
            default=86400.0,
            ge=60.0,
            le=604800.0,
            description="조회 시간 윈도우 (초, 기본 24시간)",
        ),
    ) -> UsageStatsResponse:
        """사용 통계를 반환한다."""
        stats = collector.get_usage_stats(window_seconds=window)

        return UsageStatsResponse(
            total_requests=stats.total_requests,
            requests_per_minute=stats.requests_per_minute,
            top_endpoints=[
                {"endpoint": ep, "count": cnt} for ep, cnt in stats.top_endpoints
            ],
            status_code_distribution=[
                {"status_code": code, "count": cnt}
                for code, cnt in stats.status_code_distribution
            ],
            hourly_counts=[{"hour": h, "count": cnt} for h, cnt in stats.hourly_counts],
        )

    @router.get("/health-detail")
    async def get_health_detail() -> dict:
        """서비스 상태 상세 정보를 반환한다."""
        components = {
            "search_service": {
                "available": state.search_service is not None,
            },
            "generation_service": {
                "available": state.generation_service is not None,
            },
            "toc_service": {
                "available": state.toc_service is not None,
            },
            "evidence_filter": {
                "available": state.evidence_filter is not None,
            },
            "comparison_service": {
                "available": state.comparison_service is not None,
            },
        }

        return {
            "status": "ok" if state.is_ready else "initializing",
            "version": state.version,
            "components": components,
            "metrics_summary": {
                "total_requests": collector.total_requests,
                "uptime_seconds": round(collector.get_metrics(60).uptime_seconds, 1),
            },
        }

    return router
