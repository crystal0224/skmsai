"""EvidenceFilter — 근거 커버리지 + 환각 탐지 서비스.

PR-024: LLM 응답의 근거 커버리지를 확인하고 환각을 필터링한다.

기능:
- 응답에 인용된 quote_id가 실제 검색 결과에 존재하는지 검증
- 응답에서 언급된 개정판이 실제 검색 결과에 포함되는지 검증
- 응답 문장별 근거 매칭률 추정
- 환각 지표(hallucination indicators) 감지
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from scripts.lib.search_types import SearchHit

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# EvidenceCheckResult — 검증 결과 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceCheckResult:
    """근거 커버리지 + 환각 필터 검증 결과.

    Attributes:
        coverage_score: 근거 커버리지 점수 (0.0~1.0)
        cited_quote_ids: 응답에서 인용된 quote_id 목록
        valid_quote_ids: 유효한 (검색 결과에 존재하는) quote_id 목록
        invalid_quote_ids: 무효한 (검색 결과에 없는) quote_id 목록
        cited_editions: 응답에서 언급된 개정판 목록
        unsupported_editions: 검색 결과에 없는 개정판 목록
        hallucination_flags: 환각 지표 목록
        passed: 검증 통과 여부
    """

    coverage_score: float
    cited_quote_ids: tuple[str, ...]
    valid_quote_ids: tuple[str, ...]
    invalid_quote_ids: tuple[str, ...]
    cited_editions: tuple[str, ...]
    unsupported_editions: tuple[str, ...]
    hallucination_flags: tuple[str, ...]
    passed: bool


# ---------------------------------------------------------------------------
# EvidenceFilterConfig — 설정 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceFilterConfig:
    """근거 필터 설정.

    Attributes:
        min_coverage: 최소 커버리지 점수 (미만이면 실패)
        max_invalid_quotes: 허용되는 최대 무효 quote_id 수
        check_editions: 개정판 참조 검증 활성화
        check_hallucination: 환각 지표 감지 활성화
    """

    min_coverage: float = 0.0
    max_invalid_quotes: int = 0
    check_editions: bool = True
    check_hallucination: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceFilterConfig:
        """dict에서 생성."""
        return cls(
            min_coverage=float(data.get("min_coverage", 0.0)),
            max_invalid_quotes=int(data.get("max_invalid_quotes", 0)),
            check_editions=bool(data.get("check_editions", True)),
            check_hallucination=bool(data.get("check_hallucination", True)),
        )


# ---------------------------------------------------------------------------
# EvidenceFilter — 메인 서비스
# ---------------------------------------------------------------------------

# quote_id 패턴: edition|section|type|number (4+ segments, pipe-separated)
_QUOTE_ID_RE = re.compile(r"\b(\d{4}-(?:\d{1,2}차|초판)\|[^|\s]+\|[^|\s]+\|[^|\s]+)\b")

# 개정판 참조 패턴
_EDITION_MENTION_RE = re.compile(r"(?:(\d{1,2})차\s*(?:개정판)?|초판|현행)")

# 환각 지표 패턴
_HALLUCINATION_PATTERNS = [
    (re.compile(r"(?:일반적으로|통상적으로|보통)\s+.{5,}(?:알려져|여겨)"), "일반론 주장"),
    (re.compile(r"(?:제\s*\d+\s*조|조항\s*\d+)"), "구체적 조항 번호 (SKMS에 없음)"),
    (re.compile(r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일"), "구체적 날짜 (환각 가능)"),
    (re.compile(r"(?:약\s*)?\d+(?:\.\d+)?%"), "구체적 백분율 수치"),
]


class EvidenceFilter:
    """근거 커버리지 + 환각 탐지 서비스."""

    def __init__(self, config: EvidenceFilterConfig | None = None) -> None:
        self._config = config or EvidenceFilterConfig()

    def check(
        self,
        answer: str,
        hits: list[SearchHit],
    ) -> EvidenceCheckResult:
        """LLM 응답의 근거 커버리지를 검증한다.

        Args:
            answer: LLM이 생성한 답변 텍스트
            hits: 검색 결과 (SearchHit 목록)

        Returns:
            EvidenceCheckResult (불변)
        """
        if not answer or not hits:
            return EvidenceCheckResult(
                coverage_score=0.0,
                cited_quote_ids=(),
                valid_quote_ids=(),
                invalid_quote_ids=(),
                cited_editions=(),
                unsupported_editions=(),
                hallucination_flags=(),
                passed=not answer,  # 빈 응답이면 pass, 있는데 hits 없으면 fail
            )

        # 검색 결과에서 유효한 quote_id 집합
        hit_quote_ids = {h.quote_id for h in hits}
        hit_editions = {h.edition_id for h in hits}

        # 1. quote_id 인용 검증
        cited_ids = tuple(set(_QUOTE_ID_RE.findall(answer)))
        valid_ids = tuple(qid for qid in cited_ids if qid in hit_quote_ids)
        invalid_ids = tuple(qid for qid in cited_ids if qid not in hit_quote_ids)

        # 2. 커버리지 점수 계산
        coverage = _compute_coverage(answer, hits)

        # 3. 개정판 참조 검증
        cited_editions: tuple[str, ...] = ()
        unsupported_editions: tuple[str, ...] = ()
        if self._config.check_editions:
            cited_editions, unsupported_editions = _check_edition_references(
                answer, hit_editions
            )

        # 4. 환각 지표 감지
        hallucination_flags: tuple[str, ...] = ()
        if self._config.check_hallucination:
            hallucination_flags = _detect_hallucination_indicators(answer)

        # 통과 판정
        passed = True
        if self._config.min_coverage > 0 and coverage < self._config.min_coverage:
            passed = False
        if len(invalid_ids) > self._config.max_invalid_quotes:
            passed = False

        return EvidenceCheckResult(
            coverage_score=coverage,
            cited_quote_ids=cited_ids,
            valid_quote_ids=valid_ids,
            invalid_quote_ids=invalid_ids,
            cited_editions=cited_editions,
            unsupported_editions=unsupported_editions,
            hallucination_flags=hallucination_flags,
            passed=passed,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_coverage(answer: str, hits: list[SearchHit]) -> float:
    """응답의 근거 커버리지를 추정한다.

    각 검색 결과 텍스트에서 핵심 구문(4자 이상 단어)을 추출하고,
    응답에 해당 구문이 포함된 비율로 커버리지를 계산한다.
    """
    if not hits:
        return 0.0

    # 검색 결과에서 핵심 구문 추출 (4자 이상 단어)
    evidence_phrases: set[str] = set()
    for h in hits:
        words = re.findall(r"[\w가-힣]{4,}", h.text)
        evidence_phrases.update(words)

    if not evidence_phrases:
        return 0.0

    # 응답에 포함된 근거 구문 수
    matched = sum(1 for phrase in evidence_phrases if phrase in answer)
    return matched / len(evidence_phrases)


def _check_edition_references(
    answer: str,
    hit_editions: set[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """응답에서 언급된 개정판이 검색 결과에 있는지 확인한다."""
    # 개정판 참조 매핑
    edition_map: dict[str, str] = {
        "초판": "1979-초판",
        "현행": "2020-14차",
    }
    for i in range(1, 15):
        edition_map[f"{i}차"] = f"{_year_for_revision(i)}-{i}차"

    mentioned = set()
    for match in _EDITION_MENTION_RE.finditer(answer):
        full = match.group()
        mapped = edition_map.get(full.replace("개정판", "").strip())
        if mapped:
            mentioned.add(mapped)

    cited = tuple(sorted(mentioned))
    unsupported = tuple(ed for ed in cited if ed not in hit_editions)
    return cited, unsupported


def _year_for_revision(num: int) -> int:
    """개정 차수 → 연도."""
    year_map = {
        0: 1979,
        1: 1981,
        2: 1982,
        3: 1983,
        4: 1984,
        5: 1985,
        6: 1988,
        7: 1991,
        8: 1995,
        9: 1997,
        10: 1998,
        11: 2004,
        12: 2008,
        13: 2016,
        14: 2020,
    }
    return year_map.get(num, 2020)


def _detect_hallucination_indicators(answer: str) -> tuple[str, ...]:
    """응답에서 환각 지표를 감지한다."""
    flags: list[str] = []
    for pattern, label in _HALLUCINATION_PATTERNS:
        if pattern.search(answer):
            flags.append(label)
    return tuple(flags)
