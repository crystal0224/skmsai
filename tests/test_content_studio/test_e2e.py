"""Content Studio E2E 통합 테스트.

PR-049: 전체 파이프라인 E2E — mock LLM + mock MCP.
6개 콘텐츠 유형 전부를 ContentStudio.generate()로 실행하고
파일 생성, 메타데이터, 인용 등을 검증한다.
"""
from __future__ import annotations

import time

import pytest

from src.content_studio import ContentStudio
from src.content_studio.assembler import AssemblerConfig, FileAssembler
from src.content_studio.asset_generator import AssetGenerator
from src.content_studio.generator import ContentGenerator
from src.content_studio.models import (
    ContentOptions,
    ContentRequest,
    GeneratedAsset,
)
from src.content_studio.planner import ContentPlanner

# Mock classes imported from conftest (auto-discovered by pytest)
from tests.test_content_studio.conftest import (
    MockLLMClient,
    MockSearchService,
    MockGenerationService,
)


# ---------------------------------------------------------------------------
# Full pipeline fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def e2e_studio(tmp_path) -> ContentStudio:
    """모든 서비스가 활성화된 E2E ContentStudio."""
    llm = MockLLMClient()
    search = MockSearchService()
    gen = MockGenerationService()

    studio = ContentStudio.create(
        llm_client=llm,
        search_service=search,
        generation_service=gen,
        config_path=str(tmp_path / "nonexistent.yaml"),
        output_dir=str(tmp_path / "output"),
    )
    return studio


@pytest.fixture
def viz_only_studio(tmp_path) -> ContentStudio:
    """Generator 없이 Planner + Assembler만 있는 ContentStudio (viz/quiz용)."""
    llm = MockLLMClient()
    studio = ContentStudio.create(
        llm_client=llm,
        config_path=str(tmp_path / "nonexistent.yaml"),
        output_dir=str(tmp_path / "output"),
    )
    return studio


# ---------------------------------------------------------------------------
# E2E: 6개 콘텐츠 유형 전체 파이프라인
# ---------------------------------------------------------------------------


class TestE2ELecture:
    """강의자료 전체 파이프라인 E2E."""

    @pytest.mark.asyncio
    async def test_lecture_generates_files(self, e2e_studio):
        request = ContentRequest(
            content_type="lecture",
            topic="SUPEX 추구",
            options=ContentOptions(duration_min=30),
        )
        result = await e2e_studio.generate(request)

        assert result.content_type == "lecture"
        assert result.topic == "SUPEX 추구"
        assert len(result.files) >= 1
        for f in result.files:
            assert f.size_bytes > 0

    @pytest.mark.asyncio
    async def test_lecture_metadata(self, e2e_studio):
        request = ContentRequest(
            content_type="lecture",
            topic="인간중심경영",
            options=ContentOptions(duration_min=20),
        )
        result = await e2e_studio.generate(request)
        meta = dict(result.metadata)

        assert "total_elapsed_ms" in meta
        assert meta["content_type"] == "lecture"
        assert meta["file_count"] >= 1

    @pytest.mark.asyncio
    async def test_lecture_citations(self, e2e_studio):
        request = ContentRequest(
            content_type="lecture",
            topic="합리적 경영",
        )
        result = await e2e_studio.generate(request)
        assert isinstance(result.citations, tuple)


class TestE2ECardNews:
    """카드뉴스 전체 파이프라인 E2E."""

    @pytest.mark.asyncio
    async def test_card_news_generates_3_files(self, e2e_studio):
        request = ContentRequest(
            content_type="card_news",
            topic="VWBE 문화",
            options=ContentOptions(num_items=3),
        )
        result = await e2e_studio.generate(request)

        assert result.content_type == "card_news"
        assert len(result.files) == 3
        for f in result.files:
            assert f.size_bytes > 0

    @pytest.mark.asyncio
    async def test_card_news_html_fallback(self, e2e_studio):
        """이미지 에셋 없이 HTML fallback 동작."""
        request = ContentRequest(
            content_type="card_news",
            topic="SK Manship",
            options=ContentOptions(num_items=3),
        )
        result = await e2e_studio.generate(request)
        assert all(f.file_type == "html" for f in result.files)


class TestE2EWorkshop:
    """워크숍 전체 파이프라인 E2E."""

    @pytest.mark.asyncio
    async def test_workshop_generates_file(self, e2e_studio):
        request = ContentRequest(
            content_type="workshop",
            topic="SKMS 이해",
            options=ContentOptions(duration_min=60),
        )
        result = await e2e_studio.generate(request)

        assert result.content_type == "workshop"
        assert len(result.files) >= 1
        assert result.files[0].size_bytes > 0

    @pytest.mark.asyncio
    async def test_workshop_metadata(self, e2e_studio):
        request = ContentRequest(
            content_type="workshop",
            topic="조직관리",
            options=ContentOptions(duration_min=90),
        )
        result = await e2e_studio.generate(request)
        meta = dict(result.metadata)
        assert meta["content_type"] == "workshop"


