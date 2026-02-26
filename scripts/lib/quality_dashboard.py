"""최종 품질 대시보드 — Golden QA 100 기반 V2 품질 보고서.

PR-039: V1 품질 보고서를 확장하여 100문항 기반 최종 품질 대시보드 제공.

기능:
- Golden QA V1(50) + V2(50) 통합 로드
- 커버리지 분석 (개정판별 문항 분포)
- V2 품질 보고서 생성 (V1 확장 + 커버리지 + 트렌드)
- 품질 대시보드 API 데이터 생성
"""
from __future__ import annotations

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
from scripts.lib.quality_report import (
    DifficultyBreakdown,
    GoldenQuestion,
    QueryTypeBreakdown,
    V1QualityReport,
    compute_difficulty_breakdowns,
    compute_query_type_breakdowns,
    generate_v1_report,
    load_golden_questions,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# EditionCoverage — 개정판별 커버리지 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EditionCoverage:
    """개정판별 Golden QA 커버리지.

    Attributes:
        edition: 개정판 식별자 (예: "14차", "초판")
        question_count: 해당 개정판 관련 문항 수
        query_types: 포함된 질의 유형
        difficulties: 포함된 난이도
    """

    edition: str
    question_count: int
    query_types: tuple[str, ...]
    difficulties: tuple[str, ...]


# ---------------------------------------------------------------------------
# QualitySummary — 축별 요약 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QualitySummary:
    """축별 품질 요약.

    Attributes:
        axis: 평가 축
        mean_score: 전체 평균 점수
        pass_rate: 기준 이상 비율 (%)
        weakest_type: 가장 낮은 점수의 질의 유형
        weakest_type_mean: 가장 낮은 유형의 평균 점수
    """

    axis: str
    mean_score: float
    pass_rate: float
    weakest_type: str
    weakest_type_mean: float


# ---------------------------------------------------------------------------
# V2QualityReport — V2 품질 보고서 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class V2QualityReport:
    """V2 최종 품질 보고서.

    V1QualityReport를 확장하여 커버리지 분석, 축별 요약, 권장사항을 포함한다.

    Attributes:
        v1_report: V1 품질 보고서 (기반)
        edition_coverages: 개정판별 커버리지
        quality_summaries: 축별 품질 요약
        recommendations: 개선 권장사항
        coverage_score: 커버리지 점수 (0~100%)
        overall_grade: 종합 등급 (A/B/C/D/F)
    """

    v1_report: V1QualityReport
    edition_coverages: tuple[EditionCoverage, ...]
    quality_summaries: tuple[QualitySummary, ...]
    recommendations: tuple[str, ...]
    coverage_score: float
    overall_grade: str


# ---------------------------------------------------------------------------
# Golden QA 통합 로드
# ---------------------------------------------------------------------------


def load_all_golden_questions(
    v1_path: Path,
    v2_path: Path,
) -> list[GoldenQuestion]:
    """V1 + V2 Golden QA를 통합 로드한다.

    Args:
        v1_path: V1 JSONL 경로
        v2_path: V2 JSONL 경로

    Returns:
        통합된 GoldenQuestion 리스트
    """
    v1 = load_golden_questions(v1_path)
    v2 = load_golden_questions(v2_path)

    # ID 중복 검사
    seen_ids: set[str] = set()
    merged: list[GoldenQuestion] = []

    for q in v1 + v2:
        if q.id in seen_ids:
            logger.warning("중복 Golden QA ID: %s — 건너뜀", q.id)
            continue
        seen_ids.add(q.id)
        merged.append(q)

    logger.info("Golden QA 통합: V1=%d, V2=%d, 합계=%d", len(v1), len(v2), len(merged))
    return merged


# ---------------------------------------------------------------------------
# 커버리지 분석
# ---------------------------------------------------------------------------

# 알려진 개정판 목록
KNOWN_EDITIONS = (
    "초판",
    "1차",
    "10차",
    "11차",
    "12차",
    "13차",
    "14차",
)


def compute_edition_coverages(
    questions: list[GoldenQuestion],
) -> tuple[EditionCoverage, ...]:
    """개정판별 Golden QA 커버리지를 계산한다.

    Args:
        questions: Golden QA 질의 리스트

    Returns:
        EditionCoverage 튜플 (개정판별 정렬)
    """
    edition_data: dict[str, dict[str, set[str]]] = {}

    for q in questions:
        if q.expected_edition is None:
            continue
        ed = q.expected_edition
        if ed not in edition_data:
            edition_data[ed] = {"types": set(), "difficulties": set(), "ids": set()}
        edition_data[ed]["types"].add(q.query_type)
        edition_data[ed]["difficulties"].add(q.difficulty)
        edition_data[ed]["ids"].add(q.id)

    coverages: list[EditionCoverage] = []
    for ed in KNOWN_EDITIONS:
        data = edition_data.get(ed)
        if data:
            coverages.append(
                EditionCoverage(
                    edition=ed,
                    question_count=len(data["ids"]),
                    query_types=tuple(sorted(data["types"])),
                    difficulties=tuple(sorted(data["difficulties"])),
                )
            )
        else:
            coverages.append(
                EditionCoverage(
                    edition=ed,
                    question_count=0,
                    query_types=(),
                    difficulties=(),
                )
            )

    return tuple(coverages)


def compute_coverage_score(coverages: tuple[EditionCoverage, ...]) -> float:
    """커버리지 점수를 계산한다 (0~100%).

    모든 알려진 개정판에 최소 1개 문항이 있으면 100%.

    Args:
        coverages: 개정판별 커버리지

    Returns:
        커버리지 점수 (0~100)
    """
    if not coverages:
        return 0.0
    covered = sum(1 for c in coverages if c.question_count > 0)
    return round((covered / len(coverages)) * 100, 1)


# ---------------------------------------------------------------------------
# 축별 품질 요약
# ---------------------------------------------------------------------------


def compute_quality_summaries(
    results: list[EvalResult],
    type_breakdowns: tuple[QueryTypeBreakdown, ...],
    thresholds: dict[str, float] | None = None,
) -> tuple[QualitySummary, ...]:
    """축별 품질 요약을 계산한다.

    Args:
        results: 평가 결과 리스트
        type_breakdowns: 질의 유형별 분석
        thresholds: 축별 임계값

    Returns:
        QualitySummary 튜플
    """
    thresholds = thresholds or DEFAULT_THRESHOLDS

    if not results:
        return ()

    axis_stats = compute_axis_stats(results, thresholds)
    summaries: list[QualitySummary] = []

    for stat in axis_stats:
        # 유형별로 해당 축 평균 점수 비교 → 가장 약한 유형 탐색
        weakest_type = "unknown"
        weakest_mean = float("inf")

        for bd in type_breakdowns:
            for bd_stat in bd.axis_stats:
                if bd_stat.axis == stat.axis and bd_stat.mean < weakest_mean:
                    weakest_mean = bd_stat.mean
                    weakest_type = bd.query_type

        pass_rate = (stat.above_threshold / stat.total) * 100 if stat.total > 0 else 0.0

        summaries.append(
            QualitySummary(
                axis=stat.axis,
                mean_score=round(stat.mean, 2),
                pass_rate=round(pass_rate, 1),
                weakest_type=weakest_type,
                weakest_type_mean=round(weakest_mean, 2)
                if weakest_mean != float("inf")
                else 0.0,
            )
        )

    return tuple(summaries)


# ---------------------------------------------------------------------------
# 권장사항 생성
# ---------------------------------------------------------------------------


def generate_recommendations(
    report: V1QualityReport,
    summaries: tuple[QualitySummary, ...],
    coverage_score: float,
) -> tuple[str, ...]:
    """품질 개선 권장사항을 생성한다.

    Args:
        report: V1 품질 보고서
        summaries: 축별 품질 요약
        coverage_score: 커버리지 점수

    Returns:
        권장사항 문자열 튜플
    """
    recs: list[str] = []

    # 커버리지 부족
    if coverage_score < 100.0:
        recs.append(f"개정판 커버리지 {coverage_score}% — " "미커버 개정판에 대한 Golden QA 추가 필요")

    # 통과율 부족
    qr = report.quality_report
    if qr.pass_rate < qr.pass_rate_threshold:
        gap = qr.pass_rate_threshold - qr.pass_rate
        recs.append(
            f"통과율 {qr.pass_rate}%로 기준({qr.pass_rate_threshold}%) 미달 — "
            f"{gap:.1f}%p 개선 필요"
        )

    # 약한 축 탐색
    for s in summaries:
        threshold = DEFAULT_THRESHOLDS.get(s.axis, 3.5)
        if s.mean_score < threshold:
            recs.append(
                f"{s.axis} 축 평균 {s.mean_score}이 기준({threshold}) 미달 — "
                f"'{s.weakest_type}' 유형에서 특히 약함 (평균 {s.weakest_type_mean})"
            )

    # 회귀 검사 실패
    if report.regression_total > 0:
        reg_pass_rate = (report.regression_passed / report.regression_total) * 100
        if reg_pass_rate < 100.0:
            recs.append(
                f"회귀 검사 통과율 {reg_pass_rate:.0f}% — "
                f"{report.regression_total - report.regression_passed}건 실패 수정 필요"
            )

    # 난이도별 불균형
    for bd in report.difficulty_breakdowns:
        if bd.pass_rate < 70.0:
            recs.append(
                f"'{bd.difficulty}' 난이도 통과율 {bd.pass_rate}% — " "프롬프트 또는 검색 전략 개선 필요"
            )

    if not recs:
        recs.append("모든 품질 지표가 기준을 충족합니다. 추가 개선 불필요.")

    return tuple(recs)


# ---------------------------------------------------------------------------
# 종합 등급 산출
# ---------------------------------------------------------------------------


def compute_overall_grade(
    pass_rate: float,
    coverage_score: float,
    regression_rate: float,
) -> str:
    """종합 등급을 산출한다.

    Args:
        pass_rate: 통과율 (%)
        coverage_score: 커버리지 점수 (%)
        regression_rate: 회귀 검사 통과율 (%)

    Returns:
        등급 문자열 (A/B/C/D/F)
    """
    # 가중 평균: 통과율 50%, 커버리지 25%, 회귀 25%
    weighted = pass_rate * 0.50 + coverage_score * 0.25 + regression_rate * 0.25

    if weighted >= 90:
        return "A"
    if weighted >= 80:
        return "B"
    if weighted >= 70:
        return "C"
    if weighted >= 60:
        return "D"
    return "F"


# ---------------------------------------------------------------------------
# V2 보고서 생성
# ---------------------------------------------------------------------------


def generate_v2_report(
    results: list[EvalResult],
    questions: list[GoldenQuestion],
    thresholds: dict[str, float] | None = None,
    pass_rate_threshold: float = DEFAULT_PASS_RATE_THRESHOLD,
) -> V2QualityReport:
    """V2 최종 품질 보고서를 생성한다.

    Args:
        results: 평가 결과 리스트
        questions: 통합 Golden QA 리스트 (100개)
        thresholds: 축별 임계값
        pass_rate_threshold: 통과율 임계값

    Returns:
        V2QualityReport (불변)
    """
    thresholds = thresholds or DEFAULT_THRESHOLDS

    # V1 보고서 생성
    v1 = generate_v1_report(results, questions, thresholds, pass_rate_threshold)

    # 커버리지 분석
    coverages = compute_edition_coverages(questions)
    coverage_score = compute_coverage_score(coverages)

    # 축별 요약
    summaries = compute_quality_summaries(results, v1.query_type_breakdowns, thresholds)

    # 권장사항
    recommendations = generate_recommendations(v1, summaries, coverage_score)

    # 회귀 통과율
    regression_rate = (
        (v1.regression_passed / v1.regression_total) * 100
        if v1.regression_total > 0
        else 100.0
    )

    # 종합 등급
    grade = compute_overall_grade(
        v1.quality_report.pass_rate,
        coverage_score,
        regression_rate,
    )

    return V2QualityReport(
        v1_report=v1,
        edition_coverages=coverages,
        quality_summaries=summaries,
        recommendations=recommendations,
        coverage_score=coverage_score,
        overall_grade=grade,
    )


# ---------------------------------------------------------------------------
# 보고서 포맷팅 — Markdown
# ---------------------------------------------------------------------------


def format_v2_report_markdown(report: V2QualityReport) -> str:
    """V2 품질 보고서를 Markdown으로 포맷팅한다.

    Args:
        report: V2QualityReport

    Returns:
        Markdown 문자열
    """
    v1 = report.v1_report
    qr = v1.quality_report
    gate_label = "PASS" if qr.gate_passed else "FAIL"

    lines: list[str] = []

    # 헤더
    lines.append(
        f"# V2 Final Quality Report — {gate_label} (Grade: {report.overall_grade})"
    )
    lines.append("")

    # 개요
    lines.append("## 개요")
    lines.append("")
    lines.append(f"- **Golden QA 문항**: {v1.golden_question_count}")
    lines.append(f"- **평가 완료**: {v1.evaluated_count}")
    lines.append(f"- **통과**: {qr.passed_count}")
    lines.append(f"- **실패**: {qr.failed_count}")
    lines.append(f"- **통과율**: {qr.pass_rate}% (기준: {qr.pass_rate_threshold}%)")
    lines.append(f"- **회귀 검사**: {v1.regression_passed}/{v1.regression_total}")
    lines.append(f"- **커버리지**: {report.coverage_score}%")
    lines.append(f"- **종합 등급**: **{report.overall_grade}**")
    lines.append(f"- **판정**: **{gate_label}**")
    lines.append("")

    # 축별 품질 요약
    lines.append("## 축별 품질 요약")
    lines.append("")
    lines.append("| 축 | 평균 | 기준이상(%) | 약한 유형 | 약한 유형 평균 |")
    lines.append("|---|---|---|---|---|")
    for s in report.quality_summaries:
        lines.append(
            f"| {s.axis} | {s.mean_score} | {s.pass_rate}% | "
            f"{s.weakest_type} | {s.weakest_type_mean} |"
        )
    lines.append("")

    # 개정판별 커버리지
    lines.append("## 개정판별 커버리지")
    lines.append("")
    lines.append("| 개정판 | 문항 수 | 질의 유형 | 난이도 |")
    lines.append("|---|---|---|---|")
    for c in report.edition_coverages:
        types_str = ", ".join(c.query_types) if c.query_types else "-"
        diffs_str = ", ".join(c.difficulties) if c.difficulties else "-"
        lines.append(
            f"| {c.edition} | {c.question_count} | {types_str} | {diffs_str} |"
        )
    lines.append("")

    # 질의 유형별 분석
    lines.append("## 질의 유형별 분석")
    lines.append("")
    lines.append("| 유형 | 문항 | 통과 | 실패 | 통과율 |")
    lines.append("|---|---|---|---|---|")
    for bd in v1.query_type_breakdowns:
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
    for bd in v1.difficulty_breakdowns:
        lines.append(
            f"| {bd.difficulty} | {bd.total} | {bd.passed} | "
            f"{bd.failed} | {bd.pass_rate}% |"
        )
    lines.append("")

    # 권장사항
    lines.append("## 권장사항")
    lines.append("")
    for i, rec in enumerate(report.recommendations, 1):
        lines.append(f"{i}. {rec}")
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


def format_v2_report_json(report: V2QualityReport) -> dict[str, Any]:
    """V2 품질 보고서를 JSON 직렬화 가능한 dict로 변환한다.

    Args:
        report: V2QualityReport

    Returns:
        JSON 직렬화 가능한 dict
    """
    v1 = report.v1_report
    qr = v1.quality_report

    return {
        "overall_grade": report.overall_grade,
        "gate_passed": qr.gate_passed,
        "coverage_score": report.coverage_score,
        "golden_question_count": v1.golden_question_count,
        "evaluated_count": v1.evaluated_count,
        "passed_count": qr.passed_count,
        "failed_count": qr.failed_count,
        "pass_rate": qr.pass_rate,
        "pass_rate_threshold": qr.pass_rate_threshold,
        "regression": {
            "total": v1.regression_total,
            "passed": v1.regression_passed,
        },
        "quality_summaries": [
            {
                "axis": s.axis,
                "mean_score": s.mean_score,
                "pass_rate": s.pass_rate,
                "weakest_type": s.weakest_type,
                "weakest_type_mean": s.weakest_type_mean,
            }
            for s in report.quality_summaries
        ],
        "edition_coverages": [
            {
                "edition": c.edition,
                "question_count": c.question_count,
                "query_types": list(c.query_types),
                "difficulties": list(c.difficulties),
            }
            for c in report.edition_coverages
        ],
        "query_type_breakdowns": [
            {
                "query_type": bd.query_type,
                "total": bd.total,
                "passed": bd.passed,
                "failed": bd.failed,
                "pass_rate": bd.pass_rate,
            }
            for bd in v1.query_type_breakdowns
        ],
        "difficulty_breakdowns": [
            {
                "difficulty": bd.difficulty,
                "total": bd.total,
                "passed": bd.passed,
                "failed": bd.failed,
                "pass_rate": bd.pass_rate,
            }
            for bd in v1.difficulty_breakdowns
        ],
        "recommendations": list(report.recommendations),
        "failed_questions": list(qr.failed_questions),
    }
