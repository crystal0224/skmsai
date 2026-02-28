"""Content Studio 공유 테스트 fixture.

TD-004: 중복 테스트 헬퍼를 conftest.py로 통합.

이 파일은 tests/test_content_studio/ 하위 테스트 파일들에서 반복되는
mock 객체, 팩토리 함수, 공통 fixture를 통합 제공한다.

주요 fixture:
- mock_search_hit_factory: MockSearchHit 인스턴스 생성 팩토리
- mock_search_service: hybrid_search를 제공하는 mock 검색 서비스
- mock_generation_result_factory: MockGenerationResult 인스턴스 생성 팩토리
- mock_generation_service: generate를 제공하는 mock 생성 서비스
- mock_llm_client_factory: 키워드 기반 JSON 응답을 반환하는 mock LLM 클라이언트 팩토리
- sample_content_request: ContentRequest 생성 팩토리 fixture
- sample_lecture_plan: 테스트용 기본 LecturePlan
- sample_card_news_plan: 테스트용 기본 CardNewsPlan
- assembler_config: tmp_path 기반 AssemblerConfig
"""
from __future__ import annotations

from typing import Any

import pytest

from scripts.lib.content_studio.assembler import AssemblerConfig, FileAssembler
from scripts.lib.content_studio.asset_generator import AssetGenerator
from scripts.lib.content_studio.generator import ContentGenerator
from scripts.lib.content_studio.models import (
    CardNewsPlan,
    CardPlan,
    ContentOptions,
    ContentRequest,
    LecturePlan,
    SlidePlan,
)
from scripts.lib.content_studio.planner import ContentPlanner
from scripts.lib.content_studio import ContentStudio


# ---------------------------------------------------------------------------
# Mock classes — 3개 이상 테스트 파일에서 중복 사용된 패턴 통합
# (test_orchestrator, test_e2e, test_content_api)
# ---------------------------------------------------------------------------


class MockSearchHit:
    """테스트용 간이 검색 결과.

    SearchHit 프로토콜의 최소 구현. 여러 테스트 파일에서 동일한 형태로
    반복 정의되던 mock 클래스를 통합한 것이다.
    """

    def __init__(
        self,
        quote_id: str = "q-001",
        text: str = "SKMS 원문",
    ) -> None:
        self.quote_id = quote_id
        self.text = text
        self.edition_id = "2020-14차"
        self.year = 2020
        self.quote_type = "principle"
        self.section_path = ("1장",)
        self.quality_flags = ()


class MockGenerationResult:
    """테스트용 생성 결과.

    GenerationService.generate()의 반환값을 흉내내는 mock.
    answer, prompt_name, validation_passed 속성을 제공한다.
    """

    def __init__(self, answer: str = "생성된 콘텐츠") -> None:
        self.answer = answer
        self.prompt_name = "test"
        self.validation_passed = True


class MockSearchService:
    """테스트용 간이 검색 서비스.

    hybrid_search() 호출 시 MockSearchHit 목록을 반환한다.
    쿼리 해시 기반으로 고유한 quote_id를 생성하여 중복 제거 테스트를 지원한다.
    """

    def hybrid_search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        edition_filter: str | None = None,
    ) -> list[MockSearchHit]:
        return [MockSearchHit(quote_id=f"q-{hash(query) % 1000:03d}")]


class MockGenerationService:
    """테스트용 간이 생성 서비스.

    generate() 호출 시 MockGenerationResult를 반환한다.
    """

    def generate(
        self,
        query: str,
        context: str,
        intent: str,
        output_type: str | None = None,
    ) -> MockGenerationResult:
        return MockGenerationResult()


class MockLLMClient:
    """6개 content_type 키워드에 대응하는 JSON 응답을 반환하는 mock LLM 클라이언트.

    프롬프트 내 한글 키워드로 content_type을 판별하여 적절한
    JSON 응답을 반환한다. 추가 responses dict를 생성자에 전달하면
    키워드 매칭 시 해당 응답이 우선 사용된다.
    """

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self._responses = responses or {}
        self.call_count = 0

    async def generate(self, prompt: str) -> str:
        self.call_count += 1

        # 사용자 지정 응답이 있으면 우선 매칭
        for key, response in self._responses.items():
            if key in prompt:
                return response

        # 기본 키워드 매칭
        if "카드뉴스" in prompt:
            return _CARD_NEWS_JSON
        if "워크숍" in prompt:
            return _WORKSHOP_JSON
        if "시각화" in prompt:
            return _VISUALIZATION_JSON
        if "퀴즈" in prompt:
            return _QUIZ_JSON
        if "오디오" in prompt:
            return _AUDIO_JSON

        # Default: lecture
        return _LECTURE_JSON


# ---------------------------------------------------------------------------
# Default JSON responses for MockLLMClient
# ---------------------------------------------------------------------------

_LECTURE_JSON = """{
    "title": "테스트 강의",
    "subtitle": "서브타이틀",
    "duration_min": 30,
    "slides": [
        {"index": 1, "title": "소개", "layout": "title_only"},
        {"index": 2, "title": "본론", "layout": "title_content"}
    ],
    "learning_objectives": ["목표1"]
}"""

_CARD_NEWS_JSON = """{
    "title": "VWBE 카드",
    "total_cards": 3,
    "cards": [
        {"index": 1, "headline": "VWBE", "body": "설명1"},
        {"index": 2, "headline": "실천", "body": "설명2"},
        {"index": 3, "headline": "결과", "body": "설명3"}
    ]
}"""

