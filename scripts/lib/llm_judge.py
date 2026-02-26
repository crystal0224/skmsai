"""LLMJudge — LLM-as-Judge 4축 자동 평가기.

PR-029: LLM을 활용하여 RAG 답변을 4개 축으로 자동 평가한다.

평가 축:
- relevance (1-5): 답변이 질의에 얼마나 관련 있는가
- faithfulness (1-5): 답변이 컨텍스트에 얼마나 충실한가
- quote_accuracy (1-5): 인용이 정확하고 형식을 갖추었는가
- temporal_correctness (1-5): 개정판 맥락이 올바르게 처리되었는가
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from scripts.lib.quality_gate import DEFAULT_THRESHOLDS, EVAL_AXES
from scripts.lib.search_types import SearchHit

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

SCORE_MIN = 1
SCORE_MAX = 5

DEFAULT_JUDGE_MODEL = "claude-sonnet-4-20250514"
DEFAULT_MAX_TOKENS = 500
DEFAULT_CONTEXT_MAX_CHARS = 200

JUDGE_SYSTEM_PROMPT = """\
당신은 SKMS(SK경영관리체계) RAG 시스템의 품질 평가자입니다.
사용자의 질의, 시스템 답변, 검색된 컨텍스트를 분석하여 4가지 축으로 평가하세요.

## 평가 축

1. **relevance** (1-5): 답변이 질의에 얼마나 관련 있는가?
   - 5: 질의의 모든 측면에 완벽하게 답변
   - 3: 부분적으로 관련 있으나 핵심 누락
   - 1: 완전히 무관한 답변

2. **faithfulness** (1-5): 답변이 제공된 컨텍스트에 얼마나 충실한가?
   - 5: 모든 내용이 컨텍스트에 근거
   - 3: 일부 내용이 컨텍스트에 없는 추측
   - 1: 대부분 환각(hallucination)

3. **quote_accuracy** (1-5): 인용이 정확하고 형식을 갖추었는가?
   - 5: 모든 인용이 정확하고 [출처: N차 개정판, 섹션] 형식 준수
   - 3: 인용이 있으나 형식 불완전
   - 1: 인용 없음 또는 부정확

4. **temporal_correctness** (1-5): 개정판 맥락이 올바르게 처리되었는가?
   - 5: 개정판 간 구분이 명확하고 시간축 충돌 적절히 안내
   - 3: 개정판 정보 있으나 일부 혼동
   - 1: 개정판 구분 없이 혼합

## 출력 형식

반드시 아래 JSON으로만 응답하세요:

