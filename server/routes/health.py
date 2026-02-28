"""헬스체크 API 라우트.

PR-013: /api/health 엔드포인트.
TD-009: Content Studio 및 MCP 어댑터 헬스체크 확장.
"""
from __future__ import annotations

from fastapi import APIRouter, Response

from server.dependencies import AppState
from server.models import ContentStudioHealthResponse, HealthResponse


def _build_content_studio_health(
    content_studio: object | None,
) -> ContentStudioHealthResponse | None:
    """Content Studio 인스턴스에서 헬스체크 정보를 추출한다.

    Args:
        content_studio: ContentStudio 인스턴스 또는 None.

    Returns:
        ContentStudioHealthResponse 또는 None (Content Studio 미초기화 시).
    """
    if content_studio is None:
        return None

    return ContentStudioHealthResponse(
        available=True,
        has_planner=getattr(content_studio, "has_planner", False),
        has_generator=getattr(content_studio, "has_generator", False),
        has_asset_generator=getattr(content_studio, "has_asset_generator", False),
        has_assembler=getattr(content_studio, "has_assembler", False),
        has_plan_cache=getattr(content_studio, "has_plan_cache", False),
    )


def create_health_router(state: AppState) -> APIRouter:
    """헬스체크 라우터를 생성한다."""
    router = APIRouter(prefix="/api", tags=["health"])

    @router.get("/health", response_model=HealthResponse)
    async def health(response: Response) -> HealthResponse:
        """서비스 상태를 반환한다.

        초기화 전에는 HTTP 503을 반환하여 로드밸런서가 트래픽을 보내지 않게 한다.
        TD-009: Content Studio 가용 상태를 포함한다.
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
        content_studio_health = _build_content_studio_health(state.content_studio)

        return HealthResponse(
            status=status,
            version=state.version,
            components=components,
            content_studio=content_studio_health,
        )

    return router
