"""ContentGenerator 테스트.

PR-044: ContentGenerator — outline to content generation using RAG.
Mock SearchService/GenerationService로 각 콘텐츠 유형 생성을 테스트.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from src.content_studio.generator import (
    AudioContent,
    CardContent,
    CardNewsContent,
    ContentGenerator,
    LectureContent,
    PhaseContent,
    SectionContent,
    SlideContent,
    WorkshopContent,
    _count_words,
    _format_hits_as_context,
)
from src.content_studio.models import (
    AudioPlan,
    CardNewsPlan,
    CardPlan,
    LecturePlan,
    ScriptSection,
    SlidePlan,
    WorkshopPhase,
    WorkshopPlan,
)
from scripts.lib.search_types import SearchHit


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_hit(
    quote_id: str = "2020-14차|경영|definition|001",
    text: str = "SKMS는 SK의 경영철학이다.",
    score: float = 0.9,
    edition_id: str = "2020-14차",
    year: int = 2020,
    revision_num: int = 14,
    quote_type: str = "definition",
) -> SearchHit:
    return SearchHit(
        quote_id=quote_id,
        text=text,
        score=score,
        edition_id=edition_id,
        year=year,
        revision_num=revision_num,
        quote_type=quote_type,
        section_path=("경영", "철학"),
        source="hybrid",
        content_hash="abc123",
        quality_flags=(),
    )


@dataclass
class MockGenerationResult:
    answer: str
    prompt_name: str = "content_gen.md"
    validation_passed: bool | None = None
    validation_errors: tuple[str, ...] = ()
    retried: bool = False
    context_token_estimate: int = 100


class MockSearchService:
    """Mock SearchService — returns pre-defined hits."""

    def __init__(self, hits: list[SearchHit] | None = None) -> None:
        self._hits = hits if hits is not None else [_make_hit()]
        self.call_count = 0
        self.last_query: str | None = None
        self.last_edition_filter: str | None = None

    def hybrid_search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        edition_filter: str | None = None,
    ) -> list[SearchHit]:
        self.call_count += 1
        self.last_query = query
        self.last_edition_filter = edition_filter
        return list(self._hits)


class MockGenerationService:
    """Mock GenerationService — returns pre-defined text."""

    def __init__(self, answer: str = "생성된 콘텐츠입니다.") -> None:
        self._answer = answer
        self.call_count = 0
        self.last_query: str | None = None

    def generate(
        self,
        query: str,
        context: str,
        intent: str,
        output_type: str | None = None,
    ) -> MockGenerationResult:
        self.call_count += 1
        self.last_query = query
        return MockGenerationResult(answer=self._answer)


@dataclass(frozen=True)
class MockEvidenceResult:
    coverage_score: float = 0.8
    cited_quote_ids: tuple[str, ...] = ()
    valid_quote_ids: tuple[str, ...] = ()
    invalid_quote_ids: tuple[str, ...] = ()
    cited_editions: tuple[str, ...] = ()
    unsupported_editions: tuple[str, ...] = ()
    hallucination_flags: tuple[str, ...] = ()
    passed: bool = True


class MockEvidenceFilter:
    """Mock EvidenceFilter."""

    def __init__(self, result: MockEvidenceResult | None = None) -> None:
        self._result = result or MockEvidenceResult()
        self.call_count = 0

    def check(self, answer: str, hits: list[SearchHit]) -> MockEvidenceResult:
        self.call_count += 1
        return self._result


@dataclass(frozen=True)
class MockTemporalWarning:
    rule_id: str = "TC-001"
    severity: str = "high"
    concept: str = "경영철학"
    message: str = "시간축 충돌 감지"
    editions: tuple[str, ...] = ()


@dataclass(frozen=True)
class MockGuardrailResult:
    has_conflict: bool = False
    warnings: tuple[MockTemporalWarning, ...] = ()
    edition_count: int = 1
    definition_count: int = 0


class MockTemporalGuardrail:
    """Mock TemporalGuardrail."""

    def __init__(self, result: MockGuardrailResult | None = None) -> None:
        self._result = result or MockGuardrailResult()
        self.call_count = 0

    def check(
        self,
        hits: list[SearchHit],
        *,
        query: str = "",
        edition_hint: str | None = None,
    ) -> MockGuardrailResult:
        self.call_count += 1
        return self._result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_lecture_plan(num_slides: int = 2) -> LecturePlan:
    slides = tuple(
        SlidePlan(
            index=i + 1,
            title=f"슬라이드 {i + 1}",
            layout="title_content",
            key_points=(f"포인트 {i + 1}-1", f"포인트 {i + 1}-2"),
            rag_query=f"SKMS 경영철학 슬라이드 {i + 1}",
            edition_filter="2020-14차" if i == 0 else None,
            speaker_notes=f"발표자 노트 {i + 1}",
        )
        for i in range(num_slides)
    )
    return LecturePlan(
        title="SKMS 경영철학 강의",
        subtitle="기본 개념",
        duration_min=30,
        slides=slides,
        learning_objectives=("SKMS 이해", "경영철학 적용"),
    )


def _make_card_news_plan(num_cards: int = 3) -> CardNewsPlan:
    cards = tuple(
        CardPlan(
            index=i + 1,
            headline=f"카드 헤드라인 {i + 1}",
            body=f"카드 본문 가이드 {i + 1}",
        )
        for i in range(num_cards)
    )
    return CardNewsPlan(
        title="SKMS 카드뉴스",
        total_cards=num_cards,
        cards=cards,
    )


def _make_workshop_plan(num_phases: int = 2) -> WorkshopPlan:
    phase_types = ["intro", "main", "activity", "wrap_up"]
    phases = tuple(
        WorkshopPhase(
            phase_type=phase_types[i % len(phase_types)],
            title=f"워크숍 단계 {i + 1}",
            duration_min=15,
            description=f"단계 {i + 1} 설명",
            rag_query=f"SKMS 워크숍 {i + 1}",
        )
        for i in range(num_phases)
    )
    return WorkshopPlan(
        title="SKMS 워크숍",
        duration_min=60,
        target_audience="신입사원",
        phases=phases,
    )


def _make_audio_plan(num_sections: int = 2) -> AudioPlan:
    sections = tuple(
        ScriptSection(
            index=i + 1,
            speaker="narrator" if i % 2 == 0 else "expert",
            text=f"오디오 대본 {i + 1}",
            rag_query=f"SKMS 오디오 {i + 1}",
        )
        for i in range(num_sections)
    )
    return AudioPlan(
        title="SKMS 오디오 콘텐츠",
        style="narration",
        total_duration_min=10,
        sections=sections,
    )


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestContentDataclasses:
    """Content 데이터클래스 불변성 + 기본값 테스트."""

    def test_slide_content_frozen(self) -> None:
        sc = SlideContent(
            index=1,
            title="제목",
            body_text="본문",
            key_points=("a", "b"),
            quote_ids=("q1",),
        )
        assert sc.index == 1
        assert sc.speaker_notes == ""
        with pytest.raises(AttributeError):
            sc.title = "변경"  # type: ignore[misc]

    def test_lecture_content_defaults(self) -> None:
        lc = LectureContent(slides=(), citations=())
        assert lc.warnings == ()

    def test_card_content_frozen(self) -> None:
        cc = CardContent(index=1, headline="제목", body="본문", quote_ids=("q1",))
        assert cc.index == 1
        with pytest.raises(AttributeError):
            cc.body = "변경"  # type: ignore[misc]

    def test_card_news_content_defaults(self) -> None:
        cnc = CardNewsContent(cards=(), citations=())
        assert cnc.warnings == ()

    def test_phase_content_frozen(self) -> None:
        pc = PhaseContent(
            phase_type="intro",
            title="제목",
            content_text="내용",
            quote_ids=("q1",),
        )
        assert pc.phase_type == "intro"

    def test_workshop_content_defaults(self) -> None:
        wc = WorkshopContent(phases=(), citations=())
        assert wc.quiz_questions == ()
        assert wc.warnings == ()

    def test_section_content_frozen(self) -> None:
        sc = SectionContent(index=1, speaker="narrator", text="대본", quote_ids=())
        assert sc.speaker == "narrator"

    def test_audio_content_defaults(self) -> None:
        ac = AudioContent(sections=(), citations=())
        assert ac.total_word_count == 0
        assert ac.warnings == ()


# ---------------------------------------------------------------------------
# Lecture generation tests
# ---------------------------------------------------------------------------


class TestGenerateLectureContent:
    """generate_lecture_content 테스트."""

    @pytest.mark.asyncio
    async def test_basic_lecture_generation(self) -> None:
        search = MockSearchService()
        gen = MockGenerationService(answer="SKMS의 핵심 경영철학입니다.")
        generator = ContentGenerator(search, gen)

        plan = _make_lecture_plan(num_slides=2)
        result = await generator.generate_lecture_content(plan)

        assert isinstance(result, LectureContent)
        assert len(result.slides) == 2
        assert search.call_count == 2
        assert gen.call_count == 2

    @pytest.mark.asyncio
    async def test_lecture_slide_content_fields(self) -> None:
        search = MockSearchService()
        gen = MockGenerationService(answer="생성된 본문")
        generator = ContentGenerator(search, gen)

        plan = _make_lecture_plan(num_slides=1)
        result = await generator.generate_lecture_content(plan)

        slide = result.slides[0]
        assert slide.index == 1
        assert slide.title == "슬라이드 1"
        assert slide.body_text == "생성된 본문"
        assert slide.key_points == ("포인트 1-1", "포인트 1-2")
        assert slide.speaker_notes == "발표자 노트 1"
        assert len(slide.quote_ids) > 0

    @pytest.mark.asyncio
    async def test_lecture_citations_deduplicated(self) -> None:
        hit = _make_hit(quote_id="same-id")
        search = MockSearchService(hits=[hit])
        gen = MockGenerationService()
        generator = ContentGenerator(search, gen)

        plan = _make_lecture_plan(num_slides=3)
        result = await generator.generate_lecture_content(plan)

        assert result.citations == ("same-id",)

    @pytest.mark.asyncio
    async def test_lecture_edition_filter_passed(self) -> None:
        search = MockSearchService()
        gen = MockGenerationService()
        generator = ContentGenerator(search, gen)

        plan = _make_lecture_plan(num_slides=1)
        await generator.generate_lecture_content(plan)

        assert search.last_edition_filter == "2020-14차"

    @pytest.mark.asyncio
    async def test_lecture_empty_search_results_warning(self) -> None:
        search = MockSearchService(hits=[])
        gen = MockGenerationService()
        generator = ContentGenerator(search, gen)

        plan = _make_lecture_plan(num_slides=1)
        result = await generator.generate_lecture_content(plan)

        assert len(result.slides) == 1
        assert any("검색 결과 없음" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Card News generation tests
# ---------------------------------------------------------------------------


class TestGenerateCardNewsContent:
    """generate_card_news_content 테스트."""

    @pytest.mark.asyncio
    async def test_basic_card_news_generation(self) -> None:
        search = MockSearchService()
        gen = MockGenerationService(answer="카드 본문입니다.")
        generator = ContentGenerator(search, gen)

        plan = _make_card_news_plan(num_cards=3)
        result = await generator.generate_card_news_content(plan)

        assert isinstance(result, CardNewsContent)
        assert len(result.cards) == 3
        assert search.call_count == 3
        assert gen.call_count == 3

    @pytest.mark.asyncio
    async def test_card_content_fields(self) -> None:
        search = MockSearchService()
        gen = MockGenerationService(answer="카드 내용")
        generator = ContentGenerator(search, gen)

        plan = _make_card_news_plan(num_cards=1)
        result = await generator.generate_card_news_content(plan)

        card = result.cards[0]
        assert card.index == 1
        assert card.headline == "카드 헤드라인 1"
        assert card.body == "카드 내용"
        assert len(card.quote_ids) > 0

    @pytest.mark.asyncio
    async def test_card_news_empty_search_warning(self) -> None:
        search = MockSearchService(hits=[])
        gen = MockGenerationService()
        generator = ContentGenerator(search, gen)

        plan = _make_card_news_plan(num_cards=1)
        result = await generator.generate_card_news_content(plan)

        assert len(result.cards) == 1
        assert any("검색 결과 없음" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_card_news_uses_headline_as_query(self) -> None:
        search = MockSearchService()
        gen = MockGenerationService()
        generator = ContentGenerator(search, gen)

        plan = _make_card_news_plan(num_cards=1)
        await generator.generate_card_news_content(plan)

        assert search.last_query == "카드 헤드라인 1"


# ---------------------------------------------------------------------------
# Workshop generation tests
# ---------------------------------------------------------------------------


class TestGenerateWorkshopContent:
    """generate_workshop_content 테스트."""

    @pytest.mark.asyncio
    async def test_basic_workshop_generation(self) -> None:
        search = MockSearchService()
        gen = MockGenerationService(answer="워크숍 내용입니다.")
        generator = ContentGenerator(search, gen)

        plan = _make_workshop_plan(num_phases=2)
        result = await generator.generate_workshop_content(plan)

        assert isinstance(result, WorkshopContent)
        assert len(result.phases) == 2
        assert search.call_count == 2

    @pytest.mark.asyncio
    async def test_workshop_phase_fields(self) -> None:
        search = MockSearchService()
        gen = MockGenerationService(answer="단계 콘텐츠")
        generator = ContentGenerator(search, gen)

        plan = _make_workshop_plan(num_phases=1)
        result = await generator.generate_workshop_content(plan)

        phase = result.phases[0]
        assert phase.phase_type == "intro"
        assert phase.title == "워크숍 단계 1"
        assert phase.content_text == "단계 콘텐츠"
        assert len(phase.quote_ids) > 0

    @pytest.mark.asyncio
    async def test_workshop_uses_rag_query(self) -> None:
        search = MockSearchService()
        gen = MockGenerationService()
        generator = ContentGenerator(search, gen)

        plan = _make_workshop_plan(num_phases=1)
        await generator.generate_workshop_content(plan)

        assert search.last_query == "SKMS 워크숍 1"

    @pytest.mark.asyncio
    async def test_workshop_empty_search_warning(self) -> None:
        search = MockSearchService(hits=[])
        gen = MockGenerationService()
        generator = ContentGenerator(search, gen)

        plan = _make_workshop_plan(num_phases=1)
        result = await generator.generate_workshop_content(plan)

        assert any("검색 결과 없음" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Audio generation tests
# ---------------------------------------------------------------------------


class TestGenerateAudioContent:
    """generate_audio_content 테스트."""

    @pytest.mark.asyncio
    async def test_basic_audio_generation(self) -> None:
        search = MockSearchService()
        gen = MockGenerationService(answer="오디오 대본입니다.")
        generator = ContentGenerator(search, gen)

        plan = _make_audio_plan(num_sections=2)
        result = await generator.generate_audio_content(plan)

        assert isinstance(result, AudioContent)
        assert len(result.sections) == 2
        assert search.call_count == 2

    @pytest.mark.asyncio
    async def test_audio_section_fields(self) -> None:
        search = MockSearchService()
        gen = MockGenerationService(answer="대본 텍스트")
        generator = ContentGenerator(search, gen)

        plan = _make_audio_plan(num_sections=1)
        result = await generator.generate_audio_content(plan)

        section = result.sections[0]
        assert section.index == 1
        assert section.speaker == "narrator"
        assert section.text == "대본 텍스트"

    @pytest.mark.asyncio
    async def test_audio_word_count(self) -> None:
        search = MockSearchService()
        gen = MockGenerationService(answer="하나 둘 셋 넷 다섯")
        generator = ContentGenerator(search, gen)

        plan = _make_audio_plan(num_sections=2)
        result = await generator.generate_audio_content(plan)

        assert result.total_word_count == 10  # 5 words * 2 sections

    @pytest.mark.asyncio
    async def test_audio_duration_overflow_warning(self) -> None:
        long_text = " ".join(["단어"] * 2000)
        search = MockSearchService()
        gen = MockGenerationService(answer=long_text)
        generator = ContentGenerator(search, gen)

        plan = _make_audio_plan(num_sections=2)
        result = await generator.generate_audio_content(plan)

        assert any("초과" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_audio_empty_search_warning(self) -> None:
        search = MockSearchService(hits=[])
        gen = MockGenerationService()
        generator = ContentGenerator(search, gen)

        plan = _make_audio_plan(num_sections=1)
        result = await generator.generate_audio_content(plan)

        assert any("검색 결과 없음" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Evidence filter integration tests
# ---------------------------------------------------------------------------


class TestEvidenceFilterIntegration:
    """EvidenceFilter 통합 테스트."""

    @pytest.mark.asyncio
    async def test_evidence_filter_called(self) -> None:
        search = MockSearchService()
        gen = MockGenerationService()
        ef = MockEvidenceFilter()
        generator = ContentGenerator(search, gen, evidence_filter=ef)

        plan = _make_lecture_plan(num_slides=1)
        await generator.generate_lecture_content(plan)

        assert ef.call_count == 1

    @pytest.mark.asyncio
    async def test_evidence_filter_hallucination_flags_in_warnings(self) -> None:
        search = MockSearchService()
        gen = MockGenerationService()
        ef = MockEvidenceFilter(
            result=MockEvidenceResult(
                hallucination_flags=("일반론 주장", "구체적 날짜"),
                passed=True,
            )
        )
        generator = ContentGenerator(search, gen, evidence_filter=ef)

        plan = _make_lecture_plan(num_slides=1)
        result = await generator.generate_lecture_content(plan)

        assert any("일반론 주장" in w for w in result.warnings)
        assert any("구체적 날짜" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_evidence_filter_failed_warning(self) -> None:
        search = MockSearchService()
        gen = MockGenerationService()
        ef = MockEvidenceFilter(result=MockEvidenceResult(passed=False))
        generator = ContentGenerator(search, gen, evidence_filter=ef)

        plan = _make_lecture_plan(num_slides=1)
        result = await generator.generate_lecture_content(plan)

        assert any("커버리지 검증 미통과" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_evidence_filter_not_called_when_no_hits(self) -> None:
        search = MockSearchService(hits=[])
        gen = MockGenerationService()
        ef = MockEvidenceFilter()
        generator = ContentGenerator(search, gen, evidence_filter=ef)

        plan = _make_lecture_plan(num_slides=1)
        await generator.generate_lecture_content(plan)

        assert ef.call_count == 0


# ---------------------------------------------------------------------------
# Temporal guardrail integration tests
# ---------------------------------------------------------------------------


class TestTemporalGuardrailIntegration:
    """TemporalGuardrail 통합 테스트."""

    @pytest.mark.asyncio
    async def test_guardrail_called(self) -> None:
        search = MockSearchService()
        gen = MockGenerationService()
        tg = MockTemporalGuardrail()
        generator = ContentGenerator(search, gen, temporal_guardrail=tg)

        plan = _make_lecture_plan(num_slides=1)
        await generator.generate_lecture_content(plan)

        assert tg.call_count == 1

    @pytest.mark.asyncio
    async def test_guardrail_warnings_in_result(self) -> None:
        search = MockSearchService()
        gen = MockGenerationService()
        tg = MockTemporalGuardrail(
            result=MockGuardrailResult(
                has_conflict=True,
                warnings=(MockTemporalWarning(message="시간축 충돌 감지"),),
            )
        )
        generator = ContentGenerator(search, gen, temporal_guardrail=tg)

        plan = _make_lecture_plan(num_slides=1)
        result = await generator.generate_lecture_content(plan)

        assert any("시간축 충돌 감지" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_guardrail_not_called_when_no_hits(self) -> None:
        search = MockSearchService(hits=[])
        gen = MockGenerationService()
        tg = MockTemporalGuardrail()
        generator = ContentGenerator(search, gen, temporal_guardrail=tg)

        plan = _make_lecture_plan(num_slides=1)
        await generator.generate_lecture_content(plan)

        assert tg.call_count == 0


# ---------------------------------------------------------------------------
# None filters tests
# ---------------------------------------------------------------------------


class TestNoneFilters:
    """EvidenceFilter/TemporalGuardrail가 None일 때 정상 동작 테스트."""

    @pytest.mark.asyncio
    async def test_no_evidence_filter(self) -> None:
        search = MockSearchService()
        gen = MockGenerationService()
        generator = ContentGenerator(search, gen)

        plan = _make_lecture_plan(num_slides=1)
        result = await generator.generate_lecture_content(plan)

        assert isinstance(result, LectureContent)
        assert not any("[근거검증]" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_no_temporal_guardrail(self) -> None:
        search = MockSearchService()
        gen = MockGenerationService()
        generator = ContentGenerator(search, gen)

        plan = _make_lecture_plan(num_slides=1)
        result = await generator.generate_lecture_content(plan)

        assert isinstance(result, LectureContent)
        assert not any("[시간축]" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_both_filters_none(self) -> None:
        search = MockSearchService()
        gen = MockGenerationService()
        generator = ContentGenerator(
            search, gen, evidence_filter=None, temporal_guardrail=None
        )

        plan = _make_card_news_plan(num_cards=2)
        result = await generator.generate_card_news_content(plan)

        assert isinstance(result, CardNewsContent)
        assert len(result.cards) == 2


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    """헬퍼 함수 테스트."""

    def test_format_hits_as_context_empty(self) -> None:
        result = _format_hits_as_context([])
        assert result == "(검색 결과 없음)"

    def test_format_hits_as_context_single(self) -> None:
        hit = _make_hit()
        result = _format_hits_as_context([hit])
        assert "[CHUNK 1]" in result
        assert hit.quote_id in result
        assert hit.text in result
        assert hit.edition_id in result

    def test_format_hits_as_context_multiple(self) -> None:
        hits = [
            _make_hit(quote_id="q1", text="첫 번째"),
            _make_hit(quote_id="q2", text="두 번째"),
        ]
        result = _format_hits_as_context(hits)
        assert "[CHUNK 1]" in result
        assert "[CHUNK 2]" in result

    def test_count_words_empty(self) -> None:
        assert _count_words("") == 0

    def test_count_words_simple(self) -> None:
        assert _count_words("하나 둘 셋") == 3

    def test_count_words_multiline(self) -> None:
        assert _count_words("하나 둘\n셋 넷") == 4


# ---------------------------------------------------------------------------
# Cross-content type tests
# ---------------------------------------------------------------------------


class TestMultipleContentTypes:
    """여러 콘텐츠 유형을 같은 generator로 생성."""

    @pytest.mark.asyncio
    async def test_same_generator_different_types(self) -> None:
        search = MockSearchService()
        gen = MockGenerationService()
        generator = ContentGenerator(search, gen)

        lecture = await generator.generate_lecture_content(
            _make_lecture_plan(num_slides=1)
        )
        card_news = await generator.generate_card_news_content(
            _make_card_news_plan(num_cards=1)
        )
        workshop = await generator.generate_workshop_content(
            _make_workshop_plan(num_phases=1)
        )
        audio = await generator.generate_audio_content(_make_audio_plan(num_sections=1))

        assert isinstance(lecture, LectureContent)
        assert isinstance(card_news, CardNewsContent)
        assert isinstance(workshop, WorkshopContent)
        assert isinstance(audio, AudioContent)
        assert search.call_count == 4
        assert gen.call_count == 4
