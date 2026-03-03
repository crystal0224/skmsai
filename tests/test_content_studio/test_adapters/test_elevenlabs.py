"""ElevenLabs TTS 어댑터 테스트 — Mock API 기반.

PR-042: ElevenLabs 어댑터 단위 테스트.

실제 API 호출 없이 모든 경로를 테스트한다:
- 단건 TTS
- 멀티섹션 합성
- 음성 매핑
- API 오류 시 graceful fallback
- 설정 관리
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.content_studio.adapters.base import AudioGenerator, MCPAdapter
from src.content_studio.adapters.elevenlabs import (
    DEFAULT_MODEL,
    VOICE_MAP,
    ElevenLabsAdapter,
    ElevenLabsConfig,
)
from src.content_studio.models import GeneratedAsset, ScriptSection


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def config(tmp_path: Path) -> ElevenLabsConfig:
    return ElevenLabsConfig(
        api_key="test-elevenlabs-key",
        model=DEFAULT_MODEL,
        output_dir=str(tmp_path),
        default_voice="narrator",
        default_language="ko",
    )


@pytest.fixture()
def adapter(config: ElevenLabsConfig) -> ElevenLabsAdapter:
    return ElevenLabsAdapter(config)


@pytest.fixture()
def mock_client() -> MagicMock:
    """ElevenLabs 클라이언트 mock."""
    client = MagicMock()
    # text_to_speech.convert 가 바이트를 반환하도록 설정
    client.text_to_speech.convert = MagicMock(return_value=b"\xff\xfb\x90\x00" * 100)
    return client


@pytest.fixture()
def mock_client_iterator() -> MagicMock:
    """iterator로 오디오 청크를 반환하는 mock 클라이언트."""
    client = MagicMock()
    client.text_to_speech.convert = MagicMock(
        return_value=iter([b"\xff\xfb", b"\x90\x00", b"\x00" * 50])
    )
    return client


@pytest.fixture()
def sample_sections() -> tuple[ScriptSection, ...]:
    """테스트용 스크립트 섹션."""
    return (
        ScriptSection(index=1, speaker="narrator", text="SKMS의 핵심 가치를 살펴보겠습니다."),
        ScriptSection(index=2, speaker="host", text="먼저 인간중심 경영에 대해 알아봅시다."),
        ScriptSection(index=3, speaker="expert", text="SUPEX 추구는 최고 수준의 성과를 의미합니다."),
    )


# ---------------------------------------------------------------------------
# ElevenLabsConfig Tests
# ---------------------------------------------------------------------------


class TestElevenLabsConfig:
    def test_default_config(self) -> None:
        config = ElevenLabsConfig()
        assert config.api_key is None
        assert config.model == DEFAULT_MODEL
        assert config.default_voice == "narrator"
        assert config.default_language == "ko"

    def test_config_from_dict(self) -> None:
        data = {
            "api_key": "my-key",
            "model": "eleven_monolingual_v1",
            "output_dir": "/custom/audio",
            "default_voice": "host",
            "default_language": "en",
        }
        config = ElevenLabsConfig.from_dict(data)
        assert config.api_key == "my-key"
        assert config.model == "eleven_monolingual_v1"
        assert config.default_voice == "host"
        assert config.default_language == "en"

    def test_config_from_dict_defaults(self) -> None:
        config = ElevenLabsConfig.from_dict({})
        assert config.api_key is None
        assert config.model == DEFAULT_MODEL

    def test_config_is_frozen(self) -> None:
        config = ElevenLabsConfig()
        with pytest.raises(AttributeError):
            config.model = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Protocol Conformance Tests
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_is_mcp_adapter(self, adapter: ElevenLabsAdapter) -> None:
        assert isinstance(adapter, MCPAdapter)

    def test_is_audio_generator(self, adapter: ElevenLabsAdapter) -> None:
        assert isinstance(adapter, AudioGenerator)


# ---------------------------------------------------------------------------
# Voice Mapping Tests
# ---------------------------------------------------------------------------


class TestVoiceMapping:
    def test_voice_map_keys(self) -> None:
        assert set(VOICE_MAP.keys()) == {"narrator", "host", "expert"}

    def test_voice_map_values(self) -> None:
        assert VOICE_MAP["narrator"] == "korean-female-01"
        assert VOICE_MAP["host"] == "korean-male-01"
        assert VOICE_MAP["expert"] == "korean-male-02"

    def test_resolve_known_voice(self, adapter: ElevenLabsAdapter) -> None:
        assert adapter._resolve_voice_id("narrator") == "korean-female-01"
        assert adapter._resolve_voice_id("host") == "korean-male-01"
        assert adapter._resolve_voice_id("expert") == "korean-male-02"

    def test_resolve_unknown_voice_passthrough(
        self, adapter: ElevenLabsAdapter
    ) -> None:
        assert adapter._resolve_voice_id("custom-voice-id-123") == "custom-voice-id-123"


# ---------------------------------------------------------------------------
# Availability Tests
# ---------------------------------------------------------------------------


class TestAvailability:
    @pytest.mark.asyncio
    async def test_is_available_with_api_key(
        self, adapter: ElevenLabsAdapter, mock_client: MagicMock
    ) -> None:
        adapter._client = mock_client
        result = await adapter.is_available()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_available_without_api_key(self, tmp_path: Path) -> None:
        config = ElevenLabsConfig(api_key=None, output_dir=str(tmp_path))
        adapter = ElevenLabsAdapter(config)
        adapter._api_key = ""
        result = await adapter.is_available()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_ok(
        self, adapter: ElevenLabsAdapter, mock_client: MagicMock
    ) -> None:
        adapter._client = mock_client
        result = await adapter.health_check()
        assert result["status"] == "ok"
        assert result["adapter"] == "elevenlabs"
        assert result["has_api_key"] is True

    @pytest.mark.asyncio
    async def test_health_check_error(self, tmp_path: Path) -> None:
        config = ElevenLabsConfig(api_key=None, output_dir=str(tmp_path))
        adapter = ElevenLabsAdapter(config)
        adapter._api_key = ""
        result = await adapter.health_check()
        assert result["status"] == "error"
        assert result["has_api_key"] is False


# ---------------------------------------------------------------------------
# text_to_speech Tests
# ---------------------------------------------------------------------------


class TestTextToSpeech:
    @pytest.mark.asyncio
    async def test_tts_success_bytes(
        self, adapter: ElevenLabsAdapter, mock_client: MagicMock
    ) -> None:
        """바이트 응답으로 TTS 성공."""
        adapter._client = mock_client

        result = await adapter.text_to_speech(
            "SKMS는 SK그룹의 경영 철학입니다.",
            "narrator",
            "ko",
        )

        assert result is not None
        assert result.asset_type == "audio"
        assert result.prompt_used == "SKMS는 SK그룹의 경영 철학입니다."
        assert result.file_path.endswith(".mp3")
        assert "elevenlabs" in result.file_path

        meta = dict(result.metadata)
        assert meta["adapter"] == "elevenlabs"
        assert meta["voice"] == "narrator"
        assert meta["voice_id"] == "korean-female-01"
        assert meta["language"] == "ko"

    @pytest.mark.asyncio
    async def test_tts_success_iterator(
        self, adapter: ElevenLabsAdapter, mock_client_iterator: MagicMock
    ) -> None:
        """iterator 응답으로 TTS 성공."""
        adapter._client = mock_client_iterator

        result = await adapter.text_to_speech("테스트 텍스트", "host", "ko")

        assert result is not None
        assert result.asset_type == "audio"
        file_path = Path(result.file_path)
        assert file_path.exists()
        assert file_path.stat().st_size > 0

    @pytest.mark.asyncio
    async def test_tts_creates_file(
        self, adapter: ElevenLabsAdapter, mock_client: MagicMock
    ) -> None:
        """TTS로 생성된 파일이 실제로 존재하는지 확인."""
        adapter._client = mock_client

        result = await adapter.text_to_speech("파일 생성 테스트", "narrator", "ko")
        assert result is not None

        file_path = Path(result.file_path)
        assert file_path.exists()
        assert file_path.stat().st_size > 0

    @pytest.mark.asyncio
    async def test_tts_empty_text_returns_none(
        self, adapter: ElevenLabsAdapter
    ) -> None:
        """빈 텍스트 → None."""
        result = await adapter.text_to_speech("", "narrator", "ko")
        assert result is None

    @pytest.mark.asyncio
    async def test_tts_whitespace_only_returns_none(
        self, adapter: ElevenLabsAdapter
    ) -> None:
        """공백만 있는 텍스트 → None."""
        result = await adapter.text_to_speech("   ", "narrator", "ko")
        assert result is None

    @pytest.mark.asyncio
    async def test_tts_api_error_returns_none(self, adapter: ElevenLabsAdapter) -> None:
        """API 오류 시 None 반환."""
        client = MagicMock()
        client.text_to_speech.convert = MagicMock(side_effect=RuntimeError("API error"))
        adapter._client = client

        result = await adapter.text_to_speech("test", "narrator", "ko")
        assert result is None

    @pytest.mark.asyncio
    async def test_tts_no_client_returns_none(self, tmp_path: Path) -> None:
        """클라이언트 없으면 None."""
        config = ElevenLabsConfig(api_key=None, output_dir=str(tmp_path))
        adapter = ElevenLabsAdapter(config)
        adapter._api_key = ""

        result = await adapter.text_to_speech("test", "narrator", "ko")
        assert result is None

    @pytest.mark.asyncio
    async def test_tts_empty_audio_returns_none(
        self, adapter: ElevenLabsAdapter
    ) -> None:
        """응답에 오디오 데이터 없으면 None."""
        client = MagicMock()
        client.text_to_speech.convert = MagicMock(return_value=b"")
        adapter._client = client

        result = await adapter.text_to_speech("test", "narrator", "ko")
        assert result is None

    @pytest.mark.asyncio
    async def test_tts_custom_voice_id(
        self, adapter: ElevenLabsAdapter, mock_client: MagicMock
    ) -> None:
        """VOICE_MAP에 없는 custom voice ID 사용."""
        adapter._client = mock_client

        result = await adapter.text_to_speech("test", "custom-voice-xyz", "en")
        assert result is not None

        meta = dict(result.metadata)
        assert meta["voice"] == "custom-voice-xyz"
        assert meta["voice_id"] == "custom-voice-xyz"


# ---------------------------------------------------------------------------
# synthesize_sections Tests
# ---------------------------------------------------------------------------


class TestSynthesizeSections:
    @pytest.mark.asyncio
    async def test_synthesize_success(
        self,
        adapter: ElevenLabsAdapter,
        mock_client: MagicMock,
        sample_sections: tuple[ScriptSection, ...],
    ) -> None:
        """멀티섹션 합성 성공."""
        adapter._client = mock_client

        result = await adapter.synthesize_sections(sample_sections, language="ko")

        assert result is not None
        assert result.asset_type == "audio"
        assert "elevenlabs-multi" in result.file_path
        assert result.file_path.endswith(".mp3")

        meta = dict(result.metadata)
        assert meta["sections_count"] == 3
        assert meta["total_sections"] == 3

        # 프롬프트에 모든 섹션 텍스트가 포함
        assert "[narrator]" in result.prompt_used
        assert "[host]" in result.prompt_used
        assert "[expert]" in result.prompt_used

    @pytest.mark.asyncio
    async def test_synthesize_empty_sections(self, adapter: ElevenLabsAdapter) -> None:
        """빈 섹션 목록 → None."""
        result = await adapter.synthesize_sections((), language="ko")
        assert result is None

    @pytest.mark.asyncio
    async def test_synthesize_partial_failure(self, adapter: ElevenLabsAdapter) -> None:
        """일부 섹션 실패 시 성공한 섹션만으로 결과 생성."""
        call_count = 0

        def side_effect(**kwargs: Any) -> bytes:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("TTS error on section 2")
            return b"\xff\xfb\x90\x00" * 50

        client = MagicMock()
        client.text_to_speech.convert = MagicMock(side_effect=side_effect)
        adapter._client = client

        sections = (
            ScriptSection(index=1, speaker="narrator", text="섹션 1"),
            ScriptSection(index=2, speaker="host", text="섹션 2 (실패)"),
            ScriptSection(index=3, speaker="expert", text="섹션 3"),
        )

        result = await adapter.synthesize_sections(sections, language="ko")
        assert result is not None

        meta = dict(result.metadata)
        assert meta["sections_count"] == 2  # 1 + 3 성공
        assert meta["total_sections"] == 3

    @pytest.mark.asyncio
    async def test_synthesize_all_fail(self, adapter: ElevenLabsAdapter) -> None:
        """모든 섹션 실패 → None."""
        client = MagicMock()
        client.text_to_speech.convert = MagicMock(side_effect=RuntimeError("fail"))
        adapter._client = client

        sections = (
            ScriptSection(index=1, speaker="narrator", text="섹션 1"),
            ScriptSection(index=2, speaker="host", text="섹션 2"),
        )

        result = await adapter.synthesize_sections(sections, language="ko")
        assert result is None

    @pytest.mark.asyncio
    async def test_synthesize_no_client(self, tmp_path: Path) -> None:
        """클라이언트 없으면 None."""
        config = ElevenLabsConfig(api_key=None, output_dir=str(tmp_path))
        adapter = ElevenLabsAdapter(config)
        adapter._api_key = ""

        sections = (ScriptSection(index=1, speaker="narrator", text="test"),)

        result = await adapter.synthesize_sections(sections, language="ko")
        assert result is None


# ---------------------------------------------------------------------------
# Internal Helper Tests
# ---------------------------------------------------------------------------


class TestInternalHelpers:
    def test_generate_filename_format(self, adapter: ElevenLabsAdapter) -> None:
        filename = adapter._generate_filename()
        assert filename.startswith("elevenlabs-")
        assert filename.endswith(".mp3")

    def test_generate_filename_custom_prefix(self, adapter: ElevenLabsAdapter) -> None:
        filename = adapter._generate_filename(prefix="elevenlabs-multi")
        assert filename.startswith("elevenlabs-multi-")

    def test_generate_filename_unique(self, adapter: ElevenLabsAdapter) -> None:
        filenames = {adapter._generate_filename() for _ in range(10)}
        assert len(filenames) == 10

    def test_ensure_output_dir_creates_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "audio" / "output"
        config = ElevenLabsConfig(output_dir=str(target))
        adapter = ElevenLabsAdapter(config)

        result = adapter._ensure_output_dir()
        assert result.exists()
        assert result.is_dir()
