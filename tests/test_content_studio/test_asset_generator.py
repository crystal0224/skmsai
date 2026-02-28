"""AssetGenerator 테스트.

PR-045: 에셋 생성 + 캐싱 + fallback 테스트.
"""
from __future__ import annotations

import pytest

from scripts.lib.content_studio.asset_generator import AssetGenerator
from scripts.lib.content_studio.models import (
    GeneratedAsset,
    LecturePlan,
    SlidePlan,
    CardNewsPlan,
    CardPlan,
    AudioPlan,
    ScriptSection,
    VisualizationPlan,
)


# ---------------------------------------------------------------------------
# Mock Adapters
# ---------------------------------------------------------------------------


class MockImageGenerator:
    def __init__(self, available: bool = True, fail: bool = False):
        self._available = available
        self._fail = fail
        self.call_count = 0

    async def is_available(self) -> bool:
        return self._available

    async def generate_image(
        self, prompt: str, width: int, height: int, style: str
    ) -> GeneratedAsset | None:
        self.call_count += 1
        if self._fail:
            return None
        return GeneratedAsset(
            asset_type="image",
            file_path=f"/tmp/mock-{self.call_count}.png",
            prompt_used=prompt,
            width=width,
            height=height,
        )


class MockChartGenerator:
    def __init__(self, available: bool = True, fail: bool = False):
        self._available = available
        self._fail = fail
        self.call_count = 0

    async def is_available(self) -> bool:
        return self._available

    async def generate_chart(
        self, chart_type: str, data: dict, options: dict
    ) -> GeneratedAsset | None:
        self.call_count += 1
        if self._fail:
            return None
        return GeneratedAsset(
            asset_type="chart",
            file_path=f"/tmp/mock-chart-{self.call_count}.svg",
            prompt_used=chart_type,
        )


