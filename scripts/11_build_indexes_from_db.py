"""DB → Chroma + BM25 인덱스 재구축.

PR-011: DB가 source of truth. JSONL이 아닌 DB에서 읽는다.

Usage:
    python scripts/11_build_indexes_from_db.py
    python scripts/11_build_indexes_from_db.py --db-path data/skms.db --index-dir indexes/
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.db import get_connection, init_db  # noqa: E402
from scripts.lib.quote import QuoteObject  # noqa: E402
from scripts.lib.quote_repository import QuoteRepository  # noqa: E402
from scripts.lib.vector_store import (  # noqa: E402
    VectorStore,
    quote_to_chroma_metadata,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def build_vector_index(
    quotes: list[QuoteObject],
    index_dir: Path,
    collection_name: str,
    embedding_model: str,
    batch_size: int,
) -> int:
    """Chroma 벡터 인덱스를 구축한다."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY 미설정 → 벡터 인덱스 건너뜀")
        return 0

    try:
        from openai import OpenAI
    except ImportError as e:
        logger.warning("패키지 없음 (%s) → 벡터 인덱스 건너뜀", e)
        return 0

    client = OpenAI(api_key=api_key)

    # VectorStore from_path (기존 인덱스 삭제 후 재생성)
    chroma_path = index_dir / "chroma"
    chroma_path.mkdir(parents=True, exist_ok=True)

    try:
        import chromadb

        chroma_client = chromadb.PersistentClient(path=str(chroma_path))
        try:
            chroma_client.delete_collection(collection_name)
        except Exception:
            pass
        collection = chroma_client.create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
    except ImportError as e:
        logger.warning("chromadb 없음 (%s) → 벡터 인덱스 건너뜀", e)
        return 0

    store = VectorStore(collection)
    logger.info("벡터 인덱싱 대상: %d개", len(quotes))

    indexed = 0
    for i in range(0, len(quotes), batch_size):
        batch = quotes[i : i + batch_size]
        texts = [q.text for q in batch]

        try:
            response = client.embeddings.create(model=embedding_model, input=texts)
            embeddings = [item.embedding for item in response.data]
        except Exception as e:
            logger.warning("임베딩 오류 (batch %d): %s", i, e)
            continue

        ids = [q.quote_id for q in batch]
        metadatas = [quote_to_chroma_metadata(q) for q in batch]

        store.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        indexed += len(batch)
        logger.info("벡터: %d/%d 완료", indexed, len(quotes))

    logger.info("벡터 인덱스 완료: %d개", indexed)
    return indexed


def build_bm25_from_db(
    quotes: list[QuoteObject],
    index_path: Path,
    type_boost: dict[str, float],
) -> int:
    """BM25 인덱스를 QuoteObject에서 구축한다."""
    from scripts.lib.bm25_index import BM25Index

    bm25 = BM25Index.from_quotes(quotes, type_boost=type_boost)
    bm25.save(index_path)
    logger.info("BM25 인덱스 완료: %d개", bm25.size)
    return bm25.size


def main() -> None:
    parser = argparse.ArgumentParser(description="DB → Chroma + BM25 인덱스 구축")
    parser.add_argument("--db-path", type=Path, default=None, help="SQLite DB 경로")
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=Path("indexes/"),
        help="인덱스 출력 디렉토리",
    )
    parser.add_argument(
        "--collection-name",
        default="skms_quotes",
        help="Chroma 컬렉션명",
    )
    parser.add_argument(
        "--embedding-model",
        default="text-embedding-3-large",
        help="임베딩 모델",
    )
    parser.add_argument("--batch-size", type=int, default=100, help="임베딩 배치 크기")
    parser.add_argument(
        "--quality-exclude",
        nargs="*",
        default=["ocr_error"],
        help="제외할 quality_flags",
    )
    args = parser.parse_args()

    # DB 초기화 + 연결
    init_db(args.db_path)
    conn = get_connection(args.db_path)
    try:
        repo = QuoteRepository(conn)
        quotes = repo.find_excluding_flags(args.quality_exclude)
        total = repo.count_total()
        logger.info("DB: %d quotes (필터 후 %d개)", total, len(quotes))

        if not quotes:
            logger.error("적재된 quote가 없습니다. 먼저 10_ingest.py를 실행하세요.")
            sys.exit(1)

        # 타입별 통계
        type_counts: dict[str, int] = {}
        for q in quotes:
            type_counts[q.quote_type] = type_counts.get(q.quote_type, 0) + 1
        for t in sorted(type_counts, key=lambda x: type_counts[x], reverse=True):
            logger.info("  %s: %d개", t, type_counts[t])

        args.index_dir.mkdir(parents=True, exist_ok=True)

        # 벡터 인덱스
        vec_count = build_vector_index(
            quotes,
            args.index_dir,
            collection_name=args.collection_name,
            embedding_model=args.embedding_model,
            batch_size=args.batch_size,
        )

        # BM25 인덱스
        type_boost = {"definition": 2.0, "principle": 1.5}
        bm25_path = args.index_dir / "bm25_index.pkl"
        bm25_count = build_bm25_from_db(quotes, bm25_path, type_boost)

        # 메타데이터 저장
        meta = {
            "source": "db",
            "total_quotes_in_db": total,
            "filtered_quotes": len(quotes),
            "vector_indexed": vec_count,
            "bm25_indexed": bm25_count,
            "embedding_model": args.embedding_model,
            "quality_exclude": args.quality_exclude,
            "type_distribution": type_counts,
        }
        meta_path = args.index_dir / "meta.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        logger.info("메타: %s", meta_path)
        logger.info("완료: 벡터=%d, BM25=%d", vec_count, bm25_count)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
