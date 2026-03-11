"""서버 의존성 주입.

PR-013: FastAPI 서버 DI (SearchService, GenerationService 등).
PR-027: EvidenceFilter, CrossVersionComparisonService 추가.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

from scripts.lib.bm25_index import BM25Index
from scripts.lib.cross_version_comparison import CrossVersionComparisonService
from scripts.lib.evidence_filter import EvidenceFilter, EvidenceFilterConfig
from scripts.lib.generation import GenerationConfig, GenerationService
from scripts.lib.pinecone_store import create_vector_store
from scripts.lib.search_service import SearchService
from scripts.lib.toc_service import TOCService

logger = logging.getLogger(__name__)


class AppState:
    """애플리케이션 상태 (서비스 인스턴스 보관)."""

    def __init__(self) -> None:
        self.search_service: SearchService | None = None
        self.generation_service: GenerationService | None = None
        self.toc_service: TOCService | None = None
        self.evidence_filter: EvidenceFilter | None = None
        self.comparison_service: CrossVersionComparisonService | None = None
        self.content_studio: Any = None  # ContentStudio (Phase 4)
        self.version: str = "0.2.0"
        self._initialized: bool = False

    @property
    def is_ready(self) -> bool:
        return self._initialized

    def initialize(
        self,
        index_dir: Path = Path("indexes"),
        config_dir: Path = Path("config"),
        data_dir: Path = Path("data/processed"),
    ) -> None:
        """서비스를 초기화한다."""
        # 검색 서비스 초기화
        retrieval_config = _load_yaml(config_dir / "retrieval.yaml")
        retrieval = retrieval_config.get("retrieval", {})

        # VectorStore (Chroma or Pinecone — provider 기반 팩토리)
        vector_config = retrieval.get("vector", {})
        vector_store = create_vector_store(vector_config, index_dir)

        # BM25Index
        bm25_path = Path(
            retrieval.get("keyword", {}).get("index_path", "indexes/bm25_index.pkl")
        )
        bm25_index = BM25Index.from_path(bm25_path)

        # Embedding function (OpenAI)
        embedding_model = vector_config.get("embedding_model") or os.environ.get(
            "OPENAI_EMBEDDING_MODEL",
            "text-embedding-3-large",
        )
        embedding_fn = _make_embedding_fn(embedding_model)

        self.search_service = SearchService(
            vector_store=vector_store,
            bm25_index=bm25_index,
            embedding_fn=embedding_fn,
        )
        logger.info(
            "SearchService 초기화 완료: vector=%s, bm25=%s",
            vector_store.is_available,
            bm25_index is not None,
        )

        # 생성 서비스 초기화
        gen_config = GenerationConfig.from_yaml(config_dir / "generation.yaml")
        anthropic_client = _make_anthropic_client()

        if anthropic_client:
            self.generation_service = GenerationService(
                client=anthropic_client,
                config=gen_config,
            )
            self.generation_service.load_prompts(Path(gen_config.prompts_dir))
            logger.info("GenerationService 초기화 완료")
        else:
            logger.warning("ANTHROPIC_API_KEY 미설정 → GenerationService 비활성")

        # TOC 서비스 초기화
        structure_path = data_dir / "structure.json"
        if structure_path.exists():
            raw_text_path = Path("data/raw/SKMSraw.txt")
            self.toc_service = TOCService.from_path(structure_path, raw_text_path)
            logger.info(
                "TOCService 초기화 완료: %d editions", self.toc_service.edition_count
            )
        else:
            logger.warning("structure.json 없음 → TOCService 비활성")

        # EvidenceFilter 초기화
        self.evidence_filter = EvidenceFilter()
        logger.info("EvidenceFilter 초기화 완료")

        # CrossVersionComparisonService 초기화
        concept_timeline = None
        timeline_path = Path("config/concept_timeline.yaml")
        if timeline_path.exists():
            try:
                from scripts.lib.concept_timeline import ConceptTimeline

                concept_timeline = ConceptTimeline.from_yaml(timeline_path)
                logger.info(
                    "ConceptTimeline 로드 완료: %d concepts",
                    concept_timeline.concept_count,
                )
            except Exception as e:
                logger.warning("ConceptTimeline 로드 실패: %s", e)

        self.comparison_service = CrossVersionComparisonService(
            concept_timeline=concept_timeline,
        )
        logger.info("CrossVersionComparisonService 초기화 완료")

        self._initialized = True


def _load_yaml(path: Path) -> dict:
    """YAML 파일을 안전하게 로드한다."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _make_embedding_fn(embedding_model: str = "text-embedding-3-large") -> Any:
    """OpenAI 임베딩 함수를 생성한다."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY 미설정 → 벡터 검색 비활성")
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)

        def _embed(text: str) -> list[float]:
            response = client.embeddings.create(model=embedding_model, input=[text])
            return response.data[0].embedding

        return _embed
    except ImportError:
        logger.warning("openai 패키지 없음 → 벡터 검색 비활성")
        return None


def _make_anthropic_client() -> Any:
    """Anthropic 클라이언트를 생성한다."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        import anthropic

        return anthropic.Anthropic(api_key=api_key)
    except ImportError:
        logger.warning("anthropic 패키지 없음 → 생성 서비스 비활성")
        return None
