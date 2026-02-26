"""V2 생성 API 라우트.

PR-027: /api/v2/generate — 근거 검증 + 렌더링 통합 답변 생성.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from scripts.lib.generation import (
    detect_temporal_conflicts,
    format_context,
)
from scripts.lib.output_renderer import render
from server.dependencies import AppState
from server.models import (
    EvidenceCheckResponse,
    GenerateV2Request,
    GenerateV2Response,
)


def create_generate_v2_router(state: AppState) -> APIRouter:
    """V2 생성 라우터를 생성한다."""
    router = APIRouter(prefix="/api/v2", tags=["generate-v2"])

    @router.post("/generate", response_model=GenerateV2Response)
    async def generate_v2(request: GenerateV2Request) -> GenerateV2Response:
        """V2 답변 생성 — 근거 검증 + 렌더링 통합."""
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
            return GenerateV2Response(
                query=request.query,
                intent="open_ended",
                answer="검색 결과가 없습니다.",
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

        # 근거 검증 (optional)
        evidence_check = None
        if request.include_evidence_check and state.evidence_filter:
            check_result = state.evidence_filter.check(result.answer, hits)
            evidence_check = EvidenceCheckResponse(
                coverage_score=check_result.coverage_score,
                cited_quote_ids=list(check_result.cited_quote_ids),
                valid_quote_ids=list(check_result.valid_quote_ids),
                invalid_quote_ids=list(check_result.invalid_quote_ids),
                hallucination_flags=list(check_result.hallucination_flags),
                passed=check_result.passed,
            )

        # 렌더링 (optional, output_type이 있을 때만)
        rendered = None
        render_success = None
        if (
            request.include_rendered
            and request.output_type
            and request.output_type in ("summary", "card", "comparison_table")
        ):
            render_result = render(result.answer, request.output_type)
            rendered = render_result.rendered if render_result.success else None
            render_success = render_result.success

        return GenerateV2Response(
            query=request.query,
            intent=intent,
            answer=result.answer,
            prompt_name=result.prompt_name,
            validation_passed=result.validation_passed,
            citations=citations,
            search_hits_count=len(hits),
            evidence_check=evidence_check,
            rendered=rendered,
            render_success=render_success,
        )

    return router
