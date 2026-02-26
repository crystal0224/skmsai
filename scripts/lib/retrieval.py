"""공유 검색 함수 모듈.

04_retrieve_and_answer.py와 05_eval_run.py에서 공통 사용.
순환 import 방지를 위해 별도 모듈로 추출 (v5: PR-1 retrieve_quotes).

제공 함수:
  - load_bm25_index()      : BM25 인덱스 로드
  - load_chroma_collection(): Chroma 컬렉션 로드
  - build_chroma_where()    : Chroma where 조건 동적 구성
  - vector_search()         : Chroma 벡터 검색 (type_filter + section_filter)
  - bm25_search()           : BM25 키워드 검색 (type_filter + section_filter)
  - hybrid_fusion()         : RRF 기반 하이브리드 퓨전
  - retrieve_quotes()       : 단일 엔트리 하이브리드 검색 (PR-1)
  - edition_sort_key()      : 개정판 연대순 정렬 키
  - EDITION_ORDER           : 개정판 연대순 매핑
"""
from __future__ import annotations

import json
import pickle
import re
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Edition ordering (chronological) — shared across pipeline
# ---------------------------------------------------------------------------


# 값 = 개정 차수 (초판=0, 1차=1, ..., 14차=14), 순차 인덱스가 아님.
# 2차~4차는 SKMSraw.txt에 수록되지 않아 생략 (OCR 원본 미존재).
EDITION_ORDER: dict[str, int] = {
    "1979-초판": 0,
    "1981-1차": 1,
    "1988-5차": 5,
    "1989-6차": 6,
    "1990-7차": 7,
    "1995-8차": 8,
    "1997-9차": 9,
    "1998-10차": 10,
    "2004-11차": 11,
    "2008-12차": 12,
    "2016-13차": 13,
    "2020-14차": 14,
}


def edition_sort_key(edition_id: str) -> int:
    """개정판 ID에서 연대순 정렬 키를 추출한다.

    EDITION_ORDER에 없는 개정판은 차수 부분을 파싱하여 정렬 키로 사용.
    차수가 없으면 연도를 사용 (fallback).
    """
    if edition_id in EDITION_ORDER:
        return EDITION_ORDER[edition_id]
    # "1983-3차" → 차수 3 추출 시도
    rev_match = re.search(r"(\d+)차", edition_id)
    if rev_match:
        return int(rev_match.group(1))
    # 차수 없으면 연도 (초판 등 특수 케이스)
    year_match = re.match(r"(\d{4})", edition_id)
    if year_match:
        return int(year_match.group(1))
    return 9999


# ---------------------------------------------------------------------------
# Index loaders
# ---------------------------------------------------------------------------


def load_bm25_index(path: Path) -> dict | None:
    """BM25 인덱스를 로드한다."""
    if not path.exists():
        print(f"[lib] 경고: BM25 인덱스 없음: {path}", file=sys.stderr)
        return None
    with open(path, "rb") as f:
        return pickle.load(f)


