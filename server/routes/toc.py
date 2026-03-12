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
        title: str | None = None,
    ) -> dict:
        """섹션의 모든 텍스트 조각을 합쳐서 전문을 반환한다 (DB 기반 통합).

        PR-075: 다중 텍스트 조각 통합 기능 (Full-Text 보장).
        """
        import sqlite3
        from pathlib import Path

        db_path = Path("data/skms.db")
        if not db_path.exists():
            raise HTTPException(status_code=500, detail="데이터베이스를 찾을 수 없습니다")

        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # 1. 먼저 제목(title)으로 해당 섹션의 모든 조각을 찾음 (가장 정확한 방법)
                # section_path 컬럼에 제목이 포함된 모든 데이터를 가져옴
                rows = []
                if title:
                    query_title = "SELECT text FROM quotes WHERE edition_id = ? AND section_path LIKE ? ORDER BY start_line"
                    rows = conn.execute(query_title, (edition_id, f'%"{title}"%')).fetchall()
                
                # 2. 제목으로 결과가 없으면 line 번호 기반으로 근처 조각들을 가져옴 (Fallback)
                if not rows:
                    query_line = "SELECT text FROM quotes WHERE edition_id = ? AND start_line >= ? AND start_line < ? + 10 ORDER BY start_line"
                    rows = conn.execute(query_line, (edition_id, line, line)).fetchall()

                if rows:
                    # 모든 조각을 하나의 텍스트로 합침
                    full_text = "\n\n".join([row["text"] for row in rows])
                    return {"edition_id": edition_id, "line": line, "text": full_text}
                
                return {"edition_id": edition_id, "line": line, "text": "해당 섹션의 본문 데이터를 찾을 수 없습니다."}
        except Exception as e:
            return {"edition_id": edition_id, "line": line, "text": f"본문 로드 중 오류 발생: {str(e)}"}

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
