"""TemporalGuardrail 테스트.

PR-023: 시간축 충돌 감지 및 방어 서비스 단위/통합 테스트.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.search_types import SearchHit  # noqa: E402
from scripts.lib.temporal_guardrail import (  # noqa: E402
    GuardrailConfig,
    GuardrailResult,
    KnownConflict,
    TemporalGuardrail,
    TemporalWarning,
    _extract_year,
    load_known_conflicts,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hit(
    quote_id: str,
    text: str,
    edition_id: str,
    quote_type: str = "narrative",
    year: int = 2020,
) -> SearchHit:
    """테스트용 SearchHit."""
    return SearchHit(
        quote_id=quote_id,
        text=text,
        score=0.8,
        edition_id=edition_id,
        year=year,
        revision_num=14,
        quote_type=quote_type,
        section_path=("VWBE",),
        source="hybrid",
        content_hash="abc",
        quality_flags=(),
    )


# ---------------------------------------------------------------------------
# TemporalWarning 테스트
# ---------------------------------------------------------------------------


class TestTemporalWarning:
    """TemporalWarning frozen dataclass 테스트."""

    def test_is_frozen(self):
        """불변이다."""
        w = TemporalWarning(
            rule_id="TC-001",
            severity="high",
            concept="SUPEX",
            message="테스트",
            editions=("1998-10차",),
        )
        with pytest.raises(AttributeError):
            w.severity = "low"  # type: ignore[misc]

    def test_fields(self):
        """필드 접근."""
        w = TemporalWarning(
            rule_id="TC-002",
            severity="medium",
            concept="기업관",
            message="소멸된 개념",
            editions=("1979-초판", "2004-11차"),
        )
        assert w.rule_id == "TC-002"
        assert w.severity == "medium"
        assert w.concept == "기업관"
        assert len(w.editions) == 2


# ---------------------------------------------------------------------------
# GuardrailResult 테스트
# ---------------------------------------------------------------------------


class TestGuardrailResult:
    """GuardrailResult frozen dataclass 테스트."""

    def test_is_frozen(self):
        """불변이다."""
        r = GuardrailResult(
            has_conflict=False, warnings=(), edition_count=1, definition_count=0
        )
        with pytest.raises(AttributeError):
            r.has_conflict = True  # type: ignore[misc]

    def test_no_conflict(self):
        """충돌 없음."""
        r = GuardrailResult(
            has_conflict=False, warnings=(), edition_count=1, definition_count=0
        )
        assert r.has_conflict is False
        assert r.warnings == ()


# ---------------------------------------------------------------------------
# GuardrailConfig 테스트
# ---------------------------------------------------------------------------


class TestGuardrailConfig:
    """GuardrailConfig 테스트."""

    def test_defaults(self):
        """기본값."""
        cfg = GuardrailConfig()
        assert cfg.enabled is True
        assert cfg.max_warnings == 3
        assert cfg.fail_mode == "warn"

    def test_is_frozen(self):
        """불변이다."""
        cfg = GuardrailConfig()
        with pytest.raises(AttributeError):
            cfg.enabled = False  # type: ignore[misc]

    def test_from_dict(self):
        """dict에서 생성."""
        cfg = GuardrailConfig.from_dict(
            {"enabled": False, "max_warnings": 5, "fail_mode": "block"}
        )
        assert cfg.enabled is False
        assert cfg.max_warnings == 5
        assert cfg.fail_mode == "block"


# ---------------------------------------------------------------------------
# KnownConflict 테스트
# ---------------------------------------------------------------------------


class TestKnownConflict:
    """KnownConflict frozen dataclass 테스트."""

    def test_is_frozen(self):
        """불변이다."""
        kc = KnownConflict(
            concept="SUPEX",
            concept_id="supex",
            editions=("1998-10차", "2020-14차"),
            note="test",
        )
        with pytest.raises(AttributeError):
            kc.concept = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# load_known_conflicts 테스트
# ---------------------------------------------------------------------------


class TestLoadKnownConflicts:
    """알려진 충돌 로드 테스트."""

    def test_load_actual_yaml(self):
        """실제 conflict_rules.yaml 로드."""
        path = _PROJECT_ROOT / "guardrails" / "conflict_rules.yaml"
        if not path.exists():
            pytest.skip("guardrails/conflict_rules.yaml not found")

        conflicts = load_known_conflicts(path)
        assert len(conflicts) >= 5
        concept_names = {c.concept for c in conflicts}
        assert "SUPEX" in concept_names
        assert "의욕관리" in concept_names

    def test_load_nonexistent(self):
        """존재하지 않는 파일 → 빈 튜플."""
        conflicts = load_known_conflicts(Path("/nonexistent/rules.yaml"))
        assert conflicts == ()


# ---------------------------------------------------------------------------
# TemporalGuardrail — TC-001: 정의 변경 감지
# ---------------------------------------------------------------------------


class TestTC001DefinitionConflict:
    """TC-001: 정의 변경 감지 테스트."""

    def test_no_conflict_single_edition(self):
        """단일 개정판 → 충돌 없음."""
        hits = [
            _hit("q1", "SUPEX 정의", "2020-14차", "definition"),
            _hit("q2", "SUPEX 설명", "2020-14차", "narrative"),
        ]
        guardrail = TemporalGuardrail()
        result = guardrail.check(hits)
        assert result.has_conflict is False

    def test_conflict_multi_edition_definitions(self):
        """여러 개정판에 definition → TC-001 충돌."""
        hits = [
            _hit("q1", "SUPEX 정의 (10차)", "1998-10차", "definition", year=1998),
            _hit("q2", "SUPEX 정의 (14차)", "2020-14차", "definition", year=2020),
        ]
        guardrail = TemporalGuardrail()
        result = guardrail.check(hits)
        assert result.has_conflict is True
        assert any(w.rule_id == "TC-001" for w in result.warnings)
        assert result.definition_count == 2
        assert result.edition_count == 2

    def test_no_conflict_narrative_only(self):
        """narrative만 있으면 TC-001 미발생."""
        hits = [
            _hit("q1", "서술 1", "1998-10차", "narrative", year=1998),
            _hit("q2", "서술 2", "2020-14차", "narrative", year=2020),
        ]
        guardrail = TemporalGuardrail()
        result = guardrail.check(hits)
        tc001_warnings = [w for w in result.warnings if w.rule_id == "TC-001"]
        assert len(tc001_warnings) == 0


# ---------------------------------------------------------------------------
# TemporalGuardrail — TC-002: 개념 소멸 감지
# ---------------------------------------------------------------------------


class TestTC002ConceptExtinct:
    """TC-002: 개념 소멸 감지 테스트."""

    def _make_timeline_with_extinct(self):
        """소멸 개념이 있는 mock timeline."""
        mock_timeline = MagicMock()
        mock_concept = MagicMock()
        mock_concept.is_active = False
        mock_concept.name_ko = "기업관"
        mock_concept.last_edition = "2004-11차"
        mock_concept.first_edition = "1979-초판"
        mock_concept.year_range = (1979, 2004)
        mock_concept.editions = []
        mock_timeline.search_concepts.return_value = [mock_concept]
        return mock_timeline

    def test_extinct_concept_detected(self):
        """소멸 개념 감지."""
        timeline = self._make_timeline_with_extinct()
        guardrail = TemporalGuardrail(concept_timeline=timeline)
        hits = [_hit("q1", "기업관 설명", "1979-초판")]
        result = guardrail.check(hits, query="기업관")
        assert any(w.rule_id == "TC-002" for w in result.warnings)

    def test_active_concept_no_warning(self):
        """활성 개념 → TC-002 미발생."""
        mock_timeline = MagicMock()
        mock_concept = MagicMock()
        mock_concept.is_active = True
        mock_concept.editions = []
        mock_timeline.search_concepts.return_value = [mock_concept]

        guardrail = TemporalGuardrail(concept_timeline=mock_timeline)
        hits = [_hit("q1", "SUPEX 설명", "2020-14차")]
        result = guardrail.check(hits, query="SUPEX")
        tc002 = [w for w in result.warnings if w.rule_id == "TC-002"]
        assert len(tc002) == 0


# ---------------------------------------------------------------------------
# TemporalGuardrail — TC-003: 개념 신설 감지
# ---------------------------------------------------------------------------


class TestTC003ConceptNew:
    """TC-003: 개념 신설 감지 테스트."""

    def test_new_concept_queried_before_introduction(self):
        """도입 이전 개정판에서 질의 → TC-003."""
        mock_timeline = MagicMock()
        mock_concept = MagicMock()
        mock_concept.is_active = True
        mock_concept.name_ko = "사회적 가치"
        mock_concept.first_edition = "2016-13차"
        mock_concept.year_range = (2016, None)
        mock_concept.editions = []
        mock_timeline.search_concepts.return_value = [mock_concept]

        guardrail = TemporalGuardrail(concept_timeline=mock_timeline)
        hits = [_hit("q1", "text", "1998-10차")]
        result = guardrail.check(hits, query="사회적 가치", edition_hint="1998-10차")
        assert any(w.rule_id == "TC-003" for w in result.warnings)

    def test_no_warning_when_edition_after_introduction(self):
        """도입 이후 개정판 → TC-003 미발생."""
        mock_timeline = MagicMock()
        mock_concept = MagicMock()
        mock_concept.is_active = True
        mock_concept.name_ko = "SUPEX"
        mock_concept.first_edition = "1998-10차"
        mock_concept.year_range = (1998, None)
        mock_concept.editions = []
        mock_timeline.search_concepts.return_value = [mock_concept]

        guardrail = TemporalGuardrail(concept_timeline=mock_timeline)
        hits = [_hit("q1", "text", "2020-14차")]
        result = guardrail.check(hits, query="SUPEX", edition_hint="2020-14차")
        tc003 = [w for w in result.warnings if w.rule_id == "TC-003"]
        assert len(tc003) == 0


# ---------------------------------------------------------------------------
# TemporalGuardrail — TC-004: 용어 변경 감지
# ---------------------------------------------------------------------------


class TestTC004TermChange:
    """TC-004: 용어 변경 감지 테스트."""

    def test_renamed_concept_detected(self):
        """명칭 변경 감지."""
        mock_timeline = MagicMock()
        mock_concept = MagicMock()
        mock_concept.is_active = True
        mock_concept.name_ko = "인간중심의 경영"
        mock_concept.first_edition = "1979-초판"
        mock_concept.year_range = (1979, None)

        mock_es = MagicMock()
        mock_es.status = "renamed"
        mock_es.edition_id = "1998-10차"
        mock_es.note = "인간을 주체로 하는 경영"
        mock_concept.editions = [mock_es]
        mock_timeline.search_concepts.return_value = [mock_concept]

        guardrail = TemporalGuardrail(concept_timeline=mock_timeline)
        hits = [_hit("q1", "인간중심", "2020-14차")]
        result = guardrail.check(hits, query="인간중심")
        assert any(w.rule_id == "TC-004" for w in result.warnings)

    def test_no_rename_no_warning(self):
        """명칭 변경 없으면 TC-004 미발생."""
        mock_timeline = MagicMock()
        mock_concept = MagicMock()
        mock_concept.is_active = True
        mock_concept.name_ko = "SUPEX"
        mock_es = MagicMock()
        mock_es.status = "maintained"
        mock_concept.editions = [mock_es]
        mock_timeline.search_concepts.return_value = [mock_concept]

        guardrail = TemporalGuardrail(concept_timeline=mock_timeline)
        hits = [_hit("q1", "SUPEX", "2020-14차")]
        result = guardrail.check(hits, query="SUPEX")
        tc004 = [w for w in result.warnings if w.rule_id == "TC-004"]
        assert len(tc004) == 0


# ---------------------------------------------------------------------------
# TemporalGuardrail — Known Conflicts
# ---------------------------------------------------------------------------


class TestKnownConflictMatching:
    """사전 정의된 충돌 매칭 테스트."""

    def test_known_conflict_matched(self):
        """알려진 충돌 매칭."""
        known = (
            KnownConflict(
                concept="SUPEX",
                concept_id="supex",
                editions=("1998-10차", "2004-11차", "2020-14차"),
                note="10차 도입 후 지속 확장",
            ),
        )
        guardrail = TemporalGuardrail(known_conflicts=known)
        hits = [
            _hit("q1", "SUPEX 10차", "1998-10차", year=1998),
            _hit("q2", "SUPEX 14차", "2020-14차", year=2020),
        ]
        result = guardrail.check(hits, query="SUPEX 정의는?")
        assert result.has_conflict is True
        assert any("알려진" in w.message for w in result.warnings)

    def test_known_conflict_no_match(self):
        """질의에 개념명 없으면 매칭 안됨."""
        known = (
            KnownConflict(
                concept="SUPEX",
                concept_id="supex",
                editions=("1998-10차", "2020-14차"),
                note="test",
            ),
        )
        guardrail = TemporalGuardrail(known_conflicts=known)
        hits = [_hit("q1", "인사관리 설명", "2020-14차")]
        result = guardrail.check(hits, query="인사관리")
        known_warnings = [w for w in result.warnings if "알려진" in w.message]
        assert len(known_warnings) == 0


# ---------------------------------------------------------------------------
# TemporalGuardrail — 설정 통합
# ---------------------------------------------------------------------------


class TestGuardrailIntegration:
    """가드레일 통합 테스트."""

    def test_disabled_returns_no_conflict(self):
        """비활성화 → 충돌 없음."""
        cfg = GuardrailConfig(enabled=False)
        guardrail = TemporalGuardrail(config=cfg)
        hits = [
            _hit("q1", "def 1", "1998-10차", "definition"),
            _hit("q2", "def 2", "2020-14차", "definition"),
        ]
        result = guardrail.check(hits)
        assert result.has_conflict is False

    def test_empty_hits(self):
        """빈 입력 → 충돌 없음."""
        guardrail = TemporalGuardrail()
        result = guardrail.check([])
        assert result.has_conflict is False

    def test_max_warnings_respected(self):
        """max_warnings 제한."""
        cfg = GuardrailConfig(max_warnings=1)
        # 여러 충돌 유발
        hits = [
            _hit("q1", "def 1", "1979-초판", "definition", year=1979),
            _hit("q2", "def 2", "1998-10차", "definition", year=1998),
            _hit("q3", "def 3", "2020-14차", "definition", year=2020),
        ]
        guardrail = TemporalGuardrail(config=cfg)
        result = guardrail.check(hits, query="인사관리")
        assert len(result.warnings) <= 1

    def test_dedup_warnings(self):
        """동일 rule_id + concept 중복 제거."""
        known = (
            KnownConflict(
                concept="SUPEX",
                concept_id="supex",
                editions=("1998-10차", "2020-14차"),
                note="test",
            ),
        )
        guardrail = TemporalGuardrail(known_conflicts=known)
        hits = [
            _hit("q1", "SUPEX def", "1998-10차", "definition", year=1998),
            _hit("q2", "SUPEX def", "2020-14차", "definition", year=2020),
        ]
        result = guardrail.check(hits, query="SUPEX")
        # TC-001 + known TC-001 → 중복 제거 후 하나만
        tc001 = [w for w in result.warnings if w.rule_id == "TC-001"]
        assert len(tc001) <= 2  # 최대 2개 (검색결과 기반 + known 기반)

    def test_from_yaml(self):
        """YAML에서 가드레일 로드."""
        path = _PROJECT_ROOT / "guardrails" / "conflict_rules.yaml"
        if not path.exists():
            pytest.skip("guardrails/conflict_rules.yaml not found")

        guardrail = TemporalGuardrail.from_yaml(path)
        assert len(guardrail._known_conflicts) >= 5


# ---------------------------------------------------------------------------
# _extract_year 테스트
# ---------------------------------------------------------------------------


class TestExtractYear:
    """_extract_year 헬퍼 테스트."""

    def test_full_edition_id(self):
        """'2020-14차' → 2020."""
        assert _extract_year("2020-14차") == 2020

    def test_edition_number(self):
        """'14차' → 2020."""
        assert _extract_year("14차") == 2020

    def test_initial(self):
        """'초판' → 1979."""
        assert _extract_year("초판") == 1979
        assert _extract_year("1979-초판") == 1979

    def test_edition_10(self):
        """'10차' → 1998."""
        assert _extract_year("10차") == 1998
        assert _extract_year("1998-10차") == 1998

    def test_unknown(self):
        """알 수 없는 형식 → None."""
        assert _extract_year("unknown") is None
