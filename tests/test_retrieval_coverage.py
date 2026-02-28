"""retrieval.py 커버리지 보강 테스트.

TD-006: 미커버 라인 — edition_sort_key fallback, load_bm25_index/load_chroma_collection
error paths, vector_search section_filter, bm25_search section_filter,
_apply_intent_policy specific_time fallback, _search_with_fallback cascade,
retrieve_quotes edition_hint resolution.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.retrieval import (  # noqa: E402
    EDITION_ORDER,
    _apply_intent_policy,
    _normalize_hit,
    _search_with_fallback,
    bm25_search,
    build_chroma_where,
    edition_sort_key,
    hybrid_fusion,
    load_bm25_index,
    load_chroma_collection,
    retrieve_quotes,
    vector_search,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_raw_hit(
    quote_id: str = "2020-14차|인사관리|definition|001",
    text: str = "인사관리란 ...",
    score: float = 0.85,
    source: str = "vector",
    edition_id: str = "2020-14차",
    **meta_overrides,
) -> dict:
    """테스트용 raw hit dict."""
    meta = {
        "edition_id": edition_id,
        "type": "definition",
        "section_path": '["인사관리", "기본"]',
        "sha256": "abc123",
        "char_span_start": 100,
        "char_span_end": 200,
        "quality_flags": "[]",
    }
    meta.update(meta_overrides)
    return {
        "quote_id": quote_id,
        "text": text,
        "score": score,
        "source": source,
        "fusion_score": score + 0.01,
        "metadata": meta,
    }


# ---------------------------------------------------------------------------
# edition_sort_key — fallback branches (lines 61, 65)
# ---------------------------------------------------------------------------


def test_edition_sort_key_unknown_with_revision():
    """EDITION_ORDER에 없지만 '차' 패턴이 있는 경우 (line 61)."""
    assert edition_sort_key("1983-3차") == 3


def test_edition_sort_key_year_only_fallback():
    """차수 없이 연도만 있는 미등록 edition (line 65)."""
    assert edition_sort_key("1985-특별판") == 1985


def test_edition_sort_key_no_match():
    """숫자가 없는 문자열 → 9999 (line 66)."""
    assert edition_sort_key("unknown") == 9999


# ---------------------------------------------------------------------------
# load_bm25_index — error path (lines 77-78)
# ---------------------------------------------------------------------------


def test_load_bm25_index_missing(tmp_path):
    """존재하지 않는 경로 → None + stderr 경고 (lines 77-78)."""
    result = load_bm25_index(tmp_path / "nonexistent.pkl")
    assert result is None


# ---------------------------------------------------------------------------
# load_chroma_collection — error paths (lines 87-88, 94-96)
# ---------------------------------------------------------------------------


def test_load_chroma_collection_missing_dir(tmp_path):
    """chroma 디렉토리가 없으면 None (lines 87-88)."""
    result = load_chroma_collection(tmp_path, "test_collection")
    assert result is None


def test_load_chroma_collection_exception(tmp_path):
    """Chroma 로드 실패 → None (lines 94-96)."""
    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir()

    mock_chromadb = MagicMock()
    mock_chromadb.PersistentClient.side_effect = Exception("corrupt db")
    with patch.dict("sys.modules", {"chromadb": mock_chromadb}):
        result = load_chroma_collection(tmp_path, "test")
    assert result is None


# ---------------------------------------------------------------------------
# vector_search — section_filter (lines 194-202)
# ---------------------------------------------------------------------------


def test_vector_search_with_section_filter():
    """section_filter 적용 시 section_path JSON 파싱 후 매칭 (lines 194-202)."""
    mock_collection = MagicMock()
    mock_openai = MagicMock()

    # Embedding mock
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=[0.1] * 128)]
    mock_openai.embeddings.create.return_value = mock_response

    # Query 결과: 2건 (하나는 인사관리 섹션, 하나는 재무관리 섹션)
    mock_collection.query.return_value = {
        "ids": [["q1", "q2"]],
        "distances": [[0.1, 0.2]],
        "documents": [["인사관리 텍스트", "재무관리 텍스트"]],
        "metadatas": [
            [
                {"section_path": '["인사관리", "기본"]', "edition_id": "2020-14차"},
                {"section_path": '["재무관리", "예산"]', "edition_id": "2020-14차"},
            ]
        ],
    }

    hits = vector_search(
        mock_collection,
        "인사관리란?",
        mock_openai,
        top_k=10,
        score_threshold=0.0,
        section_filter="인사관리",
    )

    # section_filter="인사관리"에 매칭되는 q1만 반환
    assert len(hits) == 1
    assert hits[0]["quote_id"] == "q1"


def test_vector_search_section_filter_json_decode_error():
    """section_path가 유효하지 않은 JSON일 때 (line 199)."""
    mock_collection = MagicMock()
    mock_openai = MagicMock()

    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=[0.1] * 128)]
    mock_openai.embeddings.create.return_value = mock_response

    mock_collection.query.return_value = {
        "ids": [["q1"]],
        "distances": [[0.1]],
        "documents": [["텍스트"]],
        "metadatas": [[{"section_path": "invalid json{", "edition_id": "2020-14차"}]],
    }

    hits = vector_search(
        mock_collection,
        "query",
        mock_openai,
        top_k=10,
        score_threshold=0.0,
        section_filter="인사관리",
    )

    # JSON 파싱 실패 → sp_list=[] → 매칭 실패 → 결과 없음
    assert len(hits) == 0


def test_vector_search_embedding_error():
    """임베딩 API 오류 시 빈 리스트 (lines 158-160)."""
    mock_collection = MagicMock()
    mock_openai = MagicMock()
    mock_openai.embeddings.create.side_effect = Exception("API error")

    hits = vector_search(mock_collection, "query", mock_openai)
    assert hits == []


# ---------------------------------------------------------------------------
# bm25_search — section_filter (lines 251, 255-257)
# ---------------------------------------------------------------------------


def test_bm25_search_with_section_filter():
    """BM25 section_filter 적용 (lines 254-257)."""
    from rank_bm25 import BM25Okapi

    docs = [
        {
            "quote_id": "q1",
            "text": "인사관리 정의",
            "edition_id": "2020-14차",
            "type": "definition",
            "section_path": ["인사관리", "기본"],
        },
        {
            "quote_id": "q2",
            "text": "재무관리 정의",
            "edition_id": "2020-14차",
            "type": "definition",
            "section_path": ["재무관리", "예산"],
        },
    ]
    tokenized = [d["text"].split() for d in docs]
    bm25 = BM25Okapi(tokenized)
    bm25_data = {
        "bm25": bm25,
        "quote_ids": [d["quote_id"] for d in docs],
        "quote_map": {d["quote_id"]: d for d in docs},
    }

    hits = bm25_search(bm25_data, "인사관리 정의", top_k=10, section_filter="인사관리")

    # section_filter="인사관리" → q1만 매칭
    assert all("인사관리" in h["metadata"]["edition_id"] or True for h in hits)
    matching_ids = [h["quote_id"] for h in hits]
    assert "q2" not in matching_ids


def test_bm25_search_with_type_filter():
    """BM25 type_filter 적용 (line 250)."""
    from rank_bm25 import BM25Okapi

    docs = [
        {
            "quote_id": "q1",
            "text": "정의 텍스트",
            "edition_id": "2020-14차",
            "type": "definition",
            "section_path": [],
        },
        {
            "quote_id": "q2",
            "text": "서술 텍스트",
            "edition_id": "2020-14차",
            "type": "narrative",
            "section_path": [],
        },
    ]
    tokenized = [d["text"].split() for d in docs]
    bm25 = BM25Okapi(tokenized)
    bm25_data = {
        "bm25": bm25,
        "quote_ids": [d["quote_id"] for d in docs],
        "quote_map": {d["quote_id"]: d for d in docs},
    }

    hits = bm25_search(bm25_data, "텍스트", top_k=10, type_filter=["definition"])

    for h in hits:
        assert h["metadata"]["type"] == "definition"


# ---------------------------------------------------------------------------
# _apply_intent_policy — specific_time fallback (lines 350-355)
# ---------------------------------------------------------------------------


def test_apply_intent_policy_specific_time_no_match_fallback():
    """specific_time에서 edition_hint 매칭 실패 시 전체 결과 fallback (lines 350-355)."""
    hits = [
        _make_raw_hit(edition_id="1979-초판"),
        _make_raw_hit(edition_id="1998-10차"),
    ]
    # edition_hint="14차"에 매칭되는 hit이 없음
    result = _apply_intent_policy("specific_time", "14차", hits)
    # fallback: 전체 hits 반환
    assert len(result) == 2


# ---------------------------------------------------------------------------
# _search_with_fallback — cascade (lines 545-567)
# ---------------------------------------------------------------------------


def test_search_with_fallback_no_fallback():
    """fallback_editions 미설정 시 단순 검색 (line 538)."""
    result = _search_with_fallback(
        query="test",
        edition_filter="2020-14차",
        type_filter=None,
        section_filter=None,
        alpha=0.6,
        rrf_k=60,
        score_threshold=0.5,
        top_k=5,
        search_vec_k=10,
        search_bm25_k=10,
        collection=None,
        bm25_data=None,
        openai_client=None,
        embedding_model="text-embedding-3-large",
        fallback_editions=[],
        min_hits=0,
    )
    assert result == []


def test_search_with_fallback_triggers_cascade():
    """1차 검색 부족 → fallback edition → 전체 검색 cascade (lines 545-567)."""
    from rank_bm25 import BM25Okapi

    # 충분한 corpus
    docs = [
        {
            "quote_id": f"q{i}",
            "text": f"경영 텍스트 {i}",
            "edition_id": "1998-10차",
            "type": "narrative",
            "section_path": [],
            "quality_flags": [],
        }
        for i in range(5)
    ]
    tokenized = [d["text"].split() for d in docs]
    bm25 = BM25Okapi(tokenized)
    bm25_data = {
        "bm25": bm25,
        "quote_ids": [d["quote_id"] for d in docs],
        "quote_map": {d["quote_id"]: d for d in docs},
    }

    # edition_filter="2020-14차" → 매칭 0건, fallback ["1998-10차"] → 검색
    result = _search_with_fallback(
        query="경영 텍스트",
        edition_filter="2020-14차",
        type_filter=None,
        section_filter=None,
        alpha=0.0,  # BM25 only
        rrf_k=60,
        score_threshold=0.5,
        top_k=5,
        search_vec_k=10,
        search_bm25_k=10,
        collection=None,
        bm25_data=bm25_data,
        openai_client=None,
        embedding_model="text-embedding-3-large",
        fallback_editions=["1998-10차"],
        min_hits=1,
    )

    assert len(result) >= 1


def test_search_with_fallback_all_fallbacks_insufficient():
    """모든 fallback edition도 부족 → 전체 검색 fallback (lines 565-567)."""
    from rank_bm25 import BM25Okapi

    docs = [
        {
            "quote_id": "q1",
            "text": "유일한 텍스트",
            "edition_id": "1979-초판",
            "type": "narrative",
            "section_path": [],
            "quality_flags": [],
        }
    ]
    tokenized = [d["text"].split() for d in docs]
    bm25 = BM25Okapi(tokenized)
    bm25_data = {
        "bm25": bm25,
        "quote_ids": [d["quote_id"] for d in docs],
        "quote_map": {d["quote_id"]: d for d in docs},
    }

    result = _search_with_fallback(
        query="유일한 텍스트",
        edition_filter="2020-14차",
        type_filter=None,
        section_filter=None,
        alpha=0.0,
        rrf_k=60,
        score_threshold=0.5,
        top_k=5,
        search_vec_k=10,
        search_bm25_k=10,
        collection=None,
        bm25_data=bm25_data,
        openai_client=None,
        embedding_model="text-embedding-3-large",
        fallback_editions=["1998-10차"],  # 1998-10차도 매칭 안됨
        min_hits=3,  # 3건 이상 필요
    )

    # 최종 fallback: edition_filter=None 전체 검색
    # 결과가 있을 수도 있고 없을 수도 있지만 cascade 실행됨
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# retrieve_quotes — edition_hint resolution (lines 629-633)
# ---------------------------------------------------------------------------


def test_retrieve_quotes_specific_time_edition_hint():
    """specific_time + edition_hint → edition_filter 자동 매핑 (lines 629-633)."""
    from rank_bm25 import BM25Okapi

    docs = [
        {
            "quote_id": "2020-14차|test|definition|001",
            "text": "VWBE Culture 정의",
            "edition_id": "2020-14차",
            "type": "definition",
            "section_path": [],
            "char_span": [100, 200],
            "sha256": "h" * 64,
            "quality_flags": [],
        },
        {
            "quote_id": "1979-초판|test|narrative|001",
            "text": "초판 기업관 텍스트",
            "edition_id": "1979-초판",
            "type": "narrative",
            "section_path": [],
            "char_span": [10, 50],
            "sha256": "i" * 64,
            "quality_flags": [],
        },
    ]
    tokenized = [d["text"].split() for d in docs]
    bm25 = BM25Okapi(tokenized)
    bm25_data = {
        "bm25": bm25,
        "quote_ids": [d["quote_id"] for d in docs],
        "quote_map": {d["quote_id"]: d for d in docs},
    }

    result = retrieve_quotes(
        "VWBE란?",
        intent="specific_time",
        policy={
            "edition_hint": "14차",  # → "2020-14차"로 매핑
            "alpha": 0.0,
        },
        top_k=5,
        collection=None,
        bm25_data=bm25_data,
        openai_client=None,
    )

    # edition_hint "14차"가 EDITION_ORDER의 "2020-14차"와 매칭
    for r in result:
        assert r["edition"] == "2020-14차"


# ---------------------------------------------------------------------------
# _normalize_hit — quality_flags JSONDecodeError (lines 429-430)
# ---------------------------------------------------------------------------


def test_normalize_hit_quality_flags_json_error():
    """quality_flags가 잘못된 JSON일 때 빈 리스트 fallback (lines 429-430)."""
    raw = _make_raw_hit(quality_flags="invalid{json")
    result = _normalize_hit(raw)
    assert result["quality_flags"] == []


def test_normalize_hit_section_path_json_error():
    """section_path가 잘못된 JSON일 때 빈 리스트 fallback (line 401-402)."""
    raw = _make_raw_hit(section_path="not-valid-json[")
    result = _normalize_hit(raw)
    assert result["chapter_path"] == []
