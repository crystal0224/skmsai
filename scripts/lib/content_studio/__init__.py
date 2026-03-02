"""Content Studio — SKMS 기반 교육 콘텐츠 자동 생성 오케스트레이터.

Phase 4: Content Studio (PR-040~PR-052).

5단계 파이프라인:
1. ContentPlanner — 주제 → 아웃라인
2. ContentGenerator — 아웃라인 → 본문 (RAG 기반)
3. AssetGenerator — 이미지/차트/오디오 생성 (MCP)
4. FileAssembler — 최종 파일 조립 (PPTX/PDF/HTML)
5. Publisher — 사내 플랫폼 배포

PR-047: ContentStudio 오케스트레이터 구현.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from scripts.lib.content_studio.assembler import AssemblerConfig, FileAssembler
from scripts.lib.content_studio.asset_generator import AssetGenerator
from scripts.lib.content_studio.errors import (
    AssemblyError,
    AssetError,
    ContentStudioError,
    GenerationError,
    PlanningError,
)
from scripts.lib.content_studio.generator import (
    ContentGenerator,
    EvidenceFilterProtocol,
    GenerationServiceProtocol,
    SearchServiceProtocol,
    TemporalGuardrailProtocol,
)
from scripts.lib.content_studio.models import (
    VALID_VIZ_TYPES,
    AudioPlan,
    CardNewsPlan,
    ContentOptions,
    ContentPlan,
    ContentRequest,
    ContentResult,
    GeneratedAsset,
    GeneratedFile,
    LecturePlan,
    QuizPlan,
    VisualizationPlan,
    WorkshopPlan,
    load_content_studio_config,
)
from scripts.lib.content_studio.plan_cache import CacheStats, PlanCache
from scripts.lib.content_studio.planner import ContentPlanner, LLMClient

logger = logging.getLogger(__name__)

__all__ = [
    "ContentStudio",
    "ContentStudioError",
    "PlanningError",
    "GenerationError",
    "AssetError",
    "AssemblyError",
    "PlanCache",
    "CacheStats",
]

# ---------------------------------------------------------------------------
# 지원하는 콘텐츠 유형 메타데이터
# ---------------------------------------------------------------------------

CONTENT_TYPE_INFO: tuple[dict[str, Any], ...] = (
    {
        "type": "lecture",
        "label": "강의자료",
        "description": "PPTX 슬라이드 기반 강의자료 (발표자 노트 포함)",
        "output_formats": ["pptx", "html"],
        "default_duration_min": 30,
    },
    {
        "type": "card_news",
        "label": "카드뉴스",
        "description": "소셜 미디어용 이미지 카드 세트",
        "output_formats": ["png", "html"],
        "default_num_items": 5,
    },
    {
        "type": "workshop",
        "label": "워크숍",
        "description": "워크숍 진행자 가이드 (단계별 시간 배분)",
        "output_formats": ["html", "pdf"],
        "default_duration_min": 60,
    },
    {
        "type": "visualization",
        "label": "시각화",
        "description": "개념 시각화 (타임라인, 마인드맵, 비교 차트 등)",
        "output_formats": ["svg", "png", "html"],
    },
    {
        "type": "audio",
        "label": "오디오",
        "description": "교육용 오디오 콘텐츠 (나레이션, 대화, 팟캐스트)",
        "output_formats": ["mp3", "html"],
        "default_duration_min": 5,
    },
    {
        "type": "quiz",
        "label": "퀴즈",
        "description": "학습 확인용 4지선다 퀴즈",
        "output_formats": ["html", "pdf"],
        "default_num_items": 10,
    },
)


# ---------------------------------------------------------------------------
# ContentStudio
# ---------------------------------------------------------------------------


class ContentStudio:
    """Content Studio 메인 오케스트레이터.

    5단계 파이프라인을 조율하여 콘텐츠를 생성한다.
    모든 서비스는 DI로 주입. 누락 시 해당 단계를 스킵하고 경고 로그를 남긴다.
    """

    def __init__(
        self,
        planner: ContentPlanner | None = None,
        generator: ContentGenerator | None = None,
        asset_generator: AssetGenerator | None = None,
        assembler: FileAssembler | None = None,
        config: dict[str, Any] | None = None,
        plan_cache: PlanCache | None = None,
    ) -> None:
        self._planner = planner
        self._generator = generator
        self._asset_gen = asset_generator
        self._assembler = assembler
        self._config = config or {}
        self._plan_cache = plan_cache

    @classmethod
    def create(
        cls,
        llm_client: LLMClient | None = None,
        search_service: SearchServiceProtocol | None = None,
        generation_service: GenerationServiceProtocol | None = None,
        evidence_filter: EvidenceFilterProtocol | None = None,
        temporal_guardrail: TemporalGuardrailProtocol | None = None,
        image_generator: Any | None = None,
        chart_generator: Any | None = None,
        audio_generator: Any | None = None,
        config_path: str | Path = "config/content_studio.yaml",
        output_dir: str = "output",
    ) -> ContentStudio:
        """팩토리 메서드: 설정 파일 기반으로 전체 파이프라인을 초기화한다.

        Args:
            llm_client: LLM 클라이언트 (ContentPlanner용).
            search_service: 검색 서비스 (ContentGenerator용).
            generation_service: 생성 서비스 (ContentGenerator용).
            evidence_filter: 근거 검증 필터 (optional).
            temporal_guardrail: 시간축 가드레일 (optional).
            image_generator: 이미지 생성 어댑터 (optional).
            chart_generator: 차트 생성 어댑터 (optional).
            audio_generator: 오디오 생성 어댑터 (optional).
            config_path: content_studio.yaml 경로.
            output_dir: 출력 디렉토리.

        Returns:
            초기화된 ContentStudio 인스턴스.
        """
        # 설정 로드
        config: dict[str, Any] = {}
        try:
            config = load_content_studio_config(config_path)
            logger.info("Content Studio 설정 로드 완료: %s", config_path)
        except (FileNotFoundError, ValueError) as e:
            logger.warning("설정 파일 로드 실패, 기본값 사용: %s", e)

        # 1. Planner
        planner = None
        if llm_client is not None:
            planner = ContentPlanner(llm_client=llm_client, config=config)
            logger.info("ContentPlanner 초기화 완료")
        else:
            logger.warning("LLM 클라이언트 미설정 → ContentPlanner 비활성")

        # 2. Generator
        generator = None
        if search_service is not None and generation_service is not None:
            generator = ContentGenerator(
                search_service=search_service,
                generation_service=generation_service,
                evidence_filter=evidence_filter,
                temporal_guardrail=temporal_guardrail,
            )
            logger.info("ContentGenerator 초기화 완료")
        else:
            logger.warning("SearchService/GenerationService 미설정 → ContentGenerator 비활성")

        # 3. AssetGenerator
        cache_dir = config.get("cache_dir", f"{output_dir}/assets")
        asset_gen = AssetGenerator(
            image_generator=image_generator,
            chart_generator=chart_generator,
            audio_generator=audio_generator,
            cache_dir=cache_dir,
        )
        logger.info("AssetGenerator 초기화 완료 (cache: %s)", cache_dir)

        # 4. Assembler
        assembler_config = AssemblerConfig(
            output_dir=config.get("output_dir", output_dir),
        )
        assembler = FileAssembler(assembler_config)
        logger.info("FileAssembler 초기화 완료 (output: %s)", assembler_config.output_dir)

        # 5. PlanCache (optional)
        plan_cache: PlanCache | None = None
        cache_config = config.get("plan_cache", {})
        if cache_config.get("enabled", True):
            ttl = cache_config.get("ttl_seconds", 86400)
            max_entries = cache_config.get("max_entries", 100)
            plan_cache = PlanCache(ttl_seconds=ttl, max_entries=max_entries)
            logger.info("PlanCache 초기화 완료 (ttl=%ds, max=%d)", ttl, max_entries)

        return cls(
            planner=planner,
            generator=generator,
            asset_generator=asset_gen,
            assembler=assembler,
            config=config,
            plan_cache=plan_cache,
        )

    # -----------------------------------------------------------------------
    # Main pipeline
    # -----------------------------------------------------------------------

    async def generate(self, request: ContentRequest) -> ContentResult:
        """콘텐츠 생성 전체 파이프라인을 실행한다.

        5단계: Plan → Generate → Assets → Assemble → Result.

        Args:
            request: 콘텐츠 생성 요청.

        Returns:
            ContentResult (생성된 파일, 인용, 메타데이터 포함).
        """
        start = time.time()
        metadata: dict[str, Any] = {"content_type": request.content_type}

        # Stage 1: Plan
        plan = await self._stage_plan(request)
        metadata["plan_elapsed_ms"] = _elapsed_ms(start)

        # Stage 2: Generate content
        content = await self._stage_generate(plan, request.content_type)
        metadata["generate_elapsed_ms"] = _elapsed_ms(start)

        # Stage 3: Generate assets
        assets = await self._stage_assets(plan)
        metadata["asset_count"] = len(assets)
        metadata["assets_elapsed_ms"] = _elapsed_ms(start)

        # Stage 4: Assemble files
        files = self._stage_assemble(
            request.content_type, content, assets, request.topic
        )
        metadata["file_count"] = len(files)
        metadata["assemble_elapsed_ms"] = _elapsed_ms(start)

        # Collect citations
        citations = _extract_citations(content)

        total_ms = _elapsed_ms(start)
        metadata["total_elapsed_ms"] = total_ms
        logger.info(
            "콘텐츠 생성 완료: type=%s, topic=%s, files=%d, elapsed=%.0fms",
            request.content_type,
            request.topic,
            len(files),
            total_ms,
        )

        return ContentResult(
            content_type=request.content_type,
            topic=request.topic,
            files=tuple(files),
            citations=tuple(citations),
            metadata=tuple(sorted(metadata.items())),
            plan=plan,
        )

    async def plan_only(self, request: ContentRequest) -> ContentPlan:
        """Plan 단계만 실행 (미리보기/검토용).

        Args:
            request: 콘텐츠 생성 요청.

        Returns:
            생성된 ContentPlan.
        """
        return await self._stage_plan(request)

    # -----------------------------------------------------------------------
    # Properties
    # -----------------------------------------------------------------------

    @property
    def has_planner(self) -> bool:
        return self._planner is not None

    @property
    def has_generator(self) -> bool:
        return self._generator is not None

    @property
    def has_asset_generator(self) -> bool:
        return self._asset_gen is not None

    @property
    def has_assembler(self) -> bool:
        return self._assembler is not None

    @property
    def has_plan_cache(self) -> bool:
        return self._plan_cache is not None

    @property
    def plan_cache(self) -> PlanCache | None:
        return self._plan_cache

    @staticmethod
    def content_types() -> tuple[dict[str, Any], ...]:
        """지원하는 콘텐츠 유형 메타데이터를 반환한다."""
        return CONTENT_TYPE_INFO

    # -----------------------------------------------------------------------
    # Pipeline stages (private)
    # -----------------------------------------------------------------------

    async def _stage_plan(self, request: ContentRequest) -> ContentPlan:
        """Stage 1: Plan 생성 (캐시 히트 시 LLM 호출 스킵)."""
        if self._planner is None:
            raise PlanningError("ContentPlanner가 초기화되지 않았습니다")

        ct = request.content_type
        opts = request.options
        topic = request.topic

        # 캐시 조회
        cache_key: str | None = None
        if self._plan_cache is not None:
            cache_key = PlanCache.cache_key(ct, topic, opts)
            cached_plan = self._plan_cache.get(cache_key)
            if cached_plan is not None:
                logger.info("Plan 캐시 히트: type=%s, topic=%s", ct, topic)
                return cached_plan

        try:
            if ct == "lecture":
                duration = opts.duration_min or 30
                plan = await self._planner.plan_lecture(topic, duration, opts)
            elif ct == "card_news":
                num_cards = opts.num_items or 5
                plan = await self._planner.plan_card_news(topic, num_cards, opts)
            elif ct == "workshop":
                duration = opts.duration_min or 60
                plan = await self._planner.plan_workshop(topic, duration, opts)
            elif ct == "audio":
                duration = opts.duration_min or 5
                audio_style = (
                    opts.style
                    if opts.style in ("narration", "dialogue", "podcast")
                    else "dialogue"
                )
                plan = await self._planner.plan_audio(
                    topic, duration, audio_style, opts
                )
            elif ct == "visualization":
                viz_type = opts.style if opts.style in VALID_VIZ_TYPES else "timeline"
                plan = await self._planner.plan_visualization(topic, viz_type, opts)
            elif ct == "quiz":
                num_q = opts.num_items or 10
                plan = await self._planner.plan_quiz(topic, num_q, opts)
            else:
                raise PlanningError(f"지원하지 않는 콘텐츠 유형: {ct}")
        except PlanningError:
            raise
        except Exception as e:
            raise PlanningError(f"Plan 생성 실패: {e}") from e

        # 캐시 저장
        if self._plan_cache is not None and cache_key is not None:
            self._plan_cache.put(cache_key, plan)
            logger.info("Plan 캐시 저장: type=%s, topic=%s", ct, topic)

        return plan

    async def _stage_generate(self, plan: ContentPlan, content_type: str) -> Any:
        """Stage 2: Content 생성 (RAG 기반)."""
        if self._generator is None:
            logger.warning("ContentGenerator 미설정 → 콘텐츠 생성 스킵")
            return None

        if content_type == "lecture" and isinstance(plan, LecturePlan):
            return await self._generator.generate_lecture_content(plan)
        elif content_type == "card_news" and isinstance(plan, CardNewsPlan):
            return await self._generator.generate_card_news_content(plan)
        elif content_type == "workshop" and isinstance(plan, WorkshopPlan):
            return await self._generator.generate_workshop_content(plan)
        elif content_type == "audio" and isinstance(plan, AudioPlan):
            return await self._generator.generate_audio_content(plan)
        elif content_type in ("visualization", "quiz"):
            # visualization과 quiz는 plan 단계에서 충분하므로 content 생성 스킵
            return None
        else:
            logger.warning("콘텐츠 생성 미지원 유형: %s", content_type)
            return None

    async def _stage_assets(self, plan: ContentPlan) -> list[GeneratedAsset]:
        """Stage 3: 에셋 생성."""
        if self._asset_gen is None:
            logger.warning("AssetGenerator 미설정 → 에셋 생성 스킵")
            return []
        return await self._asset_gen.generate_assets(plan)

    def _stage_assemble(
        self,
        content_type: str,
        content: Any,
        assets: list[GeneratedAsset],
        topic: str,
    ) -> list[GeneratedFile]:
        """Stage 4: 최종 파일 조립."""
        if self._assembler is None:
            logger.warning("FileAssembler 미설정 → 파일 조립 스킵")
            return []

        asset_list = assets if assets else None

        if content_type == "lecture" and content is not None:
            result = self._assembler.assemble_lecture(
                content, assets=asset_list, topic=topic
            )
            return [result]
        elif content_type == "card_news" and content is not None:
            results = self._assembler.assemble_card_news(
                content, assets=asset_list, topic=topic
            )
            return list(results)
        elif content_type == "workshop" and content is not None:
            result = self._assembler.assemble_workshop(
                content, assets=asset_list, topic=topic
            )
            return [result]
        elif content_type == "audio" and content is not None:
            result = self._assembler.assemble_audio(
                content, assets=asset_list, topic=topic
            )
            return [result]
        elif content_type == "visualization":
            result = self._assembler.assemble_visualization(
                content, assets=asset_list, topic=topic
            )
            return [result]
        elif content_type == "quiz":
            # Quiz는 HTML 조립
            return self._assemble_quiz(content, topic)
        else:
            logger.warning("파일 조립 미지원/콘텐츠 없음: type=%s", content_type)
            return []

    def _assemble_quiz(self, content: Any, topic: str) -> list[GeneratedFile]:
        """퀴즈 HTML 파일 조립 (FileAssembler 미지원 시 직접 생성)."""
        if self._assembler is None:
            return []

        # Quiz는 visualization과 유사하게 HTML fallback 사용
        result = self._assembler.assemble_visualization(content, topic=f"quiz-{topic}")
        return [result]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _elapsed_ms(start: float) -> float:
    """시작 시간 대비 경과 밀리초."""
    return (time.time() - start) * 1000


def _extract_citations(content: Any) -> list[str]:
    """Content 객체에서 인용 목록 추출."""
    if content is None:
        return []
    if hasattr(content, "citations"):
        return list(content.citations)
    return []
