"""PPTX 템플릿 시스템 테스트.

PR-050: PptxTheme, 테마 로드, 레이아웃 선택, TOC/Footer 생성.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.content_studio.pptx_templates import (
    PptxTheme,
    generate_footer,
    generate_toc_data,
    load_themes,
    select_layout,
    select_theme,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

THEMES_YAML_PATH = Path(__file__).parent.parent.parent / "config" / "pptx_themes.yaml"

REQUIRED_FIELDS = (
    "name",
    "primary",
    "secondary",
    "accent",
    "background",
    "text",
    "font",
)


def _make_slide_ns(**kwargs) -> SimpleNamespace:
    """테스트용 간이 슬라이드 객체."""
    defaults = {"index": 1, "title": "테스트", "layout": "title_content", "key_points": ()}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ===================================================================
# PptxTheme
# ===================================================================


class TestPptxTheme:
    def test_frozen(self):
        theme = PptxTheme(
            name="Test",
            primary="#000",
            secondary="#111",
            accent="#222",
            background="#FFF",
            text="#333",
            font="Arial",
        )
        with pytest.raises(AttributeError):
            theme.primary = "#999"  # type: ignore[misc]

    def test_fields(self):
        theme = PptxTheme(
            name="Test",
            primary="#E4002B",
            secondary="#003DA5",
            accent="#FF6B35",
            background="#FFFFFF",
            text="#1A1A1A",
            font="맑은 고딕",
        )
        assert theme.name == "Test"
        assert theme.primary == "#E4002B"
        assert theme.secondary == "#003DA5"
        assert theme.accent == "#FF6B35"
        assert theme.background == "#FFFFFF"
        assert theme.text == "#1A1A1A"
        assert theme.font == "맑은 고딕"

    def test_from_dict(self):
        data = {
            "name": "Corporate (SK)",
            "primary": "#E4002B",
            "secondary": "#003DA5",
            "accent": "#FF6B35",
            "background": "#FFFFFF",
            "text": "#1A1A1A",
            "font": "맑은 고딕",
        }
        theme = PptxTheme.from_dict(data)
        assert theme.name == "Corporate (SK)"
        assert theme.font == "맑은 고딕"


# ===================================================================
# load_themes
# ===================================================================


class TestLoadThemes:
    def test_load_3_themes(self):
        themes = load_themes(THEMES_YAML_PATH)
        assert "corporate" in themes
        assert "education" in themes
        assert "seminar" in themes
        assert len(themes) == 3

    def test_load_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_themes("/nonexistent/pptx_themes.yaml")

    def test_each_theme_has_required_fields(self):
        themes = load_themes(THEMES_YAML_PATH)
        for theme_name, theme in themes.items():
            for field_name in REQUIRED_FIELDS:
                assert hasattr(
                    theme, field_name
                ), f"Theme {theme_name!r} missing field {field_name!r}"
                assert getattr(
                    theme, field_name
                ), f"Theme {theme_name!r} has empty {field_name!r}"


# ===================================================================
# select_theme
# ===================================================================


class TestSelectTheme:
    def test_professional_maps_to_corporate(self):
        assert select_theme("professional") == "corporate"

    def test_casual_maps_to_education(self):
        assert select_theme("casual") == "education"

    def test_academic_maps_to_seminar(self):
        assert select_theme("academic") == "seminar"

    def test_unknown_maps_to_corporate(self):
        assert select_theme("funky") == "corporate"

    def test_empty_maps_to_corporate(self):
        assert select_theme("") == "corporate"


# ===================================================================
# select_layout
# ===================================================================


class TestSelectLayout:
    def test_few_key_points(self):
        plan = _make_slide_ns(key_points=("A", "B", "C"), layout="")
        assert select_layout(plan) == "title_content"

    def test_many_key_points(self):
        plan = _make_slide_ns(key_points=("A", "B", "C", "D"), layout="")
        assert select_layout(plan) == "title_content_image"

    def test_explicit_layout(self):
        plan = _make_slide_ns(layout="comparison", key_points=("A",))
        assert select_layout(plan) == "comparison"

    def test_no_key_points(self):
        plan = _make_slide_ns(key_points=(), layout="")
        assert select_layout(plan) == "title_content"

    def test_comparison_layout(self):
        plan = _make_slide_ns(layout="comparison", key_points=())
        assert select_layout(plan) == "comparison"


# ===================================================================
# generate_toc_data
# ===================================================================


class TestGenerateTocData:
    def test_with_section_headers(self):
        slides = [
            _make_slide_ns(index=1, title="Introduction", layout="title_only"),
            _make_slide_ns(index=2, title="Chapter 1", layout="section_header"),
            _make_slide_ns(index=3, title="Details", layout="title_content"),
            _make_slide_ns(index=4, title="Chapter 2", layout="section_header"),
        ]
        toc = generate_toc_data(slides)
        assert len(toc) == 3
        assert toc[0] == {"index": 1, "title": "Introduction"}
        assert toc[1] == {"index": 2, "title": "Chapter 1"}
        assert toc[2] == {"index": 4, "title": "Chapter 2"}

    def test_no_section_headers_returns_empty(self):
        slides = [
            _make_slide_ns(index=2, title="Slide 2", layout="title_content"),
            _make_slide_ns(index=3, title="Slide 3", layout="title_content"),
        ]
        toc = generate_toc_data(slides)
        assert toc == []

    def test_mixed_layouts(self):
        slides = [
            _make_slide_ns(index=1, title="Title", layout="title_only"),
            _make_slide_ns(index=2, title="Content", layout="title_content"),
            _make_slide_ns(index=3, title="Section", layout="section_header"),
            _make_slide_ns(index=4, title="More", layout="title_content_image"),
        ]
        toc = generate_toc_data(slides)
        titles = [entry["title"] for entry in toc]
        assert "Title" in titles
        assert "Section" in titles
        assert "Content" not in titles
        assert "More" not in titles


# ===================================================================
# generate_footer
# ===================================================================


class TestGenerateFooter:
    def test_default_footer(self):
        footer = generate_footer()
        assert footer["company"] == "SK Group"
        assert footer["date"] == date.today().isoformat()
        assert footer["show_page_number"] is True

    def test_custom_company(self):
        footer = generate_footer(company="SK Telecom")
        assert footer["company"] == "SK Telecom"

    def test_custom_date(self):
        footer = generate_footer(date_str="2026-01-01")
        assert footer["date"] == "2026-01-01"
