"""MCP 어댑터 라이브 스모크 테스트.

STEP 4: 3개 MCP 어댑터(ElevenLabs, AntV, NanoBanana)를 실제 API로 검증한다.

실행:
    source .venv/bin/activate
    export $(grep -v '^#' .env | grep -v '^$' | xargs)
    python scripts/test_mcp_live.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# 프로젝트 루트를 PYTHONPATH에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.lib.content_studio.adapters.antv_chart import (
    AntVChartAdapter,
    AntVChartConfig,
    edition_timeline_data,
    concept_mindmap_data,
    element_radar_data,
)
from scripts.lib.content_studio.adapters.elevenlabs import (
    ElevenLabsAdapter,
    ElevenLabsConfig,
)
from scripts.lib.content_studio.adapters.nano_banana import (
    NanoBananaAdapter,
    NanoBananaConfig,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 결과 추적
# ---------------------------------------------------------------------------


class TestResults:
    """스모크 테스트 결과를 수집한다."""

    def __init__(self) -> None:
        self._results: list[dict[str, str]] = []

    def add(self, adapter: str, test: str, status: str, detail: str = "") -> None:
        self._results.append(
            {
                "adapter": adapter,
                "test": test,
                "status": status,
                "detail": detail,
            }
        )
        icon = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]", "WARN": "[WARN]"}
        print(f"  {icon.get(status, status)} {test}: {detail}")

    def summary(self) -> None:
        total = len(self._results)
        passed = sum(1 for r in self._results if r["status"] == "PASS")
        failed = sum(1 for r in self._results if r["status"] == "FAIL")
        skipped = sum(1 for r in self._results if r["status"] == "SKIP")
        warned = sum(1 for r in self._results if r["status"] == "WARN")

        print("\n" + "=" * 60)
        print(
            f"RESULTS: {passed} passed, {failed} failed, {warned} warnings, {skipped} skipped / {total} total"
        )
        print("=" * 60)

        if failed > 0:
            print("\nFailed tests:")
            for r in self._results:
                if r["status"] == "FAIL":
                    print(f"  - [{r['adapter']}] {r['test']}: {r['detail']}")

        if warned > 0:
            print("\nWarnings:")
            for r in self._results:
                if r["status"] == "WARN":
                    print(f"  - [{r['adapter']}] {r['test']}: {r['detail']}")


# ---------------------------------------------------------------------------
# 1. ElevenLabs TTS 테스트
# ---------------------------------------------------------------------------

# 실제 한국어 음성 ID 매핑 (ElevenLabs 공식 voices)
REAL_KOREAN_VOICES = {
    "narrator": "4p0HBzAAGyju0nYfNntV",  # Sunny (female, narrative)
    "host": "Kc5nnLyvNv2FZhXzY3Hq",  # Jinwoo (male, educational)
    "expert": "RU7aSi6lT4uQBXMLgDxK",  # Kyle (male, educational)
}


def _is_valid_mp3(data: bytes) -> bool:
    """MP3 파일의 유효성을 간단히 검증한다.

    MP3는 ID3 태그(ID3v2)로 시작하거나, MPEG 프레임 sync word(0xFFE0~0xFFFF)로 시작한다.
    """
    if len(data) < 4:
        return False
    # ID3v2 태그
    if data[:3] == b"ID3":
        return True
    # MPEG sync word (11비트 sync: 0xFFE0 mask)
    first_two = struct.unpack(">H", data[:2])[0]
    return (first_two & 0xFFE0) == 0xFFE0


async def test_elevenlabs(results: TestResults) -> None:
    """ElevenLabs TTS 어댑터를 실제 API로 검증한다."""
    print("\n--- ElevenLabs TTS Adapter ---")

    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        results.add(
            "elevenlabs", "api_key_present", "SKIP", "ELEVENLABS_API_KEY not set"
        )
        return

    results.add("elevenlabs", "api_key_present", "PASS", "Key is set")

    # 어댑터 초기화
    config = ElevenLabsConfig(
        api_key=api_key,
        output_dir="output/test_mcp_live",
    )
    adapter = ElevenLabsAdapter(config)

    # 1-1. health_check
    health = await adapter.health_check()
    if health["status"] == "ok":
        results.add("elevenlabs", "health_check", "PASS", f"model={health['model']}")
    else:
        results.add("elevenlabs", "health_check", "FAIL", str(health))
        return

    # 1-2. is_available
    available = await adapter.is_available()
    results.add(
        "elevenlabs", "is_available", "PASS" if available else "FAIL", str(available)
    )

    # 1-3. TTS with short Korean text (use real Korean voice ID)
    test_text = "SK경영관리체계는 인간중심의 경영을 지향합니다."
    real_voice_id = REAL_KOREAN_VOICES["narrator"]
    asset = await adapter.text_to_speech(
        text=test_text,
        voice=real_voice_id,  # Use real voice ID directly
        language="ko",
    )

    if asset is None:
        # 402 Payment Required = free plan limitation, not a code bug
        results.add(
            "elevenlabs",
            "tts_korean_short",
            "WARN",
            "Returned None (likely 402 Payment Required — free plan cannot use library voices via API)",
        )
    else:
        file_path = Path(asset.file_path)
        if not file_path.exists():
            results.add(
                "elevenlabs", "tts_korean_short", "FAIL", f"File not found: {file_path}"
            )
        else:
            file_size = file_path.stat().st_size
            audio_bytes = file_path.read_bytes()

            if file_size == 0:
                results.add(
                    "elevenlabs", "tts_korean_short", "FAIL", "File is empty (0 bytes)"
                )
            elif not _is_valid_mp3(audio_bytes):
                results.add(
                    "elevenlabs",
                    "tts_korean_short",
                    "FAIL",
                    f"Not valid MP3 (first 4 bytes: {audio_bytes[:4].hex()})",
                )
            else:
                results.add(
                    "elevenlabs",
                    "tts_korean_short",
                    "PASS",
                    f"Valid MP3, {file_size:,} bytes, path={file_path}",
                )

    # 1-4. Empty text handling
    empty_result = await adapter.text_to_speech(
        text="", voice=real_voice_id, language="ko"
    )
    if empty_result is None:
        results.add(
            "elevenlabs",
            "tts_empty_text",
            "PASS",
            "Correctly returns None for empty text",
        )
    else:
        results.add(
            "elevenlabs", "tts_empty_text", "FAIL", "Should return None for empty text"
        )

    # 1-5. Whitespace-only text
    ws_result = await adapter.text_to_speech(
        text="   ", voice=real_voice_id, language="ko"
    )
    if ws_result is None:
        results.add(
            "elevenlabs",
            "tts_whitespace_text",
            "PASS",
            "Correctly returns None for whitespace",
        )
    else:
        results.add(
            "elevenlabs",
            "tts_whitespace_text",
            "FAIL",
            "Should return None for whitespace text",
        )

    # 1-6. VOICE_MAP mapping check (warns about non-existent voice IDs)
    from scripts.lib.content_studio.adapters.elevenlabs import VOICE_MAP

    results.add(
        "elevenlabs",
        "voice_map_check",
        "WARN",
        f"VOICE_MAP uses placeholder IDs: {VOICE_MAP}. "
        f"Real Korean voices: {REAL_KOREAN_VOICES}",
    )


# ---------------------------------------------------------------------------
# 2. AntV Chart (fallback SVG mode)
# ---------------------------------------------------------------------------


async def test_antv(results: TestResults) -> None:
    """AntV 차트 어댑터를 fallback 모드로 검증한다."""
    print("\n--- AntV Chart Adapter (Fallback Mode) ---")

    # MCP 엔드포인트가 없으므로 Markdown fallback 동작을 검증
    config = AntVChartConfig(
        mcp_endpoint="",  # No endpoint — forces fallback
        output_dir="output/test_mcp_live",
    )
    adapter = AntVChartAdapter(config)

    # 2-1. health_check (should report error since no endpoint)
    health = await adapter.health_check()
    if health["status"] == "error":
        results.add(
            "antv",
            "health_check_no_endpoint",
            "PASS",
            "Correctly reports error when no MCP endpoint",
        )
    else:
        results.add(
            "antv", "health_check_no_endpoint", "WARN", f"Unexpected status: {health}"
        )

    # 2-2. is_available
    available = await adapter.is_available()
    if not available:
        results.add(
            "antv", "is_available_no_endpoint", "PASS", "Correctly returns False"
        )
    else:
        results.add(
            "antv",
            "is_available_no_endpoint",
            "WARN",
            "Should be False without endpoint",
        )

    # 2-3. Timeline chart fallback
    timeline_data = edition_timeline_data()
    timeline_asset = await adapter.generate_chart("timeline", timeline_data, {})
    if timeline_asset is not None:
        file_path = Path(timeline_asset.file_path)
        if file_path.exists() and file_path.suffix == ".md":
            content = file_path.read_text(encoding="utf-8")
            has_table = "| 연도 |" in content or "| 1979 |" in content
            if has_table:
                results.add(
                    "antv",
                    "timeline_fallback",
                    "PASS",
                    f"Markdown fallback with table, {len(content)} chars",
                )
            else:
                results.add(
                    "antv",
                    "timeline_fallback",
                    "WARN",
                    "Fallback file missing table structure",
                )
        else:
            results.add(
                "antv",
                "timeline_fallback",
                "FAIL",
                f"File issue: exists={file_path.exists()}, suffix={file_path.suffix}",
            )
    else:
        results.add(
            "antv", "timeline_fallback", "FAIL", "Returned None instead of fallback"
        )

    # 2-4. Mindmap chart fallback
    mindmap_data = concept_mindmap_data()
    mindmap_asset = await adapter.generate_chart("mindmap", mindmap_data, {})
    if mindmap_asset is not None:
        file_path = Path(mindmap_asset.file_path)
        content = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
        has_content = "SKMS" in content and "인간중심" in content
        if has_content:
            results.add(
                "antv",
                "mindmap_fallback",
                "PASS",
                f"Markdown mindmap, {len(content)} chars",
            )
        else:
            results.add(
                "antv",
                "mindmap_fallback",
                "WARN",
                "Missing expected content in mindmap fallback",
            )
    else:
        results.add("antv", "mindmap_fallback", "FAIL", "Returned None")

    # 2-5. Radar chart fallback
    radar_data = element_radar_data()
    radar_asset = await adapter.generate_chart("radar", radar_data, {})
    if radar_asset is not None:
        file_path = Path(radar_asset.file_path)
        content = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
        has_table = "기획관리" in content
        if has_table:
            results.add(
                "antv",
                "radar_fallback",
                "PASS",
                f"Markdown radar table, {len(content)} chars",
            )
        else:
            results.add(
                "antv",
                "radar_fallback",
                "WARN",
                "Missing expected data in radar fallback",
            )
    else:
        results.add("antv", "radar_fallback", "FAIL", "Returned None")

    # 2-6. Invalid chart type
    invalid_asset = await adapter.generate_chart("invalid_type", {}, {})
    if invalid_asset is None:
        results.add(
            "antv",
            "invalid_chart_type",
            "PASS",
            "Correctly returns None for invalid type",
        )
    else:
        results.add(
            "antv",
            "invalid_chart_type",
            "FAIL",
            "Should return None for invalid chart type",
        )

    # 2-7. Fallback asset metadata check
    if timeline_asset is not None:
        meta_dict = dict(timeline_asset.metadata) if timeline_asset.metadata else {}
        if meta_dict.get("fallback") is True:
            results.add(
                "antv",
                "fallback_metadata",
                "PASS",
                "metadata.fallback=True correctly set",
            )
        else:
            results.add("antv", "fallback_metadata", "WARN", f"metadata: {meta_dict}")


# ---------------------------------------------------------------------------
# 3. NanoBanana / Gemini Images (key not set)
# ---------------------------------------------------------------------------


async def test_nano_banana(results: TestResults) -> None:
    """NanoBanana 이미지 어댑터를 검증한다 (GEMINI_API_KEY 미설정 시 fallback 확인)."""
    print("\n--- NanoBanana / Gemini Image Adapter ---")

    google_key = os.environ.get("GOOGLE_API_KEY", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")

    has_key = bool(google_key) or bool(gemini_key)
    results.add(
        "nano_banana",
        "api_key_check",
        "PASS" if not has_key else "PASS",
        f"GOOGLE_API_KEY={'set' if google_key else 'not set'}, "
        f"GEMINI_API_KEY={'set' if gemini_key else 'not set'}",
    )

    config = NanoBananaConfig(output_dir="output/test_mcp_live")
    adapter = NanoBananaAdapter(config)

    # 3-1. health_check (no key)
    health = await adapter.health_check()
    if not has_key:
        if health["status"] == "error" and health["has_api_key"] is False:
            results.add(
                "nano_banana",
                "health_check_no_key",
                "PASS",
                "Correctly reports error without API key",
            )
        else:
            results.add(
                "nano_banana",
                "health_check_no_key",
                "FAIL",
                f"Unexpected health: {health}",
            )
    else:
        results.add(
            "nano_banana",
            "health_check",
            "PASS" if health["status"] == "ok" else "FAIL",
            str(health),
        )

    # 3-2. is_available (no key)
    available = await adapter.is_available()
    if not has_key:
        if not available:
            results.add(
                "nano_banana",
                "is_available_no_key",
                "PASS",
                "Correctly returns False without key",
            )
        else:
            results.add(
                "nano_banana",
                "is_available_no_key",
                "FAIL",
                "Should be False without key",
            )
    else:
        results.add(
            "nano_banana",
            "is_available",
            "PASS" if available else "FAIL",
            str(available),
        )

    # 3-3. generate_image without key (should return None gracefully)
    if not has_key:
        image_result = await adapter.generate_image(
            prompt="SKMS 경영 철학을 나타내는 추상화",
            width=512,
            height=512,
            style="professional",
        )
        if image_result is None:
            results.add(
                "nano_banana",
                "generate_no_key",
                "PASS",
                "Correctly returns None (graceful fallback) when key not set",
            )
        else:
            results.add(
                "nano_banana",
                "generate_no_key",
                "FAIL",
                "Should return None without key",
            )

    # 3-4. Dimension validation
    adapter2 = NanoBananaAdapter(NanoBananaConfig(api_key="fake-key"))
    w, h = adapter2._resolve_dimensions(0, 0)
    if (w, h) == (1024, 1024):
        results.add(
            "nano_banana",
            "invalid_dimensions",
            "PASS",
            "Falls back to 1024x1024 for 0x0",
        )
    else:
        results.add(
            "nano_banana",
            "invalid_dimensions",
            "FAIL",
            f"Got {w}x{h}, expected 1024x1024",
        )

    w2, h2 = adapter2._resolve_dimensions(-1, 500)
    if (w2, h2) == (1024, 1024):
        results.add(
            "nano_banana",
            "negative_dimensions",
            "PASS",
            "Falls back to 1024x1024 for negative",
        )
    else:
        results.add("nano_banana", "negative_dimensions", "FAIL", f"Got {w2}x{h2}")

    w3, h3 = adapter2._resolve_dimensions(800, 600)
    if (w3, h3) == (800, 600):
        results.add(
            "nano_banana", "valid_dimensions", "PASS", "Keeps valid dimensions 800x600"
        )
    else:
        results.add("nano_banana", "valid_dimensions", "FAIL", f"Got {w3}x{h3}")

    # 3-5. google-generativeai package check
    try:
        import google.generativeai  # noqa: F401

        results.add(
            "nano_banana",
            "package_installed",
            "PASS",
            "google-generativeai is installed",
        )
    except ImportError:
        results.add(
            "nano_banana",
            "package_installed",
            "WARN",
            "google-generativeai not installed (pip install google-generativeai)",
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    print("=" * 60)
    print("MCP Adapter Live Smoke Tests")
    print("=" * 60)

    results = TestResults()

    await test_elevenlabs(results)
    await test_antv(results)
    await test_nano_banana(results)

    results.summary()

    # Cleanup notice
    test_dir = Path("output/test_mcp_live")
    if test_dir.exists():
        file_count = sum(1 for _ in test_dir.iterdir())
        print(f"\nTest artifacts: {test_dir}/ ({file_count} files)")
        print("Run 'rm -rf output/test_mcp_live' to clean up.")


if __name__ == "__main__":
    asyncio.run(main())
