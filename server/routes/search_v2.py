"""V2 검색 API 라우트.

PR-027: /api/v2/search — 근거 검증 + 개정판 비교 통합 검색.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from server.dependencies import AppState
from server.models import (
    ComparisonResponse,
    EditionGroupResponse,
    EvidenceCheckResponse,
    SearchHitResponse,
    SearchV2Request,
    SearchV2Response,
)


def create_search_v2_router(state: AppState) -> APIRouter:
    """V2 검색 라우터를 생성한다."""
    router = APIRouter(prefix="/api/v2", tags=["search-v2"])

    @router.post("/search", response_model=SearchV2Response)
    async def search_v2(request: SearchV2Request) -> SearchV2Response:
        """V2 하이브리드 검색 — 근거 검증 + 개정판 비교 통합."""
        if not state.search_service:
            raise HTTPException(status_code=503, detail="검색 서비스가 초기화되지 않았습니다")

        svc = state.search_service

        # 검색 실행
        if request.mode == "vector":
            hits = svc.vector_search(
                request.query,
                top_k=request.top_k,
                edition_filter=request.edition_filter,
                type_filter=request.type_filter,
            )
        elif request.mode == "bm25":
            hits = svc.bm25_search(
                request.query,
                top_k=request.top_k,
                edition_filter=request.edition_filter,
                type_filter=request.type_filter,
            )
        else:
            hits = svc.hybrid_search(
                request.query,
                top_k=request.top_k,
                edition_filter=request.edition_filter,
                type_filter=request.type_filter,
            )

        hit_responses = [
            SearchHitResponse(
                quote_id=h.quote_id,
                text=h.text,
                score=h.score,
                edition_id=h.edition_id,
                year=h.year,
                quote_type=h.quote_type,
                section_path=list(h.section_path),
                source=h.source,
            )
            for h in hits
        ]

        # 근거 검증 (optional)
        evidence_check = None
        if request.include_evidence_check and state.evidence_filter and hits:
            # evidence_filter는 answer 기반이지만 v2 search에서는
            # hits의 quote_id 유효성만 체크 (answer=""로 coverage=0)
            check_result = state.evidence_filter.check("", hits)
            evidence_check = EvidenceCheckResponse(
                coverage_score=check_result.coverage_score,
                cited_quote_ids=list(check_result.cited_quote_ids),
                valid_quote_ids=list(check_result.valid_quote_ids),
                invalid_quote_ids=list(check_result.invalid_quote_ids),
                hallucination_flags=list(check_result.hallucination_flags),
                passed=check_result.passed,
            )

        # 개정판 비교 (optional)
        comparison = None
        if request.include_comparison and state.comparison_service and hits:
            ctx = state.comparison_service.build_comparison(request.query, hits)
            formatted = state.comparison_service.format_comparison_prompt(ctx)

            edition_groups = [
                EditionGroupResponse(
                    edition_id=g.edition_id,
                    year=g.year,
                    hit_count=g.hit_count,
                    definition_texts=list(g.definition_texts),
                    narrative_texts=list(g.narrative_texts),
                )
                for g in ctx.edition_groups
            ]

            comparison = ComparisonResponse(
                edition_count=ctx.edition_count,
                concept_name=ctx.concept_name,
                edition_groups=edition_groups,
                formatted_prompt=formatted,
            )

        return SearchV2Response(
            query=request.query,
            mode=request.mode,
            hits=hit_responses,
            total=len(hit_responses),
            evidence_check=evidence_check,
            comparison=comparison,
        )

    return router