def load_chroma_collection(index_dir: Path, collection_name: str):
    """Chroma 컬렉션을 로드한다."""
    chroma_path = index_dir / "chroma"
    if not chroma_path.exists():
        print(f"[lib] 경고: Chroma 인덱스 없음: {chroma_path}", file=sys.stderr)
        return None
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(chroma_path))
        return client.get_collection(collection_name)
    except Exception as e:
        print(f"[lib] 경고: Chroma 로드 실패: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Chroma where filter builder
# ---------------------------------------------------------------------------


def build_chroma_where(
    edition_filter: str | None,
    type_filter: list[str] | None,
) -> dict | None:
    """Chroma where 조건을 조합한다.

    - edition_filter: 특정 개정판만 필터링
    - type_filter: 특정 quote 타입만 필터링 (예: ["definition", "principle"])
    """
    conditions: list[dict] = []

    if edition_filter:
        conditions.append({"edition_id": {"$eq": edition_filter}})

    if type_filter and len(type_filter) > 0:
        if len(type_filter) == 1:
            conditions.append({"type": {"$eq": type_filter[0]}})
        else:
            conditions.append({"type": {"$in": type_filter}})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


# ---------------------------------------------------------------------------
# Vector search
# ---------------------------------------------------------------------------


def vector_search(
    collection: Any,
    query: str,
    openai_client: Any,
    embedding_model: str = "text-embedding-3-large",
    top_k: int = 10,
    score_threshold: float = 0.5,
    edition_filter: str | None = None,
    type_filter: list[str] | None = None,
    section_filter: str | None = None,
) -> list[dict]:
    """Chroma 벡터 검색을 수행한다.

    type_filter: Chroma where 조건으로 적용
    section_filter: 결과 후처리로 필터링 (section_path JSON 파싱)
    """
    if collection is None or openai_client is None:
        return []

    try:
        response = openai_client.embeddings.create(model=embedding_model, input=[query])
        query_embedding = response.data[0].embedding
    except Exception as e:
        print(f"[lib] 임베딩 오류: {e}", file=sys.stderr)
        return []

    where_filter = build_chroma_where(edition_filter, type_filter)

    # section_filter가 있으면 더 많은 결과를 요청하여 후처리로 필터링
    request_k = top_k * 3 if section_filter else top_k

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=request_k,
        where=where_filter,
    )

    hits: list[dict] = []
    if results and results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            score = 1.0 - (results["distances"][0][i] if results["distances"] else 0)
            if score >= score_threshold:
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                hits.append(
                    {
                        "quote_id": doc_id,
                        "text": results["documents"][0][i]
                        if results["documents"]
                        else "",
                        "score": score,
                        "source": "vector",
                        "metadata": metadata,
                    }
                )

    # section_filter 후처리 (section_path JSON → 리스트 파싱 후 개별 요소 매칭)
    if section_filter:

        def _section_matches(h: dict) -> bool:
            raw = h.get("metadata", {}).get("section_path", "[]")
            try:
                sp_list = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError:
                sp_list = []
            return any(section_filter in s for s in sp_list)

        hits = [h for h in hits if _section_matches(h)]

    return hits[:top_k]


# ---------------------------------------------------------------------------
# BM25 search
# ---------------------------------------------------------------------------


def bm25_search(
    bm25_data: dict | None,
    query: str,
    top_k: int = 10,
    edition_filter: str | None = None,
    type_filter: list[str] | None = None,
    section_filter: str | None = None,
) -> list[dict]:
    """BM25 키워드 검색을 수행한다.

    type_filter: quote 타입 필터링
    section_filter: section_path 접두사 매칭
    """
    if bm25_data is None:
        return []

    bm25 = bm25_data["bm25"]
    quote_ids = bm25_data["quote_ids"]
    quote_map = bm25_data["quote_map"]

    tokens = query.split()
    scores = bm25.get_scores(tokens)

    # (score, index) 쌍으로 정렬
    scored = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)

    hits: list[dict] = []
    for idx, score in scored[: top_k * 3]:  # 필터링 여유분 확대
        if score <= 0:
            break
        qid = quote_ids[idx]
        q = quote_map.get(qid, {})

        # edition 필터
        if edition_filter and q.get("edition_id") != edition_filter:
            continue

        # type 필터
        if type_filter and q.get("type", "narrative") not in type_filter:
            continue

        # section_path 필터 (섹션 경로 내 접두사 매칭)
        if section_filter:
            section_path = q.get("section_path", [])
            if not any(section_filter in s for s in section_path):
                continue

        section_path_raw = q.get("section_path", [])
        hits.append(
            {
                "quote_id": qid,
                "text": q.get("text", ""),
                "score": float(score),
                "source": "bm25",
                "metadata": {
                    "edition_id": q.get("edition_id", ""),
                    "type": q.get("type", "narrative"),
                    "section_path": json.dumps(section_path_raw, ensure_ascii=False),
                    "quality_flags": json.dumps(
                        q.get("quality_flags", []), ensure_ascii=False
                    ),
                },
            }
        )
        if len(hits) >= top_k:
            break

    return hits


# ---------------------------------------------------------------------------
# Hybrid fusion (RRF)
# ---------------------------------------------------------------------------


