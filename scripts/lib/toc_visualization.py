"""TOCVisualization — 인터랙티브 목차 트리 뷰어 서비스.

PR-028: TOC 트리를 다양한 형식으로 렌더링하고, 탐색 기능을 제공한다.

기능:
- render_tree(): TOC 트리를 Markdown 트리로 렌더링
- render_breadcrumb(): 특정 노드의 경로(breadcrumb) 생성
- compare_editions(): 두 개정판의 목차 구조 비교
- get_tree_stats(): 트리 통계 (깊이, 노드 수 등)
- find_node_by_line(): 줄번호로 노드 탐색
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from scripts.lib.toc_service import EditionTOC, TOCNode, TOCService

logger = logging.getLogger(__name__)

# 레벨별 인덴트 깊이
_LEVEL_DEPTH: dict[str, int] = {
    "H0": 0,
    "H1": 0,
    "H2": 1,
    "H3": 2,
    "H4": 3,
    "H4b": 3,
    "H5": 4,
}


# ---------------------------------------------------------------------------
# TreeStats — 트리 통계 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TreeStats:
    """목차 트리 통계.

    Attributes:
        edition_id: 개정판 식별자
        total_nodes: 전체 노드 수
        max_depth: 최대 깊이
        level_counts: 레벨별 노드 수
        leaf_count: 리프 노드 수
    """

    edition_id: str
    total_nodes: int
    max_depth: int
    level_counts: dict[str, int]
    leaf_count: int


# ---------------------------------------------------------------------------
# BreadcrumbItem — 경로 항목 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BreadcrumbItem:
    """경로 탐색 항목.

    Attributes:
        level: 레벨 (H1, H2, ...)
        title: 제목
        line: 줄번호
    """

    level: str
    title: str
    line: int


# ---------------------------------------------------------------------------
# EditionComparison — 개정판 비교 결과 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EditionComparison:
    """두 개정판의 목차 구조 비교 결과.

    Attributes:
        edition_a: 개정판 A ID
        edition_b: 개정판 B ID
        only_in_a: A에만 있는 제목
        only_in_b: B에만 있는 제목
        common: 공통 제목
        stats_a: A의 통계
        stats_b: B의 통계
    """

    edition_a: str
    edition_b: str
    only_in_a: tuple[str, ...]
    only_in_b: tuple[str, ...]
    common: tuple[str, ...]
    stats_a: TreeStats
    stats_b: TreeStats


# ---------------------------------------------------------------------------
# 렌더링 함수
# ---------------------------------------------------------------------------


def render_tree(edition_toc: EditionTOC, max_depth: int = 0) -> str:
    """TOC 트리를 Markdown 트리로 렌더링한다.

    Args:
        edition_toc: 개정판 TOC
        max_depth: 최대 렌더링 깊이 (0=무제한)

    Returns:
        Markdown 문자열
    """
    lines: list[str] = []
    lines.append(f"## {edition_toc.edition_id} ({edition_toc.year})")
    lines.append("")

    for section in edition_toc.sections:
        _render_node(section, 0, max_depth, lines)

    return "\n".join(lines)


def _render_node(
    node: TOCNode,
    depth: int,
    max_depth: int,
    lines: list[str],
) -> None:
    """노드를 재귀적으로 렌더링한다."""
    if max_depth > 0 and depth >= max_depth:
        return

    indent = "  " * depth
    has_children = len(node.children) > 0
    marker = "+" if has_children else "-"

    lines.append(f"{indent}{marker} **{node.title}** `{node.level}` (L{node.line})")

    for child in node.children:
        _render_node(child, depth + 1, max_depth, lines)


def render_breadcrumb(
    edition_toc: EditionTOC,
    target_line: int,
) -> tuple[BreadcrumbItem, ...]:
    """특정 줄번호의 경로(breadcrumb)를 반환한다.

    Args:
        edition_toc: 개정판 TOC
        target_line: 대상 줄번호

    Returns:
        BreadcrumbItem 경로 (루트 → 대상 노드)
    """
    for section in edition_toc.sections:
        path = _find_path_to_line(section, target_line, [])
        if path is not None:
            return tuple(path)
    return ()


def _find_path_to_line(
    node: TOCNode,
    target_line: int,
    current_path: list[BreadcrumbItem],
) -> list[BreadcrumbItem] | None:
    """줄번호로 노드 경로를 탐색한다."""
    item = BreadcrumbItem(level=node.level, title=node.title, line=node.line)
    new_path = [*current_path, item]

    if node.line == target_line:
        return new_path

    for child in node.children:
        result = _find_path_to_line(child, target_line, new_path)
        if result is not None:
            return result

    return None


def format_breadcrumb(items: tuple[BreadcrumbItem, ...]) -> str:
    """BreadcrumbItem 경로를 문자열로 포맷팅한다.

    Args:
        items: BreadcrumbItem 경로

    Returns:
        "경영 기본 이념 > 인간중심의 경영 > 가. 인적 요소" 형태
    """
    if not items:
        return "(경로 없음)"
    return " > ".join(item.title for item in items)


# ---------------------------------------------------------------------------
# 통계 함수
# ---------------------------------------------------------------------------


def get_tree_stats(edition_toc: EditionTOC) -> TreeStats:
    """트리 통계를 계산한다.

    Args:
        edition_toc: 개정판 TOC

    Returns:
        TreeStats (불변)
    """
    level_counts: dict[str, int] = {}
    leaf_count = 0
    max_depth = 0

    for section in edition_toc.sections:
        _collect_stats(section, 0, level_counts)

    # leaf + max_depth 계산
    for section in edition_toc.sections:
        d, l = _measure_tree(section, 0)
        max_depth = max(max_depth, d)
        leaf_count += l

    return TreeStats(
        edition_id=edition_toc.edition_id,
        total_nodes=edition_toc.node_count,
        max_depth=max_depth,
        level_counts=level_counts,
        leaf_count=leaf_count,
    )


def _collect_stats(
    node: TOCNode,
    depth: int,
    level_counts: dict[str, int],
) -> None:
    """레벨별 노드 수를 수집한다."""
    level_counts[node.level] = level_counts.get(node.level, 0) + 1
    for child in node.children:
        _collect_stats(child, depth + 1, level_counts)


def _measure_tree(node: TOCNode, depth: int) -> tuple[int, int]:
    """최대 깊이와 리프 수를 측정한다.

    Returns:
        (max_depth, leaf_count) 튜플
    """
    if not node.children:
        return (depth, 1)

    max_d = depth
    total_leaves = 0
    for child in node.children:
        d, l = _measure_tree(child, depth + 1)
        max_d = max(max_d, d)
        total_leaves += l

    return (max_d, total_leaves)


# ---------------------------------------------------------------------------
# 개정판 비교
# ---------------------------------------------------------------------------


def compare_editions(
    toc_a: EditionTOC,
    toc_b: EditionTOC,
) -> EditionComparison:
    """두 개정판의 목차 구조를 비교한다.

    H1/H2 레벨 제목을 기준으로 공통/차이를 분석한다.

    Args:
        toc_a: 개정판 A
        toc_b: 개정판 B

    Returns:
        EditionComparison (불변)
    """
    titles_a = _collect_titles(toc_a, max_level=2)
    titles_b = _collect_titles(toc_b, max_level=2)

    set_a = set(titles_a)
    set_b = set(titles_b)

    common = tuple(sorted(set_a & set_b))
    only_a = tuple(sorted(set_a - set_b))
    only_b = tuple(sorted(set_b - set_a))

    stats_a = get_tree_stats(toc_a)
    stats_b = get_tree_stats(toc_b)

    return EditionComparison(
        edition_a=toc_a.edition_id,
        edition_b=toc_b.edition_id,
        only_in_a=only_a,
        only_in_b=only_b,
        common=common,
        stats_a=stats_a,
        stats_b=stats_b,
    )


def _collect_titles(
    edition_toc: EditionTOC,
    max_level: int,
) -> list[str]:
    """H1~max_level까지의 제목을 수집한다."""
    titles: list[str] = []
    for section in edition_toc.sections:
        _collect_titles_recursive(section, 0, max_level, titles)
    return titles


def _collect_titles_recursive(
    node: TOCNode,
    depth: int,
    max_level: int,
    titles: list[str],
) -> None:
    """재귀적으로 제목을 수집한다."""
    if depth <= max_level:
        titles.append(node.title)
    for child in node.children:
        _collect_titles_recursive(child, depth + 1, max_level, titles)


def format_comparison(comparison: EditionComparison) -> str:
    """EditionComparison을 Markdown으로 포맷팅한다.

    Args:
        comparison: 비교 결과

    Returns:
        Markdown 문자열
    """
    lines: list[str] = []

    lines.append(f"### {comparison.edition_a} vs {comparison.edition_b} 목차 비교")
    lines.append("")

    # 통계 비교표
    lines.append("| 항목 | " + comparison.edition_a + " | " + comparison.edition_b + " |")
    lines.append("|---|---|---|")
    lines.append(
        f"| 전체 노드 | {comparison.stats_a.total_nodes} | {comparison.stats_b.total_nodes} |"
    )
    lines.append(
        f"| 최대 깊이 | {comparison.stats_a.max_depth} | {comparison.stats_b.max_depth} |"
    )
    lines.append(
        f"| 리프 노드 | {comparison.stats_a.leaf_count} | {comparison.stats_b.leaf_count} |"
    )
    lines.append("")

    # 공통 섹션
    lines.append(f"**공통 섹션 ({len(comparison.common)}):**")
    for title in comparison.common:
        lines.append(f"- {title}")
    lines.append("")

    # A에만 있는 섹션
    if comparison.only_in_a:
        lines.append(
            f"**{comparison.edition_a}에만 있는 섹션 ({len(comparison.only_in_a)}):**"
        )
        for title in comparison.only_in_a:
            lines.append(f"- {title}")
        lines.append("")

    # B에만 있는 섹션
    if comparison.only_in_b:
        lines.append(
            f"**{comparison.edition_b}에만 있는 섹션 ({len(comparison.only_in_b)}):**"
        )
        for title in comparison.only_in_b:
            lines.append(f"- {title}")

    return "\n".join(lines)
