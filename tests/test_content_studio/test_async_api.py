"""비동기 콘텐츠 생성 API 테스트.

CC-04: POST /api/content/generate/async, GET /api/content/status/{request_id}.
"""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.content_studio import ContentStudio
from src.content_studio.assembler import AssemblerConfig, FileAssembler
from src.content_studio.asset_generator import AssetGenerator
from src.content_studio.generator import ContentGenerator
from src.content_studio.planner import ContentPlanner
from server.routes.content import (
    AsyncGenerateResponse,
    ContentGenerateResponse,
    GenerationJob,
    GenerationStatusResponse,
    _job_store,
    create_content_router,
)


# ---------------------------------------------------------------------------
# Mocks (shared with test_content_api)
# ---------------------------------------------------------------------------


class MockLLMClient:
    async def generate(self, prompt: str) -> str:
        return """{
            "title": "테스트 강의",
            "subtitle": "서브",
            "duration_min": 30,
            "slides": [
                {"index": 1, "title": "소개", "layout": "title_only"},
                {"index": 2, "title": "본론", "layout": "title_content"}
            ]
        }"""


class MockSearchHit:
    def __init__(self):
        self.quote_id = "q-001"
        self.text = "SKMS 원문"
        self.edition_id = "2020-14차"
        self.year = 2020
        self.quote_type = "principle"
        self.section_path = ("1장",)
        self.quality_flags = ()


class MockSearchService:
    def hybrid_search(self, query, *, top_k=None, edition_filter=None):
        return [MockSearchHit()]


class MockGenerationResult:
    answer = "생성된 내용"
    prompt_name = "test"
    validation_passed = True


class MockGenerationService:
    def generate(self, query, context, intent, output_type=None):
        return MockGenerationResult()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _MockState:
    """API 테스트용 AppState mock."""

    def __init__(self, content_studio=None):
        self.content_studio = content_studio


@pytest.fixture
def full_studio(tmp_path) -> ContentStudio:
    """모든 서비스가 활성화된 ContentStudio."""
    llm = MockLLMClient()
    planner = ContentPlanner(llm_client=llm, config={})
    generator = ContentGenerator(
        search_service=MockSearchService(),
        generation_service=MockGenerationService(),
    )
    asset_gen = AssetGenerator(cache_dir=str(tmp_path / "cache"))
    assembler = FileAssembler(AssemblerConfig(output_dir=str(tmp_path / "out")))
    return ContentStudio(
        planner=planner,
        generator=generator,
        asset_generator=asset_gen,
        assembler=assembler,
    )


@pytest.fixture
def no_planner_studio(tmp_path) -> ContentStudio:
    """Planner 없는 ContentStudio."""
    assembler = FileAssembler(AssemblerConfig(output_dir=str(tmp_path / "out")))
    return ContentStudio(assembler=assembler)


@pytest.fixture(autouse=True)
def _clear_job_store():
    """각 테스트 전후로 job store를 비운다."""
    _job_store._jobs = {}
    yield
    _job_store._jobs = {}


@pytest.fixture
def full_client(full_studio) -> TestClient:
    app = FastAPI()
    state = _MockState(content_studio=full_studio)
    app.include_router(create_content_router(state))
    return TestClient(app)


@pytest.fixture
def no_planner_client(no_planner_studio) -> TestClient:
    app = FastAPI()
    state = _MockState(content_studio=no_planner_studio)
    app.include_router(create_content_router(state))
    return TestClient(app)


@pytest.fixture
def no_studio_client() -> TestClient:
    app = FastAPI()
    state = _MockState(content_studio=None)
    app.include_router(create_content_router(state))
    return TestClient(app)


# ---------------------------------------------------------------------------
# POST /api/content/generate/async
# ---------------------------------------------------------------------------


