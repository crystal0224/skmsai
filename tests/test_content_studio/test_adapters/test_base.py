"""Protocol conformance tests for MCP adapter base interfaces.

PR-041: MCP 어댑터 프로토콜 적합성 테스트.
"""
from __future__ import annotations

from typing import Any

import pytest

from scripts.lib.content_studio.adapters.base import (
    AudioGenerator,
    ChartGenerator,
    DocumentPublisher,
    ImageGenerator,
    MCPAdapter,
)
from scripts.lib.content_studio.models import GeneratedAsset


# ---------------------------------------------------------------------------
# 테스트용 구현체 (Protocol conformance 검증)
# ---------------------------------------------------------------------------


class FakeMCPAdapter:
    """MCPAdapter 프로토콜 최소 구현."""

    async def is_available(self) -> bool:
        return True

    async def health_check(self) -> dict[str, Any]:
        return {"status": "ok", "adapter": "fake"}


class FakeImageGenerator:
    """ImageGenerator 프로토콜 최소 구현."""

    async def is_available(self) -> bool:
        return True

    async def health_check(self) -> dict[str, Any]:
        return {"status": "ok", "adapter": "fake_image"}

    async def generate_image(
        self, prompt: str, width: int, height: int, style: str
    ) -> GeneratedAsset | None:
        return GeneratedAsset(
            asset_type="image",
            file_path="/tmp/test.png",
            prompt_used=prompt,
            width=width,
            height=height,
        )

    async def edit_image(
        self, image_path: str, edit_prompt: str
    ) -> GeneratedAsset | None:
        return GeneratedAsset(
            asset_type="image",
            file_path="/tmp/edited.png",
            prompt_used=edit_prompt,
        )


class FakeChartGenerator:
    """ChartGenerator 프로토콜 최소 구현."""

    async def is_available(self) -> bool:
        return True

    async def health_check(self) -> dict[str, Any]:
        return {"status": "ok", "adapter": "fake_chart"}

    async def generate_chart(
        self, chart_type: str, data: dict[str, Any], options: dict[str, Any]
    ) -> GeneratedAsset | None:
        return GeneratedAsset(
            asset_type="chart",
            file_path="/tmp/chart.svg",
            prompt_used=chart_type,
        )


class FakeAudioGenerator:
    """AudioGenerator 프로토콜 최소 구현."""

    async def is_available(self) -> bool:
        return True

    async def health_check(self) -> dict[str, Any]:
        return {"status": "ok", "adapter": "fake_audio"}

    async def text_to_speech(
        self, text: str, voice: str, language: str
    ) -> GeneratedAsset | None:
        return GeneratedAsset(
            asset_type="audio",
            file_path="/tmp/audio.mp3",
            prompt_used=text,
        )


class FakeDocumentPublisher:
    """DocumentPublisher 프로토콜 최소 구현."""

    async def is_available(self) -> bool:
        return True

    async def health_check(self) -> dict[str, Any]:
        return {"status": "ok", "adapter": "fake_publisher"}

    async def publish(
        self,
        content: dict[str, Any],
        destination: str,
        metadata: dict[str, Any],
    ) -> str | None:
        return f"https://published.example.com/{destination}"


class IncompleteAdapter:
    """MCPAdapter 프로토콜 미충족 — is_available 누락."""

    async def health_check(self) -> dict[str, Any]:
        return {"status": "ok"}


class IncompleteImageGenerator:
    """ImageGenerator 프로토콜 미충족 — generate_image 누락."""

    async def is_available(self) -> bool:
        return True

    async def health_check(self) -> dict[str, Any]:
        return {"status": "ok"}

    async def edit_image(
        self, image_path: str, edit_prompt: str
    ) -> GeneratedAsset | None:
        return None


# ---------------------------------------------------------------------------
# MCPAdapter Protocol Tests
# ---------------------------------------------------------------------------


class TestMCPAdapterProtocol:
    """MCPAdapter 프로토콜 적합성 테스트."""

    def test_fake_adapter_is_instance(self) -> None:
        adapter = FakeMCPAdapter()
        assert isinstance(adapter, MCPAdapter)

    @pytest.mark.asyncio
    async def test_fake_adapter_is_available(self) -> None:
        adapter = FakeMCPAdapter()
        result = await adapter.is_available()
        assert result is True

    @pytest.mark.asyncio
    async def test_fake_adapter_health_check(self) -> None:
        adapter = FakeMCPAdapter()
        result = await adapter.health_check()
        assert result["status"] == "ok"
        assert result["adapter"] == "fake"

    def test_incomplete_adapter_not_instance(self) -> None:
        """is_available 누락 시 MCPAdapter가 아니다."""
        adapter = IncompleteAdapter()
        assert not isinstance(adapter, MCPAdapter)


