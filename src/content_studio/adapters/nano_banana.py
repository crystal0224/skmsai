"""NanoBanana 2 이미지 생성 어댑터.

PR-041: Google Gemini 기반 이미지 생성.

NanoBanana 2 (Nano Banana 2)는 Google의 Gemini 모델을 활용한
이미지 생성 서비스이다. ImageGenerator 프로토콜을 구현한다.

해상도 매핑:
- "512": 512x512
- "1K": 1024x1024
- "2K": 2048x2048
- "4K": 4096x4096

종횡비 매핑:
- "16:9": 1920x1080
- "1:1": 1080x1080
- "9:16": 1080x1920
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.content_studio.models import GeneratedAsset

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

RESOLUTION_MAP: dict[str, tuple[int, int]] = {
    "512": (512, 512),
    "1K": (1024, 1024),
    "2K": (2048, 2048),
    "4K": (4096, 4096),
}

ASPECT_RATIO_MAP: dict[str, tuple[int, int]] = {
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
    "9:16": (1080, 1920),
}

DEFAULT_OUTPUT_DIR = "output/assets"


# ---------------------------------------------------------------------------
# NanoBananaConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NanoBananaConfig:
    """NanoBanana 어댑터 설정 (불변).

    Attributes:
        api_key: Google Gemini API 키. None이면 환경변수에서 읽는다.
        model: 사용할 모델명.
        output_dir: 에셋 출력 디렉토리.
        default_style: 기본 이미지 스타일.
    """

    api_key: str | None = None
    model: str = "gemini-2.0-flash-exp"
    output_dir: str = DEFAULT_OUTPUT_DIR
    default_style: str = "professional"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NanoBananaConfig:
        return cls(
            api_key=data.get("api_key"),
            model=data.get("model", "gemini-2.0-flash-exp"),
            output_dir=data.get("output_dir", DEFAULT_OUTPUT_DIR),
            default_style=data.get("default_style", "professional"),
        )


# ---------------------------------------------------------------------------
# NanoBananaAdapter
# ---------------------------------------------------------------------------


class NanoBananaAdapter:
    """NanoBanana 2 이미지 생성 어댑터.

    Google Gemini API를 사용하여 이미지를 생성한다.
    ImageGenerator 프로토콜을 구현한다.

    API 오류 시 None을 반환하고 경고 로그를 남긴다 (graceful fallback).
    """

    def __init__(self, config: NanoBananaConfig | None = None) -> None:
        self._config = config or NanoBananaConfig()
        self._api_key = self._config.api_key or os.environ.get("GOOGLE_API_KEY", "")
        self._client: Any = None

    def _ensure_output_dir(self) -> Path:
        """출력 디렉토리를 확인/생성하고 Path를 반환한다."""
        output_path = Path(self._config.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        return output_path

    def _generate_filename(self) -> str:
        """고유 파일명을 생성한다: nano-banana-{timestamp}-{uuid[:8]}.png"""
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
        uid = uuid.uuid4().hex[:8]
        return f"nano-banana-{ts}-{uid}.png"

    def _resolve_dimensions(self, width: int, height: int) -> tuple[int, int]:
        """요청된 크기를 검증하고 반환한다.

        해상도 매핑이나 종횡비 매핑에 해당하지 않으면
        원본 width, height를 그대로 사용한다.
        """
        if width <= 0 or height <= 0:
            logger.warning("유효하지 않은 크기: %dx%d, 기본값 1024x1024 사용", width, height)
            return (1024, 1024)
        return (width, height)

    def _get_client(self) -> Any:
        """Gemini 클라이언트를 lazy 초기화한다."""
        if self._client is not None:
            return self._client

        try:
            import google.generativeai as genai

            genai.configure(api_key=self._api_key)
            self._client = genai.GenerativeModel(self._config.model)
            return self._client
        except ImportError:
            logger.warning("google-generativeai 패키지 미설치")
            return None
        except Exception:
            logger.warning("Gemini 클라이언트 초기화 실패", exc_info=True)
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
            "adapter": "nano_banana",
            "model": self._config.model,
            "has_api_key": bool(self._api_key),
            "output_dir": self._config.output_dir,
        }

    async def generate_image(
        self,
        prompt: str,
        width: int,
        height: int,
        style: str,
    ) -> GeneratedAsset | None:
        """프롬프트로 이미지를 생성한다.

        Args:
            prompt: 이미지 생성 프롬프트.
            width: 이미지 너비 (px).
            height: 이미지 높이 (px).
            style: 시각 스타일.

        Returns:
            GeneratedAsset 또는 None (실패 시).
        """
        resolved_w, resolved_h = self._resolve_dimensions(width, height)

        try:
            client = self._get_client()
            if client is None:
                logger.warning("NanoBanana 클라이언트 사용 불가")
                return None

            # 스타일 힌트를 포함한 프롬프트 구성
            styled_prompt = (
                f"Generate an image in {style} style: {prompt}. "
                f"Resolution: {resolved_w}x{resolved_h}."
            )

            response = client.generate_content(styled_prompt)

            # 출력 디렉토리 확인 및 파일 저장
            output_dir = self._ensure_output_dir()
            filename = self._generate_filename()
            file_path = output_dir / filename

            # 응답에서 이미지 데이터 추출 및 저장
            if hasattr(response, "images") and response.images:
                image_data = response.images[0]
                file_path.write_bytes(image_data)
            elif hasattr(response, "parts"):
                # Gemini 2.0 응답 형식
                for part in response.parts:
                    if hasattr(part, "inline_data") and part.inline_data:
                        file_path.write_bytes(part.inline_data.data)
                        break
                else:
                    logger.warning("응답에 이미지 데이터 없음")
                    return None
            else:
                logger.warning("지원하지 않는 응답 형식")
                return None

            return GeneratedAsset(
                asset_type="image",
                file_path=str(file_path),
                prompt_used=prompt,
                width=resolved_w,
                height=resolved_h,
                metadata=(
                    ("adapter", "nano_banana"),
                    ("model", self._config.model),
                    ("style", style),
                ),
            )

        except Exception:
            logger.warning("NanoBanana 이미지 생성 실패", exc_info=True)
            return None

    async def edit_image(
        self,
        image_path: str,
        edit_prompt: str,
    ) -> GeneratedAsset | None:
        """기존 이미지를 편집한다.

        Args:
            image_path: 원본 이미지 경로.
            edit_prompt: 편집 프롬프트.

        Returns:
            편집된 GeneratedAsset 또는 None (실패 시).
        """
        source = Path(image_path)
        if not source.exists():
            logger.warning("원본 이미지 파일 없음: %s", image_path)
            return None

        try:
            client = self._get_client()
            if client is None:
                logger.warning("NanoBanana 클라이언트 사용 불가")
                return None

            # 원본 이미지 읽기
            image_bytes = source.read_bytes()

            response = client.generate_content(
                [edit_prompt, {"mime_type": "image/png", "data": image_bytes}]
            )

            output_dir = self._ensure_output_dir()
            filename = self._generate_filename()
            file_path = output_dir / filename

            if hasattr(response, "images") and response.images:
                file_path.write_bytes(response.images[0])
            elif hasattr(response, "parts"):
                for part in response.parts:
                    if hasattr(part, "inline_data") and part.inline_data:
                        file_path.write_bytes(part.inline_data.data)
                        break
                else:
                    logger.warning("편집 응답에 이미지 데이터 없음")
                    return None
            else:
                logger.warning("지원하지 않는 편집 응답 형식")
                return None

            return GeneratedAsset(
                asset_type="image",
                file_path=str(file_path),
                prompt_used=edit_prompt,
                metadata=(
                    ("adapter", "nano_banana"),
                    ("model", self._config.model),
                    ("source_image", image_path),
                ),
            )

        except Exception:
            logger.warning("NanoBanana 이미지 편집 실패", exc_info=True)
            return None
