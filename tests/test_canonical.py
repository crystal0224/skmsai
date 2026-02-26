#!/usr/bin/env python3
"""lib/canonical.py 단위 테스트 (PR-5).

Usage:
    python tests/test_canonical.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Ensure scripts/ is on sys.path
_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPT_DIR))

from lib.canonical import (  # noqa: E402
    CanonicalStore,
    format_canonical_context,
    load_canonical_store,
)


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

_SAMPLE_ITEMS = [
    {
        "canonical_id": "CAN-TEST-001",
        "subject": "경영의 궁극적 목적",
        "claim_type": "목적",
        "quote_ids": ["2020-14차|_root|principle|004"],
        "summary_ko": "SK 경영의 궁극적 목적은 구성원 행복이다.",
        "doc_id": "SKMS-2020-14",
        "year": 2020,
        "edition": "2020-14차",
    },
    {
        "canonical_id": "CAN-TEST-002",
        "subject": "VWBE (자발적·의욕적 두뇌활용)",
        "claim_type": "정의",
        "quote_ids": ["2020-14차|_root|principle|005", "2020-14차|_root|principle|006"],
        "summary_ko": "VWBE는 자발적이고 의욕적인 두뇌활용을 뜻한다.",
        "doc_id": "SKMS-2020-14",
        "year": 2020,
        "edition": "2020-14차",
    },
    {
        "canonical_id": "CAN-TEST-003",
        "subject": "패기",
        "claim_type": "정의",
        "quote_ids": ["2020-14차|_root|principle|006"],
        "summary_ko": "패기는 VWBE가 외부로 발현되는 모습이다.",
        "doc_id": "SKMS-2020-14",
        "year": 2020,
        "edition": "2020-14차",
    },
    {
        "canonical_id": "CAN-TEST-004",
        "subject": "SUPEX Company",
        "claim_type": "정의",
        "quote_ids": ["2020-14차|_root|principle|008"],
        "summary_ko": "SUPEX Company는 지속적인 가치를 창출하는 회사이다.",
        "doc_id": "SKMS-2020-14",
        "year": 2020,
        "edition": "2020-14차",
    },
]


def _make_store() -> CanonicalStore:
    return CanonicalStore(_SAMPLE_ITEMS)


# ---------------------------------------------------------------------------
# CanonicalStore tests
# ---------------------------------------------------------------------------


def test_store_count():
    """count가 올바른지 확인."""
    store = _make_store()
    assert store.count == 4
    print("  PASS: store count")


def test_store_empty():
    """빈 store 생성."""
    store = CanonicalStore([])
    assert store.count == 0
    assert store.lookup("anything") is None
    print("  PASS: store empty")


def test_lookup_exact_subject():
    """subject 정확 일치 조회."""
    store = _make_store()
    result = store.lookup("패기")
    assert result is not None
    assert result["canonical_id"] == "CAN-TEST-003"
    print("  PASS: lookup exact subject")


def test_lookup_subject_in_query():
    """query 안에 subject 포함."""
    store = _make_store()
    result = store.lookup("경영의 궁극적 목적은 무엇인가?")
    assert result is not None
    assert result["canonical_id"] == "CAN-TEST-001"
    print("  PASS: lookup subject in query")


def test_lookup_longest_subject_wins():
    """가장 긴 subject가 우선 매칭."""
    store = _make_store()
    # "SUPEX Company"(13) vs 다른 subject
    result = store.lookup("SUPEX Company의 정의는?")
    assert result is not None
    assert result["canonical_id"] == "CAN-TEST-004"
    print("  PASS: lookup longest subject wins")


def test_lookup_keyword():
    """키워드 기반 매칭."""
    store = _make_store()
    result = store.lookup("VWBE란 무엇인가?")
    assert result is not None
    assert result["canonical_id"] == "CAN-TEST-002"
    print("  PASS: lookup keyword")


def test_lookup_no_match():
    """매칭 없음."""
    store = _make_store()
    result = store.lookup("인사관리 정의")
    assert result is None
    print("  PASS: lookup no match")


def test_lookup_by_id():
    """canonical_id로 조회."""
    store = _make_store()
    result = store.lookup_by_id("CAN-TEST-002")
    assert result is not None
    assert result["subject"] == "VWBE (자발적·의욕적 두뇌활용)"
    print("  PASS: lookup by id")


def test_lookup_by_id_missing():
    """존재하지 않는 canonical_id."""
    store = _make_store()
    result = store.lookup_by_id("CAN-NONEXISTENT")
    assert result is None
    print("  PASS: lookup by id missing")


def test_all_items():
    """all_items가 새 리스트를 반환."""
    store = _make_store()
    items = store.all_items()
    assert len(items) == 4
    assert items is not store._items  # 다른 객체
    print("  PASS: all items")


def test_subjects():
    """subjects가 모든 subject를 반환."""
    store = _make_store()
    subjects = store.subjects()
    assert "패기" in subjects
    assert "SUPEX Company" in subjects
    assert len(subjects) == 4
    print("  PASS: subjects")


def test_immutability():
    """lookup 결과 수정이 원본에 영향 없음."""
    store = _make_store()
    result = store.lookup("패기")
    assert result is not None
    result["subject"] = "MODIFIED"
    # 다시 조회하면 원본 유지
    result2 = store.lookup("패기")
    assert result2 is not None
    assert result2["subject"] == "패기"
    print("  PASS: immutability")


def test_immutability_nested():
    """lookup 결과의 중첩 리스트(quote_ids) 수정이 원본에 영향 없음."""
    store = _make_store()
    result = store.lookup("VWBE란 무엇인가?")
    assert result is not None
    original_len = len(result["quote_ids"])
    result["quote_ids"].append("INJECTED")
    # 다시 조회하면 원본 유지
    result2 = store.lookup("VWBE란 무엇인가?")
    assert result2 is not None
    assert len(result2["quote_ids"]) == original_len
    assert "INJECTED" not in result2["quote_ids"]
    print("  PASS: immutability nested")


# ---------------------------------------------------------------------------
# load from file tests
# ---------------------------------------------------------------------------


def test_load_from_file():
    """JSONL 파일에서 로드."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as f:
        for item in _SAMPLE_ITEMS:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
        tmp_path = f.name

    store = CanonicalStore.load(tmp_path)
    assert store.count == 4
    Path(tmp_path).unlink()
    print("  PASS: load from file")


