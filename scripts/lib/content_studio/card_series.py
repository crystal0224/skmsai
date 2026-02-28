"""Card News Series -- 시리즈 설정과 이미지 프롬프트 빌더.

PR-051: Card News Series + Visualization Data Transforms.

시리즈 프리셋 3종 (daily_skms, deep_read, edition_compare) 정의.
NanoBanana2 이미지 생성용 프롬프트 빌더 포함.
"""
from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# SeriesConfig 데이터 모델
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SeriesConfig:
    """카드뉴스 시리즈 설정 -- 불변.

    Attributes:
        series_name: 시리즈 식별자 (예: "daily_skms").
        card_count: 에피소드당 카드 수.
        schedule: 발행 주기 ("daily", "weekly", "monthly").
        visual_style: 시각 스타일 ("square", "portrait", "landscape").
        width: 이미지 너비 (px).
        height: 이미지 높이 (px).
        description: 시리즈 설명.
    """

    series_name: str
    card_count: int
    schedule: str
    visual_style: str
    width: int
    height: int
    description: str


# ---------------------------------------------------------------------------
# 시리즈 프리셋
# ---------------------------------------------------------------------------

SERIES_PRESETS: tuple[SeriesConfig, ...] = (
    SeriesConfig(
        series_name="daily_skms",
        card_count=1,
        schedule="daily",
        visual_style="square",
        width=1080,
        height=1080,
        description="매일 1장, SKMS 핵심 개념 카드",
    ),
    SeriesConfig(
        series_name="deep_read",
        card_count=5,
        schedule="weekly",
        visual_style="portrait",
        width=1080,
        height=1350,
        description="주간 5장, SKMS 심층 읽기 시리즈",
    ),
    SeriesConfig(
        series_name="edition_compare",
        card_count=2,
        schedule="monthly",
        visual_style="landscape",
        width=1200,
        height=675,
        description="월간 2장, 개정판 Before/After 비교",
    ),
)


# ---------------------------------------------------------------------------
# 프리셋 조회
# ---------------------------------------------------------------------------


def get_series_preset(name: str) -> SeriesConfig | None:
    """시리즈 이름으로 프리셋을 조회한다.

    Args:
        name: 시리즈 식별자 (예: "daily_skms").

    Returns:
        SeriesConfig 또는 None (없을 경우).
    """
    for preset in SERIES_PRESETS:
        if preset.series_name == name:
            return preset
    return None


def list_series_presets() -> tuple[SeriesConfig, ...]:
    """전체 시리즈 프리셋 목록을 반환한다.

    Returns:
        SeriesConfig 튜플.
    """
    return SERIES_PRESETS


# ---------------------------------------------------------------------------
# 이미지 프롬프트 빌더
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATES: dict[str, str] = {
    "daily_skms": ("SKMS 교육용 카드 이미지. 주제: {topic}. " "정사각형 구도, 깔끔한 인포그래픽 스타일, 한국어."),
    "deep_read": (
        "SKMS 심층 분석 카드 {card_index}/{card_count}. 주제: {topic}. " "세로 스크롤 레이아웃, 전문적 톤."
    ),
    "edition_compare": (
        "SKMS 개정판 비교 카드 {card_index}/{card_count}. 주제: {topic}. "
        "Before/After 구도, 타임라인 스타일."
    ),
}

_DEFAULT_PROMPT_TEMPLATE = "SKMS 교육용 카드. 주제: {topic}. 카드 {card_index}."


def build_image_prompt(series: SeriesConfig, topic: str, card_index: int) -> str:
    """시리즈 설정과 주제로 이미지 생성 프롬프트를 빌드한다.

    Args:
        series: 시리즈 설정.
        topic: 카드 주제 (예: "SUPEX 추구").
        card_index: 카드 순서 (1-based).

    Returns:
        NanoBanana2 이미지 생성용 프롬프트 문자열.
    """
    template = _PROMPT_TEMPLATES.get(series.series_name, _DEFAULT_PROMPT_TEMPLATE)
    return template.format(
        topic=topic,
        card_index=card_index,
        card_count=series.card_count,
    )
