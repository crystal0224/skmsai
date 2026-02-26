"""헬스체크 API 라우트.

PR-013: /api/health 엔드포인트.
"""
from __future__ import annotations

from fastapi import APIRouter, Response

from server.dependencies import AppState
from server.models import HealthResponse


def create_health_router(state: AppState) -> APIRouter:
    """헬스체크 라우터를 생성한다."""
    router = APIRouter(prefix="/api", tags=["health"])

    @router.get("/health", response_model=HealthResponse)
    async def health(response: Response) -> HealthResponse:
        """서비스 상태를 반환한다.

        초기화 전에는 HTTP 503을 반환하여 로드밸런서가 트래픽을 보내지 않게 한다.
        """
        components = {
            "search_service": state.search_service is not None,
            "generation_service": state.generation_service is not None,
            "toc_service": state.toc_service is not None,
            "initialized": state.is_ready,
        }

        if not state.is_ready:
            response.status_code = 503

        status = "ok" if state.is_ready else "initializing"
        return HealthResponse(
            status=status,
            version=state.version,
            components=components,
        )

    return router
