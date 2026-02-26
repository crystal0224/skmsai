"""SearchService — Vector + BM25 하이브리드 검색 서비스.

PR-011: 개정판 필터 검색 API.
PR-019: BM25 동의어 확장 통합.
PR-020: Hybrid Retrieval 고도화 — HybridConfig, 점수 정규화, 진단 로깅.
PR-021: Reranker 통합 — optional reranker step in hybrid_search.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from scripts.lib.bm25_index import BM25Index
from scripts.lib.search_types import SearchHit
from scripts.lib.synonym_map import SynonymMap
from scripts.lib.vector_store import RawVectorHit, VectorStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HybridConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HybridConfig:
    """하이브리드 검색 설정 (불변).

    retrieval.yaml의 hybrid 섹션에서 로드한다.
    """

    alpha: float = 0.6
    rrf_k: int = 60
    final_top_k: int = 5
    vector_top_k_multiplier: int = 2
    bm25_top_k_multiplier: int = 2
    score_threshold: float = 0.5
    normalize_scores: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HybridConfig:
        """dict에서 HybridConfig를 생성한다."""
        return cls(
            alpha=float(data.get("alpha", 0.6)),
            rrf_k=int(data.get("rrf_k", 60)),
            final_top_k=int(data.get("final_top_k", 5)),
            vector_top_k_multiplier=int(data.get("vector_top_k_multiplier", 2)),
            bm25_top_k_multiplier=int(data.get("bm25_top_k_multiplier", 2)),
            score_threshold=float(data.get("score_threshold", 0.5)),
            normalize_scores=bool(data.get("normalize_scores", True)),
        )

    @classmethod
    def from_yaml(cls, path: Path) -> HybridConfig:
        """retrieval.yaml에서 hybrid 섹션을 로드한다."""
        import yaml

        if not path.exists():
            logger.warning("검색 설정 파일 없음: %s, 기본값 사용", path)
            return cls()

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        hybrid_data = data.get("retrieval", {}).get("hybrid", {})
        return cls.from_dict(hybrid_data)


# ---------------------------------------------------------------------------
# SearchService
# ---------------------------------------------------------------------------


class SearchService:
    """Vector + BM25 하이브리드 검색 서비스.

    embedding_fn: query → embedding 변환 함수.
    synonym_map: 동의어 확장 맵 (BM25/Hybrid 검색에서 사용).
    hybrid_config: 하이브리드 검색 설정.
    reranker: optional Reranker (Cohere/Cross-Encoder).
    """

    def __init__(
        self,
        vector_store: VectorStore,
        bm25_index: BM25Index | None = None,
        *,
        embedding_fn: Callable[[str], list[float]] | None = None,
        synonym_map: SynonymMap | None = None,
        hybrid_config: HybridConfig | None = None,
        reranker: Any | None = None,
    ) -> None:
        self._vector_store = vector_store
        self._bm25_index = bm25_index
        self._embedding_fn = embedding_fn
        self._synonym_map = synonym_map
        self._hybrid_config = hybrid_config or HybridConfig()
        self._reranker = reranker

    @property
    def hybrid_config(self) -> HybridConfig:
        """현재 하이브리드 검색 설정."""
        return self._hybrid_config

    def vector_search(
        self,
        query: str,
        *,
        top_k: int = 10,
        edition_filter: str | None = None,
        type_filter: list[str] | None = None,
        score_threshold: float = 0.5,
    ) -> list[SearchHit]:
        """벡터 유사도 검색."""
        if self._embedding_fn is None or not self._vector_store.is_available:
            return []

        embedding = self._embedding_fn(query)

        # Build Chroma where filter
        where = _build_where(edition_filter, type_filter)

        raw_hits = self._vector_store.query(
            embedding=embedding,
            n_results=top_k,
            where=where,
        )

        hits: list[SearchHit] = []
        for h in raw_hits:
            score = max(0.0, 1.0 - h.distance)
            if score < score_threshold:
                continue
            hit = _raw_hit_to_search_hit(h, score)
            hits.append(hit)

        return hits

    def bm25_search(
        self,
        query: str,
        *,
        top_k: int = 10,
        edition_filter: str | None = None,
        type_filter: list[str] | None = None,
    ) -> list[SearchHit]:
        """BM25 키워드 검색 (동의어 확장 포함)."""
        if self._bm25_index is None:
            return []

        return self._bm25_index.search(
            query,
            top_k=top_k,
            edition_filter=edition_filter,
            type_filter=type_filter,
            synonym_map=self._synonym_map,
        )

    def hybrid_search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        edition_filter: str | None = None,
        type_filter: list[str] | None = None,
        alpha: float | None = None,
        rrf_k: int | None = None,
    ) -> list[SearchHit]:
        """RRF 기반 하이브리드 검색 (Vector + BM25).

        파라미터 미지정 시 hybrid_config 기본값을 사용한다.
        """
        cfg = self._hybrid_config
        final_top_k = top_k if top_k is not None else cfg.final_top_k
        effective_alpha = alpha if alpha is not None else cfg.alpha
        effective_rrf_k = rrf_k if rrf_k is not None else cfg.rrf_k

        vec_top_k = final_top_k * cfg.vector_top_k_multiplier
        bm25_top_k = final_top_k * cfg.bm25_top_k_multiplier

        vec_hits = self.vector_search(
            query,
            top_k=vec_top_k,
            edition_filter=edition_filter,
            type_filter=type_filter,
            score_threshold=cfg.score_threshold,
        )
        bm25_hits = self.bm25_search(
            query,
            top_k=bm25_top_k,
            edition_filter=edition_filter,
            type_filter=type_filter,
        )

        logger.debug(
            "Hybrid 검색: query='%s', vec=%d, bm25=%d, alpha=%.2f",
            query,
            len(vec_hits),
            len(bm25_hits),
            effective_alpha,
        )

        # BM25 점수 정규화 (0~1 범위)
        if cfg.normalize_scores and bm25_hits:
            bm25_hits = _normalize_bm25_scores(bm25_hits)

        fused = _rrf_fusion(
            vec_hits, bm25_hits, effective_alpha, effective_rrf_k, final_top_k
        )

        # Reranker (optional)
        if self._reranker is not None and fused:
            logger.debug("Reranker 적용: %d건 → top_n=%d", len(fused), final_top_k)
            fused = self._reranker.rerank(query, fused, top_n=final_top_k)

        return fused

    def search_by_edition(
        self,
        query: str,
        edition_id: str,
        *,
        top_k: int = 10,
        mode: str = "hybrid",
    ) -> list[SearchHit]:
        """개정판 필터 검색 편의 메서드."""
        if mode == "vector":
            return self.vector_search(query, top_k=top_k, edition_filter=edition_id)
        if mode == "bm25":
            return self.bm25_search(query, top_k=top_k, edition_filter=edition_id)
        return self.hybrid_search(query, top_k=top_k, edition_filter=edition_id)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_where(
    edition_filter: str | None,
    type_filter: list[str] | None,
) -> dict | None:
    """Chroma where 조건을 조합한다."""
    conditions: list[dict] = []

    if edition_filter:
        conditions.append({"edition_id": {"$eq": edition_filter}})
    if type_filter:
        if len(type_filter) == 1:
            conditions.append({"type": {"$eq": type_filter[0]}})
        else:
            conditions.append({"type": {"$in": type_filter}})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _raw_hit_to_search_hit(hit: RawVectorHit, score: float) -> SearchHit:
    """RawVectorHit → SearchHit."""
    meta = hit.metadata
    edition_id = meta.get("edition_id", "")

    year_match = re.match(r"(\d{4})", edition_id)
    year = int(year_match.group(1)) if year_match else 0

    rev_match = re.search(r"(\d+)차", edition_id)
    revision_num = int(rev_match.group(1)) if rev_match else 0

    section_raw = meta.get("section_path", "[]")
    if isinstance(section_raw, str):
        try:
            section_list = json.loads(section_raw)
        except json.JSONDecodeError:
            section_list = []
    else:
        section_list = list(section_raw) if section_raw else []

    flags_raw = meta.get("quality_flags", "[]")
    if isinstance(flags_raw, str):
        try:
            flags_list = json.loads(flags_raw)
        except json.JSONDecodeError:
            flags_list = []
    else:
        flags_list = list(flags_raw) if flags_raw else []

    return SearchHit(
        quote_id=hit.id,
        text=hit.document,
        score=score,
        edition_id=edition_id,
        year=year,
        revision_num=revision_num,
        quote_type=meta.get("type", "narrative"),
        section_path=tuple(section_list),
        source="vector",
        content_hash=meta.get("sha256", ""),
        quality_flags=tuple(flags_list),
    )


def _normalize_bm25_scores(hits: list[SearchHit]) -> list[SearchHit]:
    """BM25 점수를 0~1 범위로 정규화한다 (min-max scaling)."""
    if not hits:
        return hits

    scores = [h.score for h in hits]
    min_score = min(scores)
    max_score = max(scores)

    if max_score == min_score:
        # 모든 점수가 동일하면 0.5로 설정
        return [
            SearchHit(
                quote_id=h.quote_id,
                text=h.text,
                score=0.5,
                edition_id=h.edition_id,
                year=h.year,
                revision_num=h.revision_num,
                quote_type=h.quote_type,
                section_path=h.section_path,
                source=h.source,
                content_hash=h.content_hash,
                quality_flags=h.quality_flags,
            )
            for h in hits
        ]

    score_range = max_score - min_score
    return [
        SearchHit(
            quote_id=h.quote_id,
            text=h.text,
            score=(h.score - min_score) / score_range,
            edition_id=h.edition_id,
            year=h.year,
            revision_num=h.revision_num,
            quote_type=h.quote_type,
            section_path=h.section_path,
            source=h.source,
            content_hash=h.content_hash,
            quality_flags=h.quality_flags,
        )
        for h in hits
    ]


def _rrf_fusion(
    vec_hits: list[SearchHit],
    bm25_hits: list[SearchHit],
    alpha: float,
    rrf_k: int,
    final_top_k: int,
) -> list[SearchHit]:
    """RRF(Reciprocal Rank Fusion)로 결합한다."""
    scores: dict[str, float] = {}
    hit_map: dict[str, SearchHit] = {}

    for rank, hit in enumerate(vec_hits):
        scores[hit.quote_id] = scores.get(hit.quote_id, 0) + alpha / (rrf_k + rank + 1)
        hit_map[hit.quote_id] = hit

    for rank, hit in enumerate(bm25_hits):
        scores[hit.quote_id] = scores.get(hit.quote_id, 0) + (1 - alpha) / (
            rrf_k + rank + 1
        )
        if hit.quote_id not in hit_map:
            hit_map[hit.quote_id] = hit

    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

    results: list[SearchHit] = []
    for qid in sorted_ids[:final_top_k]:
        original = hit_map[qid]
        # fusion_score로 SearchHit 재생성
        fused = SearchHit(
            quote_id=original.quote_id,
            text=original.text,
            score=scores[qid],
            edition_id=original.edition_id,
            year=original.year,
            revision_num=original.revision_num,
            quote_type=original.quote_type,
            section_path=original.section_path,
            source="hybrid",
            content_hash=original.content_hash,
            quality_flags=original.quality_flags,
        )
        results.append(fused)

    return results
