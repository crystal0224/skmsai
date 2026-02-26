"""검색 API 라우트.

PR-013: /api/search 엔드포인트.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from server.dependencies import AppState
from server.models import SearchHitResponse, SearchRequest, SearchResponse


def create_search_router(state: AppState) -> APIRouter:
    """검색 라우터를 생성한다."""
    router = APIRouter(prefix="/api", tags=["search"])

    @router.post("/search", response_model=SearchResponse)
    async def search(request: SearchRequest) -> SearchResponse:
        """하이브리드 검색을 수행한다."""
        if not state.search_service:
            raise HTTPException(status_code=503, detail="검색 서비스가 초기화되지 않았습니다")

        svc = state.search_service

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

        return SearchResponse(
            query=request.query,
            mode=request.mode,
            hits=hit_responses,
            total=len(hit_responses),
        )

    return router
