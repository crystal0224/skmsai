"""Content Studio 데이터 모델 — 전체 frozen dataclass 정의.

PR-040: Content Studio 데이터 모델 + 설정.

모든 모델은 frozen dataclass (불변). 컬렉션은 tuple 사용.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypedDict, Union

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

VALID_CONTENT_TYPES: frozenset[str] = frozenset(
    {"lecture", "card_news", "workshop", "visualization", "audio", "quiz"}
)

VALID_LAYOUTS: frozenset[str] = frozenset(
    {
        "title_only",
        "title_content",
        "title_content_image",
        "comparison",
        "section_header",
    }
)

VALID_PHASE_TYPES: frozenset[str] = frozenset({"intro", "main", "activity", "wrap_up"})

VALID_AUDIO_STYLES: frozenset[str] = frozenset({"narration", "dialogue", "podcast"})

VALID_VIZ_TYPES: frozenset[str] = frozenset(
    {"timeline", "mindmap", "comparison", "wordcloud", "radar", "sankey", "flowchart"}
)

VALID_DIFFICULTIES: frozenset[str] = frozenset({"easy", "medium", "hard"})

VALID_ASSET_TYPES: frozenset[str] = frozenset({"image", "chart", "audio"})

VALID_FILE_TYPES: frozenset[str] = frozenset(
    {"pptx", "png", "pdf", "svg", "mp3", "html"}
)


# ---------------------------------------------------------------------------
# 공통 모델
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContentOptions:
    """콘텐츠 생성 옵션 (불변).

    Attributes:
        duration_min: 강의/워크숍 시간(분).
        num_items: 슬라이드/카드/문항 수.
        edition_filter: 특정 개정판 제한 (예: "2020-14차").
        style: 시각 스타일 (professional, casual, academic).
        language: 출력 언어 (ko, en).
        include_quiz: 학습 퀴즈 포함 여부.
        include_speaker_notes: 발표자 노트 포함 여부.
    """

    duration_min: int | None = None
    num_items: int | None = None
    edition_filter: str | None = None
    style: str = "professional"
    language: str = "ko"
    include_quiz: bool = False
    include_speaker_notes: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "duration_min": self.duration_min,
            "num_items": self.num_items,
            "edition_filter": self.edition_filter,
            "style": self.style,
            "language": self.language,
            "include_quiz": self.include_quiz,
            "include_speaker_notes": self.include_speaker_notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContentOptions:
        return cls(
            duration_min=data.get("duration_min"),
            num_items=data.get("num_items"),
            edition_filter=data.get("edition_filter"),
            style=data.get("style", "professional"),
            language=data.get("language", "ko"),
            include_quiz=data.get("include_quiz", False),
            include_speaker_notes=data.get("include_speaker_notes", True),
        )


@dataclass(frozen=True)
class ContentRequest:
    """콘텐츠 생성 요청 (불변).

    Attributes:
        content_type: 콘텐츠 유형 (lecture, card_news, workshop, visualization, audio, quiz).
        topic: 주제 (예: "SUPEX 추구의 변천사").
        options: 유형별 옵션.
    """

    content_type: str
    topic: str
    options: ContentOptions = field(default_factory=ContentOptions)

    def __post_init__(self) -> None:
        if self.content_type not in VALID_CONTENT_TYPES:
            raise ValueError(
                f"유효하지 않은 content_type: {self.content_type!r}. "
                f"허용: {sorted(VALID_CONTENT_TYPES)}"
            )
        if not self.topic or not self.topic.strip():
            raise ValueError("topic은 빈 문자열일 수 없습니다")
        if len(self.topic) > 200:
            raise ValueError(f"topic은 200자 이내여야 합니다: {len(self.topic)}자")

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_type": self.content_type,
            "topic": self.topic,
            "options": self.options.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContentRequest:
        options_data = data.get("options", {})
        options = (
            ContentOptions.from_dict(options_data)
            if isinstance(options_data, dict)
            else ContentOptions()
        )
        return cls(
            content_type=data["content_type"],
            topic=data["topic"],
            options=options,
        )


@dataclass(frozen=True)
class GeneratedAsset:
    """생성된 에셋 (이미지/차트/오디오) — 불변.

    Attributes:
        asset_type: 에셋 유형 (image, chart, audio).
        file_path: 로컬 파일 경로.
        prompt_used: 생성에 사용된 프롬프트.
        width: 이미지/차트 너비 (px).
        height: 이미지/차트 높이 (px).
        metadata: 추가 메타데이터.
    """

    asset_type: str
    file_path: str
    prompt_used: str
    width: int | None = None
    height: int | None = None
    metadata: tuple[tuple[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.asset_type not in VALID_ASSET_TYPES:
            raise ValueError(f"유효하지 않은 asset_type: {self.asset_type!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_type": self.asset_type,
            "file_path": self.file_path,
            "prompt_used": self.prompt_used,
            "width": self.width,
            "height": self.height,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GeneratedAsset:
        meta = data.get("metadata", {})
        metadata_tuple = tuple(sorted(meta.items())) if isinstance(meta, dict) else ()
        return cls(
            asset_type=data["asset_type"],
            file_path=data["file_path"],
            prompt_used=data["prompt_used"],
            width=data.get("width"),
            height=data.get("height"),
            metadata=metadata_tuple,
        )

    @property
    def content_hash(self) -> str:
        """캐싱용 해시: 동일 프롬프트+크기 → 동일 해시."""
        raw = f"{self.prompt_used}|{self.width}|{self.height}|{self.asset_type}"
        return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class GeneratedFile:
    """생성된 최종 파일 — 불변.

    Attributes:
        file_type: 파일 유형 (pptx, png, pdf, svg, mp3, html).
        file_path: 로컬 경로.
        file_name: 파일명.
        size_bytes: 파일 크기 (bytes).
    """

    file_type: str
    file_path: str
    file_name: str
    size_bytes: int

    def __post_init__(self) -> None:
        if self.file_type not in VALID_FILE_TYPES:
            raise ValueError(f"유효하지 않은 file_type: {self.file_type!r}")
        if self.size_bytes < 0:
            raise ValueError(f"size_bytes는 0 이상이어야 합니다: {self.size_bytes}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_type": self.file_type,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GeneratedFile:
        return cls(
            file_type=data["file_type"],
            file_path=data["file_path"],
            file_name=data["file_name"],
            size_bytes=data["size_bytes"],
        )


# ---------------------------------------------------------------------------
# 강의자료 (Lecture)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SlidePlan:
    """슬라이드 계획 — 불변.

    Attributes:
        index: 슬라이드 순서 (1-based).
        title: 슬라이드 제목.
        layout: 레이아웃 유형.
        key_points: 핵심 포인트 (3~5개).
        rag_query: RAG 검색에 사용할 쿼리.
        edition_filter: 특정 개정판 제한.
        asset_type: 에셋 유형 (image, chart, None).
        asset_prompt: 이미지/차트 생성 프롬프트.
        speaker_notes: 발표자 노트.
    """

    index: int
    title: str
    layout: str = "title_content"
    key_points: tuple[str, ...] = ()
    rag_query: str = ""
    edition_filter: str | None = None
    asset_type: str | None = None
    asset_prompt: str | None = None
    speaker_notes: str | None = None

    def __post_init__(self) -> None:
        if self.index < 1:
            raise ValueError(f"index는 1 이상이어야 합니다: {self.index}")
        if self.layout not in VALID_LAYOUTS:
            raise ValueError(f"유효하지 않은 layout: {self.layout!r}")
        if self.asset_type is not None and self.asset_type not in {"image", "chart"}:
            raise ValueError(f"유효하지 않은 asset_type: {self.asset_type!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "title": self.title,
            "layout": self.layout,
            "key_points": list(self.key_points),
            "rag_query": self.rag_query,
            "edition_filter": self.edition_filter,
            "asset_type": self.asset_type,
            "asset_prompt": self.asset_prompt,
            "speaker_notes": self.speaker_notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SlidePlan:
        return cls(
            index=data["index"],
            title=data["title"],
            layout=data.get("layout", "title_content"),
            key_points=tuple(data.get("key_points", ())),
            rag_query=data.get("rag_query", ""),
            edition_filter=data.get("edition_filter"),
            asset_type=data.get("asset_type"),
            asset_prompt=data.get("asset_prompt"),
            speaker_notes=data.get("speaker_notes"),
        )


@dataclass(frozen=True)
class LecturePlan:
    """강의자료 계획 — 불변.

    Attributes:
        title: 강의 제목.
        subtitle: 부제.
        duration_min: 강의 시간(분).
        slides: 슬라이드 계획 목록.
        learning_objectives: 학습 목표 (3~5개).
    """

    title: str
    subtitle: str
    duration_min: int
    slides: tuple[SlidePlan, ...] = ()
    learning_objectives: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.duration_min < 1:
            raise ValueError(f"duration_min은 1 이상이어야 합니다: {self.duration_min}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "duration_min": self.duration_min,
            "slides": [s.to_dict() for s in self.slides],
            "learning_objectives": list(self.learning_objectives),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LecturePlan:
        slides = tuple(SlidePlan.from_dict(s) for s in data.get("slides", ()))
        return cls(
            title=data["title"],
            subtitle=data.get("subtitle", ""),
            duration_min=data["duration_min"],
            slides=slides,
            learning_objectives=tuple(data.get("learning_objectives", ())),
        )


# ---------------------------------------------------------------------------
# 카드뉴스 (CardNews)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CardPlan:
    """카드 계획 — 불변.

    Attributes:
        index: 카드 순서 (1-based).
        headline: 카드 제목 (짧게).
        body: 본문 (2~3줄).
        source_quote: 출처 quote_id.
        image_prompt: 나노바나나2 이미지 생성 프롬프트.
        text_overlay: 이미지 위 텍스트 오버레이.
    """

    index: int
    headline: str
    body: str
    source_quote: str = ""
    image_prompt: str = ""
    text_overlay: str | None = None

    def __post_init__(self) -> None:
        if self.index < 1:
            raise ValueError(f"index는 1 이상이어야 합니다: {self.index}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "headline": self.headline,
            "body": self.body,
            "source_quote": self.source_quote,
            "image_prompt": self.image_prompt,
            "text_overlay": self.text_overlay,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CardPlan:
        return cls(
            index=data["index"],
            headline=data["headline"],
            body=data["body"],
            source_quote=data.get("source_quote", ""),
            image_prompt=data.get("image_prompt", ""),
            text_overlay=data.get("text_overlay"),
        )


@dataclass(frozen=True)
class CardNewsPlan:
    """카드뉴스 계획 — 불변.

    Attributes:
        title: 카드뉴스 시리즈 제목.
        total_cards: 총 카드 수.
        cards: 카드 계획 목록.
        image_size: 이미지 크기 (width, height). 기본 (1080, 1080).
    """

    title: str
    total_cards: int
    cards: tuple[CardPlan, ...] = ()
    image_size: tuple[int, int] = (1080, 1080)

    def __post_init__(self) -> None:
        if self.total_cards < 1:
            raise ValueError(f"total_cards는 1 이상이어야 합니다: {self.total_cards}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "total_cards": self.total_cards,
            "cards": [c.to_dict() for c in self.cards],
            "image_size": list(self.image_size),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CardNewsPlan:
        cards = tuple(CardPlan.from_dict(c) for c in data.get("cards", ()))
        img = data.get("image_size", [1080, 1080])
        return cls(
            title=data["title"],
            total_cards=data["total_cards"],
            cards=cards,
            image_size=tuple(img) if isinstance(img, list) else img,
        )


# ---------------------------------------------------------------------------
# 워크숍 (Workshop)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkshopPhase:
    """워크숍 단계 — 불변.

    Attributes:
        phase_type: 단계 유형 (intro, main, activity, wrap_up).
        title: 단계 제목.
        duration_min: 소요 시간(분).
        description: 단계 설명.
        facilitator_guide: 진행자 가이드.
        materials_needed: 필요 자료 목록.
        rag_query: RAG 검색 쿼리.
    """

    phase_type: str
    title: str
    duration_min: int
    description: str = ""
    facilitator_guide: str = ""
    materials_needed: tuple[str, ...] = ()
    rag_query: str | None = None

    def __post_init__(self) -> None:
        if self.phase_type not in VALID_PHASE_TYPES:
            raise ValueError(f"유효하지 않은 phase_type: {self.phase_type!r}")
        if self.duration_min < 1:
            raise ValueError(f"duration_min은 1 이상이어야 합니다: {self.duration_min}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase_type": self.phase_type,
            "title": self.title,
            "duration_min": self.duration_min,
            "description": self.description,
            "facilitator_guide": self.facilitator_guide,
            "materials_needed": list(self.materials_needed),
            "rag_query": self.rag_query,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkshopPhase:
        return cls(
            phase_type=data["phase_type"],
            title=data["title"],
            duration_min=data["duration_min"],
            description=data.get("description", ""),
            facilitator_guide=data.get("facilitator_guide", ""),
            materials_needed=tuple(data.get("materials_needed", ())),
            rag_query=data.get("rag_query"),
        )


@dataclass(frozen=True)
class WorkshopPlan:
    """워크숍 계획 — 불변.

    Attributes:
        title: 워크숍 제목.
        duration_min: 총 소요 시간(분).
        target_audience: 대상 참가자.
        phases: 워크숍 단계 목록.
    """

    title: str
    duration_min: int
    target_audience: str = ""
    phases: tuple[WorkshopPhase, ...] = ()

    def __post_init__(self) -> None:
        if self.duration_min < 1:
            raise ValueError(f"duration_min은 1 이상이어야 합니다: {self.duration_min}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "duration_min": self.duration_min,
            "target_audience": self.target_audience,
            "phases": [p.to_dict() for p in self.phases],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkshopPlan:
        phases = tuple(WorkshopPhase.from_dict(p) for p in data.get("phases", ()))
        return cls(
            title=data["title"],
            duration_min=data["duration_min"],
            target_audience=data.get("target_audience", ""),
            phases=phases,
        )


# ---------------------------------------------------------------------------
# 오디오 (Audio)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScriptSection:
    """스크립트 섹션 — 불변.

    Attributes:
        index: 섹션 순서 (1-based).
        speaker: 발화자 (narrator, host, expert).
        text: 대본 텍스트.
        rag_query: RAG 검색 쿼리.
    """

    index: int
    speaker: str
    text: str
    rag_query: str | None = None

    def __post_init__(self) -> None:
        if self.index < 1:
            raise ValueError(f"index는 1 이상이어야 합니다: {self.index}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "speaker": self.speaker,
            "text": self.text,
            "rag_query": self.rag_query,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScriptSection:
        return cls(
            index=data["index"],
            speaker=data["speaker"],
            text=data["text"],
            rag_query=data.get("rag_query"),
        )


@dataclass(frozen=True)
class AudioPlan:
    """오디오 계획 — 불변.

    Attributes:
        title: 오디오 제목.
        style: 스타일 (narration, dialogue, podcast).
        total_duration_min: 총 길이(분).
        sections: 스크립트 섹션 목록.
    """

    title: str
    style: str
    total_duration_min: int
    sections: tuple[ScriptSection, ...] = ()

    def __post_init__(self) -> None:
        if self.style not in VALID_AUDIO_STYLES:
            raise ValueError(f"유효하지 않은 style: {self.style!r}")
        if self.total_duration_min < 1:
            raise ValueError(
                f"total_duration_min은 1 이상이어야 합니다: {self.total_duration_min}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "style": self.style,
            "total_duration_min": self.total_duration_min,
            "sections": [s.to_dict() for s in self.sections],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AudioPlan:
        sections = tuple(ScriptSection.from_dict(s) for s in data.get("sections", ()))
        return cls(
            title=data["title"],
            style=data["style"],
            total_duration_min=data["total_duration_min"],
            sections=sections,
        )


# ---------------------------------------------------------------------------
# 시각화 (Visualization)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VisualizationPlan:
    """시각화 계획 — 불변.

    Attributes:
        title: 시각화 제목.
        viz_type: 시각화 유형 (timeline, mindmap, comparison 등).
        data_description: 데이터 설명 (LLM이 이해할 수 있도록).
        rag_query: RAG 검색 쿼리.
        chart_options: 차트 옵션 (테마, 색상 등).
    """

    title: str
    viz_type: str
    data_description: str = ""
    rag_query: str = ""
    chart_options: tuple[tuple[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.viz_type not in VALID_VIZ_TYPES:
            raise ValueError(f"유효하지 않은 viz_type: {self.viz_type!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "viz_type": self.viz_type,
            "data_description": self.data_description,
            "rag_query": self.rag_query,
            "chart_options": dict(self.chart_options),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VisualizationPlan:
        opts = data.get("chart_options", {})
        chart_options = tuple(sorted(opts.items())) if isinstance(opts, dict) else ()
        return cls(
            title=data["title"],
            viz_type=data["viz_type"],
            data_description=data.get("data_description", ""),
            rag_query=data.get("rag_query", ""),
            chart_options=chart_options,
        )


# ---------------------------------------------------------------------------
# 퀴즈 (Quiz)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QuizQuestion:
    """퀴즈 문항 — 불변.

    Attributes:
        index: 문항 순서 (1-based).
        question_text: 문제 텍스트.
        choices: 선택지 목록 (4지선다).
        correct_answer: 정답 인덱스 (0-based).
        explanation: 해설.
        difficulty: 난이도 (easy, medium, hard).
        source_quote: 출처 quote_id.
    """

    index: int
    question_text: str
    choices: tuple[str, ...] = ()
    correct_answer: int = 0
    explanation: str = ""
    difficulty: str = "medium"
    source_quote: str = ""

    def __post_init__(self) -> None:
        if self.index < 1:
            raise ValueError(f"index는 1 이상이어야 합니다: {self.index}")
        if self.difficulty not in VALID_DIFFICULTIES:
            raise ValueError(f"유효하지 않은 difficulty: {self.difficulty!r}")
        if self.choices and (
            self.correct_answer < 0 or self.correct_answer >= len(self.choices)
        ):
            raise ValueError(
                f"correct_answer 범위 초과: {self.correct_answer} (choices: {len(self.choices)}개)"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "question_text": self.question_text,
            "choices": list(self.choices),
            "correct_answer": self.correct_answer,
            "explanation": self.explanation,
            "difficulty": self.difficulty,
            "source_quote": self.source_quote,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QuizQuestion:
        return cls(
            index=data["index"],
            question_text=data["question_text"],
            choices=tuple(data.get("choices", ())),
            correct_answer=data.get("correct_answer", 0),
            explanation=data.get("explanation", ""),
            difficulty=data.get("difficulty", "medium"),
            source_quote=data.get("source_quote", ""),
        )


@dataclass(frozen=True)
class QuizPlan:
    """퀴즈 계획 — 불변.

    Attributes:
        title: 퀴즈 제목.
        total_questions: 총 문항 수.
        questions: 문항 목록.
        difficulty_distribution: 난이도 분포 (easy, medium, hard 비율).
    """

    title: str
    total_questions: int
    questions: tuple[QuizQuestion, ...] = ()
    difficulty_distribution: tuple[tuple[str, float], ...] = (
        ("easy", 0.3),
        ("medium", 0.5),
        ("hard", 0.2),
    )

    def __post_init__(self) -> None:
        if self.total_questions < 1:
            raise ValueError(f"total_questions는 1 이상이어야 합니다: {self.total_questions}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "total_questions": self.total_questions,
            "questions": [q.to_dict() for q in self.questions],
            "difficulty_distribution": dict(self.difficulty_distribution),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QuizPlan:
        questions = tuple(QuizQuestion.from_dict(q) for q in data.get("questions", ()))
        dist = data.get(
            "difficulty_distribution", {"easy": 0.3, "medium": 0.5, "hard": 0.2}
        )
        dist_tuple = tuple(sorted(dist.items())) if isinstance(dist, dict) else ()
        return cls(
            title=data["title"],
            total_questions=data["total_questions"],
            questions=questions,
            difficulty_distribution=dist_tuple,
        )


# ---------------------------------------------------------------------------
# ContentPlan Union + ContentResult
# ---------------------------------------------------------------------------

ContentPlan = Union[
    LecturePlan, CardNewsPlan, WorkshopPlan, AudioPlan, VisualizationPlan, QuizPlan
]


@dataclass(frozen=True)
class ContentResult:
    """콘텐츠 생성 결과 — 불변.

    Attributes:
        content_type: 콘텐츠 유형.
        topic: 주제.
        files: 생성된 파일 목록.
        citations: 사용된 quote_id 목록.
        metadata: 생성 메타데이터 (소요시간, RAG 횟수 등).
        plan: 사용된 계획.
    """

    content_type: str
    topic: str
    files: tuple[GeneratedFile, ...]
    citations: tuple[str, ...]
    metadata: tuple[tuple[str, Any], ...] = ()
    plan: ContentPlan | None = None

    def __post_init__(self) -> None:
        if self.content_type not in VALID_CONTENT_TYPES:
            raise ValueError(f"유효하지 않은 content_type: {self.content_type!r}")

    def to_dict(self) -> dict[str, Any]:
        plan_dict = self.plan.to_dict() if self.plan else None
        return {
            "content_type": self.content_type,
            "topic": self.topic,
            "files": [f.to_dict() for f in self.files],
            "citations": list(self.citations),
            "metadata": dict(self.metadata),
            "plan": plan_dict,
        }


# ---------------------------------------------------------------------------
# 설정 TypedDict
# ---------------------------------------------------------------------------


class _ContentStudioConfigRequired(TypedDict):
    """ContentStudioConfig 필수 키."""

    output_dir: str


class ContentStudioConfig(_ContentStudioConfigRequired, total=False):
    """Content Studio 설정 딕셔너리 타입.

    load_content_studio_config()의 반환 타입.
    output_dir만 필수, 나머지는 선택.
    """

    mcp_servers: dict[str, Any]
    lecture: dict[str, Any]
    card_news: dict[str, Any]
    workshop: dict[str, Any]
    audio: dict[str, Any]
    visualization: dict[str, Any]
    quiz: dict[str, Any]


# ---------------------------------------------------------------------------
# 설정 로더
# ---------------------------------------------------------------------------


def load_content_studio_config(path: str | Path) -> ContentStudioConfig:
    """content_studio.yaml을 로드하고 기본 스키마를 검증한다.

    Args:
        path: YAML 파일 경로.

    Returns:
        파싱된 ContentStudioConfig 딕셔너리.

    Raises:
        FileNotFoundError: 파일이 존재하지 않을 때.
        ValueError: 필수 키가 누락되었을 때.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"설정 파일의 최상위는 dict여야 합니다: {type(raw)}")

    config = raw.get("content_studio")
    if config is None:
        raise ValueError("설정 파일에 'content_studio' 키가 필요합니다")

    # 필수 하위 키 검증
    required_keys = {"output_dir"}
    missing = required_keys - set(config.keys())
    if missing:
        raise ValueError(f"필수 설정 키가 누락되었습니다: {missing}")

    return config
