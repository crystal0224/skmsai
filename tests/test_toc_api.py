"""TOC API 엔드포인트 테스트.

PR-014: GET /api/editions, GET /api/toc/{edition_id}, GET /api/toc.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from scripts.lib.toc_service import TOCService  # noqa: E402
from server.dependencies import AppState  # noqa: E402
from server.models import (  # noqa: E402
    EditionInfoResponse,
    EditionsListResponse,
    TOCNodeResponse,
    TOCResponse,
    TOCSectionSearchResponse,
)
from server.routes.toc import create_toc_router  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SAMPLE_STRUCTURE = {
    "source_file": "test.txt",
    "total_lines": 100,
    "edition_count": 2,
    "total_sections": 5,
    "header_gaps": [],
    "editions": [
        {
            "edition_id": "1979-초판",
            "year": 1979,
            "label": "초판",
            "start_line": 11,
            "end_line": 726,
            "match_type": "type_a",
            "raw_text": "1979년 초판",
            "sections": [
                {
                    "level": "H1",
                    "title": "기업관",
                    "line": 13,
                    "children": [
                        {
                            "level": "H2",
                            "title": "1. 인간중심의 경영",
                            "line": 39,
                            "children": [],
                        },
                    ],
                },
            ],
        },
        {
            "edition_id": "2020-14차",
            "year": 2020,
            "label": "14차",
            "start_line": 15073,
            "end_line": 15330,
            "match_type": "type_b",
            "raw_text": "2020년 14차 개정판",
            "sections": [
                {
                    "level": "H1",
                    "title": "VWBE Culture",
                    "line": 15080,
                    "children": [
                        {
                            "level": "H2",
                            "title": "1. VWBE 정의",
                            "line": 15090,
                            "children": [],
                        },
                    ],
                },
                {
                    "level": "H1",
                    "title": "인간중심의 경영",
                    "line": 15100,
                    "children": [],
                },
            ],
        },
    ],
}


def _make_app_with_toc(tmp_path: Path) -> FastAPI:
    """TOC 서비스가 포함된 테스트 앱."""
    structure_path = tmp_path / "structure.json"
    structure_path.write_text(json.dumps(_SAMPLE_STRUCTURE, ensure_ascii=False))

    state = AppState()
    state._initialized = True
    state.toc_service = TOCService.from_path(structure_path)

    app = FastAPI(title="Test")
    app.include_router(create_toc_router(state))
    return app


def _make_app_no_toc() -> FastAPI:
    """TOC 서비스 없는 테스트 앱."""
    state = AppState()
    state._initialized = True

    app = FastAPI(title="Test")
    app.include_router(create_toc_router(state))
    return app


# ---------------------------------------------------------------------------
# GET /api/editions 테스트
# ---------------------------------------------------------------------------


def test_list_editions(tmp_path):
    """GET /api/editions 전체 개정판 목록."""
    app = _make_app_with_toc(tmp_path)
    with TestClient(app) as client:
        resp = client.get("/api/editions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["editions"]) == 2
    assert data["editions"][0]["edition_id"] == "1979-초판"
    assert data["editions"][1]["edition_id"] == "2020-14차"


def test_list_editions_has_metadata(tmp_path):
    """개정판에 메타데이터가 포함된다."""
    app = _make_app_with_toc(tmp_path)
    with TestClient(app) as client:
        resp = client.get("/api/editions")
    data = resp.json()
    ed = data["editions"][1]
    assert ed["year"] == 2020
    assert ed["label"] == "14차"
    assert ed["start_line"] == 15073
    assert ed["end_line"] == 15330
    assert ed["section_count"] > 0


def test_list_editions_no_service():
    """TOC 서비스 미초기화 → 503."""
    app = _make_app_no_toc()
    with TestClient(app) as client:
        resp = client.get("/api/editions")
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET /api/toc/{edition_id} 테스트
# ---------------------------------------------------------------------------


def test_get_edition_toc(tmp_path):
    """GET /api/toc/2020-14차 목차 트리."""
    app = _make_app_with_toc(tmp_path)
    with TestClient(app) as client:
        resp = client.get("/api/toc/2020-14차")
    assert resp.status_code == 200
    data = resp.json()
    assert data["edition_id"] == "2020-14차"
    assert data["year"] == 2020
    assert data["label"] == "14차"
    assert len(data["sections"]) == 2
    assert data["node_count"] > 0


def test_get_edition_toc_nested_children(tmp_path):
    """중첩 children이 올바르게 반환된다."""
    app = _make_app_with_toc(tmp_path)
    with TestClient(app) as client:
        resp = client.get("/api/toc/2020-14차")
    data = resp.json()
    vwbe = data["sections"][0]
    assert vwbe["title"] == "VWBE Culture"
    assert len(vwbe["children"]) == 1
    assert vwbe["children"][0]["title"] == "1. VWBE 정의"


def test_get_edition_toc_not_found(tmp_path):
    """존재하지 않는 개정판 → 404."""
    app = _make_app_with_toc(tmp_path)
    with TestClient(app) as client:
        resp = client.get("/api/toc/nonexistent")
    assert resp.status_code == 404


def test_get_edition_toc_no_service():
    """TOC 서비스 미초기화 → 503."""
    app = _make_app_no_toc()
    with TestClient(app) as client:
        resp = client.get("/api/toc/2020-14차")
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET /api/toc?q= 검색 테스트
# ---------------------------------------------------------------------------


def test_search_sections(tmp_path):
    """GET /api/toc?q=인간중심 섹션 검색."""
    app = _make_app_with_toc(tmp_path)
    with TestClient(app) as client:
        resp = client.get("/api/toc", params={"q": "인간중심"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "인간중심"
    assert data["total"] >= 1


def test_search_sections_with_edition_filter(tmp_path):
    """GET /api/toc?q=인간중심&edition_id=2020-14차 에디션 필터."""
    app = _make_app_with_toc(tmp_path)
    with TestClient(app) as client:
        resp = client.get("/api/toc", params={"q": "인간중심", "edition_id": "2020-14차"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["edition_id"] == "2020-14차"
    for r in data["results"]:
        assert r["edition_id"] == "2020-14차"


def test_search_sections_empty_query(tmp_path):
    """빈 검색어 → 400."""
    app = _make_app_with_toc(tmp_path)
    with TestClient(app) as client:
        resp = client.get("/api/toc", params={"q": ""})
    assert resp.status_code == 400


def test_search_sections_no_match(tmp_path):
    """매칭 없으면 빈 결과."""
    app = _make_app_with_toc(tmp_path)
    with TestClient(app) as client:
        resp = client.get("/api/toc", params={"q": "존재하지않는키워드"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0


def test_search_sections_no_service():
    """TOC 서비스 미초기화 → 503."""
    app = _make_app_no_toc()
    with TestClient(app) as client:
        resp = client.get("/api/toc", params={"q": "test"})
    assert resp.status_code == 503


def test_search_sections_result_has_path(tmp_path):
    """검색 결과에 path가 포함된다."""
    app = _make_app_with_toc(tmp_path)
    with TestClient(app) as client:
        resp = client.get("/api/toc", params={"q": "VWBE 정의"})
    data = resp.json()
    assert data["total"] == 1
    r = data["results"][0]
    assert "VWBE Culture" in r["path"]
    assert r["level"] == "H2"


# ---------------------------------------------------------------------------
# Pydantic 모델 테스트
# ---------------------------------------------------------------------------


def test_toc_node_response_recursive():
    """TOCNodeResponse는 재귀적 children을 가진다."""
    node = TOCNodeResponse(
        level="H1",
        title="root",
        line=1,
        children=[
            TOCNodeResponse(level="H2", title="child", line=2, children=[]),
        ],
    )
    assert len(node.children) == 1
    assert node.children[0].title == "child"


def test_editions_list_response():
    """EditionsListResponse 생성."""
    resp = EditionsListResponse(
        editions=[
            EditionInfoResponse(
                edition_id="2020-14차",
                year=2020,
                label="14차",
                start_line=15073,
                end_line=15330,
                section_count=29,
            ),
        ],
        total=1,
    )
    assert resp.total == 1
    assert resp.editions[0].edition_id == "2020-14차"
