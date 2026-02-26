"""ConceptTimeline — 개념별 시계열 추적 서비스.

PR-018: SKMS 핵심 개념의 개정판별 도입/변경/폐지 이력을 추적한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 유효한 상태 값
VALID_STATUSES = frozenset(
    {"introduced", "maintained", "modified", "renamed", "removed"}
)

# 유효한 카테고리
VALID_CATEGORIES = frozenset(
    {
        "core_philosophy",
        "management_principle",
        "supex",
        "dynamic_element",
        "static_element",
        "modern_value",
    }
)


@dataclass(frozen=True)
class EditionStatus:
    """특정 개정판에서의 개념 상태 (불변)."""

    edition_id: str
    year: int
    status: str
    note: str


@dataclass(frozen=True)
class ConceptInfo:
    """단일 개념 정보 (불변)."""

    concept_id: str
    name_ko: str
    name_en: str
    category: str
    first_edition: str
    last_edition: str | None
    description: str
    editions: tuple[EditionStatus, ...]

    @property
    def is_active(self) -> bool:
        """현재 활성 개념인지 여부."""
        return self.last_edition is None

    @property
    def edition_count(self) -> int:
        """등장한 개정판 수."""
        return len(self.editions)

    @property
    def year_range(self) -> tuple[int, int | None]:
        """등장 연도 범위 (시작, 끝)."""
        if not self.editions:
            return (0, None)
        first_year = self.editions[0].year
        last_year = self.editions[-1].year if self.last_edition else None
        return (first_year, last_year)


@dataclass(frozen=True)
class ConceptTimeline:
    """개념별 시계열 추적 서비스 (불변).

    YAML 기반 개념-개정판 매핑을 로드하고 쿼리한다.
    """

    concepts: tuple[ConceptInfo, ...]
    _id_index: dict[str, int]
    _category_index: dict[str, tuple[int, ...]]
    _edition_index: dict[str, tuple[int, ...]]

    @classmethod
    def from_yaml(cls, path: Path) -> ConceptTimeline:
        """YAML 파일에서 개념 타임라인을 로드한다."""
        import yaml

        if not path.exists():
            logger.warning("개념 타임라인 파일 없음: %s", path)
            return cls.empty()

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConceptTimeline:
        """dict에서 개념 타임라인을 생성한다."""
        editions_meta = {
            e["edition_id"]: e["year"] for e in data.get("editions_metadata", [])
        }

        raw_concepts = data.get("concepts", [])
        concepts: list[ConceptInfo] = []
        id_index: dict[str, int] = {}
        category_index: dict[str, list[int]] = {}
        edition_index: dict[str, list[int]] = {}

        for i, raw in enumerate(raw_concepts):
            concept = _parse_concept(raw, editions_meta)
            concepts.append(concept)
            id_index[concept.concept_id] = i

            # 카테고리 인덱스
            cat_list = category_index.setdefault(concept.category, [])
            cat_list.append(i)

            # 개정판 인덱스
            for es in concept.editions:
                ed_list = edition_index.setdefault(es.edition_id, [])
                ed_list.append(i)

        return cls(
            concepts=tuple(concepts),
            _id_index=id_index,
            _category_index={k: tuple(v) for k, v in category_index.items()},
            _edition_index={k: tuple(v) for k, v in edition_index.items()},
        )

    @classmethod
    def empty(cls) -> ConceptTimeline:
        """빈 ConceptTimeline을 생성한다."""
        return cls(
            concepts=(),
            _id_index={},
            _category_index={},
            _edition_index={},
        )

    @property
    def concept_count(self) -> int:
        """등록된 개념 수."""
        return len(self.concepts)

    @property
    def categories(self) -> tuple[str, ...]:
        """등록된 카테고리 목록."""
        return tuple(sorted(self._category_index.keys()))

    def get_concept(self, concept_id: str) -> ConceptInfo | None:
        """개념 ID로 조회한다."""
        idx = self._id_index.get(concept_id)
        if idx is None:
            return None
        return self.concepts[idx]

    def get_by_category(self, category: str) -> tuple[ConceptInfo, ...]:
        """카테고리별 개념 목록."""
        indices = self._category_index.get(category, ())
        return tuple(self.concepts[i] for i in indices)

    def get_by_edition(self, edition_id: str) -> tuple[ConceptInfo, ...]:
        """특정 개정판에 등장하는 개념 목록."""
        indices = self._edition_index.get(edition_id, ())
        return tuple(self.concepts[i] for i in indices)

    def get_active_concepts(self) -> tuple[ConceptInfo, ...]:
        """현재 활성 개념 목록 (last_edition=null)."""
        return tuple(c for c in self.concepts if c.is_active)

    def get_concept_status(
        self, concept_id: str, edition_id: str
    ) -> EditionStatus | None:
        """특정 개정판에서의 개념 상태."""
        concept = self.get_concept(concept_id)
        if concept is None:
            return None
        for es in concept.editions:
            if es.edition_id == edition_id:
                return es
        return None

    def search_concepts(self, query: str) -> tuple[ConceptInfo, ...]:
        """개념 이름(한/영)으로 검색한다."""
        query_lower = query.lower()
        return tuple(
            c
            for c in self.concepts
            if query_lower in c.name_ko.lower()
            or query_lower in c.name_en.lower()
            or query_lower in c.concept_id.lower()
        )

    def get_evolution_summary(self, concept_id: str) -> dict[str, Any] | None:
        """개념의 진화 요약을 반환한다."""
        concept = self.get_concept(concept_id)
        if concept is None:
            return None

        introduced_count = sum(1 for e in concept.editions if e.status == "introduced")
        modified_count = sum(1 for e in concept.editions if e.status == "modified")
        renamed_count = sum(1 for e in concept.editions if e.status == "renamed")

        return {
            "concept_id": concept.concept_id,
            "name_ko": concept.name_ko,
            "name_en": concept.name_en,
            "category": concept.category,
            "is_active": concept.is_active,
            "first_edition": concept.first_edition,
            "last_edition": concept.last_edition,
            "edition_count": concept.edition_count,
            "introduced_count": introduced_count,
            "modified_count": modified_count,
            "renamed_count": renamed_count,
            "editions": [
                {
                    "edition_id": e.edition_id,
                    "year": e.year,
                    "status": e.status,
                    "note": e.note,
                }
                for e in concept.editions
            ],
        }


def _parse_concept(raw: dict[str, Any], editions_meta: dict[str, int]) -> ConceptInfo:
    """raw dict를 ConceptInfo로 변환한다."""
    concept_id = raw.get("concept_id", "")
    editions_raw = raw.get("editions", {})

    edition_statuses: list[EditionStatus] = []

    # 개정판을 연도순으로 정렬
    sorted_editions = sorted(
        editions_raw.items(),
        key=lambda x: editions_meta.get(x[0], 9999),
    )

    for edition_id, info in sorted_editions:
        if isinstance(info, dict):
            status = info.get("status", "maintained")
            note = info.get("note", "")
        else:
            status = "maintained"
            note = ""

        year = editions_meta.get(edition_id, 0)
        edition_statuses.append(
            EditionStatus(
                edition_id=edition_id,
                year=year,
                status=status,
                note=note,
            )
        )

    return ConceptInfo(
        concept_id=concept_id,
        name_ko=raw.get("name_ko", ""),
        name_en=raw.get("name_en", ""),
        category=raw.get("category", ""),
        first_edition=raw.get("first_edition", ""),
        last_edition=raw.get("last_edition"),
        description=raw.get("description", ""),
        editions=tuple(edition_statuses),
    )
