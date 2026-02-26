"""TemporalGuardrail — 시간축 충돌 감지 및 방어 서비스.

PR-023: 검색 결과에서 시간축 충돌을 감지하고 사용자에게 경고를 제공한다.

감지 규칙 (guardrails/conflict_rules.yaml):
- TC-001: 정의 변경 감지 — 같은 개념이 여러 개정판에서 다르게 정의
- TC-002: 개념 소멸 감지 — 이전 개정판에만 존재하는 개념
- TC-003: 개념 신설 감지 — 질의 대상 개정판 이후에 도입된 개념
- TC-004: 용어 변경 감지 — 동일 개념의 명칭이 개정판마다 다름
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.lib.search_types import SearchHit

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TemporalWarning — 시간축 경고 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TemporalWarning:
    """시간축 충돌 경고 단건.

    Attributes:
        rule_id: 감지 규칙 ID (TC-001 ~ TC-004)
        severity: 심각도 ("high", "medium", "low")
        concept: 관련 개념명
        message: 사용자 안내 메시지
        editions: 관련 개정판 목록
    """

    rule_id: str
    severity: str
    concept: str
    message: str
    editions: tuple[str, ...]


# ---------------------------------------------------------------------------
# GuardrailResult — 가드레일 검사 결과 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GuardrailResult:
    """시간축 가드레일 검사 결과.

    Attributes:
        has_conflict: 충돌 존재 여부
        warnings: 감지된 경고 목록
        edition_count: 검색 결과에 포함된 개정판 수
        definition_count: 검색 결과에 포함된 definition 타입 수
    """

    has_conflict: bool
    warnings: tuple[TemporalWarning, ...]
    edition_count: int
    definition_count: int


# ---------------------------------------------------------------------------
# GuardrailConfig — 설정 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GuardrailConfig:
    """가드레일 설정.

    Attributes:
        enabled: 활성화 여부
        max_warnings: 응답에 포함할 최대 경고 수
        fail_mode: 충돌 시 동작 ("warn", "block", "silent")
    """

    enabled: bool = True
    max_warnings: int = 3
    fail_mode: str = "warn"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GuardrailConfig:
        """dict에서 생성."""
        return cls(
            enabled=bool(data.get("enabled", True)),
            max_warnings=int(data.get("max_warnings", 3)),
            fail_mode=str(data.get("fail_mode", "warn")),
        )


# ---------------------------------------------------------------------------
# Known Conflicts Registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KnownConflict:
    """사전 정의된 알려진 충돌."""

    concept: str
    concept_id: str
    editions: tuple[str, ...]
    note: str


def load_known_conflicts(path: Path) -> tuple[KnownConflict, ...]:
    """guardrails/conflict_rules.yaml에서 known_conflicts를 로드한다."""
    if not path.exists():
        logger.warning("충돌 규칙 파일 없음: %s", path)
        return ()

    import yaml

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    raw = data.get("temporal_conflict", {}).get("known_conflicts", [])
    conflicts = []
    for item in raw:
        conflicts.append(
            KnownConflict(
                concept=item.get("concept", ""),
                concept_id=item.get("concept_id", ""),
                editions=tuple(item.get("editions", [])),
                note=item.get("note", ""),
            )
        )
    return tuple(conflicts)


# ---------------------------------------------------------------------------
# TemporalGuardrail — 메인 서비스
# ---------------------------------------------------------------------------


class TemporalGuardrail:
    """시간축 충돌 감지 서비스.

    검색 결과(SearchHit)를 분석하여 시간축 충돌을 감지하고
    구조화된 경고를 반환한다.
    """

    def __init__(
        self,
        *,
        config: GuardrailConfig | None = None,
        known_conflicts: tuple[KnownConflict, ...] = (),
        concept_timeline: Any | None = None,
    ) -> None:
        self._config = config or GuardrailConfig()
        self._known_conflicts = known_conflicts
        self._concept_timeline = concept_timeline

    @classmethod
    def from_yaml(
        cls,
        rules_path: Path,
        *,
        concept_timeline: Any | None = None,
    ) -> TemporalGuardrail:
        """YAML 파일에서 가드레일을 로드한다."""
        known = load_known_conflicts(rules_path)

        import yaml

        config = GuardrailConfig()
        if rules_path.exists():
            with open(rules_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            policy = data.get("temporal_conflict", {}).get("response_policy", {})
            config = GuardrailConfig(
                enabled=True,
                max_warnings=int(policy.get("max_conflicts_shown", 3)),
                fail_mode=str(policy.get("fail_mode", "warn")),
            )

        return cls(
            config=config,
            known_conflicts=known,
            concept_timeline=concept_timeline,
        )

    def check(
        self,
        hits: list[SearchHit],
        *,
        query: str = "",
        edition_hint: str | None = None,
    ) -> GuardrailResult:
        """검색 결과에서 시간축 충돌을 검사한다.

        Args:
            hits: 검색 결과 목록
            query: 사용자 질의 (개념명 매칭에 사용)
            edition_hint: 사용자가 지정한 개정판 (single_version 질의)

        Returns:
            GuardrailResult (불변)
        """
        if not self._config.enabled or not hits:
            return GuardrailResult(
                has_conflict=False,
                warnings=(),
                edition_count=0,
                definition_count=0,
            )

        warnings: list[TemporalWarning] = []

        # 기본 통계
        editions = set()
        definition_count = 0
        for h in hits:
            editions.add(h.edition_id)
            if h.quote_type == "definition":
                definition_count += 1

        # TC-001: 정의 변경 감지
        tc001 = self._check_definition_conflict(hits)
        warnings.extend(tc001)

        # TC-002 / TC-003: 개념 소멸/신설 감지 (known_conflicts + concept_timeline)
        tc002_003 = self._check_concept_existence(query, edition_hint)
        warnings.extend(tc002_003)

        # TC-004: 용어 변경 감지
        tc004 = self._check_term_changes(query)
        warnings.extend(tc004)

        # Known conflicts 매칭
        known = self._check_known_conflicts(query, hits)
        warnings.extend(known)

        # 중복 제거 (rule_id + concept 기준)
        seen = set()
        unique_warnings: list[TemporalWarning] = []
        for w in warnings:
            key = (w.rule_id, w.concept)
            if key not in seen:
                seen.add(key)
                unique_warnings.append(w)

        # max_warnings 제한
        limited = unique_warnings[: self._config.max_warnings]

        return GuardrailResult(
            has_conflict=len(limited) > 0,
            warnings=tuple(limited),
            edition_count=len(editions),
            definition_count=definition_count,
        )

    def _check_definition_conflict(
        self, hits: list[SearchHit]
    ) -> list[TemporalWarning]:
        """TC-001: 동일 개념의 정의가 여러 개정판에 걸쳐 존재하는 경우."""
        # edition별 definition quote 수집
        edition_defs: dict[str, list[str]] = {}
        for h in hits:
            if h.quote_type == "definition":
                if h.edition_id not in edition_defs:
                    edition_defs[h.edition_id] = []
                edition_defs[h.edition_id].append(h.text[:50])

        if len(edition_defs) < 2:
            return []

        editions_sorted = tuple(sorted(edition_defs.keys()))
        return [
            TemporalWarning(
                rule_id="TC-001",
                severity="high",
                concept="(검색 결과 내 정의)",
                message=(
                    f"정의(definition) 타입 quote가 {len(editions_sorted)}개 "
                    f"개정판에 걸쳐 존재합니다: {', '.join(editions_sorted)}. "
                    "어느 개정판 기준으로 답변할지 확인하세요."
                ),
                editions=editions_sorted,
            )
        ]

    def _check_concept_existence(
        self,
        query: str,
        edition_hint: str | None,
    ) -> list[TemporalWarning]:
        """TC-002/TC-003: concept_timeline 기반 개념 소멸/신설 감지."""
        if self._concept_timeline is None or not query:
            return []

        warnings: list[TemporalWarning] = []

        # 질의에서 개념 검색
        matches = self._concept_timeline.search_concepts(query)
        if not matches:
            return []

        for concept in matches:
            # TC-002: 개념이 최신 개정판에 없는 경우 (소멸)
            if not concept.is_active:
                last_year = concept.year_range[1]
                warnings.append(
                    TemporalWarning(
                        rule_id="TC-002",
                        severity="medium",
                        concept=concept.name_ko,
                        message=(
                            f"'{concept.name_ko}'은(는) {concept.last_edition}까지만 "
                            "등장합니다. 현행 SKMS에는 해당 개념이 없습니다."
                        ),
                        editions=(concept.first_edition, concept.last_edition or ""),
                    ),
                )

            # TC-003: edition_hint가 개념 도입 이전인 경우 (신설)
            if edition_hint and concept.first_edition:
                first_year = concept.year_range[0]
                # edition_hint에서 연도 추출
                hint_year = _extract_year(edition_hint)
                if hint_year and first_year and hint_year < first_year:
                    warnings.append(
                        TemporalWarning(
                            rule_id="TC-003",
                            severity="medium",
                            concept=concept.name_ko,
                            message=(
                                f"'{concept.name_ko}'은(는) {concept.first_edition}에서 "
                                f"처음 도입되었습니다. {edition_hint}에는 존재하지 않습니다."
                            ),
                            editions=(concept.first_edition,),
                        ),
                    )

        return warnings

    def _check_term_changes(self, query: str) -> list[TemporalWarning]:
        """TC-004: concept_timeline 기반 용어 변경 감지."""
        if self._concept_timeline is None or not query:
            return []

        warnings: list[TemporalWarning] = []
        matches = self._concept_timeline.search_concepts(query)

        for concept in matches:
            # renamed 상태인 개정판이 있는지 확인
            renamed_editions = []
            for es in concept.editions:
                if es.status == "renamed":
                    renamed_editions.append(f"{es.edition_id}: {es.note or '명칭 변경'}")

            if renamed_editions:
                warnings.append(
                    TemporalWarning(
                        rule_id="TC-004",
                        severity="low",
                        concept=concept.name_ko,
                        message=(
                            f"'{concept.name_ko}'의 명칭이 개정판에 따라 "
                            f"변경되었습니다: {'; '.join(renamed_editions)}"
                        ),
                        editions=tuple(
                            es.edition_id
                            for es in concept.editions
                            if es.status == "renamed"
                        ),
                    ),
                )

        return warnings

    def _check_known_conflicts(
        self,
        query: str,
        hits: list[SearchHit],
    ) -> list[TemporalWarning]:
        """사전 정의된 알려진 충돌을 매칭한다."""
        if not self._known_conflicts or not query:
            return []

        query_lower = query.lower()
        hit_editions = {h.edition_id for h in hits}
        warnings: list[TemporalWarning] = []

        for kc in self._known_conflicts:
            # 개념명이 질의에 포함되어 있는지 확인
            if (
                kc.concept.lower() not in query_lower
                and kc.concept_id not in query_lower
            ):
                continue

            # 검색 결과에 해당 개정판이 2개 이상 포함되어 있는지 확인
            overlap = hit_editions & set(kc.editions)
            if len(overlap) >= 2:
                warnings.append(
                    TemporalWarning(
                        rule_id="TC-001",
                        severity="high",
                        concept=kc.concept,
                        message=(f"'{kc.concept}'은(는) 알려진 시간축 충돌 사례입니다. " f"{kc.note}"),
                        editions=kc.editions,
                    ),
                )

        return warnings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_year(edition_hint: str) -> int | None:
    """개정판 힌트에서 연도를 추출한다."""
    import re

    # "2020-14차" → 2020
    match = re.match(r"(\d{4})", edition_hint)
    if match:
        return int(match.group(1))

    # "14차" → 매핑
    match = re.match(r"(\d{1,2})차", edition_hint)
    if match:
        num = int(match.group(1))
        year_map = {
            0: 1979,
            1: 1981,
            10: 1998,
            11: 2004,
            12: 2008,
            13: 2016,
            14: 2020,
        }
        return year_map.get(num)

    # "초판" → 1979
    if "초판" in edition_hint:
        return 1979

    return None
