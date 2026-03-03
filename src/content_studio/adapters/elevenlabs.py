"""ElevenLabs TTS 오디오 생성 어댑터.

PR-042: ElevenLabs API 기반 음성 합성.

ElevenLabs API를 통해 텍스트를 음성(MP3)으로 변환한다.
AudioGenerator 프로토콜을 구현한다.

음성 매핑 (SKMS 기본):
- narrator → korean-female-01 (나레이터)
- host → korean-male-01 (진행자)
- expert → korean-male-02 (전문가)

멀티섹션 합성:
- 여러 ScriptSection을 순차적으로 합성하여 단일 MP3로 연결한다.
"""
from __future__ import annotations

import io
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.content_studio.models import GeneratedAsset, ScriptSection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

VOICE_MAP: dict[str, str] = {
    "narrator": "korean-female-01",
    "host": "korean-male-01",
    "expert": "korean-male-02",
}

DEFAULT_OUTPUT_DIR = "output/assets"

DEFAULT_MODEL = "eleven_multilingual_v2"


# ---------------------------------------------------------------------------
# ElevenLabsConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ElevenLabsConfig:
    """ElevenLabs 어댑터 설정 (불변).

    Attributes:
        api_key: ElevenLabs API 키. None이면 환경변수에서 읽는다.
        model: 사용할 TTS 모델.
        output_dir: 오디오 출력 디렉토리.
        default_voice: 기본 음성 ID.
        default_language: 기본 언어.
    """

    api_key: str | None = None
    model: str = DEFAULT_MODEL
    output_dir: str = DEFAULT_OUTPUT_DIR
    default_voice: str = "narrator"
    default_language: str = "ko"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ElevenLabsConfig:
        return cls(
            api_key=data.get("api_key"),
            model=data.get("model", DEFAULT_MODEL),
            output_dir=data.get("output_dir", DEFAULT_OUTPUT_DIR),
            default_voice=data.get("default_voice", "narrator"),
            default_language=data.get("default_language", "ko"),
        )


# ---------------------------------------------------------------------------
# ElevenLabsAdapter
# ---------------------------------------------------------------------------


