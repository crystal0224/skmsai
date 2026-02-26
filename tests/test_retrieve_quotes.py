#!/usr/bin/env python3
"""retrieve_quotes() 단일 엔트리 함수 스모크 테스트.

API 키 없이 단위 테스트로 실행 가능.

Usage:
    python tests/test_retrieve_quotes.py
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

# Ensure scripts/ is on sys.path
_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPT_DIR))

from lib.retrieval import (  # noqa: E402
    EDITION_ORDER,
    _apply_intent_policy,
    _normalize_hit,
    edition_sort_key,
    retrieve_quotes,
)

REQUIRED_FIELDS = {
    "quote_id",
    "doc_id",
    "year",
    "edition",
    "type",
    "chapter_path",
    "score",
    "span",
    "sha256",
    "text",
    "source",
    "quality_flags",
}


def _make_raw_hit(
    quote_id: str = "2020-14차|인사관리|definition|001",
    text: str = "인사관리란 ...",
    score: float = 0.85,
    source: str = "vector",
    edition_id: str = "2020-14차",
    quote_type: str = "definition",
    section_path: str = '["인사관리", "기본"]',
    sha256: str = "abc123",
    char_span_start: int = 100,
    char_span_end: int = 200,
) -> dict:
    """테스트용 raw hit dict를 생성한다."""
    return {
        "quote_id": quote_id,
        "text": text,
        "score": score,
        "source": source,
        "fusion_score": score + 0.01,
        "metadata": {
            "edition_id": edition_id,
            "type": quote_type,
            "section_path": section_path,
            "sha256": sha256,
            "char_span_start": char_span_start,
            "char_span_end": char_span_end,
            "quality_flags": "[]",
        },
    }


# ---------------------------------------------------------------------------
# _normalize_hit tests
# ---------------------------------------------------------------------------


def test_normalize_hit_fields():
    """_normalize_hit이 필수 필드를 모두 포함하는지 확인."""
    raw = _make_raw_hit()
    result = _normalize_hit(raw)

    missing = REQUIRED_FIELDS - set(result.keys())
    assert not missing, f"Missing fields: {missing}"

    assert result["quote_id"] == "2020-14차|인사관리|definition|001"
    assert result["doc_id"] == "2020-14차"
    assert result["year"] == 2020
    assert result["edition"] == "2020-14차"
    assert result["type"] == "definition"
    assert result["chapter_path"] == ["인사관리", "기본"]
    assert result["span"] == [100, 200]
    assert result["sha256"] == "abc123"
    assert result["text"] == "인사관리란 ..."
    assert isinstance(result["quality_flags"], list)
    print("  PASS: _normalize_hit fields")


def test_normalize_hit_bm25_fallback():
    """BM25 cross-reference로 span/sha256 보완."""
    raw = _make_raw_hit()
    # Chroma-specific 필드 제거 → BM25 fallback 테스트
    del raw["metadata"]["sha256"]
    del raw["metadata"]["char_span_start"]
    del raw["metadata"]["char_span_end"]

    bm25_data = {
        "quote_map": {
            "2020-14차|인사관리|definition|001": {
                "char_span": [500, 600],
                "sha256": "bm25hash",
            }
        }
    }

    result = _normalize_hit(raw, bm25_data)
    assert result["span"] == [500, 600], f"Expected [500, 600], got {result['span']}"
    assert result["sha256"] == "bm25hash"
    print("  PASS: _normalize_hit BM25 fallback")


def test_normalize_hit_immutability():
    """_normalize_hit이 원본 hit을 변경하지 않는지 확인."""
    raw = _make_raw_hit()
    original = copy.deepcopy(raw)
    _normalize_hit(raw)
    assert raw == original, "Original hit was mutated!"
    print("  PASS: _normalize_hit immutability")


def test_normalize_hit_list_section_path_immutability():
    """section_path가 리스트일 때 원본을 변경하지 않는지 확인."""
    raw = {
        "quote_id": "test|001",
        "text": "test",
        "score": 0.5,
        "source": "bm25",
        "metadata": {
            "edition_id": "2020-14차",
            "type": "narrative",
            "section_path": ["인사관리", "기본"],  # list, not JSON string
            "quality_flags": [],
        },
    }
    original_sp = raw["metadata"]["section_path"].copy()
    result = _normalize_hit(raw)
    # chapter_path는 새 리스트여야 함 (원본 참조 아님)
    assert (
        result["chapter_path"] is not raw["metadata"]["section_path"]
    ), "chapter_path should be a copy, not the same object"
    assert (
        raw["metadata"]["section_path"] == original_sp
    ), "Original section_path was mutated"
    print("  PASS: _normalize_hit list section_path immutability")


def test_normalize_hit_year_extraction():
    """다양한 edition_id에서 year 추출 확인."""
    for eid, expected_year in [("2020-14차", 2020), ("1979-초판", 1979), ("unknown", 0)]:
        raw = _make_raw_hit(edition_id=eid)
        result = _normalize_hit(raw)
        assert (
            result["year"] == expected_year
        ), f"{eid}: expected {expected_year}, got {result['year']}"
    print("  PASS: _normalize_hit year extraction")


# ---------------------------------------------------------------------------
# edition_sort_key tests
# ---------------------------------------------------------------------------


def test_edition_sort_key():
    """edition_sort_key 정렬 순서 확인."""
    assert edition_sort_key("2020-14차") > edition_sort_key("1979-초판")
    assert edition_sort_key("2020-14차") == 14
    assert edition_sort_key("1979-초판") == 0
    assert edition_sort_key("unknown") == 9999
    print("  PASS: edition_sort_key")


def test_edition_order_completeness():
    """EDITION_ORDER에 최소 10개 이상의 개정판이 등록되어 있는지 확인."""
    assert len(EDITION_ORDER) >= 10, f"Only {len(EDITION_ORDER)} editions"
    assert "2020-14차" in EDITION_ORDER, "Latest edition missing"
    assert "1979-초판" in EDITION_ORDER, "First edition missing"
    print("  PASS: EDITION_ORDER completeness")


# ---------------------------------------------------------------------------
# _apply_intent_policy tests
# ---------------------------------------------------------------------------


def test_apply_intent_policy_general_definition():
    """general_definition은 최신판 우선 정렬."""
    hits = [
        _make_raw_hit(edition_id="1979-초판"),
        _make_raw_hit(edition_id="2020-14차"),
        _make_raw_hit(edition_id="1998-10차"),
    ]
    result = _apply_intent_policy("general_definition", None, hits)
    editions = [h["metadata"]["edition_id"] for h in result]
    assert editions == ["2020-14차", "1998-10차", "1979-초판"], f"Got: {editions}"
    print("  PASS: _apply_intent_policy general_definition")


def test_apply_intent_policy_evolution():
    """evolution_comparison은 연대순 정렬."""
    hits = [
        _make_raw_hit(edition_id="2020-14차"),
        _make_raw_hit(edition_id="1979-초판"),
        _make_raw_hit(edition_id="1998-10차"),
    ]
    result = _apply_intent_policy("evolution_comparison", None, hits)
    editions = [h["metadata"]["edition_id"] for h in result]
    assert editions == ["1979-초판", "1998-10차", "2020-14차"], f"Got: {editions}"
    print("  PASS: _apply_intent_policy evolution_comparison")


def test_apply_intent_policy_specific_time():
    """specific_time + edition_hint는 해당 개정판만 필터링."""
    hits = [
        _make_raw_hit(edition_id="2020-14차"),
        _make_raw_hit(edition_id="1979-초판"),
        _make_raw_hit(edition_id="1998-10차"),
    ]
    result = _apply_intent_policy("specific_time", "14차", hits)
    editions = [h["metadata"]["edition_id"] for h in result]
    assert editions == ["2020-14차"], f"Got: {editions}"
    print("  PASS: _apply_intent_policy specific_time")


def test_apply_intent_policy_latest_first_hook():
    """latest_first=True는 open_ended에서 최신판 우선 정렬."""
    hits = [
        _make_raw_hit(edition_id="1979-초판"),
        _make_raw_hit(edition_id="2020-14차"),
    ]
    result = _apply_intent_policy("open_ended", None, hits, latest_first=True)
    editions = [h["metadata"]["edition_id"] for h in result]
    assert editions[0] == "2020-14차", f"Got: {editions}"
    print("  PASS: _apply_intent_policy latest_first hook")


# ---------------------------------------------------------------------------
# retrieve_quotes tests
# ---------------------------------------------------------------------------


def test_retrieve_quotes_empty():
    """검색 인덱스 없을 때 빈 리스트 반환."""
    result = retrieve_quotes(
        "테스트 질의",
        "open_ended",
        {},
        top_k=5,
        collection=None,
        bm25_data=None,
        openai_client=None,
    )
    assert result == [], f"Expected [], got {result}"
    print("  PASS: retrieve_quotes empty")


def test_retrieve_quotes_return_format():
    """retrieve_quotes 반환 형식이 표준을 준수하는지 확인 (BM25 only)."""
    from rank_bm25 import BM25Okapi

    # BM25 IDF가 0이 되지 않도록 충분한 크기의 코퍼스 구성 (최소 5개)
    docs = [
        {
            "quote_id": "2020-14차|경영|definition|001",
            "edition_id": "2020-14차",
            "type": "definition",
            "section_path": ["경영관리"],
            "text": "SUPEX란 Super Excellent 수준을 의미한다",
            "char_span": [100, 200],
            "sha256": "hash1",
            "quality_flags": [],
            "start_line": 10,
            "token_count": 8,
        },
        {
            "quote_id": "1998-10차|경영|narrative|001",
            "edition_id": "1998-10차",
            "type": "narrative",
            "section_path": ["SUPEX추구"],
            "text": "SUPEX 추구는 SK의 핵심 경영방식이다",
            "char_span": [300, 400],
            "sha256": "hash2",
            "quality_flags": [],
            "start_line": 20,
            "token_count": 7,
        },
        {
            "quote_id": "2016-13차|인사|narrative|001",
            "edition_id": "2016-13차",
            "type": "narrative",
            "section_path": ["인사관리"],
            "text": "인사관리의 기본 원칙을 설명한다",
            "char_span": [500, 600],
            "sha256": "hash3",
            "quality_flags": [],
            "start_line": 30,
            "token_count": 5,
        },
        {
            "quote_id": "2008-12차|조직|narrative|001",
            "edition_id": "2008-12차",
            "type": "narrative",
            "section_path": ["조직관리"],
            "text": "조직 구조와 의사결정 체계를 정의한다",
            "char_span": [700, 800],
            "sha256": "hash4",
            "quality_flags": [],
            "start_line": 40,
            "token_count": 6,
        },
        {
            "quote_id": "2004-11차|재무|narrative|001",
            "edition_id": "2004-11차",
            "type": "narrative",
            "section_path": ["재무관리"],
            "text": "재무 건전성 확보가 경영의 기초이다",
            "char_span": [900, 1000],
            "sha256": "hash5",
            "quality_flags": [],
            "start_line": 50,
            "token_count": 6,
        },
    ]

    tokenized = [d["text"].split() for d in docs]
    bm25 = BM25Okapi(tokenized)
    bm25_data = {
        "bm25": bm25,
        "quote_ids": [d["quote_id"] for d in docs],
        "quote_map": {d["quote_id"]: d for d in docs},
        "tokenized_corpus": tokenized,
    }

    result = retrieve_quotes(
        "SUPEX란 무엇인가",
        "general_definition",
        {"alpha": 0.0},  # BM25 only (alpha=0 → keyword weight 100%)
        top_k=2,
        collection=None,
        bm25_data=bm25_data,
        openai_client=None,
    )

    assert len(result) > 0, "Expected at least 1 result"

    for r in result:
        missing = REQUIRED_FIELDS - set(r.keys())
        assert not missing, f"Missing fields in result: {missing}"
        assert isinstance(r["quote_id"], str)
        assert isinstance(r["year"], int)
        assert isinstance(r["chapter_path"], list)
        assert isinstance(r["span"], list) and len(r["span"]) == 2
        assert (
            isinstance(r["sha256"], str) and r["sha256"]
        ), f"sha256 empty for {r['quote_id']}"
        assert isinstance(r["quality_flags"], list)

    # general_definition → 최신판 우선
    if len(result) >= 2:
        assert (
            result[0]["year"] >= result[1]["year"]
        ), f"Expected latest first: {result[0]['year']} >= {result[1]['year']}"

    print(f"  PASS: retrieve_quotes return format ({len(result)} results)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("[PR-1] retrieve_quotes 스모크 테스트")
    print("=" * 50)

    tests = [
        test_normalize_hit_fields,
        test_normalize_hit_bm25_fallback,
        test_normalize_hit_immutability,
        test_normalize_hit_list_section_path_immutability,
        test_normalize_hit_year_extraction,
        test_edition_sort_key,
        test_edition_order_completeness,
        test_apply_intent_policy_general_definition,
        test_apply_intent_policy_evolution,
        test_apply_intent_policy_specific_time,
        test_apply_intent_policy_latest_first_hook,
        test_retrieve_quotes_empty,
        test_retrieve_quotes_return_format,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test.__name__}: {e}")
            failed += 1

    print(f"\n{'=' * 50}")
    print(f"결과: {passed} PASS, {failed} FAIL / {len(tests)} total")

    if failed > 0:
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
