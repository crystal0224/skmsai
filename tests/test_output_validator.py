#!/usr/bin/env python3
"""lib/output_validator.py 단위 테스트 (PR-7).

Usage:
    python tests/test_output_validator.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure scripts/ is on sys.path
_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPT_DIR))

from lib.output_validator import (  # noqa: E402
    ValidationResult,
    _extract_json,
    _is_valid_quote_id,
    _safe_errors,
    validate_content_output,
)


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


def test_extract_json_code_block():
    """```json 블록에서 JSON 추출."""
    text = 'some text\n```json\n{"title": "test"}\n```\nmore text'
    result = _extract_json(text)
    assert result == {"title": "test"}
    print("  PASS: extract json code block")


def test_extract_json_bare():
    """순수 JSON 추출."""
    text = '  {"title": "test", "body": "hello"}'
    result = _extract_json(text)
    assert result == {"title": "test", "body": "hello"}
    print("  PASS: extract json bare")


def test_extract_json_array():
    """JSON 배열 추출."""
    text = '[{"front": "Q"}, {"front": "Q2"}]'
    result = _extract_json(text)
    assert isinstance(result, list)
    assert len(result) == 2
    print("  PASS: extract json array")


def test_extract_json_none():
    """JSON 없는 텍스트."""
    text = "This is just plain text with no JSON."
    result = _extract_json(text)
    assert result is None
    print("  PASS: extract json none")


def test_is_valid_quote_id():
    """quote_id 형식 검증 (4-segment 이상 필수)."""
    assert _is_valid_quote_id("2020-14차|_root|principle|001") is True
    assert _is_valid_quote_id("") is False
    assert _is_valid_quote_id("invalid") is False
    # 2-segment는 거부 (기존에는 통과했던 케이스)
    assert _is_valid_quote_id("edition|only") is False
    # 3-segment도 거부
    assert _is_valid_quote_id("a|b|c") is False
    # 빈 segment가 있으면 거부
    assert _is_valid_quote_id("a||c|d") is False
    print("  PASS: is valid quote_id")


# ---------------------------------------------------------------------------
# ValidationResult tests
# ---------------------------------------------------------------------------


def test_validation_result_pass():
    """통과 결과."""
    vr = ValidationResult(passed=True, errors=[], output_type="summary")
    assert vr.passed is True
    assert vr.errors == []
    assert vr.output_type == "summary"
    d = vr.to_dict()
    assert d["passed"] is True
    assert d["error_count"] == 0
    print("  PASS: validation result pass")


def test_validation_result_fail():
    """실패 결과."""
    vr = ValidationResult(passed=False, errors=["error1", "error2"], output_type="card")
    assert vr.passed is False
    assert len(vr.errors) == 2
    d = vr.to_dict()
    assert d["passed"] is False
    assert d["error_count"] == 2
    print("  PASS: validation result fail")


def test_validation_result_immutability():
    """errors 리스트 변경이 원본에 영향 없음."""
    vr = ValidationResult(passed=False, errors=["e1"], output_type="quiz")
    errors = vr.errors
    errors.append("injected")
    assert len(vr.errors) == 1
    print("  PASS: validation result immutability")


# ---------------------------------------------------------------------------
# Summary validation tests
# ---------------------------------------------------------------------------


def test_validate_summary_pass():
    """유효한 summary 출력."""
    raw = json.dumps(
        {
            "title": "SKMS 요약",
            "body": "SK 경영철학의 핵심은 구성원 행복 추구이다. VWBE를 통해 SUPEX를 달성한다.",
            "key_points": ["구성원 행복", "VWBE", "SUPEX"],
            "citations": ["2020-14차|_root|principle|001"],
        },
        ensure_ascii=False,
    )
    result = validate_content_output(raw, "summary")
    assert result.passed is True, f"errors: {result.errors}"
    print("  PASS: validate summary pass")


def test_validate_summary_missing_citation():
    """citations에 quote_id 없으면 실패."""
    raw = json.dumps(
        {
            "title": "SKMS 요약",
            "body": "SK 경영철학의 핵심은 구성원 행복이다. VWBE를 통해 SUPEX를 달성한다.",
            "key_points": ["구성원 행복"],
            "citations": ["출처 불명"],
        },
        ensure_ascii=False,
    )
    result = validate_content_output(raw, "summary")
    assert result.passed is False
    assert any("quote_id" in e for e in result.errors)
    print("  PASS: validate summary missing citation")


def test_validate_summary_no_citations():
    """citations 필드 없으면 실패."""
    raw = json.dumps(
        {
            "title": "SKMS 요약",
            "body": "SK 경영철학의 핵심은 구성원 행복이다. VWBE를 통해 SUPEX를 달성한다.",
            "key_points": ["구성원 행복"],
        },
        ensure_ascii=False,
    )
    result = validate_content_output(raw, "summary")
    assert result.passed is False
    print("  PASS: validate summary no citations")


# ---------------------------------------------------------------------------
# Card validation tests
# ---------------------------------------------------------------------------


def test_validate_card_single_pass():
    """유효한 단일 카드."""
    raw = json.dumps(
        {
            "front": "VWBE란?",
            "back": "자발적·의욕적 두뇌활용",
            "edition_tag": "2020-14차",
            "citations": ["2020-14차|_root|principle|005"],
        },
        ensure_ascii=False,
    )
    result = validate_content_output(raw, "card")
    assert result.passed is True
    print("  PASS: validate card single pass")


def test_validate_card_list_pass():
    """유효한 카드 목록."""
    cards = [
        {
            "front": "VWBE란?",
            "back": "자발적·의욕적 두뇌활용",
            "edition_tag": "2020",
            "citations": ["2020-14차|_root|principle|005"],
        },
        {
            "front": "패기란?",
            "back": "VWBE가 외부로 발현",
            "edition_tag": "2020",
            "citations": ["2020-14차|_root|principle|006"],
        },
    ]
    raw = json.dumps({"cards": cards}, ensure_ascii=False)
    result = validate_content_output(raw, "card")
    assert result.passed is True
    print("  PASS: validate card list pass")


def test_validate_card_no_quote_id():
    """카드에 유효한 quote_id 없으면 실패."""
    raw = json.dumps(
        {
            "front": "VWBE란?",
            "back": "자발적·의욕적 두뇌활용",
            "citations": ["14차 개정판"],
        },
        ensure_ascii=False,
    )
    result = validate_content_output(raw, "card")
    assert result.passed is False
    print("  PASS: validate card no quote_id")


def test_validate_card_too_many_citations():
    """카드당 citations 3개 이상이면 실패."""
    raw = json.dumps(
        {
            "front": "VWBE란?",
            "back": "답변",
            "citations": [
                "2020-14차|_root|principle|001",
                "2020-14차|_root|principle|002",
                "2020-14차|_root|principle|003",
            ],
        },
        ensure_ascii=False,
    )
    result = validate_content_output(raw, "card")
    assert result.passed is False
    print("  PASS: validate card too many citations")


# ---------------------------------------------------------------------------
# Quiz validation tests
# ---------------------------------------------------------------------------


def test_validate_quiz_pass():
    """유효한 퀴즈."""
    raw = json.dumps(
        {
            "question": "SK 경영의 궁극적 목적은?",
            "choices": ["이익 극대화", "구성원 행복", "시장 점유율", "기술 혁신"],
            "correct_index": 1,
            "explanation": "SKMS에 따르면 경영의 궁극적 목적은 구성원 행복이다.",
            "citations": ["2020-14차|_root|principle|004"],
        },
        ensure_ascii=False,
    )
    result = validate_content_output(raw, "quiz")
    assert result.passed is True
    print("  PASS: validate quiz pass")


def test_validate_quiz_wrong_choices_count():
    """선택지 3개면 실패."""
    raw = json.dumps(
        {
            "question": "질문",
            "choices": ["A", "B", "C"],
            "correct_index": 0,
            "explanation": "설명",
            "citations": ["2020-14차|_root|principle|001"],
        },
        ensure_ascii=False,
    )
    result = validate_content_output(raw, "quiz")
    assert result.passed is False
    print("  PASS: validate quiz wrong choices count")


def test_validate_quiz_no_quote_id():
    """정답 근거에 quote_id 없으면 실패."""
    raw = json.dumps(
        {
            "question": "질문",
            "choices": ["A", "B", "C", "D"],
            "correct_index": 0,
            "explanation": "설명",
            "citations": ["참고자료"],
        },
        ensure_ascii=False,
    )
    result = validate_content_output(raw, "quiz")
    assert result.passed is False
    print("  PASS: validate quiz no quote_id")


def test_validate_quiz_invalid_correct_index():
    """correct_index 범위 초과."""
    raw = json.dumps(
        {
            "question": "질문",
            "choices": ["A", "B", "C", "D"],
            "correct_index": 4,
            "explanation": "설명",
            "citations": ["2020-14차|_root|principle|001"],
        },
        ensure_ascii=False,
    )
    result = validate_content_output(raw, "quiz")
    assert result.passed is False
    print("  PASS: validate quiz invalid correct_index")


# ---------------------------------------------------------------------------
# Comparison table validation tests
# ---------------------------------------------------------------------------


def test_validate_comparison_pass():
    """유효한 비교표."""
    raw = json.dumps(
        {
            "concept": "패기",
            "columns": ["1979-초판", "2020-14차"],
            "rows": [
                {
                    "aspect": "정의",
                    "values": {
                        "1979-초판": "열정적 실행",
                        "2020-14차": "VWBE의 외부 발현",
                    },
                    "quote_ids": [
                        "1979-초판|_root|definition|001",
                        "2020-14차|_root|principle|006",
                    ],
                }
            ],
            "evolution_summary": "패기 개념이 확장되었다.",
        },
        ensure_ascii=False,
    )
    result = validate_content_output(raw, "comparison_table")
    assert result.passed is True
    print("  PASS: validate comparison pass")


def test_validate_comparison_row_no_quote():
    """비교 행에 quote_id 없으면 실패."""
    raw = json.dumps(
        {
            "concept": "패기",
            "columns": ["초판", "14차"],
            "rows": [
                {
                    "aspect": "정의",
                    "values": {"초판": "v1", "14차": "v2"},
                    "quote_ids": ["출처 없음"],
                }
            ],
        },
        ensure_ascii=False,
    )
    result = validate_content_output(raw, "comparison_table")
    assert result.passed is False
    print("  PASS: validate comparison row no quote")


# ---------------------------------------------------------------------------
# Slide validation tests
# ---------------------------------------------------------------------------


def test_validate_slide_pass():
    """유효한 슬라이드."""
    raw = json.dumps(
        {
            "slides": [
                {
                    "slide_number": 1,
                    "title": "SKMS 소개",
                    "body": ["SK 경영철학", "구성원 행복 추구"],
                    "sources": ["2020-14차|_root|principle|001"],
                }
            ]
        },
        ensure_ascii=False,
    )
    result = validate_content_output(raw, "slide")
    assert result.passed is True
    print("  PASS: validate slide pass")


def test_validate_slide_no_source():
    """슬라이드에 sources 없으면 실패."""
    raw = json.dumps(
        {
            "slide_number": 1,
            "title": "SKMS 소개",
            "body": ["SK 경영철학"],
            "sources": [],
        },
        ensure_ascii=False,
    )
    result = validate_content_output(raw, "slide")
    assert result.passed is False
    print("  PASS: validate slide no source")


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


def test_validate_unknown_type():
    """알 수 없는 output_type."""
    result = validate_content_output("{}", "unknown_type")
    assert result.passed is False
    assert "알 수 없는" in result.errors[0]
    print("  PASS: validate unknown type")


def test_validate_no_json():
    """JSON 없는 응답."""
    result = validate_content_output("순수 텍스트 응답입니다.", "summary")
    assert result.passed is False
    assert "JSON" in result.errors[0]
    print("  PASS: validate no json")


def test_validate_json_in_markdown():
    """마크다운 코드 블록 내 JSON."""
    raw = '```json\n{"title": "T", "body": "SK 경영철학 요약입니다.", "key_points": ["핵심"], "citations": ["2020-14차|_root|principle|001"]}\n```'
    result = validate_content_output(raw, "summary")
    assert result.passed is True
    print("  PASS: validate json in markdown")


def test_validate_array_as_cards():
    """배열 형태의 카드 목록."""
    cards = [
        {
            "front": "Q1",
            "back": "A1",
            "citations": ["2020-14차|_root|principle|001"],
        },
        {
            "front": "Q2",
            "back": "A2",
            "citations": ["2020-14차|_root|principle|002"],
        },
    ]
    raw = json.dumps(cards, ensure_ascii=False)
    result = validate_content_output(raw, "card")
    assert result.passed is True
    print("  PASS: validate array as cards")


def test_to_dict_for_trace():
    """to_dict()가 trace에 필요한 필드를 포함."""
    vr = ValidationResult(
        passed=False,
        errors=["e1", "e2", "e3", "e4", "e5", "e6"],
        output_type="quiz",
    )
    d = vr.to_dict()
    assert "passed" in d
    assert "output_type" in d
    assert "error_count" in d
    assert d["error_count"] == 6
    assert len(d["errors"]) <= 5  # 최대 5개
    print("  PASS: to_dict for trace")


def test_safe_errors_no_field_values():
    """_safe_errors가 LLM 필드 값을 포함하지 않는지 검증."""
    from pydantic import ValidationError as PydanticValidationError

    from lib.output_validator import SummaryOutput

    # 의도적으로 잘못된 데이터로 ValidationError 유발
    try:
        SummaryOutput.model_validate(
            {
                "title": "T",
                "body": "short",  # min_length=10 위반
                "key_points": ["k"],
                "citations": ["no-pipe"],
            }
        )
        assert False, "Should have raised ValidationError"
    except PydanticValidationError as e:
        safe = _safe_errors(e)
        assert len(safe) >= 1
        # safe 메시지에 원본 필드 값("short", "no-pipe")이 포함되지 않아야 함
        for msg in safe:
            assert "short" not in msg, f"Field value leaked: {msg}"
            assert "no-pipe" not in msg, f"Field value leaked: {msg}"
        print("  PASS: safe errors no field values")


def test_validation_errors_no_llm_data_in_trace():
    """validate_content_output의 errors가 LLM 데이터를 포함하지 않는지 검증."""
    raw = json.dumps(
        {
            "title": "T",
            "body": "short",
            "key_points": ["k"],
            "citations": ["출처 불명"],
        },
        ensure_ascii=False,
    )
    result = validate_content_output(raw, "summary")
    assert result.passed is False
    # errors에 원본 필드 값이 포함되지 않아야 함
    for err in result.errors:
        assert "short" not in err, f"LLM data leaked into error: {err}"
    print("  PASS: validation errors no llm data in trace")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("[PR-7] lib/output_validator.py 단위 테스트")
    print("=" * 50)

    tests = [
        test_extract_json_code_block,
        test_extract_json_bare,
        test_extract_json_array,
        test_extract_json_none,
        test_is_valid_quote_id,
        test_validation_result_pass,
        test_validation_result_fail,
        test_validation_result_immutability,
        test_validate_summary_pass,
        test_validate_summary_missing_citation,
        test_validate_summary_no_citations,
        test_validate_card_single_pass,
        test_validate_card_list_pass,
        test_validate_card_no_quote_id,
        test_validate_card_too_many_citations,
        test_validate_quiz_pass,
        test_validate_quiz_wrong_choices_count,
        test_validate_quiz_no_quote_id,
        test_validate_quiz_invalid_correct_index,
        test_validate_comparison_pass,
        test_validate_comparison_row_no_quote,
        test_validate_slide_pass,
        test_validate_slide_no_source,
        test_validate_unknown_type,
        test_validate_no_json,
        test_validate_json_in_markdown,
        test_validate_array_as_cards,
        test_to_dict_for_trace,
        test_safe_errors_no_field_values,
        test_validation_errors_no_llm_data_in_trace,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test.__name__}: {e}")
            failed += 1

    print(f"\n{'=' * 50}")
    print(f"결과: {passed} PASS, {failed} FAIL / {len(tests)} total")

    if failed > 0:
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
