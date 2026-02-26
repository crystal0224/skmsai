"""ConceptTimeline 테스트.

PR-018: 개념별 시계열 추적 서비스 단위/통합 테스트.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.concept_timeline import (  # noqa: E402
    VALID_CATEGORIES,
    VALID_STATUSES,
    ConceptInfo,
    ConceptTimeline,
    EditionStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_data() -> dict:
    """테스트용 개념 타임라인 데이터."""
    return {
        "editions_metadata": [
            {"edition_id": "1979-초판", "year": 1979, "label": "초판"},
            {"edition_id": "1981-1차", "year": 1981, "label": "1차"},
            {"edition_id": "1998-10차", "year": 1998, "label": "10차"},
            {"edition_id": "2004-11차", "year": 2004, "label": "11차"},
            {"edition_id": "2020-14차", "year": 2020, "label": "14차"},
        ],
        "concepts": [
            {
                "concept_id": "인간중심경영",
                "name_ko": "인간중심의 경영",
                "name_en": "Human-Centered Management",
                "category": "core_philosophy",
                "first_edition": "1979-초판",
                "last_edition": None,
                "description": "사람 중심 경영",
                "editions": {
                    "1979-초판": {"status": "introduced", "note": "최초 정립"},
                    "1981-1차": {"status": "maintained"},
                    "1998-10차": {
                        "status": "renamed",
                        "note": "인간을 주체로 하는 경영",
                    },
                    "2004-11차": {"status": "maintained"},
                    "2020-14차": {"status": "maintained"},
                },
            },
            {
                "concept_id": "SUPEX",
                "name_ko": "SUPEX (Super Excellent)",
                "name_en": "SUPEX - Super Excellent Level",
                "category": "supex",
                "first_edition": "1998-10차",
                "last_edition": None,
                "description": "최고 수준",
                "editions": {
                    "1998-10차": {"status": "introduced", "note": "SUPEX 도입"},
                    "2004-11차": {
                        "status": "modified",
                        "note": "SUPEX Company 확장",
                    },
                    "2020-14차": {"status": "maintained"},
                },
            },
            {
                "concept_id": "기업관",
                "name_ko": "기업관",
                "name_en": "Corporate Philosophy",
                "category": "core_philosophy",
                "first_edition": "1979-초판",
                "last_edition": "2004-11차",
                "description": "기업의 존재 이유",
                "editions": {
                    "1979-초판": {"status": "introduced"},
                    "1981-1차": {"status": "maintained"},
                    "1998-10차": {"status": "maintained"},
                    "2004-11차": {"status": "maintained", "note": "추구가치로 계승"},
                },
            },
        ],
    }


@pytest.fixture()
def timeline(sample_data) -> ConceptTimeline:
    """테스트용 ConceptTimeline."""
    return ConceptTimeline.from_dict(sample_data)


# ---------------------------------------------------------------------------
# EditionStatus 테스트
# ---------------------------------------------------------------------------


def test_edition_status_is_frozen():
    """EditionStatus는 불변이다."""
    es = EditionStatus(edition_id="1979-초판", year=1979, status="introduced", note="")
    with pytest.raises(AttributeError):
        es.status = "modified"  # type: ignore[misc]


def test_edition_status_fields():
    """EditionStatus 필드 접근."""
    es = EditionStatus(edition_id="2020-14차", year=2020, status="modified", note="변경됨")
    assert es.edition_id == "2020-14차"
    assert es.year == 2020
    assert es.status == "modified"
    assert es.note == "변경됨"


# ---------------------------------------------------------------------------
# ConceptInfo 테스트
# ---------------------------------------------------------------------------


def test_concept_info_is_frozen(timeline):
    """ConceptInfo는 불변이다."""
    concept = timeline.get_concept("인간중심경영")
    assert concept is not None
    with pytest.raises(AttributeError):
        concept.name_ko = "changed"  # type: ignore[misc]


def test_concept_is_active(timeline):
    """활성 개념 확인."""
    active = timeline.get_concept("인간중심경영")
    assert active is not None
    assert active.is_active is True

    inactive = timeline.get_concept("기업관")
    assert inactive is not None
    assert inactive.is_active is False


def test_concept_edition_count(timeline):
    """등장 개정판 수."""
    concept = timeline.get_concept("인간중심경영")
    assert concept is not None
    assert concept.edition_count == 5


def test_concept_year_range(timeline):
    """연도 범위."""
    concept = timeline.get_concept("SUPEX")
    assert concept is not None
    assert concept.year_range == (1998, None)  # still active

    concept2 = timeline.get_concept("기업관")
    assert concept2 is not None
    assert concept2.year_range == (1979, 2004)  # ended in 2004


# ---------------------------------------------------------------------------
# ConceptTimeline.from_dict 테스트
# ---------------------------------------------------------------------------


def test_from_dict_concept_count(timeline):
    """개념 수."""
    assert timeline.concept_count == 3


def test_from_dict_empty():
    """빈 데이터."""
    ct = ConceptTimeline.from_dict({})
    assert ct.concept_count == 0


def test_from_dict_categories(timeline):
    """카테고리 목록."""
    cats = timeline.categories
    assert "core_philosophy" in cats
    assert "supex" in cats


# ---------------------------------------------------------------------------
# ConceptTimeline.empty 테스트
# ---------------------------------------------------------------------------


def test_empty():
    """빈 ConceptTimeline."""
    ct = ConceptTimeline.empty()
    assert ct.concept_count == 0
    assert ct.categories == ()


# ---------------------------------------------------------------------------
# ConceptTimeline.from_yaml 테스트
# ---------------------------------------------------------------------------


def test_from_yaml(tmp_path, sample_data):
    """YAML 파일 로드."""
    import yaml

    path = tmp_path / "concept_timeline.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(sample_data, f, allow_unicode=True)

    ct = ConceptTimeline.from_yaml(path)
    assert ct.concept_count == 3


def test_from_yaml_nonexistent():
    """존재하지 않는 파일은 빈 타임라인."""
    ct = ConceptTimeline.from_yaml(Path("/nonexistent/timeline.yaml"))
    assert ct.concept_count == 0


# ---------------------------------------------------------------------------
# get_concept 테스트
# ---------------------------------------------------------------------------


def test_get_concept(timeline):
    """ID로 개념 조회."""
    concept = timeline.get_concept("SUPEX")
    assert concept is not None
    assert concept.name_ko == "SUPEX (Super Excellent)"


def test_get_concept_not_found(timeline):
    """없는 개념은 None."""
    assert timeline.get_concept("없는개념") is None


# ---------------------------------------------------------------------------
# get_by_category 테스트
# ---------------------------------------------------------------------------


def test_get_by_category(timeline):
    """카테고리별 조회."""
    core = timeline.get_by_category("core_philosophy")
    assert len(core) == 2
    names = {c.concept_id for c in core}
    assert "인간중심경영" in names
    assert "기업관" in names


def test_get_by_category_empty(timeline):
    """없는 카테고리는 빈 튜플."""
    assert timeline.get_by_category("nonexistent") == ()


# ---------------------------------------------------------------------------
# get_by_edition 테스트
# ---------------------------------------------------------------------------


def test_get_by_edition(timeline):
    """개정판별 개념 조회."""
    concepts_1979 = timeline.get_by_edition("1979-초판")
    ids = {c.concept_id for c in concepts_1979}
    assert "인간중심경영" in ids
    assert "기업관" in ids
    assert "SUPEX" not in ids


def test_get_by_edition_2020(timeline):
    """2020 개정판에서 활성 개념만."""
    concepts_2020 = timeline.get_by_edition("2020-14차")
    ids = {c.concept_id for c in concepts_2020}
    assert "인간중심경영" in ids
    assert "SUPEX" in ids
    assert "기업관" not in ids


# ---------------------------------------------------------------------------
# get_active_concepts 테스트
# ---------------------------------------------------------------------------


def test_get_active_concepts(timeline):
    """활성 개념 목록."""
    active = timeline.get_active_concepts()
    ids = {c.concept_id for c in active}
    assert "인간중심경영" in ids
    assert "SUPEX" in ids
    assert "기업관" not in ids  # last_edition="2004-11차"


# ---------------------------------------------------------------------------
# get_concept_status 테스트
# ---------------------------------------------------------------------------


def test_get_concept_status(timeline):
    """특정 개정판에서의 상태."""
    status = timeline.get_concept_status("인간중심경영", "1979-초판")
    assert status is not None
    assert status.status == "introduced"
    assert status.note == "최초 정립"


def test_get_concept_status_renamed(timeline):
    """이름 변경 상태."""
    status = timeline.get_concept_status("인간중심경영", "1998-10차")
    assert status is not None
    assert status.status == "renamed"


def test_get_concept_status_not_in_edition(timeline):
    """해당 개정판에 없는 경우."""
    status = timeline.get_concept_status("SUPEX", "1979-초판")
    assert status is None


def test_get_concept_status_invalid_concept(timeline):
    """없는 개념."""
    assert timeline.get_concept_status("없는개념", "1979-초판") is None


# ---------------------------------------------------------------------------
# search_concepts 테스트
# ---------------------------------------------------------------------------


def test_search_concepts_korean(timeline):
    """한글 검색."""
    results = timeline.search_concepts("인간")
    assert len(results) == 1
    assert results[0].concept_id == "인간중심경영"


def test_search_concepts_english(timeline):
    """영어 검색."""
    results = timeline.search_concepts("SUPEX")
    assert len(results) == 1


def test_search_concepts_case_insensitive(timeline):
    """대소문자 무관."""
    results = timeline.search_concepts("supex")
    assert len(results) == 1


def test_search_concepts_no_match(timeline):
    """매칭 없음."""
    assert timeline.search_concepts("없는용어") == ()


def test_search_concepts_partial(timeline):
    """부분 매칭."""
    results = timeline.search_concepts("경영")
    assert len(results) == 1  # "인간중심의 경영"


# ---------------------------------------------------------------------------
# get_evolution_summary 테스트
# ---------------------------------------------------------------------------


def test_evolution_summary(timeline):
    """진화 요약."""
    summary = timeline.get_evolution_summary("인간중심경영")
    assert summary is not None
    assert summary["concept_id"] == "인간중심경영"
    assert summary["is_active"] is True
    assert summary["edition_count"] == 5
    assert summary["introduced_count"] == 1
    assert summary["renamed_count"] == 1
    assert len(summary["editions"]) == 5


def test_evolution_summary_not_found(timeline):
    """없는 개념."""
    assert timeline.get_evolution_summary("없는개념") is None


# ---------------------------------------------------------------------------
# ConceptTimeline 불변성 테스트
# ---------------------------------------------------------------------------


def test_timeline_is_frozen(timeline):
    """ConceptTimeline은 불변이다."""
    with pytest.raises(AttributeError):
        timeline.concepts = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# editions 정렬 테스트
# ---------------------------------------------------------------------------


def test_editions_sorted_by_year(timeline):
    """개정판이 연도순으로 정렬된다."""
    concept = timeline.get_concept("인간중심경영")
    assert concept is not None
    years = [e.year for e in concept.editions]
    assert years == sorted(years)


# ---------------------------------------------------------------------------
# Constants 테스트
# ---------------------------------------------------------------------------


def test_valid_statuses():
    """유효한 상태 값."""
    assert "introduced" in VALID_STATUSES
    assert "modified" in VALID_STATUSES
    assert "renamed" in VALID_STATUSES
    assert "removed" in VALID_STATUSES
    assert "maintained" in VALID_STATUSES


def test_valid_categories():
    """유효한 카테고리."""
    assert "core_philosophy" in VALID_CATEGORIES
    assert "supex" in VALID_CATEGORIES
    assert "static_element" in VALID_CATEGORIES


# ---------------------------------------------------------------------------
# 실제 concept_timeline.yaml 통합 테스트
# ---------------------------------------------------------------------------


def test_load_actual_yaml():
    """실제 config/concept_timeline.yaml 로드."""
    path = _PROJECT_ROOT / "config" / "concept_timeline.yaml"
    if not path.exists():
        pytest.skip("config/concept_timeline.yaml not found")

    ct = ConceptTimeline.from_yaml(path)
    assert ct.concept_count >= 30


def test_actual_yaml_supex_concept():
    """실제 YAML에서 SUPEX 개념."""
    path = _PROJECT_ROOT / "config" / "concept_timeline.yaml"
    if not path.exists():
        pytest.skip("config/concept_timeline.yaml not found")

    ct = ConceptTimeline.from_yaml(path)
    concept = ct.get_concept("SUPEX")
    assert concept is not None
    assert concept.first_edition == "1995-8차"
    assert concept.is_active is True


def test_actual_yaml_has_all_categories():
    """실제 YAML에 모든 카테고리 존재."""
    path = _PROJECT_ROOT / "config" / "concept_timeline.yaml"
    if not path.exists():
        pytest.skip("config/concept_timeline.yaml not found")

    ct = ConceptTimeline.from_yaml(path)
    cats = set(ct.categories)
    assert "core_philosophy" in cats
    assert "supex" in cats
    assert "static_element" in cats
    assert "dynamic_element" in cats


def test_actual_yaml_active_concepts():
    """실제 YAML에서 활성 개념 존재."""
    path = _PROJECT_ROOT / "config" / "concept_timeline.yaml"
    if not path.exists():
        pytest.skip("config/concept_timeline.yaml not found")

    ct = ConceptTimeline.from_yaml(path)
    active = ct.get_active_concepts()
    assert len(active) >= 5
    active_ids = {c.concept_id for c in active}
    assert "SUPEX" in active_ids
    assert "인간중심경영" in active_ids


def test_actual_yaml_edition_consistency():
    """실제 YAML에서 개정판 상태가 유효한 값만 포함."""
    path = _PROJECT_ROOT / "config" / "concept_timeline.yaml"
    if not path.exists():
        pytest.skip("config/concept_timeline.yaml not found")

    ct = ConceptTimeline.from_yaml(path)
    for concept in ct.concepts:
        for es in concept.editions:
            assert es.status in VALID_STATUSES, (
                f"'{concept.concept_id}' 개정판 '{es.edition_id}'에 "
                f"유효하지 않은 상태: '{es.status}'"
            )
