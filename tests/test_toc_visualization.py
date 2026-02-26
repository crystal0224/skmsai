"""TOCVisualization 테스트.

PR-028: 인터랙티브 목차 트리 뷰어 단위/통합 테스트.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.toc_service import EditionTOC, TOCNode  # noqa: E402
from scripts.lib.toc_visualization import (  # noqa: E402
    BreadcrumbItem,
    EditionComparison,
    TreeStats,
    compare_editions,
    format_breadcrumb,
    format_comparison,
    get_tree_stats,
    render_breadcrumb,
    render_tree,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_toc(edition_id: str = "2020-14차", year: int = 2020) -> EditionTOC:
    """테스트용 EditionTOC 생성."""
    return EditionTOC(
        edition_id=edition_id,
        year=year,
        label="14차",
        sections=(
            TOCNode(
                level="H1",
                title="경영 기본 이념",
                line=100,
                children=(
                    TOCNode(
                        level="H2",
                        title="1. 인간중심의 경영",
                        line=110,
                        children=(
                            TOCNode(
                                level="H3",
                                title="가. 인적 요소의 중요성",
                                line=120,
                                children=(),
                            ),
                            TOCNode(
                                level="H3",
                                title="나. 사람 관리의 어려움",
                                line=130,
                                children=(),
                            ),
                        ),
                    ),
                    TOCNode(
                        level="H2",
                        title="2. 합리적 경영",
                        line=200,
                        children=(),
                    ),
                ),
            ),
            TOCNode(
                level="H1",
                title="SUPEX 추구",
                line=300,
                children=(),
            ),
        ),
    )


def _make_simple_toc(edition_id: str = "1979-초판") -> EditionTOC:
    """간단한 테스트용 TOC."""
    return EditionTOC(
        edition_id=edition_id,
        year=1979,
        label="초판",
        sections=(
            TOCNode(
                level="H1",
                title="경영 기본 이념",
                line=10,
                children=(
                    TOCNode(
                        level="H2",
                        title="1. 기업관",
                        line=20,
                        children=(),
                    ),
                ),
            ),
            TOCNode(
                level="H1",
                title="경영 원칙",
                line=50,
                children=(),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# TreeStats 테스트
# ---------------------------------------------------------------------------


class TestTreeStats:
    """TreeStats 테스트."""

    def test_is_frozen(self):
        """불변이다."""
        stats = TreeStats(
            edition_id="test",
            total_nodes=5,
            max_depth=2,
            level_counts={"H1": 2},
            leaf_count=3,
        )
        with pytest.raises(AttributeError):
            stats.total_nodes = 10  # type: ignore[misc]

    def test_fields(self):
        """필드 접근."""
        stats = TreeStats(
            edition_id="2020-14차",
            total_nodes=6,
            max_depth=2,
            level_counts={"H1": 2, "H2": 2, "H3": 2},
            leaf_count=3,
        )
        assert stats.edition_id == "2020-14차"
        assert stats.total_nodes == 6


# ---------------------------------------------------------------------------
# BreadcrumbItem 테스트
# ---------------------------------------------------------------------------


class TestBreadcrumbItem:
    """BreadcrumbItem 테스트."""

    def test_is_frozen(self):
        """불변이다."""
        item = BreadcrumbItem(level="H1", title="test", line=10)
        with pytest.raises(AttributeError):
            item.title = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# EditionComparison 테스트
# ---------------------------------------------------------------------------


class TestEditionComparison:
    """EditionComparison 테스트."""

    def test_is_frozen(self):
        """불변이다."""
        comp = EditionComparison(
            edition_a="A",
            edition_b="B",
            only_in_a=(),
            only_in_b=(),
            common=("공통",),
            stats_a=TreeStats("A", 1, 0, {}, 1),
            stats_b=TreeStats("B", 1, 0, {}, 1),
        )
        with pytest.raises(AttributeError):
            comp.common = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# render_tree 테스트
# ---------------------------------------------------------------------------


class TestRenderTree:
    """render_tree 함수 테스트."""

    def test_basic(self):
        """기본 트리 렌더링."""
        toc = _make_toc()
        result = render_tree(toc)

        assert "## 2020-14차 (2020)" in result
        assert "**경영 기본 이념**" in result
        assert "**1. 인간중심의 경영**" in result
        assert "**가. 인적 요소의 중요성**" in result
        assert "**SUPEX 추구**" in result

    def test_max_depth(self):
        """최대 깊이 제한."""
        toc = _make_toc()
        result = render_tree(toc, max_depth=1)

        assert "**경영 기본 이념**" in result
        assert "**SUPEX 추구**" in result
        # H2 이하는 안 보임
        assert "인간중심의 경영" not in result

    def test_empty_sections(self):
        """빈 섹션."""
        toc = EditionTOC(
            edition_id="test",
            year=2000,
            label="test",
            sections=(),
        )
        result = render_tree(toc)
        assert "## test (2000)" in result

    def test_markers(self):
        """부모 노드(+)와 리프 노드(-)."""
        toc = _make_toc()
        result = render_tree(toc)
        # H1 "경영 기본 이념"은 자식 있으므로 +
        assert "+ **경영 기본 이념**" in result
        # H1 "SUPEX 추구"는 자식 없으므로 -
        assert "- **SUPEX 추구**" in result


# ---------------------------------------------------------------------------
# render_breadcrumb 테스트
# ---------------------------------------------------------------------------


class TestRenderBreadcrumb:
    """render_breadcrumb 함수 테스트."""

    def test_root_node(self):
        """루트 노드."""
        toc = _make_toc()
        path = render_breadcrumb(toc, 100)
        assert len(path) == 1
        assert path[0].title == "경영 기본 이념"

    def test_deep_node(self):
        """깊은 노드."""
        toc = _make_toc()
        path = render_breadcrumb(toc, 120)
        assert len(path) == 3
        assert path[0].title == "경영 기본 이념"
        assert path[1].title == "1. 인간중심의 경영"
        assert path[2].title == "가. 인적 요소의 중요성"

    def test_not_found(self):
        """줄번호가 없는 경우."""
        toc = _make_toc()
        path = render_breadcrumb(toc, 9999)
        assert path == ()

    def test_second_root(self):
        """두 번째 루트 노드."""
        toc = _make_toc()
        path = render_breadcrumb(toc, 300)
        assert len(path) == 1
        assert path[0].title == "SUPEX 추구"


# ---------------------------------------------------------------------------
# format_breadcrumb 테스트
# ---------------------------------------------------------------------------


class TestFormatBreadcrumb:
    """format_breadcrumb 함수 테스트."""

    def test_basic(self):
        """기본 포맷."""
        items = (
            BreadcrumbItem(level="H1", title="경영 기본 이념", line=100),
            BreadcrumbItem(level="H2", title="인간중심의 경영", line=110),
        )
        result = format_breadcrumb(items)
        assert result == "경영 기본 이념 > 인간중심의 경영"

    def test_empty(self):
        """빈 경로."""
        result = format_breadcrumb(())
        assert result == "(경로 없음)"

    def test_single(self):
        """단일 항목."""
        items = (BreadcrumbItem(level="H1", title="단일노드", line=1),)
        result = format_breadcrumb(items)
        assert result == "단일노드"


# ---------------------------------------------------------------------------
# get_tree_stats 테스트
# ---------------------------------------------------------------------------


class TestGetTreeStats:
    """get_tree_stats 함수 테스트."""

    def test_basic(self):
        """기본 통계."""
        toc = _make_toc()
        stats = get_tree_stats(toc)

        assert stats.edition_id == "2020-14차"
        assert stats.total_nodes == 6  # H1(2) + H2(2) + H3(2)
        assert stats.max_depth == 2  # H1 > H2 > H3
        assert stats.level_counts["H1"] == 2
        assert stats.level_counts["H2"] == 2
        assert stats.level_counts["H3"] == 2
        assert stats.leaf_count == 4  # 가, 나, 합리적경영, SUPEX추구

    def test_empty(self):
        """빈 TOC."""
        toc = EditionTOC(
            edition_id="empty",
            year=2000,
            label="empty",
            sections=(),
        )
        stats = get_tree_stats(toc)
        assert stats.total_nodes == 0
        assert stats.max_depth == 0
        assert stats.leaf_count == 0

    def test_flat_tree(self):
        """깊이 0인 트리 (루트만)."""
        toc = EditionTOC(
            edition_id="flat",
            year=2000,
            label="flat",
            sections=(
                TOCNode(level="H1", title="A", line=1, children=()),
                TOCNode(level="H1", title="B", line=2, children=()),
            ),
        )
        stats = get_tree_stats(toc)
        assert stats.max_depth == 0
        assert stats.leaf_count == 2


# ---------------------------------------------------------------------------
# compare_editions 테스트
# ---------------------------------------------------------------------------


class TestCompareEditions:
    """compare_editions 함수 테스트."""

    def test_basic(self):
        """기본 비교."""
        toc_a = _make_toc("2020-14차", 2020)
        toc_b = _make_simple_toc("1979-초판")

        comp = compare_editions(toc_a, toc_b)

        assert comp.edition_a == "2020-14차"
        assert comp.edition_b == "1979-초판"
        assert "경영 기본 이념" in comp.common
        assert len(comp.only_in_a) > 0 or len(comp.only_in_b) > 0

    def test_identical(self):
        """동일 TOC 비교."""
        toc = _make_toc()
        comp = compare_editions(toc, toc)

        assert len(comp.only_in_a) == 0
        assert len(comp.only_in_b) == 0
        assert len(comp.common) > 0

    def test_stats_included(self):
        """통계가 포함된다."""
        toc_a = _make_toc()
        toc_b = _make_simple_toc()
        comp = compare_editions(toc_a, toc_b)

        assert comp.stats_a.total_nodes == 6
        assert comp.stats_b.total_nodes == 3


# ---------------------------------------------------------------------------
# format_comparison 테스트
# ---------------------------------------------------------------------------


class TestFormatComparison:
    """format_comparison 함수 테스트."""

    def test_basic(self):
        """기본 포맷."""
        toc_a = _make_toc()
        toc_b = _make_simple_toc()
        comp = compare_editions(toc_a, toc_b)
        result = format_comparison(comp)

        assert "목차 비교" in result
        assert "전체 노드" in result
        assert "**공통 섹션" in result

    def test_only_in_sections(self):
        """차이 섹션 표시."""
        toc_a = _make_toc()
        toc_b = _make_simple_toc()
        comp = compare_editions(toc_a, toc_b)
        result = format_comparison(comp)

        # 최소 한쪽에는 고유 섹션이 있어야 함
        has_only = "에만 있는 섹션" in result
        assert has_only


# ---------------------------------------------------------------------------
# 통합 테스트
# ---------------------------------------------------------------------------


class TestTOCVisualizationIntegration:
    """통합 테스트."""

    def test_tree_and_breadcrumb(self):
        """트리 렌더링 + 경로 탐색."""
        toc = _make_toc()

        # 트리 렌더링
        tree = render_tree(toc)
        assert "경영 기본 이념" in tree

        # 경로 탐색
        path = render_breadcrumb(toc, 130)
        assert len(path) == 3
        formatted = format_breadcrumb(path)
        assert "경영 기본 이념" in formatted
        assert "나. 사람 관리의 어려움" in formatted

    def test_stats_and_comparison(self):
        """통계 + 비교."""
        toc_a = _make_toc()
        toc_b = _make_simple_toc()

        stats = get_tree_stats(toc_a)
        assert stats.total_nodes > 0

        comp = compare_editions(toc_a, toc_b)
        md = format_comparison(comp)
        assert "| 전체 노드 |" in md

    def test_full_pipeline(self):
        """전체 파이프라인."""
        toc = _make_toc()

        # 1. 트리 렌더링
        tree = render_tree(toc, max_depth=2)
        assert "2020-14차" in tree

        # 2. 통계
        stats = get_tree_stats(toc)
        assert stats.total_nodes == 6

        # 3. 경로 탐색
        path = render_breadcrumb(toc, 120)
        assert len(path) == 3
        assert format_breadcrumb(path) == "경영 기본 이념 > 1. 인간중심의 경영 > 가. 인적 요소의 중요성"
