"""AntV 차트 어댑터 테스트 — Mock MCP 기반.

PR-042: AntV 차트 어댑터 단위 테스트.

실제 MCP 호출 없이 모든 경로를 테스트한다:
- 차트 유형별 생성
- 테마별 생성
- Markdown fallback
- 설정 관리
- SKMS 특화 데이터 헬퍼
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.content_studio.adapters.antv_chart import (
    VALID_CHART_TYPES,
    VALID_THEMES,
    AntVChartAdapter,
    AntVChartConfig,
    _chart_data_to_markdown,
    concept_mindmap_data,
    edition_timeline_data,
    element_radar_data,
)
from src.content_studio.adapters.base import ChartGenerator, MCPAdapter
from src.content_studio.models import GeneratedAsset


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def config(tmp_path: Path) -> AntVChartConfig:
    return AntVChartConfig(
        mcp_endpoint="http://localhost:3000/antv",
        output_dir=str(tmp_path),
        default_theme="classic",
        default_width=800,
        default_height=600,
        output_format="svg",
    )


@pytest.fixture()
def adapter(config: AntVChartConfig) -> AntVChartAdapter:
    return AntVChartAdapter(config)


@pytest.fixture()
def mock_client_with_svg() -> MagicMock:
    """SVG 바이트를 반환하는 mock MCP 클라이언트."""
    client = MagicMock()
    client.get = MagicMock(return_value=b"<svg>chart</svg>")
    # dict-like 클라이언트 시뮬레이션
    return {
        "endpoint": "http://localhost:3000/antv",
        "_mock_result": b"<svg>chart</svg>",
    }


# ---------------------------------------------------------------------------
# AntVChartConfig Tests
# ---------------------------------------------------------------------------


class TestAntVChartConfig:
    def test_default_config(self) -> None:
        config = AntVChartConfig()
        assert config.mcp_endpoint == ""
        assert config.default_theme == "classic"
        assert config.default_width == 800
        assert config.default_height == 600
        assert config.output_format == "svg"

    def test_config_from_dict(self) -> None:
        data = {
            "mcp_endpoint": "http://my-server:3000",
            "default_theme": "dark",
            "default_width": 1200,
            "default_height": 900,
            "output_format": "png",
        }
        config = AntVChartConfig.from_dict(data)
        assert config.mcp_endpoint == "http://my-server:3000"
        assert config.default_theme == "dark"
        assert config.default_width == 1200
        assert config.output_format == "png"

    def test_config_from_dict_defaults(self) -> None:
        config = AntVChartConfig.from_dict({})
        assert config.mcp_endpoint == ""
        assert config.default_theme == "classic"

    def test_config_is_frozen(self) -> None:
        config = AntVChartConfig()
        with pytest.raises(AttributeError):
            config.default_theme = "dark"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Protocol Conformance Tests
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_is_mcp_adapter(self, adapter: AntVChartAdapter) -> None:
        assert isinstance(adapter, MCPAdapter)

    def test_is_chart_generator(self, adapter: AntVChartAdapter) -> None:
        assert isinstance(adapter, ChartGenerator)


# ---------------------------------------------------------------------------
# Constants Tests
# ---------------------------------------------------------------------------


class TestConstants:
    def test_valid_chart_types(self) -> None:
        expected = {
            "timeline",
            "mindmap",
            "comparison",
            "wordcloud",
            "radar",
            "sankey",
            "flowchart",
        }
        assert VALID_CHART_TYPES == expected

    def test_valid_themes(self) -> None:
        assert VALID_THEMES == {"classic", "dark", "light"}


# ---------------------------------------------------------------------------
# Availability Tests
# ---------------------------------------------------------------------------


class TestAvailability:
    @pytest.mark.asyncio
    async def test_is_available_with_endpoint(self, adapter: AntVChartAdapter) -> None:
        result = await adapter.is_available()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_available_without_endpoint(self, tmp_path: Path) -> None:
        config = AntVChartConfig(mcp_endpoint="", output_dir=str(tmp_path))
        adapter = AntVChartAdapter(config)
        result = await adapter.is_available()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_ok(self, adapter: AntVChartAdapter) -> None:
        result = await adapter.health_check()
        assert result["status"] == "ok"
        assert result["adapter"] == "antv_chart"

    @pytest.mark.asyncio
    async def test_health_check_error(self, tmp_path: Path) -> None:
        config = AntVChartConfig(mcp_endpoint="", output_dir=str(tmp_path))
        adapter = AntVChartAdapter(config)
        result = await adapter.health_check()
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# generate_chart Tests
# ---------------------------------------------------------------------------


class TestGenerateChart:
    @pytest.mark.asyncio
    async def test_generate_chart_success_svg_bytes(
        self, adapter: AntVChartAdapter, tmp_path: Path
    ) -> None:
        """SVG 바이트 응답으로 차트 생성 성공."""
        adapter._client = {
            "endpoint": "http://localhost",
            "_mock_result": b"<svg>chart</svg>",
        }

        result = await adapter.generate_chart(
            "timeline",
            edition_timeline_data(),
            {"theme": "classic"},
        )

        assert result is not None
        assert result.asset_type == "chart"
        assert "antv-timeline" in result.file_path
        assert result.file_path.endswith(".svg")
        assert result.width == 800
        assert result.height == 600

        meta = dict(result.metadata)
        assert meta["adapter"] == "antv_chart"
        assert meta["chart_type"] == "timeline"

    @pytest.mark.asyncio
    async def test_generate_chart_success_string(
        self, adapter: AntVChartAdapter, tmp_path: Path
    ) -> None:
        """문자열 응답(SVG 텍스트)으로 차트 생성 성공."""
        adapter._client = {
            "endpoint": "http://localhost",
            "_mock_result": "<svg>text chart</svg>",
        }

        result = await adapter.generate_chart(
            "radar",
            element_radar_data(),
            {"theme": "dark"},
        )

        assert result is not None
        assert result.asset_type == "chart"
        file_path = Path(result.file_path)
        assert file_path.exists()
        content = file_path.read_text(encoding="utf-8")
        assert "<svg>" in content

    @pytest.mark.asyncio
    async def test_generate_chart_invalid_type(self, adapter: AntVChartAdapter) -> None:
        """지원하지 않는 차트 유형 → None."""
        result = await adapter.generate_chart(
            "pie_chart_3d",
            {"data": []},
            {},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_chart_invalid_theme_uses_default(
        self, adapter: AntVChartAdapter
    ) -> None:
        """유효하지 않은 테마 → 기본 테마 사용."""
        adapter._client = {
            "endpoint": "http://localhost",
            "_mock_result": b"<svg>chart</svg>",
        }

        result = await adapter.generate_chart(
            "mindmap",
            concept_mindmap_data(),
            {"theme": "neon_rainbow"},
        )

        assert result is not None
        meta = dict(result.metadata)
        assert meta["theme"] == "classic"  # default

    @pytest.mark.asyncio
    async def test_generate_chart_custom_dimensions(
        self, adapter: AntVChartAdapter
    ) -> None:
        """custom width/height 사용."""
        adapter._client = {
            "endpoint": "http://localhost",
            "_mock_result": b"<svg>chart</svg>",
        }

        result = await adapter.generate_chart(
            "timeline",
            {"title": "test", "events": []},
            {"width": 1200, "height": 900},
        )

        assert result is not None
        assert result.width == 1200
        assert result.height == 900

    @pytest.mark.asyncio
    async def test_generate_chart_no_client_fallback(self, tmp_path: Path) -> None:
        """클라이언트 없으면 Markdown fallback."""
        config = AntVChartConfig(mcp_endpoint="", output_dir=str(tmp_path))
        adapter = AntVChartAdapter(config)

        result = await adapter.generate_chart(
            "timeline",
            edition_timeline_data(),
            {},
        )

        assert result is not None
        assert result.asset_type == "chart"
        assert "fallback" in result.file_path

        meta = dict(result.metadata)
        assert meta["fallback"] is True

    @pytest.mark.asyncio
    async def test_generate_chart_api_error_fallback(
        self, adapter: AntVChartAdapter
    ) -> None:
        """MCP 오류 시 Markdown fallback."""
        bad_client = MagicMock()
        bad_client.generate = MagicMock(side_effect=RuntimeError("MCP error"))
        adapter._client = bad_client

        result = await adapter.generate_chart(
            "radar",
            element_radar_data(),
            {},
        )

        assert result is not None
        assert "fallback" in result.file_path

    @pytest.mark.asyncio
    async def test_generate_chart_no_mock_result_fallback(
        self, adapter: AntVChartAdapter
    ) -> None:
        """dict 클라이언트에 _mock_result 없으면 fallback."""
        adapter._client = {"endpoint": "http://localhost"}

        result = await adapter.generate_chart(
            "mindmap",
            concept_mindmap_data(),
            {},
        )

        assert result is not None
        assert "fallback" in result.file_path


# ---------------------------------------------------------------------------
# Markdown Fallback Tests
# ---------------------------------------------------------------------------


class TestMarkdownFallback:
    def test_timeline_markdown(self) -> None:
        data = edition_timeline_data()
        md = _chart_data_to_markdown("timeline", data)
        assert "SKMS 개정 연혁" in md
        assert "1979" in md
        assert "| 연도 |" in md

    def test_radar_markdown(self) -> None:
        data = element_radar_data()
        md = _chart_data_to_markdown("radar", data)
        assert "경영 요소 평가" in md
        assert "기획관리" in md
        assert "| 지표 |" in md

    def test_mindmap_markdown(self) -> None:
        data = concept_mindmap_data()
        md = _chart_data_to_markdown("mindmap", data)
        assert "**SKMS**" in md
        assert "인간중심의 경영" in md
        assert "- 의욕관리" in md

    def test_unknown_type_json_fallback(self) -> None:
        data = {"title": "test", "values": [1, 2, 3]}
        md = _chart_data_to_markdown("sankey", data)
        assert "```json" in md
        assert "test" in md


# ---------------------------------------------------------------------------
# SKMS Data Helper Tests
# ---------------------------------------------------------------------------


class TestSKMSDataHelpers:
    def test_edition_timeline_data_structure(self) -> None:
        data = edition_timeline_data()
        assert data["chart_type"] == "timeline"
        assert len(data["events"]) == 12
        assert data["events"][0]["year"] == 1979
        assert data["events"][-1]["year"] == 2020

    def test_concept_mindmap_data_structure(self) -> None:
        data = concept_mindmap_data()
        assert data["chart_type"] == "mindmap"
        assert data["root"] == "SKMS"
        assert len(data["children"]) == 3

    def test_element_radar_data_structure(self) -> None:
        data = element_radar_data()
        assert data["chart_type"] == "radar"
        assert len(data["indicators"]) == 8
        assert len(data["series"]) == 2
        for s in data["series"]:
            assert len(s["values"]) == len(data["indicators"])


# ---------------------------------------------------------------------------
# Internal Helper Tests
# ---------------------------------------------------------------------------


class TestInternalHelpers:
    def test_generate_filename_format(self, adapter: AntVChartAdapter) -> None:
        filename = adapter._generate_filename("timeline")
        assert filename.startswith("antv-timeline-")
        assert filename.endswith(".svg")

    def test_generate_filename_unique(self, adapter: AntVChartAdapter) -> None:
        filenames = {adapter._generate_filename("radar") for _ in range(10)}
        assert len(filenames) == 10

    def test_ensure_output_dir_creates_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "charts" / "output"
        config = AntVChartConfig(output_dir=str(target))
        adapter = AntVChartAdapter(config)

        result = adapter._ensure_output_dir()
        assert result.exists()
        assert result.is_dir()
