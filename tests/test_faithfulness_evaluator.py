"""Tests for scripts.lib.faithfulness_evaluator."""
from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from scripts.lib.faithfulness_evaluator import (
    Claim,
    FaithfulnessEvaluator,
    FaithfulnessResult,
    evaluate_without_llm,
    _build_result,
    _empty_result,
    _longest_common_substring_length,
    _split_sentences,
    _strip_markdown_fences,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CONTEXT_1 = {
    "quote_id": "1979-초판|경영기본이념|sect|001",
    "text": "SKMS는 인간위주의 경영을 기본 이념으로 한다.",
}

CONTEXT_2 = {
    "quote_id": "2020-14차|SUPEX추구|sect|002",
    "text": "SUPEX 추구는 인간의 능력으로 도달할 수 있는 최고의 수준을 의미한다.",
}


@pytest.fixture()
def contexts() -> list[dict[str, str]]:
    return [CONTEXT_1, CONTEXT_2]


# ---------------------------------------------------------------------------
# Frozen dataclass tests
# ---------------------------------------------------------------------------


class TestDataclassImmutability:
    def test_claim_is_frozen(self) -> None:
        claim = Claim(text="test", is_grounded=True)
        with pytest.raises(AttributeError):
            claim.text = "changed"  # type: ignore[misc]

    def test_faithfulness_result_is_frozen(self) -> None:
        result = FaithfulnessResult(
            is_faithful=True,
            claims=(),
            grounded_count=0,
            hallucinated_count=0,
            grounded_ratio=1.0,
        )
        with pytest.raises(AttributeError):
            result.is_faithful = False  # type: ignore[misc]

    def test_claim_default_supporting_quote_id(self) -> None:
        claim = Claim(text="hello", is_grounded=False)
        assert claim.supporting_quote_id is None


# ---------------------------------------------------------------------------
# evaluate_without_llm tests
# ---------------------------------------------------------------------------


class TestEvaluateWithoutLLM:
    def test_empty_answer_returns_faithful(self) -> None:
        result = evaluate_without_llm("", [CONTEXT_1])
        assert result.is_faithful is True
        assert result.claims == ()
        assert result.grounded_ratio == 1.0

    def test_whitespace_answer_returns_faithful(self) -> None:
        result = evaluate_without_llm("   ", [CONTEXT_1])
        assert result.is_faithful is True

    def test_empty_contexts_all_hallucinated(self) -> None:
        result = evaluate_without_llm("SKMS는 인간위주의 경영이다.", [])
        assert result.is_faithful is False
        assert result.hallucinated_count == 1

    def test_grounded_answer(self, contexts: list[dict[str, str]]) -> None:
        # Answer reuses text from context 1
        answer = "SKMS는 인간위주의 경영을 기본 이념으로 한다."
        result = evaluate_without_llm(answer, contexts)
        assert result.is_faithful is True
        assert result.grounded_count == 1
        assert result.hallucinated_count == 0
        assert result.grounded_ratio == 1.0

    def test_hallucinated_answer(self, contexts: list[dict[str, str]]) -> None:
        # Completely fabricated text with no overlap
        answer = "최태원 회장은 2023년 7월 15일에 새로운 비전을 발표했다."
        result = evaluate_without_llm(answer, contexts)
        assert result.is_faithful is False
        assert result.hallucinated_count >= 1

    def test_mixed_grounded_and_hallucinated(
        self, contexts: list[dict[str, str]]
    ) -> None:
        answer = "SKMS는 인간위주의 경영을 기본 이념으로 한다. " "삼성전자는 세계 최대의 반도체 기업이다."
        result = evaluate_without_llm(answer, contexts)
        assert result.grounded_count >= 1
        assert result.hallucinated_count >= 1
        assert result.is_faithful is False
        assert 0.0 < result.grounded_ratio < 1.0

    def test_supporting_quote_id_set(self) -> None:
        answer = "인간위주의 경영을 기본 이념으로 한다."
        result = evaluate_without_llm(answer, [CONTEXT_1])
        grounded_claims = [c for c in result.claims if c.is_grounded]
        assert len(grounded_claims) >= 1
        assert grounded_claims[0].supporting_quote_id == CONTEXT_1["quote_id"]

    def test_min_overlap_chars_parameter(self) -> None:
        ctx = {"quote_id": "q1", "text": "ABCDEFGH의 설명입니다."}
        answer = "ABCDEFGH는 중요하다."
        # With default min_overlap_chars=8, should be grounded
        result = evaluate_without_llm(answer, [ctx], min_overlap_chars=8)
        assert result.grounded_count >= 1

        # With very high threshold, nothing grounds
        result_strict = evaluate_without_llm(answer, [ctx], min_overlap_chars=100)
        assert result_strict.grounded_count == 0

    def test_multiple_sentences(self, contexts: list[dict[str, str]]) -> None:
        answer = (
            "SKMS는 인간위주의 경영을 기본 이념으로 한다. " "SUPEX 추구는 인간의 능력으로 도달할 수 있는 최고의 수준을 의미한다."
        )
        result = evaluate_without_llm(answer, contexts)
        assert result.is_faithful is True
        assert result.grounded_count == 2
        assert result.grounded_ratio == 1.0

    def test_context_with_empty_text(self) -> None:
        ctx = {"quote_id": "q1", "text": ""}
        answer = "테스트 문장입니다."
        result = evaluate_without_llm(answer, [ctx])
        assert result.hallucinated_count >= 1


# ---------------------------------------------------------------------------
# LLM-based evaluate tests (mocked)
# ---------------------------------------------------------------------------


@dataclass
class _FakeContentBlock:
    text: str


@dataclass
class _FakeMessage:
    content: list[_FakeContentBlock]


def _make_mock_client(responses: list[str]) -> MagicMock:
    """Create a mock client that returns predefined text responses."""
    client = MagicMock()
    side_effects = [
        _FakeMessage(content=[_FakeContentBlock(text=r)]) for r in responses
    ]
    client.messages.create.side_effect = side_effects
    return client


class TestEvaluateWithLLM:
    def test_all_grounded(self, contexts: list[dict[str, str]]) -> None:
        # Response 1: extract claims → 2 claims
        claims_json = json.dumps(["SKMS는 인간위주 경영이다.", "SUPEX는 최고 수준이다."])
        # Response 2 & 3: judge each claim as grounded
        judge_1 = json.dumps(
            {"is_grounded": True, "supporting_quote_id": CONTEXT_1["quote_id"]}
        )
        judge_2 = json.dumps(
            {"is_grounded": True, "supporting_quote_id": CONTEXT_2["quote_id"]}
        )
        client = _make_mock_client([claims_json, judge_1, judge_2])

        evaluator = FaithfulnessEvaluator(client)
        result = evaluator.evaluate("테스트 답변", contexts)

        assert result.is_faithful is True
        assert result.grounded_count == 2
        assert result.hallucinated_count == 0
        assert result.grounded_ratio == 1.0
        assert len(result.claims) == 2
        assert result.claims[0].supporting_quote_id == CONTEXT_1["quote_id"]

    def test_one_hallucinated(self, contexts: list[dict[str, str]]) -> None:
        claims_json = json.dumps(["주장A", "주장B"])
        judge_1 = json.dumps(
            {"is_grounded": True, "supporting_quote_id": CONTEXT_1["quote_id"]}
        )
        judge_2 = json.dumps({"is_grounded": False, "supporting_quote_id": None})
        client = _make_mock_client([claims_json, judge_1, judge_2])

        evaluator = FaithfulnessEvaluator(client)
        result = evaluator.evaluate("답변", contexts)

        assert result.is_faithful is False
        assert result.grounded_count == 1
        assert result.hallucinated_count == 1
        assert result.grounded_ratio == 0.5

    def test_empty_answer(self, contexts: list[dict[str, str]]) -> None:
        client = _make_mock_client([])
        evaluator = FaithfulnessEvaluator(client)
        result = evaluator.evaluate("", contexts)
        assert result.is_faithful is True
        assert result.claims == ()
        # No LLM calls for empty answer
        client.messages.create.assert_not_called()

    def test_extraction_failure_returns_empty(
        self, contexts: list[dict[str, str]]
    ) -> None:
        client = MagicMock()
        client.messages.create.side_effect = RuntimeError("API error")
        evaluator = FaithfulnessEvaluator(client)
        result = evaluator.evaluate("답변 텍스트", contexts)
        assert result.is_faithful is True
        assert result.claims == ()

    def test_judge_failure_marks_hallucinated(
        self, contexts: list[dict[str, str]]
    ) -> None:
        claims_json = json.dumps(["주장A"])
        # First call succeeds (extraction), second fails (judgment)
        client = MagicMock()
        call_count = 0

        def side_effect(**kwargs: object) -> _FakeMessage:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _FakeMessage(content=[_FakeContentBlock(text=claims_json)])
            raise RuntimeError("API error")

        client.messages.create.side_effect = side_effect
        evaluator = FaithfulnessEvaluator(client)
        result = evaluator.evaluate("답변", contexts)

        assert result.is_faithful is False
        assert result.hallucinated_count == 1
        assert result.claims[0].is_grounded is False

    def test_markdown_fenced_response(self, contexts: list[dict[str, str]]) -> None:
        claims_json = '```json\n["주장A"]\n```'
        judge_resp = '```json\n{"is_grounded": true, "supporting_quote_id": "q1"}\n```'
        client = _make_mock_client([claims_json, judge_resp])

        evaluator = FaithfulnessEvaluator(client)
        result = evaluator.evaluate("답변", contexts)
        assert result.grounded_count == 1

    def test_custom_model_and_max_tokens(self) -> None:
        client = _make_mock_client(
            [
                json.dumps(["A"]),
                json.dumps({"is_grounded": True, "supporting_quote_id": None}),
            ]
        )
        evaluator = FaithfulnessEvaluator(
            client, model="claude-haiku-3", max_tokens=512
        )
        evaluator.evaluate("text", [{"quote_id": "q1", "text": "ctx"}])

        call_kwargs = client.messages.create.call_args_list[0].kwargs
        assert call_kwargs["model"] == "claude-haiku-3"
        assert call_kwargs["max_tokens"] == 512

    def test_no_claims_extracted(self, contexts: list[dict[str, str]]) -> None:
        # LLM returns empty list
        client = _make_mock_client([json.dumps([])])
        evaluator = FaithfulnessEvaluator(client)
        result = evaluator.evaluate("답변", contexts)
        assert result.is_faithful is True
        assert result.claims == ()


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_split_sentences_korean(self) -> None:
        text = "첫 번째 문장이다. 두 번째 문장이다. 세 번째!"
        parts = _split_sentences(text)
        assert len(parts) == 3

    def test_split_sentences_empty(self) -> None:
        assert _split_sentences("") == []
        assert _split_sentences("   ") == []

    def test_split_sentences_single(self) -> None:
        parts = _split_sentences("단일 문장")
        assert len(parts) == 1
        assert parts[0] == "단일 문장"

    def test_longest_common_substring_exact(self) -> None:
        assert _longest_common_substring_length("abcdef", "abcdef") == 6

    def test_longest_common_substring_partial(self) -> None:
        assert _longest_common_substring_length("xxabcxx", "yyabcyy") == 3

    def test_longest_common_substring_none(self) -> None:
        assert _longest_common_substring_length("abc", "xyz") == 0

    def test_longest_common_substring_empty(self) -> None:
        assert _longest_common_substring_length("", "abc") == 0
        assert _longest_common_substring_length("abc", "") == 0

    def test_longest_common_substring_korean(self) -> None:
        a = "인간위주의 경영을 기본 이념으로"
        b = "SKMS는 인간위주의 경영을 기본 이념으로 한다."
        assert _longest_common_substring_length(a, b) >= len("인간위주의 경영을 기본 이념으로")

    def test_strip_markdown_fences_json(self) -> None:
        raw = '```json\n["a","b"]\n```'
        assert _strip_markdown_fences(raw) == '["a","b"]'

    def test_strip_markdown_fences_plain(self) -> None:
        raw = '["a"]'
        assert _strip_markdown_fences(raw) == '["a"]'

    def test_strip_markdown_fences_no_language(self) -> None:
        raw = '```\n{"key": "val"}\n```'
        assert _strip_markdown_fences(raw) == '{"key": "val"}'

    def test_empty_result(self) -> None:
        result = _empty_result()
        assert result.is_faithful is True
        assert result.grounded_ratio == 1.0
        assert result.claims == ()

    def test_build_result_empty(self) -> None:
        result = _build_result(())
        assert result.is_faithful is True

    def test_build_result_all_grounded(self) -> None:
        claims = (
            Claim(text="a", is_grounded=True, supporting_quote_id="q1"),
            Claim(text="b", is_grounded=True, supporting_quote_id="q2"),
        )
        result = _build_result(claims)
        assert result.is_faithful is True
        assert result.grounded_count == 2
        assert result.hallucinated_count == 0
        assert result.grounded_ratio == 1.0

    def test_build_result_mixed(self) -> None:
        claims = (
            Claim(text="a", is_grounded=True),
            Claim(text="b", is_grounded=False),
            Claim(text="c", is_grounded=False),
        )
        result = _build_result(claims)
        assert result.is_faithful is False
        assert result.grounded_count == 1
        assert result.hallucinated_count == 2
        assert abs(result.grounded_ratio - 1 / 3) < 0.01
