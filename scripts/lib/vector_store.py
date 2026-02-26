"""VectorStore — Chroma 벡터 스토어 추상화.

PR-011: DB 소스 인덱스 구축 + 검색 API.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable

from scripts.lib.quote import QuoteObject

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RawVectorHit:
    """Chroma query() 결과 단건."""

    id: str
    document: str
    distance: float
    metadata: Any  # MappingProxyType (immutable dict)

    def __post_init__(self) -> None:
        if isinstance(self.metadata, dict):
            object.__setattr__(self, "metadata", MappingProxyType(self.metadata))


class VectorStore:
    """Chroma 벡터 스토어 래퍼.

    Injectable: 테스트 시 EphemeralClient 사용.
    production에서는 from_path()로 PersistentClient 생성.
    """

    def __init__(self, collection: Any | None) -> None:
        self._collection = collection

    @classmethod
    def from_path(cls, path: Path, collection_name: str = "skms_quotes") -> VectorStore:
        """PersistentClient에서 컬렉션을 로드한다."""
        try:
            import chromadb
        except ImportError:
            logger.warning("chromadb 패키지 없음")
            return cls(None)

        chroma_path = path if str(path).endswith("chroma") else path / "chroma"
        if not chroma_path.exists():
            logger.warning("Chroma 인덱스 경로 없음: %s", chroma_path)
            return cls(None)

        client = chromadb.PersistentClient(path=str(chroma_path))
        try:
            collection = client.get_collection(collection_name)
        except Exception:
            logger.warning("컬렉션 '%s' 없음, 새로 생성", collection_name)
            collection = client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return cls(collection)

    @classmethod
    def ephemeral(cls, collection_name: str = "skms_quotes") -> VectorStore:
        """테스트용 in-memory 스토어를 생성한다."""
        import chromadb

        client = chromadb.EphemeralClient()
        # 테스트 격리: 기존 컬렉션 삭제 후 재생성
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass
        collection = client.create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        return cls(collection)

    @property
    def is_available(self) -> bool:
        return self._collection is not None

    def count(self) -> int:
        if not self.is_available:
            return 0
        return self._collection.count()

    def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> int:
        """벡터를 upsert한다. 삽입된 건수를 반환한다."""
        if not self.is_available:
            return 0
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        return len(ids)

    def query(
        self,
        embedding: list[float],
        n_results: int = 10,
        where: dict | None = None,
    ) -> list[RawVectorHit]:
        """벡터 유사도 검색을 수행한다."""
        if not self.is_available:
            return []

        kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": n_results,
        }
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)

        hits: list[RawVectorHit] = []
        if results and results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                hits.append(
                    RawVectorHit(
                        id=doc_id,
                        document=(
                            results["documents"][0][i] if results["documents"] else ""
                        ),
                        distance=(
                            results["distances"][0][i] if results["distances"] else 0.0
                        ),
                        metadata=(
                            results["metadatas"][0][i] if results["metadatas"] else {}
                        ),
                    )
                )
        return hits


# ---------------------------------------------------------------------------
# QuoteObject ↔ Chroma 변환 헬퍼
# ---------------------------------------------------------------------------


def quote_to_chroma_metadata(quote: QuoteObject) -> dict:
    """QuoteObject → Chroma 메타데이터 dict.

    기존 인덱스 호환: type (not quote_type), sha256 (not content_hash).
    """
    return {
        "edition_id": quote.edition_id,
        "type": quote.quote_type,
        "section_path": json.dumps(list(quote.section_path), ensure_ascii=False),
        "start_line": quote.start_line,
        "char_span_start": quote.char_span[0],
        "char_span_end": quote.char_span[1],
        "token_count": quote.token_count,
        "sha256": quote.content_hash,
        "quality_flags": json.dumps(list(quote.quality_flags), ensure_ascii=False),
    }


# ---------------------------------------------------------------------------
# 테스트용 fake 임베딩 함수
# ---------------------------------------------------------------------------


def make_fake_embedding_fn(
    dim: int = 1536, seed: int = 42
) -> Callable[[str], list[float]]:
    """테스트용 결정론적 임베딩 함수.

    동일 텍스트에 대해 항상 같은 벡터를 반환한다.
    """
    import random

    def _embed(text: str) -> list[float]:
        rng = random.Random(hash(text) % (2**32) + seed)
        return [rng.uniform(-1, 1) for _ in range(dim)]

    return _embed
