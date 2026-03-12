"""PPTX 템플릿 시스템 — 테마 로드, 레이아웃 선택, TOC/Footer 생성.

PR-050: PPTX Template System for Content Studio.

테마는 config/pptx_themes.yaml에서 로드.
스타일 → 테마 매핑, 슬라이드 콘텐츠 기반 레이아웃 자동 선택.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, TypedDict

import yaml


# ---------------------------------------------------------------------------
# PptxTheme 데이터 모델
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PptxTheme:
    """PPTX 색상 테마 — 불변 (미니멀리즘 규격).

    Attributes:
        name: 테마 표시 이름.
        primary: 주 강조 색상 (SK Blue).
        secondary: 보조 색상 (연한 블루 또는 회색).
        accent: 포인트 색상.
        background: 배경 색상 (화이트 고정).
        text: 기본 텍스트 색상 (다크 그레이).
        font: 기본 폰트 이름.
    """

    name: str = "minimal_corporate"
    primary: str = "#0052A2"
    secondary: str = "#6C757D"
    accent: str = "#0052A2"
    background: str = "#FFFFFF"
    text: str = "#1A1A2E"
    font: str = "Pretendard"

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
# 레이아웃 선택 (PR-055: Intelligent Layout Selection)
# ---------------------------------------------------------------------------

_LAYOUT_NAME_TO_INDEX: dict[str, int] = {
    "title_only": 0,
    "title_content": 1,
    "section_header": 2,
    "title_content_image": 1,  # 보통 Title and Content 사용 후 이미지 배치
    "comparison": 3,
    "two_content": 3,
    "content_with_caption": 7,
    "picture_with_caption": 8,
}


def select_layout(slide_plan: Any) -> str:
    """슬라이드 콘텐츠 및 디자인 힌트에 기반해 레이아웃을 자동 선택한다.

    Args:
        slide_plan: SlidePlan 또는 key_points/layout 속성을 가진 객체.

    Returns:
        레이아웃 이름 문자열 (VALID_LAYOUTS 중 하나).
    """
    layout = getattr(slide_plan, "layout", "title_content")
    hint = getattr(slide_plan, "design_hint", "") or ""
    hint = hint.lower()

    # 1. 명시적 레이아웃이 title_content일 때 design_hint로 세분화
    if layout == "title_content":
        if "비교" in hint or "대비" in hint or "comparison" in hint:
            return "comparison"
        if "이미지 강조" in hint or "비주얼" in hint:
            return "picture_with_caption"
        if "요약" in hint or "결론" in hint:
            return "content_with_caption"

    # 2. 에셋 유무에 따른 보정
    if hasattr(slide_plan, "asset_type") and slide_plan.asset_type == "image":
        if layout == "title_content":
            return "title_content_image"

    return layout


def get_layout_index(layout_name: str) -> int:
    """레이아웃 이름에 해당하는 python-pptx 슬라이드 레이아웃 인덱스를 반환한다.

    Args:
        layout_name: 레이아웃 이름 (title_only, comparison 등).

    Returns:
        슬라이드 레이아웃 인덱스 (0~10). 기본값 1 (Title and Content).
    """
    return _LAYOUT_NAME_TO_INDEX.get(layout_name, 1)


# ---------------------------------------------------------------------------
# TypedDict 정의
# ---------------------------------------------------------------------------


class TocEntry(TypedDict):
    """TOC 항목 딕셔너리 타입."""

    index: int
    title: str


class FooterData(TypedDict):
    """슬라이드 Footer 딕셔너리 타입."""

    company: str
    date: str
    show_page_number: bool


# ---------------------------------------------------------------------------
# TOC 생성
# ---------------------------------------------------------------------------


def generate_toc_data(slides: tuple | list) -> list[TocEntry]:
    """슬라이드 목록에서 TOC(목차) 데이터를 추출한다.

    section_header 레이아웃이거나 index <= 1인 슬라이드를 필터링한다.

    Args:
        slides: SlidePlan 목록.

    Returns:
        TocEntry 리스트 [{"index": int, "title": str}, ...].
    """
    toc: list[TocEntry] = []
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
) -> FooterData:
    """PPTX 슬라이드 footer 데이터를 생성한다.

    Args:
        company: 회사명.
        date_str: 날짜 문자열 (ISO format). None이면 오늘 날짜.

    Returns:
        FooterData 딕셔너리.
    """
    return {
        "company": company,
        "date": date_str or date.today().isoformat(),
        "show_page_number": True,
    }
