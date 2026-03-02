"""파일 다운로드 엔드포인트 테스트.

GET /api/content/download/{request_id}/{filename}
"""
from __future__ import annotations

import time
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.routes.content import (
    ContentGenerateResponse,
    GeneratedFileResponse,
    GenerationJob,
    _job_store,
    create_content_router,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _MockState:
    """API 테스트용 AppState mock."""

    def __init__(self):
        self.content_studio = None


@pytest.fixture(autouse=True)
def _clear_job_store():
    """각 테스트 전후로 job store를 비운다."""
    _job_store._jobs = {}
    yield
    _job_store._jobs = {}


@pytest.fixture
def client():
    app = FastAPI()
    state = _MockState()
    app.include_router(create_content_router(state))
    return TestClient(app)


@pytest.fixture
def completed_job(tmp_path, monkeypatch):
    """완료된 작업과 다운로드 가능한 파일을 생성한다.

    CWD를 tmp_path로 변경하여 Path("output").resolve()가 tmp_path/output을 반환하도록 한다.
    """
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "output" / "lectures"
    output_dir.mkdir(parents=True)
    test_file = output_dir / "test-slide.pptx"
    test_file.write_bytes(b"fake pptx content")

    request_id = str(uuid.uuid4())
    result = ContentGenerateResponse(
        content_type="lecture",
        topic="테스트",
        files=[
            GeneratedFileResponse(
                file_type="pptx",
                file_path=str(test_file),
                file_name="test-slide.pptx",
                size_bytes=17,
            )
        ],
        citations=["원문1"],
        metadata={"total_elapsed_ms": 100},
    )
    job = GenerationJob(
        request_id=request_id,
        status="completed",
        content_type="lecture",
        topic="테스트",
        created_at=time.time(),
        completed_at=time.time(),
        result=result,
        error=None,
    )
    _job_store.put(job)
    return request_id, test_file


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDownloadEndpoint:
    def test_download_success(self, client, completed_job):
        """정상적인 파일 다운로드."""
        request_id, test_file = completed_job
        resp = client.get(f"/api/content/download/{request_id}/test-slide.pptx")
        assert resp.status_code == 200
        assert resp.content == b"fake pptx content"
        assert "presentation" in resp.headers.get("content-type", "")

    def test_download_invalid_request_id(self, client):
        """잘못된 request_id 형식."""
        resp = client.get("/api/content/download/not-a-uuid/file.pptx")
        assert resp.status_code == 400
        assert "유효하지 않은 request_id" in resp.json()["detail"]

    def test_download_not_found_job(self, client):
        """존재하지 않는 작업."""
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/content/download/{fake_id}/file.pptx")
        assert resp.status_code == 404
        assert "작업을 찾을 수 없습니다" in resp.json()["detail"]

    def test_download_pending_job(self, client):
        """아직 완료되지 않은 작업."""
        request_id = str(uuid.uuid4())
        job = GenerationJob(
            request_id=request_id,
            status="running",
            content_type="lecture",
            topic="테스트",
            created_at=time.time(),
            completed_at=None,
            result=None,
            error=None,
        )
        _job_store.put(job)
        resp = client.get(f"/api/content/download/{request_id}/file.pptx")
        assert resp.status_code == 400
        assert "완료된 작업" in resp.json()["detail"]

    def test_download_file_not_in_result(self, client, completed_job):
        """결과에 없는 파일명."""
        request_id, _ = completed_job
        resp = client.get(f"/api/content/download/{request_id}/nonexistent.pptx")
        assert resp.status_code == 404
        assert "파일을 찾을 수 없습니다" in resp.json()["detail"]

    def test_download_path_traversal_in_filename(self, client):
        """파일명에 경로 탐색 시도 (/ 포함 → FastAPI가 라우트 불일치로 404)."""
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/content/download/{fake_id}/../../etc/passwd")
        # FastAPI routes treat extra slashes as different paths → 404
        assert resp.status_code in (400, 404)

    def test_download_path_traversal_dotdot(self, client, completed_job):
        """파일명에 .. 포함."""
        request_id, _ = completed_job
        resp = client.get(f"/api/content/download/{request_id}/..secret")
        assert resp.status_code == 400

    def test_download_path_traversal_backslash(self, client, completed_job):
        """파일명에 백슬래시 포함."""
        request_id, _ = completed_job
        resp = client.get(f"/api/content/download/{request_id}/test\\file.pptx")
        assert resp.status_code == 400


class TestGuessMediaType:
    """_guess_media_type 유틸 함수 테스트."""

    def test_pptx(self):
        from server.routes.content import _guess_media_type

        assert "presentation" in _guess_media_type("slide.pptx")

    def test_html(self):
        from server.routes.content import _guess_media_type

        assert _guess_media_type("quiz.html") == "text/html"

    def test_svg(self):
        from server.routes.content import _guess_media_type

        assert _guess_media_type("chart.svg") == "image/svg+xml"

    def test_mp3(self):
        from server.routes.content import _guess_media_type

        assert _guess_media_type("audio.mp3") == "audio/mpeg"

    def test_unknown(self):
        from server.routes.content import _guess_media_type

        assert _guess_media_type("file.xyz") == "application/octet-stream"

    def test_png(self):
        from server.routes.content import _guess_media_type

        assert _guess_media_type("card.png") == "image/png"
