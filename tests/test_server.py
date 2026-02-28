"""FastAPI 서버 테스트.

PR-013: API 엔드포인트 + 미들웨어 + 에러 핸들링.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from scripts.lib.search_types import SearchHit  # noqa: E402
from server.app import create_app  # noqa: E402
from server.dependencies import AppState  # noqa: E402
from server.models import (  # noqa: E402
    ContentStudioHealthResponse,
    ErrorResponse,
    GenerateRequest,
    GenerateResponse,
    HealthResponse,
    SearchHitResponse,
    SearchRequest,
    SearchResponse,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_search_hit(**overrides) -> SearchHit:
    """테스트용 SearchHit."""
    defaults = {
        "quote_id": "2020-14차|VWBE|definition|001",
        "text": "VWBE Culture 정의",
        "score": 0.85,
        "edition_id": "2020-14차",
        "year": 2020,
        "revision_num": 14,
        "quote_type": "definition",
        "section_path": ("VWBE Culture",),
        "source": "hybrid",
        "content_hash": "a" * 64,
        "quality_flags": (),
    }
    defaults.update(overrides)
    return SearchHit(**defaults)


@pytest.fixture()
def mock_state():
    """초기화된 mock AppState."""
    state = AppState()
    state._initialized = True

    # Mock search service
    mock_search = MagicMock()
    mock_search.hybrid_search.return_value = [_make_search_hit()]
    mock_search.vector_search.return_value = [_make_search_hit(source="vector")]
    mock_search.bm25_search.return_value = [_make_search_hit(source="bm25")]
    state.search_service = mock_search

    # Mock generation service
    mock_gen = MagicMock()
    mock_gen_result = MagicMock()
    mock_gen_result.answer = "LLM 생성 답변"
    mock_gen_result.prompt_name = "answer.md"
    mock_gen_result.validation_passed = None
    mock_gen.generate.return_value = mock_gen_result
    state.generation_service = mock_gen

    return state


def FastAPI_with_mock_state(state: AppState):
    """Mock state를 사용하는 FastAPI 앱."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from server.routes.generate import create_generate_router
    from server.routes.health import create_health_router
    from server.routes.search import create_search_router

    app = FastAPI(title="Test")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(create_health_router(state))
    app.include_router(create_search_router(state))
    app.include_router(create_generate_router(state))
    return app


# ---------------------------------------------------------------------------
# Pydantic 모델 테스트
# ---------------------------------------------------------------------------


def test_search_request_defaults():
    """SearchRequest 기본값."""
    req = SearchRequest(query="test")
    assert req.mode == "hybrid"
    assert req.top_k == 5


def test_search_request_validation():
    """SearchRequest 유효성 검증."""
    with pytest.raises(Exception):  # pydantic ValidationError
        SearchRequest(query="")  # min_length=1


def test_search_request_mode_validation():
    """SearchRequest mode 유효성 검증."""
    with pytest.raises(Exception):
        SearchRequest(query="test", mode="invalid")


def test_generate_request_defaults():
    """GenerateRequest 기본값."""
    req = GenerateRequest(query="test")
    assert req.output_type is None
    assert req.top_k == 5


def test_generate_request_invalid_output_type():
    """유효하지 않은 output_type → ValidationError."""
    with pytest.raises(Exception):
        GenerateRequest(query="test", output_type="invalid_type")


def test_health_response():
    """HealthResponse 생성."""
    resp = HealthResponse(
        status="ok",
        version="0.1.0",
        components={"search_service": True},
    )
    assert resp.status == "ok"


def test_error_response():
    """ErrorResponse 생성."""
    resp = ErrorResponse(error="not_found", detail="리소스 없음")
    assert resp.error == "not_found"


def test_search_hit_response():
    """SearchHitResponse 생성."""
    resp = SearchHitResponse(
        quote_id="test|001",
        text="테스트",
        score=0.9,
        edition_id="2020-14차",
        year=2020,
        quote_type="definition",
        section_path=["VWBE"],
        source="hybrid",
    )
    assert resp.quote_id == "test|001"


# ---------------------------------------------------------------------------
# Health API 테스트
# ---------------------------------------------------------------------------


def test_health_endpoint(mock_state):
    """GET /api/health 응답."""
    app = FastAPI_with_mock_state(mock_state)
    with TestClient(app) as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["components"]["initialized"] is True


def test_health_not_initialized():
    """초기화 전 /api/health → 503."""
    state = AppState()
    app = FastAPI_with_mock_state(state)
    with TestClient(app) as client:
        resp = client.get("/api/health")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "initializing"


# ---------------------------------------------------------------------------
# Search API 테스트
# ---------------------------------------------------------------------------


