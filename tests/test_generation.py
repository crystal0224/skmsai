"""GenerationService 테스트.

PR-012: 생성 파이프라인 (context formatting, LLM 호출, 검증).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.generation import (  # noqa: E402
    GenerationConfig,
    GenerationResult,
    GenerationService,
    TemporalConflict,
    _estimate_tokens,
    detect_temporal_conflicts,
    extract_quote_ids,
    format_context,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_mock_client(response_text: str = "테스트 답변") -> MagicMock:
    """모킹된 Anthropic 클라이언트."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=response_text)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    return mock_client


def _make_test_hits() -> list[dict]:
    """테스트용 검색 결과 hits."""
    return [
        {
            "quote_id": "2020-14차|VWBE|definition|001",
            "text": "VWBE Culture 정의 텍스트",
            "edition": "2020-14차",
            "type": "definition",
            "chapter_path": ["VWBE Culture", "1. 정의"],
            "quality_flags": [],
        },
        {
            "quote_id": "1979-초판|기업관|narrative|001",
            "text": "초판 기업관 서술 텍스트",
            "edition": "1979-초판",
            "type": "narrative",
            "chapter_path": ["기업관"],
            "quality_flags": ["ocr_error"],
        },
    ]


# ---------------------------------------------------------------------------
# GenerationConfig 테스트
# ---------------------------------------------------------------------------


def test_generation_config_defaults():
    """기본 설정이 올바르다."""
    config = GenerationConfig.from_yaml()
    assert config.model == "claude-sonnet-4-20250514"
    assert config.max_tokens == 3000
    assert config.max_retries == 1


def test_generation_config_is_frozen():
    """GenerationConfig는 불변이다."""
    config = GenerationConfig.from_yaml()
    with pytest.raises(AttributeError):
        config.model = "other-model"  # type: ignore[misc]


def test_generation_config_from_yaml(tmp_path):
    """YAML 파일에서 설정을 로드한다."""
    yaml_content = "generation:\n  model: custom-model\n  max_tokens: 5000\n"
    config_path = tmp_path / "generation.yaml"
    config_path.write_text(yaml_content)
    config = GenerationConfig.from_yaml(config_path)
    assert config.model == "custom-model"
    assert config.max_tokens == 5000
    assert config.max_retries == 1  # 기본값 유지


def test_generation_config_missing_file():
    """존재하지 않는 파일이면 기본값."""
    config = GenerationConfig.from_yaml(Path("/nonexistent/path.yaml"))
    assert config.model == "claude-sonnet-4-20250514"


def test_generation_config_respects_token_caps(tmp_path):
    """토큰 cap 설정이 있으면 max_tokens를 클램프한다."""
    yaml_content = (
        "generation:\n"
        "  max_tokens: 5000\n"
        "  max_tokens_cap: 1200\n"
        "  router_max_tokens: 900\n"
        "  router_max_tokens_cap: 300\n"
    )
    config_path = tmp_path / "generation.yaml"
    config_path.write_text(yaml_content)
    config = GenerationConfig.from_yaml(config_path)
    assert config.max_tokens == 1200
    assert config.router_max_tokens == 300


# ---------------------------------------------------------------------------
# GenerationResult 테스트
# ---------------------------------------------------------------------------


def test_generation_result_is_frozen():
    """GenerationResult는 불변이다."""
    result = GenerationResult(
        answer="test",
        prompt_name="answer.md",
        validation_passed=None,
        validation_errors=(),
        retried=False,
        context_token_estimate=100,
    )
    with pytest.raises(AttributeError):
        result.answer = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TemporalConflict 테스트
# ---------------------------------------------------------------------------


def test_temporal_conflict_is_frozen():
    """TemporalConflict는 불변이다."""
    conflict = TemporalConflict(
        has_conflict=False,
        conflicting_editions=(),
        definition_count=0,
    )
    with pytest.raises(AttributeError):
        conflict.has_conflict = True  # type: ignore[misc]


def test_detect_no_conflict():
    """정의가 한 개정판에만 있으면 충돌 없음."""
    hits = [
        {"type": "definition", "edition": "2020-14차"},
        {"type": "narrative", "edition": "1979-초판"},
    ]
    result = detect_temporal_conflicts(hits)
    assert not result.has_conflict
    assert result.definition_count == 1


def test_detect_conflict():
    """정의가 2개 이상 개정판에 걸치면 충돌."""
    hits = [
        {"type": "definition", "edition": "2020-14차"},
        {"type": "definition", "edition": "1979-초판"},
    ]
    result = detect_temporal_conflicts(hits)
    assert result.has_conflict
    assert result.definition_count == 2
    assert len(result.conflicting_editions) == 2