def hybrid_fusion(
    vector_hits: list[dict],
    bm25_hits: list[dict],
    alpha: float = 0.6,
    rrf_k: int = 60,
    final_top_k: int = 5,
) -> list[dict]:
    """RRF(Reciprocal Rank Fusion)로 벡터 + BM25 결과를 결합한다."""
    scores: dict[str, float] = {}
    doc_map: dict[str, dict] = {}

    # 벡터 결과 RRF 점수
    for rank, hit in enumerate(vector_hits):
        qid = hit["quote_id"]
        scores[qid] = scores.get(qid, 0) + alpha / (rrf_k + rank + 1)
        doc_map[qid] = hit

    # BM25 결과 RRF 점수
    for rank, hit in enumerate(bm25_hits):
        qid = hit["quote_id"]
        scores[qid] = scores.get(qid, 0) + (1 - alpha) / (rrf_k + rank + 1)
        if qid not in doc_map:
            doc_map[qid] = hit

    # 점수 기준 정렬
    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

    results: list[dict] = []
    for qid in sorted_ids[:final_top_k]:
        hit = {**doc_map[qid], "fusion_score": scores[qid]}
        results.append(hit)

    return results


# ---------------------------------------------------------------------------
# retrieve_quotes — single entry function (PR-1)
# ---------------------------------------------------------------------------


def _apply_intent_policy(
    intent: str,
    edition_hint: str | None,
    hits: list[dict],
    latest_first: bool = False,
) -> list[dict]:
    """의도별 검색 결과 후처리 정책을 적용한다.

    A (specific_time):         edition_hint 기준 필터링
    B (general_definition):    최신판 우선 정렬
    C (evolution_comparison):  연대순 정렬
    D (content_generation):    latest_first 훅 적용 (2단계)
    E (open_ended):            latest_first 훅 적용 (2단계)
    """
    if intent == "specific_time" and edition_hint:
        filtered = [
            h
            for h in hits
            if edition_hint in h.get("metadata", {}).get("edition_id", "")
        ]
        if filtered:
            return filtered
        # edition_hint 매칭 실패 — 전체 결과로 fallback (검색 범위 보존)
        print(
            f"[lib] 경고: specific_time edition_hint='{edition_hint}' 매칭 실패, "
            f"전체 {len(hits)}건으로 fallback",
            file=sys.stderr,
        )
        return hits

    if intent == "general_definition":
        return sorted(
            hits,
            key=lambda h: edition_sort_key(h.get("metadata", {}).get("edition_id", "")),
            reverse=True,
        )

    if intent == "evolution_comparison":
        return sorted(
            hits,
            key=lambda h: edition_sort_key(h.get("metadata", {}).get("edition_id", "")),
        )

    # open_ended, content_generation: latest_first 훅 적용
    if latest_first:
        return sorted(
            hits,
            key=lambda h: edition_sort_key(h.get("metadata", {}).get("edition_id", "")),
            reverse=True,
        )

    return hits


def _normalize_hit(hit: dict, bm25_data: dict | None = None) -> dict:
    """Raw hit을 표준 반환 형식으로 변환한다.

    반환 필드: quote_id, doc_id, year, edition, type,
              chapter_path, score, span, sha256, text,
              source, quality_flags
    """
    meta = hit.get("metadata", {})
    edition_id = meta.get("edition_id", "")
    quote_id = hit.get("quote_id", "")

    # year: edition_id 앞 4자리
    year_match = re.match(r"(\d{4})", edition_id)
    year = int(year_match.group(1)) if year_match else 0

    # chapter_path: section_path를 파싱
    section_raw = meta.get("section_path", "[]")
    if isinstance(section_raw, str):
        try:
            chapter_path = json.loads(section_raw)
        except json.JSONDecodeError:
            chapter_path = []
    else:
        chapter_path = list(section_raw) if section_raw else []

    # span + sha256: Chroma metadata 우선, bm25 quote_map fallback
    span = [0, 0]
    sha256 = ""

    if "char_span_start" in meta:
        span = [meta.get("char_span_start", 0), meta.get("char_span_end", 0)]
    if "sha256" in meta:
        sha256 = meta.get("sha256", "")

    # bm25 cross-reference for missing fields
    if bm25_data and (span == [0, 0] or not sha256):
        quote_map = bm25_data.get("quote_map", {})
        q = quote_map.get(quote_id, {})
        if span == [0, 0]:
            span = list(q.get("char_span", [0, 0]))
        if not sha256:
            sha256 = q.get("sha256", "")

    # quality_flags
    flags_raw = meta.get("quality_flags", "[]")
    if isinstance(flags_raw, str):
        try:
            quality_flags = json.loads(flags_raw)
        except json.JSONDecodeError:
            quality_flags = []
    else:
        quality_flags = list(flags_raw) if flags_raw else []

    return {
        "quote_id": quote_id,
        "doc_id": edition_id,
        "year": year,
        "edition": edition_id,
        "type": meta.get("type", "narrative"),
        "chapter_path": chapter_path,
        "score": hit.get("fusion_score", hit.get("score", 0.0)),
        "span": span,
        "sha256": sha256,
        "text": hit.get("text", ""),
        "source": hit.get("source", ""),
        "quality_flags": quality_flags,
    }


