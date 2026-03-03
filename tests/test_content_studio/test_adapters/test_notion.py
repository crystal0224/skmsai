"""Notion 어댑터 테스트 — Mock API 기반.

PR-048: Notion 어댑터 단위 테스트.

테스트 범위:
- NotionConfig frozen dataclass
- 가용성 확인 (API 키 유무)
- 헬스체크
- 배포 URL 생성
- DocumentPublisher 프로토콜 준수
"""
from __future__ import annotations

import pytest

from src.content_studio.adapters.base import DocumentPublisher, MCPAdapter
from src.content_studio.adapters.notion import (
    NotionAdapter,
    NotionConfig,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def config() -> NotionConfig:
    return NotionConfig(
        api_key="test-notion-key",
        database_id="db-12345",
        workspace_name="SKMS-Test",
    )


@pytest.fixture()
def adapter(config: NotionConfig) -> NotionAdapter:
    return NotionAdapter(config)


# ---------------------------------------------------------------------------
# NotionConfig Tests
# ---------------------------------------------------------------------------


class TestNotionConfig:
    def test_frozen(self) -> None:
        config = NotionConfig()
        with pytest.raises(AttributeError):
            config.api_key = "new-key"  # type: ignore[misc]

    def test_fields(self) -> None:
        config = NotionConfig(
            api_key="key-abc",
            database_id="db-xyz",
            workspace_name="MyWorkspace",
        )
        assert config.api_key == "key-abc"
        assert config.database_id == "db-xyz"
        assert config.workspace_name == "MyWorkspace"

    def test_defaults(self) -> None:
        config = NotionConfig()
        assert config.api_key == ""
        assert config.database_id == ""
        assert config.workspace_name == "SKMS"


# ---------------------------------------------------------------------------
# NotionAdapter Tests
# ---------------------------------------------------------------------------


class TestNotionAdapter:
    @pytest.mark.asyncio
    async def test_is_available_with_key(self, adapter: NotionAdapter) -> None:
        result = await adapter.is_available()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_available_no_key(self) -> None:
        adapter = NotionAdapter(NotionConfig(api_key=""))
        result = await adapter.is_available()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check(self, adapter: NotionAdapter) -> None:
        result = await adapter.health_check()
        assert result["status"] == "ok"
        assert result["adapter"] == "notion"
        assert result["has_api_key"] is True
        assert result["database_id"] == "db-12345"
        assert result["workspace_name"] == "SKMS-Test"

    @pytest.mark.asyncio
    async def test_health_check_no_key(self) -> None:
        adapter = NotionAdapter(NotionConfig(api_key=""))
        result = await adapter.health_check()
        assert result["status"] == "error"
        assert result["has_api_key"] is False

    @pytest.mark.asyncio
    async def test_publish_returns_url(self, adapter: NotionAdapter) -> None:
        url = await adapter.publish(
            content={"content_type": "lecture", "topic": "SUPEX"},
            destination="notion",
            metadata={"title": "테스트"},
        )
        assert url is not None
        assert "notion.so" in url
        assert "db-12345" in url
        assert url.startswith("https://")

    @pytest.mark.asyncio
    async def test_publish_no_key_returns_none(self) -> None:
        adapter = NotionAdapter(NotionConfig(api_key=""))
        url = await adapter.publish(
            content={"data": "test"},
            destination="notion",
            metadata={},
        )
        assert url is None

    def test_protocol_conformance(self, adapter: NotionAdapter) -> None:
        assert isinstance(adapter, DocumentPublisher)
        assert isinstance(adapter, MCPAdapter)