def test_search_hybrid(mock_state):
    """POST /api/search (hybrid)."""
    app = FastAPI_with_mock_state(mock_state)
    with TestClient(app) as client:
        resp = client.post("/api/search", json={"query": "SUPEX란?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "hybrid"
    assert data["total"] > 0
    assert data["hits"][0]["quote_id"] == "2020-14차|VWBE|definition|001"


def test_search_vector(mock_state):
    """POST /api/search (vector)."""
    app = FastAPI_with_mock_state(mock_state)
    with TestClient(app) as client:
        resp = client.post("/api/search", json={"query": "test", "mode": "vector"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "vector"


def test_search_bm25(mock_state):
    """POST /api/search (bm25)."""
    app = FastAPI_with_mock_state(mock_state)
    with TestClient(app) as client:
        resp = client.post("/api/search", json={"query": "test", "mode": "bm25"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "bm25"


def test_search_with_filters(mock_state):
    """POST /api/search with edition_filter."""
    app = FastAPI_with_mock_state(mock_state)
    with TestClient(app) as client:
        resp = client.post(
            "/api/search",
            json={
                "query": "test",
                "edition_filter": "2020-14차",
                "type_filter": ["definition"],
                "top_k": 10,
            },
        )
    assert resp.status_code == 200
    # Verify filters were passed to service
    mock_state.search_service.hybrid_search.assert_called_once()
    call_kwargs = mock_state.search_service.hybrid_search.call_args
    assert call_kwargs.kwargs["edition_filter"] == "2020-14차"


def test_search_service_unavailable():
    """검색 서비스 미초기화 → 503."""
    state = AppState()
    state._initialized = True
    app = FastAPI_with_mock_state(state)
    with TestClient(app) as client:
        resp = client.post("/api/search", json={"query": "test"})
    assert resp.status_code == 503


def test_search_invalid_request():
    """유효하지 않은 요청 → 422."""
    state = AppState()
    state._initialized = True
    app = FastAPI_with_mock_state(state)
    with TestClient(app) as client:
        resp = client.post("/api/search", json={"query": ""})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Generate API 테스트
# ---------------------------------------------------------------------------


def test_generate_basic(mock_state):
    """POST /api/generate 기본 생성."""
    app = FastAPI_with_mock_state(mock_state)
    with TestClient(app) as client:
        resp = client.post("/api/generate", json={"query": "SUPEX란 무엇인가?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "LLM 생성 답변"
    assert data["search_hits_count"] > 0


def test_generate_with_output_type(mock_state):
    """POST /api/generate with output_type."""
    app = FastAPI_with_mock_state(mock_state)
    with TestClient(app) as client:
        resp = client.post(
            "/api/generate",
            json={"query": "카드 만들어줘", "output_type": "card"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "content_generation"


def test_generate_no_search_service():
    """검색 서비스 미초기화 → 503."""
    state = AppState()
    state._initialized = True
    mock_gen = MagicMock()
    state.generation_service = mock_gen
    app = FastAPI_with_mock_state(state)
    with TestClient(app) as client:
        resp = client.post("/api/generate", json={"query": "test"})
    assert resp.status_code == 503


def test_generate_no_gen_service():
    """생성 서비스 미초기화 → 503."""
    state = AppState()
    state._initialized = True
    state.search_service = MagicMock()
    app = FastAPI_with_mock_state(state)
    with TestClient(app) as client:
        resp = client.post("/api/generate", json={"query": "test"})
    assert resp.status_code == 503


def test_generate_no_results(mock_state):
    """검색 결과 없으면 빈 답변."""
    mock_state.search_service.hybrid_search.return_value = []
    app = FastAPI_with_mock_state(mock_state)
    with TestClient(app) as client:
        resp = client.post("/api/generate", json={"query": "nonexistent"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["search_hits_count"] == 0


# ---------------------------------------------------------------------------
# Health API — Content Studio 확장 테스트 (TD-009)
# ---------------------------------------------------------------------------


class _MockContentStudio:
    """Content Studio 헬스체크 테스트용 mock.

    has_planner, has_generator 등의 property를 제공한다.
    """

    def __init__(
        self,
        *,
        has_planner: bool = True,
        has_generator: bool = True,
        has_asset_generator: bool = True,
        has_assembler: bool = True,
        has_plan_cache: bool = True,
    ) -> None:
        self._has_planner = has_planner
        self._has_generator = has_generator
        self._has_asset_generator = has_asset_generator
        self._has_assembler = has_assembler
        self._has_plan_cache = has_plan_cache

    @property
    def has_planner(self) -> bool:
        return self._has_planner

    @property
    def has_generator(self) -> bool:
        return self._has_generator

    @property
    def has_asset_generator(self) -> bool:
        return self._has_asset_generator

    @property
    def has_assembler(self) -> bool:
        return self._has_assembler

    @property
    def has_plan_cache(self) -> bool:
        return self._has_plan_cache


def test_health_with_content_studio(mock_state):
    """TD-009: Content Studio 초기화된 상태에서 health 응답에 content_studio 포함."""
    mock_state.content_studio = _MockContentStudio()
    app = FastAPI_with_mock_state(mock_state)
    with TestClient(app) as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    # 기존 필드 유지 (backward compatible)
    assert "components" in data
    assert data["components"]["initialized"] is True
    # Content Studio 필드 확인
    cs = data["content_studio"]
    assert cs is not None
    assert cs["available"] is True
    assert cs["has_planner"] is True
    assert cs["has_generator"] is True
    assert cs["has_asset_generator"] is True
    assert cs["has_assembler"] is True
    assert cs["has_plan_cache"] is True


def test_health_without_content_studio(mock_state):
    """TD-009: Content Studio 미초기화 → content_studio 필드 None."""
    mock_state.content_studio = None
    app = FastAPI_with_mock_state(mock_state)
    with TestClient(app) as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    # content_studio가 None이면 JSON에서 null로 직렬화
    assert data["content_studio"] is None


def test_health_content_studio_partial(mock_state):
    """TD-009: Content Studio 일부 서비스만 활성화."""
    mock_state.content_studio = _MockContentStudio(
        has_planner=True,
        has_generator=False,
        has_asset_generator=True,
        has_assembler=False,
        has_plan_cache=False,
    )
    app = FastAPI_with_mock_state(mock_state)
    with TestClient(app) as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    cs = data["content_studio"]
    assert cs["available"] is True
    assert cs["has_planner"] is True
    assert cs["has_generator"] is False
    assert cs["has_asset_generator"] is True
    assert cs["has_assembler"] is False
    assert cs["has_plan_cache"] is False


def test_health_content_studio_backward_compatible():
    """TD-009: Content Studio가 없는 상태에서도 기존 health 응답 형식 유지."""
    state = AppState()
    state._initialized = True
    state.search_service = MagicMock()
    state.generation_service = MagicMock()
    state.toc_service = MagicMock()
    # content_studio는 기본 None
    app = FastAPI_with_mock_state(state)
    with TestClient(app) as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] is not None
    assert data["components"]["search_service"] is True
    assert data["components"]["generation_service"] is True
    assert data["components"]["toc_service"] is True
    assert data["content_studio"] is None


def test_health_content_studio_health_response_model():
    """TD-009: ContentStudioHealthResponse Pydantic 모델 직접 테스트."""
    model = ContentStudioHealthResponse(
        available=True,
        has_planner=False,
        has_generator=True,
        has_asset_generator=False,
        has_assembler=True,
        has_plan_cache=False,
    )
    assert model.available is True
    assert model.has_planner is False
    assert model.has_generator is True
    assert model.has_asset_generator is False
    assert model.has_assembler is True
    assert model.has_plan_cache is False

    # JSON 직렬화 확인
    dumped = model.model_dump()
    assert dumped == {
        "available": True,
        "has_planner": False,
        "has_generator": True,
        "has_asset_generator": False,
        "has_assembler": True,
        "has_plan_cache": False,
    }


def test_health_response_model_with_content_studio():
    """TD-009: HealthResponse에 content_studio 포함 시 직렬화 확인."""
    resp = HealthResponse(
        status="ok",
        version="0.2.0",
        components={"initialized": True},
        content_studio=ContentStudioHealthResponse(
            available=True,
            has_planner=True,
            has_generator=True,
            has_asset_generator=True,
            has_assembler=True,
            has_plan_cache=True,
        ),
    )
    dumped = resp.model_dump()
    assert dumped["content_studio"]["available"] is True
    assert dumped["content_studio"]["has_planner"] is True


def test_health_response_model_without_content_studio():
    """TD-009: HealthResponse에 content_studio 없으면 None."""
    resp = HealthResponse(
        status="ok",
        version="0.2.0",
        components={"initialized": True},
    )
    assert resp.content_studio is None
    dumped = resp.model_dump()
    assert dumped["content_studio"] is None


# ---------------------------------------------------------------------------
# AppState 테스트
# ---------------------------------------------------------------------------


def test_app_state_initial():
    """AppState 초기 상태."""
    state = AppState()
    assert not state.is_ready
    assert state.search_service is None
    assert state.generation_service is None
