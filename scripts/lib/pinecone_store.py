"""PineconeStore — Pinecone 벡터 스토어 구현.

PR-031: Chroma → Pinecone 마이그레이션.

VectorStore와 동일한 인터페이스를 제공하여 SearchService에서
투명하게 교체 가능하다.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from scripts.lib.vector_store import RawVectorHit

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PineconeConfig — Pinecone 설정 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PineconeConfig:
    """Pinecone 벡터 스토어 설정.

    Attributes:
        api_key: Pinecone API 키 (환경변수에서 로드)
        index_name: Pinecone 인덱스 이름
        namespace: Pinecone 네임스페이스 (빈 문자열이면 기본)
        metric: 거리 메트릭 (cosine, euclidean, dotproduct)
        dimension: 벡터 차원 수
        cloud: Pinecone 클라우드 (aws, gcp, azure)
        region: Pinecone 리전
    """

    api_key: str = ""
    index_name: str = "skms-quotes"
    namespace: str = ""
    metric: str = "cosine"
    dimension: int = 3072  # text-embedding-3-large
    cloud: str = "aws"
    region: str = "us-east-1"

    @classmethod
    def from_dict(cls, data: dict[str, Any], api_key: str = "") -> PineconeConfig:
        """dict에서 설정을 로드한다."""
        return cls(
            api_key=api_key or data.get("api_key", ""),
            index_name=data.get("index_name", "skms-quotes"),
            namespace=data.get("namespace", ""),
            metric=data.get("metric", "cosine"),
            dimension=int(data.get("dimension", 3072)),
            cloud=data.get("cloud", "aws"),
            region=data.get("region", "us-east-1"),
        )


# ---------------------------------------------------------------------------
# PineconeStore — Pinecone 벡터 스토어
# ---------------------------------------------------------------------------


class PineconeStore:
    """Pinecone 벡터 스토어.

    VectorStore와 동일한 인터페이스를 제공한다.
    is_available, count(), upsert(), query(), build_where().
    """

    def __init__(
        self,
        index: Any | None = None,
        *,
        namespace: str = "",
    ) -> None:
        self._index = index
        self._namespace = namespace

    @classmethod
    def from_config(cls, config: PineconeConfig) -> PineconeStore:
        """PineconeConfig에서 스토어를 생성한다.

        Pinecone SDK가 없거나 API 키가 없으면 비활성 스토어를 반환한다.
        """
        if not config.api_key:
            logger.warning("Pinecone API 키 없음")
            return cls(None, namespace=config.namespace)

        try:
            from pinecone import Pinecone

            pc = Pinecone(api_key=config.api_key)

            # 인덱스 존재 확인 및 생성
            existing = [idx.name for idx in pc.list_indexes()]
            if config.index_name not in existing:
                from pinecone import ServerlessSpec

                pc.create_index(
                    name=config.index_name,
                    dimension=config.dimension,
                    metric=config.metric,
                    spec=ServerlessSpec(
                        cloud=config.cloud,
                        region=config.region,
                    ),
                )
                logger.info(
                    "Pinecone 인덱스 생성: %s (%s, dim=%d)",
                    config.index_name,
                    config.metric,
                    config.dimension,
                )

            index = pc.Index(config.index_name)
            return cls(index, namespace=config.namespace)

        except ImportError:
            logger.warning("pinecone 패키지 없음")
            return cls(None, namespace=config.namespace)
        except Exception as e:
            logger.error("Pinecone 초기화 실패: %s", e)
            return cls(None, namespace=config.namespace)

    @property
    def is_available(self) -> bool:
        """인덱스가 사용 가능한지 반환한다."""
        return self._index is not None

    def count(self) -> int:
        """인덱스의 벡터 수를 반환한다."""
        if not self.is_available:
            return 0
        try:
            stats = self._index.describe_index_stats()
            ns_stats = stats.get("namespaces", {})
            if self._namespace:
                return ns_stats.get(self._namespace, {}).get("vector_count", 0)
            return stats.get("total_vector_count", 0)
        except Exception:
            return 0

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

        # Pinecone은 metadata에 document를 포함
        vectors: list[dict[str, Any]] = []
        for i, vid in enumerate(ids):
            meta = dict(metadatas[i])
            meta["_document"] = documents[i]
            vectors.append(
                {
                    "id": vid,
                    "values": embeddings[i],
                    "metadata": meta,
                }
            )

        # 배치 처리 (Pinecone 제한: 1000 vectors/request)
        batch_size = 100
        total = 0
        for start in range(0, len(vectors), batch_size):
            batch = vectors[start : start + batch_size]
            try:
                self._index.upsert(
                    vectors=batch,
                    namespace=self._namespace or None,
                )
                total += len(batch)
            except Exception as e:
                logger.error("Pinecone upsert 실패 (batch %d): %s", start, e)

        return total

    def query(
        self,
        embedding: list[float],
        n_results: int = 10,
        where: dict | None = None,
    ) -> list[RawVectorHit]:
        """벡터 유사도 검색을 수행한다.

        VectorStore.query()와 동일한 인터페이스.
        Pinecone 결과를 RawVectorHit으로 변환한다.
        """
        if not self.is_available:
            return []

        kwargs: dict[str, Any] = {
            "vector": embedding,
            "top_k": n_results,
            "include_metadata": True,
        }
        if self._namespace:
            kwargs["namespace"] = self._namespace
        if where:
            kwargs["filter"] = where

        try:
            results = self._index.query(**kwargs)
        except Exception as e:
            logger.error("Pinecone query 실패: %s", e)
            return []

        hits: list[RawVectorHit] = []
        for match in results.get("matches", []):
            metadata = dict(match.get("metadata", {}))
            document = metadata.pop("_document", "")
            # Pinecone score는 유사도 (1=동일, 0=무관) — cosine distance = 1 - score
            score = match.get("score", 0.0)
            distance = 1.0 - score

            hits.append(
                RawVectorHit(
                    id=match["id"],
                    document=document,
                    distance=distance,
                    metadata=metadata,
                )
            )

        return hits

    @staticmethod
    def build_where(
        edition_filter: str | None,
        type_filter: list[str] | None,
    ) -> dict | None:
        """Pinecone 메타데이터 필터를 조합한다.

        Pinecone filter 형식: {"field": {"$op": value}}
        """
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


# ---------------------------------------------------------------------------
# 팩토리 함수
# ---------------------------------------------------------------------------


def create_vector_store(
    config: dict[str, Any],
    index_dir: Path = Path("indexes"),
) -> Any:
    """retrieval.yaml 설정으로 벡터 스토어를 생성한다.

    provider가 "pinecone"이면 PineconeStore, 그 외에는 VectorStore(Chroma).

    Args:
        config: retrieval.yaml의 vector 섹션
        index_dir: Chroma용 인덱스 디렉토리

    Returns:
        VectorStore 또는 PineconeStore
    """
    import os

    provider = config.get("provider", "chroma")

    if provider == "pinecone":
        api_key = os.environ.get("PINECONE_API_KEY", "")
        pinecone_config = config.get("pinecone", {})
        pc_config = PineconeConfig.from_dict(pinecone_config, api_key=api_key)
        store = PineconeStore.from_config(pc_config)
        logger.info(
            "PineconeStore 생성: index=%s, available=%s",
            pc_config.index_name,
            store.is_available,
        )
        return store

    # 기본: Chroma
    from scripts.lib.vector_store import VectorStore

    collection_name = config.get("collection_name", "skms_quotes")
    store = VectorStore.from_path(index_dir, collection_name=collection_name)
    logger.info(
        "VectorStore(Chroma) 생성: collection=%s, available=%s",
        collection_name,
        store.is_available,
    )
    return store
