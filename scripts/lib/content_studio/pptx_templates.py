"""PPTX 템플릿 시스템 — 테마 로드, 레이아웃 선택, TOC/Footer 생성.

PR-050: PPTX Template System for Content Studio.

테마는 config/pptx_themes.yaml에서 로드.
스타일 → 테마 매핑, 슬라이드 콘텐츠 기반 레이아웃 자동 선택.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# PptxTheme 데이터 모델
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PptxTheme:
    """PPTX 색상 테마 — 불변.

    Attributes:
        name: 테마 표시 이름.
        primary: 주 색상 (hex).
        secondary: 보조 색상 (hex).
        accent: 강조 색상 (hex).
        background: 배경 색상 (hex).
        text: 텍스트 색상 (hex).
        font: 기본 폰트 이름.
    """

    name: str
    primary: str
    secondary: str
    accent: str
    background: str
    text: str
    font: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PptxTheme:
        return cls(
            name=data["name"],
            primary=data["primary"],
            secondary=data["secondary"],
            accent=data["accent"],
            background=data["background"],
            text=data["text"],
            font=data["font"],
        )


# ---------------------------------------------------------------------------
# 테마 로드
# ---------------------------------------------------------------------------

_STYLE_TO_THEME: dict[str, str] = {
    "professional": "corporate",
    "casual": "education",
    "academic": "seminar",
}


def load_themes(yaml_path: str | Path) -> dict[str, PptxTheme]:
    """YAML 파일에서 PPTX 테마를 로드한다.

    Args:
        yaml_path: pptx_themes.yaml 파일 경로.

    Returns:
        테마 이름 → PptxTheme 딕셔너리.

    Raises:
        FileNotFoundError: 파일이 존재하지 않을 때.
    """
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"테마 파일을 찾을 수 없습니다: {path}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    themes_data = raw.get("themes", {})
    return {key: PptxTheme.from_dict(value) for key, value in themes_data.items()}


# ---------------------------------------------------------------------------
# 테마 선택
# ---------------------------------------------------------------------------


def select_theme(style: str) -> str:
    """스타일 문자열을 테마 이름으로 매핑한다.

    Args:
        style: 스타일 (professional, casual, academic 등).

    Returns:
        테마 이름 (corporate, education, seminar).
    """
    return _STYLE_TO_THEME.get(style, "corporate")


# ---------------------------------------------------------------------------
# 레이아웃 선택
# ---------------------------------------------------------------------------


def select_layout(slide_plan: Any) -> str:
    """슬라이드 콘텐츠에 기반해 레이아웃을 자동 선택한다.

    Args:
        slide_plan: SlidePlan 또는 key_points/layout 속성을 가진 객체.

    Returns:
        레이아웃 이름 문자열.
    """
    # 명시적 layout 속성이 있으면 우선 사용
    if hasattr(slide_plan, "layout") and slide_plan.layout:
        return slide_plan.layout

    # key_points 개수에 따른 자동 선택
    if hasattr(slide_plan, "key_points") and slide_plan.key_points:
        if len(slide_plan.key_points) <= 3:
            return "title_content"
        return "title_content_image"

    return "title_content"


# ---------------------------------------------------------------------------
# TOC 생성
# ---------------------------------------------------------------------------


def generate_toc_data(slides: tuple | list) -> list[dict[str, Any]]:
    """슬라이드 목록에서 TOC(목차) 데이터를 추출한다.

    section_header 레이아웃이거나 index <= 1인 슬라이드를 필터링한다.

    Args:
        slides: SlidePlan 목록.

    Returns:
        TOC 항목 리스트 [{"index": int, "title": str}, ...].
    """
    toc: list[dict[str, Any]] = []
    for slide in slides:
        layout = getattr(slide, "layout", "")
        index = getattr(slide, "index", 0)
        title = getattr(slide, "title", "")

        if layout == "section_header" or index <= 1:
            toc.append({"index": index, "title": title})

    return toc


# ---------------------------------------------------------------------------
# Footer 생성
# ---------------------------------------------------------------------------


def generate_footer(
    company: str = "SK Group",
    date_str: str | None = None,
) -> dict[str, Any]:
    """PPTX 슬라이드 footer 데이터를 생성한다.

    Args:
        company: 회사명.
        date_str: 날짜 문자열 (ISO format). None이면 오늘 날짜.

    Returns:
        Footer 딕셔너리.
    """
    return {
        "company": company,
        "date": date_str or date.today().isoformat(),
        "show_page_number": True,
    }
