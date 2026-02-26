"""Quality Gate 테스트.

PR-016: MVP 품질 게이트 로직 + 보고서 생성.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.quality_gate import (  # noqa: E402
    DEFAULT_PASS_RATE_THRESHOLD,
    DEFAULT_THRESHOLDS,
    EVAL_AXES,
    AxisStats,
    EvalResult,
    QualityReport,
    compute_axis_stats,
    evaluate_quality_gate,
    format_report_json,
    format_report_markdown,
    load_eval_results,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_eval_result(
    id: str = "q-001",
    passed: bool = True,
    judge_passed: bool = True,
    regression_passed: bool = True,
    scores: dict | None = None,
) -> EvalResult:
    """테스트용 EvalResult."""
    default_scores = {
        "relevance": 4.5,
        "faithfulness": 4.0,
        "quote_accuracy": 4.0,
        "temporal_correctness": 4.5,
    }
    return EvalResult(
        id=id,
        query="테스트 질의",
        query_type="single_version",
        passed=passed,
        judge_passed=judge_passed,
        regression_passed=regression_passed,
        scores=scores or default_scores,
        regression_failures=() if regression_passed else ("failure1",),
    )


def _make_results_jsonl(results: list[dict], path: Path) -> Path:
    """테스트용 results.jsonl 파일."""
    with open(path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


# ---------------------------------------------------------------------------
# EvalResult 테스트
# ---------------------------------------------------------------------------


def test_eval_result_is_frozen():
    """EvalResult는 불변이다."""
    result = _make_eval_result()
    with pytest.raises(AttributeError):
        result.passed = False  # type: ignore[misc]


def test_eval_result_fields():
    """EvalResult 필드가 올바르다."""
    result = _make_eval_result(id="q-005", passed=False)
    assert result.id == "q-005"
    assert result.passed is False
    assert result.scores["relevance"] == 4.5


# ---------------------------------------------------------------------------
# AxisStats 테스트
# ---------------------------------------------------------------------------


def test_axis_stats_is_frozen():
    """AxisStats는 불변이다."""
    stat = AxisStats(
        axis="relevance",
        mean=4.0,
        min_val=3.0,
        max_val=5.0,
        threshold=3.5,
        above_threshold=4,
        total=5,
    )
    with pytest.raises(AttributeError):
        stat.mean = 5.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# compute_axis_stats 테스트
# ---------------------------------------------------------------------------


def test_compute_axis_stats_basic():
    """기본 통계 계산."""
    results = [
        _make_eval_result(
            scores={
                "relevance": 5.0,
                "faithfulness": 4.0,
                "quote_accuracy": 3.0,
                "temporal_correctness": 4.0,
            }
        ),
        _make_eval_result(
            scores={
                "relevance": 3.0,
                "faithfulness": 5.0,
                "quote_accuracy": 5.0,
                "temporal_correctness": 5.0,
            }
        ),
    ]
    stats = compute_axis_stats(results)
    assert len(stats) == 4

    relevance = stats[0]
    assert relevance.axis == "relevance"
    assert relevance.mean == 4.0
    assert relevance.min_val == 3.0
    assert relevance.max_val == 5.0


def test_compute_axis_stats_empty():
    """빈 결과는 빈 tuple."""
    stats = compute_axis_stats([])
    assert stats == ()


def test_compute_axis_stats_above_threshold():
    """기준 이상 개수 계산."""
    results = [
        _make_eval_result(
            scores={
                "relevance": 4.0,
                "faithfulness": 4.0,
                "quote_accuracy": 4.0,
                "temporal_correctness": 4.0,
            }
        ),
        _make_eval_result(
            scores={
                "relevance": 2.0,
                "faithfulness": 3.0,
                "quote_accuracy": 3.0,
                "temporal_correctness": 2.0,
            }
        ),
        _make_eval_result(
            scores={
                "relevance": 5.0,
                "faithfulness": 5.0,
                "quote_accuracy": 5.0,
                "temporal_correctness": 5.0,
            }
        ),
    ]
    stats = compute_axis_stats(results)
    relevance = stats[0]
    # threshold=3.5, values=[4.0, 2.0, 5.0] → 2 above
    assert relevance.above_threshold == 2


# ---------------------------------------------------------------------------
# evaluate_quality_gate 테스트
# ---------------------------------------------------------------------------


def test_gate_pass():
    """모든 항목 통과 → PASS."""
    results = [_make_eval_result(id=f"q-{i:03d}") for i in range(5)]
    report = evaluate_quality_gate(results)
    assert report.gate_passed is True
    assert report.pass_rate == 100.0
    assert report.passed_count == 5
    assert report.failed_count == 0


def test_gate_fail_low_pass_rate():
    """통과율 미달 → FAIL."""
    results = [
        _make_eval_result(id="q-001", passed=True),
        _make_eval_result(id="q-002", passed=False),
        _make_eval_result(id="q-003", passed=False),
        _make_eval_result(id="q-004", passed=False),
        _make_eval_result(id="q-005", passed=False),
    ]
    report = evaluate_quality_gate(results)
    assert report.gate_passed is False
    assert report.pass_rate == 20.0
    assert report.failed_count == 4


def test_gate_custom_threshold():
    """커스텀 통과율 임계값."""
    results = [
        _make_eval_result(id="q-001", passed=True),
        _make_eval_result(id="q-002", passed=True),
        _make_eval_result(id="q-003", passed=False),
    ]
    # 66.7% pass rate, threshold=50% → PASS
    report = evaluate_quality_gate(results, pass_rate_threshold=50.0)
    assert report.gate_passed is True

    # 66.7% pass rate, threshold=70% → FAIL
    report = evaluate_quality_gate(results, pass_rate_threshold=70.0)
    assert report.gate_passed is False


def test_gate_empty_results():
    """빈 결과 → FAIL."""
    report = evaluate_quality_gate([])
    assert report.gate_passed is False
    assert report.total_questions == 0


def test_gate_regression_failures():
    """회귀 실패 카운트."""
    results = [
        _make_eval_result(id="q-001", regression_passed=False),
        _make_eval_result(id="q-002", regression_passed=True),
        _make_eval_result(id="q-003", regression_passed=False),
    ]
    report = evaluate_quality_gate(results)
    assert report.regression_failure_count == 2


def test_gate_failed_questions_list():
    """실패 문항 목록."""
    results = [
        _make_eval_result(id="q-001", passed=True),
        _make_eval_result(id="q-002", passed=False),
        _make_eval_result(id="q-003", passed=False),
    ]
    report = evaluate_quality_gate(results)
    assert "q-002" in report.failed_questions
    assert "q-003" in report.failed_questions
    assert "q-001" not in report.failed_questions


def test_gate_includes_axis_stats():
    """보고서에 축별 통계 포함."""
    results = [_make_eval_result() for _ in range(3)]
    report = evaluate_quality_gate(results)
    assert len(report.axis_stats) == 4
    assert report.axis_stats[0].axis == "relevance"


def test_quality_report_is_frozen():
    """QualityReport는 불변이다."""
    report = evaluate_quality_gate([_make_eval_result()])
    with pytest.raises(AttributeError):
        report.gate_passed = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# load_eval_results 테스트
# ---------------------------------------------------------------------------


def test_load_eval_results(tmp_path):
    """results.jsonl에서 결과를 로드한다."""
    results_data = [
        {
            "id": "q-001",
            "query": "테스트",
            "query_type": "single_version",
            "passed": True,
            "judge_passed": True,
            "regression_passed": True,
            "scores": {
                "relevance": 4,
                "faithfulness": 5,
                "quote_accuracy": 4,
                "temporal_correctness": 5,
            },
            "regression_failures": [],
        },
        {
            "id": "q-002",
            "query": "테스트2",
            "query_type": "definition",
            "passed": False,
            "judge_passed": False,
            "regression_passed": True,
            "scores": {
                "relevance": 2,
                "faithfulness": 3,
                "quote_accuracy": 2,
                "temporal_correctness": 3,
            },
            "regression_failures": [],
        },
    ]
    path = _make_results_jsonl(results_data, tmp_path / "results.jsonl")
    results = load_eval_results(path)
    assert len(results) == 2
    assert results[0].id == "q-001"
    assert results[0].passed is True
    assert results[1].passed is False


def test_load_eval_results_empty_file(tmp_path):
    """빈 파일은 빈 리스트."""
    path = tmp_path / "results.jsonl"
    path.write_text("")
    results = load_eval_results(path)
    assert results == []


def test_load_eval_results_nonexistent():
    """존재하지 않는 파일은 빈 리스트."""
    results = load_eval_results(Path("/nonexistent/results.jsonl"))
    assert results == []


def test_load_eval_results_invalid_json(tmp_path):
    """유효하지 않은 JSON 행은 건너뛴다."""
    path = tmp_path / "results.jsonl"
    path.write_text(
        '{"id": "q-001", "passed": true, "scores": {}}\n'
        "invalid json line\n"
        '{"id": "q-002", "passed": false, "scores": {}}\n'
    )
    results = load_eval_results(path)
    assert len(results) == 2


# ---------------------------------------------------------------------------
# format_report_markdown 테스트
# ---------------------------------------------------------------------------


def test_report_markdown_pass():
    """통과 보고서 Markdown."""
    results = [_make_eval_result() for _ in range(5)]
    report = evaluate_quality_gate(results)
    md = format_report_markdown(report)
    assert "PASS" in md
    assert "100.0%" in md
    assert "통과율" in md
    assert "축별 통계" in md


def test_report_markdown_fail():
    """실패 보고서 Markdown."""
    results = [
        _make_eval_result(id="q-001", passed=True),
        _make_eval_result(id="q-002", passed=False),
        _make_eval_result(id="q-003", passed=False),
        _make_eval_result(id="q-004", passed=False),
        _make_eval_result(id="q-005", passed=False),
    ]
    report = evaluate_quality_gate(results)
    md = format_report_markdown(report)
    assert "FAIL" in md
    assert "실패 문항" in md
    assert "q-002" in md


def test_report_markdown_has_table():
    """보고서에 축별 통계 테이블 포함."""
    results = [_make_eval_result()]
    report = evaluate_quality_gate(results)
    md = format_report_markdown(report)
    assert "| 축 |" in md
    assert "relevance" in md
    assert "faithfulness" in md


# ---------------------------------------------------------------------------
# format_report_json 테스트
# ---------------------------------------------------------------------------


def test_report_json_structure():
    """JSON 보고서 구조."""
    results = [_make_eval_result()]
    report = evaluate_quality_gate(results)
    data = format_report_json(report)
    assert "gate_passed" in data
    assert "total_questions" in data
    assert "axis_stats" in data
    assert isinstance(data["axis_stats"], list)
    assert len(data["axis_stats"]) == 4


def test_report_json_serializable():
    """JSON 보고서는 직렬화 가능하다."""
    results = [_make_eval_result()]
    report = evaluate_quality_gate(results)
    data = format_report_json(report)
    # json.dumps가 에러 없이 실행되어야 한다
    json_str = json.dumps(data, ensure_ascii=False)
    assert len(json_str) > 0


# ---------------------------------------------------------------------------
# Constants 테스트
# ---------------------------------------------------------------------------


def test_eval_axes():
    """4개 평가 축."""
    assert len(EVAL_AXES) == 4
    assert "relevance" in EVAL_AXES
    assert "faithfulness" in EVAL_AXES


def test_default_thresholds():
    """기본 임계값."""
    assert DEFAULT_THRESHOLDS["faithfulness"] == 4.0
    assert DEFAULT_THRESHOLDS["relevance"] == 3.5


def test_default_pass_rate():
    """기본 통과율."""
    assert DEFAULT_PASS_RATE_THRESHOLD == 80.0