class MockAudioGenerator:
    def __init__(self, available: bool = True, fail: bool = False):
        self._available = available
        self._fail = fail
        self.call_count = 0

    async def is_available(self) -> bool:
        return self._available

    async def text_to_speech(
        self, text: str, voice: str, language: str
    ) -> GeneratedAsset | None:
        self.call_count += 1
        if self._fail:
            return None
        return GeneratedAsset(
            asset_type="audio",
            file_path=f"/tmp/mock-audio-{self.call_count}.mp3",
            prompt_used=text[:50],
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_lecture_with_assets() -> LecturePlan:
    return LecturePlan(
        title="SUPEX 강의",
        subtitle="테스트",
        duration_min=30,
        slides=(
            SlidePlan(index=1, title="표지", layout="title_only"),
            SlidePlan(
                index=2,
                title="SUPEX란",
                asset_type="image",
                asset_prompt="기업 이미지 SUPEX",
            ),
            SlidePlan(
                index=3,
                title="타임라인",
                asset_type="chart",
                asset_prompt="SUPEX 변천 타임라인",
            ),
            SlidePlan(index=4, title="요약"),
        ),
    )


def _make_card_news_with_images() -> CardNewsPlan:
    return CardNewsPlan(
        title="VWBE 카드",
        total_cards=2,
        cards=(
            CardPlan(index=1, headline="VWBE", body="설명", image_prompt="VWBE 일러스트"),
            CardPlan(index=2, headline="실천", body="방법", image_prompt="실천 이미지"),
        ),
    )


def _make_audio_plan() -> AudioPlan:
    return AudioPlan(
        title="SKMS 요약",
        style="dialogue",
        total_duration_min=5,
        sections=(
            ScriptSection(index=1, speaker="host", text="안녕하세요. 오늘은 SKMS에 대해 알아보겠습니다."),
            ScriptSection(index=2, speaker="expert", text="SKMS는 SK그룹의 경영체계입니다."),
        ),
    )


def _make_viz_plan() -> VisualizationPlan:
    return VisualizationPlan(
        title="마인드맵",
        viz_type="mindmap",
        data_description="SKMS 3대 철학",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAssetGenerator:
    @pytest.mark.asyncio
    async def test_init_creates_cache_dir(self, tmp_path):
        cache_dir = str(tmp_path / "cache")
        gen = AssetGenerator(cache_dir=cache_dir)
        assert (tmp_path / "cache").is_dir()

    @pytest.mark.asyncio
    async def test_no_adapters_returns_empty(self, tmp_path):
        gen = AssetGenerator(cache_dir=str(tmp_path / "cache"))
        plan = _make_lecture_with_assets()
        results = await gen.generate_assets(plan)
        assert results == []

    @pytest.mark.asyncio
    async def test_lecture_image_generation(self, tmp_path):
        mock_img = MockImageGenerator()
        gen = AssetGenerator(
            image_generator=mock_img, cache_dir=str(tmp_path / "cache")
        )
        plan = _make_lecture_with_assets()
        results = await gen.generate_assets(plan)

        # 슬라이드 2가 image 에셋
        image_results = [r for r in results if r.asset_type == "image"]
        assert len(image_results) == 1
        assert mock_img.call_count == 1

    @pytest.mark.asyncio
    async def test_lecture_chart_generation(self, tmp_path):
        mock_chart = MockChartGenerator()
        gen = AssetGenerator(
            chart_generator=mock_chart, cache_dir=str(tmp_path / "cache")
        )
        plan = _make_lecture_with_assets()
        results = await gen.generate_assets(plan)

        chart_results = [r for r in results if r.asset_type == "chart"]
        assert len(chart_results) == 1
        assert mock_chart.call_count == 1

    @pytest.mark.asyncio
    async def test_lecture_both_adapters(self, tmp_path):
        mock_img = MockImageGenerator()
        mock_chart = MockChartGenerator()
        gen = AssetGenerator(
            image_generator=mock_img,
            chart_generator=mock_chart,
            cache_dir=str(tmp_path / "cache"),
        )
        plan = _make_lecture_with_assets()
        results = await gen.generate_assets(plan)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_card_news_images(self, tmp_path):
        mock_img = MockImageGenerator()
        gen = AssetGenerator(
            image_generator=mock_img, cache_dir=str(tmp_path / "cache")
        )
        plan = _make_card_news_with_images()
        results = await gen.generate_assets(plan)
        assert len(results) == 2
        assert all(r.asset_type == "image" for r in results)

    @pytest.mark.asyncio
    async def test_audio_generation(self, tmp_path):
        mock_audio = MockAudioGenerator()
        gen = AssetGenerator(
            audio_generator=mock_audio, cache_dir=str(tmp_path / "cache")
        )
        plan = _make_audio_plan()
        results = await gen.generate_assets(plan)
        assert len(results) == 2
        assert all(r.asset_type == "audio" for r in results)

    @pytest.mark.asyncio
    async def test_visualization_chart(self, tmp_path):
        mock_chart = MockChartGenerator()
        gen = AssetGenerator(
            chart_generator=mock_chart, cache_dir=str(tmp_path / "cache")
        )
        plan = _make_viz_plan()
        results = await gen.generate_assets(plan)
        assert len(results) == 1
        assert results[0].asset_type == "chart"

    @pytest.mark.asyncio
    async def test_adapter_unavailable_skipped(self, tmp_path):
        mock_img = MockImageGenerator(available=False)
        gen = AssetGenerator(
            image_generator=mock_img, cache_dir=str(tmp_path / "cache")
        )
        plan = _make_lecture_with_assets()
        results = await gen.generate_assets(plan)
        image_results = [r for r in results if r.asset_type == "image"]
        assert len(image_results) == 0

    @pytest.mark.asyncio
    async def test_adapter_returns_none(self, tmp_path):
        mock_img = MockImageGenerator(fail=True)
        gen = AssetGenerator(
            image_generator=mock_img, cache_dir=str(tmp_path / "cache")
        )
        plan = _make_lecture_with_assets()
        results = await gen.generate_assets(plan)
        image_results = [r for r in results if r.asset_type == "image"]
        assert len(image_results) == 0

    @pytest.mark.asyncio
    async def test_metadata_includes_slide_index(self, tmp_path):
        mock_img = MockImageGenerator()
        gen = AssetGenerator(
            image_generator=mock_img, cache_dir=str(tmp_path / "cache")
        )
        plan = _make_lecture_with_assets()
        results = await gen.generate_assets(plan)
        image_results = [r for r in results if r.asset_type == "image"]
        if image_results:
            meta = dict(image_results[0].metadata)
            assert "slide_index" in meta

    @pytest.mark.asyncio
    async def test_metadata_includes_card_index(self, tmp_path):
        mock_img = MockImageGenerator()
        gen = AssetGenerator(
            image_generator=mock_img, cache_dir=str(tmp_path / "cache")
        )
        plan = _make_card_news_with_images()
        results = await gen.generate_assets(plan)
        if results:
            meta = dict(results[0].metadata)
            assert "card_index" in meta

    @pytest.mark.asyncio
    async def test_no_asset_slides_skipped(self, tmp_path):
        """asset_type이 None인 슬라이드는 스킵."""
        mock_img = MockImageGenerator()
        gen = AssetGenerator(
            image_generator=mock_img, cache_dir=str(tmp_path / "cache")
        )
        plan = LecturePlan(
            title="test",
            subtitle="test",
            duration_min=10,
            slides=(SlidePlan(index=1, title="텍스트만"),),
        )
        results = await gen.generate_assets(plan)
        assert len(results) == 0
        assert mock_img.call_count == 0

    @pytest.mark.asyncio
    async def test_partial_failure(self, tmp_path):
        """일부 어댑터 실패해도 나머지 성공."""
        mock_img = MockImageGenerator(fail=True)
        mock_chart = MockChartGenerator(fail=False)
        gen = AssetGenerator(
            image_generator=mock_img,
            chart_generator=mock_chart,
            cache_dir=str(tmp_path / "cache"),
        )
        plan = _make_lecture_with_assets()
        results = await gen.generate_assets(plan)
        # image 실패, chart 성공
        assert len(results) == 1
        assert results[0].asset_type == "chart"


class TestAssetGeneratorCaching:
    @pytest.mark.asyncio
    async def test_cache_key_deterministic(self):
        k1 = AssetGenerator._cache_key("test", 100, 100, "image")
        k2 = AssetGenerator._cache_key("test", 100, 100, "image")
        assert k1 == k2

    @pytest.mark.asyncio
    async def test_cache_key_varies_with_prompt(self):
        k1 = AssetGenerator._cache_key("test1", 100, 100, "image")
        k2 = AssetGenerator._cache_key("test2", 100, 100, "image")
        assert k1 != k2

    @pytest.mark.asyncio
    async def test_find_cached_returns_none_empty_dir(self, tmp_path):
        gen = AssetGenerator(cache_dir=str(tmp_path / "cache"))
        result = gen._find_cached("nonexistent_hash")
        assert result is None

    @pytest.mark.asyncio
    async def test_find_cached_hits_matching_file(self, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        # 캐시 파일 생성
        key = AssetGenerator._cache_key("test", 100, 100, "image")
        fake_file = cache_dir / f"cached-{key[:16]}.png"
        fake_file.write_bytes(b"\x89PNG")

        gen = AssetGenerator(cache_dir=str(cache_dir))
        result = gen._find_cached(key)
        assert result is not None
        assert result.asset_type == "image"


class TestExtractAssetRequests:
    def test_lecture_slides(self, tmp_path):
        gen = AssetGenerator(cache_dir=str(tmp_path / "cache"))
        plan = _make_lecture_with_assets()
        reqs = gen._extract_asset_requests(plan)
        assert len(reqs) == 2  # 1 image + 1 chart
        types = {r["asset_type"] for r in reqs}
        assert types == {"image", "chart"}

    def test_card_news(self, tmp_path):
        gen = AssetGenerator(cache_dir=str(tmp_path / "cache"))
        plan = _make_card_news_with_images()
        reqs = gen._extract_asset_requests(plan)
        assert len(reqs) == 2
        assert all(r["asset_type"] == "image" for r in reqs)

    def test_audio_sections(self, tmp_path):
        gen = AssetGenerator(cache_dir=str(tmp_path / "cache"))
        plan = _make_audio_plan()
        reqs = gen._extract_asset_requests(plan)
        assert len(reqs) == 2
        assert all(r["asset_type"] == "audio" for r in reqs)

    def test_visualization(self, tmp_path):
        gen = AssetGenerator(cache_dir=str(tmp_path / "cache"))
        plan = _make_viz_plan()
        reqs = gen._extract_asset_requests(plan)
        assert len(reqs) == 1
        assert reqs[0]["asset_type"] == "chart"
        assert reqs[0]["chart_type"] == "mindmap"
