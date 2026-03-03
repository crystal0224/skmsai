"""Card News Series 테스트.

PR-051: SeriesConfig 불변성, 프리셋 조회, 이미지 프롬프트 빌더.
"""
from __future__ import annotations

import pytest

from src.content_studio.card_series import (
    SERIES_PRESETS,
    SeriesConfig,
    build_image_prompt,
    get_series_preset,
    list_series_presets,
)


# ===================================================================
# SeriesConfig
# ===================================================================


class TestSeriesConfig:
    def test_frozen(self):
        config = SeriesConfig(
            series_name="test",
            card_count=1,
            schedule="daily",
            visual_style="square",
            width=100,
            height=100,
            description="test",
        )
        with pytest.raises(AttributeError):
            config.series_name = "modified"  # type: ignore[misc]

    def test_fields(self):
        config = SeriesConfig(
            series_name="my_series",
            card_count=3,
            schedule="weekly",
            visual_style="portrait",
            width=1080,
            height=1350,
            description="my description",
        )
        assert config.series_name == "my_series"
        assert config.card_count == 3
        assert config.schedule == "weekly"
        assert config.visual_style == "portrait"
        assert config.width == 1080
        assert config.height == 1350
        assert config.description == "my description"

    def test_daily_skms_preset(self):
        preset = get_series_preset("daily_skms")
        assert preset is not None
        assert preset.card_count == 1
        assert preset.schedule == "daily"
        assert preset.visual_style == "square"
        assert preset.width == 1080
        assert preset.height == 1080
        assert preset.description == "매일 1장, SKMS 핵심 개념 카드"

    def test_deep_read_preset(self):
        preset = get_series_preset("deep_read")
        assert preset is not None
        assert preset.card_count == 5
        assert preset.schedule == "weekly"
        assert preset.visual_style == "portrait"
        assert preset.width == 1080
        assert preset.height == 1350
        assert preset.description == "주간 5장, SKMS 심층 읽기 시리즈"

    def test_edition_compare_preset(self):
        preset = get_series_preset("edition_compare")
        assert preset is not None
        assert preset.card_count == 2
        assert preset.schedule == "monthly"
        assert preset.visual_style == "landscape"
        assert preset.width == 1200
        assert preset.height == 675
        assert preset.description == "월간 2장, 개정판 Before/After 비교"


# ===================================================================
# get_series_preset
# ===================================================================


class TestGetSeriesPreset:
    def test_get_existing(self):
        result = get_series_preset("daily_skms")
        assert result is not None
        assert isinstance(result, SeriesConfig)
        assert result.series_name == "daily_skms"

    def test_get_nonexistent(self):
        result = get_series_preset("nonexistent_series")
        assert result is None


# ===================================================================
# list_series_presets
# ===================================================================


class TestListSeriesPresets:
    def test_returns_tuple(self):
        presets = list_series_presets()
        assert isinstance(presets, tuple)

    def test_three_presets(self):
        presets = list_series_presets()
        assert len(presets) == 3

    def test_same_as_constant(self):
        assert list_series_presets() is SERIES_PRESETS


# ===================================================================
# build_image_prompt
# ===================================================================


class TestBuildImagePrompt:
    def test_daily_skms_prompt(self):
        series = get_series_preset("daily_skms")
        assert series is not None
        prompt = build_image_prompt(series, "SUPEX 추구", 1)
        assert "SUPEX 추구" in prompt
        assert "정사각형" in prompt
        assert "인포그래픽" in prompt

    def test_deep_read_prompt(self):
        series = get_series_preset("deep_read")
        assert series is not None
        prompt = build_image_prompt(series, "인간중심경영", 3)
        assert "3/5" in prompt
        assert "인간중심경영" in prompt
        assert "심층 분석" in prompt

    def test_edition_compare_prompt(self):
        series = get_series_preset("edition_compare")
        assert series is not None
        prompt = build_image_prompt(series, "VWBE 문화", 1)
        assert "Before/After" in prompt
        assert "VWBE 문화" in prompt
        assert "1/2" in prompt

    def test_unknown_series_prompt(self):
        custom = SeriesConfig(
            series_name="custom_unknown",
            card_count=3,
            schedule="daily",
            visual_style="square",
            width=800,
            height=800,
            description="custom",
        )
        prompt = build_image_prompt(custom, "테스트 주제", 2)
        assert "테스트 주제" in prompt
        assert "카드 2" in prompt
        assert "SKMS 교육용 카드" in prompt
