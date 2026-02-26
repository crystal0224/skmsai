#!/usr/bin/env python3
"""벡터 인덱스(Chroma) + 키워드 인덱스(BM25) 구축.

quotes.jsonl 스키마 (02_extract_quotes.py 출력):
  quote_id, edition_id, type, section_path, text,
  char_span, start_line, token_count, sha256, quality_flags

Usage:
    python scripts/03_build_indexes.py
    python scripts/03_build_indexes.py --input data/processed/quotes.jsonl --index-dir indexes/
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
from pathlib import Path

import yaml


def load_config(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_quotes(path: Path) -> list[dict]:
    """quotes.jsonl을 읽어 리스트로 반환한다."""
    quotes: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                quotes.append(json.loads(line))
    return quotes


def filter_by_quality(quotes: list[dict], exclude_flags: list[str]) -> list[dict]:
    """품질 플래그가 exclude 목록에 해당하는 quote를 제외한다."""
    return [
        q
        for q in quotes
        if not any(flag in exclude_flags for flag in q.get("quality_flags", []))
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Chroma 벡터 인덱스
# ─────────────────────────────────────────────────────────────────────────────


def build_chroma_index(
    quotes: list[dict],
    index_dir: Path,
    collection_name: str,
    embedding_model: str,
    dimension: int,
    batch_size: int,
) -> int:
    """Chroma 벡터 인덱스를 구축한다."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print(
            "[03] 경고: OPENAI_API_KEY 미설정 → 벡터 인덱스 건너뜀",
            file=sys.stderr,
        )
        return 0

    try:
        import chromadb
        from openai import OpenAI
    except ImportError as e:
        print(f"[03] 경고: 패키지 없음 ({e}) → 벡터 인덱스 건너뜀", file=sys.stderr)
        return 0

    client = OpenAI(api_key=api_key)
    chroma_path = index_dir / "chroma"
    chroma_path.mkdir(parents=True, exist_ok=True)

    chroma_client = chromadb.PersistentClient(path=str(chroma_path))

    # 기존 컬렉션 삭제 후 재생성
    try:
        chroma_client.delete_collection(collection_name)
    except Exception:
        pass
    collection = chroma_client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    print(f"[03] 벡터 인덱싱 대상: {len(quotes)}개", file=sys.stderr)

    indexed_count = 0
    for i in range(0, len(quotes), batch_size):
        batch = quotes[i : i + batch_size]
        texts = [q["text"] for q in batch]

        try:
            response = client.embeddings.create(model=embedding_model, input=texts)
            embeddings = [item.embedding for item in response.data]
        except Exception as e:
            print(f"[03] 임베딩 오류 (batch {i}): {e}", file=sys.stderr)
            continue

        ids = [q["quote_id"] for q in batch]
        metadatas = [
            {
                "edition_id": q["edition_id"],
                "type": q.get("type", "narrative"),
                "section_path": json.dumps(q["section_path"], ensure_ascii=False),
                "start_line": q.get("start_line", 0),
                "char_span_start": q["char_span"][0],
                "char_span_end": q["char_span"][1],
                "token_count": q["token_count"],
                "sha256": q.get("sha256", ""),
                "quality_flags": json.dumps(
                    q.get("quality_flags", []), ensure_ascii=False
                ),
            }
            for q in batch
        ]

        collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=texts,
        )
        indexed_count += len(batch)
        print(
            f"[03] 벡터: {indexed_count}/{len(quotes)} 완료",
            file=sys.stderr,
            end="\r",
        )

    print(f"\n[03] 벡터 인덱스 완료: {indexed_count}개", file=sys.stderr)
    return indexed_count


# ─────────────────────────────────────────────────────────────────────────────
# BM25 키워드 인덱스
# ─────────────────────────────────────────────────────────────────────────────


