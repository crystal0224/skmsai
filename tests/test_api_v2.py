"""API v2 테스트.

PR-027: /api/v2/search, /api/v2/generate 엔드포인트 테스트.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.cross_version_comparison import (  # noqa: E402
    ComparisonConfig,
    ComparisonContext,
    CrossVersionComparisonService,
    EditionGroup,
)
from scripts.lib.evidence_filter import (  # noqa: E402
    EvidenceCheckResult,
    EvidenceFilter,
    EvidenceFilterConfig,
)
from scripts.lib.search_types import SearchHit  # noqa: E402
from server.dependencies import AppState  # noqa: E402
from server.models import (  # noqa: E402
    ComparisonResponse,
    EditionGroupResponse,
    EvidenceCheckResponse,
    GenerateV2Request,
    GenerateV2Response,
    SearchV2Request,
    SearchV2Response,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hit(
    quote_id: str = "2020-14차|VWBE|definition|001",
    text: str = "VWBE 정의 텍스트",
    edition_id: str = "2020-14차",
    year: int = 2020,
    quote_type: str = "narrative",
) -> SearchHit:
    """테스트용 SearchHit."""
    return SearchHit(
        quote_id=quote_id,
        text=text,
        score=0.8,
        edition_id=edition_id,
        year=year,
        revision_num=14,
        quote_type=quote_type,
        section_path=("VWBE",),
        source="hybrid",
        content_hash="abc",
        quality_flags=(),
    )


def _make_mock_state() -> AppState:
    """모든 서비스가 모킹된 AppState."""
    state = AppState()

    # SearchService mock
    state.search_service = MagicMock()
    state.search_service.hybrid_search.return_value = [
        _hit("q1", "SUPEX 정의", "2020-14차", 2020, "definition"),
    ]
    state.search_service.vector_search.return_value = [
        _hit("q1", "SUPEX 정의", "2020-14차", 2020, "definition"),
    ]
    state.search_service.bm25_search.return_value = [
        _hit("q1", "SUPEX 정의", "2020-14차", 2020, "definition"),
    ]

    # GenerationService mock
    state.generation_service = MagicMock()
    state.generation_service.generate.return_value = MagicMock(
        answer='{"title":"SUPEX 요약","body":"SUPEX는 최고 수준을 추구합니다.","key_points":["최고수준"],"citations":["2020-14차|_root|def|001"]}',
        prompt_name="content_gen.md",
        validation_passed=True,
    )

    # EvidenceFilter (real instance)
    state.evidence_filter = EvidenceFilter()

    # CrossVersionComparisonService (real instance)
    state.comparison_service = CrossVersionComparisonService()

    state._initialized = True
    return state


# ---------------------------------------------------------------------------
# Pydantic 모델 테스트
# ---------------------------------------------------------------------------


class TestV2Models:
    """V2 Pydantic 모델 테스트."""

    def test_search_v2_request_defaults(self):
        """SearchV2Request 기본값."""
        req = SearchV2Request(query="SUPEX")
        assert req.mode == "hybrid"
        assert req.top_k == 5
        assert req.include_evidence_check is True
        assert req.include_comparison is False

    def test_search_v2_request_custom(self):
        """SearchV2Request 커스텀 값."""
        req = SearchV2Request(
            query="VWBE",
            mode="vector",
            top_k=10,
            include_comparison=True,
        )
        assert req.mode == "vector"
        assert req.include_comparison is True

    def test_generate_v2_request_defaults(self):
        """GenerateV2Request 기본값."""
        req = GenerateV2Request(query="SUPEX란?")
        assert req.output_type is None
        assert req.include_evidence_check is True
        assert req.include_rendered is True

    def test_evidence_check_response(self):
        """EvidenceCheckResponse 필드."""
        resp = EvidenceCheckResponse(
            coverage_score=0.8,
            cited_quote_ids=["q1"],
            valid_quote_ids=["q1"],
            invalid_quote_ids=[],
            hallucination_flags=[],
            passed=True,
        )
        assert resp.coverage_score == 0.8
        assert resp.passed is True

    def test_comparison_response(self):
        """ComparisonResponse 필드."""
        resp = ComparisonResponse(
            edition_count=2,
            concept_name="SUPEX",
            edition_groups=[],
            formatted_prompt="[CROSS-VERSION COMPARISON]",
        )
        assert resp.edition_count == 2

    def test_search_v2_response(self):
        """SearchV2Response 옵셔널 필드."""
        resp = SearchV2Response(
            query="test",
            mode="hybrid",
            hits=[],
            total=0,
        )
        assert resp.evidence_check is None
        assert resp.comparison is None

    def test_generate_v2_response(self):
        """GenerateV2Response 옵셔널 필드."""
        resp = GenerateV2Response(
            query="test",
            intent="open_ended",
            answer="답변",
            prompt_name="answer.md",
            validation_passed=None,
            citations=[],
            search_hits_count=0,
        )
        assert resp.evidence_check is None
        assert resp.rendered is None
        assert resp.render_success is None


# ---------------------------------------------------------------------------
# Search V2 라우트 테스트
# ---------------------------------------------------------------------------


class TestSearchV2Route:
    """POST /api/v2/search 테스트."""

    @pytest.fixture
    def client(self):
        """TestClient."""
        from fastapi.testclient import TestClient

        from server.routes.search_v2 import create_search_v2_router

        state = _make_mock_state()
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(create_search_v2_router(state))
        return TestClient(app)

    def test_basic_search(self, client):
        """기본 검색."""
        resp = client.post(
            "/api/v2/search",
            json={"query": "SUPEX", "include_evidence_check": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "SUPEX"
        assert data["total"] >= 1
        assert data["evidence_check"] is None

    def test_with_evidence_check(self, client):
        """근거 검증 포함."""
        resp = client.post(
            "/api/v2/search",
            json={"query": "SUPEX", "include_evidence_check": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["evidence_check"] is not None
        assert "coverage_score" in data["evidence_check"]
        assert "passed" in data["evidence_check"]

    def test_with_comparison(self, client):
        """개정판 비교 포함."""
        resp = client.post(
            "/api/v2/search",
            json={"query": "SUPEX", "include_comparison": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["comparison"] is not None
        assert "edition_count" in data["comparison"]

    def test_no_search_service(self):
        """검색 서비스 없음 → 503."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from server.routes.search_v2 import create_search_v2_router

        state = AppState()
        app = FastAPI()
        app.include_router(create_search_v2_router(state))
        client = TestClient(app)

        resp = client.post("/api/v2/search", json={"query": "test"})
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Generate V2 라우트 테스트
# ---------------------------------------------------------------------------


