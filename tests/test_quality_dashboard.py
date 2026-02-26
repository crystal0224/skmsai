"""품질 대시보드 테스트.

PR-039: Golden QA 100 + 최종 품질 대시보드 테스트.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scripts.lib.quality_dashboard import (
    KNOWN_EDITIONS,
    EditionCoverage,
    QualitySummary,
    V2QualityReport,
    compute_coverage_score,
    compute_edition_coverages,
    compute_overall_grade,
    compute_quality_summaries,
    format_v2_report_json,
    format_v2_report_markdown,
    generate_recommendations,
    generate_v2_report,
    load_all_golden_questions,
)
from scripts.lib.quality_gate import (
    DEFAULT_THRESHOLDS,
    EVAL_AXES,
    AxisStats,
    EvalResult,
    QualityReport,
)
from scripts.lib.quality_report import (
    DifficultyBreakdown,
    GoldenQuestion,
    QueryTypeBreakdown,
    V1QualityReport,
    load_golden_questions,
)


# ---------------------------------------------------------------------------
# 테스트 헬퍼
# ---------------------------------------------------------------------------


def _make_eval_result(
    id: str,
    query_type: str = "definition",
    passed: bool = True,
    scores: dict[str, float] | None = None,
    regression_passed: bool = True,
) -> EvalResult:
    """테스트용 EvalResult를 생성한다."""
    default_scores = {axis: 4.5 for axis in EVAL_AXES}
    return EvalResult(
        id=id,
        query=f"질의 {id}",
        query_type=query_type,
        passed=passed,
        judge_passed=passed,
        regression_passed=regression_passed,
        scores=scores or default_scores,
        regression_failures=() if regression_passed else ("test_failure",),
    )


def _make_golden_question(
    id: str,
    query_type: str = "definition",
    expected_edition: str | None = None,
    difficulty: str = "medium",
    regression_checks: tuple[dict[str, Any], ...] = (),
) -> GoldenQuestion:
    """테스트용 GoldenQuestion을 생성한다."""
    return GoldenQuestion(
        id=id,
        query=f"질의 {id}",
        query_type=query_type,
        expected_edition=expected_edition,
        expected_keywords=("테스트",),
        difficulty=difficulty,
        regression_checks=regression_checks,
    )


# ---------------------------------------------------------------------------
# EditionCoverage 테스트
# ---------------------------------------------------------------------------


class TestEditionCoverage:
    """EditionCoverage frozen dataclass 테스트."""

    def test_fields(self):
        cov = EditionCoverage(
            edition="14차",
            question_count=5,
            query_types=("single_version",),
            difficulties=("easy", "medium"),
        )
        assert cov.edition == "14차"
        assert cov.question_count == 5
        assert "single_version" in cov.query_types

    def test_immutable(self):
        cov = EditionCoverage(
            edition="초판",
            question_count=3,
            query_types=(),
            difficulties=(),
        )
        with pytest.raises(AttributeError):
            cov.question_count = 10  # type: ignore[misc]


class TestQualitySummary:
    """QualitySummary frozen dataclass 테스트."""

    def test_fields(self):
        s = QualitySummary(
            axis="relevance",
            mean_score=4.2,
            pass_rate=85.0,
            weakest_type="open_ended",
            weakest_type_mean=3.8,
        )
        assert s.axis == "relevance"
        assert s.mean_score == 4.2

    def test_immutable(self):
        s = QualitySummary(
            axis="relevance",
            mean_score=4.2,
            pass_rate=85.0,
            weakest_type="open_ended",
            weakest_type_mean=3.8,
        )
        with pytest.raises(AttributeError):
            s.mean_score = 5.0  # type: ignore[misc]


class TestV2QualityReport:
    """V2QualityReport frozen dataclass 테스트."""

    def test_immutable(self):
        v1 = V1QualityReport(
            quality_report=QualityReport(
                total_questions=10,
                passed_count=8,
                failed_count=2,
                pass_rate=80.0,
                pass_rate_threshold=80.0,
                gate_passed=True,
                axis_stats=(),
                regression_failure_count=0,
                failed_questions=(),
                thresholds=dict(DEFAULT_THRESHOLDS),
            ),
            query_type_breakdowns=(),
            difficulty_breakdowns=(),
            golden_question_count=10,
            evaluated_count=10,
            regression_total=0,
            regression_passed=0,
        )
        report = V2QualityReport(
            v1_report=v1,
            edition_coverages=(),
            quality_summaries=(),
            recommendations=(),
            coverage_score=100.0,
            overall_grade="A",
        )
        with pytest.raises(AttributeError):
            report.overall_grade = "F"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Golden QA V2 파일 테스트
# ---------------------------------------------------------------------------


class TestGoldenQAV2File:
    """Golden QA V2 파일 구조 검증."""

    def test_v2_file_exists(self):
        path = Path("eval/questions.golden_v2.jsonl")
        assert path.exists(), "V2 Golden QA 파일 없음"

    def test_v2_has_50_questions(self):
        path = Path("eval/questions.golden_v2.jsonl")
        questions = load_golden_questions(path)
        assert len(questions) == 50

    def test_v2_ids_start_at_51(self):
        path = Path("eval/questions.golden_v2.jsonl")
        questions = load_golden_questions(path)
        ids = [q.id for q in questions]
        assert ids[0] == "g-051"
        assert ids[-1] == "g-100"

    def test_v2_has_all_query_types(self):
        path = Path("eval/questions.golden_v2.jsonl")
        questions = load_golden_questions(path)
        types = {q.query_type for q in questions}
        assert types == {"single_version", "cross_version", "definition", "open_ended"}

    def test_v2_has_all_difficulties(self):
        path = Path("eval/questions.golden_v2.jsonl")
        questions = load_golden_questions(path)
        difficulties = {q.difficulty for q in questions}
        assert difficulties == {"easy", "medium", "hard"}

    def test_v2_has_regression_checks(self):
        path = Path("eval/questions.golden_v2.jsonl")
        questions = load_golden_questions(path)
        with_checks = [q for q in questions if q.regression_checks]
        assert len(with_checks) >= 3

    def test_no_duplicate_ids(self):
        path = Path("eval/questions.golden_v2.jsonl")
        questions = load_golden_questions(path)
        ids = [q.id for q in questions]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# load_all_golden_questions 테스트
# ---------------------------------------------------------------------------


class TestLoadAllGoldenQuestions:
    """load_all_golden_questions() 통합 로드 테스트."""

    def test_loads_100_questions(self):
        v1_path = Path("eval/questions.golden_v1.jsonl")
        v2_path = Path("eval/questions.golden_v2.jsonl")
        questions = load_all_golden_questions(v1_path, v2_path)
        assert len(questions) == 100

    def test_all_ids_unique(self):
        v1_path = Path("eval/questions.golden_v1.jsonl")
        v2_path = Path("eval/questions.golden_v2.jsonl")
        questions = load_all_golden_questions(v1_path, v2_path)
        ids = [q.id for q in questions]
        assert len(ids) == len(set(ids))

    def test_handles_missing_v2(self, tmp_path):
        v1_path = Path("eval/questions.golden_v1.jsonl")
        v2_path = tmp_path / "nonexistent.jsonl"
        questions = load_all_golden_questions(v1_path, v2_path)
        assert len(questions) == 50  # V1만 로드


# ---------------------------------------------------------------------------
# compute_edition_coverages 테스트
# ---------------------------------------------------------------------------


class TestComputeEditionCoverages:
    """compute_edition_coverages() 테스트."""

    def test_all_known_editions_present(self):
        questions = [
            _make_golden_question("q1", expected_edition="14차"),
            _make_golden_question("q2", expected_edition="초판"),
        ]
        coverages = compute_edition_coverages(questions)
        editions = [c.edition for c in coverages]
        for ed in KNOWN_EDITIONS:
            assert ed in editions

    def test_counts_correct(self):
        questions = [
            _make_golden_question("q1", expected_edition="14차"),
            _make_golden_question("q2", expected_edition="14차"),
            _make_golden_question("q3", expected_edition="초판"),
        ]
        coverages = compute_edition_coverages(questions)
        cov_map = {c.edition: c for c in coverages}
        assert cov_map["14차"].question_count == 2
        assert cov_map["초판"].question_count == 1
        assert cov_map["10차"].question_count == 0

    def test_null_edition_excluded(self):
        questions = [
            _make_golden_question("q1", expected_edition=None),
        ]
        coverages = compute_edition_coverages(questions)
        # 모든 개정판의 question_count가 0
        assert all(c.question_count == 0 for c in coverages)

    def test_query_types_tracked(self):
        questions = [
            _make_golden_question(
                "q1", query_type="single_version", expected_edition="14차"
            ),
            _make_golden_question(
                "q2", query_type="definition", expected_edition="14차"
            ),
        ]
        coverages = compute_edition_coverages(questions)
        cov_map = {c.edition: c for c in coverages}
        assert "definition" in cov_map["14차"].query_types
        assert "single_version" in cov_map["14차"].query_types

    def test_real_golden_qa_coverage(self):
        """실제 Golden QA 100개의 커버리지 확인."""
        v1_path = Path("eval/questions.golden_v1.jsonl")
        v2_path = Path("eval/questions.golden_v2.jsonl")
        questions = load_all_golden_questions(v1_path, v2_path)
        coverages = compute_edition_coverages(questions)
        # 모든 알려진 개정판에 최소 1개 문항
        for c in coverages:
            assert c.question_count >= 1, f"{c.edition}에 문항 없음"


# ---------------------------------------------------------------------------
# compute_coverage_score 테스트
# ---------------------------------------------------------------------------


class TestComputeCoverageScore:
    """compute_coverage_score() 테스트."""

    def test_full_coverage(self):
        coverages = tuple(
            EditionCoverage(
                edition=ed, question_count=1, query_types=(), difficulties=()
            )
            for ed in KNOWN_EDITIONS
        )
        assert compute_coverage_score(coverages) == 100.0

    def test_partial_coverage(self):
        coverages = (
            EditionCoverage(
                edition="14차", question_count=1, query_types=(), difficulties=()
            ),
            EditionCoverage(
                edition="초판", question_count=0, query_types=(), difficulties=()
            ),
        )
        assert compute_coverage_score(coverages) == 50.0

    def test_no_coverage(self):
        coverages = (
            EditionCoverage(
                edition="14차", question_count=0, query_types=(), difficulties=()
            ),
        )
        assert compute_coverage_score(coverages) == 0.0

    def test_empty_coverages(self):
        assert compute_coverage_score(()) == 0.0


# ---------------------------------------------------------------------------
# compute_quality_summaries 테스트
# ---------------------------------------------------------------------------


class TestComputeQualitySummaries:
    """compute_quality_summaries() 테스트."""

    def test_returns_summaries_per_axis(self):
        results = [_make_eval_result("q1"), _make_eval_result("q2")]
        type_breakdowns = (
            QueryTypeBreakdown(
                query_type="definition",
                total=2,
                passed=2,
                failed=0,
                pass_rate=100.0,
                axis_stats=tuple(
                    AxisStats(
                        axis=axis,
                        mean=4.5,
                        min_val=4.0,
                        max_val=5.0,
                        threshold=DEFAULT_THRESHOLDS[axis],
                        above_threshold=2,
                        total=2,
                    )
                    for axis in EVAL_AXES
                ),
            ),
        )
        summaries = compute_quality_summaries(results, type_breakdowns)
        assert len(summaries) == len(EVAL_AXES)

    def test_empty_results(self):
        summaries = compute_quality_summaries([], ())
        assert summaries == ()

    def test_weakest_type_identified(self):
        results = [
            _make_eval_result(
                "q1",
                query_type="definition",
                scores={
                    "relevance": 4.5,
                    "faithfulness": 4.5,
                    "quote_accuracy": 4.5,
                    "temporal_correctness": 4.5,
                },
            ),
            _make_eval_result(
                "q2",
                query_type="open_ended",
                scores={
                    "relevance": 2.0,
                    "faithfulness": 2.0,
                    "quote_accuracy": 2.0,
                    "temporal_correctness": 2.0,
                },
            ),
        ]
        type_breakdowns = (
            QueryTypeBreakdown(
                query_type="definition",
                total=1,
                passed=1,
                failed=0,
                pass_rate=100.0,
                axis_stats=tuple(
                    AxisStats(
                        axis=a,
                        mean=4.5,
                        min_val=4.5,
                        max_val=4.5,
                        threshold=3.5,
                        above_threshold=1,
                        total=1,
                    )
                    for a in EVAL_AXES
                ),
            ),
            QueryTypeBreakdown(
                query_type="open_ended",
                total=1,
                passed=0,
                failed=1,
                pass_rate=0.0,
                axis_stats=tuple(
                    AxisStats(
                        axis=a,
                        mean=2.0,
                        min_val=2.0,
                        max_val=2.0,
                        threshold=3.5,
                        above_threshold=0,
                        total=1,
                    )
                    for a in EVAL_AXES
                ),
            ),
        )
        summaries = compute_quality_summaries(results, type_breakdowns)
        for s in summaries:
            assert s.weakest_type == "open_ended"
            assert s.weakest_type_mean == 2.0


# ---------------------------------------------------------------------------
# compute_overall_grade 테스트
# ---------------------------------------------------------------------------


class TestComputeOverallGrade:
    """compute_overall_grade() 테스트."""

    def test_grade_a(self):
        assert compute_overall_grade(95.0, 100.0, 100.0) == "A"

    def test_grade_b(self):
        assert compute_overall_grade(85.0, 80.0, 80.0) == "B"

    def test_grade_c(self):
        assert compute_overall_grade(70.0, 70.0, 70.0) == "C"

    def test_grade_d(self):
        assert compute_overall_grade(60.0, 60.0, 60.0) == "D"

    def test_grade_f(self):
        assert compute_overall_grade(40.0, 40.0, 40.0) == "F"


# ---------------------------------------------------------------------------
# generate_recommendations 테스트
# ---------------------------------------------------------------------------


class TestGenerateRecommendations:
    """generate_recommendations() 테스트."""

    def test_all_good(self):
        v1 = V1QualityReport(
            quality_report=QualityReport(
                total_questions=10,
                passed_count=10,
                failed_count=0,
                pass_rate=100.0,
                pass_rate_threshold=80.0,
                gate_passed=True,
                axis_stats=(),
                regression_failure_count=0,
                failed_questions=(),
                thresholds=dict(DEFAULT_THRESHOLDS),
            ),
            query_type_breakdowns=(),
            difficulty_breakdowns=(),
            golden_question_count=10,
            evaluated_count=10,
            regression_total=2,
            regression_passed=2,
        )
        summaries = (
            QualitySummary(
                axis="relevance",
                mean_score=4.5,
                pass_rate=100.0,
                weakest_type="definition",
                weakest_type_mean=4.5,
            ),
        )
        recs = generate_recommendations(v1, summaries, 100.0)
        assert len(recs) == 1
        assert "충족" in recs[0]

    def test_low_coverage(self):
        v1 = V1QualityReport(
            quality_report=QualityReport(
                total_questions=10,
                passed_count=10,
                failed_count=0,
                pass_rate=100.0,
                pass_rate_threshold=80.0,
                gate_passed=True,
                axis_stats=(),
                regression_failure_count=0,
                failed_questions=(),
                thresholds=dict(DEFAULT_THRESHOLDS),
            ),
            query_type_breakdowns=(),
            difficulty_breakdowns=(),
            golden_question_count=10,
            evaluated_count=10,
            regression_total=0,
            regression_passed=0,
        )
        summaries = ()
        recs = generate_recommendations(v1, summaries, 50.0)
        assert any("커버리지" in r for r in recs)

    def test_low_pass_rate(self):
        v1 = V1QualityReport(
            quality_report=QualityReport(
                total_questions=10,
                passed_count=5,
                failed_count=5,
                pass_rate=50.0,
                pass_rate_threshold=80.0,
                gate_passed=False,
                axis_stats=(),
                regression_failure_count=0,
                failed_questions=("q1", "q2", "q3", "q4", "q5"),
                thresholds=dict(DEFAULT_THRESHOLDS),
            ),
            query_type_breakdowns=(),
            difficulty_breakdowns=(),
            golden_question_count=10,
            evaluated_count=10,
            regression_total=0,
            regression_passed=0,
        )
        recs = generate_recommendations(v1, (), 100.0)
        assert any("미달" in r for r in recs)

    def test_regression_failure(self):
        v1 = V1QualityReport(
            quality_report=QualityReport(
                total_questions=10,
                passed_count=10,
                failed_count=0,
                pass_rate=100.0,
                pass_rate_threshold=80.0,
                gate_passed=True,
                axis_stats=(),
                regression_failure_count=1,
                failed_questions=(),
                thresholds=dict(DEFAULT_THRESHOLDS),
            ),
            query_type_breakdowns=(),
            difficulty_breakdowns=(),
            golden_question_count=10,
            evaluated_count=10,
            regression_total=3,
            regression_passed=2,
        )
        recs = generate_recommendations(v1, (), 100.0)
        assert any("회귀" in r for r in recs)


# ---------------------------------------------------------------------------
# generate_v2_report 테스트
# ---------------------------------------------------------------------------


class TestGenerateV2Report:
    """generate_v2_report() 통합 테스트."""

    def test_basic_report(self):
        questions = [
            _make_golden_question("q1", expected_edition="14차", difficulty="easy"),
            _make_golden_question("q2", expected_edition="초판", difficulty="hard"),
        ]
        results = [
            _make_eval_result("q1"),
            _make_eval_result("q2"),
        ]
        report = generate_v2_report(results, questions)
        assert isinstance(report, V2QualityReport)
        assert report.v1_report.golden_question_count == 2
        assert report.coverage_score > 0
        assert report.overall_grade in ("A", "B", "C", "D", "F")

    def test_with_failures(self):
        questions = [
            _make_golden_question("q1", difficulty="easy"),
            _make_golden_question("q2", difficulty="hard"),
            _make_golden_question("q3", difficulty="medium"),
        ]
        results = [
            _make_eval_result("q1", passed=True),
            _make_eval_result(
                "q2",
                passed=False,
                scores={
                    "relevance": 2.0,
                    "faithfulness": 2.0,
                    "quote_accuracy": 2.0,
                    "temporal_correctness": 2.0,
                },
            ),
            _make_eval_result("q3", passed=True),
        ]
        report = generate_v2_report(results, questions)
        assert report.v1_report.quality_report.failed_count == 1
        assert len(report.recommendations) > 0

    def test_empty_results(self):
        questions = [_make_golden_question("q1")]
        report = generate_v2_report([], questions)
        assert report.v1_report.quality_report.gate_passed is False
        assert report.overall_grade == "F"

    def test_with_regression_checks(self):
        questions = [
            _make_golden_question(
                "q1",
                expected_edition="14차",
                regression_checks=(
                    {"type": "latest_edition_first", "expected_first_year": 2020},
                ),
            ),
        ]
        results = [
            _make_eval_result("q1", regression_passed=False),
        ]
        report = generate_v2_report(results, questions)
        assert report.v1_report.regression_total == 1
        assert report.v1_report.regression_passed == 0


# ---------------------------------------------------------------------------
# format_v2_report_markdown 테스트
# ---------------------------------------------------------------------------


class TestFormatV2ReportMarkdown:
    """format_v2_report_markdown() 테스트."""

    def test_contains_header(self):
        questions = [_make_golden_question("q1", expected_edition="14차")]
        results = [_make_eval_result("q1")]
        report = generate_v2_report(results, questions)
        md = format_v2_report_markdown(report)
        assert "# V2 Final Quality Report" in md

    def test_contains_grade(self):
        questions = [_make_golden_question("q1", expected_edition="14차")]
        results = [_make_eval_result("q1")]
        report = generate_v2_report(results, questions)
        md = format_v2_report_markdown(report)
        assert "Grade:" in md

    def test_contains_coverage_section(self):
        questions = [_make_golden_question("q1", expected_edition="14차")]
        results = [_make_eval_result("q1")]
        report = generate_v2_report(results, questions)
        md = format_v2_report_markdown(report)
        assert "## 개정판별 커버리지" in md

    def test_contains_recommendations(self):
        questions = [_make_golden_question("q1", expected_edition="14차")]
        results = [_make_eval_result("q1")]
        report = generate_v2_report(results, questions)
        md = format_v2_report_markdown(report)
        assert "## 권장사항" in md


# ---------------------------------------------------------------------------
# format_v2_report_json 테스트
# ---------------------------------------------------------------------------


class TestFormatV2ReportJson:
    """format_v2_report_json() 테스트."""

    def test_has_required_keys(self):
        questions = [_make_golden_question("q1", expected_edition="14차")]
        results = [_make_eval_result("q1")]
        report = generate_v2_report(results, questions)
        data = format_v2_report_json(report)
        assert "overall_grade" in data
        assert "gate_passed" in data
        assert "coverage_score" in data
        assert "quality_summaries" in data
        assert "edition_coverages" in data
        assert "recommendations" in data

    def test_json_serializable(self):
        import json

        questions = [_make_golden_question("q1", expected_edition="14차")]
        results = [_make_eval_result("q1")]
        report = generate_v2_report(results, questions)
        data = format_v2_report_json(report)
        # JSON 직렬화 가능해야 함
        json_str = json.dumps(data, ensure_ascii=False)
        assert len(json_str) > 0

    def test_pass_rate_matches(self):
        questions = [
            _make_golden_question("q1"),
            _make_golden_question("q2"),
        ]
        results = [
            _make_eval_result("q1", passed=True),
            _make_eval_result("q2", passed=False),
        ]
        report = generate_v2_report(results, questions)
        data = format_v2_report_json(report)
        assert data["pass_rate"] == 50.0
        assert data["passed_count"] == 1
        assert data["failed_count"] == 1


# ---------------------------------------------------------------------------
# Quality API 테스트
# ---------------------------------------------------------------------------


class TestQualityAPI:
    """품질 대시보드 API 엔드포인트 테스트."""

    def test_coverage_endpoint(self):
        from server.app import app

        client = TestClient(app)
        resp = client.get("/api/quality/coverage")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_questions" in data
        assert data["total_questions"] == 100
        assert "coverage_score" in data
        assert "editions" in data

    def test_summary_endpoint_no_results(self):
        from server.app import app

        client = TestClient(app)
        resp = client.get("/api/quality/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["golden_questions"] == 100

    def test_report_endpoint_no_results(self):
        from server.app import app

        client = TestClient(app)
        resp = client.get("/api/quality/report")
        assert resp.status_code == 200
        data = resp.json()
        assert "golden_questions" in data or "golden_question_count" in data

    def test_report_format_param(self):
        from server.app import app

        client = TestClient(app)
        # JSON format (기본)
        resp = client.get("/api/quality/report?format=json")
        assert resp.status_code == 200

    def test_coverage_has_all_editions(self):
        from server.app import app

        client = TestClient(app)
        resp = client.get("/api/quality/coverage")
        data = resp.json()
        edition_names = [e["edition"] for e in data["editions"]]
        for ed in KNOWN_EDITIONS:
            assert ed in edition_names


# ---------------------------------------------------------------------------
# 통합 테스트: 실제 Golden QA 파일
# ---------------------------------------------------------------------------


class TestGoldenQAIntegration:
    """실제 Golden QA 파일 기반 통합 테스트."""

    def test_100_questions_loaded(self):
        v1_path = Path("eval/questions.golden_v1.jsonl")
        v2_path = Path("eval/questions.golden_v2.jsonl")
        questions = load_all_golden_questions(v1_path, v2_path)
        assert len(questions) == 100

    def test_query_type_distribution(self):
        v1_path = Path("eval/questions.golden_v1.jsonl")
        v2_path = Path("eval/questions.golden_v2.jsonl")
        questions = load_all_golden_questions(v1_path, v2_path)
        types = {}
        for q in questions:
            types[q.query_type] = types.get(q.query_type, 0) + 1
        # 각 유형이 10개 이상
        for qt, count in types.items():
            assert count >= 10, f"{qt}가 {count}개로 부족"

    def test_difficulty_distribution(self):
        v1_path = Path("eval/questions.golden_v1.jsonl")
        v2_path = Path("eval/questions.golden_v2.jsonl")
        questions = load_all_golden_questions(v1_path, v2_path)
        diffs = {}
        for q in questions:
            diffs[q.difficulty] = diffs.get(q.difficulty, 0) + 1
        # 각 난이도가 15개 이상
        for d, count in diffs.items():
            assert count >= 15, f"{d}가 {count}개로 부족"

    def test_regression_checks_count(self):
        v1_path = Path("eval/questions.golden_v1.jsonl")
        v2_path = Path("eval/questions.golden_v2.jsonl")
        questions = load_all_golden_questions(v1_path, v2_path)
        with_checks = [q for q in questions if q.regression_checks]
        assert len(with_checks) >= 7, f"회귀 검사 문항 {len(with_checks)}개로 부족"

    def test_full_edition_coverage(self):
        v1_path = Path("eval/questions.golden_v1.jsonl")
        v2_path = Path("eval/questions.golden_v2.jsonl")
        questions = load_all_golden_questions(v1_path, v2_path)
        coverages = compute_edition_coverages(questions)
        score = compute_coverage_score(coverages)
        assert score == 100.0, f"커버리지 {score}% — 일부 개정판 누락"

    def test_expected_keywords_present(self):
        v1_path = Path("eval/questions.golden_v1.jsonl")
        v2_path = Path("eval/questions.golden_v2.jsonl")
        questions = load_all_golden_questions(v1_path, v2_path)
        for q in questions:
            assert len(q.expected_keywords) >= 1, f"{q.id}: expected_keywords 없음"
