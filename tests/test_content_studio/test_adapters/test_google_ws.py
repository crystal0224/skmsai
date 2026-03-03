"""Google Workspace 어댑터 테스트 — Mock API 기반.

PR-048: Google Workspace 어댑터 단위 테스트.

테스트 범위:
- GoogleWSConfig frozen dataclass
- 가용성 확인 (credentials 파일 유무)
- 헬스체크
- 배포 URL 생성
- DocumentPublisher 프로토콜 준수
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.content_studio.adapters.base import DocumentPublisher, MCPAdapter
from src.content_studio.adapters.google_ws import (
    GoogleWorkspaceAdapter,
    GoogleWSConfig,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def creds_file(tmp_path: Path) -> Path:
    """임시 credentials JSON 파일."""
    creds = tmp_path / "service-account.json"
    creds.write_text('{"type": "service_account"}', encoding="utf-8")
    return creds


@pytest.fixture()
def config(creds_file: Path) -> GoogleWSConfig:
    return GoogleWSConfig(
        credentials_path=str(creds_file),
        folder_id="folder-abc123",
        auto_convert=True,
    )


@pytest.fixture()
def adapter(config: GoogleWSConfig) -> GoogleWorkspaceAdapter:
    return GoogleWorkspaceAdapter(config)


# ---------------------------------------------------------------------------
# GoogleWSConfig Tests
# ---------------------------------------------------------------------------


class TestGoogleWSConfig:
    def test_frozen(self) -> None:
        config = GoogleWSConfig()
        with pytest.raises(AttributeError):
            config.folder_id = "new-id"  # type: ignore[misc]

    def test_fields(self, creds_file: Path) -> None:
        config = GoogleWSConfig(
            credentials_path=str(creds_file),
            folder_id="folder-xyz",
            auto_convert=False,
        )
        assert config.credentials_path == str(creds_file)
        assert config.folder_id == "folder-xyz"
        assert config.auto_convert is False

    def test_defaults(self) -> None:
        config = GoogleWSConfig()
        assert config.credentials_path == ""
        assert config.folder_id == ""
        assert config.auto_convert is True


# ---------------------------------------------------------------------------
# GoogleWorkspaceAdapter Tests
# ---------------------------------------------------------------------------


class TestGoogleWorkspaceAdapter:
    @pytest.mark.asyncio
    async def test_is_available_with_creds(
        self, adapter: GoogleWorkspaceAdapter
    ) -> None:
        result = await adapter.is_available()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_available_no_creds(self) -> None:
        adapter = GoogleWorkspaceAdapter(GoogleWSConfig(credentials_path=""))
        result = await adapter.is_available()
        assert result is False

    @pytest.mark.asyncio
    async def test_is_available_missing_file(self) -> None:
        adapter = GoogleWorkspaceAdapter(
            GoogleWSConfig(credentials_path="/nonexistent/path.json")
        )
        result = await adapter.is_available()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check(self, adapter: GoogleWorkspaceAdapter) -> None:
        result = await adapter.health_check()
        assert result["status"] == "ok"
        assert result["adapter"] == "google_ws"
        assert result["has_credentials"] is True
        assert result["folder_id"] == "folder-abc123"
        assert result["auto_convert"] is True

    @pytest.mark.asyncio
    async def test_health_check_no_creds(self) -> None:
        adapter = GoogleWorkspaceAdapter(GoogleWSConfig(credentials_path=""))
        result = await adapter.health_check()
        assert result["status"] == "error"
        assert result["has_credentials"] is False

    @pytest.mark.asyncio
    async def test_publish_returns_url(self, adapter: GoogleWorkspaceAdapter) -> None:
        url = await adapter.publish(
            content={"content_type": "lecture", "topic": "SUPEX"},
            destination="google_ws",
            metadata={"title": "테스트"},
        )
        assert url is not None
        assert "drive.google.com" in url
        assert url.startswith("https://")

    @pytest.mark.asyncio
    async def test_publish_no_creds_returns_none(self) -> None:
        adapter = GoogleWorkspaceAdapter(GoogleWSConfig(credentials_path=""))
        url = await adapter.publish(
            content={"data": "test"},
            destination="google_ws",
            metadata={},
        )
        assert url is None

    def test_protocol_conformance(self, adapter: GoogleWorkspaceAdapter) -> None:
        assert isinstance(adapter, DocumentPublisher)
        assert isinstance(adapter, MCPAdapter)
