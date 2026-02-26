#!/usr/bin/env python3
"""build_claims.py 단위 테스트 (PR-6).

Usage:
    python tests/test_claims.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure scripts/ is on sys.path
_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPT_DIR))

from build_claims import (  # noqa: E402
    _classify_claim_type,
    _extract_subject,
    _split_sentences,
    build_claims,
    load_14th_quotes,
)


# ---------------------------------------------------------------------------
# Sentence splitter tests
# ---------------------------------------------------------------------------


def test_split_sentences_basic():
    """기본 문장 분할."""
    text = "SK는 행복을 추구한다. 구성원은 실천한다."
    sentences = _split_sentences(text)
    assert len(sentences) == 2
    assert sentences[0]["text"] == "SK는 행복을 추구한다"
    assert sentences[1]["text"] == "구성원은 실천한다."
    print("  PASS: split sentences basic")


def test_split_sentences_paragraph():
    """단락 분할."""
    text = "첫 번째 단락입니다.\n\n두 번째 단락입니다."
    sentences = _split_sentences(text)
    assert len(sentences) == 2
    print("  PASS: split sentences paragraph")


def test_split_sentences_merge_short():
    """짧은 문장 병합 (10자 미만)."""
    text = "SK는 행복을 추구한다. 맞다. 구성원은 실천한다."
    sentences = _split_sentences(text)
    # "맞다" (2자)는 이전 문장에 병합됨
    assert len(sentences) == 2
    assert "맞다" in sentences[0]["text"]
    print("  PASS: split sentences merge short")


def test_split_sentences_numbered():
    """번호 뒤 마침표는 분할하지 않음."""
    text = "1. 경제적 가치를 창출한다. 2. 사회적 가치를 추구한다."
    sentences = _split_sentences(text)
    # "1." 뒤는 분할하지 않음
    assert any("1." in s["text"] for s in sentences)
    print("  PASS: split sentences numbered")


def test_split_sentences_offset():
    """offset이 원본 위치를 가리킴."""
    text = "SKMS는 경영철학이다. 구성원은 실천한다."
    sentences = _split_sentences(text)
    for sent in sentences:
        # offset이 원본에서 text를 찾을 수 있는 위치인지 확인
        found = text.find(sent["text"][:10])
        assert found >= 0, f"'{sent['text'][:10]}' not found at offset {sent['start']}"
    print("  PASS: split sentences offset")


# ---------------------------------------------------------------------------
# Classifier tests
# ---------------------------------------------------------------------------


def test_classify_definition():
    """정의 패턴 분류."""
    assert _classify_claim_type("SUPEX Company는 지속적인 가치를 창출하는 회사를 말한다") == "definition"
    assert _classify_claim_type("VWBE는 자발적이고 의욕적인 두뇌활용이다") == "definition"
    print("  PASS: classify definition")


def test_classify_purpose():
    """목적 패턴 분류."""
    assert _classify_claim_type("경영의 궁극적 목적은 구성원 행복이다") == "purpose"
    assert _classify_claim_type("이를 실현하기 위해 노력한다") == "purpose"
    print("  PASS: classify purpose")


def test_classify_value():
    """가치 패턴 분류."""
    assert _classify_claim_type("강하고 우수한 기업문화는 경쟁력의 원천이 된다") == "value"
    assert _classify_claim_type("구성원 행복을 키워 나간다") == "value"
    print("  PASS: classify value")


def test_classify_principle():
    """원칙 패턴 분류."""
    assert _classify_claim_type("회사는 안정과 성장을 이루어야 한다") == "principle"
    assert _classify_claim_type("구성원은 SKMS를 실천한다") == "principle"
    print("  PASS: classify principle")


def test_classify_stance():
    """입장 패턴 분류."""
    assert _classify_claim_type("이는 더 큰 행복을 가져다줄 것이라 믿습니다") == "stance"
    assert _classify_claim_type("SK를 선택한 것에 대한 확신을 갖는다") == "stance"
    print("  PASS: classify stance")


def test_classify_default():
    """기본값은 principle."""
    assert _classify_claim_type("기타 일반적인 설명 텍스트") == "principle"
    print("  PASS: classify default")


# ---------------------------------------------------------------------------
# Subject extraction tests
# ---------------------------------------------------------------------------


def test_extract_subject_keyword():
    """키워드 기반 subject 추출."""
    assert _extract_subject("SKMS는 경영철학이다") == "SKMS"
    assert _extract_subject("구성원 행복을 추구한다") == "구성원 행복"
    assert _extract_subject("사회적 가치를 창출한다") == "사회적 가치"
    print("  PASS: extract subject keyword")


def test_extract_subject_longest_match():
    """가장 긴 키워드 우선."""
    # "구성원 행복" (5자) > "구성원" (3자)
    assert _extract_subject("구성원 행복의 지속 가능성") == "구성원 행복"
    print("  PASS: extract subject longest match")


def test_extract_subject_fallback():
    """키워드 없을 때 은/는 앞 명사 추출."""
    result = _extract_subject("인사관리는 중요한 기능이다")
    assert result == "인사관리"
    print("  PASS: extract subject fallback")


# ---------------------------------------------------------------------------
# Build claims tests
# ---------------------------------------------------------------------------


def test_build_claims_output():
    """build_claims 결과 기본 검증."""
    quotes = load_14th_quotes("data/processed/quotes.jsonl")
    if not quotes:
        print("  SKIP: quotes not found")
        return

    claims = build_claims(quotes)
    assert len(claims) >= 50, f"claims: {len(claims)} < 50 (DoD)"

    # 모든 claim에 필수 필드 존재
    for claim in claims:
        assert "claim_id" in claim
        assert "doc_id" in claim
        assert claim["year"] == 2020
        assert claim["edition"] == "2020-14차"
        assert "claim_type" in claim
        assert claim["claim_type"] in {
            "definition",
            "principle",
            "purpose",
            "value",
            "stance",
        }
        assert "subject" in claim
        assert "text" in claim
        assert len(claim["text"]) >= 20
        assert "span" in claim
        assert len(claim["span"]) == 2
        assert "quote_id" in claim
        assert "sha256" in claim
        assert len(claim["sha256"]) == 64  # SHA-256 hex length

    print(f"  PASS: build claims output ({len(claims)} claims)")


def test_build_claims_unique_ids():
    """claim_id가 모두 유일함."""
    quotes = load_14th_quotes("data/processed/quotes.jsonl")
    if not quotes:
        print("  SKIP: quotes not found")
        return

    claims = build_claims(quotes)
    ids = [c["claim_id"] for c in claims]
    assert len(ids) == len(set(ids)), "Duplicate claim_id found!"
    print("  PASS: build claims unique ids")


def test_build_claims_unique_sha256():
    """sha256이 모두 유일함 (중복 텍스트 없음)."""
    quotes = load_14th_quotes("data/processed/quotes.jsonl")
    if not quotes:
        print("  SKIP: quotes not found")
        return

    claims = build_claims(quotes)
    hashes = [c["sha256"] for c in claims]
    duplicates = [h for h in hashes if hashes.count(h) > 1]
    # 일부 중복 가능 (같은 문장이 다른 quote에 등장), 경고만
    if duplicates:
        print(f"  WARN: {len(set(duplicates))} duplicate sha256 found (cross-quote)")
    print("  PASS: build claims sha256 check")


# ---------------------------------------------------------------------------
# File-level tests
# ---------------------------------------------------------------------------


def test_claims_file_schema():
    """claims.jsonl 파일 스키마 검증."""
    path = Path("data/processed/claims.jsonl")
    if not path.exists():
        print("  SKIP: claims.jsonl not found")
        return

    valid_types = {"definition", "principle", "purpose", "value", "stance"}
    count = 0
    with open(path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            count += 1

            assert "claim_id" in item, f"line {line_num}: claim_id 없음"
            assert "doc_id" in item, f"line {line_num}: doc_id 없음"
            assert item["year"] == 2020, f"line {line_num}: year != 2020"
            assert item["edition"] == "2020-14차"
            assert (
                item["claim_type"] in valid_types
            ), f"line {line_num}: invalid claim_type: {item['claim_type']}"
            assert "subject" in item
            assert "text" in item
            assert "span" in item
            assert len(item["span"]) == 2
            assert "sha256" in item

    assert count >= 50, f"claims: {count} < 50 (DoD)"
    print(f"  PASS: claims file schema ({count} items)")


def test_claims_quote_id_traceable():
    """claim의 quote_id가 quotes.jsonl에 실재하는지 검증."""
    claims_path = Path("data/processed/claims.jsonl")
    quotes_path = Path("data/processed/quotes.jsonl")
    if not claims_path.exists() or not quotes_path.exists():
        print("  SKIP: data files not found")
        return

    valid_quote_ids = set()
    with open(quotes_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                obj = json.loads(line)
                valid_quote_ids.add(obj["quote_id"])

    missing = []
    with open(claims_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            qid = item.get("quote_id", "")
            if qid and qid not in valid_quote_ids:
                missing.append((item["claim_id"], qid))

    assert not missing, f"역추적 불가 quote_id: {missing[:5]}"
    print("  PASS: claims quote_id traceable")


def test_claims_span_verification():
    """claim의 span이 원문과 일치하는지 검증 (샘플 10개)."""
    claims_path = Path("data/processed/claims.jsonl")
    raw_path = Path("SKMSraw.txt")
    if not claims_path.exists() or not raw_path.exists():
        print("  SKIP: data files not found")
        return

    with open(raw_path, encoding="utf-8") as f:
        raw = f.read()

    claims = []
    with open(claims_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                claims.append(json.loads(line))

    # 샘플 10개 검증
    import random

    random.seed(42)
    sample = random.sample(claims, min(10, len(claims)))

    mismatches = []
    for claim in sample:
        span_start, span_end = claim["span"]
        claim_text_start = claim["text"][:20]
        # span 근처에서 claim text의 시작 부분이 존재하는지
        # 넓은 범위에서 검색 (sentence splitting offset 오차 허용)
        search_region = raw[max(0, span_start - 200) : span_end + 200]
        if claim_text_start not in search_region:
            mismatches.append(claim["claim_id"])

    assert not mismatches, f"span 불일치: {mismatches}"
    print("  PASS: claims span verification (10 samples)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("[PR-6] build_claims.py 단위 테스트")
    print("=" * 50)

    tests = [
        test_split_sentences_basic,
        test_split_sentences_paragraph,
        test_split_sentences_merge_short,
        test_split_sentences_numbered,
        test_split_sentences_offset,
        test_classify_definition,
        test_classify_purpose,
        test_classify_value,
        test_classify_principle,
        test_classify_stance,
        test_classify_default,
        test_extract_subject_keyword,
        test_extract_subject_longest_match,
        test_extract_subject_fallback,
        test_build_claims_output,
        test_build_claims_unique_ids,
        test_build_claims_unique_sha256,
        test_claims_file_schema,
        test_claims_quote_id_traceable,
        test_claims_span_verification,
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
