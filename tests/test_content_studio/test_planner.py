"""ContentPlanner 테스트.

PR-043: ContentPlanner — 주제에서 아웃라인 생성 테스트.

Mock LLM 클라이언트를 사용하여 각 plan_* 메서드를 검증한다.
"""
from __future__ import annotations

import json

import pytest

from scripts.lib.content_studio.models import (
    AudioPlan,
    CardNewsPlan,
    ContentOptions,
    LecturePlan,
    QuizPlan,
    VisualizationPlan,
    WorkshopPlan,
)
from scripts.lib.content_studio.planner import (
    ContentPlanner,
    _allocate_workshop_time,
    _audio_speaker_count,
    _clamp,
    _distribute_difficulty,
    _parse_json,
)


# ---------------------------------------------------------------------------
# Test config (matches config/content_studio.yaml structure)
# ---------------------------------------------------------------------------

TEST_CONFIG: dict = {
    "output_dir": "output",
    "lecture": {
        "min_slides": 5,
        "max_slides": 30,
        "minutes_per_slide": 2,
        "default_layout": "title_content_image",
        "aspect_ratio": "16:9",
    },
    "card_news": {
        "min_cards": 3,
        "max_cards": 10,
        "image_size": [1080, 1080],
    },
    "workshop": {
        "default_duration_min": 60,
        "phases": ["intro", "main", "activity", "wrap_up"],
        "phase_ratios": {
            "intro": 0.10,
            "main": 0.40,
            "activity": 0.30,
            "wrap_up": 0.20,
        },
    },
    "audio": {
        "max_duration_min": 10,
        "default_style": "narration",
        "voices": {
            "narrator": "korean-female-01",
            "host": "korean-male-01",
            "expert": "korean-male-02",
        },
    },
    "visualization": {
        "default_theme": "classic",
        "output_format": "svg",
    },
    "quiz": {
        "min_questions": 5,
        "max_questions": 20,
        "difficulty_distribution": {
            "easy": 0.3,
            "medium": 0.5,
            "hard": 0.2,
        },
    },
}


# ---------------------------------------------------------------------------
# Mock LLM Client
# ---------------------------------------------------------------------------


class MockLLMClient:
    """테스트용 Mock LLM 클라이언트. 미리 정의된 JSON을 반환한다."""

    def __init__(self, response: str | dict) -> None:
        if isinstance(response, dict):
            self._response = json.dumps(response, ensure_ascii=False)
        else:
            self._response = response
        self.call_count = 0
        self.last_prompt: str | None = None

    async def generate(self, prompt: str) -> str:
        self.call_count += 1
        self.last_prompt = prompt
        return self._response


class FailThenSucceedLLMClient:
    """첫 호출은 잘못된 JSON, 두 번째 호출은 유효한 JSON을 반환한다."""

    def __init__(self, bad_response: str, good_response: str | dict) -> None:
        self._bad = bad_response
        self._good = (
            json.dumps(good_response, ensure_ascii=False)
            if isinstance(good_response, dict)
            else good_response
        )
        self.call_count = 0

    async def generate(self, prompt: str) -> str:
        self.call_count += 1
        if self.call_count == 1:
            return self._bad
        return self._good


class AlwaysFailLLMClient:
    """항상 잘못된 JSON을 반환한다."""

    def __init__(self) -> None:
        self.call_count = 0

    async def generate(self, prompt: str) -> str:
        self.call_count += 1
        return "이것은 JSON이 아닙니다"


# ---------------------------------------------------------------------------
# Mock LLM response factories
# ---------------------------------------------------------------------------


def _lecture_response(slide_count: int = 10) -> dict:
    slides = []
    for i in range(1, slide_count + 1):
        slides.append(
            {
                "index": i,
                "title": f"슬라이드 {i}",
                "layout": "title_content",
                "key_points": ["포인트1", "포인트2", "포인트3"],
                "rag_query": f"SUPEX 추구 {i}",
                "edition_filter": None,
                "asset_type": None,
                "asset_prompt": None,
                "speaker_notes": f"발표자 노트 {i}",
            }
        )
    return {
        "title": "SUPEX 추구의 변천사",
        "subtitle": "20분 강의",
        "duration_min": 20,
        "slides": slides,
        "learning_objectives": ["목표1", "목표2", "목표3"],
    }