# ---------------------------------------------------------------------------
# ImageGenerator Protocol Tests
# ---------------------------------------------------------------------------


class TestImageGeneratorProtocol:
    """ImageGenerator 프로토콜 적합성 테스트."""

    def test_fake_image_gen_is_instance(self) -> None:
        gen = FakeImageGenerator()
        assert isinstance(gen, ImageGenerator)

    def test_fake_image_gen_is_also_mcp_adapter(self) -> None:
        gen = FakeImageGenerator()
        assert isinstance(gen, MCPAdapter)

    @pytest.mark.asyncio
    async def test_generate_image_returns_asset(self) -> None:
        gen = FakeImageGenerator()
        result = await gen.generate_image("a blue sky", 1024, 1024, "professional")
        assert result is not None
        assert result.asset_type == "image"
        assert result.width == 1024
        assert result.height == 1024

    @pytest.mark.asyncio
    async def test_edit_image_returns_asset(self) -> None:
        gen = FakeImageGenerator()
        result = await gen.edit_image("/tmp/test.png", "make it brighter")
        assert result is not None
        assert result.asset_type == "image"
        assert result.prompt_used == "make it brighter"

    def test_incomplete_image_gen_not_instance(self) -> None:
        """generate_image 누락 시 ImageGenerator가 아니다."""
        gen = IncompleteImageGenerator()
        assert not isinstance(gen, ImageGenerator)


# ---------------------------------------------------------------------------
# ChartGenerator Protocol Tests
# ---------------------------------------------------------------------------


class TestChartGeneratorProtocol:
    """ChartGenerator 프로토콜 적합성 테스트."""

    def test_fake_chart_gen_is_instance(self) -> None:
        gen = FakeChartGenerator()
        assert isinstance(gen, ChartGenerator)

    def test_fake_chart_gen_is_also_mcp_adapter(self) -> None:
        gen = FakeChartGenerator()
        assert isinstance(gen, MCPAdapter)

    @pytest.mark.asyncio
    async def test_generate_chart_returns_asset(self) -> None:
        gen = FakeChartGenerator()
        result = await gen.generate_chart("bar", {"x": [1, 2]}, {"theme": "dark"})
        assert result is not None
        assert result.asset_type == "chart"


# ---------------------------------------------------------------------------
# AudioGenerator Protocol Tests
# ---------------------------------------------------------------------------


class TestAudioGeneratorProtocol:
    """AudioGenerator 프로토콜 적합성 테스트."""

    def test_fake_audio_gen_is_instance(self) -> None:
        gen = FakeAudioGenerator()
        assert isinstance(gen, AudioGenerator)

    def test_fake_audio_gen_is_also_mcp_adapter(self) -> None:
        gen = FakeAudioGenerator()
        assert isinstance(gen, MCPAdapter)

    @pytest.mark.asyncio
    async def test_text_to_speech_returns_asset(self) -> None:
        gen = FakeAudioGenerator()
        result = await gen.text_to_speech("안녕하세요", "alloy", "ko")
        assert result is not None
        assert result.asset_type == "audio"


# ---------------------------------------------------------------------------
# DocumentPublisher Protocol Tests
# ---------------------------------------------------------------------------


class TestDocumentPublisherProtocol:
    """DocumentPublisher 프로토콜 적합성 테스트."""

    def test_fake_publisher_is_instance(self) -> None:
        pub = FakeDocumentPublisher()
        assert isinstance(pub, DocumentPublisher)

    def test_fake_publisher_is_also_mcp_adapter(self) -> None:
        pub = FakeDocumentPublisher()
        assert isinstance(pub, MCPAdapter)

    @pytest.mark.asyncio
    async def test_publish_returns_url(self) -> None:
        pub = FakeDocumentPublisher()
        result = await pub.publish(
            {"title": "test"}, "courses/123", {"author": "admin"}
        )
        assert result is not None
        assert "courses/123" in result