```json
{
  "relevance": <1-5>,
  "faithfulness": <1-5>,
  "quote_accuracy": <1-5>,
  "temporal_correctness": <1-5>,
  "reasoning": "평가 근거를 2-3문장으로"
}
```
"""


# ---------------------------------------------------------------------------
# LLMClient Protocol — DI를 위한 프로토콜
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMClient(Protocol):
    """LLM API 호출 프로토콜.

    테스트 시 mock으로 교체 가능.
    """

    def create_message(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict[str, str]],
    ) -> str:
        """LLM 메시지를 생성하고 텍스트 응답을 반환한다."""
        ...


# ---------------------------------------------------------------------------
# JudgeConfig — 평가 설정 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JudgeConfig:
    """LLM-as-Judge 설정.

    Attributes:
        model: LLM 모델 이름
        max_tokens: 최대 토큰 수
        thresholds: 축별 통과 임계값
        context_max_chars: 컨텍스트 항목당 최대 문자 수
        system_prompt: 평가 시스템 프롬프트
    """

    model: str = DEFAULT_JUDGE_MODEL
    max_tokens: int = DEFAULT_MAX_TOKENS
    thresholds: dict[str, float] = None  # type: ignore[assignment]
    context_max_chars: int = DEFAULT_CONTEXT_MAX_CHARS
    system_prompt: str = JUDGE_SYSTEM_PROMPT

    def __post_init__(self) -> None:
        if self.thresholds is None:
            object.__setattr__(self, "thresholds", dict(DEFAULT_THRESHOLDS))


# ---------------------------------------------------------------------------
# JudgeScore — 4축 점수 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JudgeScore:
    """4축 평가 점수.

    Attributes:
        relevance: 관련성 점수 (1-5)
        faithfulness: 충실성 점수 (1-5)
        quote_accuracy: 인용 정확도 점수 (1-5)
        temporal_correctness: 시간축 정확도 점수 (1-5)
        reasoning: 평가 근거
    """

    relevance: float
    faithfulness: float
    quote_accuracy: float
    temporal_correctness: float
    reasoning: str

    def to_dict(self) -> dict[str, float]:
        """EVAL_AXES 축 점수를 dict로 반환한다."""
        return {
            "relevance": self.relevance,
            "faithfulness": self.faithfulness,
            "quote_accuracy": self.quote_accuracy,
            "temporal_correctness": self.temporal_correctness,
        }

    @property
    def mean_score(self) -> float:
        """4축 평균 점수."""
        values = [
            self.relevance,
            self.faithfulness,
            self.quote_accuracy,
            self.temporal_correctness,
        ]
        return sum(values) / len(values)


# ---------------------------------------------------------------------------
# AxisResult — 축별 통과 결과 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AxisResult:
    """단일 축의 평가 결과.

    Attributes:
        axis: 평가 축 이름
        score: 점수 (1-5)
        threshold: 임계값
        passed: 통과 여부
    """

    axis: str
    score: float
    threshold: float
    passed: bool


# ---------------------------------------------------------------------------
# JudgeResult — 평가 결과 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JudgeResult:
    """단일 평가의 전체 결과.

    Attributes:
        query_id: 질의 식별자
        query: 질의 텍스트
        query_type: 질의 유형
        scores: 4축 점수
        axis_results: 축별 통과 결과
        judge_passed: 전체 통과 여부 (모든 축 통과)
        error: 오류 메시지 (정상이면 None)
    """

    query_id: str
    query: str
    query_type: str
    scores: JudgeScore
    axis_results: tuple[AxisResult, ...]
    judge_passed: bool
    error: str | None = None

    def to_eval_dict(self) -> dict[str, Any]:
        """QualityGate용 EvalResult 호환 dict로 변환한다."""
        return {
            "id": self.query_id,
            "query": self.query,
            "query_type": self.query_type,
            "scores": self.scores.to_dict(),
            "judge_passed": self.judge_passed,
        }


# ---------------------------------------------------------------------------
# 컨텍스트 포맷팅
# ---------------------------------------------------------------------------


def format_judge_context(
    hits: list[SearchHit] | list[dict[str, Any]],
    max_chars: int = DEFAULT_CONTEXT_MAX_CHARS,
) -> str:
    """검색 결과를 평가용 컨텍스트 문자열로 포맷팅한다.

    SearchHit와 legacy dict 형식 모두 지원한다.

    Args:
        hits: 검색 결과 리스트
        max_chars: 항목당 최대 문자 수

    Returns:
        포맷팅된 컨텍스트 문자열
    """
    if not hits:
        return "(검색 결과 없음)"

    parts: list[str] = []
    for h in hits:
        if isinstance(h, SearchHit):
            edition_id = h.edition_id
            text = h.text
        else:
            meta = h.get("metadata", {})
            edition_id = meta.get("edition_id", h.get("edition_id", "?"))
            text = h.get("text", "")

        truncated = text[:max_chars] + "..." if len(text) > max_chars else text
        parts.append(f"- [{edition_id}] {truncated}")

    return "\n".join(parts)


def build_judge_user_message(
    query: str,
    answer: str,
    context_summary: str,
) -> str:
    """평가용 사용자 메시지를 구성한다.

    Args:
        query: 질의 텍스트
        answer: 시스템 답변
        context_summary: 컨텍스트 요약 문자열

    Returns:
        포맷팅된 사용자 메시지
    """
    return (
        f"## 질의\n{query}\n\n"
        f"## 시스템 답변\n{answer}\n\n"
        f"## 검색된 컨텍스트 (요약)\n{context_summary}"
    )


# ---------------------------------------------------------------------------
# JSON 파싱
# ---------------------------------------------------------------------------


def parse_judge_response(text: str) -> JudgeScore:
    """LLM 응답 텍스트를 JudgeScore로 파싱한다.

    JSON 코드 블록 마커(```json ... ```)를 자동으로 처리한다.

    Args:
        text: LLM 응답 텍스트

    Returns:
        JudgeScore

    Raises:
        ValueError: JSON 파싱 실패 시
    """
    cleaned = text.strip()

    # 코드 블록 추출
    if "```json" in cleaned:
        cleaned = cleaned.split("```json")[1].split("```")[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```")[1].split("```")[0].strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 파싱 실패: {cleaned[:200]}") from e

    return JudgeScore(
        relevance=_clamp_score(data.get("relevance", 0)),
        faithfulness=_clamp_score(data.get("faithfulness", 0)),
        quote_accuracy=_clamp_score(data.get("quote_accuracy", 0)),
        temporal_correctness=_clamp_score(data.get("temporal_correctness", 0)),
        reasoning=str(data.get("reasoning", "")),
    )


def _clamp_score(value: Any) -> float:
    """점수를 1-5 범위로 클램핑한다.

    0 또는 변환 불가 값은 0.0을 반환한다 (미응답/오류 표시).
    유효한 양수 값은 [1, 5] 범위로 클램핑한다.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if v <= 0:
        return 0.0
    return max(SCORE_MIN, min(SCORE_MAX, v))


# ---------------------------------------------------------------------------
# 임계값 검사
# ---------------------------------------------------------------------------


