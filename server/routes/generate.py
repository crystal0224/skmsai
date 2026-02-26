"""생성 API 라우트.

PR-013: /api/generate 엔드포인트.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from scripts.lib.generation import (
    detect_temporal_conflicts,
    format_context,
)
from server.dependencies import AppState
from server.models import GenerateRequest, GenerateResponse


def create_generate_router(state: AppState) -> APIRouter:
    """생성 라우터를 생성한다."""
    router = APIRouter(prefix="/api", tags=["generate"])

    @router.post("/generate", response_model=GenerateResponse)
    async def generate(request: GenerateRequest) -> GenerateResponse:
        """질의에 대한 답변을 생성한다."""
        if not state.generation_service:
            raise HTTPException(
                status_code=503,
                detail="생성 서비스를 현재 사용할 수 없습니다",
            )
        if not state.search_service:
            raise HTTPException(status_code=503, detail="검색 서비스가 초기화되지 않았습니다")

        svc = state.search_service
        gen = state.generation_service

        # 검색
        hits = svc.hybrid_search(
            request.query,
            top_k=request.top_k,
            edition_filter=request.edition_filter,
        )

        if not hits:
            return GenerateResponse(
                query=request.query,
                intent="open_ended",
                answer="검색 결과가 없습니다. 인덱스를 먼저 구축해주세요.",
                prompt_name="",
                validation_passed=None,
                citations=[],
                search_hits_count=0,
            )

        # SearchHit → dict 변환 (format_context 호환)
        hit_dicts = [
            {
                "quote_id": h.quote_id,
                "text": h.text,
                "edition": h.edition_id,
                "type": h.quote_type,
                "chapter_path": list(h.section_path),
                "quality_flags": list(h.quality_flags),
            }
            for h in hits
        ]

        # 시간축 충돌 감지
        conflict = detect_temporal_conflicts(hit_dicts)

        # 의도 결정
        intent = "content_generation" if request.output_type else "open_ended"

        # 컨텍스트 포맷팅
        context = format_context(
            hit_dicts,
            intent=intent,
            conflict=conflict,
            output_type=request.output_type,
        )

        # 답변 생성
        result = gen.generate(
            query=request.query,
            context=context,
            intent=intent,
            output_type=request.output_type,
        )

        citations = [h.quote_id for h in hits]

        return GenerateResponse(
            query=request.query,
            intent=intent,
            answer=result.answer,
            prompt_name=result.prompt_name,
            validation_passed=result.validation_passed,
            citations=citations,
            search_hits_count=len(hits),
        )

    return router
