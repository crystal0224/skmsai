"""디자인 토큰 함수 단위 테스트."""
from src.content_studio.assembler import (
    _design_tokens,
    _base_reset,
    _responsive_wrapper,
    _card_fixed_styles,
)


class TestDesignTokens:
    def test_returns_css_custom_properties(self):
        css = _design_tokens()
        assert ":root" in css
        assert "--c-primary" in css
        assert "--c-text-muted" in css

    def test_wcag_muted_color_is_not_aaa_or_999(self):
        css = _design_tokens()
        assert "#AAA" not in css
        assert "#aaa" not in css
        assert "#999" not in css

    def test_warm_neutral_palette(self):
        css = _design_tokens()
        assert "#6B7280" in css or "#6b7280" in css
        assert "#FAFAF8" in css or "#fafaf8" in css

    def test_includes_font_stack(self):
        css = _design_tokens()
        assert "Pretendard" in css

    def test_includes_radius_tokens(self):
        css = _design_tokens()
        assert "--radius-sm" in css
        assert "--radius-md" in css
        assert "--radius-lg" in css


class TestBaseReset:
    def test_returns_box_sizing(self):
        css = _base_reset()
        assert "box-sizing" in css

    def test_uses_css_variables(self):
        css = _base_reset()
        assert "var(--" in css


class TestResponsiveWrapper:
    def test_returns_max_width(self):
        css = _responsive_wrapper()
        assert "max-width" in css
        assert "clamp" in css

    def test_content_wrap_class(self):
        css = _responsive_wrapper()
        assert ".content-wrap" in css


class TestCardFixedStyles:
    def test_returns_fixed_1080(self):
        css = _card_fixed_styles()
        assert "1080px" in css

    def test_uses_print_media_query(self):
        css = _card_fixed_styles()
        assert "@media print" in css or "@media" in css
