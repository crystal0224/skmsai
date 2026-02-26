"""CrossVersionComparison — 개정판 간 비교 서비스.

PR-025: 검색 결과를 개정판별로 그룹화하고, 구조화된 비교 컨텍스트를 생성한다.

기능:
- 검색 결과를 개정판별로 그룹화 (시간순 정렬)
- 개념 타임라인 기반 진화 메타데이터 통합
- 개정판별 정의 변경 추출
- LLM 프롬프트용 구조화된 비교 컨텍스트 포맷팅
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from scripts.lib.concept_timeline import ConceptInfo, ConceptTimeline
from scripts.lib.search_types import SearchHit

logger = logging.getLogger(__name__)

# 개정판 정렬 순서 (시간순)
EDITION_ORDER: dict[str, int] = {
    "1979-초판": 0,
    "1981-1차": 1,
    "1982-2차": 2,
    "1983-3차": 3,
    "1984-4차": 4,
    "1985-5차": 5,
    "1988-6차": 6,
    "1991-7차": 7,
    "1995-8차": 8,
    "1997-9차": 9,
    "1998-10차": 10,
    "2004-11차": 11,
    "2008-12차": 12,
    "2016-13차": 13,
    "2020-14차": 14,
}


def _edition_sort_key(edition_id: str) -> int:
    """개정판 ID → 정렬 키."""
    return EDITION_ORDER.get(edition_id, 99)


# ---------------------------------------------------------------------------
# EditionGroup — 개정판별 검색 결과 그룹 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EditionGroup:
    """단일 개정판의 검색 결과 그룹.

    Attributes:
        edition_id: 개정판 식별자
        year: 출판 연도
        hits: 해당 개정판의 SearchHit 목록
        definition_texts: definition 타입 텍스트 목록
        narrative_texts: narrative 타입 텍스트 목록
    """

    edition_id: str
    year: int
    hits: tuple[SearchHit, ...]
    definition_texts: tuple[str, ...]
    narrative_texts: tuple[str, ...]

    @property
    def hit_count(self) -> int:
        """검색 결과 수."""
        return len(self.hits)

    @property
    def has_definition(self) -> bool:
        """definition 타입이 포함되어 있는지."""
        return len(self.definition_texts) > 0


# ---------------------------------------------------------------------------
# ComparisonContext — 비교 컨텍스트 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComparisonContext:
    """개정판 간 비교 컨텍스트.

    Attributes:
        query: 사용자 질의
        edition_groups: 개정판별 그룹 (시간순)
        edition_count: 비교 대상 개정판 수
        total_hits: 전체 검색 결과 수
        evolution_summary: ConceptTimeline 진화 요약 (없으면 None)
        concept_name: 대상 개념명 (감지된 경우)
    """

    query: str
    edition_groups: tuple[EditionGroup, ...]
    edition_count: int
    total_hits: int
    evolution_summary: dict[str, Any] | None
    concept_name: str


# ---------------------------------------------------------------------------
# ComparisonConfig — 설정 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComparisonConfig:
    """비교 서비스 설정.

    Attributes:
        max_editions: 비교할 최대 개정판 수 (0=무제한)
        include_narratives: narrative 텍스트 포함 여부
        max_text_length: 비교 텍스트 최대 길이 (잘림)
    """

    max_editions: int = 0
    include_narratives: bool = True
    max_text_length: int = 500

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ComparisonConfig:
        """dict에서 생성."""
        return cls(
            max_editions=int(data.get("max_editions", 0)),
            include_narratives=bool(data.get("include_narratives", True)),
            max_text_length=int(data.get("max_text_length", 500)),
        )


# ---------------------------------------------------------------------------
# CrossVersionComparisonService — 메인 서비스
# ---------------------------------------------------------------------------


class CrossVersionComparisonService:
    """개정판 간 비교 서비스.

    검색 결과를 개정판별로 그룹화하고, 구조화된 비교 컨텍스트를 생성한다.
    """

    def __init__(
        self,
        *,
        config: ComparisonConfig | None = None,
        concept_timeline: ConceptTimeline | None = None,
    ) -> None:
        self._config = config or ComparisonConfig()
        self._timeline = concept_timeline

    def build_comparison(
        self,
        query: str,
        hits: list[SearchHit],
    ) -> ComparisonContext:
        """검색 결과에서 비교 컨텍스트를 생성한다.

        Args:
            query: 사용자 질의
            hits: 검색 결과 (SearchHit 목록)

        Returns:
            ComparisonContext (불변)
        """
        if not hits:
            return ComparisonContext(
                query=query,
                edition_groups=(),
                edition_count=0,
                total_hits=0,
                evolution_summary=None,
                concept_name="",
            )

        # 1. 개정판별 그룹화
        groups = _group_by_edition(hits, self._config.max_text_length)

        # 2. 시간순 정렬
        groups = tuple(sorted(groups, key=lambda g: _edition_sort_key(g.edition_id)))

        # 3. max_editions 제한
        if self._config.max_editions > 0:
            groups = groups[: self._config.max_editions]

        # 4. ConceptTimeline 연동
        concept_name = ""
        evolution_summary = None
        if self._timeline is not None:
            concept_name, evolution_summary = _lookup_evolution(query, self._timeline)

        return ComparisonContext(
            query=query,
            edition_groups=groups,
            edition_count=len(groups),
            total_hits=len(hits),
            evolution_summary=evolution_summary,
            concept_name=concept_name,
        )

    def format_comparison_prompt(
        self,
        context: ComparisonContext,
    ) -> str:
        """비교 컨텍스트를 LLM 프롬프트용 텍스트로 포맷팅한다.

        Args:
            context: ComparisonContext

        Returns:
            포맷팅된 비교 컨텍스트 문자열
        """
        if context.edition_count == 0:
            return "[비교 대상 없음]"

        lines: list[str] = []

        # 헤더
        lines.append("[CROSS-VERSION COMPARISON]")
        lines.append(f"query: {context.query}")
        lines.append(f"editions_compared: {context.edition_count}")

        if context.concept_name:
            lines.append(f"target_concept: {context.concept_name}")

        # 진화 요약 (있으면)
        if context.evolution_summary:
            summary = context.evolution_summary
            lines.append("")
            lines.append("[EVOLUTION SUMMARY]")
            lines.append(
                f"concept: {summary.get('name_ko', '')} ({summary.get('name_en', '')})"
            )
            lines.append(f"category: {summary.get('category', '')}")
            lines.append(f"active: {summary.get('is_active', True)}")
            lines.append(f"first: {summary.get('first_edition', '')}")
            if summary.get("last_edition"):
                lines.append(f"last: {summary['last_edition']}")
            lines.append(f"modified_count: {summary.get('modified_count', 0)}")

            # 개정판별 상태
            for ed in summary.get("editions", []):
                status_line = f"  {ed['edition_id']} ({ed['year']}): {ed['status']}"
                if ed.get("note"):
                    status_line += f" — {ed['note']}"
                lines.append(status_line)

        # 개정판별 내용
        for group in context.edition_groups:
            lines.append("")
            lines.append(f"[EDITION: {group.edition_id} ({group.year})]")

            if group.definition_texts:
                for i, text in enumerate(group.definition_texts, 1):
                    lines.append(f"  [정의 {i}] {text}")

            if self._config.include_narratives and group.narrative_texts:
                for i, text in enumerate(group.narrative_texts, 1):
                    lines.append(f"  [서술 {i}] {text}")

            if not group.definition_texts and not group.narrative_texts:
                lines.append("  (해당 개정판에 관련 인용 없음)")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _group_by_edition(
    hits: list[SearchHit],
    max_text_length: int,
) -> tuple[EditionGroup, ...]:
    """검색 결과를 개정판별로 그룹화한다."""
    edition_map: dict[str, list[SearchHit]] = {}
    for h in hits:
        if h.edition_id not in edition_map:
            edition_map[h.edition_id] = []
        edition_map[h.edition_id].append(h)

    groups: list[EditionGroup] = []
    for edition_id, ed_hits in edition_map.items():
        year = ed_hits[0].year if ed_hits else 0

        definition_texts: list[str] = []
        narrative_texts: list[str] = []

        for h in ed_hits:
            text = h.text[:max_text_length] if len(h.text) > max_text_length else h.text
            if h.quote_type == "definition":
                definition_texts.append(text)
            else:
                narrative_texts.append(text)

        groups.append(
            EditionGroup(
                edition_id=edition_id,
                year=year,
                hits=tuple(ed_hits),
                definition_texts=tuple(definition_texts),
                narrative_texts=tuple(narrative_texts),
            )
        )

    return tuple(groups)


def _lookup_evolution(
    query: str,
    timeline: ConceptTimeline,
) -> tuple[str, dict[str, Any] | None]:
    """ConceptTimeline에서 질의 관련 개념의 진화 요약을 조회한다.

    Returns:
        (concept_name, evolution_summary) 튜플
    """
    matches = timeline.search_concepts(query)
    if not matches:
        return ("", None)

    # 가장 첫 번째 매칭 사용 (search_concepts 결과)
    concept = matches[0]
    summary = timeline.get_evolution_summary(concept.concept_id)
    return (concept.name_ko, summary)
