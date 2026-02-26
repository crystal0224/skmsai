"""VectorStore 테스트 (EphemeralClient 기반).

PR-011: upsert, query, filter, fake embedding 검증.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

chromadb = pytest.importorskip("chromadb")

from scripts.lib.quote import QuoteObject  # noqa: E402
from scripts.lib.vector_store import (  # noqa: E402
    RawVectorHit,
    VectorStore,
    make_fake_embedding_fn,
    quote_to_chroma_metadata,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store():
    """테스트용 ephemeral VectorStore."""
    return VectorStore.ephemeral("test_collection")


@pytest.fixture()
def embed_fn():
    """테스트용 fake 임베딩 함수."""
    return make_fake_embedding_fn(dim=128)


def _make_test_quote(index: int = 0, **overrides) -> QuoteObject:
    """테스트용 QuoteObject 생성."""
    text = overrides.get("text", f"테스트 텍스트 {index}")
    edition_id = overrides.get("edition_id", "2020-14차")
    start_line = overrides.get("start_line", 15200 + index)
    return QuoteObject(
        quote_id=overrides.get("quote_id", f"2020-14차|VWBE|narrative|{index:03d}"),
        text=str(text),
        edition_id=str(edition_id),
        year=int(overrides.get("year", 2020)),
        revision_num=int(overrides.get("revision_num", 14)),
        quote_type=str(overrides.get("quote_type", "narrative")),
        section_path=overrides.get("section_path", ("VWBE Culture",)),
        start_line=int(start_line),
        char_span=overrides.get("char_span", (100, 200)),
        token_count=int(overrides.get("token_count", 20)),
        content_hash=QuoteObject.compute_hash(
            str(text), str(edition_id), int(start_line)
        ),
        quality_flags=overrides.get("quality_flags", ()),
        is_definition=bool(overrides.get("is_definition", False)),
    )


# ---------------------------------------------------------------------------
# VectorStore 기본 테스트
# ---------------------------------------------------------------------------


def test_ephemeral_store_is_available(store):
    """Ephemeral store는 available이다."""
    assert store.is_available is True


def test_unavailable_store():
    """None collection → unavailable."""
    store = VectorStore(None)
    assert store.is_available is False
    assert store.count() == 0
    assert store.query([0.1] * 128) == []
    assert store.upsert([], [], [], []) == 0


def test_upsert_and_count(store, embed_fn):
    """upsert 후 count가 증가한다."""
    assert store.count() == 0

    ids = ["q1", "q2"]
    embeddings = [embed_fn(f"text {i}") for i in range(2)]
    documents = ["text 0", "text 1"]
    metadatas = [{"edition_id": "2020-14차"}, {"edition_id": "1979-초판"}]

    result = store.upsert(ids, embeddings, documents, metadatas)
    assert result == 2
    assert store.count() == 2


def test_upsert_idempotent(store, embed_fn):
    """동일 ID 재upsert → count 불변."""
    ids = ["q1"]
    embeddings = [embed_fn("text")]
    documents = ["text"]
    metadatas = [{"edition_id": "2020-14차"}]

    store.upsert(ids, embeddings, documents, metadatas)
    assert store.count() == 1

    store.upsert(ids, embeddings, documents, metadatas)
    assert store.count() == 1


def test_query_returns_hits(store, embed_fn):
    """query는 RawVectorHit 리스트를 반환한다."""
    ids = ["q1", "q2", "q3"]
    embeddings = [embed_fn(f"doc {i}") for i in range(3)]
    documents = [f"doc {i}" for i in range(3)]
    metadatas = [
        {"edition_id": "2020-14차", "type": "narrative"},
        {"edition_id": "1979-초판", "type": "definition"},
        {"edition_id": "2020-14차", "type": "definition"},
    ]
    store.upsert(ids, embeddings, documents, metadatas)

    query_emb = embed_fn("doc 0")
    hits = store.query(query_emb, n_results=3)

    assert len(hits) > 0
    assert all(isinstance(h, RawVectorHit) for h in hits)
    assert hits[0].id in ids


def test_query_with_edition_filter(store, embed_fn):
    """edition_id 필터가 적용된다."""
    ids = ["q1", "q2"]
    embeddings = [embed_fn(f"text {i}") for i in range(2)]
    documents = ["text 0", "text 1"]
    metadatas = [
        {"edition_id": "2020-14차", "type": "narrative"},
        {"edition_id": "1979-초판", "type": "narrative"},
    ]
    store.upsert(ids, embeddings, documents, metadatas)

    query_emb = embed_fn("text 0")
    hits = store.query(
        query_emb,
        n_results=10,
        where={"edition_id": {"$eq": "2020-14차"}},
    )

    assert len(hits) == 1
    assert hits[0].metadata["edition_id"] == "2020-14차"


def test_query_with_type_filter(store, embed_fn):
    """type 필터가 적용된다."""
    ids = ["q1", "q2", "q3"]
    embeddings = [embed_fn(f"text {i}") for i in range(3)]
    documents = [f"text {i}" for i in range(3)]
    metadatas = [
        {"edition_id": "2020-14차", "type": "narrative"},
        {"edition_id": "2020-14차", "type": "definition"},
        {"edition_id": "2020-14차", "type": "checklist"},
    ]
    store.upsert(ids, embeddings, documents, metadatas)

    query_emb = embed_fn("text")
    hits = store.query(
        query_emb,
        n_results=10,
        where={"type": {"$eq": "definition"}},
    )

    assert len(hits) == 1
    assert hits[0].metadata["type"] == "definition"


# ---------------------------------------------------------------------------
# quote_to_chroma_metadata 테스트
# ---------------------------------------------------------------------------


def test_quote_to_chroma_metadata():
    """QuoteObject → Chroma metadata 변환."""
    q = _make_test_quote(
        quote_type="definition",
        section_path=("기업관", "1. 인간중심"),
        quality_flags=("ocr_error",),
    )
    meta = quote_to_chroma_metadata(q)

    assert meta["edition_id"] == "2020-14차"
    assert meta["type"] == "definition"  # quote_type → type
    assert meta["sha256"] == q.content_hash  # content_hash → sha256
    assert json.loads(meta["section_path"]) == ["기업관", "1. 인간중심"]
    assert json.loads(meta["quality_flags"]) == ["ocr_error"]
    assert meta["start_line"] == q.start_line
    assert meta["char_span_start"] == 100
    assert meta["char_span_end"] == 200


# ---------------------------------------------------------------------------
# Fake embedding 테스트
# ---------------------------------------------------------------------------


def test_fake_embedding_deterministic():
    """동일 텍스트 → 동일 임베딩."""
    fn = make_fake_embedding_fn(dim=64)
    e1 = fn("hello")
    e2 = fn("hello")
    assert e1 == e2


def test_fake_embedding_different_texts():
    """다른 텍스트 → 다른 임베딩."""
    fn = make_fake_embedding_fn(dim=64)
    e1 = fn("hello")
    e2 = fn("world")
    assert e1 != e2


def test_fake_embedding_correct_dimension():
    """임베딩 차원이 올바르다."""
    fn = make_fake_embedding_fn(dim=128)
    e = fn("test")
    assert len(e) == 128


# ---------------------------------------------------------------------------
# RawVectorHit 테스트
# ---------------------------------------------------------------------------


def test_raw_vector_hit_is_frozen():
    """RawVectorHit는 불변이다."""
    hit = RawVectorHit(id="q1", document="text", distance=0.1, metadata={})
    with pytest.raises(AttributeError):
        hit.distance = 0.5  # type: ignore[misc]
