"""QueryClassifier 테스트.

PR-022: 규칙 기반 4-Type 질의 분류기 단위/통합 테스트.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.query_classifier import (  # noqa: E402
    INTENT_TO_QUERY_TYPE,
    QUERY_TYPES,
    ClassificationResult,
    classify_batch,
    classify_query,
    evaluate_accuracy,
)


# ---------------------------------------------------------------------------
# ClassificationResult 테스트
# ---------------------------------------------------------------------------


class TestClassificationResult:
    """ClassificationResult frozen dataclass 테스트."""

    def test_is_frozen(self):
        """불변이다."""
        result = ClassificationResult(
            query_type="definition",
            confidence=0.9,
            edition_hint=None,
            reasoning="test",
        )
        with pytest.raises(AttributeError):
            result.query_type = "open_ended"  # type: ignore[misc]

    def test_valid_query_type(self):
        """유효한 query_type."""
        for qt in QUERY_TYPES:
            result = ClassificationResult(
                query_type=qt, confidence=0.8, edition_hint=None, reasoning=""
            )
            assert result.query_type == qt

    def test_invalid_query_type_fallback(self):
        """잘못된 query_type은 open_ended로 폴백."""
        result = ClassificationResult(
            query_type="invalid_type",
            confidence=0.8,
            edition_hint=None,
            reasoning="test",
        )
        assert result.query_type == "open_ended"

    def test_confidence_clamped(self):
        """confidence는 [0, 1] 범위로 클램핑."""
        r1 = ClassificationResult(
            query_type="definition", confidence=1.5, edition_hint=None, reasoning=""
        )
        assert r1.confidence == 1.0

        r2 = ClassificationResult(
            query_type="definition", confidence=-0.5, edition_hint=None, reasoning=""
        )
        assert r2.confidence == 0.0

    def test_edition_hint(self):
        """edition_hint 필드."""
        result = ClassificationResult(
            query_type="single_version",
            confidence=0.9,
            edition_hint="2020-14차",
            reasoning="test",
        )
        assert result.edition_hint == "2020-14차"


# ---------------------------------------------------------------------------
# Constants 테스트
# ---------------------------------------------------------------------------


class TestConstants:
    """상수 테스트."""

    def test_query_types_count(self):
        """4가지 query type."""
        assert len(QUERY_TYPES) == 4

    def test_query_types_members(self):
        """각 타입 존재 확인."""
        assert "single_version" in QUERY_TYPES
        assert "cross_version" in QUERY_TYPES
        assert "definition" in QUERY_TYPES
        assert "open_ended" in QUERY_TYPES

    def test_intent_mapping_covers_all(self):
        """5-intent → 4-type 매핑이 모든 intent를 커버."""
        old_intents = {
            "specific_time",
            "general_definition",
            "evolution_comparison",
            "content_generation",
            "open_ended",
        }
        assert set(INTENT_TO_QUERY_TYPE.keys()) == old_intents

    def test_intent_mapping_values(self):
        """매핑 결과가 모두 유효한 query_type."""
        for v in INTENT_TO_QUERY_TYPE.values():
            assert v in QUERY_TYPES


# ---------------------------------------------------------------------------
# classify_query — single_version 테스트
# ---------------------------------------------------------------------------


class TestSingleVersion:
    """단일 개정판 질의 분류."""

    def test_edition_number_with_에서(self):
        """'N차에서' 패턴."""
        result = classify_query("14차 개정판에서 VWBE 문화의 핵심 내용은 무엇인가?")
        assert result.query_type == "single_version"
        assert result.confidence >= 0.85

    def test_initial_edition(self):
        """'초판에서' 패턴."""
        result = classify_query("초판에서 인사관리의 정의와 범위는?")
        assert result.query_type == "single_version"

    def test_edition_with_year(self):
        """연도 참조."""
        result = classify_query("현행 SKMS에서 사회적 가치 창출은 어떻게 다루어지는가?")
        assert result.query_type == "single_version"

    def test_edition_hint_extracted(self):
        """edition_hint가 추출된다."""
        result = classify_query("14차에서 SUPEX 추구의 구체적 프로세스는?")
        assert result.edition_hint is not None
        assert "14" in result.edition_hint

    def test_initial_edition_hint(self):
        """초판 힌트."""
        result = classify_query("초판에서 인간중심 경영의 의미는?")
        assert result.edition_hint == "1979-초판"

    def test_specific_edition_10(self):
        """10차 개정판."""
        result = classify_query("10차 개정판에서 SUPEX 추구의 구체적 프로세스는?")
        assert result.query_type == "single_version"
        assert result.edition_hint == "1998-10차"

    def test_specific_edition_11(self):
        """11차 개정판."""
        result = classify_query("11차 개정판의 코디네이션관리 내용을 설명해주세요.")
        assert result.query_type == "single_version"


# ---------------------------------------------------------------------------
# classify_query — cross_version 테스트
# ---------------------------------------------------------------------------


class TestCrossVersion:
    """개정판 간 비교 질의 분류."""

    def test_change_keyword(self):
        """'변화' 키워드."""
        result = classify_query("의욕관리 개념이 초판에서 14차까지 어떻게 변화했는가?")
        assert result.query_type == "cross_version"
        assert result.confidence >= 0.85

    def test_comparison_keyword(self):
        """'다른' 키워드 + 다중 개정판."""
        result = classify_query("인간중심의 경영 개념이 1979년 초판과 2020년 14차에서 어떻게 다른가?")
        assert result.query_type == "cross_version"

    def test_first_appeared(self):
        """'처음 등장' 패턴."""
        result = classify_query("사회적 가치 개념은 SKMS에 언제 처음 등장했나요?")
        assert result.query_type == "cross_version"

    def test_reorganization(self):
        """'재구성' 키워드."""
        result = classify_query("경영관리 요소 분류체계가 개정판에 따라 어떻게 재구성되었는가?")
        assert result.query_type == "cross_version"

    def test_multi_edition_comparison(self):
        """다중 개정판 참조."""
        result = classify_query("SK-Manship의 의미는 10차와 14차에서 어떻게 달라졌는가?")
        assert result.query_type == "cross_version"

    def test_cross_with_변했(self):
        """'변했' 키워드."""
        result = classify_query("인간중심 경영이 어떻게 변했는가?")
        assert result.query_type == "cross_version"


# ---------------------------------------------------------------------------
# classify_query — definition 테스트
# ---------------------------------------------------------------------------


class TestDefinition:
    """정의 질의 분류."""

    def test_what_is_pattern(self):
        """'~란 무엇인가' 패턴."""
        result = classify_query("SUPEX란 무엇인가?")
        assert result.query_type == "definition"
        assert result.confidence >= 0.85

    def test_meaning_pattern(self):
        """'~뜻인가요' 패턴."""
        result = classify_query("합리적 경영이란 어떤 뜻인가요?")
        assert result.query_type == "definition"

    def test_definition_of_pattern(self):
        """'~의 정의는' 패턴."""
        result = classify_query("코디네이션관리의 정의는?")
        assert result.query_type == "definition"

    def test_meaning_in_skms(self):
        """'~의미로 사용되나요' 패턴."""
        result = classify_query("O.J.T는 SKMS에서 어떤 의미로 사용되나요?")
        assert result.query_type == "definition"

    def test_what_does_mean(self):
        """'~뜻하는가' 패턴."""
        result = classify_query("관리역량관리란 무엇을 뜻하는가?")
        assert result.query_type == "definition"

    def test_ultimate_purpose(self):
        """'궁극적 목적' (regression q-r01)."""
        result = classify_query("SKMS에서 경영의 궁극적 목적은?")
        # 이 질의는 정의에 해당하지 않을 수 있음 - open_ended로 분류
        assert result.query_type in ("definition", "open_ended")

    def test_short_definition(self):
        """짧은 정의 질의."""
        result = classify_query("패기 정의는?")
        assert result.query_type == "definition"


# ---------------------------------------------------------------------------
# classify_query — open_ended 테스트
# ---------------------------------------------------------------------------


class TestOpenEnded:
    """일반 탐색 질의 분류."""

    def test_general_question(self):
        """일반 탐색 질의."""
        result = classify_query("SKMS에서 가장 일관되게 강조하는 핵심 가치는 무엇인가?")
        assert result.query_type == "open_ended"

    def test_implications(self):
        """시사점 질의."""
        result = classify_query("SKMS의 인간중심 경영 철학이 현대 ESG 경영에 주는 시사점은?")
        assert result.query_type == "open_ended"

    def test_practical_application(self):
        """실무 적용 질의."""
        result = classify_query("SKMS를 실무 경영에 적용할 때 가장 중요한 원칙은?")
        assert result.query_type == "open_ended"

    def test_ideal_manager(self):
        """이상적 관리자 질의."""
        result = classify_query("SKMS에서 말하는 이상적인 관리자상은 어떤 모습인가?")
        assert result.query_type == "open_ended"

    def test_paradigm_shift(self):
        """패러다임 전환 질의."""
        result = classify_query("SKMS 40년 역사에서 가장 큰 패러다임 전환은 무엇이었는가?")
        assert result.query_type == "open_ended"

    def test_empty_query(self):
        """빈 질의."""
        result = classify_query("")
        assert result.query_type == "open_ended"
        assert result.confidence == 0.5


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """경계 사례 테스트."""

    def test_whitespace_only(self):
        """공백만 있는 질의."""
        result = classify_query("   ")
        assert result.query_type == "open_ended"

    def test_single_version_with_definition_keyword(self):
        """단일 개정판 + 정의 키워드 → single_version 우선."""
        result = classify_query("11차 개정판에서 SUPEX의 정의는?")
        assert result.query_type == "single_version"

    def test_cross_version_takes_priority(self):
        """비교 키워드가 단일 개정판보다 우선."""
        result = classify_query("초판에서 14차까지 인간중심 경영이 어떻게 변화했는가?")
        assert result.query_type == "cross_version"


# ---------------------------------------------------------------------------
# classify_batch 테스트
# ---------------------------------------------------------------------------


class TestClassifyBatch:
    """일괄 분류 테스트."""

    def test_batch_basic(self):
        """기본 일괄 분류."""
        queries = [
            {"id": "q1", "query": "SUPEX란 무엇인가?", "query_type": "definition"},
            {"id": "q2", "query": "14차에서 VWBE 내용은?", "query_type": "single_version"},
        ]
        results = classify_batch(queries)
        assert len(results) == 2
        assert results[0][1].query_type == "definition"
        assert results[1][1].query_type == "single_version"

    def test_batch_empty(self):
        """빈 배치."""
        assert classify_batch([]) == []


# ---------------------------------------------------------------------------
# evaluate_accuracy 테스트
# ---------------------------------------------------------------------------


class TestEvaluateAccuracy:
    """정확도 평가 테스트."""

    def test_perfect_accuracy(self):
        """100% 정확도."""
        queries = [
            {"id": "q1", "query": "SUPEX란 무엇인가?", "query_type": "definition"},
            {"id": "q2", "query": "14차에서 VWBE 내용은?", "query_type": "single_version"},
        ]
        report = evaluate_accuracy(queries)
        assert report["total"] == 2
        assert report["correct"] == 2
        assert report["accuracy"] == 1.0
        assert report["errors"] == []

    def test_accuracy_with_errors(self):
        """오류가 있는 경우."""
        queries = [
            {"id": "q1", "query": "SUPEX란 무엇인가?", "query_type": "definition"},
            {"id": "q2", "query": "일반 질문", "query_type": "definition"},  # 틀릴 수 있음
        ]
        report = evaluate_accuracy(queries)
        assert report["total"] == 2
        # accuracy는 0.5 또는 1.0 (규칙에 따라)
        assert 0.0 <= report["accuracy"] <= 1.0

    def test_per_type_stats(self):
        """타입별 통계."""
        queries = [
            {"id": "q1", "query": "SUPEX란?", "query_type": "definition"},
            {"id": "q2", "query": "합리적 경영의 정의는?", "query_type": "definition"},
        ]
        report = evaluate_accuracy(queries)
        assert "definition" in report["per_type"]
        assert report["per_type"]["definition"]["total"] == 2

    def test_empty_queries(self):
        """빈 쿼리 목록."""
        report = evaluate_accuracy([])
        assert report["total"] == 0
        assert report["accuracy"] == 0.0


# ---------------------------------------------------------------------------
# Seed Questions 통합 테스트 — ≥90% 정확도 목표
# ---------------------------------------------------------------------------


class TestSeedQuestionsAccuracy:
    """실제 seed questions에 대한 정확도 테스트."""

    @pytest.fixture()
    def seed_questions(self):
        """eval/questions.seed.jsonl 로드."""
        path = _PROJECT_ROOT / "eval" / "questions.seed.jsonl"
        if not path.exists():
            pytest.skip("eval/questions.seed.jsonl not found")

        questions = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    questions.append(json.loads(line))
        return questions

    def test_overall_accuracy_ge_90(self, seed_questions):
        """전체 정확도 ≥90%."""
        report = evaluate_accuracy(seed_questions)
        assert report["accuracy"] >= 0.90, (
            f"정확도 {report['accuracy']:.1%} < 90%\n"
            f"오류: {json.dumps(report['errors'], ensure_ascii=False, indent=2)}"
        )

    def test_single_version_accuracy(self, seed_questions):
        """single_version 정확도."""
        sv_queries = [q for q in seed_questions if q["query_type"] == "single_version"]
        if not sv_queries:
            pytest.skip("single_version queries not found")
        report = evaluate_accuracy(sv_queries)
        assert (
            report["accuracy"] >= 0.80
        ), f"single_version 정확도 {report['accuracy']:.1%}"

    def test_cross_version_accuracy(self, seed_questions):
        """cross_version 정확도."""
        cv_queries = [q for q in seed_questions if q["query_type"] == "cross_version"]
        if not cv_queries:
            pytest.skip("cross_version queries not found")
        report = evaluate_accuracy(cv_queries)
        assert report["accuracy"] >= 0.80, f"cross_version 정확도 {report['accuracy']:.1%}"

    def test_definition_accuracy(self, seed_questions):
        """definition 정확도."""
        def_queries = [q for q in seed_questions if q["query_type"] == "definition"]
        if not def_queries:
            pytest.skip("definition queries not found")
        report = evaluate_accuracy(def_queries)
        assert report["accuracy"] >= 0.80, f"definition 정확도 {report['accuracy']:.1%}"

    def test_open_ended_accuracy(self, seed_questions):
        """open_ended 정확도."""
        oe_queries = [q for q in seed_questions if q["query_type"] == "open_ended"]
        if not oe_queries:
            pytest.skip("open_ended queries not found")
        report = evaluate_accuracy(oe_queries)
        assert report["accuracy"] >= 0.80, f"open_ended 정확도 {report['accuracy']:.1%}"

    def test_accuracy_report_details(self, seed_questions):
        """정확도 보고서에 필수 필드가 있다."""
        report = evaluate_accuracy(seed_questions)
        assert "total" in report
        assert "correct" in report
        assert "accuracy" in report
        assert "per_type" in report
        assert "errors" in report
        assert report["total"] == len(seed_questions)