class ElevenLabsAdapter:
    """ElevenLabs TTS 오디오 생성 어댑터.

    ElevenLabs API를 사용하여 텍스트를 음성으로 변환한다.
    AudioGenerator 프로토콜을 구현한다.

    API 오류 시 None을 반환하고 경고 로그를 남긴다 (graceful fallback).
    """

    def __init__(self, config: ElevenLabsConfig | None = None) -> None:
        self._config = config or ElevenLabsConfig()
        self._api_key = self._config.api_key or os.environ.get("ELEVENLABS_API_KEY", "")
        self._client: Any = None

    def _ensure_output_dir(self) -> Path:
        """출력 디렉토리를 확인/생성하고 Path를 반환한다."""
        output_path = Path(self._config.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        return output_path

    def _generate_filename(self, prefix: str = "elevenlabs") -> str:
        """고유 파일명을 생성한다: {prefix}-{timestamp}-{uuid[:8]}.mp3"""
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
        uid = uuid.uuid4().hex[:8]
        return f"{prefix}-{ts}-{uid}.mp3"

    def _resolve_voice_id(self, voice: str) -> str:
        """음성 이름을 ElevenLabs voice ID로 변환한다.

        VOICE_MAP에 있으면 매핑된 ID를 반환, 없으면 원본을 그대로 사용한다.
        """
        return VOICE_MAP.get(voice, voice)

    def _get_client(self) -> Any:
        """ElevenLabs 클라이언트를 lazy 초기화한다."""
        if self._client is not None:
            return self._client

        if not self._api_key:
            logger.warning("ELEVENLABS_API_KEY 미설정")
            return None

        try:
            from elevenlabs.client import ElevenLabs

            self._client = ElevenLabs(api_key=self._api_key)
            return self._client
        except ImportError:
            logger.warning("elevenlabs 패키지 미설치")
            return None
        except Exception:
            logger.warning("ElevenLabs 클라이언트 초기화 실패", exc_info=True)
            return None

    async def is_available(self) -> bool:
        """API 키가 설정되어 있고 클라이언트 초기화가 가능한지 확인한다."""
        if not self._api_key:
            return False
        client = self._get_client()
        return client is not None

    async def health_check(self) -> dict[str, Any]:
        """어댑터 상태를 반환한다."""
        available = await self.is_available()
        return {
            "status": "ok" if available else "error",
            "adapter": "elevenlabs",
            "model": self._config.model,
            "has_api_key": bool(self._api_key),
            "output_dir": self._config.output_dir,
        }

    async def text_to_speech(
        self,
        text: str,
        voice: str,
        language: str,
    ) -> GeneratedAsset | None:
        """텍스트를 음성으로 변환한다.

        Args:
            text: 변환할 텍스트.
            voice: 음성 이름 또는 ID (narrator, host, expert 등).
            language: 언어 코드 (ko, en 등).

        Returns:
            GeneratedAsset (MP3 파일) 또는 None (실패 시).
        """
        if not text or not text.strip():
            logger.warning("빈 텍스트는 변환할 수 없습니다")
            return None

        voice_id = self._resolve_voice_id(voice)

        try:
            client = self._get_client()
            if client is None:
                logger.warning("ElevenLabs 클라이언트 사용 불가")
                return None

            audio_data = client.text_to_speech.convert(
                text=text,
                voice_id=voice_id,
                model_id=self._config.model,
            )

            # 응답이 iterator인 경우 바이트로 합치기
            if hasattr(audio_data, "__iter__") and not isinstance(audio_data, bytes):
                audio_bytes = b"".join(audio_data)
            else:
                audio_bytes = audio_data

            if not audio_bytes:
                logger.warning("TTS 응답에 오디오 데이터 없음")
                return None

            output_dir = self._ensure_output_dir()
            filename = self._generate_filename()
            file_path = output_dir / filename
            file_path.write_bytes(audio_bytes)

            return GeneratedAsset(
                asset_type="audio",
                file_path=str(file_path),
                prompt_used=text,
                metadata=(
                    ("adapter", "elevenlabs"),
                    ("model", self._config.model),
                    ("voice", voice),
                    ("voice_id", voice_id),
                    ("language", language),
                ),
            )

        except Exception:
            logger.warning("ElevenLabs TTS 실패", exc_info=True)
            return None

    async def synthesize_sections(
        self,
        sections: tuple[ScriptSection, ...],
        language: str = "ko",
    ) -> GeneratedAsset | None:
        """여러 ScriptSection을 순차적으로 합성하여 단일 MP3로 반환한다.

        Args:
            sections: 스크립트 섹션 목록.
            language: 언어 코드.

        Returns:
            GeneratedAsset (합성된 MP3) 또는 None (실패 시).
        """
        if not sections:
            logger.warning("합성할 섹션이 없습니다")
            return None

        audio_chunks: list[bytes] = []
        full_text_parts: list[str] = []

        for section in sections:
            voice = section.speaker
            voice_id = self._resolve_voice_id(voice)

            try:
                client = self._get_client()
                if client is None:
                    logger.warning("ElevenLabs 클라이언트 사용 불가")
                    return None

                audio_data = client.text_to_speech.convert(
                    text=section.text,
                    voice_id=voice_id,
                    model_id=self._config.model,
                )

                if hasattr(audio_data, "__iter__") and not isinstance(
                    audio_data, bytes
                ):
                    chunk = b"".join(audio_data)
                else:
                    chunk = audio_data

                if chunk:
                    audio_chunks.append(chunk)
                    full_text_parts.append(f"[{voice}] {section.text}")

            except Exception:
                logger.warning("섹션 %d TTS 실패, 건너뜀", section.index, exc_info=True)

        if not audio_chunks:
            logger.warning("합성된 오디오 청크 없음")
            return None

        # 단순 연결 (실제 프로덕션에서는 pydub 등으로 적절히 병합)
        combined = b"".join(audio_chunks)

        output_dir = self._ensure_output_dir()
        filename = self._generate_filename(prefix="elevenlabs-multi")
        file_path = output_dir / filename
        file_path.write_bytes(combined)

        return GeneratedAsset(
            asset_type="audio",
            file_path=str(file_path),
            prompt_used="\n".join(full_text_parts),
            metadata=(
                ("adapter", "elevenlabs"),
                ("model", self._config.model),
                ("language", language),
                ("sections_count", len(audio_chunks)),
                ("total_sections", len(sections)),
            ),
        )
