"""헬스체크 API 라우트.

PR-013: /api/health 엔드포인트.
"""
from __future__ import annotations

from fastapi import APIRouter

from server.dependencies import AppState
from server.models import HealthResponse


def create_health_router(state: AppState) -> APIRouter:
    """헬스체크 라우터를 생성한다."""
    router = APIRouter(prefix="/api", tags=["health"])

    @router.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        """서비스 상태를 반환한다."""
        components = {
            "search_service": state.search_service is not None,
            "generation_service": state.generation_service is not None,
            "initialized": state.is_ready,
        }

        status = "ok" if state.is_ready else "initializing"
        return HealthResponse(
            status=status,
            version=state.version,
            components=components,
        )

    return router
