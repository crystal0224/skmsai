"""OutputRenderer — 3종 출력 렌더러.

PR-026: LLM 생성 결과를 summary/card/comparison_table 형식으로 렌더링한다.

기능:
- render_summary(): SummaryOutput → Markdown 요약
- render_card(): CardOutput → Markdown 카드
- render_card_list(): CardListOutput → Markdown 카드 목록
- render_comparison_table(): ComparisonTableOutput → Markdown 비교표
- render(): output_type 기반 자동 디스패치
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from scripts.lib.output_validator import (
    CardListOutput,
    CardOutput,
    ComparisonTableOutput,
    SummaryOutput,
    _extract_json,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RenderResult — 렌더링 결과 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RenderResult:
    """렌더링 결과.

    Attributes:
        output_type: 출력 유형
        rendered: 렌더링된 Markdown 텍스트
        raw_data: 파싱된 원본 데이터 (dict)
        success: 렌더링 성공 여부
        error: 실패 시 오류 메시지
    """

    output_type: str
    rendered: str
    raw_data: dict[str, Any] | None
    success: bool
    error: str


# ---------------------------------------------------------------------------
# 렌더링 함수
# ---------------------------------------------------------------------------


def render_summary(data: SummaryOutput) -> str:
    """SummaryOutput → Markdown 요약.

    Args:
        data: 검증된 SummaryOutput

    Returns:
        Markdown 문자열
    """
    lines: list[str] = []

    # 제목
    lines.append(f"### {data.title}")
    lines.append("")

    # 본문
    lines.append(data.body)
    lines.append("")

    # 핵심 포인트
    if data.key_points:
        lines.append("**핵심 포인트:**")
        for point in data.key_points:
            lines.append(f"- {point}")
        lines.append("")

    # 출처
    if data.citations:
        lines.append("**출처:**")
        for citation in data.citations:
            lines.append(f"- `{citation}`")

    return "\n".join(lines)


def render_card(data: CardOutput) -> str:
    """CardOutput → Markdown 카드.

    Args:
        data: 검증된 CardOutput

    Returns:
        Markdown 문자열
    """
    lines: list[str] = []

    # 카드 헤더
    edition_label = f" ({data.edition_tag})" if data.edition_tag else ""
    lines.append(f"---")
    lines.append(f"**Q:** {data.front}{edition_label}")
    lines.append("")
    lines.append(f"**A:** {data.back}")

    # 출처
    if data.citations:
        citations_str = ", ".join(f"`{c}`" for c in data.citations)
        lines.append(f"  *출처: {citations_str}*")

    lines.append("---")

    return "\n".join(lines)


def render_card_list(data: CardListOutput) -> str:
    """CardListOutput → Markdown 카드 목록.

    Args:
        data: 검증된 CardListOutput

    Returns:
        Markdown 문자열
    """
    lines: list[str] = []

    lines.append(f"## 지식 카드 ({len(data.cards)}장)")
    lines.append("")

    for i, card in enumerate(data.cards, 1):
        lines.append(f"### 카드 {i}")
        lines.append(render_card(card))
        lines.append("")

    return "\n".join(lines)


def render_comparison_table(data: ComparisonTableOutput) -> str:
    """ComparisonTableOutput → Markdown 비교표.

    Args:
        data: 검증된 ComparisonTableOutput

    Returns:
        Markdown 문자열
    """
    lines: list[str] = []

    # 제목
    lines.append(f"### {data.concept} — 개정판 비교")
    lines.append("")

    # 테이블 헤더
    header = "| 항목 | " + " | ".join(data.columns) + " |"
    separator = "|---" + "|---" * len(data.columns) + "|"
    lines.append(header)
    lines.append(separator)

    # 테이블 행
    for row in data.rows:
        values = []
        for col in data.columns:
            val = row.values.get(col, "—")
            # 셀 내용이 길면 축약
            if len(val) > 80:
                val = val[:77] + "..."
            # 파이프 문자 이스케이프
            val = val.replace("|", "\\|")
            values.append(val)
        row_line = f"| {row.aspect} | " + " | ".join(values) + " |"
        lines.append(row_line)

    lines.append("")

    # 진화 요약
    if data.evolution_summary:
        lines.append(f"**변화 요약:** {data.evolution_summary}")
        lines.append("")

    # 출처
    all_quote_ids: list[str] = []
    for row in data.rows:
        all_quote_ids.extend(row.quote_ids)
    if all_quote_ids:
        unique_ids = list(dict.fromkeys(all_quote_ids))  # 순서 유지 중복 제거
        lines.append("**출처:**")
        for qid in unique_ids:
            lines.append(f"- `{qid}`")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 통합 렌더 디스패치
# ---------------------------------------------------------------------------

# output_type → 렌더링 함수 매핑
_RENDERER_MAP: dict[str, str] = {
    "summary": "summary",
    "card": "card",
    "comparison_table": "comparison_table",
}


def render(raw_answer: str, output_type: str) -> RenderResult:
    """LLM 응답을 output_type에 맞게 렌더링한다.

    JSON을 파싱하고, output_type에 따라 적절한 렌더러를 호출한다.

    Args:
        raw_answer: LLM이 생성한 원문 응답 (JSON 포함)
        output_type: 출력 유형 ("summary", "card", "comparison_table")

    Returns:
        RenderResult (불변)
    """
    if output_type not in _RENDERER_MAP:
        return RenderResult(
            output_type=output_type,
            rendered="",
            raw_data=None,
            success=False,
            error=f"지원하지 않는 output_type: {output_type}",
        )

    # JSON 추출
    data = _extract_json(raw_answer)
    if data is None:
        return RenderResult(
            output_type=output_type,
            rendered="",
            raw_data=None,
            success=False,
            error="JSON 추출 실패",
        )

    raw_dict = data if isinstance(data, dict) else None

    try:
        if output_type == "summary":
            parsed = SummaryOutput.model_validate(data)
            rendered = render_summary(parsed)
        elif output_type == "card":
            rendered = _render_card_dispatch(data)
        elif output_type == "comparison_table":
            parsed = ComparisonTableOutput.model_validate(data)
            rendered = render_comparison_table(parsed)
        else:
            return RenderResult(
                output_type=output_type,
                rendered="",
                raw_data=raw_dict,
                success=False,
                error=f"렌더러 미구현: {output_type}",
            )

        return RenderResult(
            output_type=output_type,
            rendered=rendered,
            raw_data=raw_dict,
            success=True,
            error="",
        )

    except Exception as e:
        logger.warning("렌더링 실패 (%s): %s", output_type, e)
        return RenderResult(
            output_type=output_type,
            rendered="",
            raw_data=raw_dict,
            success=False,
            error=str(e),
        )


def _render_card_dispatch(data: Any) -> str:
    """카드 데이터를 단일/목록에 따라 렌더링한다."""
    # 배열이면 카드 목록
    if isinstance(data, list):
        card_list = CardListOutput.model_validate({"cards": data})
        return render_card_list(card_list)

    # dict에 cards 키가 있으면 카드 목록
    if isinstance(data, dict) and "cards" in data:
        card_list = CardListOutput.model_validate(data)
        return render_card_list(card_list)

    # 단일 카드
    card = CardOutput.model_validate(data)
    return render_card(card)
