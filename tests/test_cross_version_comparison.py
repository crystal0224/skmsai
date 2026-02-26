"""CrossVersionComparisonService 테스트.

PR-025: 개정판 간 비교 서비스 단위/통합 테스트.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.concept_timeline import (  # noqa: E402
    ConceptInfo,
    ConceptTimeline,
    EditionStatus,
)
from scripts.lib.cross_version_comparison import (  # noqa: E402
    EDITION_ORDER,
    ComparisonConfig,
    ComparisonContext,
    CrossVersionComparisonService,
    EditionGroup,
    _edition_sort_key,
    _group_by_edition,
    _lookup_evolution,
)
from scripts.lib.search_types import SearchHit  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hit(
    quote_id: str,
    text: str,
    edition_id: str = "2020-14차",
    year: int = 2020,
    quote_type: str = "narrative",
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


def _make_timeline() -> ConceptTimeline:
    """테스트용 ConceptTimeline 생성."""
    return ConceptTimeline.from_dict(
        {
            "editions_metadata": [
                {"edition_id": "1979-초판", "year": 1979},
                {"edition_id": "2020-14차", "year": 2020},
            ],
            "concepts": [
                {
                    "concept_id": "supex",
                    "name_ko": "SUPEX 추구",
                    "name_en": "SUPEX Pursuit",
                    "category": "supex",
                    "first_edition": "1979-초판",
                    "last_edition": None,
                    "description": "Super Excellent 수준 추구",
                    "editions": {
                        "1979-초판": {"status": "introduced", "note": "최초 도입"},
                        "2020-14차": {"status": "modified", "note": "VWBE 문화 통합"},
                    },
                },
                {
                    "concept_id": "vwbe",
                    "name_ko": "VWBE",
                    "name_en": "Voluntary and Willing Brain Engagement",
                    "category": "modern_value",
                    "first_edition": "2020-14차",
                    "last_edition": None,
                    "description": "자발적 의욕적 두뇌활용",
                    "editions": {
                        "2020-14차": {"status": "introduced", "note": "14차에서 신설"},
                    },
                },
            ],
        }
    )


# ---------------------------------------------------------------------------
# _edition_sort_key 테스트
# ---------------------------------------------------------------------------


class TestEditionSortKey:
    """개정판 정렬 키 테스트."""

    def test_known_edition(self):
        """알려진 개정판."""
        assert _edition_sort_key("1979-초판") == 0
        assert _edition_sort_key("2020-14차") == 14

    def test_unknown_edition(self):
        """알 수 없는 개정판은 99."""
        assert _edition_sort_key("unknown") == 99

    def test_chronological_order(self):
        """시간순 정렬."""
        editions = ["2020-14차", "1979-초판", "1998-10차"]
        sorted_editions = sorted(editions, key=_edition_sort_key)
        assert sorted_editions == ["1979-초판", "1998-10차", "2020-14차"]


# ---------------------------------------------------------------------------
# EditionGroup 테스트
# ---------------------------------------------------------------------------


class TestEditionGroup:
    """EditionGroup 테스트."""

    def test_is_frozen(self):
        """불변이다."""
        g = EditionGroup(
            edition_id="2020-14차",
            year=2020,
            hits=(),
            definition_texts=(),
            narrative_texts=(),
        )
        with pytest.raises(AttributeError):
            g.edition_id = "other"  # type: ignore[misc]

    def test_hit_count(self):
        """검색 결과 수."""
        hits = (_hit("q1", "text1"), _hit("q2", "text2"))
        g = EditionGroup(
            edition_id="2020-14차",
            year=2020,
            hits=hits,
            definition_texts=(),
            narrative_texts=("text1", "text2"),
        )
        assert g.hit_count == 2

    def test_has_definition(self):
        """definition 포함 여부."""
        g1 = EditionGroup(
            edition_id="2020-14차",
            year=2020,
            hits=(),
            definition_texts=("def1",),
            narrative_texts=(),
        )
        assert g1.has_definition is True

        g2 = EditionGroup(
            edition_id="2020-14차",
            year=2020,
            hits=(),
            definition_texts=(),
            narrative_texts=("text1",),
        )
        assert g2.has_definition is False


# ---------------------------------------------------------------------------
# ComparisonContext 테스트
# ---------------------------------------------------------------------------


class TestComparisonContext:
    """ComparisonContext 테스트."""

    def test_is_frozen(self):
        """불변이다."""
        ctx = ComparisonContext(
            query="test",
            edition_groups=(),
            edition_count=0,
            total_hits=0,
            evolution_summary=None,
            concept_name="",
        )
        with pytest.raises(AttributeError):
            ctx.query = "other"  # type: ignore[misc]

    def test_fields(self):
        """필드 접근."""
        ctx = ComparisonContext(
            query="SUPEX 변화",
            edition_groups=(),
            edition_count=2,
            total_hits=5,
            evolution_summary={"name_ko": "SUPEX"},
            concept_name="SUPEX 추구",
        )
        assert ctx.query == "SUPEX 변화"
        assert ctx.edition_count == 2
        assert ctx.concept_name == "SUPEX 추구"


# ---------------------------------------------------------------------------
# ComparisonConfig 테스트
# ---------------------------------------------------------------------------


class TestComparisonConfig:
    """ComparisonConfig 테스트."""

    def test_defaults(self):
        """기본값."""
        cfg = ComparisonConfig()
        assert cfg.max_editions == 0
        assert cfg.include_narratives is True
        assert cfg.max_text_length == 500

    def test_is_frozen(self):
        """불변이다."""
        cfg = ComparisonConfig()
        with pytest.raises(AttributeError):
            cfg.max_editions = 5  # type: ignore[misc]

    def test_from_dict(self):
        """dict에서 생성."""
        cfg = ComparisonConfig.from_dict(
            {"max_editions": 3, "include_narratives": False, "max_text_length": 200}
        )
        assert cfg.max_editions == 3
        assert cfg.include_narratives is False
        assert cfg.max_text_length == 200


# ---------------------------------------------------------------------------
# _group_by_edition 테스트
# ---------------------------------------------------------------------------


class TestGroupByEdition:
    """_group_by_edition 함수 테스트."""

    def test_single_edition(self):
        """단일 개정판."""
        hits = [_hit("q1", "text1"), _hit("q2", "text2")]
        groups = _group_by_edition(hits, 500)
        assert len(groups) == 1
        assert groups[0].edition_id == "2020-14차"
        assert groups[0].hit_count == 2

    def test_multiple_editions(self):
        """여러 개정판."""
        hits = [
            _hit("q1", "초판 텍스트", "1979-초판", 1979),
            _hit("q2", "14차 텍스트", "2020-14차", 2020),
        ]
        groups = _group_by_edition(hits, 500)
        assert len(groups) == 2
        edition_ids = {g.edition_id for g in groups}
        assert edition_ids == {"1979-초판", "2020-14차"}

    def test_definition_vs_narrative(self):
        """definition과 narrative 분리."""
        hits = [
            _hit("q1", "정의 텍스트", quote_type="definition"),
            _hit("q2", "서술 텍스트", quote_type="narrative"),
        ]
        groups = _group_by_edition(hits, 500)
        assert len(groups) == 1
        assert groups[0].definition_texts == ("정의 텍스트",)
        assert groups[0].narrative_texts == ("서술 텍스트",)

    def test_text_truncation(self):
        """긴 텍스트 잘림."""
        long_text = "가" * 600
        hits = [_hit("q1", long_text)]
        groups = _group_by_edition(hits, 100)
        assert len(groups[0].narrative_texts[0]) == 100

    def test_empty_hits(self):
        """빈 검색 결과."""
        groups = _group_by_edition([], 500)
        assert len(groups) == 0


# ---------------------------------------------------------------------------
# _lookup_evolution 테스트
# ---------------------------------------------------------------------------


class TestLookupEvolution:
    """_lookup_evolution 함수 테스트."""

    def test_found(self):
        """개념 매칭 성공."""
        timeline = _make_timeline()
        name, summary = _lookup_evolution("SUPEX 추구", timeline)
        assert name == "SUPEX 추구"
        assert summary is not None
        assert summary["concept_id"] == "supex"

    def test_not_found(self):
        """개념 매칭 실패."""
        timeline = _make_timeline()
        name, summary = _lookup_evolution("존재하지않는개념", timeline)
        assert name == ""
        assert summary is None

    def test_partial_match(self):
        """부분 매칭."""
        timeline = _make_timeline()
        name, summary = _lookup_evolution("VWBE", timeline)
        assert name == "VWBE"
        assert summary is not None


# ---------------------------------------------------------------------------
# CrossVersionComparisonService — 기본 검증
# ---------------------------------------------------------------------------


class TestCrossVersionServiceBasic:
    """기본 검증 테스트."""

    def test_empty_hits(self):
        """빈 검색 결과."""
        svc = CrossVersionComparisonService()
        ctx = svc.build_comparison("SUPEX 변화", [])
        assert ctx.edition_count == 0
        assert ctx.total_hits == 0
        assert ctx.edition_groups == ()

    def test_single_edition_hits(self):
        """단일 개정판 결과."""
        svc = CrossVersionComparisonService()
        hits = [_hit("q1", "SUPEX 정의", "2020-14차", 2020, "definition")]
        ctx = svc.build_comparison("SUPEX", hits)
        assert ctx.edition_count == 1
        assert ctx.edition_groups[0].edition_id == "2020-14차"

    def test_multi_edition_hits(self):
        """여러 개정판 결과 (시간순 정렬)."""
        svc = CrossVersionComparisonService()
        hits = [
            _hit("q1", "14차 정의", "2020-14차", 2020, "definition"),
            _hit("q2", "초판 정의", "1979-초판", 1979, "definition"),
            _hit("q3", "10차 서술", "1998-10차", 1998),
        ]
        ctx = svc.build_comparison("SUPEX 변화", hits)
        assert ctx.edition_count == 3
        # 시간순 정렬 확인
        assert ctx.edition_groups[0].edition_id == "1979-초판"
        assert ctx.edition_groups[1].edition_id == "1998-10차"
        assert ctx.edition_groups[2].edition_id == "2020-14차"

    def test_max_editions_limit(self):
        """max_editions 제한."""
        cfg = ComparisonConfig(max_editions=2)
        svc = CrossVersionComparisonService(config=cfg)
        hits = [
            _hit("q1", "초판", "1979-초판", 1979),
            _hit("q2", "10차", "1998-10차", 1998),
            _hit("q3", "14차", "2020-14차", 2020),
        ]
        ctx = svc.build_comparison("query", hits)
        assert ctx.edition_count == 2
        # 시간순으로 먼저 2개
        assert ctx.edition_groups[0].edition_id == "1979-초판"
        assert ctx.edition_groups[1].edition_id == "1998-10차"


# ---------------------------------------------------------------------------
# CrossVersionComparisonService — ConceptTimeline 통합
# ---------------------------------------------------------------------------


class TestCrossVersionWithTimeline:
    """ConceptTimeline 통합 테스트."""

    def test_evolution_summary_integrated(self):
        """진화 요약 통합."""
        timeline = _make_timeline()
        svc = CrossVersionComparisonService(concept_timeline=timeline)
        hits = [
            _hit("q1", "초판 SUPEX", "1979-초판", 1979),
            _hit("q2", "14차 SUPEX", "2020-14차", 2020),
        ]
        ctx = svc.build_comparison("SUPEX 추구", hits)
        assert ctx.concept_name == "SUPEX 추구"
        assert ctx.evolution_summary is not None
        assert ctx.evolution_summary["concept_id"] == "supex"
        assert ctx.evolution_summary["modified_count"] == 1

    def test_no_timeline(self):
        """타임라인 없으면 진화 요약 없음."""
        svc = CrossVersionComparisonService()
        hits = [_hit("q1", "text")]
        ctx = svc.build_comparison("SUPEX", hits)
        assert ctx.evolution_summary is None
        assert ctx.concept_name == ""

    def test_concept_not_in_timeline(self):
        """타임라인에 없는 개념."""
        timeline = _make_timeline()
        svc = CrossVersionComparisonService(concept_timeline=timeline)
        hits = [_hit("q1", "text")]
        ctx = svc.build_comparison("알수없는개념", hits)
        assert ctx.evolution_summary is None


# ---------------------------------------------------------------------------
# CrossVersionComparisonService — format_comparison_prompt
# ---------------------------------------------------------------------------


class TestFormatComparisonPrompt:
    """format_comparison_prompt 테스트."""

    def test_empty_context(self):
        """빈 컨텍스트."""
        svc = CrossVersionComparisonService()
        ctx = ComparisonContext(
            query="test",
            edition_groups=(),
            edition_count=0,
            total_hits=0,
            evolution_summary=None,
            concept_name="",
        )
        result = svc.format_comparison_prompt(ctx)
        assert result == "[비교 대상 없음]"

    def test_basic_format(self):
        """기본 포맷."""
        svc = CrossVersionComparisonService()
        hits = [
            _hit("q1", "초판에서의 정의", "1979-초판", 1979, "definition"),
            _hit("q2", "14차에서의 정의", "2020-14차", 2020, "definition"),
        ]
        ctx = svc.build_comparison("SUPEX", hits)
        prompt = svc.format_comparison_prompt(ctx)

        assert "[CROSS-VERSION COMPARISON]" in prompt
        assert "query: SUPEX" in prompt
        assert "editions_compared: 2" in prompt
        assert "[EDITION: 1979-초판 (1979)]" in prompt
        assert "[EDITION: 2020-14차 (2020)]" in prompt
        assert "[정의 1]" in prompt

    def test_with_evolution_summary(self):
        """진화 요약 포함."""
        timeline = _make_timeline()
        svc = CrossVersionComparisonService(concept_timeline=timeline)
        hits = [
            _hit("q1", "초판", "1979-초판", 1979),
            _hit("q2", "14차", "2020-14차", 2020),
        ]
        ctx = svc.build_comparison("SUPEX 추구", hits)
        prompt = svc.format_comparison_prompt(ctx)

        assert "[EVOLUTION SUMMARY]" in prompt
        assert "concept: SUPEX 추구 (SUPEX Pursuit)" in prompt
        assert "active: True" in prompt
        assert "modified_count: 1" in prompt

    def test_narratives_excluded(self):
        """narrative 제외."""
        cfg = ComparisonConfig(include_narratives=False)
        svc = CrossVersionComparisonService(config=cfg)
        hits = [
            _hit("q1", "정의 텍스트", quote_type="definition"),
            _hit("q2", "서술 텍스트", quote_type="narrative"),
        ]
        ctx = svc.build_comparison("query", hits)
        prompt = svc.format_comparison_prompt(ctx)

        assert "[정의 1]" in prompt
        assert "[서술 1]" not in prompt

    def test_narratives_included(self):
        """narrative 포함 (기본)."""
        svc = CrossVersionComparisonService()
        hits = [_hit("q1", "서술 텍스트", quote_type="narrative")]
        ctx = svc.build_comparison("query", hits)
        prompt = svc.format_comparison_prompt(ctx)

        assert "[서술 1]" in prompt

    def test_no_content_message(self):
        """정의/서술 모두 없는 경우."""
        svc = CrossVersionComparisonService()
        # 빈 그룹을 직접 만들어서 테스트
        group = EditionGroup(
            edition_id="2020-14차",
            year=2020,
            hits=(),
            definition_texts=(),
            narrative_texts=(),
        )
        ctx = ComparisonContext(
            query="test",
            edition_groups=(group,),
            edition_count=1,
            total_hits=0,
            evolution_summary=None,
            concept_name="",
        )
        prompt = svc.format_comparison_prompt(ctx)
        assert "(해당 개정판에 관련 인용 없음)" in prompt


# ---------------------------------------------------------------------------
# EDITION_ORDER 테스트
# ---------------------------------------------------------------------------


class TestEditionOrder:
    """EDITION_ORDER 상수 테스트."""

    def test_all_15_editions(self):
        """15개 개정판 (초판 + 14차)."""
        assert len(EDITION_ORDER) == 15

    def test_초판_is_first(self):
        """초판은 0."""
        assert EDITION_ORDER["1979-초판"] == 0

    def test_14차_is_last(self):
        """14차는 14."""
        assert EDITION_ORDER["2020-14차"] == 14


# ---------------------------------------------------------------------------
# 통합 테스트
# ---------------------------------------------------------------------------


class TestCrossVersionIntegration:
    """통합 테스트."""

    def test_full_pipeline(self):
        """전체 파이프라인 테스트."""
        timeline = _make_timeline()
        svc = CrossVersionComparisonService(concept_timeline=timeline)

        hits = [
            _hit(
                "q1", "SUPEX는 Super Excellent 수준을 의미한다", "1979-초판", 1979, "definition"
            ),
            _hit(
                "q2", "SUPEX 추구는 인간의 능력으로 도달할 수 있는 최고 수준", "1998-10차", 1998, "narrative"
            ),
            _hit(
                "q3",
                "SUPEX 추구는 VWBE 문화와 결합하여 더 높은 성과를 달성",
                "2020-14차",
                2020,
                "definition",
            ),
        ]

        ctx = svc.build_comparison("SUPEX 추구", hits)
        assert ctx.edition_count == 3
        assert ctx.concept_name == "SUPEX 추구"
        assert ctx.evolution_summary is not None

        prompt = svc.format_comparison_prompt(ctx)
        assert "[CROSS-VERSION COMPARISON]" in prompt
        assert "[EVOLUTION SUMMARY]" in prompt
        assert "1979-초판" in prompt
        assert "1998-10차" in prompt
        assert "2020-14차" in prompt

    def test_config_max_editions_with_timeline(self):
        """max_editions + timeline 통합."""
        timeline = _make_timeline()
        cfg = ComparisonConfig(max_editions=2)
        svc = CrossVersionComparisonService(config=cfg, concept_timeline=timeline)

        hits = [
            _hit("q1", "초판", "1979-초판", 1979),
            _hit("q2", "10차", "1998-10차", 1998),
            _hit("q3", "14차", "2020-14차", 2020),
        ]

        ctx = svc.build_comparison("SUPEX 추구", hits)
        assert ctx.edition_count == 2
        assert ctx.total_hits == 3  # 전체 hits는 유지
        assert ctx.concept_name == "SUPEX 추구"

    def test_multiple_hits_same_edition(self):
        """같은 개정판 여러 결과."""
        svc = CrossVersionComparisonService()
        hits = [
            _hit("q1", "정의1", "2020-14차", 2020, "definition"),
            _hit("q2", "정의2", "2020-14차", 2020, "definition"),
            _hit("q3", "서술1", "2020-14차", 2020, "narrative"),
        ]
        ctx = svc.build_comparison("query", hits)
        assert ctx.edition_count == 1
        assert ctx.edition_groups[0].hit_count == 3
        assert len(ctx.edition_groups[0].definition_texts) == 2
        assert len(ctx.edition_groups[0].narrative_texts) == 1
