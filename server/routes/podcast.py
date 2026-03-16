"""Podcast API 라우트 — skms_podcast.py Premium Engine을 웹에서 호출.

Endpoints:
- POST /api/podcast/generate  — 팟캐스트 생성 (비동기, request_id 반환)
- GET  /api/podcast/status/{request_id} — 진행 상태 조회
- GET  /api/podcast/download/{request_id}/{filename} — 파일 다운로드
- POST /api/podcast/transcribe — 동영상 업로드 → 트랜스크립트 반환
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
PODCAST_SCRIPTS = Path(
    os.environ.get(
        "PODCAST_PLUGIN_DIR",
        str(
            Path.home()
            / "plugins-for-claude-natives/plugins/podcast/skills/podcast/scripts"
        ),
    )
)
OUTPUT_BASE = PROJECT_ROOT / "output" / "podcast"


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class PodcastRequest(BaseModel):
    """팟캐스트 생성 요청."""

    topics: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="쉼표로 구분된 SKMS 주제 (예: 'SUPEX 추구, VWBE 문화')",
    )
    source_url: str | None = Field(default=None, description="외부 아티클 URL")
    source_text: str | None = Field(default=None, description="외부 소스 텍스트 (트랜스크립트 등)")
    duration_min: int = Field(default=8, ge=3, le=15)
    style: str = Field(default="dialogue", pattern="^(narration|dialogue|podcast)$")
    edition_filter: str | None = Field(default=None)


class PodcastFileInfo(BaseModel):
    file_name: str
    file_type: str
    size_bytes: int


class PodcastStatusResponse(BaseModel):
    request_id: str
    status: str  # pending, running, script_ready, finalizing, completed, failed
    topics: str
    created_at: float
    completed_at: float | None = None
    script: str | None = None
    files: list[PodcastFileInfo] = []
    error: str | None = None


class FinalizeRequest(BaseModel):
    """편집된 대본으로 TTS/MP4 생성 요청."""

    script: str = Field(..., min_length=10, description="편집된 대본 텍스트")


class TranscribeResponse(BaseModel):
    transcript: str
    word_count: int
    duration_seconds: float | None = None


# ---------------------------------------------------------------------------
# In-memory job store (lightweight)
# ---------------------------------------------------------------------------


@dataclass
class PodcastJob:
    request_id: str
    status: str
    topics: str
    created_at: float
    completed_at: float | None = None
    output_dir: str | None = None
    script: str | None = None
    files: list[dict[str, Any]] | None = None
    error: str | None = None


_jobs: dict[str, PodcastJob] = {}


def _has_multipart_support() -> bool:
    """python-multipart 설치 여부를 확인한다."""
    try:
        import python_multipart  # type: ignore  # noqa: F401

        return True
    except ImportError:
        try:
            import multipart  # type: ignore  # noqa: F401

            return True
        except ImportError:
            return False


_MULTIPART_AVAILABLE = _has_multipart_support()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


def create_podcast_router() -> APIRouter:
    """Podcast API 라우터를 생성한다."""
    router = APIRouter(prefix="/api/podcast", tags=["podcast"])

    @router.post("/generate")
    async def generate_podcast(request: PodcastRequest):
        """팟캐스트 생성을 시작한다 (백그라운드 실행)."""
        request_id = str(uuid.uuid4())
        job = PodcastJob(
            request_id=request_id,
            status="pending",
            topics=request.topics,
            created_at=time.time(),
        )
        _jobs[request_id] = job

        import threading

        thread = threading.Thread(
            target=_run_podcast_generation,
            args=(request_id, request),
            daemon=True,
        )
        thread.start()

        return {"request_id": request_id, "status": "pending"}

    @router.get("/status/{request_id}", response_model=PodcastStatusResponse)
    async def get_status(request_id: str):
        """팟캐스트 생성 상태를 조회한다."""
        job = _jobs.get(request_id)
        if not job:
            raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
        return PodcastStatusResponse(
            request_id=job.request_id,
            status=job.status,
            topics=job.topics,
            created_at=job.created_at,
            completed_at=job.completed_at,
            script=job.script,
            files=[PodcastFileInfo(**f) for f in (job.files or [])],
            error=job.error,
        )

    @router.get("/download/{request_id}/{filename}")
    async def download_file(request_id: str, filename: str):
        """생성된 팟캐스트 파일을 다운로드한다."""
        job = _jobs.get(request_id)
        if not job or not job.output_dir:
            raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

        file_path = Path(job.output_dir) / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
        if not file_path.resolve().is_relative_to(Path(job.output_dir).resolve()):
            raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")

        mime_map = {
            ".md": "text/markdown",
            ".mp3": "audio/mpeg",
            ".mp4": "video/mp4",
            ".txt": "text/plain",
        }
        ext = file_path.suffix.lower()
        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type=mime_map.get(ext, "application/octet-stream"),
        )

    @router.post("/finalize/{request_id}")
    async def finalize_podcast(request_id: str, req: FinalizeRequest):
        """편집된 대본으로 TTS + MP4를 생성한다."""
        job = _jobs.get(request_id)
        if not job:
            raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
        if job.status != "script_ready":
            raise HTTPException(
                status_code=400,
                detail=f"대본 편집 상태가 아닙니다. (현재: {job.status})",
            )

        # 편집된 대본 저장
        job.script = req.script
        if job.output_dir:
            script_path = Path(job.output_dir) / "script.md"
            script_path.write_text(req.script, encoding="utf-8")

        import threading

        thread = threading.Thread(target=_run_finalize, args=(request_id,), daemon=True)
        thread.start()

        return {"request_id": request_id, "status": "finalizing"}

    if _MULTIPART_AVAILABLE:

        @router.post("/transcribe", response_model=TranscribeResponse)
        async def transcribe_video(file: UploadFile = File(...)):
            """동영상 파일을 업로드하여 트랜스크립트를 추출한다."""
            if not PODCAST_SCRIPTS.exists():
                raise HTTPException(status_code=503, detail="Podcast 플러그인을 찾을 수 없습니다.")

            suffix = Path(file.filename or "video.mp4").suffix
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_video:
                content = await file.read()
                tmp_video.write(content)
                tmp_video_path = tmp_video.name

            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp_out:
                tmp_out_path = tmp_out.name

            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(PODCAST_SCRIPTS / "transcribe_video.py"),
                        "--input",
                        tmp_video_path,
                        "--output",
                        tmp_out_path,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                if result.returncode != 0:
                    raise HTTPException(
                        status_code=500,
                        detail=f"트랜스크립션 실패: {result.stderr[-300:]}",
                    )

                transcript = Path(tmp_out_path).read_text(encoding="utf-8")
                return TranscribeResponse(
                    transcript=transcript,
                    word_count=len(transcript.split()),
                )
            finally:
                os.unlink(tmp_video_path)
                if os.path.exists(tmp_out_path):
                    os.unlink(tmp_out_path)
    else:

        @router.post("/transcribe")
        async def transcribe_video_unavailable():
            """multipart 의존성이 없을 때 업로드 엔드포인트를 우아하게 비활성화한다."""
            raise HTTPException(
                status_code=503,
                detail="파일 업로드 기능이 비활성화되었습니다. python-multipart를 설치한 뒤 다시 배포하세요.",
            )

    return router


# ---------------------------------------------------------------------------
# Background generation
# ---------------------------------------------------------------------------


def _fetch_article_text(url: str) -> str:
    """URL에서 텍스트 추출."""
    import urllib.request as req

    request = req.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with req.urlopen(request, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:8000]


def _run_podcast_generation(request_id: str, request: PodcastRequest) -> None:
    """Phase 1: 대본만 생성하고 사용자 편집을 기다린다."""
    job = _jobs[request_id]
    job.status = "running"

    try:
        # 외부 소스 수집
        external_source = ""
        if request.source_url:
            external_source = _fetch_article_text(request.source_url)
        elif request.source_text:
            external_source = request.source_text

        # skms_podcast.py의 함수를 직접 호출
        sys.path.insert(0, str(PROJECT_ROOT))
        from scripts.skms_podcast import (
            retrieve_multi_context,
            generate_premium_script,
            _resolve_output_dir,
        )

        topic_list = [t.strip() for t in request.topics.split(",")]

        # 1. SKMS 컨텍스트 수집
        context = retrieve_multi_context(topic_list, request.edition_filter)

        # 외부 소스가 있으면 컨텍스트에 추가
        if external_source:
            context = f"## 외부 소스\n{external_source}\n\n---\n\n{context}"

        # 2. 대본 생성
        temp_dir = OUTPUT_BASE / "_temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        script_path = temp_dir / "script.md"

        episode_title = generate_premium_script(
            topic_list,
            context,
            request.duration_min,
            request.style,
            script_path,
        )

        # 출력 디렉토리 확정
        output_dir = _resolve_output_dir(episode_title)
        final_script = output_dir / "script.md"
        script_path.rename(final_script)

        # 대본만 저장하고 편집 대기 상태로 전환
        script_text = final_script.read_text(encoding="utf-8")
        job.status = "script_ready"
        job.output_dir = str(output_dir)
        job.script = script_text

    except Exception as e:
        logger.error("대본 생성 실패 [%s]: %s", request_id, e, exc_info=True)
        job.status = "failed"
        job.completed_at = time.time()
        job.error = str(e)


def _run_finalize(request_id: str) -> None:
    """Phase 2: 편집된 대본으로 TTS + MP4를 생성한다."""
    job = _jobs[request_id]
    job.status = "finalizing"

    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from scripts.skms_podcast import PODCAST_PLUGIN_SCRIPTS as PLUGIN_SCRIPTS

        output_dir = Path(job.output_dir)
        final_script = output_dir / "script.md"
        mp3_path = output_dir / "episode.mp3"
        mp4_path = output_dir / "episode.mp4"

        # 제목 추출
        episode_title = job.topics
        for line in job.script.split("\n"):
            if line.startswith("# "):
                episode_title = line.replace("# ", "").strip()
                break

        # 3. TTS
        subprocess.run(
            [
                sys.executable,
                str(PLUGIN_SCRIPTS / "generate_tts.py"),
                "--input",
                str(final_script),
                "--output",
                str(mp3_path),
            ],
            check=True,
            capture_output=True,
        )

        # 4. MP4
        subprocess.run(
            [
                sys.executable,
                str(PLUGIN_SCRIPTS / "convert_mp4.py"),
                "--input",
                str(mp3_path),
                "--output",
                str(mp4_path),
                "--title",
                episode_title,
                "--subtitle",
                "SKMS AI Content Studio",
            ],
            check=True,
            capture_output=True,
        )

        # 결과 저장
        files = []
        for f in [final_script, mp3_path, mp4_path]:
            if f.exists():
                files.append(
                    {
                        "file_name": f.name,
                        "file_type": f.suffix.lstrip("."),
                        "size_bytes": f.stat().st_size,
                    }
                )

        job.status = "completed"
        job.completed_at = time.time()
        job.files = files

    except Exception as e:
        logger.error("음성 생성 실패 [%s]: %s", request_id, e, exc_info=True)
        job.status = "failed"
        job.completed_at = time.time()
        job.error = str(e)
