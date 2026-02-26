"""LLMJudge 테스트.

PR-029: LLM-as-Judge 4축 자동 평가기 단위/통합 테스트.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.llm_judge import (  # noqa: E402
    JUDGE_SYSTEM_PROMPT,
    SCORE_MAX,
    SCORE_MIN,
    AxisResult,
    JudgeConfig,
    JudgeResult,
    JudgeScore,
    LLMClient,
    LLMJudge,
    build_judge_user_message,
    check_thresholds,
    format_judge_context,
    parse_judge_response,
)
from scripts.lib.quality_gate import DEFAULT_THRESHOLDS, EVAL_AXES  # noqa: E402
from scripts.lib.search_types import SearchHit  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hit(
    quote_id: str = "2020-14차|SUPEX|definition|001",
    text: str = "SUPEX는 Super Excellent 수준을 의미한다.",
    edition_id: str = "2020-14차",
    year: int = 2020,
    quote_type: str = "definition",
) -> SearchHit:
    """테스트용 SearchHit."""
    return SearchHit(
        quote_id=quote_id,
        text=text,
        score=0.9,
        edition_id=edition_id,
        year=year,
        revision_num=14,
        quote_type=quote_type,
        section_path=("SUPEX 추구",),
        source="hybrid",
        content_hash="abc123",
        quality_flags=(),
    )


def _make_good_response() -> str:
    """정상적인 평가 응답 JSON."""
    return json.dumps(
        {
            "relevance": 5,
            "faithfulness": 4,
            "quote_accuracy": 4,
            "temporal_correctness": 5,
            "reasoning": "답변이 질의에 잘 부합하며 컨텍스트에 충실합니다.",
        },
        ensure_ascii=False,
    )


def _make_low_response() -> str:
    """낮은 점수의 평가 응답 JSON."""
    return json.dumps(
        {
            "relevance": 2,
            "faithfulness": 1,
            "quote_accuracy": 2,
            "temporal_correctness": 1,
            "reasoning": "답변이 질의와 무관하며 환각이 많습니다.",
        },
        ensure_ascii=False,
    )


def _make_mock_client(response: str = "") -> MagicMock:
    """LLMClient mock 생성."""
    client = MagicMock(spec=LLMClient)
    client.create_message.return_value = response or _make_good_response()
    return client


# ---------------------------------------------------------------------------
# JudgeConfig 테스트
# ---------------------------------------------------------------------------


class TestJudgeConfig:
    """JudgeConfig 테스트."""

    def test_defaults(self):
        """기본값 확인."""
        config = JudgeConfig()
        assert config.model == "claude-sonnet-4-20250514"
        assert config.max_tokens == 500
        assert config.context_max_chars == 200
        assert config.thresholds == DEFAULT_THRESHOLDS

    def test_custom_thresholds(self):
        """커스텀 임계값."""
        custom = {"relevance": 4.0, "faithfulness": 4.5}
        config = JudgeConfig(thresholds=custom)
        assert config.thresholds == custom

    def test_is_frozen(self):
        """불변이다."""
        config = JudgeConfig()
        with pytest.raises(AttributeError):
            config.model = "other"  # type: ignore[misc]

    def test_default_thresholds_independent(self):
        """기본 임계값은 독립적인 복사본이다."""
        config1 = JudgeConfig()
        config2 = JudgeConfig()
        assert config1.thresholds is not config2.thresholds
        assert config1.thresholds == config2.thresholds


# ---------------------------------------------------------------------------
# JudgeScore 테스트
# ---------------------------------------------------------------------------


class TestJudgeScore:
    """JudgeScore 테스트."""

    def test_is_frozen(self):
        """불변이다."""
        score = JudgeScore(
            relevance=5.0,
            faithfulness=4.0,
            quote_accuracy=4.0,
            temporal_correctness=5.0,
            reasoning="좋음",
        )
        with pytest.raises(AttributeError):
            score.relevance = 1.0  # type: ignore[misc]

    def test_to_dict(self):
        """to_dict 변환."""
        score = JudgeScore(
            relevance=5.0,
            faithfulness=4.0,
            quote_accuracy=3.0,
            temporal_correctness=2.0,
            reasoning="테스트",
        )
        d = score.to_dict()
        assert d == {
            "relevance": 5.0,
            "faithfulness": 4.0,
            "quote_accuracy": 3.0,
            "temporal_correctness": 2.0,
        }

    def test_mean_score(self):
        """평균 점수 계산."""
        score = JudgeScore(
            relevance=4.0,
            faithfulness=4.0,
            quote_accuracy=4.0,
            temporal_correctness=4.0,
            reasoning="균일",
        )
        assert score.mean_score == 4.0

    def test_mean_score_mixed(self):
        """혼합 점수의 평균."""
        score = JudgeScore(
            relevance=5.0,
            faithfulness=3.0,
            quote_accuracy=4.0,
            temporal_correctness=2.0,
            reasoning="혼합",
        )
        assert score.mean_score == 3.5


# ---------------------------------------------------------------------------
# AxisResult 테스트
# ---------------------------------------------------------------------------


class TestAxisResult:
    """AxisResult 테스트."""

    def test_is_frozen(self):
        """불변이다."""
        result = AxisResult(axis="relevance", score=4.0, threshold=3.5, passed=True)
        with pytest.raises(AttributeError):
            result.passed = False  # type: ignore[misc]

    def test_fields(self):
        """필드 접근."""
        result = AxisResult(axis="faithfulness", score=3.0, threshold=4.0, passed=False)
        assert result.axis == "faithfulness"
        assert result.score == 3.0
        assert result.threshold == 4.0
        assert result.passed is False


# ---------------------------------------------------------------------------
# JudgeResult 테스트
# ---------------------------------------------------------------------------


class TestJudgeResult:
    """JudgeResult 테스트."""

    def test_is_frozen(self):
        """불변이다."""
        score = JudgeScore(5.0, 5.0, 5.0, 5.0, "완벽")
        result = JudgeResult(
            query_id="q1",
            query="SUPEX란?",
            query_type="definition",
            scores=score,
            axis_results=(),
            judge_passed=True,
        )
        with pytest.raises(AttributeError):
            result.judge_passed = False  # type: ignore[misc]

    def test_error_field(self):
        """에러 필드."""
        score = JudgeScore(0.0, 0.0, 0.0, 0.0, "에러")
        result = JudgeResult(
            query_id="q1",
            query="test",
            query_type="unknown",
            scores=score,
            axis_results=(),
            judge_passed=False,
            error="LLM 호출 실패",
        )
        assert result.error == "LLM 호출 실패"

    def test_to_eval_dict(self):
        """EvalResult 호환 dict 변환."""
        score = JudgeScore(5.0, 4.0, 4.0, 5.0, "좋음")
        result = JudgeResult(
            query_id="q1",
            query="SUPEX란?",
            query_type="definition",
            scores=score,
            axis_results=(),
            judge_passed=True,
        )
        d = result.to_eval_dict()
        assert d["id"] == "q1"
        assert d["judge_passed"] is True
        assert d["scores"]["relevance"] == 5.0


# ---------------------------------------------------------------------------
# format_judge_context 테스트
# ---------------------------------------------------------------------------


class TestFormatJudgeContext:
    """format_judge_context 함수 테스트."""

    def test_with_search_hits(self):
        """SearchHit 리스트."""
        hits = [_hit(), _hit(edition_id="1979-초판")]
        result = format_judge_context(hits)
        assert "[2020-14차]" in result
        assert "[1979-초판]" in result

    def test_with_dict_hits(self):
        """legacy dict 리스트."""
        hits = [
            {
                "text": "SUPEX 정의",
                "metadata": {"edition_id": "2020-14차"},
            }
        ]
        result = format_judge_context(hits)
        assert "[2020-14차]" in result
        assert "SUPEX 정의" in result

    def test_truncation(self):
        """텍스트 잘림."""
        hits = [_hit(text="A" * 300)]
        result = format_judge_context(hits, max_chars=50)
        assert "..." in result
        # 50자 + "..." 포함
        assert "A" * 50 in result

    def test_empty_hits(self):
        """빈 검색 결과."""
        result = format_judge_context([])
        assert result == "(검색 결과 없음)"

    def test_dict_without_metadata(self):
        """metadata 없는 dict."""
        hits = [{"text": "테스트", "edition_id": "2016-13차"}]
        result = format_judge_context(hits)
        assert "[2016-13차]" in result

    def test_no_truncation_short_text(self):
        """짧은 텍스트는 잘림 없음."""
        hits = [_hit(text="짧은 텍스트")]
        result = format_judge_context(hits)
        assert "..." not in result


# ---------------------------------------------------------------------------
# build_judge_user_message 테스트
# ---------------------------------------------------------------------------


class TestBuildJudgeUserMessage:
    """build_judge_user_message 함수 테스트."""

    def test_basic(self):
        """기본 메시지 구성."""
        msg = build_judge_user_message("질의", "답변", "컨텍스트")
        assert "## 질의\n질의" in msg
        assert "## 시스템 답변\n답변" in msg
        assert "## 검색된 컨텍스트 (요약)\n컨텍스트" in msg


# ---------------------------------------------------------------------------
# parse_judge_response 테스트
# ---------------------------------------------------------------------------


class TestParseJudgeResponse:
    """parse_judge_response 함수 테스트."""

    def test_plain_json(self):
        """일반 JSON."""
        text = _make_good_response()
        score = parse_judge_response(text)
        assert score.relevance == 5.0
        assert score.faithfulness == 4.0
        assert "잘 부합" in score.reasoning

    def test_json_code_block(self):
        """```json 블록."""
        text = '```json\n{"relevance":3,"faithfulness":3,"quote_accuracy":3,"temporal_correctness":3,"reasoning":"보통"}\n```'
        score = parse_judge_response(text)
        assert score.relevance == 3.0
        assert score.reasoning == "보통"

    def test_plain_code_block(self):
        """``` 블록 (json 마커 없음)."""
        text = '```\n{"relevance":4,"faithfulness":4,"quote_accuracy":4,"temporal_correctness":4,"reasoning":"양호"}\n```'
        score = parse_judge_response(text)
        assert score.relevance == 4.0

    def test_clamping_high(self):
        """범위 초과 점수 클램핑 (> 5)."""
        text = json.dumps(
            {
                "relevance": 10,
                "faithfulness": 5,
                "quote_accuracy": 5,
                "temporal_correctness": 5,
                "reasoning": "초과",
            }
        )
        score = parse_judge_response(text)
        assert score.relevance == SCORE_MAX  # clamped to 5

    def test_clamping_low(self):
        """범위 미만 점수 클램핑 (< 1)."""
        text = json.dumps(
            {
                "relevance": -1,
                "faithfulness": 0,
                "quote_accuracy": 1,
                "temporal_correctness": 1,
                "reasoning": "미달",
            }
        )
        score = parse_judge_response(text)
        assert score.relevance == 0.0  # -1 → 0.0 (미응답)
        assert score.faithfulness == 0.0  # 0 → 0.0 (미응답)

    def test_missing_fields(self):
        """누락 필드는 0.0."""
        text = json.dumps({"relevance": 5, "reasoning": "누락"})
        score = parse_judge_response(text)
        assert score.relevance == 5.0
        assert score.faithfulness == 0.0
        assert score.quote_accuracy == 0.0
        assert score.temporal_correctness == 0.0

    def test_invalid_json_raises(self):
        """잘못된 JSON은 ValueError."""
        with pytest.raises(ValueError, match="JSON 파싱 실패"):
            parse_judge_response("이것은 JSON이 아닙니다")

    def test_non_numeric_score(self):
        """비숫자 점수는 0.0."""
        text = json.dumps(
            {
                "relevance": "높음",
                "faithfulness": 4,
                "quote_accuracy": None,
                "temporal_correctness": 4,
                "reasoning": "비숫자",
            }
        )
        score = parse_judge_response(text)
        assert score.relevance == 0.0
        assert score.quote_accuracy == 0.0


# ---------------------------------------------------------------------------
# check_thresholds 테스트
# ---------------------------------------------------------------------------


class TestCheckThresholds:
    """check_thresholds 함수 테스트."""

    def test_all_pass(self):
        """모든 축 통과."""
        score = JudgeScore(5.0, 5.0, 5.0, 5.0, "완벽")
        passed, axis_results = check_thresholds(score)
        assert passed is True
        assert all(ar.passed for ar in axis_results)

    def test_all_fail(self):
        """모든 축 실패."""
        score = JudgeScore(1.0, 1.0, 1.0, 1.0, "불량")
        passed, axis_results = check_thresholds(score)
        assert passed is False
        assert all(not ar.passed for ar in axis_results)

    def test_partial_pass(self):
        """일부 축만 통과."""
        score = JudgeScore(5.0, 2.0, 5.0, 5.0, "부분")
        passed, axis_results = check_thresholds(score)
        assert passed is False
        # faithfulness만 실패
        faith = next(ar for ar in axis_results if ar.axis == "faithfulness")
        assert faith.passed is False
        assert faith.score == 2.0

    def test_boundary_exact_threshold(self):
        """임계값 정확 일치 → 통과."""
        score = JudgeScore(3.5, 4.0, 3.5, 3.5, "경계")
        passed, _ = check_thresholds(score)
        assert passed is True

    def test_boundary_below_threshold(self):
        """임계값 바로 아래 → 실패."""
        score = JudgeScore(3.4, 4.0, 3.5, 3.5, "미달")
        passed, axis_results = check_thresholds(score)
        assert passed is False
        rel = next(ar for ar in axis_results if ar.axis == "relevance")
        assert rel.passed is False

    def test_custom_thresholds(self):
        """커스텀 임계값."""
        score = JudgeScore(3.0, 3.0, 3.0, 3.0, "균일")
        custom = {axis: 3.0 for axis in EVAL_AXES}
        passed, _ = check_thresholds(score, custom)
        assert passed is True

    def test_axes_order(self):
        """결과 축 순서가 EVAL_AXES와 일치."""
        score = JudgeScore(5.0, 5.0, 5.0, 5.0, "확인")
        _, axis_results = check_thresholds(score)
        assert tuple(ar.axis for ar in axis_results) == EVAL_AXES


# ---------------------------------------------------------------------------
# LLMJudge 테스트
# ---------------------------------------------------------------------------


class TestLLMJudge:
    """LLMJudge 서비스 테스트."""

    def test_evaluate_success(self):
        """정상 평가."""
        client = _make_mock_client()
        judge = LLMJudge(llm_client=client)

        result = judge.evaluate(
            query="SUPEX란?",
            answer="SUPEX는 Super Excellent 수준을 추구하는 것입니다.",
            hits=[_hit()],
            query_id="q1",
            query_type="definition",
        )

        assert result.judge_passed is True
        assert result.scores.relevance == 5.0
        assert result.error is None
        client.create_message.assert_called_once()

    def test_evaluate_low_scores(self):
        """낮은 점수 → 실패."""
        client = _make_mock_client(_make_low_response())
        judge = LLMJudge(llm_client=client)

        result = judge.evaluate(
            query="SUPEX란?",
            answer="잘 모르겠습니다.",
            hits=[_hit()],
            query_id="q2",
        )

        assert result.judge_passed is False
        assert result.scores.faithfulness == 1.0

    def test_evaluate_no_client(self):
        """클라이언트 없음 → 에러 결과."""
        judge = LLMJudge()

        result = judge.evaluate(
            query="SUPEX란?",
            answer="답변",
            hits=[_hit()],
            query_id="q3",
        )

        assert result.judge_passed is False
        assert result.error is not None
        assert "클라이언트" in result.error

    def test_evaluate_llm_exception(self):
        """LLM 호출 예외 → 에러 결과."""
        client = MagicMock(spec=LLMClient)
        client.create_message.side_effect = RuntimeError("API 오류")
        judge = LLMJudge(llm_client=client)

        result = judge.evaluate(
            query="SUPEX란?",
            answer="답변",
            hits=[_hit()],
            query_id="q4",
        )

        assert result.judge_passed is False
        assert "API 오류" in result.error

    def test_evaluate_parse_error(self):
        """파싱 실패 → 에러 결과."""
        client = _make_mock_client("이것은 JSON이 아닙니다 !!!")
        judge = LLMJudge(llm_client=client)

        result = judge.evaluate(
            query="SUPEX란?",
            answer="답변",
            hits=[_hit()],
            query_id="q5",
        )

        assert result.judge_passed is False
        assert result.error is not None
        assert "JSON 파싱 실패" in result.error

    def test_evaluate_custom_config(self):
        """커스텀 설정."""
        config = JudgeConfig(
            model="custom-model",
            max_tokens=1000,
            thresholds={
                "relevance": 1.0,
                "faithfulness": 1.0,
                "quote_accuracy": 1.0,
                "temporal_correctness": 1.0,
            },
            context_max_chars=100,
        )
        client = _make_mock_client()
        judge = LLMJudge(config=config, llm_client=client)

        assert judge.config.model == "custom-model"
        assert judge.config.max_tokens == 1000

        result = judge.evaluate(
            query="test",
            answer="test",
            hits=[_hit()],
        )
        assert result.judge_passed is True

    def test_evaluate_with_dict_hits(self):
        """dict 형식 hits."""
        client = _make_mock_client()
        judge = LLMJudge(llm_client=client)

        dict_hits = [
            {
                "text": "SUPEX 정의",
                "metadata": {"edition_id": "2020-14차"},
            }
        ]
        result = judge.evaluate(
            query="SUPEX란?",
            answer="SUPEX 답변",
            hits=dict_hits,
        )
        assert result.judge_passed is True

    def test_evaluate_empty_hits(self):
        """빈 검색 결과."""
        client = _make_mock_client()
        judge = LLMJudge(llm_client=client)

        result = judge.evaluate(
            query="SUPEX란?",
            answer="답변",
            hits=[],
        )
        # LLM이 평가하므로 결과는 LLM 응답에 의존
        assert result.error is None


# ---------------------------------------------------------------------------
# evaluate_batch 테스트
# ---------------------------------------------------------------------------


class TestEvaluateBatch:
    """evaluate_batch 테스트."""

    def test_basic_batch(self):
        """기본 배치 평가."""
        client = _make_mock_client()
        judge = LLMJudge(llm_client=client)

        items = [
            {
                "query": "SUPEX란?",
                "answer": "SUPEX 답변",
                "hits": [_hit()],
                "query_id": "q1",
                "query_type": "definition",
            },
            {
                "query": "VWBE란?",
                "answer": "VWBE 답변",
                "hits": [_hit(text="VWBE 문화")],
                "query_id": "q2",
                "query_type": "definition",
            },
        ]

        results = judge.evaluate_batch(items)
        assert len(results) == 2
        assert results[0].query_id == "q1"
        assert results[1].query_id == "q2"
        assert client.create_message.call_count == 2

    def test_empty_batch(self):
        """빈 배치."""
        judge = LLMJudge(llm_client=_make_mock_client())
        results = judge.evaluate_batch([])
        assert results == []

    def test_batch_with_minimal_items(self):
        """최소 필드만 있는 항목."""
        client = _make_mock_client()
        judge = LLMJudge(llm_client=client)

        items = [{"query": "test", "answer": "test", "hits": []}]
        results = judge.evaluate_batch(items)
        assert len(results) == 1
        assert results[0].query_id == ""
        assert results[0].query_type == "unknown"


# ---------------------------------------------------------------------------
# JUDGE_SYSTEM_PROMPT 테스트
# ---------------------------------------------------------------------------


class TestJudgeSystemPrompt:
    """JUDGE_SYSTEM_PROMPT 상수 테스트."""

    def test_contains_all_axes(self):
        """모든 평가 축이 포함되어 있다."""
        for axis in EVAL_AXES:
            assert axis in JUDGE_SYSTEM_PROMPT

    def test_contains_scoring_range(self):
        """점수 범위 (1-5)가 포함되어 있다."""
        assert "(1-5)" in JUDGE_SYSTEM_PROMPT

    def test_contains_json_format(self):
        """JSON 출력 형식이 포함되어 있다."""
        assert "```json" in JUDGE_SYSTEM_PROMPT
        assert '"reasoning"' in JUDGE_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# 통합 테스트
# ---------------------------------------------------------------------------


class TestLLMJudgeIntegration:
    """통합 테스트."""

    def test_full_pipeline(self):
        """전체 파이프라인: 컨텍스트 포맷 → 메시지 구성 → 파싱 → 임계값 검사."""
        # 1. 컨텍스트 포맷
        hits = [
            _hit("2020-14차|SUPEX|def|001", "SUPEX 정의", "2020-14차"),
            _hit("1979-초판|기본이념|nar|001", "기본 이념", "1979-초판", 1979),
        ]
        context = format_judge_context(hits)
        assert "[2020-14차]" in context
        assert "[1979-초판]" in context

        # 2. 메시지 구성
        msg = build_judge_user_message("SUPEX란?", "SUPEX 답변", context)
        assert "SUPEX란?" in msg

        # 3. 파싱
        response = _make_good_response()
        score = parse_judge_response(response)
        assert score.relevance == 5.0

        # 4. 임계값 검사
        passed, axis_results = check_thresholds(score)
        assert passed is True
        assert len(axis_results) == 4

    def test_full_judge_service(self):
        """LLMJudge 서비스 전체 흐름."""
        client = _make_mock_client()
        config = JudgeConfig(context_max_chars=100)
        judge = LLMJudge(config=config, llm_client=client)

        result = judge.evaluate(
            query="SUPEX란 무엇인가?",
            answer="SUPEX는 Super Excellent 수준을 추구하는 것입니다.",
            hits=[
                _hit(),
                _hit("1979-초판|기본|nar|001", "기본 이념", "1979-초판", 1979),
            ],
            query_id="eval-001",
            query_type="definition",
        )

        assert result.query_id == "eval-001"
        assert result.judge_passed is True
        assert result.scores.mean_score > 0
        assert len(result.axis_results) == 4

        # EvalResult 호환 변환
        eval_dict = result.to_eval_dict()
        assert eval_dict["id"] == "eval-001"
        assert eval_dict["judge_passed"] is True

    def test_error_recovery(self):
        """에러 발생 시 안전한 결과 반환."""
        client = MagicMock(spec=LLMClient)
        client.create_message.side_effect = ConnectionError("네트워크 오류")
        judge = LLMJudge(llm_client=client)

        result = judge.evaluate(
            query="test",
            answer="test",
            hits=[_hit()],
            query_id="err-001",
        )

        assert result.judge_passed is False
        assert result.error is not None
        assert result.scores.relevance == 0.0
        assert result.scores.faithfulness == 0.0
        assert all(not ar.passed for ar in result.axis_results)

    def test_batch_mixed_results(self):
        """배치 평가 — 성공/실패 혼합."""
        good_response = _make_good_response()
        low_response = _make_low_response()

        client = MagicMock(spec=LLMClient)
        client.create_message.side_effect = [good_response, low_response]

        judge = LLMJudge(llm_client=client)
        results = judge.evaluate_batch(
            [
                {"query": "Q1", "answer": "A1", "hits": [], "query_id": "q1"},
                {"query": "Q2", "answer": "A2", "hits": [], "query_id": "q2"},
            ]
        )

        assert results[0].judge_passed is True
        assert results[1].judge_passed is False
