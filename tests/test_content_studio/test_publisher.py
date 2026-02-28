"""Publisher 서비스 테스트.

PR-048: Publisher 서비스 단위 테스트.

테스트 범위:
- PublishResult frozen dataclass
- Publisher 초기화 및 어댑터 등록
- 로컬 배포 (항상 성공)
- 어댑터 배포 (성공/실패)
- 부분 실패 처리
- 빈 목적지 처리
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from scripts.lib.content_studio.publisher import Publisher, PublishResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_adapter_success() -> AsyncMock:
    """성공하는 mock 어댑터."""
    adapter = AsyncMock()
    adapter.publish = AsyncMock(return_value="https://example.com/published")
    adapter.is_available = AsyncMock(return_value=True)
    adapter.health_check = AsyncMock(return_value={"status": "ok", "adapter": "mock"})
    return adapter


@pytest.fixture()
def mock_adapter_failure() -> AsyncMock:
    """실패하는 mock 어댑터."""
    adapter = AsyncMock()
    adapter.publish = AsyncMock(side_effect=RuntimeError("배포 오류"))
    adapter.is_available = AsyncMock(return_value=True)
    adapter.health_check = AsyncMock(
        return_value={"status": "ok", "adapter": "mock_fail"}
    )
    return adapter


@pytest.fixture()
def mock_adapter_returns_none() -> AsyncMock:
    """None을 반환하는 mock 어댑터."""
    adapter = AsyncMock()
    adapter.publish = AsyncMock(return_value=None)
    adapter.is_available = AsyncMock(return_value=True)
    adapter.health_check = AsyncMock(
        return_value={"status": "ok", "adapter": "mock_none"}
    )
    return adapter


@pytest.fixture()
def sample_result() -> dict[str, Any]:
    """배포할 샘플 콘텐츠 결과."""
    return {"content_type": "lecture", "topic": "SUPEX 추구"}


# ---------------------------------------------------------------------------
# PublishResult Tests
# ---------------------------------------------------------------------------


class TestPublishResult:
    def test_frozen(self) -> None:
        result = PublishResult(
            destination="local",
            url=None,
            success=True,
            error=None,
            timestamp="2026-02-28T00:00:00+00:00",
        )
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]

    def test_fields_correct(self) -> None:
        result = PublishResult(
            destination="notion",
            url="https://notion.so/page-abc",
            success=True,
            error=None,
            timestamp="2026-02-28T12:00:00+00:00",
        )
        assert result.destination == "notion"
        assert result.url == "https://notion.so/page-abc"
        assert result.success is True
        assert result.error is None
        assert result.timestamp == "2026-02-28T12:00:00+00:00"

    def test_fields_failure(self) -> None:
        result = PublishResult(
            destination="google_ws",
            url=None,
            success=False,
            error="credentials not found",
            timestamp="2026-02-28T12:00:00+00:00",
        )
        assert result.success is False
        assert result.url is None
        assert result.error == "credentials not found"


# ---------------------------------------------------------------------------
# Publisher Init Tests
# ---------------------------------------------------------------------------


class TestPublisherInit:
    def test_empty_init(self) -> None:
        publisher = Publisher()
        assert publisher._adapters == {}

    def test_init_with_adapters(self, mock_adapter_success: AsyncMock) -> None:
        publisher = Publisher(adapters={"notion": mock_adapter_success})
        assert "notion" in publisher._adapters

    def test_register_adapter(self, mock_adapter_success: AsyncMock) -> None:
        publisher = Publisher()
        publisher.register("notion", mock_adapter_success)
        assert "notion" in publisher._adapters


# ---------------------------------------------------------------------------
# Publish Tests
# ---------------------------------------------------------------------------


class TestPublish:
    @pytest.mark.asyncio
    async def test_local_success(self, sample_result: dict[str, Any]) -> None:
        """로컬 배포는 항상 성공."""
        publisher = Publisher()
        results = await publisher.publish(sample_result, ["local"])

        assert len(results) == 1
        assert results[0].destination == "local"
        assert results[0].success is True
        assert results[0].url is None
        assert results[0].error is None

    @pytest.mark.asyncio
    async def test_single_adapter_success(
        self,
        mock_adapter_success: AsyncMock,
        sample_result: dict[str, Any],
    ) -> None:
        """단일 어댑터 배포 성공."""
        publisher = Publisher(adapters={"notion": mock_adapter_success})
        results = await publisher.publish(sample_result, ["notion"])

        assert len(results) == 1
        assert results[0].destination == "notion"
        assert results[0].success is True
        assert results[0].url == "https://example.com/published"

    @pytest.mark.asyncio
    async def test_multi_adapter(
        self,
        mock_adapter_success: AsyncMock,
        sample_result: dict[str, Any],
    ) -> None:
        """여러 대상 동시 배포."""
        adapter2 = AsyncMock()
        adapter2.publish = AsyncMock(return_value="https://drive.google.com/file/d/abc")

        publisher = Publisher(
            adapters={"notion": mock_adapter_success, "google_ws": adapter2}
        )
        results = await publisher.publish(
            sample_result, ["local", "notion", "google_ws"]
        )

        assert len(results) == 3
        assert results[0].destination == "local"
        assert results[0].success is True
        assert results[1].destination == "notion"
        assert results[1].success is True
        assert results[2].destination == "google_ws"
        assert results[2].success is True

    @pytest.mark.asyncio
    async def test_partial_failure(
        self,
        mock_adapter_success: AsyncMock,
        mock_adapter_failure: AsyncMock,
        sample_result: dict[str, Any],
    ) -> None:
        """하나가 실패해도 나머지는 성공."""
        publisher = Publisher(
            adapters={
                "notion": mock_adapter_success,
                "broken": mock_adapter_failure,
            }
        )
        results = await publisher.publish(sample_result, ["notion", "broken"])

        assert len(results) == 2
        assert results[0].destination == "notion"
        assert results[0].success is True
        assert results[1].destination == "broken"
        assert results[1].success is False
        assert results[1].error is not None

    @pytest.mark.asyncio
    async def test_empty_destinations(self, sample_result: dict[str, Any]) -> None:
        """빈 목적지 목록 → 빈 결과."""
        publisher = Publisher()
        results = await publisher.publish(sample_result, [])
        assert results == ()

    @pytest.mark.asyncio
    async def test_all_fail(
        self,
        mock_adapter_failure: AsyncMock,
        sample_result: dict[str, Any],
    ) -> None:
        """모든 어댑터 실패."""
        adapter2 = AsyncMock()
        adapter2.publish = AsyncMock(side_effect=ValueError("오류"))

        publisher = Publisher(adapters={"a": mock_adapter_failure, "b": adapter2})
        results = await publisher.publish(sample_result, ["a", "b"])

        assert len(results) == 2
        assert all(not r.success for r in results)
        assert all(r.error is not None for r in results)

    @pytest.mark.asyncio
    async def test_unregistered_destination(
        self, sample_result: dict[str, Any]
    ) -> None:
        """등록되지 않은 배포 대상."""
        publisher = Publisher()
        results = await publisher.publish(sample_result, ["unknown"])

        assert len(results) == 1
        assert results[0].success is False
        assert "등록되지 않은" in (results[0].error or "")

    @pytest.mark.asyncio
    async def test_result_is_tuple(self, sample_result: dict[str, Any]) -> None:
        """결과가 tuple (불변)."""
        publisher = Publisher()
        results = await publisher.publish(sample_result, ["local"])
        assert isinstance(results, tuple)

    @pytest.mark.asyncio
    async def test_timestamp_is_iso_format(self, sample_result: dict[str, Any]) -> None:
        """타임스탬프가 ISO 형식."""
        publisher = Publisher()
        results = await publisher.publish(sample_result, ["local"])
        assert "T" in results[0].timestamp

    @pytest.mark.asyncio
    async def test_adapter_returns_none(
        self,
        mock_adapter_returns_none: AsyncMock,
        sample_result: dict[str, Any],
    ) -> None:
        """어댑터가 None 반환 시 실패 처리."""
        publisher = Publisher(adapters={"none_adapter": mock_adapter_returns_none})
        results = await publisher.publish(sample_result, ["none_adapter"])

        assert len(results) == 1
        assert results[0].success is False
        assert results[0].url is None

    @pytest.mark.asyncio
    async def test_publish_with_to_dict_result(
        self,
        mock_adapter_success: AsyncMock,
    ) -> None:
        """to_dict() 메서드가 있는 결과 객체."""

        class FakeResult:
            metadata = (("key", "value"),)

            def to_dict(self) -> dict[str, Any]:
                return {"content_type": "lecture", "topic": "test"}

        publisher = Publisher(adapters={"notion": mock_adapter_success})
        results = await publisher.publish(FakeResult(), ["notion"])

        assert len(results) == 1
        assert results[0].success is True