def check_thresholds(
    scores: JudgeScore,
    thresholds: dict[str, float] | None = None,
) -> tuple[bool, tuple[AxisResult, ...]]:
    """4축 점수를 임계값과 비교하여 통과 여부를 판정한다.

    Args:
        scores: 4축 점수
        thresholds: 축별 임계값 (None이면 DEFAULT_THRESHOLDS)

    Returns:
        (전체 통과 여부, 축별 결과 튜플)
    """
    thresholds = thresholds or DEFAULT_THRESHOLDS
    score_dict = scores.to_dict()

    results: list[AxisResult] = []
    all_passed = True

    for axis in EVAL_AXES:
        score = score_dict.get(axis, 0.0)
        threshold = thresholds.get(axis, 3.0)
        passed = score >= threshold

        if not passed:
            all_passed = False

        results.append(
            AxisResult(
                axis=axis,
                score=score,
                threshold=threshold,
                passed=passed,
            )
        )

    return all_passed, tuple(results)


# ---------------------------------------------------------------------------
# LLMJudge 서비스
# ---------------------------------------------------------------------------


class LLMJudge:
    """LLM-as-Judge 4축 자동 평가 서비스.

    LLM을 활용하여 RAG 시스템의 답변 품질을 4개 축으로 평가한다.

    Args:
        config: 평가 설정 (None이면 기본값)
        llm_client: LLM API 클라이언트 (None이면 evaluate 시 에러)
    """

    def __init__(
        self,
        config: JudgeConfig | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self._config = config or JudgeConfig()
        self._client = llm_client

    @property
    def config(self) -> JudgeConfig:
        """현재 설정을 반환한다."""
        return self._config

    def evaluate(
        self,
        query: str,
        answer: str,
        hits: list[SearchHit] | list[dict[str, Any]],
        *,
        query_id: str = "",
        query_type: str = "unknown",
    ) -> JudgeResult:
        """단일 답변을 4축으로 평가한다.

        Args:
            query: 질의 텍스트
            answer: 시스템 답변
            hits: 검색 결과 리스트
            query_id: 질의 식별자
            query_type: 질의 유형

        Returns:
            JudgeResult (불변)
        """
        if self._client is None:
            return _error_result(
                query_id=query_id,
                query=query,
                query_type=query_type,
                error="LLM 클라이언트가 설정되지 않았습니다",
                thresholds=self._config.thresholds,
            )

        # 컨텍스트 포맷팅
        context_summary = format_judge_context(
            hits, max_chars=self._config.context_max_chars
        )

        # 사용자 메시지 구성
        user_message = build_judge_user_message(query, answer, context_summary)

        # LLM 호출
        try:
            response_text = self._client.create_message(
                model=self._config.model,
                max_tokens=self._config.max_tokens,
                system=self._config.system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
        except Exception as e:
            logger.error("LLM 호출 실패: %s", e)
            return _error_result(
                query_id=query_id,
                query=query,
                query_type=query_type,
                error=f"LLM 호출 실패: {e}",
                thresholds=self._config.thresholds,
            )

        # 응답 파싱
        try:
            scores = parse_judge_response(response_text)
        except ValueError as e:
            logger.error("응답 파싱 실패: %s", e)
            return _error_result(
                query_id=query_id,
                query=query,
                query_type=query_type,
                error=str(e),
                thresholds=self._config.thresholds,
            )

        # 임계값 검사
        judge_passed, axis_results = check_thresholds(scores, self._config.thresholds)

        return JudgeResult(
            query_id=query_id,
            query=query,
            query_type=query_type,
            scores=scores,
            axis_results=axis_results,
            judge_passed=judge_passed,
        )

    def evaluate_batch(
        self,
        items: list[dict[str, Any]],
    ) -> list[JudgeResult]:
        """복수 답변을 일괄 평가한다.

        각 항목은 다음 키를 가져야 한다:
        - query (필수): 질의 텍스트
        - answer (필수): 시스템 답변
        - hits (필수): 검색 결과 리스트
        - query_id (선택): 질의 식별자
        - query_type (선택): 질의 유형

        Args:
            items: 평가 항목 리스트

        Returns:
            JudgeResult 리스트
        """
        results: list[JudgeResult] = []

        for item in items:
            result = self.evaluate(
                query=item["query"],
                answer=item["answer"],
                hits=item.get("hits", []),
                query_id=item.get("query_id", ""),
                query_type=item.get("query_type", "unknown"),
            )
            results.append(result)

        return results


# ---------------------------------------------------------------------------
# 헬퍼 함수
# ---------------------------------------------------------------------------


def _error_result(
    *,
    query_id: str,
    query: str,
    query_type: str,
    error: str,
    thresholds: dict[str, float],
) -> JudgeResult:
    """에러 발생 시 0점 JudgeResult를 생성한다."""
    zero_scores = JudgeScore(
        relevance=0.0,
        faithfulness=0.0,
        quote_accuracy=0.0,
        temporal_correctness=0.0,
        reasoning=error,
    )
    _, axis_results = check_thresholds(zero_scores, thresholds)

    return JudgeResult(
        query_id=query_id,
        query=query,
        query_type=query_type,
        scores=zero_scores,
        axis_results=axis_results,
        judge_passed=False,
        error=error,
    )
