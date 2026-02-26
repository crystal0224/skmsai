"""대시보드 API 라우트 테스트.

PR-035: 운영 대시보드 API 엔드포인트 테스트.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scripts.lib.metrics_collector import MetricsCollector
from server.dependencies import AppState
from server.routes.dashboard import create_dashboard_router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def collector() -> MetricsCollector:
    """테스트용 MetricsCollector."""
    return MetricsCollector()


@pytest.fixture()
def state() -> AppState:
    """테스트용 AppState (초기화 안 됨)."""
    return AppState()


@pytest.fixture()
def client(state: AppState, collector: MetricsCollector) -> TestClient:
    """테스트용 FastAPI TestClient."""
    app = FastAPI()
    app.include_router(create_dashboard_router(state, collector))
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/dashboard/metrics
# ---------------------------------------------------------------------------


class TestDashboardMetrics:
    """GET /api/dashboard/metrics 엔드포인트 테스트."""

    def test_empty_metrics(self, client: TestClient):
        resp = client.get("/api/dashboard/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_requests"] == 0
        assert data["success_count"] == 0
        assert data["error_count"] == 0
        assert data["error_rate"] == 0.0
        assert data["latency"]["count"] == 0
        assert data["endpoints"] == []

    def test_with_records(self, client: TestClient, collector: MetricsCollector):
        collector.record("/api/search", "POST", 200, 15.0)
        collector.record("/api/search", "POST", 200, 25.0)
        collector.record("/api/generate", "POST", 500, 100.0)

        resp = client.get("/api/dashboard/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_requests"] == 3
        assert data["success_count"] == 2
        assert data["error_count"] == 1
        assert len(data["endpoints"]) == 2

    def test_latency_fields(self, client: TestClient, collector: MetricsCollector):
        for d in [10.0, 20.0, 30.0]:
            collector.record("/api/search", "POST", 200, d)

        resp = client.get("/api/dashboard/metrics")
        data = resp.json()
        latency = data["latency"]
        assert "p50" in latency
        assert "p95" in latency
        assert "p99" in latency
        assert "mean" in latency
        assert "min" in latency
        assert "max" in latency
        assert latency["count"] == 3

    def test_endpoint_stats_fields(
        self, client: TestClient, collector: MetricsCollector
    ):
        collector.record("/api/search", "POST", 200, 15.0)

        resp = client.get("/api/dashboard/metrics")
        data = resp.json()
        assert len(data["endpoints"]) == 1
        ep = data["endpoints"][0]
        assert ep["endpoint"] == "/api/search"
        assert ep["method"] == "POST"
        assert ep["total_requests"] == 1
        assert ep["success_count"] == 1
        assert ep["error_count"] == 0
        assert ep["error_rate"] == 0.0
        assert "latency" in ep

    def test_window_parameter(self, client: TestClient, collector: MetricsCollector):
        collector.record("/api/search", "POST", 200, 10.0)

        # 기본 윈도우 (1시간)
        resp = client.get("/api/dashboard/metrics")
        assert resp.status_code == 200
        assert resp.json()["window_seconds"] == 3600.0

        # 커스텀 윈도우
        resp = client.get("/api/dashboard/metrics?window=300")
        assert resp.status_code == 200
        assert resp.json()["window_seconds"] == 300.0

    def test_window_validation(self, client: TestClient):
        # 범위 밖: 너무 작음
        resp = client.get("/api/dashboard/metrics?window=10")
        assert resp.status_code == 422

        # 범위 밖: 너무 큼
        resp = client.get("/api/dashboard/metrics?window=100000")
        assert resp.status_code == 422

    def test_uptime_present(self, client: TestClient):
        resp = client.get("/api/dashboard/metrics")
        data = resp.json()
        assert "uptime_seconds" in data
        assert data["uptime_seconds"] >= 0


# ---------------------------------------------------------------------------
# GET /api/dashboard/stats
# ---------------------------------------------------------------------------


class TestDashboardStats:
    """GET /api/dashboard/stats 엔드포인트 테스트."""

    def test_empty_stats(self, client: TestClient):
        resp = client.get("/api/dashboard/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_requests"] == 0
        assert data["top_endpoints"] == []
        assert data["status_code_distribution"] == []

    def test_with_records(self, client: TestClient, collector: MetricsCollector):
        for _ in range(5):
            collector.record("/api/search", "POST", 200, 10.0)
        for _ in range(3):
            collector.record("/api/generate", "POST", 200, 20.0)

        resp = client.get("/api/dashboard/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_requests"] == 8
        assert len(data["top_endpoints"]) == 2
        assert data["top_endpoints"][0]["endpoint"] == "/api/search"
        assert data["top_endpoints"][0]["count"] == 5

    def test_status_code_distribution(
        self, client: TestClient, collector: MetricsCollector
    ):
        collector.record("/api/search", "POST", 200, 10.0)
        collector.record("/api/search", "POST", 200, 10.0)
        collector.record("/api/search", "POST", 422, 10.0)
        collector.record("/api/search", "POST", 500, 10.0)

        resp = client.get("/api/dashboard/stats")
        data = resp.json()
        dist = {d["status_code"]: d["count"] for d in data["status_code_distribution"]}
        assert dist[200] == 2
        assert dist[422] == 1
        assert dist[500] == 1

    def test_hourly_counts(self, client: TestClient, collector: MetricsCollector):
        collector.record("/api/search", "POST", 200, 10.0)

        resp = client.get("/api/dashboard/stats?window=3600")
        data = resp.json()
        assert "hourly_counts" in data
        assert len(data["hourly_counts"]) == 1

    def test_requests_per_minute(self, client: TestClient, collector: MetricsCollector):
        for _ in range(10):
            collector.record("/api/search", "POST", 200, 10.0)

        resp = client.get("/api/dashboard/stats")
        data = resp.json()
        assert data["requests_per_minute"] > 0

    def test_window_parameter(self, client: TestClient, collector: MetricsCollector):
        collector.record("/api/search", "POST", 200, 10.0)

        resp = client.get("/api/dashboard/stats?window=7200")
        assert resp.status_code == 200

    def test_window_validation(self, client: TestClient):
        # 범위 밖
        resp = client.get("/api/dashboard/stats?window=10")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/dashboard/health-detail
# ---------------------------------------------------------------------------


class TestDashboardHealthDetail:
    """GET /api/dashboard/health-detail 엔드포인트 테스트."""

    def test_uninitialized_state(self, client: TestClient):
        resp = client.get("/api/dashboard/health-detail")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "initializing"
        assert "version" in data
        assert "components" in data
        assert "metrics_summary" in data

    def test_component_details(self, client: TestClient):
        resp = client.get("/api/dashboard/health-detail")
        data = resp.json()
        components = data["components"]
        assert "search_service" in components
        assert "generation_service" in components
        assert "toc_service" in components
        assert "evidence_filter" in components
        assert "comparison_service" in components

        # 초기화 안 됨 → 모두 False
        for key in components:
            assert components[key]["available"] is False

    def test_metrics_summary(self, client: TestClient, collector: MetricsCollector):
        collector.record("/api/search", "POST", 200, 10.0)

        resp = client.get("/api/dashboard/health-detail")
        data = resp.json()
        summary = data["metrics_summary"]
        assert summary["total_requests"] == 1
        assert summary["uptime_seconds"] >= 0


# ---------------------------------------------------------------------------
# Integration: 전체 앱에서 대시보드 라우트 등록 확인
# ---------------------------------------------------------------------------


class TestDashboardIntegration:
    """server.app에서 대시보드 라우트 등록 확인."""

    def test_dashboard_routes_registered(self):
        """create_app()에서 대시보드 라우트가 등록되었는지 확인."""
        from server.app import app

        route_paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/api/dashboard/metrics" in route_paths
        assert "/api/dashboard/stats" in route_paths
        assert "/api/dashboard/health-detail" in route_paths

    def test_metrics_collector_exists(self):
        """전역 MetricsCollector 인스턴스가 존재하는지 확인."""
        from server.app import _metrics

        assert isinstance(_metrics, MetricsCollector)