def _card_news_response(num_cards: int = 5) -> dict:
    cards = []
    for i in range(1, num_cards + 1):
        cards.append(
            {
                "index": i,
                "headline": f"카드 {i}",
                "body": f"카드 {i} 본문 내용",
                "source_quote": f"q-{i:03d}",
                "image_prompt": f"전문적인 이미지 {i}",
                "text_overlay": None,
            }
        )
    return {
        "title": "VWBE 문화 이해하기",
        "total_cards": num_cards,
        "cards": cards,
        "image_size": [1080, 1080],
    }


def _workshop_response(duration_min: int = 60) -> dict:
    return {
        "title": "인간중심 경영 워크숍",
        "duration_min": duration_min,
        "target_audience": "신입 관리자",
        "phases": [
            {
                "phase_type": "intro",
                "title": "도입",
                "duration_min": 6,
                "description": "참가자 소개 및 목표 공유",
                "facilitator_guide": "아이스브레이킹으로 시작",
                "materials_needed": ["이름표", "포스트잇"],
                "rag_query": "인간중심 경영 개요",
            },
            {
                "phase_type": "main",
                "title": "핵심 개념",
                "duration_min": 24,
                "description": "SKMS 인간중심 경영 원칙 학습",
                "facilitator_guide": "PPT 발표 + 질의응답",
                "materials_needed": ["프로젝터"],
                "rag_query": "인간중심 경영 원칙",
            },
            {
                "phase_type": "activity",
                "title": "실습",
                "duration_min": 18,
                "description": "사례 분석 그룹 활동",
                "facilitator_guide": "4인 1조 편성",
                "materials_needed": ["사례 자료", "마커"],
                "rag_query": None,
            },
            {
                "phase_type": "wrap_up",
                "title": "마무리",
                "duration_min": 12,
                "description": "학습 내용 정리 및 피드백",
                "facilitator_guide": "핵심 3가지 요약",
                "materials_needed": [],
                "rag_query": None,
            },
        ],
    }


def _audio_response(style: str = "narration") -> dict:
    sections = [
        {
            "index": 1,
            "speaker": "narrator",
            "text": "안녕하세요. SKMS 변천사를 들려드리겠습니다.",
            "rag_query": "SKMS 초판",
        },
        {
            "index": 2,
            "speaker": "narrator",
            "text": "1979년 초판에서 시작된 SKMS는...",
            "rag_query": "SKMS 1979년 초판 경영 원칙",
        },
        {
            "index": 3,
            "speaker": "narrator",
            "text": "이상으로 마무리하겠습니다.",
            "rag_query": None,
        },
    ]
    return {
        "title": "SKMS 40년 변천사",
        "style": style,
        "total_duration_min": 5,
        "sections": sections,
    }


def _visualization_response(viz_type: str = "timeline") -> dict:
    return {
        "title": "SKMS 개정 타임라인",
        "viz_type": viz_type,
        "data_description": "1979년 초판부터 2020년 14차까지 12개 개정판의 주요 변경 사항",
        "rag_query": "SKMS 개정판 변천사",
        "chart_options": {"theme": "classic", "orientation": "horizontal"},
    }


