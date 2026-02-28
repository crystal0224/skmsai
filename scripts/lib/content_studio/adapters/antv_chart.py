"""AntV 차트 생성 어댑터.

PR-042: AntV 기반 데이터 시각화 생성.

AntV MCP 서버를 통해 차트/시각화를 생성한다.
ChartGenerator 프로토콜을 구현한다.

지원 차트 유형:
- timeline, mindmap, comparison, wordcloud, radar, sankey, flowchart

테마:
- classic (기본), dark, light

SKMS 특화 헬퍼:
- edition_timeline_data(): 개정판 타임라인 데이터
- concept_mindmap_data(): 핵심 개념 마인드맵 데이터
- element_radar_data(): 경영 요소 레이더 차트 데이터
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.lib.content_studio.models import GeneratedAsset

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

VALID_CHART_TYPES: frozenset[str] = frozenset(
    {"timeline", "mindmap", "comparison", "wordcloud", "radar", "sankey", "flowchart"}
)

VALID_THEMES: frozenset[str] = frozenset({"classic", "dark", "light"})

DEFAULT_OUTPUT_DIR = "output/assets"


# ---------------------------------------------------------------------------
# AntVChartConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AntVChartConfig:
    """AntV 차트 어댑터 설정 (불변).

    Attributes:
        mcp_endpoint: AntV MCP 서버 엔드포인트.
        output_dir: 차트 출력 디렉토리.
        default_theme: 기본 테마.
        default_width: 기본 차트 너비 (px).
        default_height: 기본 차트 높이 (px).
        output_format: 출력 형식 (svg, png).
    """

    mcp_endpoint: str = ""
    output_dir: str = DEFAULT_OUTPUT_DIR
    default_theme: str = "classic"
    default_width: int = 800
    default_height: int = 600
    output_format: str = "svg"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AntVChartConfig:
        return cls(
            mcp_endpoint=data.get("mcp_endpoint", ""),
            output_dir=data.get("output_dir", DEFAULT_OUTPUT_DIR),
            default_theme=data.get("default_theme", "classic"),
            default_width=int(data.get("default_width", 800)),
            default_height=int(data.get("default_height", 600)),
            output_format=data.get("output_format", "svg"),
        )


# ---------------------------------------------------------------------------
# SKMS 특화 데이터 헬퍼
# ---------------------------------------------------------------------------


def edition_timeline_data() -> dict[str, Any]:
    """SKMS 개정판 타임라인 데이터를 반환한다."""
    return {
        "chart_type": "timeline",
        "title": "SKMS 개정 연혁",
        "events": [
            {"year": 1979, "label": "초판", "description": "SKMS 최초 제정"},
            {"year": 1981, "label": "1차 개정", "description": "체계 확립"},
            {"year": 1988, "label": "5차 개정", "description": "경영요소 확장"},
            {"year": 1989, "label": "6차 개정", "description": "관리체계 보완"},
            {"year": 1990, "label": "7차 개정", "description": "실천 체계화"},
            {"year": 1995, "label": "8차 개정", "description": "글로벌 경영 반영"},
            {"year": 1997, "label": "9차 개정", "description": "SUPEX 추구 도입"},
            {"year": 1998, "label": "10차 개정", "description": "SUPEX 추구 체계화"},
            {"year": 2004, "label": "11차 개정", "description": "패러다임 전환"},
            {"year": 2008, "label": "12차 개정", "description": "사회적 가치 반영"},
            {"year": 2016, "label": "13차 개정", "description": "행복 경영"},
            {"year": 2020, "label": "14차 개정", "description": "VWBE Culture"},
        ],
    }


def concept_mindmap_data() -> dict[str, Any]:
    """SKMS 핵심 개념 마인드맵 데이터를 반환한다."""
    return {
        "chart_type": "mindmap",
        "title": "SKMS 핵심 개념",
        "root": "SKMS",
        "children": [
            {
                "label": "인간중심의 경영",
                "children": [
                    {"label": "인간의 본질적 특성"},
                    {"label": "의욕관리"},
                    {"label": "SK-Manship"},
                ],
            },
            {
                "label": "합리적 경영",
                "children": [
                    {"label": "경험과학"},
                    {"label": "사회적 규범"},
                    {"label": "예술적 감각"},
                ],
            },
            {
                "label": "현실 인식 경영",
                "children": [
                    {"label": "경영 현실"},
                    {"label": "환경 변화 대응"},
                ],
            },
        ],
    }


def element_radar_data() -> dict[str, Any]:
    """SKMS 경영 요소 레이더 차트 데이터를 반환한다."""
    return {
        "chart_type": "radar",
        "title": "SKMS 경영 요소 평가",
        "indicators": [
            "기획관리",
            "인사관리",
            "조직관리",
            "재무관리",
            "판매관리",
            "생산관리",
            "연구개발관리",
            "구매관리",
        ],
        "series": [
            {
                "name": "정적 요소",
                "values": [0.8, 0.7, 0.75, 0.6, 0.7, 0.65, 0.8, 0.6],
            },
            {
                "name": "동적 요소",
                "values": [0.7, 0.85, 0.8, 0.5, 0.65, 0.7, 0.75, 0.55],
            },
        ],
    }


# ---------------------------------------------------------------------------
# Markdown 표 fallback
# ---------------------------------------------------------------------------


def _chart_data_to_markdown(chart_type: str, data: dict[str, Any]) -> str:
    """차트 데이터를 Markdown 표로 변환한다 (fallback용)."""
    title = data.get("title", chart_type)
    lines = [f"## {title}", ""]

    if chart_type == "timeline":
        lines.append("| 연도 | 개정 | 설명 |")
        lines.append("|------|------|------|")
        for event in data.get("events", []):
            lines.append(
                f"| {event.get('year', '')} "
                f"| {event.get('label', '')} "
                f"| {event.get('description', '')} |"
            )
    elif chart_type == "radar":
        indicators = data.get("indicators", [])
        series = data.get("series", [])
        header = "| 지표 | " + " | ".join(s.get("name", "") for s in series) + " |"
        sep = "|------|" + "|".join("------" for _ in series) + "|"
        lines.append(header)
        lines.append(sep)
        for i, ind in enumerate(indicators):
            vals = " | ".join(
                str(s.get("values", [])[i]) if i < len(s.get("values", [])) else ""
                for s in series
            )
            lines.append(f"| {ind} | {vals} |")
    elif chart_type == "mindmap":
        root = data.get("root", "")
        lines.append(f"**{root}**")
        for child in data.get("children", []):
            lines.append(f"- {child.get('label', '')}")
            for sub in child.get("children", []):
                lines.append(f"  - {sub.get('label', '')}")
    else:
        lines.append(f"```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# AntVChartAdapter
# ---------------------------------------------------------------------------


class AntVChartAdapter:
    """AntV 차트 생성 어댑터.

    AntV MCP 서버를 통해 데이터 시각화를 생성한다.
    ChartGenerator 프로토콜을 구현한다.

    차트 생성 실패 시 Markdown 표로 fallback한다 (graceful).
    """

    def __init__(self, config: AntVChartConfig | None = None) -> None:
        self._config = config or AntVChartConfig()
        self._client: Any = None

    def _ensure_output_dir(self) -> Path:
        """출력 디렉토리를 확인/생성하고 Path를 반환한다."""
        output_path = Path(self._config.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        return output_path

    def _generate_filename(self, chart_type: str) -> str:
        """고유 파일명을 생성한다: antv-{chart_type}-{timestamp}-{uuid[:8]}.{ext}"""
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
        uid = uuid.uuid4().hex[:8]
        ext = self._config.output_format
        return f"antv-{chart_type}-{ts}-{uid}.{ext}"

    def _get_client(self) -> Any:
        """MCP 클라이언트를 lazy 초기화한다."""
        if self._client is not None:
            return self._client

        if not self._config.mcp_endpoint:
            logger.warning("AntV MCP 엔드포인트 미설정")
            return None

        try:
            # MCP 클라이언트 초기화 (실제 MCP SDK 사용 시 교체)
            self._client = {"endpoint": self._config.mcp_endpoint}
            return self._client
        except Exception:
            logger.warning("AntV MCP 클라이언트 초기화 실패", exc_info=True)
            return None

    async def is_available(self) -> bool:
        """MCP 엔드포인트가 설정되어 있고 연결 가능한지 확인한다."""
        return bool(self._config.mcp_endpoint) and self._get_client() is not None

    async def health_check(self) -> dict[str, Any]:
        """어댑터 상태를 반환한다."""
        available = await self.is_available()
        return {
            "status": "ok" if available else "error",
            "adapter": "antv_chart",
            "mcp_endpoint": self._config.mcp_endpoint,
            "default_theme": self._config.default_theme,
            "output_format": self._config.output_format,
        }

    async def generate_chart(
        self,
        chart_type: str,
        data: dict[str, Any],
        options: dict[str, Any],
    ) -> GeneratedAsset | None:
        """차트를 생성한다.

        Args:
            chart_type: 차트 유형 (timeline, mindmap, comparison 등).
            data: 차트 데이터.
            options: 차트 옵션 (theme, width, height 등).

        Returns:
            GeneratedAsset (차트 파일) 또는 None (실패 시).
            차트 생성 실패 시 Markdown fallback 에셋을 반환한다.
        """
        if chart_type not in VALID_CHART_TYPES:
            logger.warning("지원하지 않는 차트 유형: %s", chart_type)
            return None

        theme = options.get("theme", self._config.default_theme)
        if theme not in VALID_THEMES:
            theme = self._config.default_theme

        width = options.get("width", self._config.default_width)
        height = options.get("height", self._config.default_height)

        try:
            client = self._get_client()
            if client is None:
                logger.warning("AntV 클라이언트 사용 불가, Markdown fallback")
                return self._markdown_fallback(chart_type, data, options)

            # MCP 서버에 차트 생성 요청
            chart_spec = {
                "chart_type": chart_type,
                "data": data,
                "theme": theme,
                "width": width,
                "height": height,
                "format": self._config.output_format,
            }

            # MCP 호출 (실제 구현 시 비동기 MCP SDK 사용)
            if hasattr(client, "generate"):
                result = client.generate(chart_spec)
            elif isinstance(client, dict):
                # Mock/stub 클라이언트 — 실제 MCP SDK 통합 전
                logger.info("AntV MCP 호출: %s", chart_type)
                result = client.get("_mock_result")
                if result is None:
                    logger.warning("AntV MCP 응답 없음, Markdown fallback")
                    return self._markdown_fallback(chart_type, data, options)
            else:
                return self._markdown_fallback(chart_type, data, options)

            # 파일 저장
            output_dir = self._ensure_output_dir()
            filename = self._generate_filename(chart_type)
            file_path = output_dir / filename

            if isinstance(result, bytes):
                file_path.write_bytes(result)
            elif isinstance(result, str):
                file_path.write_text(result, encoding="utf-8")
            else:
                logger.warning("예상하지 못한 MCP 응답 형식: %s", type(result))
                return self._markdown_fallback(chart_type, data, options)

            return GeneratedAsset(
                asset_type="chart",
                file_path=str(file_path),
                prompt_used=json.dumps(
                    {"chart_type": chart_type, "title": data.get("title", "")},
                    ensure_ascii=False,
                ),
                width=width,
                height=height,
                metadata=(
                    ("adapter", "antv_chart"),
                    ("chart_type", chart_type),
                    ("theme", theme),
                    ("format", self._config.output_format),
                ),
            )

        except Exception:
            logger.warning("AntV 차트 생성 실패, Markdown fallback", exc_info=True)
            return self._markdown_fallback(chart_type, data, options)

    def _markdown_fallback(
        self,
        chart_type: str,
        data: dict[str, Any],
        options: dict[str, Any],
    ) -> GeneratedAsset:
        """차트 생성 실패 시 Markdown 표 텍스트를 반환한다."""
        md_content = _chart_data_to_markdown(chart_type, data)

        output_dir = self._ensure_output_dir()
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
        uid = uuid.uuid4().hex[:8]
        filename = f"antv-{chart_type}-{ts}-{uid}-fallback.md"
        file_path = output_dir / filename
        file_path.write_text(md_content, encoding="utf-8")

        return GeneratedAsset(
            asset_type="chart",
            file_path=str(file_path),
            prompt_used=json.dumps(
                {
                    "chart_type": chart_type,
                    "title": data.get("title", ""),
                    "fallback": True,
                },
                ensure_ascii=False,
            ),
            metadata=(
                ("adapter", "antv_chart"),
                ("chart_type", chart_type),
                ("fallback", True),
            ),
        )