def test_detect_no_definitions():
    """정의 타입이 없으면 충돌 없음."""
    hits = [
        {"type": "narrative", "edition": "2020-14차"},
        {"type": "principle", "edition": "1979-초판"},
    ]
    result = detect_temporal_conflicts(hits)
    assert not result.has_conflict
    assert result.definition_count == 0


def test_detect_empty_hits():
    """빈 리스트는 충돌 없음."""
    result = detect_temporal_conflicts([])
    assert not result.has_conflict


# ---------------------------------------------------------------------------
# format_context 테스트
# ---------------------------------------------------------------------------


def test_format_context_metadata_block():
    """METADATA 블록이 올바르게 포맷된다."""
    hits = _make_test_hits()
    conflict = TemporalConflict(
        has_conflict=False, conflicting_editions=(), definition_count=0
    )
    ctx = format_context(hits, "open_ended", conflict)
    assert "[METADATA]" in ctx
    assert "intent: open_ended" in ctx
    assert "temporal_conflict: false" in ctx


def test_format_context_chunk_blocks():
    """CHUNK 블록이 올바르게 포맷된다."""
    hits = _make_test_hits()
    conflict = TemporalConflict(
        has_conflict=False, conflicting_editions=(), definition_count=0
    )
    ctx = format_context(hits, "open_ended", conflict)
    assert "[CHUNK 1]" in ctx
    assert "[CHUNK 2]" in ctx
    assert "2020-14차|VWBE|definition|001" in ctx


def test_format_context_with_conflict():
    """충돌 정보가 포함된다."""
    hits = _make_test_hits()
    conflict = TemporalConflict(
        has_conflict=True,
        conflicting_editions=("1979-초판", "2020-14차"),
        definition_count=2,
    )
    ctx = format_context(hits, "general_definition", conflict)
    assert "temporal_conflict: true" in ctx


def test_format_context_with_output_specs():
    """content_generation 시 output_specs가 포함된다."""
    hits = _make_test_hits()
    conflict = TemporalConflict(
        has_conflict=False, conflicting_editions=(), definition_count=0
    )
    specs = {"output_types": {"card": {"description": "지식 카드"}}}
    ctx = format_context(
        hits, "content_generation", conflict, output_type="card", output_specs=specs
    )
    assert "지식 카드" in ctx


def test_format_context_empty_hits():
    """빈 hits는 메타데이터만 반환."""
    conflict = TemporalConflict(
        has_conflict=False, conflicting_editions=(), definition_count=0
    )
    ctx = format_context([], "open_ended", conflict)
    assert "[METADATA]" in ctx
    assert "[CHUNK" not in ctx


def test_format_context_missing_keys():
    """필수 키가 없는 hit도 안전하게 처리된다."""
    hits = [{"text": "some text"}]  # quote_id 없음
    conflict = TemporalConflict(
        has_conflict=False, conflicting_editions=(), definition_count=0
    )
    ctx = format_context(hits, "open_ended", conflict)
    assert "quote_id: unknown" in ctx
    assert "some text" in ctx


def test_format_context_non_string_chapter_path():
    """chapter_path 항목이 문자열이 아니어도 안전하게 처리된다."""
    hits = [
        {
            "quote_id": "test|001",
            "text": "text",
            "edition": "2020-14차",
            "type": "definition",
            "chapter_path": ["VWBE", 123, None],
            "quality_flags": [],
        }
    ]
    conflict = TemporalConflict(
        has_conflict=False, conflicting_editions=(), definition_count=0
    )
    ctx = format_context(hits, "open_ended", conflict)
    assert "VWBE > 123 > None" in ctx


# ---------------------------------------------------------------------------
# extract_quote_ids 테스트
# ---------------------------------------------------------------------------


def test_extract_quote_ids():
    """quote_id를 추출한다."""
    hits = _make_test_hits()
    ids = extract_quote_ids(hits)
    assert len(ids) == 2
    assert isinstance(ids, tuple)


def test_extract_quote_ids_empty():
    """빈 리스트는 빈 tuple."""
    ids = extract_quote_ids([])
    assert ids == ()


# ---------------------------------------------------------------------------
# GenerationService 테스트
# ---------------------------------------------------------------------------


def test_service_generate_basic():
    """기본 생성."""
    client = _make_mock_client("LLM 답변")
    service = GenerationService(client)
    result = service.generate("질의", "컨텍스트", "open_ended")
    assert result.answer == "LLM 답변"
    assert result.prompt_name == "answer.md"
    assert result.validation_passed is None


