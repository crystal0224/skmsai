"""Quality Gate — MVP 품질 게이트 로직.

PR-016: 평가 결과를 분석하여 Go/No-Go 판정을 내린다.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 데이터 모델 (불변)
# ---------------------------------------------------------------------------

EVAL_AXES = ("relevance", "faithfulness", "quote_accuracy", "temporal_correctness")

DEFAULT_THRESHOLDS = {
    "faithfulness": 4.0,
    "relevance": 3.5,
    "quote_accuracy": 3.5,
    "temporal_correctness": 3.5,
}

DEFAULT_PASS_RATE_THRESHOLD = 80.0


@dataclass(frozen=True)
class EvalResult:
    """단일 평가 결과."""

    id: str
    query: str
    query_type: str
    passed: bool
    judge_passed: bool
    regression_passed: bool
    scores: dict[str, float]
    regression_failures: tuple[str, ...]


@dataclass(frozen=True)
class AxisStats:
    """단일 평가 축의 통계."""

    axis: str
    mean: float
    min_val: float
    max_val: float
    threshold: float
    above_threshold: int
    total: int


@dataclass(frozen=True)
class QualityReport:
    """MVP 품질 보고서."""

    total_questions: int
    passed_count: int
    failed_count: int
    pass_rate: float
    pass_rate_threshold: float
    gate_passed: bool
    axis_stats: tuple[AxisStats, ...]
    regression_failure_count: int
    failed_questions: tuple[str, ...]
    thresholds: dict[str, float]


# ---------------------------------------------------------------------------
# 평가 결과 로드
# ---------------------------------------------------------------------------


def load_eval_results(path: Path) -> list[EvalResult]:
    """eval/results.jsonl에서 평가 결과를 로드한다."""
    if not path.exists():
        logger.warning("평가 결과 파일 없음: %s", path)
        return []

    results: list[EvalResult] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                results.append(_parse_eval_result(data))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("평가 결과 파싱 실패: %s", e)

    return results


def _parse_eval_result(data: dict[str, Any]) -> EvalResult:
    """JSON dict를 EvalResult로 변환한다."""
    scores = data.get("scores", {})
    return EvalResult(
        id=data["id"],
        query=data.get("query", ""),
        query_type=data.get("query_type", "unknown"),
        passed=data.get("passed", False),
        judge_passed=data.get("judge_passed", False),
        regression_passed=data.get("regression_passed", True),
        scores={axis: float(scores.get(axis, 0.0)) for axis in EVAL_AXES},
        regression_failures=tuple(data.get("regression_failures", [])),
    )


# ---------------------------------------------------------------------------
# 품질 분석
# ---------------------------------------------------------------------------


def compute_axis_stats(
    results: list[EvalResult],
    thresholds: dict[str, float] | None = None,
) -> tuple[AxisStats, ...]:
    """각 평가 축의 통계를 계산한다."""
    if not results:
        return ()

    thresholds = thresholds or DEFAULT_THRESHOLDS
    stats: list[AxisStats] = []

    for axis in EVAL_AXES:
        values = [r.scores.get(axis, 0.0) for r in results]
        threshold = thresholds.get(axis, 3.0)
        above = sum(1 for v in values if v >= threshold)

        stats.append(
            AxisStats(
                axis=axis,
                mean=sum(values) / len(values),
                min_val=min(values),
                max_val=max(values),
                threshold=threshold,
                above_threshold=above,
                total=len(values),
            )
        )

    return tuple(stats)


def evaluate_quality_gate(
    results: list[EvalResult],
    thresholds: dict[str, float] | None = None,
    pass_rate_threshold: float = DEFAULT_PASS_RATE_THRESHOLD,
) -> QualityReport:
    """평가 결과를 분석하여 Go/No-Go 판정을 내린다.

    Args:
        results: 평가 결과 리스트.
        thresholds: 축별 점수 임계값.
        pass_rate_threshold: 통과율 임계값 (%).

    Returns:
        QualityReport (불변).
    """
    thresholds = thresholds or DEFAULT_THRESHOLDS
    total = len(results)

    if total == 0:
        return QualityReport(
            total_questions=0,
            passed_count=0,
            failed_count=0,
            pass_rate=0.0,
            pass_rate_threshold=pass_rate_threshold,
            gate_passed=False,
            axis_stats=(),
            regression_failure_count=0,
            failed_questions=(),
            thresholds=dict(thresholds),
        )

    passed_count = sum(1 for r in results if r.passed)
    failed_count = total - passed_count
    pass_rate = (passed_count / total) * 100

    regression_failure_count = sum(1 for r in results if not r.regression_passed)

    failed_questions = tuple(r.id for r in results if not r.passed)
    axis_stats = compute_axis_stats(results, thresholds)

    gate_passed = pass_rate >= pass_rate_threshold

    return QualityReport(
        total_questions=total,
        passed_count=passed_count,
        failed_count=failed_count,
        pass_rate=round(pass_rate, 1),
        pass_rate_threshold=pass_rate_threshold,
        gate_passed=gate_passed,
        axis_stats=axis_stats,
        regression_failure_count=regression_failure_count,
        failed_questions=failed_questions,
        thresholds=dict(thresholds),
    )


# ---------------------------------------------------------------------------
# 보고서 생성
# ---------------------------------------------------------------------------


def format_report_markdown(report: QualityReport) -> str:
    """품질 보고서를 Markdown 형식으로 포맷팅한다."""
    gate_emoji = "PASS" if report.gate_passed else "FAIL"
    lines = [
        f"# MVP Quality Gate Report — {gate_emoji}",
        "",
        f"- **총 평가 문항**: {report.total_questions}",
        f"- **통과**: {report.passed_count}",
        f"- **실패**: {report.failed_count}",
        f"- **통과율**: {report.pass_rate}% (기준: {report.pass_rate_threshold}%)",
        f"- **회귀 실패**: {report.regression_failure_count}건",
        "",
        "## 축별 통계",
        "",
        "| 축 | 평균 | 최소 | 최대 | 기준 | 기준 이상 |",
        "|---|---|---|---|---|---|",
    ]

    for stat in report.axis_stats:
        lines.append(
            f"| {stat.axis} | {stat.mean:.2f} | {stat.min_val:.1f} | "
            f"{stat.max_val:.1f} | {stat.threshold:.1f} | "
            f"{stat.above_threshold}/{stat.total} |"
        )

    if report.failed_questions:
        lines.extend(
            [
                "",
                "## 실패 문항",
                "",
            ]
        )
        for q_id in report.failed_questions:
            lines.append(f"- {q_id}")

    lines.extend(
        [
            "",
            f"## 판정: **{gate_emoji}**",
            "",
        ]
    )

    if report.gate_passed:
        lines.append(
            f"통과율 {report.pass_rate}%가 기준 {report.pass_rate_threshold}%를 "
            "충족합니다. MVP 품질 게이트를 통과했습니다."
        )
    else:
        lines.append(
            f"통과율 {report.pass_rate}%가 기준 {report.pass_rate_threshold}%에 "
            "미달합니다. 품질 개선이 필요합니다."
        )

    return "\n".join(lines)


def format_report_json(report: QualityReport) -> dict[str, Any]:
    """품질 보고서를 JSON 직렬화 가능한 dict로 변환한다."""
    return {
        "gate_passed": report.gate_passed,
        "total_questions": report.total_questions,
        "passed_count": report.passed_count,
        "failed_count": report.failed_count,
        "pass_rate": report.pass_rate,
        "pass_rate_threshold": report.pass_rate_threshold,
        "regression_failure_count": report.regression_failure_count,
        "thresholds": report.thresholds,
        "axis_stats": [
            {
                "axis": s.axis,
                "mean": round(s.mean, 2),
                "min": s.min_val,
                "max": s.max_val,
                "threshold": s.threshold,
                "above_threshold": s.above_threshold,
                "total": s.total,
            }
            for s in report.axis_stats
        ],
        "failed_questions": list(report.failed_questions),
    }
