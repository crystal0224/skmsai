"""QueryRouter — LLM 기반 질의 의도 분류.

PR-012: 04_retrieve_and_answer.py에서 추출한 라우팅 로직.

route_query()는 LLM을 사용하여 질의를 5가지 의도 중 하나로 분류한다.
테스트 시 client를 mock으로 교체할 수 있다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# RouteResult — 라우팅 결과 (불변)
# ---------------------------------------------------------------------------

VALID_INTENTS = frozenset(
    {
        "specific_time",
        "general_definition",
        "evolution_comparison",
        "content_generation",
        "open_ended",
    }
)

VALID_OUTPUT_TYPES = frozenset({"summary", "card", "comparison_table", "quiz", "slide"})

VALID_QUOTE_TYPES = frozenset(
    {"definition", "principle", "procedure", "checklist", "example", "narrative"}
)


@dataclass(frozen=True)
class RouteResult:
    """질의 라우팅 결과."""

    intent: str
    confidence: float
    edition_hint: str | None
    output_type: str | None
    type_filter: tuple[str, ...] | None
    section_filter: str | None
    reasoning: str

    def __post_init__(self) -> None:
        if self.intent not in VALID_INTENTS:
            object.__setattr__(self, "intent", "open_ended")
        if not (0.0 <= self.confidence <= 1.0):
            object.__setattr__(self, "confidence", max(0.0, min(1.0, self.confidence)))
        if self.output_type and self.output_type not in VALID_OUTPUT_TYPES:
            object.__setattr__(self, "output_type", None)


# ---------------------------------------------------------------------------
# Query routing
# ---------------------------------------------------------------------------

_FALLBACK = RouteResult(
    intent="open_ended",
    confidence=0.5,
    edition_hint=None,
    output_type=None,
    type_filter=None,
    section_filter=None,
    reasoning="분류 실패, open_ended로 폴백",
)


def route_query(query: str, router_prompt: str, client: Any) -> RouteResult:
    """LLM을 사용하여 질의 의도를 분류한다.

    Args:
        query: 사용자 질의.
        router_prompt: 라우터 시스템 프롬프트.
        client: Anthropic 클라이언트 (messages.create 지원).

    Returns:
        RouteResult (불변).
    """
    if not query or not query.strip():
        return _FALLBACK

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=router_prompt,
            messages=[{"role": "user", "content": query}],
        )
        text = message.content[0].text.strip()
    except Exception:
        return _FALLBACK

    return _parse_route_response(text)


def _parse_route_response(text: str) -> RouteResult:
    """LLM 응답 텍스트를 RouteResult로 파싱한다."""
    try:
        # JSON 코드 블록 추출
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        data = json.loads(text)
    except (json.JSONDecodeError, IndexError):
        return _FALLBACK

    # v1 호환: query_type → intent
    if "query_type" in data and "intent" not in data:
        data["intent"] = data.pop("query_type")

    # type_filter 유효성 검증
    raw_type_filter = data.get("type_filter")
    type_filter: tuple[str, ...] | None = None
    if raw_type_filter and isinstance(raw_type_filter, list):
        valid = tuple(t for t in raw_type_filter if t in VALID_QUOTE_TYPES)
        type_filter = valid if valid else None

    return RouteResult(
        intent=data.get("intent", "open_ended"),
        confidence=float(data.get("confidence", 0.5)),
        edition_hint=data.get("edition_hint"),
        output_type=data.get("output_type"),
        type_filter=type_filter,
        section_filter=data.get("section_filter"),
        reasoning=data.get("reasoning", ""),
    )


# ---------------------------------------------------------------------------
# Dynamic top_k
# ---------------------------------------------------------------------------


def parse_count_from_query(query: str) -> int:
    """질의에서 생성 갯수 힌트를 추출한다.

    예: "5장의 카드" → 5, "퀴즈 3개" → 3, "10문제" → 10
    """
    match = re.search(r"(\d+)\s*(장|개|매|건|문제|문항|슬라이드|페이지)", query)
    if match:
        return min(int(match.group(1)), 20)
    return 3


def compute_dynamic_top_k(
    intent: str,
    output_type: str | None,
    query: str,
    base_top_k: int,
) -> int:
    """content_generation 의도에서 요청 규모에 따라 top_k를 동적 조정한다."""
    if intent != "content_generation":
        return base_top_k

    count = parse_count_from_query(query)
    multipliers = {
        "card": 3,
        "quiz": 3,
        "slide": 2,
        "comparison_table": 0,
        "summary": 0,
    }

    multiplier = multipliers.get(output_type or "", 0)
    if multiplier > 0:
        return max(base_top_k, count * multiplier)

    # comparison_table, summary: 고정 최소값
    min_values = {"comparison_table": 12, "summary": 8}
    min_val = min_values.get(output_type or "", 8)
    return max(base_top_k, min_val)