class TestAsyncGenerate:
    def test_async_generate_returns_request_id(self, full_client):
        """비동기 생성 요청이 request_id와 pending 상태를 반환한다."""
        resp = full_client.post(
            "/api/content/generate/async",
            json={
                "content_type": "lecture",
                "topic": "SUPEX 추구",
                "options": {"duration_min": 30},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "request_id" in data
        assert data["status"] == "pending"
        assert len(data["request_id"]) == 36  # UUID4 format

    def test_async_generate_no_planner_503(self, no_planner_client):
        """Planner가 없으면 503을 반환한다."""
        resp = no_planner_client.post(
            "/api/content/generate/async",
            json={"content_type": "lecture", "topic": "테스트"},
        )
        assert resp.status_code == 503

    def test_async_generate_no_studio_503(self, no_studio_client):
        """Content Studio가 초기화되지 않으면 503을 반환한다."""
        resp = no_studio_client.post(
            "/api/content/generate/async",
            json={"content_type": "lecture", "topic": "테스트"},
        )
        assert resp.status_code == 503

    def test_async_generate_invalid_type_422(self, full_client):
        """유효하지 않은 content_type은 422를 반환한다."""
        resp = full_client.post(
            "/api/content/generate/async",
            json={"content_type": "invalid_type", "topic": "테스트"},
        )
        assert resp.status_code == 422

    def test_async_generate_response_model(self, full_client):
        """응답이 AsyncGenerateResponse 스키마에 부합한다."""
        resp = full_client.post(
            "/api/content/generate/async",
            json={"content_type": "lecture", "topic": "SKMS 개요"},
        )
        data = resp.json()
        # Validate by constructing the model
        parsed = AsyncGenerateResponse(**data)
        assert parsed.request_id == data["request_id"]
        assert parsed.status == "pending"


# ---------------------------------------------------------------------------
# GET /api/content/status/{request_id}
# ---------------------------------------------------------------------------


class TestGenerationStatus:
    def test_status_pending(self, full_client):
        """pending 상태의 작업을 조회한다."""
        # 먼저 비동기 생성 요청
        resp = full_client.post(
            "/api/content/generate/async",
            json={"content_type": "lecture", "topic": "테스트 주제"},
        )
        request_id = resp.json()["request_id"]

        # 상태 조회 — BackgroundTasks는 TestClient에서 동기적으로 실행되므로
        # 이미 completed일 수도 있지만, 적어도 상태 조회 자체는 성공해야 한다
        status_resp = full_client.get(f"/api/content/status/{request_id}")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["request_id"] == request_id
        assert data["content_type"] == "lecture"
        assert data["topic"] == "테스트 주제"
        assert data["status"] in ("pending", "running", "completed", "failed")

    def test_status_not_found_404(self, full_client):
        """존재하지 않는 request_id는 404를 반환한다."""
        resp = full_client.get("/api/content/status/nonexistent-id-12345")
        assert resp.status_code == 404

    def test_status_completed(self, full_client):
        """생성 완료된 작업의 상태를 조회한다.

        TestClient의 BackgroundTasks는 동기적으로 실행되므로,
        POST 후 즉시 GET하면 completed 상태를 확인할 수 있다.
        """
        resp = full_client.post(
            "/api/content/generate/async",
            json={
                "content_type": "lecture",
                "topic": "인간중심경영",
                "options": {"duration_min": 20},
            },
        )
        request_id = resp.json()["request_id"]

        status_resp = full_client.get(f"/api/content/status/{request_id}")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["status"] == "completed"
        assert data["completed_at"] is not None
        assert data["error"] is None

        # result가 ContentGenerateResponse 구조인지 확인
        result = data["result"]
        assert result is not None
        assert result["content_type"] == "lecture"
        assert result["topic"] == "인간중심경영"
        assert "files" in result
        assert "citations" in result


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestGenerationJobModel:
    def test_generation_job_frozen(self):
        """GenerationJob은 frozen dataclass이므로 수정 불가."""
        job = GenerationJob(
            request_id="test-id",
            status="pending",
            content_type="lecture",
            topic="테스트",
            created_at=time.time(),
            completed_at=None,
            result=None,
            error=None,
        )
        with pytest.raises(AttributeError):
            job.status = "running"  # type: ignore[misc]

    def test_generation_status_response_model(self):
        """GenerationStatusResponse 모델 필드 검증."""
        resp = GenerationStatusResponse(
            request_id="abc-123",
            status="completed",
            content_type="quiz",
            topic="SKMS 퀴즈",
            created_at=1000.0,
            completed_at=1005.0,
            result=ContentGenerateResponse(
                content_type="quiz",
                topic="SKMS 퀴즈",
                files=[],
                citations=["q-001"],
                metadata={"total_elapsed_ms": 5000},
            ),
            error=None,
        )
        assert resp.request_id == "abc-123"
        assert resp.status == "completed"
        assert resp.result is not None
        assert resp.result.content_type == "quiz"