def test_load_nonexistent_file():
    """존재하지 않는 파일 → 빈 store."""
    store = CanonicalStore.load("nonexistent/canonical.jsonl")
    assert store.count == 0
    print("  PASS: load nonexistent file")


def test_load_canonical_store_real():
    """실제 canonical_2020.jsonl 로드 (파일 존재 시)."""
    store = load_canonical_store()
    if store.count > 0:
        assert store.count >= 20  # DoD: 20개 이상
        # 모든 항목에 필수 필드 존재
        for item in store.all_items():
            assert "canonical_id" in item
            assert "subject" in item
            assert "claim_type" in item
            assert "quote_ids" in item
            assert len(item["quote_ids"]) >= 1
            assert "summary_ko" in item
            assert "doc_id" in item
            assert "year" in item
            assert "edition" in item
        print(f"  PASS: load canonical store real ({store.count} items)")
    else:
        print("  SKIP: canonical_2020.jsonl not found")


# ---------------------------------------------------------------------------
# format_canonical_context tests
# ---------------------------------------------------------------------------


def test_format_canonical_context():
    """포맷팅 결과에 필수 정보 포함."""
    item = _SAMPLE_ITEMS[0]
    text = format_canonical_context(item)
    assert "경영의 궁극적 목적" in text
    assert "목적" in text  # claim_type
    assert "2020-14차" in text
    assert item["quote_ids"][0] in text
    assert item["summary_ko"] in text
    print("  PASS: format canonical context")


# ---------------------------------------------------------------------------
# build_canonical.py output validation
# ---------------------------------------------------------------------------


def test_canonical_file_schema():
    """canonical_2020.jsonl의 각 항목 스키마 검증."""
    path = Path("data/processed/canonical_2020.jsonl")
    if not path.exists():
        print("  SKIP: canonical_2020.jsonl not found")
        return

    valid_claim_types = {"목적", "가치", "원칙", "정의", "지향점"}
    items = []
    with open(path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            items.append(item)

            # 필수 필드
            assert "canonical_id" in item, f"line {line_num}: canonical_id 없음"
            assert "subject" in item, f"line {line_num}: subject 없음"
            assert "claim_type" in item, f"line {line_num}: claim_type 없음"
            assert (
                item["claim_type"] in valid_claim_types
            ), f"line {line_num}: invalid claim_type: {item['claim_type']}"
            assert "quote_ids" in item, f"line {line_num}: quote_ids 없음"
            assert (
                1 <= len(item["quote_ids"]) <= 3
            ), f"line {line_num}: quote_ids 수: {len(item['quote_ids'])}"
            assert "summary_ko" in item, f"line {line_num}: summary_ko 없음"
            assert "doc_id" in item, f"line {line_num}: doc_id 없음"
            assert item["year"] == 2020, f"line {line_num}: year != 2020"
            assert (
                item["edition"] == "2020-14차"
            ), f"line {line_num}: edition != 2020-14차"

    assert len(items) >= 20, f"항목 수: {len(items)} < 20 (DoD)"
    print(f"  PASS: canonical file schema ({len(items)} items)")


def test_canonical_quote_ids_traceable():
    """canonical의 quote_id가 quotes.jsonl에 실재하는지 검증."""
    canonical_path = Path("data/processed/canonical_2020.jsonl")
    quotes_path = Path("data/processed/quotes.jsonl")
    if not canonical_path.exists() or not quotes_path.exists():
        print("  SKIP: data files not found")
        return

    # quotes.jsonl에서 모든 quote_id 수집
    valid_quote_ids = set()
    with open(quotes_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                obj = json.loads(line)
                valid_quote_ids.add(obj["quote_id"])

    # canonical의 모든 quote_id가 존재하는지 확인
    missing = []
    with open(canonical_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            for qid in item["quote_ids"]:
                if qid not in valid_quote_ids:
                    missing.append((item["canonical_id"], qid))

    assert not missing, f"역추적 불가 quote_id: {missing}"
    print("  PASS: canonical quote_ids traceable")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("[PR-5] lib/canonical.py 단위 테스트")
    print("=" * 50)

    tests = [
        test_store_count,
        test_store_empty,
        test_lookup_exact_subject,
        test_lookup_subject_in_query,
        test_lookup_longest_subject_wins,
        test_lookup_keyword,
        test_lookup_no_match,
        test_lookup_by_id,
        test_lookup_by_id_missing,
        test_all_items,
        test_subjects,
        test_immutability,
        test_immutability_nested,
        test_load_from_file,
        test_load_nonexistent_file,
        test_load_canonical_store_real,
        test_format_canonical_context,
        test_canonical_file_schema,
        test_canonical_quote_ids_traceable,
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
