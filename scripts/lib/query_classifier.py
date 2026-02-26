"""QueryClassifier — 규칙 기반 4-Type 질의 분류기.

PR-022: Query Router 고도화 — 4-Type 질의 분류 (≥90% 정확도).

분류 체계 (retrieval.yaml 기준):
- single_version: 단일 개정판 내 질의
- cross_version: 개정판 간 비교 질의
- definition: 용어/개념 정의 질의
- open_ended: 일반 탐색 질의

규칙 기반 분류를 우선 적용하고, 불확실한 경우 LLM 폴백을 지원한다.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QUERY_TYPES = frozenset({"single_version", "cross_version", "definition", "open_ended"})

# 기존 5-intent → 4-type 매핑
INTENT_TO_QUERY_TYPE: dict[str, str] = {
    "specific_time": "single_version",
    "general_definition": "definition",
    "evolution_comparison": "cross_version",
    "content_generation": "open_ended",
    "open_ended": "open_ended",
}

# 개정판 참조 패턴
_EDITION_PATTERNS = [
    re.compile(r"(\d{1,2})차\s*(개정판)?"),  # "14차", "10차 개정판"
    re.compile(r"초판"),
    re.compile(r"(19[7-9]\d|20[0-2]\d)년"),  # "1979년", "2020년"
    re.compile(r"현행\s*(SKMS)?"),  # "현행", "현행 SKMS"
]

# 단일 개정판 키워드 (특정 판을 지칭)
_SINGLE_EDITION_PATTERNS = [
    re.compile(r"(\d{1,2})차\s*(개정판)?에서"),  # "14차에서", "10차 개정판에서"
    re.compile(r"(\d{1,2})차\s*개정판의"),  # "11차 개정판의"
    re.compile(r"초판에서"),
    re.compile(r"초판의"),  # "초판의 ~"
    re.compile(r"(19[7-9]\d|20[0-2]\d)년\s*(판)?에서"),
    re.compile(r"현행\s*(SKMS)?에서"),
]

# 비교/시간축 키워드
_CROSS_VERSION_KEYWORDS = [
    "변화",
    "변했",
    "달라졌",
    "어떻게 다른",
    "비교",
    "비교해",
    "대비",
    "변천",
    "변천사",
    "변천과정",
    "처음 등장",
    "처음 도입",
    "언제 처음",
    "에서부터",
    "까지",
    "재구성",
    "재편",
    "개편",
    "진화",
    "발전",
]
_CROSS_VERSION_RE = re.compile("|".join(re.escape(k) for k in _CROSS_VERSION_KEYWORDS))

# 다중 개정판 참조 패턴 (비교의 신호)
_MULTI_EDITION_RE = re.compile(r"(초판|(\d{1,2})차).{0,20}(초판|(\d{1,2})차)")

# 정의 질의 패턴
_DEFINITION_PATTERNS = [
    re.compile(r"(.{1,20})(이?란|란)\s*(무엇|어떤|뭐)", re.IGNORECASE),
    re.compile(r"(.{1,20})의?\s*정의(는|는\?|를)?"),
    re.compile(r"(.{1,20})(?:이|가)\s*뭐", re.IGNORECASE),
    re.compile(r"(.{1,20})(이란|란)\??\s*$"),
    re.compile(r"(.{1,20})(?:은|는)\s*(?:어떤|무슨)\s*(?:뜻|의미|개념)"),
    re.compile(r"어떤\s*의미로\s*사용"),  # "어떤 의미로 사용되나요"
    re.compile(r"(.{1,20})의\s*(궁극적\s*)?(목적|목표|역할)(은|는|이)?\s*(\?|$)"),
    re.compile(r"what\s+is\s+", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# ClassificationResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClassificationResult:
    """질의 분류 결과 (불변).

    Attributes:
        query_type: 4가지 질의 유형 중 하나
        confidence: 분류 신뢰도 (0.0~1.0)
        edition_hint: 감지된 개정판 힌트 (없으면 None)
        reasoning: 분류 근거 (사람이 읽을 수 있는 설명)
    """

    query_type: str
    confidence: float
    edition_hint: str | None
    reasoning: str

    def __post_init__(self) -> None:
        if self.query_type not in QUERY_TYPES:
            object.__setattr__(self, "query_type", "open_ended")
        if not (0.0 <= self.confidence <= 1.0):
            object.__setattr__(self, "confidence", max(0.0, min(1.0, self.confidence)))


# ---------------------------------------------------------------------------
# Rule-based classifier
# ---------------------------------------------------------------------------


def classify_query(query: str) -> ClassificationResult:
    """규칙 기반으로 질의를 4가지 유형 중 하나로 분류한다.

    분류 우선순위:
    1. cross_version: 비교 키워드 + 다중 개정판 참조
    2. single_version: 단일 개정판 참조 + 정의 아닌 질의
    3. definition: 정의 질의 패턴 매칭
    4. open_ended: 위 패턴에 해당하지 않는 경우
    """
    if not query or not query.strip():
        return ClassificationResult(
            query_type="open_ended",
            confidence=0.5,
            edition_hint=None,
            reasoning="빈 질의",
        )

    query_stripped = query.strip()

    # Step 1: cross_version 감지
    result = _detect_cross_version(query_stripped)
    if result is not None:
        return result

    # Step 2: single_version 감지
    result = _detect_single_version(query_stripped)
    if result is not None:
        return result

    # Step 3: definition 감지
    result = _detect_definition(query_stripped)
    if result is not None:
        return result

    # Step 4: open_ended 기본값
    return ClassificationResult(
        query_type="open_ended",
        confidence=0.7,
        edition_hint=None,
        reasoning="특정 패턴 미매칭, 일반 탐색 질의",
    )


def _detect_cross_version(query: str) -> ClassificationResult | None:
    """비교/시간축 질의를 감지한다."""
    has_cross_keyword = _CROSS_VERSION_RE.search(query) is not None
    has_multi_edition = _MULTI_EDITION_RE.search(query) is not None

    # 비교 키워드 + 다중 개정판 참조 → 높은 확신
    if has_cross_keyword and has_multi_edition:
        return ClassificationResult(
            query_type="cross_version",
            confidence=0.95,
            edition_hint=None,
            reasoning="비교 키워드 + 다중 개정판 참조",
        )

    # 비교 키워드만 있어도 cross_version일 가능성 높음
    if has_cross_keyword:
        # "처음 등장/도입" + 개정판 참조 → cross_version
        if re.search(r"처음\s*(등장|도입)", query):
            return ClassificationResult(
                query_type="cross_version",
                confidence=0.90,
                edition_hint=None,
                reasoning="최초 도입 시점 질의 (시간축 탐색)",
            )

        # 일반 비교 키워드
        return ClassificationResult(
            query_type="cross_version",
            confidence=0.85,
            edition_hint=None,
            reasoning="비교/변화 키워드 감지",
        )

    # 다중 개정판 참조만 있으면 비교 가능성
    if has_multi_edition:
        return ClassificationResult(
            query_type="cross_version",
            confidence=0.80,
            edition_hint=None,
            reasoning="다중 개정판 참조 감지",
        )

    return None


def _detect_single_version(query: str) -> ClassificationResult | None:
    """단일 개정판 질의를 감지한다."""
    # "~차에서", "초판에서" 등 명시적 단일 개정판 참조
    for pattern in _SINGLE_EDITION_PATTERNS:
        match = pattern.search(query)
        if match:
            edition_hint = _extract_edition_hint(query)
            return ClassificationResult(
                query_type="single_version",
                confidence=0.90,
                edition_hint=edition_hint,
                reasoning=f"단일 개정판 참조: {match.group()}",
            )

    # "현행 SKMS에서" 패턴 (명시적 현행 참조)
    if re.search(r"현행", query):
        return ClassificationResult(
            query_type="single_version",
            confidence=0.85,
            edition_hint="2020-14차",
            reasoning="현행 SKMS 참조",
        )

    return None


def _detect_definition(query: str) -> ClassificationResult | None:
    """정의 질의를 감지한다."""
    for pattern in _DEFINITION_PATTERNS:
        match = pattern.search(query)
        if match:
            return ClassificationResult(
                query_type="definition",
                confidence=0.90,
                edition_hint=None,
                reasoning=f"정의 질의 패턴: {match.group()[:30]}",
            )

    # "~의 정의/뜻/의미" 간단 패턴
    if re.search(r"(뜻|의미|개념)\s*(은|는|이|가)?\s*(\?|$)", query):
        return ClassificationResult(
            query_type="definition",
            confidence=0.85,
            edition_hint=None,
            reasoning="뜻/의미/개념 질의 패턴",
        )

    return None


def _extract_edition_hint(query: str) -> str | None:
    """질의에서 개정판 힌트를 추출한다."""
    # "N차" 패턴
    match = re.search(r"(\d{1,2})차", query)
    if match:
        num = match.group(1)
        # 일반적인 개정판 매핑
        edition_map = {
            "1": "1981-1차",
            "10": "1998-10차",
            "11": "2004-11차",
            "12": "2008-12차",
            "13": "2016-13차",
            "14": "2020-14차",
        }
        return edition_map.get(num, f"{num}차")

    # "초판" 패턴
    if "초판" in query:
        return "1979-초판"

    # 연도 패턴
    match = re.search(r"(19[7-9]\d|20[0-2]\d)년", query)
    if match:
        year = match.group(1)
        year_map = {
            "1979": "1979-초판",
            "1981": "1981-1차",
            "1998": "1998-10차",
            "2004": "2004-11차",
            "2008": "2008-12차",
            "2016": "2016-13차",
            "2020": "2020-14차",
        }
        return year_map.get(year)

    return None


# ---------------------------------------------------------------------------
# Batch classification + accuracy evaluation
# ---------------------------------------------------------------------------


def classify_batch(
    queries: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], ClassificationResult]]:
    """여러 질의를 일괄 분류하고 결과를 반환한다.

    Args:
        queries: [{"id": ..., "query": ..., "query_type": ...}, ...]

    Returns:
        [(원본 query dict, ClassificationResult), ...]
    """
    results = []
    for item in queries:
        query = item.get("query", "")
        result = classify_query(query)
        results.append((item, result))
    return results


def evaluate_accuracy(
    queries: list[dict[str, Any]],
) -> dict[str, Any]:
    """분류 정확도를 평가한다.

    Args:
        queries: [{"id": ..., "query": ..., "query_type": ...}, ...]

    Returns:
        {
            "total": int,
            "correct": int,
            "accuracy": float,
            "per_type": {type: {"total": int, "correct": int, "accuracy": float}},
            "errors": [{"id": str, "query": str, "expected": str, "predicted": str}],
        }
    """
    classified = classify_batch(queries)

    total = 0
    correct = 0
    per_type: dict[str, dict[str, int]] = {}
    errors: list[dict[str, str]] = []

    for item, result in classified:
        expected = item.get("query_type", "open_ended")
        predicted = result.query_type

        total += 1

        if expected not in per_type:
            per_type[expected] = {"total": 0, "correct": 0}
        per_type[expected]["total"] += 1

        if predicted == expected:
            correct += 1
            per_type[expected]["correct"] += 1
        else:
            errors.append(
                {
                    "id": item.get("id", ""),
                    "query": item.get("query", ""),
                    "expected": expected,
                    "predicted": predicted,
                    "confidence": result.confidence,
                    "reasoning": result.reasoning,
                }
            )

    accuracy = correct / total if total > 0 else 0.0

    per_type_stats = {}
    for qtype, counts in per_type.items():
        type_acc = counts["correct"] / counts["total"] if counts["total"] > 0 else 0.0
        per_type_stats[qtype] = {
            "total": counts["total"],
            "correct": counts["correct"],
            "accuracy": type_acc,
        }

    return {
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "per_type": per_type_stats,
        "errors": errors,
    }
