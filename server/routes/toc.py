"""TOC API 라우트.

PR-014: 개정판별 목차 트리 제공 엔드포인트.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from server.dependencies import AppState
from server.models import (
    EditionInfoResponse,
    EditionsListResponse,
    TOCNodeResponse,
    TOCResponse,
    TOCSectionSearchResponse,
    TOCSectionSearchResult,
)


def create_toc_router(state: AppState) -> APIRouter:
    """TOC 라우터를 생성한다."""
    router = APIRouter(prefix="/api", tags=["toc"])

    @router.get("/editions", response_model=EditionsListResponse)
    async def list_editions() -> EditionsListResponse:
        """전체 개정판 목록을 반환한다."""
        if not state.toc_service:
            raise HTTPException(status_code=503, detail="TOC 서비스를 사용할 수 없습니다")

        editions = state.toc_service.list_editions()
        return EditionsListResponse(
            editions=[
                EditionInfoResponse(
                    edition_id=e.edition_id,
                    year=e.year,
                    label=e.label,
                    start_line=e.start_line,
                    end_line=e.end_line,
                    section_count=e.section_count,
                )
                for e in editions
            ],
            total=len(editions),
        )

    @router.get("/toc/{edition_id}", response_model=TOCResponse)
    async def get_edition_toc(edition_id: str) -> TOCResponse:
        """특정 개정판의 TOC 트리를 반환한다."""
        if not state.toc_service:
            raise HTTPException(status_code=503, detail="TOC 서비스를 사용할 수 없습니다")

        toc = state.toc_service.get_edition_toc(edition_id)
        if toc is None:
            raise HTTPException(
                status_code=404,
                detail=f"개정판 '{edition_id}'을(를) 찾을 수 없습니다",
            )

        return TOCResponse(
            edition_id=toc.edition_id,
            year=toc.year,
            label=toc.label,
            sections=[_node_to_response(s) for s in toc.sections],
            node_count=toc.node_count,
        )

    @router.get("/section-text")
    async def get_section_text(
        edition_id: str,
        line: int,
        max_lines: int = 100,
    ) -> dict:
        """섹션의 원문 텍스트를 반환한다."""
        if not state.toc_service:
            raise HTTPException(status_code=503, detail="TOC 서비스를 사용할 수 없습니다")

        text = state.toc_service.get_section_text(edition_id, line, max_lines)
        if text is None:
            raise HTTPException(status_code=404, detail="원문 텍스트를 사용할 수 없습니다")

        return {"edition_id": edition_id, "line": line, "text": text}

    @router.get("/toc", response_model=TOCSectionSearchResponse)
    async def search_sections(
        q: str,
        edition_id: str | None = None,
    ) -> TOCSectionSearchResponse:
        """섹션 제목으로 검색한다."""
        if not state.toc_service:
            raise HTTPException(status_code=503, detail="TOC 서비스를 사용할 수 없습니다")

        if not q or not q.strip():
            raise HTTPException(status_code=400, detail="검색어를 입력해주세요")

        results = state.toc_service.search_sections(q.strip(), edition_id)

        return TOCSectionSearchResponse(
            query=q.strip(),
            edition_id=edition_id,
            results=[
                TOCSectionSearchResult(
                    edition_id=r["edition_id"],
                    path=r["path"],
                    level=r["level"],
                    title=r["title"],
                    line=r["line"],
                )
                for r in results
            ],
            total=len(results),
        )

    return router


def _node_to_response(node) -> TOCNodeResponse:
    """TOCNode를 응답 모델로 변환한다."""
    return TOCNodeResponse(
        level=node.level,
        title=node.title,
        line=node.line,
        children=[_node_to_response(c) for c in node.children],
    )
