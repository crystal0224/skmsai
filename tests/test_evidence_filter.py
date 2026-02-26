"""EvidenceFilter 테스트.

PR-024: 근거 커버리지 + 환각 탐지 서비스 단위/통합 테스트.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.evidence_filter import (  # noqa: E402
    EvidenceCheckResult,
    EvidenceFilter,
    EvidenceFilterConfig,
    _check_edition_references,
    _compute_coverage,
    _detect_hallucination_indicators,
)
from scripts.lib.search_types import SearchHit  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hit(
    quote_id: str,
    text: str,
    edition_id: str = "2020-14차",
) -> SearchHit:
    """테스트용 SearchHit."""
    return SearchHit(
        quote_id=quote_id,
        text=text,
        score=0.8,
        edition_id=edition_id,
        year=2020,
        revision_num=14,
        quote_type="narrative",
        section_path=("VWBE",),
        source="hybrid",
        content_hash="abc",
        quality_flags=(),
    )


# ---------------------------------------------------------------------------
# EvidenceCheckResult 테스트
# ---------------------------------------------------------------------------


class TestEvidenceCheckResult:
    """EvidenceCheckResult frozen dataclass 테스트."""

    def test_is_frozen(self):
        """불변이다."""
        r = EvidenceCheckResult(
            coverage_score=0.8,
            cited_quote_ids=(),
            valid_quote_ids=(),
            invalid_quote_ids=(),
            cited_editions=(),
            unsupported_editions=(),
            hallucination_flags=(),
            passed=True,
        )
        with pytest.raises(AttributeError):
            r.passed = False  # type: ignore[misc]

    def test_fields(self):
        """필드 접근."""
        r = EvidenceCheckResult(
            coverage_score=0.9,
            cited_quote_ids=("q1",),
            valid_quote_ids=("q1",),
            invalid_quote_ids=(),
            cited_editions=("2020-14차",),
            unsupported_editions=(),
            hallucination_flags=(),
            passed=True,
        )
        assert r.coverage_score == 0.9
        assert r.cited_quote_ids == ("q1",)
        assert r.passed is True


# ---------------------------------------------------------------------------
# EvidenceFilterConfig 테스트
# ---------------------------------------------------------------------------


class TestEvidenceFilterConfig:
    """EvidenceFilterConfig 테스트."""

    def test_defaults(self):
        """기본값."""
        cfg = EvidenceFilterConfig()
        assert cfg.min_coverage == 0.0
        assert cfg.max_invalid_quotes == 0
        assert cfg.check_editions is True
        assert cfg.check_hallucination is True

    def test_is_frozen(self):
        """불변이다."""
        cfg = EvidenceFilterConfig()
        with pytest.raises(AttributeError):
            cfg.min_coverage = 0.5  # type: ignore[misc]

    def test_from_dict(self):
        """dict에서 생성."""
        cfg = EvidenceFilterConfig.from_dict(
            {"min_coverage": 0.3, "max_invalid_quotes": 2}
        )
        assert cfg.min_coverage == 0.3
        assert cfg.max_invalid_quotes == 2


# ---------------------------------------------------------------------------
# EvidenceFilter — 기본 검증
# ---------------------------------------------------------------------------


class TestEvidenceFilterBasic:
    """기본 검증 테스트."""

    def test_empty_answer(self):
        """빈 응답."""
        ef = EvidenceFilter()
        hits = [_hit("q1", "SUPEX 정의")]
        result = ef.check("", hits)
        assert result.passed is True  # 빈 응답은 pass

    def test_empty_hits(self):
        """빈 검색 결과."""
        ef = EvidenceFilter()
        result = ef.check("SUPEX는 Super Excellent입니다", [])
        assert result.passed is False  # 응답 있는데 hits 없으면 fail

    def test_both_empty(self):
        """둘 다 빈 경우."""
        ef = EvidenceFilter()
        result = ef.check("", [])
        assert result.passed is True


# ---------------------------------------------------------------------------
# EvidenceFilter — quote_id 인용 검증
# ---------------------------------------------------------------------------


class TestQuoteIdVerification:
    """quote_id 인용 검증 테스트."""

    def test_valid_quote_id_detected(self):
        """유효한 quote_id가 응답에서 감지된다."""
        hits = [_hit("2020-14차|VWBE|definition|001", "VWBE 정의 텍스트")]
        answer = "VWBE는 자발적 두뇌활용입니다 [2020-14차|VWBE|definition|001]"
        ef = EvidenceFilter()
        result = ef.check(answer, hits)
        assert len(result.valid_quote_ids) == 1
        assert "2020-14차|VWBE|definition|001" in result.valid_quote_ids

    def test_invalid_quote_id_detected(self):
        """무효한 quote_id가 감지된다."""
        hits = [_hit("2020-14차|VWBE|definition|001", "VWBE 정의")]
        answer = "답변입니다 [2020-14차|SUPEX|definition|999]"
        ef = EvidenceFilter()
        result = ef.check(answer, hits)
        assert len(result.invalid_quote_ids) == 1

    def test_no_quote_ids_in_answer(self):
        """응답에 quote_id가 없는 경우."""
        hits = [_hit("2020-14차|VWBE|definition|001", "VWBE 정의")]
        answer = "SUPEX는 Super Excellent 수준을 의미합니다."
        ef = EvidenceFilter()
        result = ef.check(answer, hits)
        assert result.cited_quote_ids == ()

    def test_max_invalid_quotes_fail(self):
        """무효 quote_id 수가 max_invalid_quotes 초과 시 실패."""
        cfg = EvidenceFilterConfig(max_invalid_quotes=0)
        hits = [_hit("2020-14차|VWBE|definition|001", "VWBE")]
        answer = "참조: [2020-14차|FAKE|definition|999]"
        ef = EvidenceFilter(config=cfg)
        result = ef.check(answer, hits)
        assert result.passed is False

    def test_max_invalid_quotes_pass(self):
        """무효 quote_id 수가 허용 범위 내면 통과."""
        cfg = EvidenceFilterConfig(max_invalid_quotes=1)
        hits = [_hit("2020-14차|VWBE|definition|001", "VWBE")]
        answer = "참조: [2020-14차|FAKE|definition|999]"
        ef = EvidenceFilter(config=cfg)
        result = ef.check(answer, hits)
        assert result.passed is True


# ---------------------------------------------------------------------------
# EvidenceFilter — 커버리지 점수
# ---------------------------------------------------------------------------


class TestCoverageScore:
    """커버리지 점수 테스트."""

    def test_high_coverage(self):
        """높은 커버리지."""
        hits = [
            _hit("q1", "SUPEX는 Super Excellent 수준을 의미하며 최고를 추구한다"),
        ]
        answer = "SUPEX는 Super Excellent 수준을 의미합니다. 최고를 추구하는 것이 핵심입니다."
        ef = EvidenceFilter()
        result = ef.check(answer, hits)
        assert result.coverage_score > 0.0

    def test_zero_coverage(self):
        """커버리지 0."""
        hits = [_hit("q1", "ABCDEF 완전히 다른 내용의 텍스트입니다")]
        answer = "가나다라마바사 전혀 관련없는 응답"
        ef = EvidenceFilter()
        result = ef.check(answer, hits)
        assert result.coverage_score == 0.0

    def test_min_coverage_fail(self):
        """최소 커버리지 미달 시 실패."""
        cfg = EvidenceFilterConfig(min_coverage=0.5)
        hits = [_hit("q1", "ABCDEF 완전히 다른 내용")]
        answer = "가나다라마바사 전혀 다른 내용"
        ef = EvidenceFilter(config=cfg)
        result = ef.check(answer, hits)
        assert result.passed is False


# ---------------------------------------------------------------------------
# _compute_coverage 직접 테스트
# ---------------------------------------------------------------------------


class TestComputeCoverage:
    """_compute_coverage 함수 테스트."""

    def test_full_match(self):
        """모든 구문이 포함되면 높은 커버리지."""
        hits = [_hit("q1", "인간중심의 경영은 사람을 중심으로 합니다")]
        # "인간중심의", "경영은", "사람을", "중심으로", "합니다" 등
        answer = "인간중심의 경영은 사람을 중심으로 하는 것이 핵심입니다"
        score = _compute_coverage(answer, hits)
        assert score > 0.0

    def test_empty_hits(self):
        """빈 hits → 0."""
        assert _compute_coverage("답변", []) == 0.0

    def test_no_match(self):
        """매칭 없음 → 0."""
        hits = [_hit("q1", "가나다라마바사 전혀다른단어들의텍스트")]
        score = _compute_coverage("완전히 다른 응답입니다", hits)
        assert score == 0.0


# ---------------------------------------------------------------------------
# _check_edition_references 테스트
# ---------------------------------------------------------------------------


class TestEditionReferences:
    """개정판 참조 검증 테스트."""

    def test_supported_edition(self):
        """검색 결과에 있는 개정판."""
        hit_editions = {"2020-14차"}
        cited, unsupported = _check_edition_references(
            "14차 개정판에서 SUPEX를 정의합니다", hit_editions
        )
        assert len(unsupported) == 0

    def test_unsupported_edition(self):
        """검색 결과에 없는 개정판."""
        hit_editions = {"2020-14차"}
        cited, unsupported = _check_edition_references(
            "10차 개정판에서 처음 도입되었습니다", hit_editions
        )
        assert len(unsupported) > 0

    def test_initial_edition(self):
        """초판 참조."""
        hit_editions = {"1979-초판"}
        cited, unsupported = _check_edition_references(
            "초판에서 인간중심 경영이 정립되었습니다", hit_editions
        )
        assert len(unsupported) == 0

    def test_no_edition_mentioned(self):
        """개정판 언급 없음."""
        hit_editions = {"2020-14차"}
        cited, unsupported = _check_edition_references(
            "SUPEX는 최고 수준을 의미합니다", hit_editions
        )
        assert cited == ()


# ---------------------------------------------------------------------------
# _detect_hallucination_indicators 테스트
# ---------------------------------------------------------------------------


class TestHallucinationDetection:
    """환각 지표 감지 테스트."""

    def test_general_claim(self):
        """일반론 주장 감지."""
        flags = _detect_hallucination_indicators("일반적으로 경영학에서는 이것이 중요한 것으로 알려져 있습니다")
        assert "일반론 주장" in flags

    def test_specific_article(self):
        """구체적 조항 번호 감지."""
        flags = _detect_hallucination_indicators("제3조에 의하면 경영 원칙이 있습니다")
        assert "구체적 조항 번호 (SKMS에 없음)" in flags

    def test_specific_date(self):
        """구체적 날짜 감지."""
        flags = _detect_hallucination_indicators("2020년 2월 15일에 개정이 발표되었습니다")
        assert "구체적 날짜 (환각 가능)" in flags

    def test_percentage(self):
        """백분율 수치 감지."""
        flags = _detect_hallucination_indicators("생산성이 약 30% 향상되었습니다")
        assert "구체적 백분율 수치" in flags

    def test_clean_text(self):
        """환각 지표 없는 깨끗한 텍스트."""
        flags = _detect_hallucination_indicators("SUPEX는 Super Excellent 수준을 의미합니다.")
        assert len(flags) == 0


# ---------------------------------------------------------------------------
# EvidenceFilter — 통합 테스트
# ---------------------------------------------------------------------------


class TestEvidenceFilterIntegration:
    """통합 테스트."""

    def test_clean_answer_passes(self):
        """근거가 있는 깨끗한 응답은 통과."""
        hits = [
            _hit("2020-14차|VWBE|definition|001", "VWBE는 자발적 의욕적 두뇌활용 문화이다"),
        ]
        answer = "VWBE는 자발적 의욕적 두뇌활용 문화입니다. " "[2020-14차|VWBE|definition|001]"
        ef = EvidenceFilter()
        result = ef.check(answer, hits)
        assert result.passed is True
        assert result.coverage_score > 0.0
        assert len(result.valid_quote_ids) == 1

    def test_hallucinated_answer_flagged(self):
        """환각이 있는 응답은 플래그가 붙는다."""
        hits = [_hit("q1", "SUPEX 설명 텍스트")]
        answer = "일반적으로 경영학에서는 이것이 중요한 것으로 알려져 있으며, 약 85%의 기업이 채택합니다."
        ef = EvidenceFilter()
        result = ef.check(answer, hits)
        assert len(result.hallucination_flags) >= 1

    def test_config_disabled_checks(self):
        """검사 비활성화 시 관련 필드가 비어있다."""
        cfg = EvidenceFilterConfig(
            check_editions=False,
            check_hallucination=False,
        )
        hits = [_hit("q1", "SUPEX")]
        answer = "일반적으로 알려져 있으며 10차에서 도입"
        ef = EvidenceFilter(config=cfg)
        result = ef.check(answer, hits)
        assert result.cited_editions == ()
        assert result.hallucination_flags == ()

    def test_multiple_hits_coverage(self):
        """여러 검색 결과에 대한 커버리지."""
        hits = [
            _hit("q1", "인간중심의 경영은 핵심 철학이다", "2020-14차"),
            _hit("q2", "SUPEX 추구는 최고 수준을 달성하기 위한 것이다", "2020-14차"),
        ]
        answer = "인간중심의 경영은 SKMS의 핵심 철학입니다. SUPEX 추구는 최고 수준을 달성하는 것을 목표로 합니다."
        ef = EvidenceFilter()
        result = ef.check(answer, hits)
        assert result.coverage_score > 0.0
        assert result.cited_quote_ids == ()  # q1, q2는 quote_id 패턴이 아님
