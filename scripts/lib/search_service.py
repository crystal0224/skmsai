"""SearchService — Vector + BM25 하이브리드 검색 서비스.

PR-011: 개정판 필터 검색 API.

기존 retrieval.py는 변경하지 않는다. SearchService는 새로운 추상화 레이어로,
VectorStore + BM25Index를 조합하여 SearchHit를 반환한다.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Callable

from scripts.lib.bm25_index import BM25Index
from scripts.lib.search_types import SearchHit
from scripts.lib.vector_store import RawVectorHit, VectorStore

logger = logging.getLogger(__name__)


class SearchService:
    """Vector + BM25 하이브리드 검색 서비스.

    embedding_fn: query → embedding 변환 함수.
    테스트 시 make_fake_embedding_fn() 사용.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        bm25_index: BM25Index | None = None,
        *,
        embedding_fn: Callable[[str], list[float]] | None = None,
    ) -> None:
        self._vector_store = vector_store
        self._bm25_index = bm25_index
        self._embedding_fn = embedding_fn

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
        """BM25 키워드 검색."""
        if self._bm25_index is None:
            return []

        return self._bm25_index.search(
            query,
            top_k=top_k,
            edition_filter=edition_filter,
            type_filter=type_filter,
        )

    def hybrid_search(
        self,
        query: str,
        *,
        top_k: int = 5,
        edition_filter: str | None = None,
        type_filter: list[str] | None = None,
        alpha: float = 0.6,
        rrf_k: int = 60,
    ) -> list[SearchHit]:
        """RRF 기반 하이브리드 검색 (Vector + BM25)."""
        vec_hits = self.vector_search(
            query,
            top_k=top_k * 2,
            edition_filter=edition_filter,
            type_filter=type_filter,
        )
        bm25_hits = self.bm25_search(
            query,
            top_k=top_k * 2,
            edition_filter=edition_filter,
            type_filter=type_filter,
        )

        return _rrf_fusion(vec_hits, bm25_hits, alpha, rrf_k, top_k)

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
