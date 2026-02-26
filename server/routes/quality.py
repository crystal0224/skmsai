"""품질 대시보드 API 라우터.

PR-039: Golden QA 100 기반 최종 품질 대시보드 엔드포인트.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

from scripts.lib.quality_dashboard import (
    V2QualityReport,
    compute_coverage_score,
    compute_edition_coverages,
    format_v2_report_json,
    format_v2_report_markdown,
    generate_v2_report,
    load_all_golden_questions,
)
from scripts.lib.quality_gate import EvalResult, load_eval_results

logger = logging.getLogger(__name__)

# Golden QA 기본 경로
_DEFAULT_V1_PATH = Path("eval/questions.golden_v1.jsonl")
_DEFAULT_V2_PATH = Path("eval/questions.golden_v2.jsonl")
_DEFAULT_RESULTS_PATH = Path("eval/results.jsonl")


def create_quality_router() -> APIRouter:
    """품질 대시보드 API 라우터를 생성한다."""
    router = APIRouter(prefix="/api/quality", tags=["quality"])

    @router.get("/report")
    def get_quality_report(
        format: str = Query("json", pattern="^(json|markdown)$"),
    ) -> dict[str, Any]:
        """최종 품질 보고서를 반환한다.

        Query params:
            format: "json" 또는 "markdown"
        """
        questions = load_all_golden_questions(_DEFAULT_V1_PATH, _DEFAULT_V2_PATH)
        results = load_eval_results(_DEFAULT_RESULTS_PATH)

        if not results:
            return {
                "status": "no_results",
                "message": "평가 결과 없음. eval/results.jsonl을 먼저 생성하세요.",
                "golden_questions": len(questions),
            }

        report = generate_v2_report(results, questions)

        if format == "markdown":
            return {
                "format": "markdown",
                "content": format_v2_report_markdown(report),
            }

        return format_v2_report_json(report)

    @router.get("/coverage")
    def get_coverage() -> dict[str, Any]:
        """개정판별 커버리지 정보를 반환한다."""
        questions = load_all_golden_questions(_DEFAULT_V1_PATH, _DEFAULT_V2_PATH)
        coverages = compute_edition_coverages(questions)
        score = compute_coverage_score(coverages)

        return {
            "total_questions": len(questions),
            "coverage_score": score,
            "editions": [
                {
                    "edition": c.edition,
                    "question_count": c.question_count,
                    "query_types": list(c.query_types),
                    "difficulties": list(c.difficulties),
                }
                for c in coverages
            ],
        }

    @router.get("/summary")
    def get_quality_summary() -> dict[str, Any]:
        """품질 요약 정보를 반환한다 (대시보드 카드용)."""
        questions = load_all_golden_questions(_DEFAULT_V1_PATH, _DEFAULT_V2_PATH)
        results = load_eval_results(_DEFAULT_RESULTS_PATH)

        if not results:
            return {
                "status": "no_results",
                "golden_questions": len(questions),
                "evaluated": 0,
            }

        report = generate_v2_report(results, questions)
        v1 = report.v1_report
        qr = v1.quality_report

        return {
            "status": "ready",
            "overall_grade": report.overall_grade,
            "gate_passed": qr.gate_passed,
            "pass_rate": qr.pass_rate,
            "coverage_score": report.coverage_score,
            "golden_questions": v1.golden_question_count,
            "evaluated": v1.evaluated_count,
            "passed": qr.passed_count,
            "failed": qr.failed_count,
            "regression_passed": v1.regression_passed,
            "regression_total": v1.regression_total,
            "recommendations_count": len(report.recommendations),
        }

    return router
