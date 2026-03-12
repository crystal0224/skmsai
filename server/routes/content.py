"""Content Studio API 라우트.

PR-047: Content Studio REST API.
CC-04: 비동기 생성 API (POST /generate/async, GET /status/{request_id}).

Endpoints:
- POST /api/content/generate — 전체 콘텐츠 생성 파이프라인
- POST /api/content/plan — Plan만 생성 (미리보기)
- GET  /api/content/types — 지원 콘텐츠 유형 목록
- POST /api/content/generate/async — 비동기 콘텐츠 생성 (request_id 반환)
- GET  /api/content/status/{request_id} — 생성 작업 상태 조회
- POST /api/content/publish/{request_id} — 콘텐츠 발행 (local/notion/google_ws)
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.content_studio.errors import ContentStudioError, PlanningError, PublishError
from src.content_studio.models import ContentOptions, ContentRequest
from src.content_studio.publisher import Publisher, PublishResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Async job model (frozen dataclass)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GenerationJob:
    """비동기 콘텐츠 생성 작업."""

    request_id: str
    status: str  # "pending", "running", "completed", "failed"
    content_type: str
    topic: str
    created_at: float
    completed_at: float | None
    result: Any | None  # ContentGenerateResponse (dict form) or None
    error: str | None


import json
import sqlite3
from datetime import datetime

# ---------------------------------------------------------------------------
# Persistent Job Store (PR-054: Database-backed Job Store)
# ---------------------------------------------------------------------------


class DatabaseJobStore:
    """SQLite 기반의 영속적 작업 저장소."""

    def __init__(self, db_path: str = "data/content_jobs.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """데이터베이스 및 테이블 초기화."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    request_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    completed_at REAL,
                    result TEXT,
                    error TEXT
                )
                """
            )
            conn.commit()

    def put(self, job: GenerationJob) -> None:
        """새 작업을 저장한다."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job.request_id,
                    job.status,
                    job.content_type,
                    job.topic,
                    job.created_at,
                    job.completed_at,
                    json.dumps(job.result) if job.result else None,
                    job.error,
                ),
            )
            conn.commit()

    def get(self, request_id: str) -> GenerationJob | None:
        """작업을 조회한다."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM jobs WHERE request_id = ?", (request_id,)).fetchone()
            if not row:
                return None
            
            result_val = json.loads(row["result"]) if row["result"] else None
            # result_val이 dict일 경우 다시 ContentGenerateResponse로 변환될 수 있게 처리
            return GenerationJob(
                request_id=row["request_id"],
                status=row["status"],
                content_type=row["content_type"],
                topic=row["topic"],
                created_at=row["created_at"],
                completed_at=row["completed_at"],
                result=result_val,
                error=row["error"],
            )

    def update(self, request_id: str, **kwargs: Any) -> GenerationJob | None:
        """기존 작업을 업데이트한다."""
        existing = self.get(request_id)
        if not existing:
            return None

        # Update SQL dynamically
        updates = []
        params = []
        for k, v in kwargs.items():
            if k == "result" and v is not None:
                updates.append("result = ?")
                params.append(json.dumps(v))
            else:
                updates.append(f"{k} = ?")
                params.append(v)
        
        if not updates:
            return existing

        params.append(request_id)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE jobs SET {', '.join(updates)} WHERE request_id = ?",
                tuple(params),
            )
            conn.commit()
        
        return self.get(request_id)


# Module-level singleton (SQLite-backed)
_job_store = DatabaseJobStore()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ContentOptionsRequest(BaseModel):
    """콘텐츠 생성 옵션."""

    duration_min: int | None = Field(default=None, description="강의/워크숍 시간(분)")
    num_items: int | None = Field(default=None, description="슬라이드/카드/문항 수")
    edition_filter: str | None = Field(default=None, description="개정판 필터")
    style: str = Field(default="professional", description="시각 스타일")
    language: str = Field(default="ko", description="출력 언어")
    include_quiz: bool = Field(default=False, description="퀴즈 포함 여부")
    include_speaker_notes: bool = Field(default=True, description="발표자 노트 포함")


class ContentGenerateRequest(BaseModel):
    """콘텐츠 생성 요청."""

    content_type: str = Field(
        ...,
        description="콘텐츠 유형 (lecture, card_news, workshop, visualization, audio, quiz)",
    )
    topic: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="주제 (예: 'SUPEX 추구의 변천사')",
    )
    options: ContentOptionsRequest = Field(
        default_factory=ContentOptionsRequest,
        description="생성 옵션",
    )


class GeneratedFileResponse(BaseModel):
    """생성된 파일 정보."""

    file_type: str
    file_path: str
    file_name: str
    size_bytes: int


class ContentGenerateResponse(BaseModel):
    """콘텐츠 생성 응답."""

    content_type: str
    topic: str
    files: list[GeneratedFileResponse]
    citations: list[str]
    metadata: dict[str, Any]


class ContentPlanResponse(BaseModel):
    """Plan 미리보기 응답."""

    content_type: str
    topic: str
    plan: dict[str, Any]


class ContentTypeInfo(BaseModel):
    """콘텐츠 유형 정보."""

    type: str
    label: str
    description: str
    output_formats: list[str]


class ContentTypesResponse(BaseModel):
    """지원 콘텐츠 유형 목록."""

    types: list[ContentTypeInfo]
    total: int


# ---------------------------------------------------------------------------
# Async generation response models
# ---------------------------------------------------------------------------


class AsyncGenerateResponse(BaseModel):
    """비동기 생성 요청 응답 (즉시 반환)."""

    request_id: str
    status: str


class GenerationStatusResponse(BaseModel):
    """생성 작업 상태 조회 응답."""

    request_id: str
    status: str
    content_type: str
    topic: str
    created_at: float
    completed_at: float | None
    result: ContentGenerateResponse | None
    error: str | None


# ---------------------------------------------------------------------------
# Publish request / response models
# ---------------------------------------------------------------------------

VALID_DESTINATIONS = {"local", "notion", "google_ws"}


class PublishRequest(BaseModel):
    """발행 요청."""

    destination: str = Field(
        default="local",
        description="발행 대상 (local, notion, google_ws)",
    )


class PublishResultResponse(BaseModel):
    """개별 발행 결과."""

    destination: str
    url: str | None
    success: bool
    error: str | None
    timestamp: str


class PublishResponse(BaseModel):
    """발행 응답."""

    request_id: str
    results: list[PublishResultResponse]


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def create_content_router(state: Any) -> APIRouter:
    """Content Studio API 라우터를 생성한다.

    Args:
        state: AppState (state.content_studio로 접근).

    Returns:
        FastAPI APIRouter.
    """
    router = APIRouter(prefix="/api/content", tags=["content-studio"])

    def _get_studio():
        """state에서 ContentStudio를 가져온다."""
        studio = getattr(state, "content_studio", None)
        if studio is None:
            raise HTTPException(
                status_code=503,
                detail="Content Studio가 초기화되지 않았습니다.",
            )
        return studio

    @router.post("/generate", response_model=ContentGenerateResponse)
    async def generate_content(
        request: ContentGenerateRequest,
    ) -> ContentGenerateResponse:
        """전체 콘텐츠 생성 파이프라인을 실행한다."""
        studio = _get_studio()
        if not studio.has_planner:
            raise HTTPException(
                status_code=503,
                detail="ContentPlanner가 초기화되지 않았습니다. LLM 클라이언트를 확인하세요.",
            )

        options = ContentOptions(
            duration_min=request.options.duration_min,
            num_items=request.options.num_items,
            edition_filter=request.options.edition_filter,
            style=request.options.style,
            language=request.options.language,
            include_quiz=request.options.include_quiz,
            include_speaker_notes=request.options.include_speaker_notes,
        )

        try:
            content_request = ContentRequest(
                content_type=request.content_type,
                topic=request.topic,
                options=options,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

        try:
            result = await studio.generate(content_request)
        except PlanningError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except ContentStudioError as e:
            logger.error("콘텐츠 생성 실패 [%s]: %s", e.stage, e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"[{e.stage}] {e}")
        except Exception as e:
            logger.error("콘텐츠 생성 실패: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"콘텐츠 생성 중 오류: {e}")

        return ContentGenerateResponse(
            content_type=result.content_type,
            topic=result.topic,
            files=[
                GeneratedFileResponse(
                    file_type=f.file_type,
                    file_path=f.file_path,
                    file_name=f.file_name,
                    size_bytes=f.size_bytes,
                )
                for f in result.files
            ],
            citations=list(result.citations),
            metadata=dict(result.metadata),
        )

    @router.post("/plan", response_model=ContentPlanResponse)
    async def preview_plan(request: ContentGenerateRequest) -> ContentPlanResponse:
        """Plan만 생성하여 미리보기를 제공한다."""
        studio = _get_studio()
        if not studio.has_planner:
            raise HTTPException(
                status_code=503,
                detail="ContentPlanner가 초기화되지 않았습니다.",
            )

        options = ContentOptions(
            duration_min=request.options.duration_min,
            num_items=request.options.num_items,
            edition_filter=request.options.edition_filter,
            style=request.options.style,
            language=request.options.language,
            include_quiz=request.options.include_quiz,
            include_speaker_notes=request.options.include_speaker_notes,
        )

        try:
            content_request = ContentRequest(
                content_type=request.content_type,
                topic=request.topic,
                options=options,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

        try:
            plan = await studio.plan_only(content_request)
        except PlanningError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except ContentStudioError as e:
            logger.error("Plan 생성 실패 [%s]: %s", e.stage, e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"[{e.stage}] {e}")
        except Exception as e:
            logger.error("Plan 생성 실패: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Plan 생성 중 오류: {e}")

        return ContentPlanResponse(
            content_type=request.content_type,
            topic=request.topic,
            plan=plan.to_dict(),
        )

    @router.get("/types", response_model=ContentTypesResponse)
    async def list_content_types() -> ContentTypesResponse:
        """지원하는 콘텐츠 유형 목록을 반환한다."""
        from src.content_studio import ContentStudio

        type_infos = ContentStudio.content_types()
        return ContentTypesResponse(
            types=[
                ContentTypeInfo(
                    type=info["type"],
                    label=info["label"],
                    description=info["description"],
                    output_formats=info.get("output_formats", []),
                )
                for info in type_infos
            ],
            total=len(type_infos),
        )

    # -------------------------------------------------------------------
    # Async generation endpoints (CC-04)
    # -------------------------------------------------------------------

    async def _run_generation(request_id: str, request: ContentGenerateRequest) -> None:
        """백그라운드에서 콘텐츠 생성을 실행한다."""
        _job_store.update(request_id, status="running")

        studio = getattr(state, "content_studio", None)
        if studio is None:
            _job_store.update(
                request_id,
                status="failed",
                completed_at=time.time(),
                error="Content Studio가 초기화되지 않았습니다.",
            )
            return

        options = ContentOptions(
            duration_min=request.options.duration_min,
            num_items=request.options.num_items,
            edition_filter=request.options.edition_filter,
            style=request.options.style,
            language=request.options.language,
            include_quiz=request.options.include_quiz,
            include_speaker_notes=request.options.include_speaker_notes,
        )

        try:
            content_request = ContentRequest(
                content_type=request.content_type,
                topic=request.topic,
                options=options,
            )
            result = await studio.generate(content_request)
            response = ContentGenerateResponse(
                content_type=result.content_type,
                topic=result.topic,
                files=[
                    GeneratedFileResponse(
                        file_type=f.file_type,
                        file_path=f.file_path,
                        file_name=f.file_name,
                        size_bytes=f.size_bytes,
                    )
                    for f in result.files
                ],
                citations=list(result.citations),
                metadata=dict(result.metadata),
            )
            _job_store.update(
                request_id,
                status="completed",
                completed_at=time.time(),
                result=response,
            )
        except Exception as e:
            logger.error("비동기 콘텐츠 생성 실패 [%s]: %s", request_id, e, exc_info=True)
            _job_store.update(
                request_id,
                status="failed",
                completed_at=time.time(),
                error=str(e),
            )

    @router.post("/generate/async", response_model=AsyncGenerateResponse)
    async def generate_content_async(
        request: ContentGenerateRequest,
        background_tasks: BackgroundTasks,
    ) -> AsyncGenerateResponse:
        """비동기 콘텐츠 생성을 시작한다.

        즉시 request_id를 반환하며, GET /status/{request_id}로 진행 상황을 조회한다.
        """
        studio = _get_studio()
        if not studio.has_planner:
            raise HTTPException(
                status_code=503,
                detail="ContentPlanner가 초기화되지 않았습니다. LLM 클라이언트를 확인하세요.",
            )

        # Validate content_type early
        try:
            ContentRequest(
                content_type=request.content_type,
                topic=request.topic,
                options=ContentOptions(),
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

        request_id = str(uuid.uuid4())
        job = GenerationJob(
            request_id=request_id,
            status="pending",
            content_type=request.content_type,
            topic=request.topic,
            created_at=time.time(),
            completed_at=None,
            result=None,
            error=None,
        )
        _job_store.put(job)

        background_tasks.add_task(_run_generation, request_id, request)

        return AsyncGenerateResponse(request_id=request_id, status="pending")

    @router.get("/status/{request_id}", response_model=GenerationStatusResponse)
    async def get_generation_status(request_id: str) -> GenerationStatusResponse:
        """비동기 생성 작업의 상태를 조회한다."""
        job = _job_store.get(request_id)
        if job is None:
            raise HTTPException(
                status_code=404,
                detail=f"작업을 찾을 수 없습니다: {request_id}",
            )

        return GenerationStatusResponse(
            request_id=job.request_id,
            status=job.status,
            content_type=job.content_type,
            topic=job.topic,
            created_at=job.created_at,
            completed_at=job.completed_at,
            result=job.result,
            error=job.error,
        )

    # -------------------------------------------------------------------
    # File download endpoint
    # -------------------------------------------------------------------

    @router.get("/download/{request_id}/{filename}")
    async def download_file(request_id: str, filename: str) -> FileResponse:
        """생성된 파일을 다운로드한다.

        request_id의 완료된 작업에서 생성된 파일 중 filename과 일치하는 파일을 반환한다.
        Path traversal 공격을 방지하기 위해 filename을 검증한다.
        """
        # Validate request_id format (UUID)
        try:
            uuid.UUID(request_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="유효하지 않은 request_id 형식입니다.")

        # Reject path traversal attempts in filename
        if "/" in filename or "\\" in filename or ".." in filename:
            raise HTTPException(status_code=400, detail="유효하지 않은 파일명입니다.")

        # Look up the completed job
        job = _job_store.get(request_id)
        if job is None:
            raise HTTPException(
                status_code=404,
                detail=f"작업을 찾을 수 없습니다: {request_id}",
            )

        if job.status != "completed" or job.result is None:
            raise HTTPException(
                status_code=400,
                detail="완료된 작업에서만 파일을 다운로드할 수 있습니다.",
            )

        # Find matching file in result
        matched_file = None
        for f in job.result.files:
            if f.file_name == filename:
                matched_file = f
                break

        if matched_file is None:
            raise HTTPException(
                status_code=404,
                detail=f"파일을 찾을 수 없습니다: {filename}",
            )

        file_path = Path(matched_file.file_path)
        if not file_path.exists():
            raise HTTPException(
                status_code=404,
                detail="파일이 서버에서 삭제되었습니다.",
            )

        # Final path traversal guard: file must be inside output/
        output_base = Path("output").resolve()
        resolved = file_path.resolve()
        if not str(resolved).startswith(str(output_base)):
            raise HTTPException(
                status_code=403,
                detail="접근이 허용되지 않은 경로입니다.",
            )

        return FileResponse(
            path=str(resolved),
            filename=filename,
            media_type=_guess_media_type(filename),
        )

    # -------------------------------------------------------------------
    # Publish endpoint (STEP 7)
    # -------------------------------------------------------------------

    @router.post("/publish/{request_id}", response_model=PublishResponse)
    async def publish_content(
        request_id: str,
        request: PublishRequest,
    ) -> PublishResponse:
        """생성된 콘텐츠를 지정 대상에 발행한다.

        local은 항상 성공 (이미 output/에 저장됨).
        notion/google_ws는 API 키 미설정 시 400을 반환한다.
        """
        # Validate request_id format (UUID)
        try:
            uuid.UUID(request_id)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="유효하지 않은 request_id 형식입니다.",
            )

        # Validate destination
        if request.destination not in VALID_DESTINATIONS:
            raise HTTPException(
                status_code=400,
                detail=f"지원하지 않는 발행 대상입니다: {request.destination}. "
                f"사용 가능: {', '.join(sorted(VALID_DESTINATIONS))}",
            )

        # Check job exists and is completed
        job = _job_store.get(request_id)
        if job is None:
            raise HTTPException(
                status_code=404,
                detail=f"작업을 찾을 수 없습니다: {request_id}",
            )

        if job.status != "completed" or job.result is None:
            raise HTTPException(
                status_code=400,
                detail="완료된 작업만 발행할 수 있습니다.",
            )

        # Build publisher with adapters from state (if available)
        publisher = _get_publisher(state)

        # For notion/google_ws, check adapter availability before calling
        if request.destination in ("notion", "google_ws"):
            adapter = publisher._adapters.get(request.destination)
            if adapter is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"{request.destination} 어댑터가 등록되지 않았습니다. " f"API 키를 확인하세요.",
                )
            available = await adapter.is_available()
            if not available:
                raise HTTPException(
                    status_code=400,
                    detail=f"{request.destination} API 키가 설정되지 않았습니다. "
                    f"서버 환경 변수를 확인하세요.",
                )

        try:
            pub_results = await publisher.publish(
                result=job.result,
                destinations=[request.destination],
            )
        except PublishError as e:
            logger.error("발행 실패 [%s]: %s", e.stage, e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"[{e.stage}] {e}")
        except Exception as e:
            logger.error("발행 실패: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"발행 중 오류: {e}")

        return PublishResponse(
            request_id=request_id,
            results=[
                PublishResultResponse(
                    destination=r.destination,
                    url=r.url,
                    success=r.success,
                    error=r.error,
                    timestamp=r.timestamp,
                )
                for r in pub_results
            ],
        )

    return router


def _guess_media_type(filename: str) -> str:
    """파일 확장자로 MIME 타입을 추정한다."""
    ext = os.path.splitext(filename)[1].lower()
    mime_map = {
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".html": "text/html",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".mp3": "audio/mpeg",
        ".pdf": "application/pdf",
        ".md": "text/markdown",
    }
    return mime_map.get(ext, "application/octet-stream")


def _get_publisher(state: Any) -> Publisher:
    """state에서 Publisher를 가져오거나 기본 Publisher를 생성한다."""
    publisher = getattr(state, "publisher", None)
    if publisher is not None:
        return publisher
    return Publisher()
