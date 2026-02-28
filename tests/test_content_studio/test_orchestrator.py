"""ContentStudio 오케스트레이터 테스트.

PR-047: 5단계 파이프라인 통합 테스트.
"""
from __future__ import annotations

import pytest

from scripts.lib.content_studio import ContentStudio, CONTENT_TYPE_INFO
from scripts.lib.content_studio.errors import PlanningError
from scripts.lib.content_studio.assembler import AssemblerConfig, FileAssembler
from scripts.lib.content_studio.asset_generator import AssetGenerator
from scripts.lib.content_studio.generator import (
    AudioContent,
    CardContent,
    CardNewsContent,
    ContentGenerator,
    LectureContent,
    PhaseContent,
    SectionContent,
    SlideContent,
    WorkshopContent,
)
from scripts.lib.content_studio.models import (
    AudioPlan,
    CardNewsPlan,
    CardPlan,
    ContentOptions,
    ContentRequest,
    GeneratedAsset,
    LecturePlan,
    QuizPlan,
    QuizQuestion,
    ScriptSection,
    SlidePlan,
    VisualizationPlan,
    WorkshopPhase,
    WorkshopPlan,
)
from scripts.lib.content_studio.planner import ContentPlanner

# Mock classes imported from conftest (auto-discovered by pytest)
from tests.test_content_studio.conftest import (
    MockLLMClient,
    MockSearchHit,
    MockSearchService,
    MockGenerationResult,
    MockGenerationService,
)


# ---------------------------------------------------------------------------
# Mock Image Generator for AssetGenerator (unique to this file)
# ---------------------------------------------------------------------------


class MockImageGenerator:
    def __init__(self):
        self.call_count = 0

    async def is_available(self) -> bool:
        return True

    async def generate_image(self, prompt, width, height, style):
        self.call_count += 1
        return GeneratedAsset(
            asset_type="image",
            file_path=f"/tmp/mock-{self.call_count}.png",
            prompt_used=prompt,
            width=width,
            height=height,
        )


# ---------------------------------------------------------------------------
# TestContentStudio
# ---------------------------------------------------------------------------


class TestContentStudioInit:
    def test_empty_init(self):
        studio = ContentStudio()
        assert not studio.has_planner
        assert not studio.has_generator
        assert not studio.has_asset_generator
        assert not studio.has_assembler

    def test_with_all_services(self, tmp_path):
        llm = MockLLMClient()
        planner = ContentPlanner(llm_client=llm, config={})
        generator = ContentGenerator(
            search_service=MockSearchService(),
            generation_service=MockGenerationService(),
        )
        asset_gen = AssetGenerator(cache_dir=str(tmp_path / "cache"))
        assembler = FileAssembler(AssemblerConfig(output_dir=str(tmp_path / "out")))

        studio = ContentStudio(
            planner=planner,
            generator=generator,
            asset_generator=asset_gen,
            assembler=assembler,
        )
        assert studio.has_planner
        assert studio.has_generator
        assert studio.has_asset_generator
        assert studio.has_assembler

    def test_content_types_static(self):
        types = ContentStudio.content_types()
        assert len(types) == 6
        type_names = {t["type"] for t in types}
        assert "lecture" in type_names
        assert "card_news" in type_names
        assert "quiz" in type_names


class TestContentStudioCreate:
    def test_create_minimal(self, tmp_path):
        """최소 파라미터로 create: planner/generator 없이."""
        studio = ContentStudio.create(
            config_path=str(tmp_path / "nonexistent.yaml"),
            output_dir=str(tmp_path / "out"),
        )
        assert not studio.has_planner
        assert not studio.has_generator
        assert studio.has_asset_generator
        assert studio.has_assembler

    def test_create_with_llm(self, tmp_path):
        llm = MockLLMClient()
        studio = ContentStudio.create(
            llm_client=llm,
            config_path=str(tmp_path / "nonexistent.yaml"),
            output_dir=str(tmp_path / "out"),
        )
        assert studio.has_planner
        assert not studio.has_generator

    def test_create_with_all(self, tmp_path):
        llm = MockLLMClient()
        search = MockSearchService()
        gen = MockGenerationService()

        studio = ContentStudio.create(
            llm_client=llm,
            search_service=search,
            generation_service=gen,
            config_path=str(tmp_path / "nonexistent.yaml"),
            output_dir=str(tmp_path / "out"),
        )
        assert studio.has_planner
        assert studio.has_generator
        assert studio.has_asset_generator
        assert studio.has_assembler