class TestE2EVisualization:
    """시각화 전체 파이프라인 E2E."""

    @pytest.mark.asyncio
    async def test_visualization_generates_file(self, viz_only_studio):
        request = ContentRequest(
            content_type="visualization",
            topic="SUPEX 변천",
        )
        result = await viz_only_studio.generate(request)

        assert result.content_type == "visualization"
        assert len(result.files) >= 1
        assert result.files[0].size_bytes > 0

    @pytest.mark.asyncio
    async def test_visualization_html_fallback(self, viz_only_studio):
        """차트 에셋 없이 HTML fallback."""
        request = ContentRequest(
            content_type="visualization",
            topic="경영요소 관계도",
        )
        result = await viz_only_studio.generate(request)
        assert result.files[0].file_type == "html"


class TestE2EAudio:
    """오디오 전체 파이프라인 E2E."""

    @pytest.mark.asyncio
    async def test_audio_generates_script(self, e2e_studio):
        request = ContentRequest(
            content_type="audio",
            topic="SKMS 이야기",
            options=ContentOptions(duration_min=5),
        )
        result = await e2e_studio.generate(request)

        assert result.content_type == "audio"
        assert len(result.files) >= 1
        assert result.files[0].size_bytes > 0

    @pytest.mark.asyncio
    async def test_audio_html_fallback(self, e2e_studio):
        """MP3 에셋 없이 HTML 스크립트 fallback."""
        request = ContentRequest(
            content_type="audio",
            topic="인간중심경영",
        )
        result = await e2e_studio.generate(request)
        assert result.files[0].file_type == "html"


class TestE2EQuiz:
    """퀴즈 전체 파이프라인 E2E."""

    @pytest.mark.asyncio
    async def test_quiz_generates_file(self, viz_only_studio):
        request = ContentRequest(
            content_type="quiz",
            topic="SKMS 기본",
            options=ContentOptions(num_items=5),
        )
        result = await viz_only_studio.generate(request)

        assert result.content_type == "quiz"
        assert len(result.files) >= 1
        assert result.files[0].size_bytes > 0


# ---------------------------------------------------------------------------
# 성능 벤치마크 (mock 기반 — <5초 확인)
# ---------------------------------------------------------------------------


class TestE2EPerformance:
    """파이프라인 성능 벤치마크 (mock 환경)."""

    @pytest.mark.asyncio
    async def test_lecture_under_5s(self, e2e_studio):
        start = time.time()
        request = ContentRequest(
            content_type="lecture",
            topic="성능 테스트",
        )
        await e2e_studio.generate(request)
        elapsed = time.time() - start
        assert elapsed < 5.0, f"Lecture 생성이 {elapsed:.1f}초 소요 (목표: <5s)"

    @pytest.mark.asyncio
    async def test_card_news_under_5s(self, e2e_studio):
        start = time.time()
        request = ContentRequest(
            content_type="card_news",
            topic="성능 테스트",
        )
        await e2e_studio.generate(request)
        elapsed = time.time() - start
        assert elapsed < 5.0, f"Card news 생성이 {elapsed:.1f}초 소요 (목표: <5s)"

    @pytest.mark.asyncio
    async def test_all_types_under_10s(self, e2e_studio):
        """6개 유형 전부 순차 실행해도 10초 이내."""
        start = time.time()
        types = [
            ("lecture", ContentOptions(duration_min=30)),
            ("card_news", ContentOptions(num_items=3)),
            ("workshop", ContentOptions(duration_min=60)),
            ("audio", ContentOptions(duration_min=5)),
            ("visualization", ContentOptions()),
            ("quiz", ContentOptions(num_items=5)),
        ]
        for ct, opts in types:
            request = ContentRequest(content_type=ct, topic="벤치마크", options=opts)
            await e2e_studio.generate(request)

        elapsed = time.time() - start
        assert elapsed < 10.0, f"전체 6유형 생성이 {elapsed:.1f}초 소요 (목표: <10s)"


# ---------------------------------------------------------------------------
# ContentResult 불변성 검증
# ---------------------------------------------------------------------------


class TestE2EResultImmutability:
    """ContentResult는 frozen dataclass여야 한다."""

    @pytest.mark.asyncio
    async def test_result_is_frozen(self, e2e_studio):
        request = ContentRequest(content_type="lecture", topic="불변성")
        result = await e2e_studio.generate(request)

        with pytest.raises(AttributeError):
            result.content_type = "changed"

    @pytest.mark.asyncio
    async def test_files_is_tuple(self, e2e_studio):
        request = ContentRequest(content_type="lecture", topic="튜플 테스트")
        result = await e2e_studio.generate(request)

        assert isinstance(result.files, tuple)
        assert isinstance(result.citations, tuple)
        assert isinstance(result.metadata, tuple)
