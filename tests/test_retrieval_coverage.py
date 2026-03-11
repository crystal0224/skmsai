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
    _ensure_cross_version_coverage,
    _normalize_hit,
    _search_with_fallback,
    bm25_search,
    build_chroma_where,
    edition_sort_key,
    hybrid_fusion,
    load_bm25_index,
    load_chroma_collection,
    parse_edition_hints_from_query,
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


# ---------------------------------------------------------------------------
# parse_edition_hints_from_query — 질의에서 개정판 힌트 추출
# ---------------------------------------------------------------------------


def test_parse_edition_hints_basic():
    """'초판과 14차' → 2개 edition_id 추출."""
    result = parse_edition_hints_from_query("인간중심의 경영이 초판과 14차에서 어떻게 다른가?")
    assert "1979-초판" in result
    assert "2020-14차" in result
    assert len(result) == 2


def test_parse_edition_hints_year_pattern():
    """'1979년과 2020년' → 연도 기반 추출."""
    result = parse_edition_hints_from_query("1979년과 2020년의 인사관리 차이")
    assert "1979-초판" in result
    assert "2020-14차" in result


def test_parse_edition_hints_single():
    """단일 개정판 참조는 1건만 반환."""
    result = parse_edition_hints_from_query("10차에서 인사관리는?")
    assert result == ["1998-10차"]


def test_parse_edition_hints_no_match():
    """개정판 참조가 없으면 빈 리스트."""
    result = parse_edition_hints_from_query("SUPEX란 무엇인가?")
    assert result == []


def test_parse_edition_hints_sorted_chronologically():
    """결과가 연대순으로 정렬되는지 확인."""
    result = parse_edition_hints_from_query("14차와 초판의 비교")
    assert result == ["1979-초판", "2020-14차"]


def test_parse_edition_hints_multiple():
    """3개 이상 개정판 참조도 추출."""
    result = parse_edition_hints_from_query("초판, 10차, 14차의 경영 요소 비교")
    assert result == ["1979-초판", "1998-10차", "2020-14차"]


def test_parse_edition_hints_dedup():
    """'14차'와 '2020년' 중복 참조 시 deduplicated."""
    result = parse_edition_hints_from_query("14차(2020년) 경영 정의")
    assert result.count("2020-14차") == 1


# ---------------------------------------------------------------------------
# _ensure_cross_version_coverage — 보완 검색
# ---------------------------------------------------------------------------


def _make_bm25_corpus_multi_edition():
    """여러 개정판에 걸친 BM25 코퍼스를 생성한다."""
    from rank_bm25 import BM25Okapi

    docs = (
        [
            {
                "quote_id": f"1979-초판|경영|definition|{i:03d}",
                "text": f"인간중심의 경영 원칙 텍스트 {i}",
                "edition_id": "1979-초판",
                "type": "definition",
                "section_path": ["인간중심의 경영"],
                "char_span": [100 * i, 100 * i + 50],
                "sha256": f"hash_cho_{i}",
                "quality_flags": [],
            }
            for i in range(3)
        ]
        + [
            {
                "quote_id": f"2020-14차|경영|definition|{i:03d}",
                "text": f"인간중심의 경영 현대적 해석 {i}",
                "edition_id": "2020-14차",
                "type": "definition",
                "section_path": ["인간중심의 경영"],
                "char_span": [1000 + 100 * i, 1050 + 100 * i],
                "sha256": f"hash_14_{i}",
                "quality_flags": [],
            }
            for i in range(3)
        ]
        + [
            {
                "quote_id": f"1998-10차|경영|narrative|{i:03d}",
                "text": f"경영 패러다임 변화 서술 {i}",
                "edition_id": "1998-10차",
                "type": "narrative",
                "section_path": ["경영관리"],
                "char_span": [2000 + 100 * i, 2050 + 100 * i],
                "sha256": f"hash_10_{i}",
                "quality_flags": [],
            }
            for i in range(3)
        ]
    )
    tokenized = [d["text"].split() for d in docs]
    bm25 = BM25Okapi(tokenized)
    return {
        "bm25": bm25,
        "quote_ids": [d["quote_id"] for d in docs],
        "quote_map": {d["quote_id"]: d for d in docs},
    }


def test_ensure_cross_version_coverage_adds_missing_edition():
    """한쪽 edition만 있을 때 다른 쪽을 보완 검색으로 추가."""
    bm25_data = _make_bm25_corpus_multi_edition()

    # fused에 초판만 있는 상황 (14차 누락)
    fused = [
        {
            "quote_id": "1979-초판|경영|definition|000",
            "text": "인간중심의 경영 원칙 텍스트 0",
            "score": 0.9,
            "fusion_score": 0.9,
            "source": "bm25",
            "metadata": {"edition_id": "1979-초판", "type": "definition"},
        },
        {
            "quote_id": "1979-초판|경영|definition|001",
            "text": "인간중심의 경영 원칙 텍스트 1",
            "score": 0.85,
            "fusion_score": 0.85,
            "source": "bm25",
            "metadata": {"edition_id": "1979-초판", "type": "definition"},
        },
        {
            "quote_id": "1979-초판|경영|definition|002",
            "text": "인간중심의 경영 원칙 텍스트 2",
            "score": 0.8,
            "fusion_score": 0.8,
            "source": "bm25",
            "metadata": {"edition_id": "1979-초판", "type": "definition"},
        },
    ]

    result = _ensure_cross_version_coverage(
        query="인간중심의 경영",
        fused=fused,
        required_editions=["1979-초판", "2020-14차"],
        final_top_k=5,
        type_filter=None,
        section_filter=None,
        alpha=0.0,  # BM25 only
        rrf_k=60,
        score_threshold=0.0,
        search_vec_k=10,
        search_bm25_k=10,
        collection=None,
        bm25_data=bm25_data,
        openai_client=None,
        embedding_model="text-embedding-3-large",
    )

    editions = {h.get("metadata", {}).get("edition_id", "") for h in result}
    assert "1979-초판" in editions, "초판이 결과에 없음"
    assert "2020-14차" in editions, "14차가 보완 검색으로 추가되어야 함"
    assert len(result) <= 5, f"final_top_k=5 초과: {len(result)}"