def _do_search(
    query: str,
    edition_filter: str | None,
    type_filter: list[str] | None,
    section_filter: str | None,
    alpha: float,
    rrf_k: int,
    score_threshold: float,
    top_k: int,
    search_vec_k: int,
    search_bm25_k: int,
    collection: Any,
    bm25_data: dict | None,
    openai_client: Any,
    embedding_model: str,
) -> list[dict]:
    """벡터 + BM25 + RRF 퓨전을 한 번 실행한다."""
    vec_hits = vector_search(
        collection,
        query,
        openai_client,
        embedding_model=embedding_model,
        top_k=search_vec_k,
        score_threshold=score_threshold,
        edition_filter=edition_filter,
        type_filter=type_filter,
        section_filter=section_filter,
    )
    bm25_hits = bm25_search(
        bm25_data,
        query,
        top_k=search_bm25_k,
        edition_filter=edition_filter,
        type_filter=type_filter,
        section_filter=section_filter,
    )
    return hybrid_fusion(
        vec_hits,
        bm25_hits,
        alpha=alpha,
        rrf_k=rrf_k,
        final_top_k=top_k,
    )


def _search_with_fallback(
    query: str,
    edition_filter: str | None,
    type_filter: list[str] | None,
    section_filter: str | None,
    alpha: float,
    rrf_k: int,
    score_threshold: float,
    top_k: int,
    search_vec_k: int,
    search_bm25_k: int,
    collection: Any,
    bm25_data: dict | None,
    openai_client: Any,
    embedding_model: str,
    fallback_editions: list[str],
    min_hits: int,
) -> list[dict]:
    """검색을 실행하고, 결과가 빈약하면 폴백 개정판으로 재검색한다.

    PR-4 정책 레이어:
      1차: edition_filter (예: 2020-14차) → 결과 >= min_hits면 반환
      2차: fallback_editions 순서대로 시도
      최종: edition_filter=None (전체)
    """
    search_args = {
        "query": query,
        "type_filter": type_filter,
        "section_filter": section_filter,
        "alpha": alpha,
        "rrf_k": rrf_k,
        "score_threshold": score_threshold,
        "top_k": top_k,
        "search_vec_k": search_vec_k,
        "search_bm25_k": search_bm25_k,
        "collection": collection,
        "bm25_data": bm25_data,
        "openai_client": openai_client,
        "embedding_model": embedding_model,
    }

    # 폴백이 설정되지 않았으면 단순 검색
    if not fallback_editions or min_hits <= 0:
        return _do_search(edition_filter=edition_filter, **search_args)

    # 1차: primary edition
    fused = _do_search(edition_filter=edition_filter, **search_args)
    if len(fused) >= min_hits:
        return fused

    print(
        f"[lib] 정책 폴백: {edition_filter} → {len(fused)}건 "
        f"(min_hits={min_hits}), 폴백 시작",
        file=sys.stderr,
    )

    # 2차: fallback editions
    for fb_edition in fallback_editions:
        fused = _do_search(edition_filter=fb_edition, **search_args)
        if len(fused) >= min_hits:
            print(
                f"[lib] 정책 폴백: {fb_edition} → {len(fused)}건 (충분)",
                file=sys.stderr,
            )
            return fused
        print(
            f"[lib] 정책 폴백: {fb_edition} → {len(fused)}건 (부족)",
            file=sys.stderr,
        )

    # 최종: 전체 검색
    print("[lib] 정책 폴백: 전체 개정판 검색", file=sys.stderr)
    return _do_search(edition_filter=None, **search_args)