def build_bm25_index(
    quotes: list[dict],
    index_path: Path,
    type_boost: dict[str, float],
) -> int:
    """BM25 키워드 인덱스를 구축한다."""
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        print(
            "[03] 경고: rank_bm25 패키지 없음 → BM25 인덱스 건너뜀",
            file=sys.stderr,
        )
        return 0

    tokenized_corpus: list[list[str]] = []
    quote_ids: list[str] = []
    quote_map: dict[str, dict] = {}

    for q in quotes:
        tokens = q["text"].split()

        # 타입별 가중치 부스트 (토큰 반복)
        boost = type_boost.get(q.get("type", "narrative"), 1.0)
        if boost > 1.0:
            tokens = tokens * int(boost)

        tokenized_corpus.append(tokens)
        quote_ids.append(q["quote_id"])
        quote_map[q["quote_id"]] = q

    bm25 = BM25Okapi(tokenized_corpus)

    index_data = {
        "bm25": bm25,
        "quote_ids": quote_ids,
        "quote_map": quote_map,
        "tokenized_corpus": tokenized_corpus,
    }

    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "wb") as f:
        pickle.dump(index_data, f)

    print(f"[03] BM25 인덱스 완료: {len(quote_ids)}개", file=sys.stderr)
    return len(quote_ids)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="벡터 + BM25 인덱스 구축")
    parser.add_argument(
        "--input", default="data/processed/quotes.jsonl", help="입력 JSONL"
    )
    parser.add_argument("--index-dir", default="indexes/", help="인덱스 출력 디렉토리")
    parser.add_argument(
        "--retrieval-config", default="config/retrieval.yaml", help="검색 설정"
    )
    parser.add_argument(
        "--pipeline-config", default="config/pipeline.yaml", help="파이프라인 설정"
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    index_dir = Path(args.index_dir)

    if not input_path.exists():
        print(f"Error: 입력 파일 없음: {input_path}", file=sys.stderr)
        print("  먼저 02_extract_quotes.py를 실행하세요.", file=sys.stderr)
        sys.exit(1)

    retrieval_cfg = load_config(Path(args.retrieval_config))
    pipeline_cfg = load_config(Path(args.pipeline_config))

    index_dir.mkdir(parents=True, exist_ok=True)

    quotes = load_quotes(input_path)
    print(f"[03] 로드: {len(quotes)}개 QuoteObject", file=sys.stderr)

    # 타입별 통계
    type_counts: dict[str, int] = {}
    for q in quotes:
        t = q.get("type", "narrative")
        type_counts[t] = type_counts.get(t, 0) + 1
    for t in sorted(type_counts, key=lambda x: type_counts[x], reverse=True):
        print(f"     {t:12s}: {type_counts[t]:>4}개", file=sys.stderr)

    # 설정 추출
    retrieval = retrieval_cfg.get("retrieval", {})
    vector_cfg = retrieval.get("vector", {})
    keyword_cfg = retrieval.get("keyword", {})
    quality_exclude = retrieval.get("filters", {}).get("quality_flag_exclude", [])

    embedding_cfg = pipeline_cfg.get("pipeline", {}).get("embedding", {})
    embedding_model = embedding_cfg.get("model", "text-embedding-3-large")
    dimension = embedding_cfg.get("dimension", 1536)
    batch_size = embedding_cfg.get("batch_size", 100)

    # 품질 필터링
    filtered = filter_by_quality(quotes, quality_exclude)
    if len(filtered) < len(quotes):
        print(
            f"[03] 품질 필터: {len(quotes)} → {len(filtered)}개 "
            f"({len(quotes) - len(filtered)}개 제외)",
            file=sys.stderr,
        )

    # 벡터 인덱스 구축
    vec_count = build_chroma_index(
        filtered,
        index_dir,
        collection_name=vector_cfg.get("collection_name", "skms_quotes"),
        embedding_model=embedding_model,
        dimension=dimension,
        batch_size=batch_size,
    )

    # BM25 인덱스 구축
    type_boost = keyword_cfg.get("type_boost", {})
    bm25_path = Path(keyword_cfg.get("index_path", "indexes/bm25_index.pkl"))
    bm25_count = build_bm25_index(filtered, bm25_path, type_boost)

    # 메타데이터 저장
    meta = {
        "total_quotes": len(quotes),
        "filtered_quotes": len(filtered),
        "vector_indexed": vec_count,
        "bm25_indexed": bm25_count,
        "embedding_model": embedding_model,
        "embedding_dimension": dimension,
        "type_distribution": type_counts,
    }
    meta_path = index_dir / "meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"[03] 메타: {meta_path}", file=sys.stderr)
    print(f"[03] 완료: 벡터={vec_count}, BM25={bm25_count}", file=sys.stderr)


if __name__ == "__main__":
    main()
