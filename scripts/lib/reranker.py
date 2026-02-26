"""Reranker — Cohere + Cross-Encoder 재순위 서비스.

PR-021: 하이브리드 검색 결과를 질의-문서 관련성 기반으로 재순위한다.

지원 백엔드:
- Cohere Rerank API (cohere-rerank-v3.5)
- Cross-Encoder (sentence-transformers)
"""
from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from scripts.lib.search_types import SearchHit

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RerankerConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RerankerConfig:
    """리랭커 설정 (불변).

    retrieval.yaml의 reranker 섹션에서 로드한다.
    """

    enabled: bool = False
    backend: str = "cohere"  # "cohere" | "cross-encoder"
    model: str = "rerank-v3.5"
    top_n: int = 5
    score_threshold: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RerankerConfig:
        """dict에서 RerankerConfig를 생성한다."""
        return cls(
            enabled=bool(data.get("enabled", False)),
            backend=str(data.get("backend", "cohere")),
            model=str(data.get("model", "rerank-v3.5")),
            top_n=int(data.get("top_n", 5)),
            score_threshold=float(data.get("score_threshold", 0.0)),
        )

    @classmethod
    def from_yaml(cls, path: Path) -> RerankerConfig:
        """retrieval.yaml에서 reranker 섹션을 로드한다."""
        import yaml

        if not path.exists():
            logger.warning("검색 설정 파일 없음: %s, 기본값 사용", path)
            return cls()

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        reranker_data = data.get("retrieval", {}).get("reranker", {})
        return cls.from_dict(reranker_data)


# ---------------------------------------------------------------------------
# RerankerResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RerankerResult:
    """리랭커 결과 단건 (불변)."""

    index: int
    relevance_score: float


# ---------------------------------------------------------------------------
# Reranker Protocol
# ---------------------------------------------------------------------------


class Reranker(Protocol):
    """리랭커 인터페이스."""

    def rerank(
        self,
        query: str,
        hits: list[SearchHit],
        top_n: int,
    ) -> list[SearchHit]:
        ...


# ---------------------------------------------------------------------------
# CohereReranker
# ---------------------------------------------------------------------------


class CohereReranker:
    """Cohere Rerank API 기반 리랭커.

    Cohere의 rerank 엔드포인트를 호출하여 질의-문서 관련성을 재평가한다.
    API 오류 시 원본 순서를 반환한다 (graceful fallback).
    """

    def __init__(
        self,
        *,
        client: Any,
        model: str = "rerank-v3.5",
        score_threshold: float = 0.0,
    ) -> None:
        self._client = client
        self._model = model
        self._score_threshold = score_threshold

    def rerank(
        self,
        query: str,
        hits: list[SearchHit],
        top_n: int,
    ) -> list[SearchHit]:
        """Cohere API로 재순위한다."""
        if not hits:
            return []

        try:
            documents = [h.text for h in hits]
            response = self._client.rerank(
                query=query,
                documents=documents,
                model=self._model,
                top_n=top_n,
            )

            results: list[SearchHit] = []
            for item in response.results:
                if item.relevance_score < self._score_threshold:
                    continue
                original = hits[item.index]
                reranked = SearchHit(
                    quote_id=original.quote_id,
                    text=original.text,
                    score=item.relevance_score,
                    edition_id=original.edition_id,
                    year=original.year,
                    revision_num=original.revision_num,
                    quote_type=original.quote_type,
                    section_path=original.section_path,
                    source="reranked",
                    content_hash=original.content_hash,
                    quality_flags=original.quality_flags,
                )
                results.append(reranked)

            return results

        except Exception:
            logger.warning("Cohere rerank 실패, 원본 순서 반환", exc_info=True)
            return hits[:top_n]


# ---------------------------------------------------------------------------
# CrossEncoderReranker
# ---------------------------------------------------------------------------


def _sigmoid(x: float) -> float:
    """Sigmoid 함수: raw score → 0~1 확률."""
    return 1.0 / (1.0 + math.exp(-x))


class CrossEncoderReranker:
    """Cross-Encoder 기반 로컬 리랭커.

    sentence-transformers의 CrossEncoder 모델을 사용한다.
    모델 오류 시 원본 순서를 반환한다 (graceful fallback).
    """

    def __init__(
        self,
        *,
        model: Any,
        score_threshold: float = 0.0,
    ) -> None:
        self._model = model
        self._score_threshold = score_threshold

    def rerank(
        self,
        query: str,
        hits: list[SearchHit],
        top_n: int,
    ) -> list[SearchHit]:
        """Cross-Encoder로 재순위한다."""
        if not hits:
            return []

        try:
            pairs = [(query, h.text) for h in hits]
            raw_scores = self._model.predict(pairs)

            # (index, normalized_score) 쌍 생성 및 정렬
            scored = [(i, _sigmoid(float(s))) for i, s in enumerate(raw_scores)]
            scored.sort(key=lambda x: x[1], reverse=True)

            results: list[SearchHit] = []
            for idx, norm_score in scored[:top_n]:
                if norm_score < self._score_threshold:
                    continue
                original = hits[idx]
                reranked = SearchHit(
                    quote_id=original.quote_id,
                    text=original.text,
                    score=norm_score,
                    edition_id=original.edition_id,
                    year=original.year,
                    revision_num=original.revision_num,
                    quote_type=original.quote_type,
                    section_path=original.section_path,
                    source="reranked",
                    content_hash=original.content_hash,
                    quality_flags=original.quality_flags,
                )
                results.append(reranked)

            return results

        except Exception:
            logger.warning("Cross-Encoder rerank 실패, 원본 순서 반환", exc_info=True)
            return hits[:top_n]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_reranker(config: RerankerConfig) -> Reranker | None:
    """RerankerConfig에 따라 적절한 리랭커를 생성한다.

    - enabled=False → None
    - backend="cohere" + COHERE_API_KEY → CohereReranker
    - backend="cross-encoder" → CrossEncoderReranker
    - 생성 실패 시 → None (graceful)
    """
    if not config.enabled:
        return None

    if config.backend == "cohere":
        api_key = os.environ.get("COHERE_API_KEY")
        if not api_key:
            logger.warning("COHERE_API_KEY 환경변수 없음, reranker 비활성화")
            return None

        try:
            import cohere

            client = cohere.ClientV2(api_key=api_key)
            return CohereReranker(
                client=client,
                model=config.model,
                score_threshold=config.score_threshold,
            )
        except ImportError:
            logger.warning("cohere 패키지 미설치, reranker 비활성화")
            return None

    if config.backend == "cross-encoder":
        try:
            import sentence_transformers

            model = sentence_transformers.CrossEncoder(config.model)
            return CrossEncoderReranker(
                model=model,
                score_threshold=config.score_threshold,
            )
        except ImportError:
            logger.warning("sentence-transformers 패키지 미설치, reranker 비활성화")
            return None

    logger.warning("알 수 없는 reranker 백엔드: %s", config.backend)
    return None
