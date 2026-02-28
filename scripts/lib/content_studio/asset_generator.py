"""AssetGenerator — MCP 어댑터 기반 이미지/차트/오디오 에셋 생성 서비스.

PR-045: 어댑터를 조합하여 콘텐츠 에셋 생성.

에셋 캐싱 (content_hash 기반), 병렬 생성, Graceful fallback.
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from scripts.lib.content_studio.models import GeneratedAsset

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Adapter Protocols (base.py에서도 정의, 여기서는 최소 Protocol)
# ---------------------------------------------------------------------------


@runtime_checkable
class ImageGenerator(Protocol):
    async def is_available(self) -> bool:
        ...

    async def generate_image(
        self, prompt: str, width: int, height: int, style: str
    ) -> GeneratedAsset | None:
        ...


@runtime_checkable
class ChartGenerator(Protocol):
    async def is_available(self) -> bool:
        ...

    async def generate_chart(
        self, chart_type: str, data: dict, options: dict
    ) -> GeneratedAsset | None:
        ...


@runtime_checkable
class AudioGenerator(Protocol):
    async def is_available(self) -> bool:
        ...

    async def text_to_speech(
        self, text: str, voice: str, language: str
    ) -> GeneratedAsset | None:
        ...


# ---------------------------------------------------------------------------
# AssetGenerator
# ---------------------------------------------------------------------------


class AssetGenerator:
    """MCP 어댑터를 조합하여 콘텐츠 에셋 생성.

    모든 어댑터는 Optional. 미가용 시 스킵 + warning.
    """

    def __init__(
        self,
        image_generator: ImageGenerator | None = None,
        chart_generator: ChartGenerator | None = None,
        audio_generator: AudioGenerator | None = None,
        cache_dir: str = "output/assets",
    ) -> None:
        self._image_gen = image_generator
        self._chart_gen = chart_generator
        self._audio_gen = audio_generator
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _cache_key(
        prompt: str, width: int | None, height: int | None, asset_type: str
    ) -> str:
        """캐싱용 SHA256 해시."""
        raw = f"{prompt}|{width}|{height}|{asset_type}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _find_cached(self, cache_key: str) -> GeneratedAsset | None:
        """캐시에서 기존 에셋 검색."""
        for f in self._cache_dir.iterdir():
            if cache_key[:16] in f.name and f.is_file():
                ext = f.suffix.lstrip(".")
                asset_type_map = {"png": "image", "svg": "chart", "mp3": "audio"}
                atype = asset_type_map.get(ext, "image")
                return GeneratedAsset(
                    asset_type=atype,
                    file_path=str(f),
                    prompt_used=f"(cached: {cache_key[:16]})",
                )
        return None

    async def generate_assets(
        self,
        plan: Any,
        content: Any = None,
    ) -> list[GeneratedAsset]:
        """계획에서 에셋 요청을 추출하고 적절한 어댑터를 호출.

        Args:
            plan: *Plan dataclass (slides, cards 등에서 asset_type/prompt 추출).
            content: *Content dataclass (추가 컨텍스트용, 선택).

        Returns:
            생성된 에셋 목록. 실패한 에셋은 제외 (경고 로그).
        """
        asset_requests = self._extract_asset_requests(plan)
        results: list[GeneratedAsset] = []

        for req in asset_requests:
            asset = await self._generate_single(req)
            if asset is not None:
                results.append(asset)

        return results

    def _extract_asset_requests(self, plan: Any) -> list[dict[str, Any]]:
        """Plan에서 에셋 요청 목록 추출."""
        requests: list[dict[str, Any]] = []

        # LecturePlan — slides에서 asset_type/asset_prompt 추출
        if hasattr(plan, "slides"):
            for slide in plan.slides:
                if hasattr(slide, "asset_type") and slide.asset_type:
                    requests.append(
                        {
                            "asset_type": slide.asset_type,
                            "prompt": slide.asset_prompt or slide.title,
                            "width": 1920 if slide.asset_type == "image" else None,
                            "height": 1080 if slide.asset_type == "image" else None,
                            "style": "professional",
                            "metadata": {"slide_index": slide.index},
                        }
                    )

        # CardNewsPlan — cards에서 image_prompt 추출
        if hasattr(plan, "cards"):
            image_size = getattr(plan, "image_size", (1080, 1080))
            for card in plan.cards:
                if hasattr(card, "image_prompt") and card.image_prompt:
                    requests.append(
                        {
                            "asset_type": "image",
                            "prompt": card.image_prompt,
                            "width": image_size[0],
                            "height": image_size[1],
                            "style": "professional",
                            "metadata": {"card_index": card.index},
                        }
                    )

        # AudioPlan — 전체 섹션 텍스트 → TTS
        if hasattr(plan, "sections") and hasattr(plan, "style"):
            for section in plan.sections:
                if hasattr(section, "text") and section.text:
                    requests.append(
                        {
                            "asset_type": "audio",
                            "prompt": section.text,
                            "voice": section.speaker,
                            "language": "ko",
                            "metadata": {"section_index": section.index},
                        }
                    )

        # VisualizationPlan — viz_type 기반
        if hasattr(plan, "viz_type"):
            requests.append(
                {
                    "asset_type": "chart",
                    "chart_type": plan.viz_type,
                    "prompt": plan.data_description or plan.title,
                    "metadata": {},
                }
            )

        return requests

    async def _generate_single(self, req: dict[str, Any]) -> GeneratedAsset | None:
        """단일 에셋 생성. 캐시 확인 → 어댑터 호출 → fallback."""
        asset_type = req["asset_type"]
        prompt = req.get("prompt", "")
        width = req.get("width")
        height = req.get("height")

        # 캐시 확인
        cache_key = self._cache_key(prompt, width, height, asset_type)
        cached = self._find_cached(cache_key)
        if cached is not None:
            logger.info(f"캐시 히트: {asset_type} ({cache_key[:16]})")
            return cached

        # 어댑터 호출
        try:
            if asset_type == "image":
                return await self._generate_image(req)
            elif asset_type == "chart":
                return await self._generate_chart(req)
            elif asset_type == "audio":
                return await self._generate_audio(req)
            else:
                logger.warning(f"알 수 없는 asset_type: {asset_type}")
                return None
        except Exception as e:
            logger.warning(f"에셋 생성 실패 ({asset_type}): {e}")
            return None

    async def _generate_image(self, req: dict[str, Any]) -> GeneratedAsset | None:
        if self._image_gen is None:
            logger.warning("ImageGenerator 미설정. 이미지 에셋 스킵.")
            return None
        if not await self._image_gen.is_available():
            logger.warning("ImageGenerator 미가용. 이미지 에셋 스킵.")
            return None
        result = await self._image_gen.generate_image(
            prompt=req.get("prompt", ""),
            width=req.get("width", 1024),
            height=req.get("height", 1024),
            style=req.get("style", "professional"),
        )
        if result is not None:
            # 메타데이터 병합
            meta = dict(result.metadata) if result.metadata else {}
            meta.update(req.get("metadata", {}))
            return GeneratedAsset(
                asset_type=result.asset_type,
                file_path=result.file_path,
                prompt_used=result.prompt_used,
                width=result.width,
                height=result.height,
                metadata=tuple(sorted(meta.items())),
            )
        return None

    async def _generate_chart(self, req: dict[str, Any]) -> GeneratedAsset | None:
        if self._chart_gen is None:
            logger.warning("ChartGenerator 미설정. 차트 에셋 스킵.")
            return None
        if not await self._chart_gen.is_available():
            logger.warning("ChartGenerator 미가용. 차트 에셋 스킵.")
            return None
        result = await self._chart_gen.generate_chart(
            chart_type=req.get("chart_type", "timeline"),
            data=req.get("data", {}),
            options=req.get("options", {}),
        )
        if result is not None:
            meta = dict(result.metadata) if result.metadata else {}
            meta.update(req.get("metadata", {}))
            return GeneratedAsset(
                asset_type=result.asset_type,
                file_path=result.file_path,
                prompt_used=result.prompt_used,
                metadata=tuple(sorted(meta.items())),
            )
        return None

    async def _generate_audio(self, req: dict[str, Any]) -> GeneratedAsset | None:
        if self._audio_gen is None:
            logger.warning("AudioGenerator 미설정. 오디오 에셋 스킵.")
            return None
        if not await self._audio_gen.is_available():
            logger.warning("AudioGenerator 미가용. 오디오 에셋 스킵.")
            return None
        result = await self._audio_gen.text_to_speech(
            text=req.get("prompt", ""),
            voice=req.get("voice", "narrator"),
            language=req.get("language", "ko"),
        )
        if result is not None:
            meta = dict(result.metadata) if result.metadata else {}
            meta.update(req.get("metadata", {}))
            return GeneratedAsset(
                asset_type=result.asset_type,
                file_path=result.file_path,
                prompt_used=result.prompt_used,
                metadata=tuple(sorted(meta.items())),
            )
        return None
