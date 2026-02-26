"""PineconeStore 테스트.

PR-031: Pinecone 마이그레이션 (Chroma → Pinecone) 단위/통합 테스트.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import MappingProxyType
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.pinecone_store import (  # noqa: E402
    PineconeConfig,
    PineconeStore,
    create_vector_store,
)
from scripts.lib.vector_store import RawVectorHit, VectorStore  # noqa: E402


# ---------------------------------------------------------------------------
# PineconeConfig 테스트
# ---------------------------------------------------------------------------


class TestPineconeConfig:
    """PineconeConfig 테스트."""

    def test_defaults(self):
        """기본값 확인."""
        config = PineconeConfig()
        assert config.api_key == ""
        assert config.index_name == "skms-quotes"
        assert config.namespace == ""
        assert config.metric == "cosine"
        assert config.dimension == 3072
        assert config.cloud == "aws"
        assert config.region == "us-east-1"

    def test_is_frozen(self):
        """불변이다."""
        config = PineconeConfig()
        with pytest.raises(AttributeError):
            config.api_key = "new-key"  # type: ignore[misc]

    def test_from_dict(self):
        """dict에서 생성."""
        data = {
            "index_name": "custom-index",
            "namespace": "test",
            "dimension": 1536,
            "cloud": "gcp",
            "region": "us-central1",
        }
        config = PineconeConfig.from_dict(data, api_key="test-key")
        assert config.api_key == "test-key"
        assert config.index_name == "custom-index"
        assert config.namespace == "test"
        assert config.dimension == 1536
        assert config.cloud == "gcp"

    def test_from_dict_defaults(self):
        """빈 dict에서 기본값."""
        config = PineconeConfig.from_dict({})
        assert config.index_name == "skms-quotes"
        assert config.dimension == 3072


# ---------------------------------------------------------------------------
# PineconeStore 초기화 테스트
# ---------------------------------------------------------------------------


class TestPineconeStoreInit:
    """PineconeStore 초기화 테스트."""

    def test_none_index(self):
        """index=None → 비활성."""
        store = PineconeStore(None)
        assert store.is_available is False
        assert store.count() == 0

    def test_with_index(self):
        """index 지정 → 활성."""
        mock_index = MagicMock()
        store = PineconeStore(mock_index)
        assert store.is_available is True

    def test_from_config_no_api_key(self):
        """API 키 없음 → 비활성."""
        config = PineconeConfig(api_key="")
        store = PineconeStore.from_config(config)
        assert store.is_available is False

    def test_from_config_no_pinecone_package(self):
        """pinecone 패키지 없음 → 비활성."""
        config = PineconeConfig(api_key="test-key")
        with patch.dict("sys.modules", {"pinecone": None}):
            store = PineconeStore.from_config(config)
            assert store.is_available is False


# ---------------------------------------------------------------------------
# PineconeStore.count 테스트
# ---------------------------------------------------------------------------


class TestPineconeStoreCount:
    """PineconeStore.count 테스트."""

    def test_count_no_namespace(self):
        """네임스페이스 없는 카운트."""
        mock_index = MagicMock()
        mock_index.describe_index_stats.return_value = {
            "total_vector_count": 42,
            "namespaces": {},
        }
        store = PineconeStore(mock_index)
        assert store.count() == 42

    def test_count_with_namespace(self):
        """네임스페이스별 카운트."""
        mock_index = MagicMock()
        mock_index.describe_index_stats.return_value = {
            "total_vector_count": 100,
            "namespaces": {"test-ns": {"vector_count": 30}},
        }
        store = PineconeStore(mock_index, namespace="test-ns")
        assert store.count() == 30

    def test_count_error(self):
        """에러 시 0."""
        mock_index = MagicMock()
        mock_index.describe_index_stats.side_effect = RuntimeError("API 오류")
        store = PineconeStore(mock_index)
        assert store.count() == 0

    def test_count_unavailable(self):
        """비활성 → 0."""
        store = PineconeStore(None)
        assert store.count() == 0


# ---------------------------------------------------------------------------
# PineconeStore.upsert 테스트
# ---------------------------------------------------------------------------


class TestPineconeStoreUpsert:
    """PineconeStore.upsert 테스트."""

    def test_basic_upsert(self):
        """기본 upsert."""
        mock_index = MagicMock()
        store = PineconeStore(mock_index)

        count = store.upsert(
            ids=["id1", "id2"],
            embeddings=[[0.1, 0.2], [0.3, 0.4]],
            documents=["doc1", "doc2"],
            metadatas=[{"edition_id": "2020-14차"}, {"edition_id": "1979-초판"}],
        )

        assert count == 2
        mock_index.upsert.assert_called_once()

        # _document가 metadata에 포함되었는지 확인
        call_kwargs = mock_index.upsert.call_args
        vectors = call_kwargs.kwargs.get("vectors", call_kwargs[1].get("vectors", []))
        assert vectors[0]["metadata"]["_document"] == "doc1"

    def test_upsert_unavailable(self):
        """비활성 → 0."""
        store = PineconeStore(None)
        count = store.upsert(
            ids=["id1"],
            embeddings=[[0.1]],
            documents=["doc"],
            metadatas=[{}],
        )
        assert count == 0

    def test_upsert_with_namespace(self):
        """네임스페이스 포함 upsert."""
        mock_index = MagicMock()
        store = PineconeStore(mock_index, namespace="test-ns")

        store.upsert(
            ids=["id1"],
            embeddings=[[0.1]],
            documents=["doc"],
            metadatas=[{}],
        )

        call_kwargs = mock_index.upsert.call_args
        assert call_kwargs.kwargs.get("namespace") == "test-ns"


# ---------------------------------------------------------------------------
# PineconeStore.query 테스트
# ---------------------------------------------------------------------------


class TestPineconeStoreQuery:
    """PineconeStore.query 테스트."""

    def test_basic_query(self):
        """기본 쿼리."""
        mock_index = MagicMock()
        mock_index.query.return_value = {
            "matches": [
                {
                    "id": "q1",
                    "score": 0.95,
                    "metadata": {
                        "_document": "SUPEX 정의 텍스트",
                        "edition_id": "2020-14차",
                        "type": "definition",
                    },
                },
                {
                    "id": "q2",
                    "score": 0.80,
                    "metadata": {
                        "_document": "VWBE 설명",
                        "edition_id": "2020-14차",
                        "type": "narrative",
                    },
                },
            ]
        }
        store = PineconeStore(mock_index)

        hits = store.query(embedding=[0.1, 0.2, 0.3], n_results=5)

        assert len(hits) == 2
        assert hits[0].id == "q1"
        assert hits[0].document == "SUPEX 정의 텍스트"
        assert hits[0].distance == pytest.approx(0.05)  # 1.0 - 0.95
        # _document가 metadata에서 제거되었는지 확인
        assert "_document" not in hits[0].metadata

    def test_query_with_filter(self):
        """필터 포함 쿼리."""
        mock_index = MagicMock()
        mock_index.query.return_value = {"matches": []}
        store = PineconeStore(mock_index)

        where = {"edition_id": {"$eq": "2020-14차"}}
        store.query(embedding=[0.1], n_results=5, where=where)

        call_kwargs = mock_index.query.call_args.kwargs
        assert call_kwargs["filter"] == where

    def test_query_unavailable(self):
        """비활성 → 빈 결과."""
        store = PineconeStore(None)
        hits = store.query(embedding=[0.1], n_results=5)
        assert hits == []

    def test_query_error(self):
        """API 에러 → 빈 결과."""
        mock_index = MagicMock()
        mock_index.query.side_effect = RuntimeError("API 오류")
        store = PineconeStore(mock_index)

        hits = store.query(embedding=[0.1], n_results=5)
        assert hits == []

    def test_query_returns_raw_vector_hit(self):
        """결과가 RawVectorHit 타입."""
        mock_index = MagicMock()
        mock_index.query.return_value = {
            "matches": [
                {
                    "id": "q1",
                    "score": 0.9,
                    "metadata": {"_document": "text", "edition_id": "test"},
                }
            ]
        }
        store = PineconeStore(mock_index)
        hits = store.query(embedding=[0.1])

        assert isinstance(hits[0], RawVectorHit)


# ---------------------------------------------------------------------------
# PineconeStore.build_where 테스트
# ---------------------------------------------------------------------------


class TestPineconeStoreBuildWhere:
    """PineconeStore.build_where 테스트."""

    def test_no_filters(self):
        """필터 없음 → None."""
        assert PineconeStore.build_where(None, None) is None

    def test_edition_only(self):
        """개정판만."""
        result = PineconeStore.build_where("2020-14차", None)
        assert result == {"edition_id": {"$eq": "2020-14차"}}

    def test_type_single(self):
        """타입 단일."""
        result = PineconeStore.build_where(None, ["definition"])
        assert result == {"type": {"$eq": "definition"}}

    def test_type_multiple(self):
        """타입 복수."""
        result = PineconeStore.build_where(None, ["definition", "narrative"])
        assert result == {"type": {"$in": ["definition", "narrative"]}}

    def test_both_filters(self):
        """개정판 + 타입."""
        result = PineconeStore.build_where("2020-14차", ["definition"])
        assert result == {
            "$and": [
                {"edition_id": {"$eq": "2020-14차"}},
                {"type": {"$eq": "definition"}},
            ]
        }


# ---------------------------------------------------------------------------
# VectorStore.build_where 테스트 (Chroma — PR-031 추가)
# ---------------------------------------------------------------------------


class TestVectorStoreBuildWhere:
    """VectorStore.build_where 테스트 (기존 _build_where 이전)."""

    def test_no_filters(self):
        """필터 없음 → None."""
        assert VectorStore.build_where(None, None) is None

    def test_edition_only(self):
        """개정판만."""
        result = VectorStore.build_where("2020-14차", None)
        assert result == {"edition_id": {"$eq": "2020-14차"}}

    def test_type_single(self):
        """타입 단일."""
        result = VectorStore.build_where(None, ["definition"])
        assert result == {"type": {"$eq": "definition"}}

    def test_type_multiple(self):
        """타입 복수."""
        result = VectorStore.build_where(None, ["definition", "narrative"])
        assert result == {"type": {"$in": ["definition", "narrative"]}}

    def test_both_filters(self):
        """개정판 + 타입."""
        result = VectorStore.build_where("2020-14차", ["definition"])
        assert result == {
            "$and": [
                {"edition_id": {"$eq": "2020-14차"}},
                {"type": {"$eq": "definition"}},
            ]
        }


# ---------------------------------------------------------------------------
# create_vector_store 팩토리 테스트
# ---------------------------------------------------------------------------


class TestCreateVectorStore:
    """create_vector_store 팩토리 테스트."""

    def test_default_chroma(self, tmp_path: Path):
        """기본 provider=chroma → VectorStore."""
        config = {"provider": "chroma", "collection_name": "test"}
        store = create_vector_store(config, tmp_path)
        assert isinstance(store, VectorStore)

    def test_explicit_chroma(self, tmp_path: Path):
        """명시적 chroma → VectorStore."""
        config = {"provider": "chroma", "collection_name": "test"}
        store = create_vector_store(config, tmp_path)
        assert isinstance(store, VectorStore)

    def test_pinecone_no_api_key(self, tmp_path: Path):
        """pinecone + API 키 없음 → 비활성 PineconeStore."""
        config = {
            "provider": "pinecone",
            "pinecone": {"index_name": "test"},
        }
        with patch.dict("os.environ", {}, clear=False):
            # PINECONE_API_KEY가 없으면 비활성
            import os

            old_key = os.environ.pop("PINECONE_API_KEY", None)
            try:
                store = create_vector_store(config, tmp_path)
                assert isinstance(store, PineconeStore)
                assert store.is_available is False
            finally:
                if old_key is not None:
                    os.environ["PINECONE_API_KEY"] = old_key

    def test_missing_provider_defaults_chroma(self, tmp_path: Path):
        """provider 미지정 → chroma."""
        config = {"collection_name": "test"}
        store = create_vector_store(config, tmp_path)
        assert isinstance(store, VectorStore)


# ---------------------------------------------------------------------------
# SearchService 호환성 테스트
# ---------------------------------------------------------------------------


class TestSearchServiceCompatibility:
    """SearchService와 PineconeStore 호환성 테스트."""

    def test_pinecone_store_in_search_service(self):
        """PineconeStore가 SearchService에서 동작."""
        from scripts.lib.search_service import SearchService

        mock_index = MagicMock()
        mock_index.query.return_value = {
            "matches": [
                {
                    "id": "2020-14차|SUPEX|definition|001",
                    "score": 0.95,
                    "metadata": {
                        "_document": "SUPEX 정의 텍스트",
                        "edition_id": "2020-14차",
                        "type": "definition",
                        "section_path": '["SUPEX 추구"]',
                        "sha256": "abc123",
                        "quality_flags": "[]",
                    },
                }
            ]
        }

        store = PineconeStore(mock_index)

        def fake_embed(text: str) -> list[float]:
            return [0.1] * 10

        svc = SearchService(
            vector_store=store,
            embedding_fn=fake_embed,
        )

        hits = svc.vector_search("SUPEX란?", top_k=5, score_threshold=0.0)

        assert len(hits) == 1
        assert hits[0].quote_id == "2020-14차|SUPEX|definition|001"
        assert hits[0].edition_id == "2020-14차"
        assert hits[0].text == "SUPEX 정의 텍스트"

    def test_chroma_store_still_works(self):
        """기존 VectorStore(Chroma)가 여전히 동작."""
        store = VectorStore(None)
        assert store.is_available is False

        where = VectorStore.build_where("2020-14차", None)
        assert where == {"edition_id": {"$eq": "2020-14차"}}


# ---------------------------------------------------------------------------
# 통합 테스트
# ---------------------------------------------------------------------------


class TestPineconeStoreIntegration:
    """통합 테스트."""

    def test_upsert_and_query_flow(self):
        """upsert → query 전체 흐름 (mock)."""
        mock_index = MagicMock()

        # upsert
        store = PineconeStore(mock_index)
        count = store.upsert(
            ids=["id1"],
            embeddings=[[0.1, 0.2]],
            documents=["SUPEX 정의"],
            metadatas=[{"edition_id": "2020-14차", "type": "definition"}],
        )
        assert count == 1

        # query
        mock_index.query.return_value = {
            "matches": [
                {
                    "id": "id1",
                    "score": 0.9,
                    "metadata": {
                        "_document": "SUPEX 정의",
                        "edition_id": "2020-14차",
                        "type": "definition",
                    },
                }
            ]
        }
        hits = store.query(embedding=[0.1, 0.2], n_results=1)
        assert len(hits) == 1
        assert hits[0].document == "SUPEX 정의"

    def test_build_where_consistency(self):
        """VectorStore와 PineconeStore의 build_where 일관성."""
        # 동일한 입력에 동일한 출력
        chroma_result = VectorStore.build_where("2020-14차", ["definition"])
        pine_result = PineconeStore.build_where("2020-14차", ["definition"])

        assert chroma_result == pine_result

    def test_config_to_store_pipeline(self, tmp_path: Path):
        """설정 → 팩토리 → 스토어 전체 흐름."""
        # Chroma
        config_chroma = {"provider": "chroma", "collection_name": "test"}
        store_chroma = create_vector_store(config_chroma, tmp_path)
        assert isinstance(store_chroma, VectorStore)

        # Pinecone (API 키 없음 → 비활성)
        import os

        old_key = os.environ.pop("PINECONE_API_KEY", None)
        try:
            config_pine = {
                "provider": "pinecone",
                "pinecone": {"index_name": "test"},
            }
            store_pine = create_vector_store(config_pine, tmp_path)
            assert isinstance(store_pine, PineconeStore)
            assert store_pine.is_available is False
        finally:
            if old_key is not None:
                os.environ["PINECONE_API_KEY"] = old_key
