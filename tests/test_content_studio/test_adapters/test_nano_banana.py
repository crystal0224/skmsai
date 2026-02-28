"""NanoBanana 어댑터 테스트 — Mock API 기반.

PR-041: NanoBanana 2 어댑터 단위 테스트.

실제 API 호출 없이 모든 경로를 테스트한다:
- 정상 이미지 생성
- 이미지 편집
- 해상도/종횡비 매핑
- API 오류 시 graceful fallback
- 설정 관리
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.lib.content_studio.adapters.base import ImageGenerator, MCPAdapter
from scripts.lib.content_studio.adapters.nano_banana import (
    ASPECT_RATIO_MAP,
    DEFAULT_OUTPUT_DIR,
    RESOLUTION_MAP,
    NanoBananaAdapter,
    NanoBananaConfig,
)
from scripts.lib.content_studio.models import GeneratedAsset


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def config() -> NanoBananaConfig:
    """테스트용 설정."""
    return NanoBananaConfig(
        api_key="test-api-key-123",
        model="gemini-2.0-flash-exp",
        output_dir="/tmp/test-nano-banana-assets",
        default_style="professional",
    )


@pytest.fixture()
def adapter(config: NanoBananaConfig) -> NanoBananaAdapter:
    """테스트용 어댑터."""
    return NanoBananaAdapter(config)


@pytest.fixture()
def mock_response() -> MagicMock:
    """성공적인 Gemini 응답 모의 객체."""
    response = MagicMock()
    response.images = None  # Gemini 2.0 uses parts

    part = MagicMock()
    part.inline_data = MagicMock()
    part.inline_data.data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # fake PNG

    response.parts = [part]
    return response


@pytest.fixture()
def mock_client(mock_response: MagicMock) -> MagicMock:
    """Gemini 클라이언트 모의 객체."""
    client = MagicMock()
    client.generate_content = MagicMock(return_value=mock_response)
    return client


# ---------------------------------------------------------------------------
# NanoBananaConfig Tests
# ---------------------------------------------------------------------------


class TestNanoBananaConfig:
    """NanoBananaConfig 테스트."""

    def test_default_config(self) -> None:
        config = NanoBananaConfig()
        assert config.api_key is None
        assert config.model == "gemini-2.0-flash-exp"
        assert config.output_dir == DEFAULT_OUTPUT_DIR
        assert config.default_style == "professional"

    def test_config_from_dict(self) -> None:
        data = {
            "api_key": "my-key",
            "model": "gemini-pro",
            "output_dir": "/custom/path",
            "default_style": "casual",
        }
        config = NanoBananaConfig.from_dict(data)
        assert config.api_key == "my-key"
        assert config.model == "gemini-pro"
        assert config.output_dir == "/custom/path"
        assert config.default_style == "casual"

    def test_config_from_dict_defaults(self) -> None:
        config = NanoBananaConfig.from_dict({})
        assert config.api_key is None
        assert config.model == "gemini-2.0-flash-exp"

    def test_config_is_frozen(self) -> None:
        config = NanoBananaConfig()
        with pytest.raises(AttributeError):
            config.model = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Protocol Conformance Tests
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """NanoBananaAdapter가 프로토콜을 올바르게 구현하는지 검증."""

    def test_is_mcp_adapter(self, adapter: NanoBananaAdapter) -> None:
        assert isinstance(adapter, MCPAdapter)

    def test_is_image_generator(self, adapter: NanoBananaAdapter) -> None:
        assert isinstance(adapter, ImageGenerator)


# ---------------------------------------------------------------------------
# Resolution/Aspect Ratio Constants Tests
# ---------------------------------------------------------------------------


class TestResolutionMaps:
    """해상도/종횡비 매핑 상수 테스트."""

    def test_resolution_map_keys(self) -> None:
        assert set(RESOLUTION_MAP.keys()) == {"512", "1K", "2K", "4K"}

    def test_resolution_map_values(self) -> None:
        assert RESOLUTION_MAP["512"] == (512, 512)
        assert RESOLUTION_MAP["1K"] == (1024, 1024)
        assert RESOLUTION_MAP["2K"] == (2048, 2048)
        assert RESOLUTION_MAP["4K"] == (4096, 4096)

    def test_aspect_ratio_map_keys(self) -> None:
        assert set(ASPECT_RATIO_MAP.keys()) == {"16:9", "1:1", "9:16"}

    def test_aspect_ratio_map_values(self) -> None:
        assert ASPECT_RATIO_MAP["16:9"] == (1920, 1080)
        assert ASPECT_RATIO_MAP["1:1"] == (1080, 1080)
        assert ASPECT_RATIO_MAP["9:16"] == (1080, 1920)


# ---------------------------------------------------------------------------
# is_available / health_check Tests
# ---------------------------------------------------------------------------


class TestAvailability:
    """가용성 및 헬스체크 테스트."""

    @pytest.mark.asyncio
    async def test_is_available_with_api_key(
        self, adapter: NanoBananaAdapter, mock_client: MagicMock
    ) -> None:
        adapter._client = mock_client
        result = await adapter.is_available()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_available_without_api_key(self) -> None:
        config = NanoBananaConfig(api_key=None)
        adapter = NanoBananaAdapter(config)
        adapter._api_key = ""
        result = await adapter.is_available()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_ok(
        self, adapter: NanoBananaAdapter, mock_client: MagicMock
    ) -> None:
        adapter._client = mock_client
        result = await adapter.health_check()
        assert result["status"] == "ok"
        assert result["adapter"] == "nano_banana"
        assert result["model"] == "gemini-2.0-flash-exp"
        assert result["has_api_key"] is True

    @pytest.mark.asyncio
    async def test_health_check_error_no_key(self) -> None:
        config = NanoBananaConfig(api_key=None)
        adapter = NanoBananaAdapter(config)
        adapter._api_key = ""
        result = await adapter.health_check()
        assert result["status"] == "error"
        assert result["has_api_key"] is False


# ---------------------------------------------------------------------------
# generate_image Tests
# ---------------------------------------------------------------------------


class TestGenerateImage:
    """이미지 생성 테스트."""

    @pytest.mark.asyncio
    async def test_generate_image_success(
        self, adapter: NanoBananaAdapter, mock_client: MagicMock, tmp_path: Path
    ) -> None:
        adapter._client = mock_client
        adapter._config = NanoBananaConfig(
            api_key="test-key",
            output_dir=str(tmp_path),
        )

        result = await adapter.generate_image(
            prompt="SKMS 인간중심경영 일러스트",
            width=1024,
            height=1024,
            style="professional",
        )

        assert result is not None
        assert result.asset_type == "image"
        assert result.width == 1024
        assert result.height == 1024
        assert result.prompt_used == "SKMS 인간중심경영 일러스트"
        assert "nano-banana" in result.file_path
        assert result.file_path.endswith(".png")

        # metadata 확인
        meta = dict(result.metadata)
        assert meta["adapter"] == "nano_banana"
        assert meta["style"] == "professional"

    @pytest.mark.asyncio
    async def test_generate_image_creates_file(
        self, adapter: NanoBananaAdapter, mock_client: MagicMock, tmp_path: Path
    ) -> None:
        adapter._client = mock_client
        adapter._config = NanoBananaConfig(
            api_key="test-key",
            output_dir=str(tmp_path),
        )

        result = await adapter.generate_image("test", 512, 512, "casual")
        assert result is not None

        file_path = Path(result.file_path)
        assert file_path.exists()
        assert file_path.stat().st_size > 0

    @pytest.mark.asyncio
    async def test_generate_image_with_images_attr(
        self, adapter: NanoBananaAdapter, tmp_path: Path
    ) -> None:
        """response.images 속성을 사용하는 응답 형식 테스트."""
        response = MagicMock()
        response.images = [b"\x89PNG" + b"\x00" * 50]
        response.parts = None

        client = MagicMock()
        client.generate_content = MagicMock(return_value=response)
        adapter._client = client
        adapter._config = NanoBananaConfig(
            api_key="test-key",
            output_dir=str(tmp_path),
        )

        result = await adapter.generate_image("test", 512, 512, "casual")
        assert result is not None
        assert result.asset_type == "image"

    @pytest.mark.asyncio
    async def test_generate_image_no_data_in_response(
        self, adapter: NanoBananaAdapter, tmp_path: Path
    ) -> None:
        """응답에 이미지 데이터가 없는 경우."""
        response = MagicMock()
        response.images = None
        part = MagicMock()
        part.inline_data = None
        response.parts = [part]

        client = MagicMock()
        client.generate_content = MagicMock(return_value=response)
        adapter._client = client
        adapter._config = NanoBananaConfig(
            api_key="test-key",
            output_dir=str(tmp_path),
        )

        result = await adapter.generate_image("test", 512, 512, "casual")
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_image_unsupported_response_format(
        self, adapter: NanoBananaAdapter, tmp_path: Path
    ) -> None:
        """지원하지 않는 응답 형식일 경우."""
        response = MagicMock(spec=[])  # no images, no parts
        client = MagicMock()
        client.generate_content = MagicMock(return_value=response)
        adapter._client = client
        adapter._config = NanoBananaConfig(
            api_key="test-key",
            output_dir=str(tmp_path),
        )

        result = await adapter.generate_image("test", 512, 512, "casual")
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_image_api_error_returns_none(
        self, adapter: NanoBananaAdapter, tmp_path: Path
    ) -> None:
        """API 오류 시 None 반환 (graceful fallback)."""
        client = MagicMock()
        client.generate_content = MagicMock(side_effect=RuntimeError("API error"))
        adapter._client = client
        adapter._config = NanoBananaConfig(
            api_key="test-key",
            output_dir=str(tmp_path),
        )

        result = await adapter.generate_image("test", 1024, 1024, "professional")
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_image_no_client_returns_none(self, tmp_path: Path) -> None:
        """클라이언트 초기화 실패 시 None 반환."""
        config = NanoBananaConfig(api_key=None, output_dir=str(tmp_path))
        adapter = NanoBananaAdapter(config)
        adapter._api_key = ""

        result = await adapter.generate_image("test", 1024, 1024, "professional")
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_image_invalid_dimensions_uses_default(
        self, adapter: NanoBananaAdapter, mock_client: MagicMock, tmp_path: Path
    ) -> None:
        """유효하지 않은 크기 → 기본값 1024x1024 사용."""
        adapter._client = mock_client
        adapter._config = NanoBananaConfig(
            api_key="test-key",
            output_dir=str(tmp_path),
        )

        result = await adapter.generate_image("test", -1, 0, "professional")
        assert result is not None
        assert result.width == 1024
        assert result.height == 1024


# ---------------------------------------------------------------------------
# edit_image Tests
# ---------------------------------------------------------------------------


class TestEditImage:
    """이미지 편집 테스트."""

    @pytest.mark.asyncio
    async def test_edit_image_success(
        self, adapter: NanoBananaAdapter, mock_client: MagicMock, tmp_path: Path
    ) -> None:
        # 원본 이미지 생성
        source_file = tmp_path / "source.png"
        source_file.write_bytes(b"\x89PNG\r\n" + b"\x00" * 50)

        adapter._client = mock_client
        adapter._config = NanoBananaConfig(
            api_key="test-key",
            output_dir=str(tmp_path / "output"),
        )

        result = await adapter.edit_image(str(source_file), "더 밝게 해줘")
        assert result is not None
        assert result.asset_type == "image"
        assert result.prompt_used == "더 밝게 해줘"

        meta = dict(result.metadata)
        assert meta["source_image"] == str(source_file)

    @pytest.mark.asyncio
    async def test_edit_image_source_not_found(
        self, adapter: NanoBananaAdapter
    ) -> None:
        """원본 파일 없으면 None 반환."""
        result = await adapter.edit_image("/nonexistent/file.png", "edit")
        assert result is None

    @pytest.mark.asyncio
    async def test_edit_image_api_error_returns_none(
        self, adapter: NanoBananaAdapter, tmp_path: Path
    ) -> None:
        """편집 API 오류 시 None 반환."""
        source_file = tmp_path / "source.png"
        source_file.write_bytes(b"\x89PNG\r\n" + b"\x00" * 50)

        client = MagicMock()
        client.generate_content = MagicMock(side_effect=RuntimeError("API error"))
        adapter._client = client
        adapter._config = NanoBananaConfig(
            api_key="test-key",
            output_dir=str(tmp_path / "output"),
        )

        result = await adapter.edit_image(str(source_file), "edit prompt")
        assert result is None

    @pytest.mark.asyncio
    async def test_edit_image_no_client_returns_none(self, tmp_path: Path) -> None:
        """클라이언트 없으면 None 반환."""
        source_file = tmp_path / "source.png"
        source_file.write_bytes(b"\x89PNG\r\n" + b"\x00" * 50)

        config = NanoBananaConfig(api_key=None, output_dir=str(tmp_path))
        adapter = NanoBananaAdapter(config)
        adapter._api_key = ""

        result = await adapter.edit_image(str(source_file), "edit")
        assert result is None


# ---------------------------------------------------------------------------
# Internal Helper Tests
# ---------------------------------------------------------------------------


class TestInternalHelpers:
    """내부 헬퍼 메서드 테스트."""

    def test_generate_filename_format(self, adapter: NanoBananaAdapter) -> None:
        filename = adapter._generate_filename()
        assert filename.startswith("nano-banana-")
        assert filename.endswith(".png")
        # 형식: nano-banana-YYYYMMDD-HHMMSS-{uuid8}.png
        parts = filename.replace(".png", "").split("-")
        assert len(parts) >= 4

    def test_generate_filename_unique(self, adapter: NanoBananaAdapter) -> None:
        filenames = {adapter._generate_filename() for _ in range(10)}
        assert len(filenames) == 10

    def test_resolve_dimensions_valid(self, adapter: NanoBananaAdapter) -> None:
        assert adapter._resolve_dimensions(1920, 1080) == (1920, 1080)
        assert adapter._resolve_dimensions(512, 512) == (512, 512)

    def test_resolve_dimensions_invalid_uses_default(
        self, adapter: NanoBananaAdapter
    ) -> None:
        assert adapter._resolve_dimensions(0, 1024) == (1024, 1024)
        assert adapter._resolve_dimensions(-1, -1) == (1024, 1024)

    def test_ensure_output_dir_creates_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "new" / "subdir"
        config = NanoBananaConfig(output_dir=str(target))
        adapter = NanoBananaAdapter(config)

        result = adapter._ensure_output_dir()
        assert result.exists()
        assert result.is_dir()
        assert result == target
