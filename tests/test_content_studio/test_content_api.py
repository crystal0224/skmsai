"""Content Studio API 라우트 테스트.

PR-047: POST /api/content/generate, POST /api/content/plan, GET /api/content/types.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.content_studio import ContentStudio
from src.content_studio.assembler import AssemblerConfig, FileAssembler
from src.content_studio.asset_generator import AssetGenerator
from src.content_studio.generator import ContentGenerator
from src.content_studio.models import (
    ContentOptions,
    GeneratedAsset,
)
from src.content_studio.planner import ContentPlanner
from server.routes.content import create_content_router

# Mock classes imported from conftest (auto-discovered by pytest)
from tests.test_content_studio.conftest import (
    MockLLMClient,
    MockSearchService,
    MockGenerationService,
)


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


# ---------------------------------------------------------------------------
# GET /api/content/types
# ---------------------------------------------------------------------------


class TestContentTypesEndpoint:
    def test_list_types(self, full_client):
        resp = full_client.get("/api/content/types")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 6
        type_names = {t["type"] for t in data["types"]}
        assert "lecture" in type_names
        assert "quiz" in type_names

    def test_types_have_labels(self, full_client):
        resp = full_client.get("/api/content/types")
        data = resp.json()
        for t in data["types"]:
            assert "label" in t
            assert "description" in t
            assert "output_formats" in t


# ---------------------------------------------------------------------------
# POST /api/content/plan
# ---------------------------------------------------------------------------


class TestPlanEndpoint:
    def test_plan_lecture(self, full_client):
        resp = full_client.post(
            "/api/content/plan",
            json={
                "content_type": "lecture",
                "topic": "SUPEX 추구",
                "options": {"duration_min": 30},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["content_type"] == "lecture"
        assert data["topic"] == "SUPEX 추구"
        assert "plan" in data
        assert "title" in data["plan"]

    def test_plan_no_planner_503(self, no_planner_client):
        resp = no_planner_client.post(
            "/api/content/plan",
            json={"content_type": "lecture", "topic": "테스트"},
        )
        assert resp.status_code == 503

    def test_plan_invalid_type_422(self, full_client):
        resp = full_client.post(
            "/api/content/plan",
            json={"content_type": "invalid_type", "topic": "테스트"},
        )
        assert resp.status_code == 422

    def test_plan_empty_topic_422(self, full_client):
        resp = full_client.post(
            "/api/content/plan",
            json={"content_type": "lecture", "topic": ""},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/content/generate
# ---------------------------------------------------------------------------


class TestGenerateEndpoint:
    def test_generate_lecture(self, full_client):
        resp = full_client.post(
            "/api/content/generate",
            json={
                "content_type": "lecture",
                "topic": "인간중심경영",
                "options": {"duration_min": 20},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["content_type"] == "lecture"
        assert data["topic"] == "인간중심경영"
        assert len(data["files"]) >= 1
        assert "total_elapsed_ms" in data["metadata"]

    def test_generate_visualization(self, full_client):
        resp = full_client.post(
            "/api/content/generate",
            json={
                "content_type": "visualization",
                "topic": "SUPEX 변천",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["content_type"] == "visualization"

    def test_generate_no_planner_503(self, no_planner_client):
        resp = no_planner_client.post(
            "/api/content/generate",
            json={"content_type": "lecture", "topic": "테스트"},
        )
        assert resp.status_code == 503

    def test_generate_default_options(self, full_client):
        """options 없이 요청해도 기본값으로 동작."""
        resp = full_client.post(
            "/api/content/generate",
            json={"content_type": "lecture", "topic": "SKMS 개요"},
        )
        assert resp.status_code == 200

    def test_generate_with_edition_filter(self, full_client):
        resp = full_client.post(
            "/api/content/generate",
            json={
                "content_type": "lecture",
                "topic": "SUPEX",
                "options": {"edition_filter": "2020-14차"},
            },
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------


class TestRequestValidation:
    def test_missing_content_type(self, full_client):
        resp = full_client.post(
            "/api/content/generate",
            json={"topic": "테스트"},
        )
        assert resp.status_code == 422

    def test_missing_topic(self, full_client):
        resp = full_client.post(
            "/api/content/generate",
            json={"content_type": "lecture"},
        )
        assert resp.status_code == 422

    def test_topic_too_long(self, full_client):
        resp = full_client.post(
            "/api/content/generate",
            json={"content_type": "lecture", "topic": "A" * 201},
        )
        assert resp.status_code == 422