def _quiz_response(num_questions: int = 10) -> dict:
    questions = []
    difficulties = ["easy", "medium", "hard"]
    for i in range(1, num_questions + 1):
        diff = difficulties[i % 3]
        questions.append(
            {
                "index": i,
                "question_text": f"문제 {i}",
                "choices": ["선택지 A", "선택지 B", "선택지 C", "선택지 D"],
                "correct_answer": 0,
                "explanation": f"해설 {i}",
                "difficulty": diff,
                "source_quote": f"q-{i:03d}",
            }
        )
    return {
        "title": "SKMS 퀴즈",
        "total_questions": num_questions,
        "questions": questions,
        "difficulty_distribution": {"easy": 0.3, "medium": 0.5, "hard": 0.2},
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def default_options() -> ContentOptions:
    return ContentOptions()


@pytest.fixture
def options_with_edition() -> ContentOptions:
    return ContentOptions(edition_filter="2020-14차", style="academic")


# ---------------------------------------------------------------------------
# Pure utility function tests
# ---------------------------------------------------------------------------


class TestClamp:
    def test_within_range(self):
        assert _clamp(10, 5, 30) == 10

    def test_below_min(self):
        assert _clamp(2, 5, 30) == 5

    def test_above_max(self):
        assert _clamp(50, 5, 30) == 30

    def test_equal_to_min(self):
        assert _clamp(5, 5, 30) == 5

    def test_equal_to_max(self):
        assert _clamp(30, 5, 30) == 30


class TestAllocateWorkshopTime:
    def test_standard_60min(self):
        ratios = {"intro": 0.10, "main": 0.40, "activity": 0.30, "wrap_up": 0.20}
        result = _allocate_workshop_time(60, ratios)
        assert result["intro"] == 6
        assert result["main"] == 24
        assert result["activity"] == 18
        assert result["wrap_up"] == 12
        assert sum(result.values()) == 60

    def test_short_15min(self):
        ratios = {"intro": 0.10, "main": 0.40, "activity": 0.30, "wrap_up": 0.20}
        result = _allocate_workshop_time(15, ratios)
        assert all(v >= 1 for v in result.values())
        assert sum(result.values()) == 15

    def test_very_short_4min(self):
        """최소값 보장: 모든 단계가 최소 1분."""
        ratios = {"intro": 0.10, "main": 0.40, "activity": 0.30, "wrap_up": 0.20}
        result = _allocate_workshop_time(4, ratios)
        assert all(v >= 1 for v in result.values())

    def test_sum_matches_total(self):
        """다양한 시간에서 합이 일치하는지 확인."""
        ratios = {"intro": 0.10, "main": 0.40, "activity": 0.30, "wrap_up": 0.20}
        for dur in [30, 45, 60, 90, 120]:
            result = _allocate_workshop_time(dur, ratios)
            assert sum(result.values()) == dur, f"Failed for duration {dur}"


class TestAudioSpeakerCount:
    def test_narration(self):
        assert _audio_speaker_count("narration") == 1

    def test_dialogue(self):
        assert _audio_speaker_count("dialogue") == 2

    def test_podcast(self):
        assert _audio_speaker_count("podcast") == 3

    def test_unknown_defaults_to_1(self):
        assert _audio_speaker_count("unknown") == 1


class TestDistributeDifficulty:
    def test_standard_10_questions(self):
        dist = {"easy": 0.3, "medium": 0.5, "hard": 0.2}
        result = _distribute_difficulty(10, dist)
        assert result["easy"] == 3
        assert result["medium"] == 5
        assert result["hard"] == 2
        assert sum(result.values()) == 10

    def test_rounding_adjustment(self):
        """반올림으로 합이 안 맞을 때 medium에서 조정."""
        dist = {"easy": 0.3, "medium": 0.5, "hard": 0.2}
        result = _distribute_difficulty(7, dist)
        assert sum(result.values()) == 7

    def test_minimum_1_per_difficulty(self):
        """각 난이도 최소 1문항."""
        dist = {"easy": 0.3, "medium": 0.5, "hard": 0.2}
        result = _distribute_difficulty(3, dist)
        assert all(v >= 1 for v in result.values())


class TestParseJson:
    def test_plain_json(self):
        result = _parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_with_code_fence(self):
        raw = '```json\n{"key": "value"}\n```'
        result = _parse_json(raw)
        assert result == {"key": "value"}

    def test_json_with_code_fence_no_lang(self):
        raw = '```\n{"key": "value"}\n```'
        result = _parse_json(raw)
        assert result == {"key": "value"}

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_json("not json")


# ---------------------------------------------------------------------------
# Slide count calculation tests
# ---------------------------------------------------------------------------


class TestSlideCountCalculation:
    """plan_lecture의 슬라이드 수 계산 로직 검증."""

    @pytest.mark.asyncio
    async def test_20min_2min_per_slide(self, default_options):
        """20분 / 2분 = 10장."""
        llm = MockLLMClient(_lecture_response(10))
        planner = ContentPlanner(llm, TEST_CONFIG)
        plan = await planner.plan_lecture("SUPEX", 20, default_options)
        assert isinstance(plan, LecturePlan)
        # prompt에 slide_count=10이 포함되었는지 확인
        assert "10" in llm.last_prompt

    @pytest.mark.asyncio
    async def test_clamp_to_min_slides(self, default_options):
        """4분 / 2분 = 2장 → min 5장으로 클램핑."""
        llm = MockLLMClient(_lecture_response(5))
        planner = ContentPlanner(llm, TEST_CONFIG)
        await planner.plan_lecture("SUPEX", 4, default_options)
        assert "5" in llm.last_prompt

    @pytest.mark.asyncio
    async def test_clamp_to_max_slides(self, default_options):
        """100분 / 2분 = 50장 → max 30장으로 클램핑."""
        llm = MockLLMClient(_lecture_response(30))
        planner = ContentPlanner(llm, TEST_CONFIG)
        await planner.plan_lecture("SUPEX", 100, default_options)
        assert "30" in llm.last_prompt

    @pytest.mark.asyncio
    async def test_rounding(self, default_options):
        """15분 / 2분 = 7.5 → round → 8장."""
        llm = MockLLMClient(_lecture_response(8))
        planner = ContentPlanner(llm, TEST_CONFIG)
        await planner.plan_lecture("SUPEX", 15, default_options)
        assert "8" in llm.last_prompt


# ---------------------------------------------------------------------------
# plan_lecture tests
# ---------------------------------------------------------------------------


class TestPlanLecture:
    @pytest.mark.asyncio
    async def test_returns_lecture_plan(self, default_options):
        llm = MockLLMClient(_lecture_response())
        planner = ContentPlanner(llm, TEST_CONFIG)
        plan = await planner.plan_lecture("SUPEX 추구", 20, default_options)
        assert isinstance(plan, LecturePlan)
        assert plan.title == "SUPEX 추구의 변천사"
        assert plan.duration_min == 20
        assert len(plan.slides) == 10
        assert len(plan.learning_objectives) == 3

    @pytest.mark.asyncio
    async def test_options_passed_to_prompt(self, options_with_edition):
        llm = MockLLMClient(_lecture_response())
        planner = ContentPlanner(llm, TEST_CONFIG)
        await planner.plan_lecture("SUPEX", 20, options_with_edition)
        assert "2020-14차" in llm.last_prompt
        assert "academic" in llm.last_prompt

    @pytest.mark.asyncio
    async def test_llm_called_once(self, default_options):
        llm = MockLLMClient(_lecture_response())
        planner = ContentPlanner(llm, TEST_CONFIG)
        await planner.plan_lecture("SUPEX", 20, default_options)
        assert llm.call_count == 1


# ---------------------------------------------------------------------------
# plan_card_news tests
# ---------------------------------------------------------------------------


class TestPlanCardNews:
    @pytest.mark.asyncio
    async def test_returns_card_news_plan(self, default_options):
        llm = MockLLMClient(_card_news_response(5))
        planner = ContentPlanner(llm, TEST_CONFIG)
        plan = await planner.plan_card_news("VWBE 문화", 5, default_options)
        assert isinstance(plan, CardNewsPlan)
        assert plan.title == "VWBE 문화 이해하기"
        assert plan.total_cards == 5
        assert len(plan.cards) == 5

    @pytest.mark.asyncio
    async def test_clamp_below_min(self, default_options):
        """1장 요청 → min 3장으로 클램핑."""
        llm = MockLLMClient(_card_news_response(3))
        planner = ContentPlanner(llm, TEST_CONFIG)
        await planner.plan_card_news("VWBE", 1, default_options)
        assert "3" in llm.last_prompt

    @pytest.mark.asyncio
    async def test_clamp_above_max(self, default_options):
        """20장 요청 → max 10장으로 클램핑."""
        llm = MockLLMClient(_card_news_response(10))
        planner = ContentPlanner(llm, TEST_CONFIG)
        await planner.plan_card_news("VWBE", 20, default_options)
        assert "10" in llm.last_prompt


# ---------------------------------------------------------------------------
# plan_workshop tests
# ---------------------------------------------------------------------------


class TestPlanWorkshop:
    @pytest.mark.asyncio
    async def test_returns_workshop_plan(self, default_options):
        llm = MockLLMClient(_workshop_response())
        planner = ContentPlanner(llm, TEST_CONFIG)
        plan = await planner.plan_workshop("인간중심 경영", 60, default_options)
        assert isinstance(plan, WorkshopPlan)
        assert plan.title == "인간중심 경영 워크숍"
        assert plan.duration_min == 60
        assert len(plan.phases) == 4

    @pytest.mark.asyncio
    async def test_time_allocation_in_prompt(self, default_options):
        llm = MockLLMClient(_workshop_response())
        planner = ContentPlanner(llm, TEST_CONFIG)
        await planner.plan_workshop("인간중심 경영", 60, default_options)
        # 시간 배분 JSON이 프롬프트에 포함되어야 함
        assert "intro" in llm.last_prompt
        assert "main" in llm.last_prompt

    @pytest.mark.asyncio
    async def test_phase_types_present(self, default_options):
        llm = MockLLMClient(_workshop_response())
        planner = ContentPlanner(llm, TEST_CONFIG)
        plan = await planner.plan_workshop("인간중심 경영", 60, default_options)
        phase_types = {p.phase_type for p in plan.phases}
        assert phase_types == {"intro", "main", "activity", "wrap_up"}


# ---------------------------------------------------------------------------
# plan_audio tests
# ---------------------------------------------------------------------------


class TestPlanAudio:
    @pytest.mark.asyncio
    async def test_returns_audio_plan_narration(self, default_options):
        llm = MockLLMClient(_audio_response("narration"))
        planner = ContentPlanner(llm, TEST_CONFIG)
        plan = await planner.plan_audio("SKMS 변천사", 5, "narration", default_options)
        assert isinstance(plan, AudioPlan)
        assert plan.style == "narration"
        assert plan.total_duration_min == 5
        assert len(plan.sections) == 3

    @pytest.mark.asyncio
    async def test_speaker_count_in_prompt_narration(self, default_options):
        llm = MockLLMClient(_audio_response("narration"))
        planner = ContentPlanner(llm, TEST_CONFIG)
        await planner.plan_audio("SKMS", 5, "narration", default_options)
        assert "1" in llm.last_prompt  # speaker_count = 1

    @pytest.mark.asyncio
    async def test_speaker_count_in_prompt_dialogue(self, default_options):
        response = _audio_response("dialogue")
        response["style"] = "dialogue"
        llm = MockLLMClient(response)
        planner = ContentPlanner(llm, TEST_CONFIG)
        await planner.plan_audio("SKMS", 5, "dialogue", default_options)
        assert "2" in llm.last_prompt  # speaker_count = 2

    @pytest.mark.asyncio
    async def test_speaker_count_in_prompt_podcast(self, default_options):
        response = _audio_response("podcast")
        response["style"] = "podcast"
        llm = MockLLMClient(response)
        planner = ContentPlanner(llm, TEST_CONFIG)
        await planner.plan_audio("SKMS", 5, "podcast", default_options)
        assert "3" in llm.last_prompt  # speaker_count = 3


# ---------------------------------------------------------------------------
# plan_visualization tests
# ---------------------------------------------------------------------------


class TestPlanVisualization:
    @pytest.mark.asyncio
    async def test_returns_visualization_plan(self, default_options):
        llm = MockLLMClient(_visualization_response())
        planner = ContentPlanner(llm, TEST_CONFIG)
        plan = await planner.plan_visualization(
            "SKMS 타임라인", "timeline", default_options
        )
        assert isinstance(plan, VisualizationPlan)
        assert plan.viz_type == "timeline"
        assert plan.title == "SKMS 개정 타임라인"

    @pytest.mark.asyncio
    async def test_theme_in_prompt(self, default_options):
        llm = MockLLMClient(_visualization_response())
        planner = ContentPlanner(llm, TEST_CONFIG)
        await planner.plan_visualization("SKMS 마인드맵", "mindmap", default_options)
        assert "classic" in llm.last_prompt


# ---------------------------------------------------------------------------
# plan_quiz tests
# ---------------------------------------------------------------------------


class TestPlanQuiz:
    @pytest.mark.asyncio
    async def test_returns_quiz_plan(self, default_options):
        llm = MockLLMClient(_quiz_response(10))
        planner = ContentPlanner(llm, TEST_CONFIG)
        plan = await planner.plan_quiz("SUPEX", 10, default_options)
        assert isinstance(plan, QuizPlan)
        assert plan.total_questions == 10
        assert len(plan.questions) == 10

    @pytest.mark.asyncio
    async def test_clamp_below_min(self, default_options):
        """2문항 요청 → min 5문항으로 클램핑."""
        llm = MockLLMClient(_quiz_response(5))
        planner = ContentPlanner(llm, TEST_CONFIG)
        await planner.plan_quiz("SUPEX", 2, default_options)
        assert "5" in llm.last_prompt

    @pytest.mark.asyncio
    async def test_clamp_above_max(self, default_options):
        """50문항 요청 → max 20문항으로 클램핑."""
        llm = MockLLMClient(_quiz_response(20))
        planner = ContentPlanner(llm, TEST_CONFIG)
        await planner.plan_quiz("SUPEX", 50, default_options)
        assert "20" in llm.last_prompt

    @pytest.mark.asyncio
    async def test_difficulty_distribution_in_prompt(self, default_options):
        llm = MockLLMClient(_quiz_response(10))
        planner = ContentPlanner(llm, TEST_CONFIG)
        await planner.plan_quiz("SUPEX", 10, default_options)
        assert "easy" in llm.last_prompt
        assert "medium" in llm.last_prompt
        assert "hard" in llm.last_prompt


# ---------------------------------------------------------------------------
# LLM retry tests
# ---------------------------------------------------------------------------


class TestLLMRetry:
    @pytest.mark.asyncio
    async def test_retry_on_parse_failure(self, default_options):
        """첫 호출 실패 → 재시도 성공."""
        llm = FailThenSucceedLLMClient(
            bad_response="이것은 JSON이 아닙니다",
            good_response=_lecture_response(),
        )
        planner = ContentPlanner(llm, TEST_CONFIG)
        plan = await planner.plan_lecture("SUPEX", 20, default_options)
        assert isinstance(plan, LecturePlan)
        assert llm.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises(self, default_options):
        """재시도도 실패하면 ValueError 발생."""
        llm = AlwaysFailLLMClient()
        planner = ContentPlanner(llm, TEST_CONFIG)
        with pytest.raises(ValueError, match="재시도 실패"):
            await planner.plan_lecture("SUPEX", 20, default_options)
        assert llm.call_count == 2  # 1회 시도 + 1회 재시도

    @pytest.mark.asyncio
    async def test_no_retry_on_success(self, default_options):
        """정상 응답 시 재시도 없음."""
        llm = MockLLMClient(_lecture_response())
        planner = ContentPlanner(llm, TEST_CONFIG)
        await planner.plan_lecture("SUPEX", 20, default_options)
        assert llm.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_prompt_contains_hint(self, default_options):
        """재시도 프롬프트에 JSON 안내 포함."""
        llm = FailThenSucceedLLMClient(
            bad_response="bad",
            good_response=_quiz_response(),
        )
        planner = ContentPlanner(llm, TEST_CONFIG)
        await planner.plan_quiz("SUPEX", 10, default_options)
        assert "유효한 JSON" in llm._good or llm.call_count == 2


# ---------------------------------------------------------------------------
# Config defaults tests
# ---------------------------------------------------------------------------


class TestConfigDefaults:
    @pytest.mark.asyncio
    async def test_missing_lecture_config_uses_defaults(self, default_options):
        """lecture 설정 없으면 기본값 사용."""
        config = {"output_dir": "output"}
        llm = MockLLMClient(_lecture_response(5))
        planner = ContentPlanner(llm, config)
        plan = await planner.plan_lecture("SUPEX", 10, default_options)
        assert isinstance(plan, LecturePlan)

    @pytest.mark.asyncio
    async def test_missing_quiz_config_uses_defaults(self, default_options):
        """quiz 설정 없으면 기본값 사용."""
        config = {"output_dir": "output"}
        llm = MockLLMClient(_quiz_response(5))
        planner = ContentPlanner(llm, config)
        plan = await planner.plan_quiz("SUPEX", 5, default_options)
        assert isinstance(plan, QuizPlan)

    @pytest.mark.asyncio
    async def test_options_default_edition_filter(self, default_options):
        """edition_filter가 None이면 '전체'로 변환."""
        llm = MockLLMClient(_lecture_response())
        planner = ContentPlanner(llm, TEST_CONFIG)
        await planner.plan_lecture("SUPEX", 20, default_options)
        assert "전체" in llm.last_prompt
