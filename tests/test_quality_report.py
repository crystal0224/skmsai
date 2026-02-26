"""V1QualityReport 테스트.

PR-030: Golden QA 50 + V1 Quality Report 단위/통합 테스트.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.quality_gate import (  # noqa: E402
    DEFAULT_THRESHOLDS,
    EVAL_AXES,
    EvalResult,
)
from scripts.lib.quality_report import (  # noqa: E402
    DifficultyBreakdown,
    GoldenQuestion,
    QueryTypeBreakdown,
    V1QualityReport,
    compute_difficulty_breakdowns,
    compute_query_type_breakdowns,
    format_v1_report_json,
    format_v1_report_markdown,
    generate_v1_report,
    load_golden_questions,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _question(
    qid: str = "g-001",
    query: str = "SUPEX란?",
    query_type: str = "definition",
    difficulty: str = "easy",
    regression_checks: tuple[dict[str, Any], ...] = (),
) -> GoldenQuestion:
    """테스트용 GoldenQuestion."""
    return GoldenQuestion(
        id=qid,
        query=query,
        query_type=query_type,
        expected_edition=None,
        expected_keywords=("SUPEX",),
        difficulty=difficulty,
        regression_checks=regression_checks,
    )


def _result(
    qid: str = "g-001",
    query_type: str = "definition",
    passed: bool = True,
    scores: dict[str, float] | None = None,
    regression_passed: bool = True,
) -> EvalResult:
    """테스트용 EvalResult."""
    default_scores = {
        "relevance": 5.0,
        "faithfulness": 5.0,
        "quote_accuracy": 5.0,
        "temporal_correctness": 5.0,
    }
    return EvalResult(
        id=qid,
        query="test query",
        query_type=query_type,
        passed=passed,
        judge_passed=passed,
        regression_passed=regression_passed,
        scores=scores or default_scores,
        regression_failures=(),
    )


def _make_sample_results() -> list[EvalResult]:
    """다양한 결과 샘플."""
    return [
        _result("g-001", "definition", True),
        _result("g-002", "definition", True),
        _result(
            "g-003",
            "definition",
            False,
            {
                "relevance": 2.0,
                "faithfulness": 3.0,
                "quote_accuracy": 2.0,
                "temporal_correctness": 3.0,
            },
        ),
        _result("g-004", "single_version", True),
        _result(
            "g-005",
            "single_version",
            False,
            {
                "relevance": 3.0,
                "faithfulness": 2.0,
                "quote_accuracy": 3.0,
                "temporal_correctness": 4.0,
            },
        ),
        _result("g-006", "cross_version", True),
        _result("g-007", "cross_version", True),
        _result("g-008", "open_ended", True),
        _result(
            "g-009",
            "open_ended",
            False,
            {
                "relevance": 1.0,
                "faithfulness": 1.0,
                "quote_accuracy": 1.0,
                "temporal_correctness": 1.0,
            },
        ),
        _result("g-010", "open_ended", True),
    ]


def _make_sample_questions() -> list[GoldenQuestion]:
    """다양한 질의 샘플."""
    return [
        _question("g-001", "SUPEX란?", "definition", "easy"),
        _question("g-002", "합리적 경영?", "definition", "medium"),
        _question("g-003", "코디네이션?", "definition", "hard"),
        _question("g-004", "14차 VWBE?", "single_version", "medium"),
        _question("g-005", "초판 인사?", "single_version", "hard"),
        _question("g-006", "의욕관리 변화?", "cross_version", "hard"),
        _question("g-007", "SK-Manship 비교?", "cross_version", "medium"),
        _question("g-008", "핵심 가치?", "open_ended", "medium"),
        _question("g-009", "ESG 시사점?", "open_ended", "hard"),
        _question("g-010", "적용 원칙?", "open_ended", "easy"),
    ]


# ---------------------------------------------------------------------------
# GoldenQuestion 테스트
# ---------------------------------------------------------------------------


class TestGoldenQuestion:
    """GoldenQuestion 테스트."""

    def test_is_frozen(self):
        """불변이다."""
        q = _question()
        with pytest.raises(AttributeError):
            q.query = "other"  # type: ignore[misc]

    def test_fields(self):
        """필드 접근."""
        q = _question("g-001", "SUPEX란?", "definition", "easy")
        assert q.id == "g-001"
        assert q.query == "SUPEX란?"
        assert q.query_type == "definition"
        assert q.difficulty == "easy"
        assert q.regression_checks == ()

    def test_with_regression_checks(self):
        """회귀 검사 포함."""
        checks = ({"type": "latest_edition_first", "expected_first_year": 2020},)
        q = _question(regression_checks=checks)
        assert len(q.regression_checks) == 1
        assert q.regression_checks[0]["type"] == "latest_edition_first"


# ---------------------------------------------------------------------------
# QueryTypeBreakdown 테스트
# ---------------------------------------------------------------------------


class TestQueryTypeBreakdown:
    """QueryTypeBreakdown 테스트."""

    def test_is_frozen(self):
        """불변이다."""
        bd = QueryTypeBreakdown(
            query_type="definition",
            total=5,
            passed=4,
            failed=1,
            pass_rate=80.0,
            axis_stats=(),
        )
        with pytest.raises(AttributeError):
            bd.pass_rate = 100.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DifficultyBreakdown 테스트
# ---------------------------------------------------------------------------


class TestDifficultyBreakdown:
    """DifficultyBreakdown 테스트."""

    def test_is_frozen(self):
        """불변이다."""
        bd = DifficultyBreakdown(
            difficulty="easy", total=3, passed=3, failed=0, pass_rate=100.0
        )
        with pytest.raises(AttributeError):
            bd.total = 10  # type: ignore[misc]


# ---------------------------------------------------------------------------
# load_golden_questions 테스트
# ---------------------------------------------------------------------------


class TestLoadGoldenQuestions:
    """load_golden_questions 함수 테스트."""

    def test_load_from_file(self, tmp_path: Path):
        """JSONL 파일 로드."""
        path = tmp_path / "questions.jsonl"
        q1 = {
            "id": "g-001",
            "query": "SUPEX란?",
            "query_type": "definition",
            "expected_keywords": ["SUPEX"],
            "difficulty": "easy",
        }
        q2 = {
            "id": "g-002",
            "query": "합리적 경영?",
            "query_type": "definition",
            "expected_keywords": ["합리적"],
            "difficulty": "medium",
        }
        path.write_text(
            json.dumps(q1, ensure_ascii=False)
            + "\n"
            + json.dumps(q2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )

        questions = load_golden_questions(path)
        assert len(questions) == 2
        assert questions[0].id == "g-001"
        assert questions[0].expected_keywords == ("SUPEX",)
        assert questions[1].difficulty == "medium"

    def test_file_not_found(self, tmp_path: Path):
        """파일 없음."""
        path = tmp_path / "nonexistent.jsonl"
        questions = load_golden_questions(path)
        assert questions == []

    def test_empty_file(self, tmp_path: Path):
        """빈 파일."""
        path = tmp_path / "empty.jsonl"
        path.write_text("", encoding="utf-8")
        questions = load_golden_questions(path)
        assert questions == []

    def test_with_regression_checks(self, tmp_path: Path):
        """회귀 검사 포함 질의."""
        path = tmp_path / "questions.jsonl"
        q = {
            "id": "g-042",
            "query": "경영 목적?",
            "query_type": "definition",
            "expected_keywords": ["행복"],
            "difficulty": "medium",
            "regression_checks": [
                {"type": "latest_edition_first", "expected_first_year": 2020}
            ],
        }
        path.write_text(json.dumps(q, ensure_ascii=False) + "\n", encoding="utf-8")

        questions = load_golden_questions(path)
        assert len(questions) == 1
        assert len(questions[0].regression_checks) == 1

    def test_invalid_json_skipped(self, tmp_path: Path):
        """잘못된 JSON은 건너뜀."""
        path = tmp_path / "questions.jsonl"
        path.write_text(
            '{"id": "g-001", "query": "test", "query_type": "def"}\n'
            "invalid json line\n"
            '{"id": "g-002", "query": "test2", "query_type": "def"}\n',
            encoding="utf-8",
        )
        questions = load_golden_questions(path)
        assert len(questions) == 2

    def test_load_real_golden_file(self):
        """실제 Golden QA 파일 로드."""
        path = Path("eval/questions.golden_v1.jsonl")
        if not path.exists():
            pytest.skip("Golden QA 파일 없음")
        questions = load_golden_questions(path)
        assert len(questions) == 50


# ---------------------------------------------------------------------------
# compute_query_type_breakdowns 테스트
# ---------------------------------------------------------------------------


class TestComputeQueryTypeBreakdowns:
    """compute_query_type_breakdowns 함수 테스트."""

    def test_basic(self):
        """기본 분석."""
        results = _make_sample_results()
        breakdowns = compute_query_type_breakdowns(results)

        # 4개 유형 (cross_version, definition, open_ended, single_version — 알파벳순)
        assert len(breakdowns) == 4
        types = [bd.query_type for bd in breakdowns]
        assert "definition" in types
        assert "single_version" in types

    def test_definition_breakdown(self):
        """definition 유형 분석."""
        results = _make_sample_results()
        breakdowns = compute_query_type_breakdowns(results)

        defn = next(bd for bd in breakdowns if bd.query_type == "definition")
        assert defn.total == 3
        assert defn.passed == 2
        assert defn.failed == 1
        assert defn.pass_rate == pytest.approx(66.7, abs=0.1)

    def test_empty_results(self):
        """빈 결과."""
        breakdowns = compute_query_type_breakdowns([])
        assert breakdowns == ()

    def test_single_type(self):
        """단일 유형."""
        results = [_result("g-001", "definition", True)]
        breakdowns = compute_query_type_breakdowns(results)
        assert len(breakdowns) == 1
        assert breakdowns[0].query_type == "definition"
        assert breakdowns[0].pass_rate == 100.0

    def test_axis_stats_included(self):
        """축별 통계 포함."""
        results = _make_sample_results()
        breakdowns = compute_query_type_breakdowns(results)

        defn = next(bd for bd in breakdowns if bd.query_type == "definition")
        assert len(defn.axis_stats) == 4  # 4축


# ---------------------------------------------------------------------------
# compute_difficulty_breakdowns 테스트
# ---------------------------------------------------------------------------


class TestComputeDifficultyBreakdowns:
    """compute_difficulty_breakdowns 함수 테스트."""

    def test_basic(self):
        """기본 분석."""
        results = _make_sample_results()
        questions = _make_sample_questions()
        breakdowns = compute_difficulty_breakdowns(results, questions)

        # easy, medium, hard 3개
        assert len(breakdowns) == 3
        diffs = [bd.difficulty for bd in breakdowns]
        assert diffs == ["easy", "medium", "hard"]

    def test_easy_all_pass(self):
        """easy 난이도 — 전체 통과."""
        results = _make_sample_results()
        questions = _make_sample_questions()
        breakdowns = compute_difficulty_breakdowns(results, questions)

        easy = next(bd for bd in breakdowns if bd.difficulty == "easy")
        assert easy.total == 2  # g-001, g-010
        assert easy.passed == 2
        assert easy.pass_rate == 100.0

    def test_hard_mixed(self):
        """hard 난이도 — 혼합."""
        results = _make_sample_results()
        questions = _make_sample_questions()
        breakdowns = compute_difficulty_breakdowns(results, questions)

        hard = next(bd for bd in breakdowns if bd.difficulty == "hard")
        assert hard.total == 4  # g-003(F), g-005(F), g-006(T), g-009(F)
        assert hard.passed == 1  # g-006만 통과
        assert hard.failed == 3

    def test_empty_results(self):
        """빈 결과."""
        breakdowns = compute_difficulty_breakdowns([], [])
        assert breakdowns == ()


# ---------------------------------------------------------------------------
# generate_v1_report 테스트
# ---------------------------------------------------------------------------


class TestGenerateV1Report:
    """generate_v1_report 함수 테스트."""

    def test_basic(self):
        """기본 보고서 생성."""
        results = _make_sample_results()
        questions = _make_sample_questions()
        report = generate_v1_report(results, questions)

        assert isinstance(report, V1QualityReport)
        assert report.golden_question_count == 10
        assert report.evaluated_count == 10
        assert report.quality_report.total_questions == 10

    def test_pass_rate(self):
        """통과율 계산."""
        results = _make_sample_results()
        questions = _make_sample_questions()
        report = generate_v1_report(results, questions)

        # 10개 중 7개 통과 → 70%
        assert report.quality_report.pass_rate == 70.0

    def test_gate_decision(self):
        """Go/No-Go 판정."""
        results = _make_sample_results()
        questions = _make_sample_questions()

        # 기본 기준 80% → 70%이므로 실패
        report = generate_v1_report(results, questions)
        assert report.quality_report.gate_passed is False

        # 기준 60%로 낮추면 통과
        report_low = generate_v1_report(results, questions, pass_rate_threshold=60.0)
        assert report_low.quality_report.gate_passed is True

    def test_regression_stats(self):
        """회귀 검사 통계."""
        checks = ({"type": "latest_edition_first", "expected_first_year": 2020},)
        questions = [
            _question("g-001", regression_checks=checks),
            _question("g-002"),
        ]
        results = [
            _result("g-001", regression_passed=True),
            _result("g-002", regression_passed=True),
        ]

        report = generate_v1_report(results, questions)
        assert report.regression_total == 1  # g-001만 회귀 검사 있음
        assert report.regression_passed == 1

    def test_empty_results(self):
        """빈 결과."""
        report = generate_v1_report([], [])
        assert report.quality_report.gate_passed is False
        assert report.evaluated_count == 0

    def test_breakdowns_present(self):
        """유형별/난이도별 분석 포함."""
        results = _make_sample_results()
        questions = _make_sample_questions()
        report = generate_v1_report(results, questions)

        assert len(report.query_type_breakdowns) == 4
        assert len(report.difficulty_breakdowns) == 3

    def test_is_frozen(self):
        """불변이다."""
        results = _make_sample_results()
        questions = _make_sample_questions()
        report = generate_v1_report(results, questions)

        with pytest.raises(AttributeError):
            report.evaluated_count = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# format_v1_report_markdown 테스트
# ---------------------------------------------------------------------------


class TestFormatV1ReportMarkdown:
    """format_v1_report_markdown 함수 테스트."""

    def test_basic(self):
        """기본 Markdown 출력."""
        results = _make_sample_results()
        questions = _make_sample_questions()
        report = generate_v1_report(results, questions)
        md = format_v1_report_markdown(report)

        assert "# V1 Quality Report" in md
        assert "## 개요" in md
        assert "## 축별 통계" in md
        assert "## 질의 유형별 분석" in md
        assert "## 난이도별 분석" in md

    def test_gate_pass_label(self):
        """PASS 라벨."""
        results = [_result(f"g-{i:03d}") for i in range(10)]
        questions = [_question(f"g-{i:03d}") for i in range(10)]
        report = generate_v1_report(results, questions)
        md = format_v1_report_markdown(report)

        assert "PASS" in md

    def test_gate_fail_label(self):
        """FAIL 라벨."""
        results = _make_sample_results()
        questions = _make_sample_questions()
        report = generate_v1_report(results, questions)
        md = format_v1_report_markdown(report)

        assert "FAIL" in md

    def test_failed_questions_listed(self):
        """실패 문항 목록."""
        results = _make_sample_results()
        questions = _make_sample_questions()
        report = generate_v1_report(results, questions)
        md = format_v1_report_markdown(report)

        assert "## 실패 문항" in md
        assert "g-003" in md

    def test_type_detail_sections(self):
        """유형별 축별 상세 섹션."""
        results = _make_sample_results()
        questions = _make_sample_questions()
        report = generate_v1_report(results, questions)
        md = format_v1_report_markdown(report)

        assert "## 유형별 축별 상세" in md
        assert "### definition" in md


# ---------------------------------------------------------------------------
# format_v1_report_json 테스트
# ---------------------------------------------------------------------------


class TestFormatV1ReportJSON:
    """format_v1_report_json 함수 테스트."""

    def test_basic(self):
        """기본 JSON 출력."""
        results = _make_sample_results()
        questions = _make_sample_questions()
        report = generate_v1_report(results, questions)
        data = format_v1_report_json(report)

        assert "gate_passed" in data
        assert "golden_question_count" in data
        assert "axis_stats" in data
        assert "query_type_breakdowns" in data
        assert "difficulty_breakdowns" in data

    def test_serializable(self):
        """JSON 직렬화 가능."""
        results = _make_sample_results()
        questions = _make_sample_questions()
        report = generate_v1_report(results, questions)
        data = format_v1_report_json(report)

        # json.dumps가 성공해야 함
        serialized = json.dumps(data, ensure_ascii=False)
        assert isinstance(serialized, str)
        assert len(serialized) > 0

    def test_regression_field(self):
        """회귀 검사 필드."""
        results = _make_sample_results()
        questions = _make_sample_questions()
        report = generate_v1_report(results, questions)
        data = format_v1_report_json(report)

        assert "regression" in data
        assert "total" in data["regression"]
        assert "passed" in data["regression"]

    def test_values_match(self):
        """값 일치 확인."""
        results = _make_sample_results()
        questions = _make_sample_questions()
        report = generate_v1_report(results, questions)
        data = format_v1_report_json(report)

        assert data["golden_question_count"] == 10
        assert data["evaluated_count"] == 10
        assert data["pass_rate"] == 70.0


# ---------------------------------------------------------------------------
# 통합 테스트
# ---------------------------------------------------------------------------


class TestQualityReportIntegration:
    """통합 테스트."""

    def test_full_pipeline(self, tmp_path: Path):
        """전체 파이프라인: 로드 → 분석 → 보고서."""
        # 1. Golden QA 파일 생성
        path = tmp_path / "golden.jsonl"
        questions_data = [
            {
                "id": "g-001",
                "query": "SUPEX?",
                "query_type": "definition",
                "expected_keywords": ["SUPEX"],
                "difficulty": "easy",
            },
            {
                "id": "g-002",
                "query": "합리적?",
                "query_type": "definition",
                "expected_keywords": ["합리적"],
                "difficulty": "medium",
            },
            {
                "id": "g-003",
                "query": "변화?",
                "query_type": "cross_version",
                "expected_keywords": ["변화"],
                "difficulty": "hard",
            },
        ]
        path.write_text(
            "\n".join(json.dumps(q, ensure_ascii=False) for q in questions_data),
            encoding="utf-8",
        )

        # 2. 질의 로드
        questions = load_golden_questions(path)
        assert len(questions) == 3

        # 3. 평가 결과 (시뮬레이션)
        results = [
            _result("g-001", "definition", True),
            _result("g-002", "definition", True),
            _result(
                "g-003",
                "cross_version",
                False,
                {
                    "relevance": 2.0,
                    "faithfulness": 2.0,
                    "quote_accuracy": 2.0,
                    "temporal_correctness": 2.0,
                },
            ),
        ]

        # 4. 보고서 생성
        report = generate_v1_report(results, questions)
        assert report.golden_question_count == 3
        assert report.evaluated_count == 3
        assert report.quality_report.pass_rate == pytest.approx(66.7, abs=0.1)

        # 5. Markdown 출력
        md = format_v1_report_markdown(report)
        assert "V1 Quality Report" in md
        assert "FAIL" in md

        # 6. JSON 출력
        data = format_v1_report_json(report)
        assert data["gate_passed"] is False
        json_str = json.dumps(data, ensure_ascii=False)
        assert "gate_passed" in json_str

    def test_real_golden_file_structure(self):
        """실제 Golden QA 파일 구조 검증."""
        path = Path("eval/questions.golden_v1.jsonl")
        if not path.exists():
            pytest.skip("Golden QA 파일 없음")

        questions = load_golden_questions(path)

        # 50문항
        assert len(questions) == 50

        # 모든 ID가 'g-' 접두사
        assert all(q.id.startswith("g-") for q in questions)

        # 4가지 유형 존재
        types = {q.query_type for q in questions}
        assert types == {"single_version", "cross_version", "definition", "open_ended"}

        # 3가지 난이도 존재
        diffs = {q.difficulty for q in questions}
        assert diffs == {"easy", "medium", "hard"}

        # 회귀 검사 포함 문항 존재
        regression_count = sum(1 for q in questions if q.regression_checks)
        assert regression_count >= 4

    def test_all_pass_report(self):
        """전체 통과 보고서."""
        questions = [_question(f"g-{i:03d}") for i in range(20)]
        results = [_result(f"g-{i:03d}") for i in range(20)]
        report = generate_v1_report(results, questions)

        assert report.quality_report.gate_passed is True
        assert report.quality_report.pass_rate == 100.0
        assert report.quality_report.failed_count == 0