_WORKSHOP_JSON = """{
    "title": "SKMS 워크숍",
    "duration_min": 60,
    "phases": [
        {"phase_type": "intro", "title": "도입", "duration_min": 10},
        {"phase_type": "main", "title": "본론", "duration_min": 30},
        {"phase_type": "wrap_up", "title": "마무리", "duration_min": 20}
    ]
}"""

_VISUALIZATION_JSON = """{
    "title": "타임라인",
    "viz_type": "timeline",
    "data_description": "SUPEX 변천사"
}"""

_QUIZ_JSON = """{
    "title": "SKMS 퀴즈",
    "total_questions": 5,
    "questions": [
        {
            "index": 1,
            "question_text": "SUPEX란?",
            "choices": ["A", "B", "C", "D"],
            "correct_answer": 0,
            "difficulty": "easy"
        }
    ]
}"""

_AUDIO_JSON = """{
    "title": "SKMS 오디오",
    "style": "dialogue",
    "total_duration_min": 5,
    "sections": [
        {"index": 1, "speaker": "host", "text": "안녕하세요"},
        {"index": 2, "speaker": "expert", "text": "SKMS란"}
    ]
}"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_search_hit_factory():
    """MockSearchHit 인스턴스를 생성하는 팩토리 fixture.

    Usage:
        hit = mock_search_hit_factory(quote_id="q-100", text="커스텀 텍스트")
    """

    def _factory(**kwargs: Any) -> MockSearchHit:
        return MockSearchHit(**kwargs)

    return _factory


@pytest.fixture
def mock_search_service() -> MockSearchService:
    """간이 검색 서비스 fixture.

    hybrid_search()를 제공하며, 쿼리별 고유 quote_id를 반환한다.
    """
    return MockSearchService()


@pytest.fixture
def mock_generation_service() -> MockGenerationService:
    """간이 생성 서비스 fixture.

    generate()를 호출하면 MockGenerationResult를 반환한다.
    """
    return MockGenerationService()


@pytest.fixture
def mock_llm_client() -> MockLLMClient:
    """키워드 기반 JSON 응답을 반환하는 mock LLM 클라이언트 fixture.

    프롬프트에 포함된 한글 키워드(강의/카드뉴스/워크숍/시각화/퀴즈/오디오)에 따라
    적절한 JSON 응답을 반환한다.
    """
    return MockLLMClient()


@pytest.fixture
def mock_llm_client_factory():
    """커스텀 응답을 설정할 수 있는 MockLLMClient 팩토리 fixture.

    Usage:
        llm = mock_llm_client_factory(responses={"키워드": '{"json": "data"}'})
    """

    def _factory(
        responses: dict[str, str] | None = None,
    ) -> MockLLMClient:
        return MockLLMClient(responses=responses)

    return _factory


@pytest.fixture
def sample_content_request():
    """ContentRequest 생성 팩토리 fixture.

    Usage:
        req = sample_content_request("lecture", "SUPEX 추구", duration_min=30)
        req = sample_content_request("card_news", "VWBE 문화", num_items=5)
    """

    def _factory(
        content_type: str = "lecture",
        topic: str = "SUPEX 추구",
        **option_kwargs: Any,
    ) -> ContentRequest:
        options = ContentOptions(**option_kwargs) if option_kwargs else ContentOptions()
        return ContentRequest(
            content_type=content_type,
            topic=topic,
            options=options,
        )

    return _factory


@pytest.fixture
def sample_lecture_plan() -> LecturePlan:
    """테스트용 기본 LecturePlan fixture.

    2개 슬라이드, 30분 강의, 학습목표 2개를 포함한 기본 계획.
    """
    slides = (
        SlidePlan(index=1, title="소개", layout="title_only"),
        SlidePlan(index=2, title="본론", layout="title_content"),
    )
    return LecturePlan(
        title="테스트 강의",
        subtitle="테스트 서브타이틀",
        duration_min=30,
        slides=slides,
        learning_objectives=("목표1", "목표2"),
    )


@pytest.fixture
def sample_card_news_plan() -> CardNewsPlan:
    """테스트용 기본 CardNewsPlan fixture.

    3개 카드를 포함한 기본 카드뉴스 계획.
    """
    cards = (
        CardPlan(index=1, headline="VWBE란", body="설명1"),
        CardPlan(index=2, headline="실천 방법", body="설명2"),
        CardPlan(index=3, headline="결과", body="설명3"),
    )
    return CardNewsPlan(
        title="VWBE 카드뉴스",
        total_cards=3,
        cards=cards,
    )


@pytest.fixture
def assembler_config(tmp_path) -> AssemblerConfig:
    """tmp_path 기반 AssemblerConfig fixture.

    임시 출력 디렉토리를 사용하는 AssemblerConfig를 반환한다.
    테스트 종료 시 자동 정리된다.
    """
    return AssemblerConfig(output_dir=str(tmp_path / "out"))


@pytest.fixture
def content_studio_full(tmp_path) -> ContentStudio:
    """모든 서비스가 활성화된 ContentStudio fixture.

    MockLLMClient, MockSearchService, MockGenerationService를 사용하여
    Planner, Generator, AssetGenerator, Assembler를 모두 갖춘 ContentStudio를 반환한다.
    """
    llm = MockLLMClient()
    search = MockSearchService()
    gen = MockGenerationService()

    return ContentStudio.create(
        llm_client=llm,
        search_service=search,
        generation_service=gen,
        config_path=str(tmp_path / "nonexistent.yaml"),
        output_dir=str(tmp_path / "out"),
    )