class TestContentStudioGenerate:
    @pytest.mark.asyncio
    async def test_generate_lecture(self, tmp_path):
        """강의자료 전체 파이프라인."""
        llm = MockLLMClient()
        search = MockSearchService()
        gen = MockGenerationService()

        studio = ContentStudio.create(
            llm_client=llm,
            search_service=search,
            generation_service=gen,
            config_path=str(tmp_path / "nonexistent.yaml"),
            output_dir=str(tmp_path / "out"),
        )

        request = ContentRequest(
            content_type="lecture",
            topic="SUPEX 추구",
            options=ContentOptions(duration_min=30),
        )
        result = await studio.generate(request)

        assert result.content_type == "lecture"
        assert result.topic == "SUPEX 추구"
        assert len(result.files) >= 1
        meta = dict(result.metadata)
        assert "total_elapsed_ms" in meta
        assert meta["content_type"] == "lecture"

    @pytest.mark.asyncio
    async def test_generate_card_news(self, tmp_path):
        """카드뉴스 전체 파이프라인."""
        llm = MockLLMClient(
            responses={
                "카드뉴스": """{
                    "title": "VWBE 카드",
                    "total_cards": 3,
                    "cards": [
                        {"index": 1, "headline": "VWBE", "body": "설명1"},
                        {"index": 2, "headline": "실천", "body": "설명2"},
                        {"index": 3, "headline": "결과", "body": "설명3"}
                    ]
                }"""
            }
        )
        search = MockSearchService()
        gen = MockGenerationService()

        studio = ContentStudio.create(
            llm_client=llm,
            search_service=search,
            generation_service=gen,
            config_path=str(tmp_path / "nonexistent.yaml"),
            output_dir=str(tmp_path / "out"),
        )

        request = ContentRequest(
            content_type="card_news",
            topic="VWBE 문화",
            options=ContentOptions(num_items=3),
        )
        result = await studio.generate(request)

        assert result.content_type == "card_news"
        assert len(result.files) >= 1

    @pytest.mark.asyncio
    async def test_generate_workshop(self, tmp_path):
        """워크숍 전체 파이프라인."""
        llm = MockLLMClient(
            responses={
                "워크숍": """{
                    "title": "SKMS 워크숍",
                    "duration_min": 60,
                    "phases": [
                        {"phase_type": "intro", "title": "도입", "duration_min": 10},
                        {"phase_type": "main", "title": "본론", "duration_min": 30},
                        {"phase_type": "wrap_up", "title": "마무리", "duration_min": 20}
                    ]
                }"""
            }
        )
        search = MockSearchService()
        gen = MockGenerationService()

        studio = ContentStudio.create(
            llm_client=llm,
            search_service=search,
            generation_service=gen,
            config_path=str(tmp_path / "nonexistent.yaml"),
            output_dir=str(tmp_path / "out"),
        )

        request = ContentRequest(
            content_type="workshop",
            topic="SKMS 이해",
            options=ContentOptions(duration_min=60),
        )
        result = await studio.generate(request)

        assert result.content_type == "workshop"
        assert len(result.files) >= 1

    @pytest.mark.asyncio
    async def test_generate_visualization(self, tmp_path):
        """시각화 파이프라인 (generator 스킵)."""
        llm = MockLLMClient(
            responses={
                "시각화": """{
                    "title": "SUPEX 타임라인",
                    "viz_type": "timeline",
                    "data_description": "SUPEX 변천사"
                }"""
            }
        )

        studio = ContentStudio.create(
            llm_client=llm,
            config_path=str(tmp_path / "nonexistent.yaml"),
            output_dir=str(tmp_path / "out"),
        )

        request = ContentRequest(
            content_type="visualization",
            topic="SUPEX 변천",
        )
        result = await studio.generate(request)

        assert result.content_type == "visualization"
        assert len(result.files) >= 1

    @pytest.mark.asyncio
    async def test_generate_no_planner_raises(self, tmp_path):
        """Planner 없이 generate 호출 시 RuntimeError."""
        studio = ContentStudio.create(
            config_path=str(tmp_path / "nonexistent.yaml"),
            output_dir=str(tmp_path / "out"),
        )

        request = ContentRequest(content_type="lecture", topic="테스트")
        with pytest.raises(PlanningError, match="ContentPlanner"):
            await studio.generate(request)


