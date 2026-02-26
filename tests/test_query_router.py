"""QueryRouter 테스트.

PR-012: 질의 라우팅 + 동적 top_k.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.query_router import (  # noqa: E402
    VALID_INTENTS,
    VALID_OUTPUT_TYPES,
    VALID_QUOTE_TYPES,
    RouteResult,
    _parse_route_response,
    compute_dynamic_top_k,
    parse_count_from_query,
    route_query,
)


# ---------------------------------------------------------------------------
# RouteResult 테스트
# ---------------------------------------------------------------------------


def test_route_result_is_frozen():
    """RouteResult는 불변이다."""
    result = RouteResult(
        intent="open_ended",
        confidence=0.8,
        edition_hint=None,
        output_type=None,
        type_filter=None,
        section_filter=None,
        reasoning="test",
    )
    with pytest.raises(AttributeError):
        result.intent = "specific_time"  # type: ignore[misc]


def test_route_result_invalid_intent_fallback():
    """잘못된 intent는 open_ended로 폴백한다."""
    result = RouteResult(
        intent="invalid_intent",
        confidence=0.8,
        edition_hint=None,
        output_type=None,
        type_filter=None,
        section_filter=None,
        reasoning="test",
    )
    assert result.intent == "open_ended"


def test_route_result_confidence_clamped():
    """confidence는 [0, 1] 범위로 클램핑된다."""
    result = RouteResult(
        intent="open_ended",
        confidence=1.5,
        edition_hint=None,
        output_type=None,
        type_filter=None,
        section_filter=None,
        reasoning="test",
    )
    assert result.confidence == 1.0


def test_route_result_invalid_output_type():
    """잘못된 output_type은 None으로 설정된다."""
    result = RouteResult(
        intent="content_generation",
        confidence=0.9,
        edition_hint=None,
        output_type="invalid_type",
        type_filter=None,
        section_filter=None,
        reasoning="test",
    )
    assert result.output_type is None


def test_route_result_valid_fields():
    """모든 필드가 올바르게 설정된다."""
    result = RouteResult(
        intent="specific_time",
        confidence=0.95,
        edition_hint="2020-14차",
        output_type="summary",
        type_filter=("definition", "principle"),
        section_filter="인사관리",
        reasoning="14차 개정판 질의",
    )
    assert result.intent == "specific_time"
    assert result.confidence == 0.95
    assert result.edition_hint == "2020-14차"
    assert result.output_type == "summary"
    assert result.type_filter == ("definition", "principle")
    assert result.section_filter == "인사관리"


# ---------------------------------------------------------------------------
# _parse_route_response 테스트
# ---------------------------------------------------------------------------


def test_parse_valid_json():
    """유효한 JSON 응답을 파싱한다."""
    text = '{"intent": "general_definition", "confidence": 0.92, "edition_hint": null, "output_type": null}'
    result = _parse_route_response(text)
    assert result.intent == "general_definition"
    assert result.confidence == 0.92


def test_parse_json_code_block():
    """```json 코드 블록을 파싱한다."""
    text = '```json\n{"intent": "specific_time", "confidence": 0.88, "edition_hint": "2020-14차"}\n```'
    result = _parse_route_response(text)
    assert result.intent == "specific_time"
    assert result.edition_hint == "2020-14차"


def test_parse_with_type_filter():
    """type_filter를 올바르게 파싱한다."""
    text = '{"intent": "content_generation", "confidence": 0.9, "output_type": "card", "type_filter": ["definition", "principle"]}'
    result = _parse_route_response(text)
    assert result.type_filter == ("definition", "principle")


def test_parse_invalid_type_filter_cleaned():
    """유효하지 않은 type_filter 항목은 제거된다."""
    text = '{"intent": "open_ended", "confidence": 0.8, "type_filter": ["definition", "invalid_type"]}'
    result = _parse_route_response(text)
    assert result.type_filter == ("definition",)


def test_parse_all_invalid_type_filter():
    """모든 type_filter가 유효하지 않으면 None."""
    text = '{"intent": "open_ended", "confidence": 0.8, "type_filter": ["invalid"]}'
    result = _parse_route_response(text)
    assert result.type_filter is None


def test_parse_invalid_json_fallback():
    """유효하지 않은 JSON은 폴백된다."""
    result = _parse_route_response("not valid json at all")
    assert result.intent == "open_ended"
    assert result.confidence == 0.5


def test_parse_non_numeric_confidence():
    """숫자가 아닌 confidence는 0.5로 폴백한다."""
    text = '{"intent": "general_definition", "confidence": "high"}'
    result = _parse_route_response(text)
    assert result.intent == "general_definition"
    assert result.confidence == 0.5


def test_parse_v1_compat_query_type():
    """v1 호환: query_type → intent 매핑."""
    text = '{"query_type": "general_definition", "confidence": 0.9}'
    result = _parse_route_response(text)
    assert result.intent == "general_definition"


# ---------------------------------------------------------------------------
# route_query 테스트
# ---------------------------------------------------------------------------


def _make_mock_client(response_text: str) -> MagicMock:
    """모킹된 Anthropic 클라이언트를 생성한다."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=response_text)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    return mock_client


def test_route_query_success():
    """정상적인 라우팅."""
    client = _make_mock_client('{"intent": "general_definition", "confidence": 0.95}')
    result = route_query("SUPEX란 무엇인가?", "system prompt", client)
    assert result.intent == "general_definition"
    assert result.confidence == 0.95


def test_route_query_uses_custom_model():
    """config에서 전달된 모델/토큰을 사용한다."""
    client = _make_mock_client('{"intent": "open_ended", "confidence": 0.8}')
    route_query(
        "test",
        "prompt",
        client,
        model="custom-router-model",
        max_tokens=300,
    )
    call_kwargs = client.messages.create.call_args
    assert call_kwargs.kwargs["model"] == "custom-router-model"
    assert call_kwargs.kwargs["max_tokens"] == 300


def test_route_query_empty_query():
    """빈 질의는 폴백."""
    client = MagicMock()
    result = route_query("", "system prompt", client)
    assert result.intent == "open_ended"
    client.messages.create.assert_not_called()


def test_route_query_client_error():
    """클라이언트 오류 시 폴백."""
    client = MagicMock()
    client.messages.create.side_effect = Exception("API error")
    result = route_query("test query", "system prompt", client)
    assert result.intent == "open_ended"
    assert result.confidence == 0.5


# ---------------------------------------------------------------------------
# parse_count_from_query 테스트
# ---------------------------------------------------------------------------


def test_parse_count_cards():
    """카드 갯수 파싱."""
    assert parse_count_from_query("5장의 카드를 만들어줘") == 5


def test_parse_count_quiz():
    """퀴즈 갯수 파싱."""
    assert parse_count_from_query("퀴즈 3개 만들어줘") == 3


def test_parse_count_max_limit():
    """최대 20개 제한."""
    assert parse_count_from_query("100문제") == 20


def test_parse_count_default():
    """갯수 힌트 없으면 기본 3."""
    assert parse_count_from_query("카드 만들어줘") == 3


# ---------------------------------------------------------------------------
# compute_dynamic_top_k 테스트
# ---------------------------------------------------------------------------


def test_dynamic_top_k_non_content():
    """content_generation 아니면 base_top_k 그대로."""
    assert compute_dynamic_top_k("open_ended", None, "query", 5) == 5


def test_dynamic_top_k_card():
    """카드: count × 3."""
    assert compute_dynamic_top_k("content_generation", "card", "5장 카드", 5) == 15


def test_dynamic_top_k_quiz():
    """퀴즈: count × 3."""
    assert compute_dynamic_top_k("content_generation", "quiz", "3개 문제", 5) == 9


def test_dynamic_top_k_comparison():
    """비교표: 최소 12."""
    assert (
        compute_dynamic_top_k("content_generation", "comparison_table", "비교", 5) == 12
    )


def test_dynamic_top_k_summary():
    """요약: 최소 8."""
    assert compute_dynamic_top_k("content_generation", "summary", "요약", 5) == 8


def test_dynamic_top_k_respects_base():
    """base_top_k가 더 크면 base_top_k 반환."""
    assert compute_dynamic_top_k("content_generation", "summary", "요약", 20) == 20


# ---------------------------------------------------------------------------
# Constants 테스트
# ---------------------------------------------------------------------------


def test_valid_intents():
    """5가지 유효 intent."""
    assert len(VALID_INTENTS) == 5
    assert "open_ended" in VALID_INTENTS


def test_valid_output_types():
    """5가지 유효 output type."""
    assert len(VALID_OUTPUT_TYPES) == 5
    assert "card" in VALID_OUTPUT_TYPES


def test_valid_quote_types():
    """6가지 유효 quote type."""
    assert len(VALID_QUOTE_TYPES) == 6
    assert "definition" in VALID_QUOTE_TYPES