class TestGenerateV2Route:
    """POST /api/v2/generate 테스트."""

    @pytest.fixture
    def client(self):
        """TestClient."""
        from fastapi.testclient import TestClient

        from server.routes.generate_v2 import create_generate_v2_router

        state = _make_mock_state()
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(create_generate_v2_router(state))
        return TestClient(app)

    def test_basic_generate(self, client):
        """기본 생성."""
        resp = client.post(
            "/api/v2/generate",
            json={
                "query": "SUPEX란?",
                "include_evidence_check": False,
                "include_rendered": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "SUPEX란?"
        assert data["search_hits_count"] >= 1
        assert data["evidence_check"] is None
        assert data["rendered"] is None

    def test_with_evidence_check(self, client):
        """근거 검증 포함."""
        resp = client.post(
            "/api/v2/generate",
            json={"query": "SUPEX란?", "include_evidence_check": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["evidence_check"] is not None
        assert "passed" in data["evidence_check"]

    def test_with_rendered_summary(self, client):
        """렌더링 포함 (summary)."""
        resp = client.post(
            "/api/v2/generate",
            json={
                "query": "SUPEX란?",
                "output_type": "summary",
                "include_rendered": True,
                "include_evidence_check": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["render_success"] is True
        assert data["rendered"] is not None
        assert "### SUPEX 요약" in data["rendered"]

    def test_no_generation_service(self):
        """생성 서비스 없음 → 503."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from server.routes.generate_v2 import create_generate_v2_router

        state = AppState()
        state.search_service = MagicMock()
        app = FastAPI()
        app.include_router(create_generate_v2_router(state))
        client = TestClient(app)

        resp = client.post("/api/v2/generate", json={"query": "test"})
        assert resp.status_code == 503

    def test_no_search_service(self):
        """검색 서비스 없음 → 503."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from server.routes.generate_v2 import create_generate_v2_router

        state = AppState()
        state.generation_service = MagicMock()
        app = FastAPI()
        app.include_router(create_generate_v2_router(state))
        client = TestClient(app)

        resp = client.post("/api/v2/generate", json={"query": "test"})
        assert resp.status_code == 503

    def test_empty_hits(self, client):
        """검색 결과 없음."""
        # override mock to return empty
        state = _make_mock_state()
        state.search_service.hybrid_search.return_value = []

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from server.routes.generate_v2 import create_generate_v2_router

        app = FastAPI()
        app.include_router(create_generate_v2_router(state))
        c = TestClient(app)

        resp = c.post("/api/v2/generate", json={"query": "없는것"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["search_hits_count"] == 0

    def test_render_not_triggered_without_output_type(self, client):
        """output_type 없으면 렌더링 안 함."""
        resp = client.post(
            "/api/v2/generate",
            json={"query": "SUPEX란?", "include_rendered": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["rendered"] is None
        assert data["render_success"] is None


# ---------------------------------------------------------------------------
# AppState V2 서비스 초기화 테스트
# ---------------------------------------------------------------------------


class TestAppStateV2:
    """AppState v2 서비스 초기화 테스트."""

    def test_default_services_none(self):
        """기본 상태에서 v2 서비스는 None."""
        state = AppState()
        assert state.evidence_filter is None
        assert state.comparison_service is None

    def test_version_updated(self):
        """버전이 0.2.0."""
        state = AppState()
        assert state.version == "0.2.0"