def test_service_generate_uses_config_model():
    """설정된 모델을 사용한다."""
    client = _make_mock_client("답변")
    config = GenerationConfig(
        model="custom-model",
        max_tokens=1000,
        router_model="custom-router",
        router_max_tokens=300,
        max_retries=0,
        prompts_dir="prompts",
    )
    service = GenerationService(client, config)
    service.generate("질의", "컨텍스트", "open_ended")
    call_kwargs = client.messages.create.call_args
    assert call_kwargs.kwargs["model"] == "custom-model"
    assert call_kwargs.kwargs["max_tokens"] == 1000


def test_service_select_prompt_answer():
    """non-content_generation은 answer.md 사용."""
    client = _make_mock_client()
    service = GenerationService(client)
    service._prompts = {"answer": "answer prompt", "content_gen": "content gen prompt"}
    prompt, name = service.select_prompt("open_ended")
    assert name == "answer.md"
    assert prompt == "answer prompt"


def test_service_select_prompt_content_gen():
    """content_generation은 content_gen.md 사용."""
    client = _make_mock_client()
    service = GenerationService(client)
    service._prompts = {"answer": "answer prompt", "content_gen": "content gen prompt"}
    prompt, name = service.select_prompt("content_generation")
    assert name == "content_gen.md"
    assert prompt == "content gen prompt"


def test_service_select_prompt_content_gen_fallback():
    """content_gen.md 없으면 answer.md로 폴백."""
    client = _make_mock_client()
    service = GenerationService(client)
    service._prompts = {"answer": "answer prompt"}
    prompt, name = service.select_prompt("content_generation")
    assert name == "answer.md"


def test_service_load_prompts(tmp_path):
    """프롬프트 파일을 로드한다."""
    (tmp_path / "answer.md").write_text("answer prompt")
    (tmp_path / "content_gen.md").write_text("content gen prompt")
    client = _make_mock_client()
    service = GenerationService(client)
    service.load_prompts(tmp_path)
    assert service.get_prompt("answer") == "answer prompt"
    assert service.get_prompt("content_gen") == "content gen prompt"


def test_service_generate_content_validation_pass():
    """content_generation 검증 통과."""
    valid_json = '{"title": "테스트 제목", "body": "SKMS의 인간중심 경영 원칙에 대한 요약입니다.", "key_points": ["포인트1"], "citations": ["2020-14차|VWBE|definition|001"]}'
    client = _make_mock_client(valid_json)
    service = GenerationService(client)
    result = service.generate("질의", "컨텍스트", "content_generation", "summary")
    assert result.validation_passed is True
    assert not result.retried


def test_service_generate_content_validation_retry():
    """content_generation 검증 실패 → 재시도."""
    bad_answer = "not valid json"
    valid_json = '{"title": "테스트 제목", "body": "SKMS의 인간중심 경영 원칙에 대한 요약입니다.", "key_points": ["포인트1"], "citations": ["2020-14차|VWBE|definition|001"]}'

    mock_message_bad = MagicMock()
    mock_message_bad.content = [MagicMock(text=bad_answer)]
    mock_message_good = MagicMock()
    mock_message_good.content = [MagicMock(text=valid_json)]

    client = MagicMock()
    client.messages.create.side_effect = [mock_message_bad, mock_message_good]

    service = GenerationService(client)
    result = service.generate("질의", "컨텍스트", "content_generation", "summary")
    assert result.validation_passed is True
    assert result.retried is True


def test_service_generate_content_validation_fail_all():
    """content_generation 재시도 후에도 검증 실패."""
    bad_answer = "not valid json"
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=bad_answer)]
    client = MagicMock()
    client.messages.create.return_value = mock_message

    service = GenerationService(client)
    result = service.generate("질의", "컨텍스트", "content_generation", "summary")
    assert result.validation_passed is False
    assert result.retried is True
    assert len(result.validation_errors) > 0


def test_service_call_llm_api_error():
    """LLM API 호출 실패 시 RuntimeError를 발생시킨다."""
    client = MagicMock()
    client.messages.create.side_effect = Exception("API connection error")
    service = GenerationService(client)
    with pytest.raises(RuntimeError, match="LLM API 호출 실패"):
        service.generate("질의", "컨텍스트", "open_ended")


# ---------------------------------------------------------------------------
# _estimate_tokens 테스트
# ---------------------------------------------------------------------------


def test_estimate_tokens_korean():
    """한국어 토큰 추정."""
    text = "한국어 텍스트"  # 6 korean chars
    tokens = _estimate_tokens(text)
    assert tokens > 0


def test_estimate_tokens_empty():
    """빈 문자열."""
    assert _estimate_tokens("") == 0


def test_estimate_tokens_mixed():
    """혼합 텍스트."""
    text = "Hello 세계"
    tokens = _estimate_tokens(text)
    assert tokens > 0
