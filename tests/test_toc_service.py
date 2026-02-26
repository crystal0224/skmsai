"""TOCService 테스트.

PR-014: 목차 트리 서비스 단위 테스트.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.toc_service import (  # noqa: E402
    EditionInfo,
    EditionTOC,
    TOCNode,
    TOCService,
)


# ---------------------------------------------------------------------------
# TOCNode 테스트
# ---------------------------------------------------------------------------


def test_toc_node_is_frozen():
    """TOCNode는 불변이다."""
    node = TOCNode(level="H1", title="test", line=1, children=())
    with pytest.raises(AttributeError):
        node.title = "modified"  # type: ignore[misc]


def test_toc_node_from_dict():
    """dict에서 TOCNode를 생성한다."""
    data = {
        "level": "H1",
        "title": "기업관",
        "line": 13,
        "children": [
            {"level": "H2", "title": "1. 인간중심의 경영", "line": 39, "children": []},
        ],
    }
    node = TOCNode.from_dict(data)
    assert node.level == "H1"
    assert node.title == "기업관"
    assert len(node.children) == 1
    assert node.children[0].title == "1. 인간중심의 경영"


def test_toc_node_from_dict_empty_children():
    """children 없는 dict도 생성 가능."""
    data = {"level": "H4", "title": "leaf", "line": 100}
    node = TOCNode.from_dict(data)
    assert node.children == ()


def test_toc_node_to_dict():
    """to_dict()로 직렬화 가능."""
    node = TOCNode(
        level="H1",
        title="test",
        line=10,
        children=(TOCNode(level="H2", title="child", line=20, children=()),),
    )
    d = node.to_dict()
    assert d["level"] == "H1"
    assert len(d["children"]) == 1
    assert d["children"][0]["title"] == "child"


def test_toc_node_node_count():
    """node_count는 자신 포함 전체 노드 수."""
    node = TOCNode(
        level="H1",
        title="root",
        line=1,
        children=(
            TOCNode(
                level="H2",
                title="child1",
                line=2,
                children=(
                    TOCNode(level="H3", title="grandchild", line=3, children=()),
                ),
            ),
            TOCNode(level="H2", title="child2", line=4, children=()),
        ),
    )
    assert node.node_count == 4


def test_toc_node_leaf_count():
    """리프 노드의 node_count는 1."""
    node = TOCNode(level="H4", title="leaf", line=1, children=())
    assert node.node_count == 1


# ---------------------------------------------------------------------------
# EditionInfo 테스트
# ---------------------------------------------------------------------------


def test_edition_info_is_frozen():
    """EditionInfo는 불변이다."""
    info = EditionInfo(
        edition_id="2020-14차",
        year=2020,
        label="14차",
        start_line=15073,
        end_line=15330,
        section_count=29,
    )
    with pytest.raises(AttributeError):
        info.year = 2021  # type: ignore[misc]


# ---------------------------------------------------------------------------
# EditionTOC 테스트
# ---------------------------------------------------------------------------


def test_edition_toc_is_frozen():
    """EditionTOC는 불변이다."""
    toc = EditionTOC(
        edition_id="2020-14차",
        year=2020,
        label="14차",
        sections=(),
    )
    with pytest.raises(AttributeError):
        toc.label = "modified"  # type: ignore[misc]


def test_edition_toc_node_count():
    """EditionTOC.node_count는 모든 섹션의 합."""
    toc = EditionTOC(
        edition_id="test",
        year=2020,
        label="test",
        sections=(
            TOCNode(level="H1", title="a", line=1, children=()),
            TOCNode(
                level="H1",
                title="b",
                line=2,
                children=(TOCNode(level="H2", title="c", line=3, children=()),),
            ),
        ),
    )
    assert toc.node_count == 3


# ---------------------------------------------------------------------------
# TOCService 테스트
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


@pytest.fixture()
def sample_structure_path(tmp_path) -> Path:
    """테스트용 structure.json 파일."""
    path = tmp_path / "structure.json"
    path.write_text(json.dumps(_SAMPLE_STRUCTURE, ensure_ascii=False))
    return path


def test_service_from_path(sample_structure_path):
    """structure.json에서 서비스를 생성한다."""
    svc = TOCService.from_path(sample_structure_path)
    assert svc.edition_count == 2


def test_service_from_nonexistent_path(tmp_path):
    """존재하지 않는 파일이면 빈 서비스."""
    svc = TOCService.from_path(tmp_path / "nonexistent.json")
    assert svc.edition_count == 0


def test_service_list_editions(sample_structure_path):
    """전체 개정판 목록."""
    svc = TOCService.from_path(sample_structure_path)
    editions = svc.list_editions()
    assert len(editions) == 2
    assert editions[0].edition_id == "1979-초판"
    assert editions[1].edition_id == "2020-14차"
    assert editions[0].section_count == 2  # 기업관 + 인간중심의 경영
    assert editions[1].section_count == 3  # VWBE Culture + VWBE 정의 + 인간중심의 경영


def test_service_get_edition_toc(sample_structure_path):
    """특정 개정판의 TOC 트리."""
    svc = TOCService.from_path(sample_structure_path)
    toc = svc.get_edition_toc("2020-14차")
    assert toc is not None
    assert toc.edition_id == "2020-14차"
    assert toc.year == 2020
    assert len(toc.sections) == 2
    assert toc.sections[0].title == "VWBE Culture"


def test_service_get_edition_toc_not_found(sample_structure_path):
    """존재하지 않는 개정판은 None."""
    svc = TOCService.from_path(sample_structure_path)
    toc = svc.get_edition_toc("nonexistent")
    assert toc is None


def test_service_get_edition_ids(sample_structure_path):
    """전체 개정판 ID."""
    svc = TOCService.from_path(sample_structure_path)
    ids = svc.get_edition_ids()
    assert len(ids) == 2
    assert "1979-초판" in ids
    assert "2020-14차" in ids


def test_service_search_sections(sample_structure_path):
    """섹션 제목 검색."""
    svc = TOCService.from_path(sample_structure_path)
    results = svc.search_sections("인간중심")
    assert len(results) == 2  # 1979 + 2020 모두
    titles = {r["title"] for r in results}
    assert "1. 인간중심의 경영" in titles or "인간중심의 경영" in titles


def test_service_search_sections_by_edition(sample_structure_path):
    """특정 개정판으로 제한된 검색."""
    svc = TOCService.from_path(sample_structure_path)
    results = svc.search_sections("인간중심", edition_id="2020-14차")
    assert len(results) == 1
    assert results[0]["edition_id"] == "2020-14차"


def test_service_search_sections_no_match(sample_structure_path):
    """매칭 없으면 빈 리스트."""
    svc = TOCService.from_path(sample_structure_path)
    results = svc.search_sections("존재하지않는키워드")
    assert len(results) == 0


def test_service_search_case_insensitive(sample_structure_path):
    """검색은 대소문자 무관."""
    svc = TOCService.from_path(sample_structure_path)
    results = svc.search_sections("vwbe")
    assert len(results) >= 1


def test_service_search_result_has_path(sample_structure_path):
    """검색 결과에 path가 포함된다."""
    svc = TOCService.from_path(sample_structure_path)
    results = svc.search_sections("VWBE 정의")
    assert len(results) == 1
    r = results[0]
    assert r["edition_id"] == "2020-14차"
    assert "VWBE Culture" in r["path"]
    assert "1. VWBE 정의" in r["path"]