def retrieve_quotes(
    query: str,
    intent: str,
    policy: dict,
    top_k: int = 8,
    *,
    collection: Any = None,
    bm25_data: dict | None = None,
    openai_client: Any = None,
    embedding_model: str = "text-embedding-3-large",
) -> list[dict]:
    """단일 엔트리 하이브리드 검색 함수.

    벡터 + BM25 + RRF 퓨전 + 의도별 후처리를 수행하고
    표준화된 dict 리스트를 반환한다.

    Args:
        query: 검색 질의
        intent: 라우팅 의도 (specific_time | general_definition |
                evolution_comparison | content_generation | open_ended)
        policy: 검색 정책 dict
            - edition_filter: str | None — 특정 개정판 제한
            - edition_hint: str | None — 의도 기반 개정판 힌트 (자동 해석)
            - type_filter: list[str] | None — quote 타입 제한
            - section_filter: str | None — 섹션 접두사 매칭
            - alpha: float — 하이브리드 가중치 (기본 0.6)
            - rrf_k: int — RRF 상수 (기본 60)
            - score_threshold: float — 벡터 스코어 컷오프 (기본 0.5)
            - vec_top_k: int — 벡터 검색 개수 (기본 top_k*2)
            - bm25_top_k: int — BM25 검색 개수 (기본 top_k*2)
            - latest_first: bool — 최신판 우선 정렬 (기본 False)
            - _policy_fallback_editions: list[str] — 폴백 개정판 순서 (PR-4)
            - _policy_min_hits: int — 폴백 트리거 최소 결과 수 (PR-4)
        top_k: 최종 반환 개수
        collection: Chroma collection (keyword-only)
        bm25_data: BM25 index dict (keyword-only)
        openai_client: OpenAI client (keyword-only)
        embedding_model: 임베딩 모델명 (keyword-only)

    Returns:
        list[dict] — 표준화 필드:
            quote_id, doc_id, year, edition, type, chapter_path,
            score, span, sha256, text, source, quality_flags
    """
    # Policy defaults
    edition_filter = policy.get("edition_filter")
    edition_hint = policy.get("edition_hint")
    type_filter = policy.get("type_filter")
    section_filter = policy.get("section_filter")
    alpha = policy.get("alpha", 0.6)
    rrf_k = policy.get("rrf_k", 60)
    score_threshold = policy.get("score_threshold", 0.5)
    latest_first = policy.get("latest_first", False)

    # Fallback cascade (PR-4 정책 레이어에서 주입)
    fallback_editions = policy.get("_policy_fallback_editions", [])
    min_hits = policy.get("_policy_min_hits", 0)

    # Resolve edition_hint → edition_filter for specific_time
    if intent == "specific_time" and edition_hint and not edition_filter:
        for eid in EDITION_ORDER:
            if edition_hint in eid:
                edition_filter = eid
                break

    # Search top_k (retrieve more for fusion quality)
    search_vec_k = policy.get("vec_top_k", max(top_k * 2, 10))
    search_bm25_k = policy.get("bm25_top_k", max(top_k * 2, 10))

    # --- Search with fallback cascade ---
    fused = _search_with_fallback(
        query=query,
        edition_filter=edition_filter,
        type_filter=type_filter,
        section_filter=section_filter,
        alpha=alpha,
        rrf_k=rrf_k,
        score_threshold=score_threshold,
        top_k=top_k,
        search_vec_k=search_vec_k,
        search_bm25_k=search_bm25_k,
        collection=collection,
        bm25_data=bm25_data,
        openai_client=openai_client,
        embedding_model=embedding_model,
        fallback_editions=fallback_editions,
        min_hits=min_hits,
    )

    # Intent-based post-processing
    fused = _apply_intent_policy(intent, edition_hint, fused, latest_first)

    # Normalize to standard format
    return [_normalize_hit(h, bm25_data) for h in fused]