class TestContentStudioPlanOnly:
    @pytest.mark.asyncio
    async def test_plan_only_lecture(self, tmp_path):
        """Plan only 모드: LecturePlan 반환."""
        llm = MockLLMClient()
        studio = ContentStudio.create(
            llm_client=llm,
            config_path=str(tmp_path / "nonexistent.yaml"),
            output_dir=str(tmp_path / "out"),
        )

        request = ContentRequest(
            content_type="lecture",
            topic="인간중심경영",
            options=ContentOptions(duration_min=20),
        )
        plan = await studio.plan_only(request)

        assert isinstance(plan, LecturePlan)
        assert plan.title == "테스트 강의"

    @pytest.mark.asyncio
    async def test_plan_only_no_planner_raises(self, tmp_path):
        studio = ContentStudio.create(
            config_path=str(tmp_path / "nonexistent.yaml"),
            output_dir=str(tmp_path / "out"),
        )

        request = ContentRequest(content_type="lecture", topic="테스트")
        with pytest.raises(PlanningError):
            await studio.plan_only(request)


class TestPipelineStages:
    """개별 파이프라인 스테이지 테스트."""

    @pytest.mark.asyncio
    async def test_stage_generate_no_generator(self, tmp_path):
        """Generator 없으면 None 반환."""
        studio = ContentStudio()
        plan = LecturePlan(title="t", subtitle="s", duration_min=10)
        result = await studio._stage_generate(plan, "lecture")
        assert result is None

    @pytest.mark.asyncio
    async def test_stage_assets_no_asset_gen(self):
        """AssetGenerator 없으면 빈 리스트."""
        studio = ContentStudio()
        plan = LecturePlan(title="t", subtitle="s", duration_min=10)
        result = await studio._stage_assets(plan)
        assert result == []

    def test_stage_assemble_no_assembler(self):
        """Assembler 없으면 빈 리스트."""
        studio = ContentStudio()
        result = studio._stage_assemble("lecture", None, [], "topic")
        assert result == []

    @pytest.mark.asyncio
    async def test_stage_generate_visualization_skip(self, tmp_path):
        """visualization은 generate 스킵."""
        gen = ContentGenerator(
            search_service=MockSearchService(),
            generation_service=MockGenerationService(),
        )
        studio = ContentStudio(generator=gen)
        plan = VisualizationPlan(title="t", viz_type="timeline")
        result = await studio._stage_generate(plan, "visualization")
        assert result is None

    @pytest.mark.asyncio
    async def test_stage_generate_quiz_skip(self, tmp_path):
        """quiz는 generate 스킵."""
        gen = ContentGenerator(
            search_service=MockSearchService(),
            generation_service=MockGenerationService(),
        )
        studio = ContentStudio(generator=gen)
        plan = QuizPlan(title="t", total_questions=5)
        result = await studio._stage_generate(plan, "quiz")
        assert result is None


class TestContentTypeInfo:
    def test_all_types_present(self):
        types = CONTENT_TYPE_INFO
        type_set = {t["type"] for t in types}
        expected = {
            "lecture",
            "card_news",
            "workshop",
            "visualization",
            "audio",
            "quiz",
        }
        assert type_set == expected

    def test_each_type_has_required_fields(self):
        for info in CONTENT_TYPE_INFO:
            assert "type" in info
            assert "label" in info
            assert "description" in info
            assert "output_formats" in info


class TestElapsedMs:
    def test_elapsed_positive(self):
        import time

        from scripts.lib.content_studio import _elapsed_ms

        start = time.time()
        ms = _elapsed_ms(start)
        assert ms >= 0


class TestExtractCitations:
    def test_none_content(self):
        from scripts.lib.content_studio import _extract_citations

        assert _extract_citations(None) == []

    def test_with_citations(self):
        from scripts.lib.content_studio import _extract_citations

        content = LectureContent(
            slides=(),
            citations=("q-001", "q-002"),
        )
        assert _extract_citations(content) == ["q-001", "q-002"]

    def test_no_citations_attr(self):
        from scripts.lib.content_studio import _extract_citations

        assert _extract_citations("string_without_citations") == []
