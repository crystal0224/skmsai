"""FastAPI 애플리케이션.

PR-013: SKMS Time-Aware RAG API 서버.

Usage:
    uvicorn server.app:app --reload
    python -m server.app
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from scripts.lib.metrics_collector import MetricsCollector
from server.dependencies import AppState
from server.models import ErrorResponse
from server.routes.content import create_content_router
from server.routes.dashboard import create_dashboard_router
from server.routes.generate import create_generate_router
from server.routes.quality import create_quality_router
from server.routes.generate_v2 import create_generate_v2_router
from server.routes.health import create_health_router
from server.routes.search import create_search_router
from server.routes.search_v2 import create_search_v2_router
from server.routes.toc import create_toc_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------

_state = AppState()
_metrics = MetricsCollector()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 시작/종료 시 실행."""
    logger.info("SKMS API 서버 시작...")
    try:
        _state.initialize()
        logger.info("서비스 초기화 완료")
    except Exception as e:
        logger.warning("서비스 초기화 실패 (degraded mode): %s", e)
        # 초기화 실패 시 degraded mode로 시작 — health 엔드포인트는 503 반환

    # Content Studio 초기화 (선택적 — LLM 클라이언트 없으면 비활성)
    try:
        from scripts.lib.content_studio import ContentStudio

        from server.dependencies import _make_anthropic_client

        _state.content_studio = ContentStudio.create(
            llm_client=_make_anthropic_client(),
            search_service=_state.search_service,
            generation_service=_state.generation_service,
            evidence_filter=_state.evidence_filter,
        )
        logger.info("Content Studio 초기화 완료")
    except Exception as e:
        logger.warning("Content Studio 초기화 실패: %s", e)

    yield
    logger.info("SKMS API 서버 종료")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """FastAPI 앱을 생성한다."""
    app = FastAPI(
        title="SKMS Time-Aware RAG API",
        description="SK경영체계 시간축 인식 RAG 파이프라인 API",
        version=_state.version,
        lifespan=lifespan,
    )

    # CORS — 환경변수로 허용 오리진 설정 (기본: localhost)
    allowed_origins = os.environ.get(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:5500,http://127.0.0.1:5500,http://localhost:5501,http://127.0.0.1:5501",
    ).split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # Request logging + metrics middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000
        logger.info(
            "%s %s → %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        # 메트릭 기록 (대시보드 자체 요청은 제외)
        path = request.url.path
        if not path.startswith("/api/dashboard"):
            _metrics.record(
                endpoint=path,
                method=request.method,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
        return response

    # Global error handler
    @app.exception_handler(Exception)
    async def global_error_handler(request: Request, exc: Exception):
        logger.error("Unhandled error: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error="internal_server_error",
                detail="서버 내부 오류가 발생했습니다",
            ).model_dump(),
        )

    # Routes — v1
    app.include_router(create_health_router(_state))
    app.include_router(create_search_router(_state))
    app.include_router(create_generate_router(_state))
    app.include_router(create_toc_router(_state))

    # Routes — v2
    app.include_router(create_search_v2_router(_state))
    app.include_router(create_generate_v2_router(_state))

    # Routes — dashboard
    app.include_router(create_dashboard_router(_state, _metrics))

    # Routes — quality
    app.include_router(create_quality_router())

    # Routes — Content Studio
    app.include_router(create_content_router(_state))

    return app


app = create_app()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
