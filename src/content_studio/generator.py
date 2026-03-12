"""ContentGenerator — 아웃라인(Plan)을 본문(Content)으로 변환하는 RAG 기반 생성 서비스.

PR-044: ContentGenerator — outline to content generation using RAG.

각 콘텐츠 유형(lecture, card_news, workshop, audio)에 대해:
1. Plan의 각 항목에서 rag_query로 SearchService 검색
2. 검색 결과를 컨텍스트로 GenerationService에 전달
3. 생성된 텍스트를 Content 데이터클래스로 구조화
4. EvidenceFilter / TemporalGuardrail로 품질 검증
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from src.content_studio.models import (
    AudioPlan,
    CardNewsPlan,
    LecturePlan,
    WorkshopPlan,
)
from scripts.lib.search_types import SearchHit

logger = logging.getLogger(__name__)

# Korean words per minute for audio duration estimation
_WORDS_PER_MINUTE_KO = 120


# ---------------------------------------------------------------------------
# Content dataclasses (frozen, immutable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SlideContent:
    """생성된 슬라이드 콘텐츠."""

    index: int
    title: str
    governing_message: str = ""
    body_text: str = ""
    key_points: tuple[str, ...] = ()
    quote_ids: tuple[str, ...] = ()
    speaker_notes: str = ""


@dataclass(frozen=True)
class LectureContent:
    """생성된 강의 콘텐츠."""

    slides: tuple[SlideContent, ...]
    citations: tuple[str, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class CardContent:
    """생성된 카드 콘텐츠."""

    index: int
    headline: str
    body: str
    quote_ids: tuple[str, ...]
    source_quote: str = ""
    source_edition: str = ""


@dataclass(frozen=True)
class CardNewsContent:
    """생성된 카드뉴스 콘텐츠."""

    cards: tuple[CardContent, ...]
    citations: tuple[str, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class PhaseContent:
    """생성된 워크숍 단계 콘텐츠."""

    phase_type: str
    title: str
    content_text: str
    quote_ids: tuple[str, ...]


@dataclass(frozen=True)
class WorkshopContent:
    """생성된 워크숍 콘텐츠."""

    phases: tuple[PhaseContent, ...]
    citations: tuple[str, ...]
    quiz_questions: tuple = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SectionContent:
    """생성된 오디오 섹션 콘텐츠."""

    index: int
    speaker: str
    text: str
    quote_ids: tuple[str, ...]


@dataclass(frozen=True)
class AudioContent:
    """생성된 오디오 콘텐츠."""

    sections: tuple[SectionContent, ...]
    citations: tuple[str, ...]
    total_word_count: int = 0
    warnings: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Protocol interfaces for dependency injection
# ---------------------------------------------------------------------------


@runtime_checkable
class SearchServiceProtocol(Protocol):
    """SearchService 인터페이스 — 테스트 시 mock 가능."""

    def hybrid_search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        edition_filter: str | None = None,
    ) -> list[SearchHit]:
        ...


@runtime_checkable
class GenerationServiceProtocol(Protocol):
    """GenerationService 인터페이스 — 테스트 시 mock 가능."""

    def generate(
        self,
        query: str,
        context: str,
        intent: str,
        output_type: str | None = None,
    ) -> Any:
        ...


@runtime_checkable
class EvidenceFilterProtocol(Protocol):
    """EvidenceFilter 인터페이스 — 테스트 시 mock 가능."""

    def check(self, answer: str, hits: list[SearchHit]) -> Any:
        ...


@runtime_checkable
class TemporalGuardrailProtocol(Protocol):
    """TemporalGuardrail 인터페이스 — 테스트 시 mock 가능."""

    def check(
        self,
        hits: list[SearchHit],
        *,
        query: str = "",
        edition_hint: str | None = None,
    ) -> Any:
        ...


# ---------------------------------------------------------------------------
# ContentGenerator
# ---------------------------------------------------------------------------


class ContentGenerator:
    """Plan을 Content로 변환하는 RAG 기반 생성 서비스.

    DI 패턴으로 SearchService/GenerationService를 주입받는다.
    EvidenceFilter/TemporalGuardrail은 선택적이며 None이면 건너뛴다.
    """

    def __init__(
        self,
        search_service: SearchServiceProtocol,
        generation_service: GenerationServiceProtocol,
        evidence_filter: EvidenceFilterProtocol | None = None,
        temporal_guardrail: TemporalGuardrailProtocol | None = None,
    ) -> None:
        self._search = search_service
        self._generation = generation_service
        self._evidence_filter = evidence_filter
        self._temporal_guardrail = temporal_guardrail

    # -------------------------------------------------------------------
    # Lecture
    # -------------------------------------------------------------------

    async def generate_lecture_content(self, plan: LecturePlan) -> LectureContent:
        """LecturePlan → LectureContent 생성."""
        slides: list[SlideContent] = []
        all_quote_ids: list[str] = []
        all_hits: list[SearchHit] = []
        warnings: list[str] = []

        for slide_plan in plan.slides:
            query = slide_plan.rag_query or slide_plan.title
            hits = await asyncio.to_thread(
                self._search.hybrid_search,
                query,
                edition_filter=slide_plan.edition_filter,
            )

            if not hits:
                warnings.append(
                    f"슬라이드 {slide_plan.index} '{slide_plan.title}': "
                    "검색 결과 없음 — RAG 컨텍스트 없이 생성"
                )

            all_hits.extend(hits)
            context = _format_hits_as_context(hits)
            prompt = _build_slide_prompt(slide_plan)

            result = await asyncio.to_thread(
                self._generation.generate,
                query=prompt,
                context=context,
                intent="content_studio",
            )

            hit_quote_ids = tuple(h.quote_id for h in hits)
            all_quote_ids.extend(hit_quote_ids)

            slide_content = SlideContent(
                index=slide_plan.index,
                title=slide_plan.title,
                body_text=_sanitize_llm_output(result.answer),
                key_points=slide_plan.key_points,
                quote_ids=hit_quote_ids,
                speaker_notes=slide_plan.speaker_notes or "",
            )
            slides.append(slide_content)

        # Quality checks
        warnings.extend(await self._run_quality_checks(all_hits, all_quote_ids))

        unique_citations = tuple(dict.fromkeys(all_quote_ids))
        return LectureContent(
            slides=tuple(slides),
            citations=unique_citations,
            warnings=tuple(warnings),
        )

    # -------------------------------------------------------------------
    # Card News
    # -------------------------------------------------------------------

    async def generate_card_news_content(self, plan: CardNewsPlan) -> CardNewsContent:
        """CardNewsPlan → CardNewsContent 생성 (JSON 파싱 방식)."""
        cards: list[CardContent] = []
        all_quote_ids: list[str] = []
        all_hits: list[SearchHit] = []
        warnings: list[str] = []

        for card_plan in plan.cards:
            query = card_plan.headline
            hits = await asyncio.to_thread(self._search.hybrid_search, query)

            if not hits:
                warnings.append(
                    f"카드 {card_plan.index} '{card_plan.headline}': "
                    "검색 결과 없음 — RAG 컨텍스트 없이 생성"
                )

            all_hits.extend(hits)
            context = _format_hits_as_context(hits)
            prompt = _build_card_prompt(card_plan)

            result = await asyncio.to_thread(
                self._generation.generate,
                query=prompt,
                context=context,
                intent="content_studio_card",
            )

            hit_quote_ids = tuple(h.quote_id for h in hits)
            all_quote_ids.extend(hit_quote_ids)

            # JSON 파싱 시도 → 실패 시 prose fallback
            body, source_quote, source_edition = _parse_card_json(result.answer)

            card_content = CardContent(
                index=card_plan.index,
                headline=card_plan.headline,
                body=body,
                quote_ids=hit_quote_ids,
                source_quote=source_quote,
                source_edition=source_edition,
            )
            cards.append(card_content)

        warnings.extend(await self._run_quality_checks(all_hits, all_quote_ids))

        unique_citations = tuple(dict.fromkeys(all_quote_ids))
        return CardNewsContent(
            cards=tuple(cards),
            citations=unique_citations,
            warnings=tuple(warnings),
        )

    # -------------------------------------------------------------------
    # Workshop
    # -------------------------------------------------------------------

    async def generate_workshop_content(self, plan: WorkshopPlan) -> WorkshopContent:
        """WorkshopPlan → WorkshopContent 생성."""
        phases: list[PhaseContent] = []
        all_quote_ids: list[str] = []
        all_hits: list[SearchHit] = []
        warnings: list[str] = []

        for phase_plan in plan.phases:
            query = phase_plan.rag_query or phase_plan.title
            hits = await asyncio.to_thread(self._search.hybrid_search, query)

            if not hits:
                warnings.append(
                    f"워크숍 단계 '{phase_plan.title}': " "검색 결과 없음 — RAG 컨텍스트 없이 생성"
                )

            all_hits.extend(hits)
            context = _format_hits_as_context(hits)
            prompt = _build_workshop_prompt(phase_plan)

            result = await asyncio.to_thread(
                self._generation.generate,
                query=prompt,
                context=context,
                intent="content_studio",
            )

            hit_quote_ids = tuple(h.quote_id for h in hits)
            all_quote_ids.extend(hit_quote_ids)

            phase_content = PhaseContent(
                phase_type=phase_plan.phase_type,
                title=phase_plan.title,
                content_text=_sanitize_llm_output(result.answer),
                quote_ids=hit_quote_ids,
            )
            phases.append(phase_content)

        warnings.extend(await self._run_quality_checks(all_hits, all_quote_ids))

        unique_citations = tuple(dict.fromkeys(all_quote_ids))
        return WorkshopContent(
            phases=tuple(phases),
            citations=unique_citations,
            warnings=tuple(warnings),
        )

    # -------------------------------------------------------------------
    # Audio
    # -------------------------------------------------------------------

    async def generate_audio_content(self, plan: AudioPlan) -> AudioContent:
        """AudioPlan → AudioContent 생성."""
        sections: list[SectionContent] = []
        all_quote_ids: list[str] = []
        all_hits: list[SearchHit] = []
        warnings: list[str] = []
        total_word_count = 0

        for section_plan in plan.sections:
            query = section_plan.rag_query or section_plan.text
            hits = await asyncio.to_thread(self._search.hybrid_search, query)

            if not hits:
                warnings.append(
                    f"오디오 섹션 {section_plan.index} '{section_plan.speaker}': "
                    "검색 결과 없음 — RAG 컨텍스트 없이 생성"
                )

            all_hits.extend(hits)
            context = _format_hits_as_context(hits)
            prompt = _build_audio_prompt(section_plan, plan.style)

            result = await asyncio.to_thread(
                self._generation.generate,
                query=prompt,
                context=context,
                intent="content_studio",
            )

            hit_quote_ids = tuple(h.quote_id for h in hits)
            all_quote_ids.extend(hit_quote_ids)

            sanitized_text = _sanitize_llm_output(result.answer)
            section_content = SectionContent(
                index=section_plan.index,
                speaker=section_plan.speaker,
                text=sanitized_text,
                quote_ids=hit_quote_ids,
            )
            sections.append(section_content)
            total_word_count += _count_words(sanitized_text)

        # Duration warning
        estimated_min = total_word_count / _WORDS_PER_MINUTE_KO
        if estimated_min > plan.total_duration_min * 1.2:
            warnings.append(
                f"예상 분량({estimated_min:.1f}분)이 목표({plan.total_duration_min}분)를 "
                "20% 이상 초과합니다"
            )

        warnings.extend(await self._run_quality_checks(all_hits, all_quote_ids))

        unique_citations = tuple(dict.fromkeys(all_quote_ids))
        return AudioContent(
            sections=tuple(sections),
            citations=unique_citations,
            total_word_count=total_word_count,
            warnings=tuple(warnings),
        )

    # -------------------------------------------------------------------
    # Quality checks (evidence filter + temporal guardrail)
    # -------------------------------------------------------------------

    async def _run_quality_checks(
        self,
        hits: list[SearchHit],
        quote_ids: list[str],
    ) -> list[str]:
        """EvidenceFilter + TemporalGuardrail 실행, 경고 목록 반환."""
        warnings: list[str] = []

        if self._evidence_filter is not None and hits:
            combined_text = " ".join(qid for qid in quote_ids)
            evidence_result = await asyncio.to_thread(
                self._evidence_filter.check, combined_text, hits
            )
            if hasattr(evidence_result, "hallucination_flags"):
                for flag in evidence_result.hallucination_flags:
                    warnings.append(f"[근거검증] {flag}")
            if hasattr(evidence_result, "passed") and not evidence_result.passed:
                warnings.append("[근거검증] 근거 커버리지 검증 미통과")

        if self._temporal_guardrail is not None and hits:
            guardrail_result = await asyncio.to_thread(
                self._temporal_guardrail.check, hits
            )
            if hasattr(guardrail_result, "warnings"):
                for tw in guardrail_result.warnings:
                    warnings.append(
                        f"[시간축] {tw.message}"
                        if hasattr(tw, "message")
                        else f"[시간축] {tw}"
                    )

        return warnings


# ---------------------------------------------------------------------------
# Internal helpers — prompt building
# ---------------------------------------------------------------------------


def _format_hits_as_context(hits: list[SearchHit]) -> str:
    """SearchHit 목록을 LLM 컨텍스트 문자열로 변환."""
    if not hits:
        return "(검색 결과 없음)"

    parts: list[str] = []
    for i, hit in enumerate(hits, start=1):
        section = " > ".join(hit.section_path) if hit.section_path else "unknown"
        part = (
            f"[CHUNK {i}]\n"
            f"quote_id: {hit.quote_id}\n"
            f"edition: {hit.edition_id}\n"
            f"section: {section}\n"
            f"type: {hit.quote_type}\n"
            f"---\n"
            f"{hit.text}\n"
        )
        parts.append(part)
    return "\n".join(parts)


def _build_slide_prompt(slide_plan: Any) -> str:
    """슬라이드 생성 프롬프트."""
    key_points_str = "\n".join(f"- {kp}" for kp in slide_plan.key_points)
    return (
        f"[작성 요청] 강의 슬라이드 본문\n\n"
        f"슬라이드 제목: {slide_plan.title}\n"
        f"레이아웃: {slide_plan.layout}\n"
        f"핵심 포인트:\n{key_points_str}\n\n"
        "제공된 컨텍스트의 SKMS 원문을 근거로 슬라이드 본문을 작성하세요.\n"
        "- 핵심 포인트 각각에 대해 2~3줄의 설명을 작성하세요.\n"
        "- 원문의 핵심 문장을 「따옴표」로 직접 인용하고 (출처: N차 개정판)을 명기하세요.\n"
        "- 명사형 종결(~함, ~임, ~필요)을 사용하세요.\n"
        "- JSON이나 코드블록 없이 순수 텍스트만 출력하세요."
    )


def _build_card_prompt(card_plan: Any) -> str:
    """카드뉴스 생성 프롬프트."""
    return (
        f"[작성 요청] 카드뉴스 본문 (전 구성원 대상)\n\n"
        f"카드 제목: {card_plan.headline}\n"
        f"본문 가이드: {card_plan.body}\n\n"
        "제공된 컨텍스트의 SKMS 원문을 근거로 카드뉴스 본문을 작성하세요.\n"
        "- 간결하고 임팩트 있는 2~3줄로 작성하세요.\n"
        "- 원문의 핵심 문장을 「따옴표」로 직접 인용하세요.\n"
        "- 명사형 종결(~함, ~임, ~것)을 사용하세요.\n"
        "- JSON이나 코드블록 없이 순수 텍스트만 출력하세요."
    )


def _build_workshop_prompt(phase_plan: Any) -> str:
    """워크숍 단계 생성 프롬프트."""
    return (
        f"[작성 요청] 워크숍 단계 콘텐츠 (리더/관리자 대상)\n\n"
        f"워크숍 단계: {phase_plan.phase_type}\n"
        f"제목: {phase_plan.title}\n"
        f"소요시간: {phase_plan.duration_min}분\n"
        f"설명: {phase_plan.description}\n\n"
        "제공된 컨텍스트의 SKMS 원문을 근거로 워크숍 단계 내용을 작성하세요.\n"
        "- 진행자 가이드: 해당 단계에서 진행자가 할 말과 행동\n"
        "- 참가자 활동: 토론 질문이나 실습 내용\n"
        "- 원문의 핵심 문장을 「따옴표」로 직접 인용하세요.\n"
        "- 명사형 종결(~함, ~임, ~필요)을 사용하세요.\n"
        "- JSON이나 코드블록 없이 순수 텍스트만 출력하세요."
    )


def _build_audio_prompt(section_plan: Any, style: str) -> str:
    """오디오 대본 생성 프롬프트."""
    return (
        f"[작성 요청] 오디오 대본 ({style} 스타일)\n\n"
        f"발화자: {section_plan.speaker}\n"
        f"대본 가이드: {section_plan.text}\n\n"
        "제공된 컨텍스트의 SKMS 원문을 근거로 오디오 대본을 작성하세요.\n"
        f"- {style} 스타일에 맞게 자연스러운 구어체로 작성하세요.\n"
        "- 원문의 핵심 문장을 인용할 때는 「따옴표」를 사용하세요.\n"
        "- 오디오이므로 ~합니다/~입니다 해요체를 사용하세요.\n"
        "- JSON이나 코드블록 없이 순수 텍스트만 출력하세요."
    )


def _parse_card_json(raw: str) -> tuple[str, str, str]:
    """LLM 카드 JSON 출력을 파싱한다.

    Returns:
        (body_text, source_quote, source_edition)
    """
    import json
    import re

    # 코드 펜스 안의 JSON 추출
    fence_match = re.search(r"```(?:json)?\s*\n?(\{.*?\})\s*```", raw, re.DOTALL)
    if fence_match:
        raw_json = fence_match.group(1)
    else:
        # 전체 텍스트에서 JSON 객체 추출
        obj_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
        raw_json = obj_match.group(0) if obj_match else ""

    if raw_json:
        try:
            data = json.loads(raw_json)
            body = data.get("body_text", "").strip()
            quote = data.get("quote", "").strip()
            source = data.get("source", "").strip()
            if body:
                return body, quote, source
        except (json.JSONDecodeError, ValueError):
            pass

    # JSON 파싱 실패 → prose fallback
    return _sanitize_llm_output(raw), "", ""


def _sanitize_llm_output(text: str) -> str:
    """LLM 출력에서 JSON/코드블록/메타 설명을 제거한다."""
    import re

    if not text:
        return text

    # 코드 펜스 블록: 내용만 추출 (```...``` → 내부 텍스트)
    text = re.sub(r"```(?:\w+)?\s*\n(.*?)```", r"\1", text, flags=re.DOTALL)
    # 남은 고아 코드 펜스 제거
    text = re.sub(r"```(?:\w+)?\s*\n?", "", text)

    # JSON 객체: 전체가 JSON이면 값 추출
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            import json

            data = json.loads(stripped)
            parts = []
            for k, v in data.items():
                if isinstance(v, str) and k not in ("type", "quiz_id", "card_id"):
                    parts.append(v)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, str):
                            parts.append(item)
            if parts:
                return "\n".join(parts)
        except (json.JSONDecodeError, ValueError):
            pass

    # 마크다운 볼드 제거: **text** → text
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)

    # 메타 설명/거부/분석 패턴 — 해당 줄 전체 제거
    refusal_patterns = [
        # "제공된 컨텍스트를 분석한 결과..." 류
        r"^.*제공(?:된|해주신) (?:SKMS |)컨텍스트.*?(?:분석|검토|확인).*$",
        # "직접적인 원문이 포함되어 있지 않습니다" 류
        r"^.*직접적인 (?:원문|내용|근거).*?(?:포함|존재|확인|찾).*$",
        # "더 많은 정보가 필요합니다" / "추가로 제공해 주시면" 류
        r"^.*(?:더 많은|추가|해당).*?(?:정보가 필요|제공해 주|제공해주).*$",
        # "컨텍스트에서 확인할 수 있는..." 분석 블록
        r"^.*컨텍스트에서 (?:확인|찾).*$",
        # "만약 해당 내용이..." 조건부 제안
        r"^.*만약.*?(?:원문|컨텍스트).*?(?:제공|포함).*$",
        # "---" 구분선
        r"^-{3,}$",
        # "**제안:**" / "**원문에 근거한..."
        r"^\*?\*?(?:제안|참고|원문에 근거한).*$",
        # "SKMS 콘텐츠 생성 원칙에 따라..." 류
        r"^.*(?:생성 원칙|작성 원칙)에 따라.*$",
        # "출처:" 단독 라인 (인용 안의 출처는 유지)
        r"^출처:.*$",
    ]
    for pattern in refusal_patterns:
        text = re.sub(pattern, "", text, flags=re.MULTILINE)

    # 빈 줄 정리 (3줄 이상 연속 → 2줄로)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _count_words(text: str) -> int:
    """텍스트의 단어 수를 추정 (한국어: 공백 기준 + 연속 한글 묶음)."""
    if not text:
        return 0
    return len(text.split())