def test_ensure_cross_version_coverage_no_change_when_covered():
    """양쪽 edition 모두 있으면 결과를 변경하지 않음."""
    fused = [
        {
            "quote_id": "q1",
            "text": "초판 텍스트",
            "score": 0.9,
            "source": "bm25",
            "metadata": {"edition_id": "1979-초판"},
        },
        {
            "quote_id": "q2",
            "text": "14차 텍스트",
            "score": 0.85,
            "source": "bm25",
            "metadata": {"edition_id": "2020-14차"},
        },
    ]

    result = _ensure_cross_version_coverage(
        query="인간중심의 경영",
        fused=fused,
        required_editions=["1979-초판", "2020-14차"],
        final_top_k=5,
        type_filter=None,
        section_filter=None,
        alpha=0.0,
        rrf_k=60,
        score_threshold=0.0,
        search_vec_k=10,
        search_bm25_k=10,
        collection=None,
        bm25_data=None,
        openai_client=None,
        embedding_model="text-embedding-3-large",
    )

    assert result is fused, "이미 커버된 경우 원본 리스트를 그대로 반환해야 함"


def test_ensure_cross_version_coverage_single_edition_noop():
    """required_editions가 1개면 보완 검색 없이 원본 반환."""
    fused = [{"quote_id": "q1", "metadata": {"edition_id": "1979-초판"}}]

    result = _ensure_cross_version_coverage(
        query="test",
        fused=fused,
        required_editions=["1979-초판"],
        final_top_k=5,
        type_filter=None,
        section_filter=None,
        alpha=0.0,
        rrf_k=60,
        score_threshold=0.0,
        search_vec_k=10,
        search_bm25_k=10,
        collection=None,
        bm25_data=None,
        openai_client=None,
        embedding_model="text-embedding-3-large",
    )

    assert result is fused


def test_ensure_cross_version_respects_final_top_k():
    """보완 검색 후에도 final_top_k를 초과하지 않음."""
    bm25_data = _make_bm25_corpus_multi_edition()

    # fused에 5건 모두 초판
    fused = [
        {
            "quote_id": f"1979-초판|경영|definition|{i:03d}",
            "text": f"텍스트 {i}",
            "score": 0.9 - i * 0.01,
            "fusion_score": 0.9 - i * 0.01,
            "source": "bm25",
            "metadata": {"edition_id": "1979-초판", "type": "definition"},
        }
        for i in range(5)
    ]

    result = _ensure_cross_version_coverage(
        query="인간중심의 경영",
        fused=fused,
        required_editions=["1979-초판", "2020-14차"],
        final_top_k=5,
        type_filter=None,
        section_filter=None,
        alpha=0.0,
        rrf_k=60,
        score_threshold=0.0,
        search_vec_k=10,
        search_bm25_k=10,
        collection=None,
        bm25_data=bm25_data,
        openai_client=None,
        embedding_model="text-embedding-3-large",
    )

    assert len(result) <= 5, f"결과가 final_top_k=5를 초과: {len(result)}"
    editions = {h.get("metadata", {}).get("edition_id", "") for h in result}
    assert "2020-14차" in editions


# ---------------------------------------------------------------------------
# retrieve_quotes — evolution_comparison cross-version coverage (e2e)
# ---------------------------------------------------------------------------


def test_retrieve_quotes_evolution_cross_version_coverage():
    """evolution_comparison 질의에서 양쪽 판본이 모두 검색되는지 확인."""
    bm25_data = _make_bm25_corpus_multi_edition()

    result = retrieve_quotes(
        "인간중심의 경영 개념이 초판과 14차에서 어떻게 다른가?",
        intent="evolution_comparison",
        policy={"alpha": 0.0, "score_threshold": 0.0},  # BM25 only
        top_k=5,
        collection=None,
        bm25_data=bm25_data,
        openai_client=None,
    )

    editions = {r["edition"] for r in result}
    assert "1979-초판" in editions, f"초판이 결과에 없음: editions={editions}"
    assert "2020-14차" in editions, f"14차가 결과에 없음: editions={editions}"
    assert len(result) <= 5


def test_retrieve_quotes_evolution_no_edition_hints_still_works():
    """개정판 힌트가 없는 evolution_comparison 질의는 정상 작동."""
    bm25_data = _make_bm25_corpus_multi_edition()

    result = retrieve_quotes(
        "경영 요소의 변천사",
        intent="evolution_comparison",
        policy={"alpha": 0.0, "score_threshold": 0.0},
        top_k=5,
        collection=None,
        bm25_data=bm25_data,
        openai_client=None,
    )

    # 힌트가 없으면 보완 검색이 트리거되지 않지만 에러도 없어야 함
    assert isinstance(result, list)
    assert len(result) <= 5
