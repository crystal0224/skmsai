"""V1QualityReport — V1 품질 보고서 생성 서비스.

PR-030: Golden QA 50 기반 V1 품질 보고서 생성.

기능:
- Golden QA 질의 로드 (JSONL)
- 평가 결과 분석 (query_type별, difficulty별 분류)
- V1 품질 보고서 생성 (Markdown + JSON)
- QualityGate 통합 (축별 통계 + Go/No-Go 판정)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.lib.quality_gate import (
    DEFAULT_PASS_RATE_THRESHOLD,
    DEFAULT_THRESHOLDS,
    EVAL_AXES,
    AxisStats,
    EvalResult,
    QualityReport,
    compute_axis_stats,
    evaluate_quality_gate,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GoldenQuestion — 골든 QA 질의 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GoldenQuestion:
    """Golden QA 질의.

    Attributes:
        id: 질의 식별자
        query: 질의 텍스트
        query_type: 질의 유형 (single_version, cross_version, definition, open_ended)
        expected_edition: 기대 개정판 (None이면 미지정)
        expected_keywords: 기대 키워드
        difficulty: 난이도 (easy, medium, hard)
        regression_checks: 회귀 검사 설정 (빈 튜플이면 없음)
    """

    id: str
    query: str
    query_type: str
    expected_edition: str | None
    expected_keywords: tuple[str, ...]
    difficulty: str
    regression_checks: tuple[dict[str, Any], ...]


# ---------------------------------------------------------------------------
# QueryTypeBreakdown — 질의 유형별 분석 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QueryTypeBreakdown:
    """질의 유형별 분석 결과.

    Attributes:
        query_type: 질의 유형
        total: 전체 문항 수
        passed: 통과 문항 수
        failed: 실패 문항 수
        pass_rate: 통과율 (%)
        axis_stats: 축별 통계
    """

    query_type: str
    total: int
    passed: int
    failed: int
    pass_rate: float
    axis_stats: tuple[AxisStats, ...]


# ---------------------------------------------------------------------------
# DifficultyBreakdown — 난이도별 분석 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DifficultyBreakdown:
    """난이도별 분석 결과.

    Attributes:
        difficulty: 난이도 (easy, medium, hard)
        total: 전체 문항 수
        passed: 통과 문항 수
        failed: 실패 문항 수
        pass_rate: 통과율 (%)
    """

    difficulty: str
    total: int
    passed: int
    failed: int
    pass_rate: float


# ---------------------------------------------------------------------------
# V1QualityReport — V1 품질 보고서 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class V1QualityReport:
    """V1 품질 보고서.

    Attributes:
        quality_report: 전체 품질 보고서 (QualityGate)
        query_type_breakdowns: 질의 유형별 분석
        difficulty_breakdowns: 난이도별 분석
        golden_question_count: Golden QA 전체 문항 수
        evaluated_count: 평가 완료 문항 수
        regression_total: 회귀 검사 포함 문항 수
        regression_passed: 회귀 검사 통과 문항 수
    """

    quality_report: QualityReport
    query_type_breakdowns: tuple[QueryTypeBreakdown, ...]
    difficulty_breakdowns: tuple[DifficultyBreakdown, ...]
    golden_question_count: int
    evaluated_count: int
    regression_total: int
    regression_passed: int


# ---------------------------------------------------------------------------
# Golden QA 로드
# ---------------------------------------------------------------------------


def load_golden_questions(path: Path) -> list[GoldenQuestion]:
    """Golden QA JSONL 파일을 로드한다.

    Args:
        path: JSONL 파일 경로

    Returns:
        GoldenQuestion 리스트
    """
    if not path.exists():
        logger.warning("Golden QA 파일 없음: %s", path)
        return []

    questions: list[GoldenQuestion] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                questions.append(_parse_golden_question(data))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Golden QA 파싱 실패: %s", e)

    return questions


def _parse_golden_question(data: dict[str, Any]) -> GoldenQuestion:
    """JSON dict를 GoldenQuestion으로 변환한다."""
    return GoldenQuestion(
        id=data["id"],
        query=data["query"],
        query_type=data.get("query_type", "unknown"),
        expected_edition=data.get("expected_edition"),
        expected_keywords=tuple(data.get("expected_keywords", [])),
        difficulty=data.get("difficulty", "medium"),
        regression_checks=tuple(data.get("regression_checks", [])),
    )


# ---------------------------------------------------------------------------
# 분석 함수
# ---------------------------------------------------------------------------


def compute_query_type_breakdowns(
    results: list[EvalResult],
    thresholds: dict[str, float] | None = None,
) -> tuple[QueryTypeBreakdown, ...]:
    """질의 유형별 분석을 수행한다.

    Args:
        results: 평가 결과 리스트
        thresholds: 축별 임계값

    Returns:
        QueryTypeBreakdown 튜플 (유형별 정렬)
    """
    thresholds = thresholds or DEFAULT_THRESHOLDS

    # 유형별 그룹화
    type_groups: dict[str, list[EvalResult]] = {}
    for r in results:
        qt = r.query_type
        if qt not in type_groups:
            type_groups[qt] = []
        type_groups[qt].append(r)

    breakdowns: list[QueryTypeBreakdown] = []
    for qt in sorted(type_groups.keys()):
        group = type_groups[qt]
        total = len(group)
        passed = sum(1 for r in group if r.passed)
        pass_rate = (passed / total) * 100 if total > 0 else 0.0
        axis_stats = compute_axis_stats(group, thresholds)

        breakdowns.append(
            QueryTypeBreakdown(
                query_type=qt,
                total=total,
                passed=passed,
                failed=total - passed,
                pass_rate=round(pass_rate, 1),
                axis_stats=axis_stats,
            )
        )

    return tuple(breakdowns)


def compute_difficulty_breakdowns(
    results: list[EvalResult],
    questions: list[GoldenQuestion],
) -> tuple[DifficultyBreakdown, ...]:
    """난이도별 분석을 수행한다.

    Args:
        results: 평가 결과 리스트
        questions: Golden QA 질의 리스트

    Returns:
        DifficultyBreakdown 튜플 (easy → medium → hard 순)
    """
    # 질의 ID → 난이도 매핑
    difficulty_map: dict[str, str] = {q.id: q.difficulty for q in questions}

    # 난이도별 그룹화
    diff_groups: dict[str, list[EvalResult]] = {}
    for r in results:
        difficulty = difficulty_map.get(r.id, "unknown")
        if difficulty not in diff_groups:
            diff_groups[difficulty] = []
        diff_groups[difficulty].append(r)

    # easy → medium → hard 순서
    order = {"easy": 0, "medium": 1, "hard": 2}
    breakdowns: list[DifficultyBreakdown] = []

    for diff in sorted(diff_groups.keys(), key=lambda d: order.get(d, 99)):
        group = diff_groups[diff]
        total = len(group)
        passed = sum(1 for r in group if r.passed)
        pass_rate = (passed / total) * 100 if total > 0 else 0.0

        breakdowns.append(
            DifficultyBreakdown(
                difficulty=diff,
                total=total,
                passed=passed,
                failed=total - passed,
                pass_rate=round(pass_rate, 1),
            )
        )

    return tuple(breakdowns)


# ---------------------------------------------------------------------------
# V1 보고서 생성
# ---------------------------------------------------------------------------


def generate_v1_report(
    results: list[EvalResult],
    questions: list[GoldenQuestion],
    thresholds: dict[str, float] | None = None,
    pass_rate_threshold: float = DEFAULT_PASS_RATE_THRESHOLD,
) -> V1QualityReport:
    """V1 품질 보고서를 생성한다.

    Args:
        results: 평가 결과 리스트
        questions: Golden QA 질의 리스트
        thresholds: 축별 임계값
        pass_rate_threshold: 통과율 임계값

    Returns:
        V1QualityReport (불변)
    """
    thresholds = thresholds or DEFAULT_THRESHOLDS

    # 전체 품질 보고서
    quality_report = evaluate_quality_gate(results, thresholds, pass_rate_threshold)

    # 유형별 분석
    type_breakdowns = compute_query_type_breakdowns(results, thresholds)

    # 난이도별 분석
    diff_breakdowns = compute_difficulty_breakdowns(results, questions)

    # 회귀 검사 통계
    question_map = {q.id: q for q in questions}
    regression_total = sum(
        1
        for r in results
        if r.id in question_map and question_map[r.id].regression_checks
    )
    regression_passed = sum(
        1
        for r in results
        if r.id in question_map
        and question_map[r.id].regression_checks
        and r.regression_passed
    )

    return V1QualityReport(
        quality_report=quality_report,
        query_type_breakdowns=type_breakdowns,
        difficulty_breakdowns=diff_breakdowns,
        golden_question_count=len(questions),
        evaluated_count=len(results),
        regression_total=regression_total,
        regression_passed=regression_passed,
    )


# ---------------------------------------------------------------------------
# 보고서 포맷팅 — Markdown
# ---------------------------------------------------------------------------


def format_v1_report_markdown(report: V1QualityReport) -> str:
    """V1 품질 보고서를 Markdown으로 포맷팅한다.

    Args:
        report: V1QualityReport

    Returns:
        Markdown 문자열
    """
    qr = report.quality_report
    gate_label = "PASS" if qr.gate_passed else "FAIL"

    lines: list[str] = []

    # 헤더
    lines.append(f"# V1 Quality Report — {gate_label}")
    lines.append("")
    lines.append("## 개요")
    lines.append("")
    lines.append(f"- **Golden QA 문항**: {report.golden_question_count}")
    lines.append(f"- **평가 완료**: {report.evaluated_count}")
    lines.append(f"- **통과**: {qr.passed_count}")
    lines.append(f"- **실패**: {qr.failed_count}")
    lines.append(f"- **통과율**: {qr.pass_rate}% (기준: {qr.pass_rate_threshold}%)")
    lines.append(f"- **회귀 검사**: {report.regression_passed}/{report.regression_total}")
    lines.append(f"- **판정**: **{gate_label}**")
    lines.append("")

    # 축별 통계
    lines.append("## 축별 통계")
    lines.append("")
    lines.append("| 축 | 평균 | 최소 | 최대 | 기준 | 기준 이상 |")
    lines.append("|---|---|---|---|---|---|")
    for stat in qr.axis_stats:
        lines.append(
            f"| {stat.axis} | {stat.mean:.2f} | {stat.min_val:.1f} | "
            f"{stat.max_val:.1f} | {stat.threshold:.1f} | "
            f"{stat.above_threshold}/{stat.total} |"
        )
    lines.append("")

    # 질의 유형별 분석
    lines.append("## 질의 유형별 분석")
    lines.append("")
    lines.append("| 유형 | 문항 | 통과 | 실패 | 통과율 |")
    lines.append("|---|---|---|---|---|")
    for bd in report.query_type_breakdowns:
        lines.append(
            f"| {bd.query_type} | {bd.total} | {bd.passed} | "
            f"{bd.failed} | {bd.pass_rate}% |"
        )
    lines.append("")

    # 난이도별 분석
    lines.append("## 난이도별 분석")
    lines.append("")
    lines.append("| 난이도 | 문항 | 통과 | 실패 | 통과율 |")
    lines.append("|---|---|---|---|---|")
    for bd in report.difficulty_breakdowns:
        lines.append(
            f"| {bd.difficulty} | {bd.total} | {bd.passed} | "
            f"{bd.failed} | {bd.pass_rate}% |"
        )
    lines.append("")

    # 유형별 축별 상세
    lines.append("## 유형별 축별 상세")
    lines.append("")
    for bd in report.query_type_breakdowns:
        if bd.axis_stats:
            lines.append(f"### {bd.query_type}")
            lines.append("")
            lines.append("| 축 | 평균 | 최소 | 최대 | 기준 이상 |")
            lines.append("|---|---|---|---|---|")
            for stat in bd.axis_stats:
                lines.append(
                    f"| {stat.axis} | {stat.mean:.2f} | {stat.min_val:.1f} | "
                    f"{stat.max_val:.1f} | {stat.above_threshold}/{stat.total} |"
                )
            lines.append("")

    # 실패 문항
    if qr.failed_questions:
        lines.append("## 실패 문항")
        lines.append("")
        for q_id in qr.failed_questions:
            lines.append(f"- {q_id}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 보고서 포맷팅 — JSON
# ---------------------------------------------------------------------------


def format_v1_report_json(report: V1QualityReport) -> dict[str, Any]:
    """V1 품질 보고서를 JSON 직렬화 가능한 dict로 변환한다.

    Args:
        report: V1QualityReport

    Returns:
        JSON 직렬화 가능한 dict
    """
    qr = report.quality_report

    return {
        "gate_passed": qr.gate_passed,
        "golden_question_count": report.golden_question_count,
        "evaluated_count": report.evaluated_count,
        "passed_count": qr.passed_count,
        "failed_count": qr.failed_count,
        "pass_rate": qr.pass_rate,
        "pass_rate_threshold": qr.pass_rate_threshold,
        "regression": {
            "total": report.regression_total,
            "passed": report.regression_passed,
        },
        "thresholds": qr.thresholds,
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
            for s in qr.axis_stats
        ],
        "query_type_breakdowns": [
            {
                "query_type": bd.query_type,
                "total": bd.total,
                "passed": bd.passed,
                "failed": bd.failed,
                "pass_rate": bd.pass_rate,
            }
            for bd in report.query_type_breakdowns
        ],
        "difficulty_breakdowns": [
            {
                "difficulty": bd.difficulty,
                "total": bd.total,
                "passed": bd.passed,
                "failed": bd.failed,
                "pass_rate": bd.pass_rate,
            }
            for bd in report.difficulty_breakdowns
        ],
        "failed_questions": list(qr.failed_questions),
    }
