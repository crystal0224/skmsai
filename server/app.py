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
from scripts.lib.security import RateLimitConfig, RateLimiter
from server.dependencies import AppState
from server.models import ErrorResponse
from server.routes.content import create_content_router
from server.routes.dashboard import create_dashboard_router
from server.routes.generate import create_generate_router
from server.routes.quality import create_quality_router
from server.routes.generate_v2 import create_generate_v2_router
from server.routes.health import create_health_router
from server.routes.podcast import create_podcast_router
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

_RATE_LIMITED_PATH_PREFIXES = (
    "/api/search",
    "/api/v2/search",
    "/api/generate",
    "/api/v2/generate",
    "/api/content/generate",
    "/api/content/plan",
)


def _env_bool(name: str, default: bool) -> bool:
    """환경변수 bool 파서."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    """환경변수 int 파서 (파싱 실패 시 기본값)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("환경변수 %s 정수 파싱 실패: %r, 기본값 %d 사용", name, raw, default)
        return default


def _build_rate_limiter() -> RateLimiter:
    """RateLimiter 인스턴스를 구성한다."""
    enabled = _env_bool("RATE_LIMIT_ENABLED", True)
    rpm = max(1, _env_int("RATE_LIMIT_REQUESTS_PER_MINUTE", 600))
    burst = max(1, _env_int("RATE_LIMIT_BURST_SIZE", 120))
    return RateLimiter(
        RateLimitConfig(
            requests_per_minute=rpm,
            burst_size=burst,
            enabled=enabled,
        )
    )


def _is_rate_limited_request(method: str, path: str) -> bool:
    """비용이 큰 API 요청에만 레이트리밋을 적용한다."""
    if method != "POST":
        return False
    return path.startswith(_RATE_LIMITED_PATH_PREFIXES)


def _resolve_client_id(request: Request) -> str:
    """클라이언트 식별자를 추출한다 (X-Forwarded-For 우선)."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _load_content_studio_llm_config(
    path: Path = Path("config/generation.yaml"),
) -> tuple[str, int]:
    """Content Studio Planner용 LLM 모델/토큰 설정을 로드한다."""
    default_model = "claude-sonnet-4-20250514"
    default_max_tokens = 2048
    default_cap = 4096

    if not path.exists():
        return default_model, default_max_tokens

    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        generation = raw.get("generation", {}) if isinstance(raw, dict) else {}
        model = str(
            generation.get(
                "content_studio_model", generation.get("model", default_model)
            )
        )
        requested = int(generation.get("content_studio_max_tokens", default_max_tokens))
        cap = int(generation.get("content_studio_max_tokens_cap", default_cap))
        if cap < 1:
            cap = default_cap
        max_tokens = max(1, min(requested, cap))
        if max_tokens != requested:
            logger.warning(
                "Content Studio max_tokens가 상한을 초과해 클램프됨: requested=%d, cap=%d",
                requested,
                cap,
            )
        return model, max_tokens
    except Exception as e:
        logger.warning("Content Studio LLM 설정 로드 실패, 기본값 사용: %s", e)
        return default_model, default_max_tokens


_rate_limiter = _build_rate_limiter()


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
        from src.content_studio import ContentStudio

        from server.dependencies import _make_anthropic_client

        studio_model, studio_max_tokens = _load_content_studio_llm_config()

        class _AnthropicLLMAdapter:
            """anthropic.Anthropic → LLMClient Protocol 어댑터."""

            def __init__(self, client, *, model: str, max_tokens: int):
                self._client = client
                self._model = model
                self._max_tokens = max_tokens

            async def generate(self, prompt: str) -> str:
                resp = self._client.messages.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                return resp.content[0].text

        raw_client = _make_anthropic_client()
        llm_adapter = (
            _AnthropicLLMAdapter(
                raw_client,
                model=studio_model,
                max_tokens=studio_max_tokens,
            )
            if raw_client
            else None
        )

        _state.content_studio = ContentStudio.create(
            llm_client=llm_adapter,
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
        path = request.url.path

        # 비용이 큰 경로 보호: 레이트리밋
        rate_result = None
        if _is_rate_limited_request(request.method, path):
            client_id = _resolve_client_id(request)
            rate_result = _rate_limiter.check(client_id)
            if not rate_result.allowed:
                duration_ms = (time.time() - start) * 1000
                response = JSONResponse(
                    status_code=429,
                    content=ErrorResponse(
                        error="rate_limited",
                        detail="요청이 너무 많습니다. 잠시 후 다시 시도하세요.",
                    ).model_dump(),
                    headers={
                        "Retry-After": str(
                            max(1, int(rate_result.retry_after_seconds))
                        ),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Limit": str(
                            _rate_limiter.config.requests_per_minute
                        ),
                    },
                )
                logger.warning(
                    "%s %s → %d (rate_limited, %.1fms, client=%s)",
                    request.method,
                    path,
                    response.status_code,
                    duration_ms,
                    client_id,
                )
                if not path.startswith("/api/dashboard"):
                    _metrics.record(
                        endpoint=path,
                        method=request.method,
                        status_code=response.status_code,
                        duration_ms=duration_ms,
                    )
                return response

        response = await call_next(request)
        if rate_result is not None:
            response.headers["X-RateLimit-Remaining"] = str(rate_result.remaining)
            response.headers["X-RateLimit-Limit"] = str(
                _rate_limiter.config.requests_per_minute
            )
        duration_ms = (time.time() - start) * 1000
        logger.info(
            "%s %s → %d (%.1fms)",
            request.method,
            path,
            response.status_code,
            duration_ms,
        )
        # 메트릭 기록 (대시보드 자체 요청은 제외)
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

    # Routes — Podcast Studio
    app.include_router(create_podcast_router())

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
