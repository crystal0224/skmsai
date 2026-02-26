#!/usr/bin/env python3
"""observability/tracing.py 단위 테스트.

로컬 백엔드만 테스트 (Langfuse/LangSmith 불필요).

Usage:
    python tests/test_tracing.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure scripts/ is on sys.path
_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPT_DIR))

from observability.tracing import (  # noqa: E402
    PipelineTrace,
    _estimate_tokens,
    _safe_retrieval_hit,
    load_observability_config,
    start_trace,
)


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


def test_load_observability_config_default():
    """설정 파일 없을 때 기본값 반환."""
    config = load_observability_config("nonexistent/path.yaml")
    assert config["tracer"] == "auto"
    assert config["privacy"]["store_raw_text"] is False
    assert config["privacy"]["text_preview"]["enabled"] is False
    print("  PASS: load_observability_config default")


def test_load_observability_config_from_file():
    """config/observability.yaml 정상 로드."""
    config = load_observability_config("config/observability.yaml")
    assert "tracer" in config
    assert "privacy" in config
    print("  PASS: load_observability_config from file")


# ---------------------------------------------------------------------------
# Privacy helper tests
# ---------------------------------------------------------------------------


def _make_hit() -> dict:
    """테스트용 검색 결과 dict."""
    return {
        "quote_id": "2020-14차|인사관리|definition|001",
        "doc_id": "2020-14차",
        "year": 2020,
        "edition": "2020-14차",
        "type": "definition",
        "score": 0.8567,
        "span": [100, 200],
        "sha256": "abc123",
        "quality_flags": ["ocr_suspect"],
        "text": "인사관리란 조직의 인적자원을 효과적으로 관리하는 활동이다.",
    }


def test_safe_retrieval_hit_no_text():
    """기본 설정에서 원문 텍스트가 제외되는지 확인."""
    hit = _make_hit()
    config = {"privacy": {"text_preview": {"enabled": False}}}
    safe = _safe_retrieval_hit(hit, config)

    assert "text" not in safe, "원문 텍스트가 포함되면 안 됨"
    assert "text_preview" not in safe, "text_preview가 OFF인데 포함됨"
    assert safe["quote_id"] == hit["quote_id"]
    assert safe["doc_id"] == hit["doc_id"]
    assert safe["sha256"] == hit["sha256"]
    assert safe["span"] == [100, 200]
    assert safe["score"] == 0.8567
    assert safe["text_length"] == len(hit["text"])
    assert safe["quality_flags"] == ["ocr_suspect"]
    print("  PASS: _safe_retrieval_hit no text")


def test_safe_retrieval_hit_with_preview():
    """text_preview ON + max_chars 제한."""
    hit = _make_hit()
    hit["text"] = "가" * 500  # 500자 텍스트
    config = {"privacy": {"text_preview": {"enabled": True, "max_chars": 400}}}
    safe = _safe_retrieval_hit(hit, config)

    assert "text_preview" in safe
    assert len(safe["text_preview"]) == 403  # 400 + "..."
    assert safe["text_preview"].endswith("...")
    assert safe["text_length"] == 500
    print("  PASS: _safe_retrieval_hit with preview")


def test_safe_retrieval_hit_short_text_preview():
    """짧은 텍스트는 잘림 없이 전체 포함."""
    hit = _make_hit()
    hit["text"] = "짧은 텍스트"
    config = {"privacy": {"text_preview": {"enabled": True, "max_chars": 400}}}
    safe = _safe_retrieval_hit(hit, config)

    assert safe["text_preview"] == "짧은 텍스트"
    assert "..." not in safe["text_preview"]
    print("  PASS: _safe_retrieval_hit short text preview")


def test_safe_retrieval_hit_immutability():
    """_safe_retrieval_hit이 원본 hit을 변경하지 않는지 확인."""
    hit = _make_hit()
    original_text = hit["text"]
    original_flags = hit["quality_flags"].copy()
    config = {"privacy": {"text_preview": {"enabled": True, "max_chars": 400}}}
    _safe_retrieval_hit(hit, config)

    assert hit["text"] == original_text
    assert hit["quality_flags"] == original_flags
    print("  PASS: _safe_retrieval_hit immutability")


# ---------------------------------------------------------------------------
# Token estimation tests
# ---------------------------------------------------------------------------


def test_estimate_tokens_korean():
    """한국어 텍스트 토큰 추정 (~2 chars/token)."""
    text = "가" * 100  # 100% 한국어
    tokens = _estimate_tokens(text)
    assert tokens == 50, f"Expected 50, got {tokens}"
    print("  PASS: _estimate_tokens korean")


def test_estimate_tokens_english():
    """영문 텍스트 토큰 추정 (~4 chars/token)."""
    text = "a" * 100  # 100% 영문
    tokens = _estimate_tokens(text)
    assert tokens == 25, f"Expected 25, got {tokens}"
    print("  PASS: _estimate_tokens english")


def test_estimate_tokens_empty():
    """빈 문자열 → 0."""
    assert _estimate_tokens("") == 0
    print("  PASS: _estimate_tokens empty")


# ---------------------------------------------------------------------------
# PipelineTrace tests
# ---------------------------------------------------------------------------


def test_start_trace_returns_trace():
    """start_trace가 PipelineTrace 인스턴스를 반환."""
    config = load_observability_config("nonexistent.yaml")
    trace = start_trace("테스트 질의", config)
    assert isinstance(trace, PipelineTrace)
    assert len(trace.trace_id) == 36  # UUID 형식
    trace.finish()
    print("  PASS: start_trace returns trace")


def test_trace_context_manager():
    """context manager로 사용 시 finish() 자동 호출."""
    config = load_observability_config("nonexistent.yaml")
    with start_trace("테스트 질의", config) as trace:
        assert isinstance(trace, PipelineTrace)
        trace.log_router(
            intent="general_definition",
            confidence=0.92,
            edition_hint=None,
            output_type=None,
        )
    # finish() 자동 호출 확인 (예외 없이 종료)
    print("  PASS: trace context manager")


def test_trace_steps_recorded():
    """각 단계의 이벤트가 steps에 기록되는지 확인."""
    config = {
        "tracer": "local",
        "console": {"print_trace_id": False, "print_step_summary": False},
        "privacy": {"text_preview": {"enabled": False}},
    }
    with start_trace("테스트", config) as trace:
        trace.log_router(
            intent="evolution_comparison",
            confidence=0.95,
            edition_hint=None,
            output_type=None,
        )
        trace.log_policy({"alpha": 0.6, "rrf_k": 60, "latest_first": False})
        trace.log_retrieval([_make_hit(), _make_hit()])
        trace.log_prompt("컨텍스트 문자열", "answer.md")
        trace.log_response("응답 텍스트")

    steps = trace.steps
    assert len(steps) == 5, f"Expected 5 steps, got {len(steps)}"

    step_names = [s["step"] for s in steps]
    assert step_names == ["router", "policy", "retrieval", "prompt", "response"]

    # router step 검증
    assert steps[0]["intent"] == "evolution_comparison"
    assert steps[0]["confidence"] == 0.95

    # policy step 검증
    assert steps[1]["alpha"] == 0.6

    # retrieval step 검증
    assert steps[2]["hit_count"] == 2
    assert len(steps[2]["hits"]) == 2
    # privacy: 원문 텍스트 없음
    for hit in steps[2]["hits"]:
        assert "text" not in hit
        assert "text_preview" not in hit
        assert "text_length" in hit

    # prompt step 검증
    assert steps[3]["system_prompt"] == "answer.md"
    assert steps[3]["context_char_count"] > 0

    # response step 검증
    assert steps[4]["response_char_count"] > 0

    print("  PASS: trace steps recorded")


def test_trace_steps_immutability():
    """steps 프로퍼티가 내부 리스트의 복사본을 반환하는지 확인."""
    config = {
        "tracer": "local",
        "console": {"print_trace_id": False, "print_step_summary": False},
        "privacy": {"text_preview": {"enabled": False}},
    }
    with start_trace("테스트", config) as trace:
        trace.log_router(
            intent="open_ended",
            confidence=0.5,
            edition_hint=None,
            output_type=None,
        )

    steps1 = trace.steps
    steps2 = trace.steps
    assert steps1 is not steps2, "steps should return a new list each time"
    print("  PASS: trace steps immutability")


def test_trace_id_format():
    """trace_id가 UUID v4 형식인지 확인."""
    import re

    config = {
        "tracer": "local",
        "console": {"print_trace_id": False, "print_step_summary": False},
        "privacy": {},
    }
    trace = start_trace("테스트", config)
    uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    assert uuid_pattern.match(trace.trace_id), f"Invalid UUID: {trace.trace_id}"
    trace.finish()
    print("  PASS: trace_id format")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("[PR-2] observability/tracing.py 단위 테스트")
    print("=" * 50)

    tests = [
        test_load_observability_config_default,
        test_load_observability_config_from_file,
        test_safe_retrieval_hit_no_text,
        test_safe_retrieval_hit_with_preview,
        test_safe_retrieval_hit_short_text_preview,
        test_safe_retrieval_hit_immutability,
        test_estimate_tokens_korean,
        test_estimate_tokens_english,
        test_estimate_tokens_empty,
        test_start_trace_returns_trace,
        test_trace_context_manager,
        test_trace_steps_recorded,
        test_trace_steps_immutability,
        test_trace_id_format,
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
