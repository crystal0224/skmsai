#!/usr/bin/env python3
"""명제(Claim) 단위 추출기 (PR-6).

2020-14차 quotes에서 문장 단위로 claim을 추출한다.
경영철학 문서의 특성상, 각 문장이 하나의 명제(정의/원칙/목적/가치/입장)를 담는다.

추출 로직:
  1. 14차 quotes를 로드
  2. 각 quote를 문장 단위로 분할 (마침표 + 줄바꿈 기준)
  3. 각 문장에 claim_type을 분류 (키워드 패턴 기반)
  4. subject를 추출 (주어 or 주제 키워드)
  5. span 기반 원문 위치 기록

Usage:
    python scripts/build_claims.py
    python scripts/build_claims.py --output data/processed/claims.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Claim type classification patterns
# ---------------------------------------------------------------------------

# 우선순위순으로 매칭. 첫 번째 매칭된 타입 사용.
_CLAIM_PATTERNS: list[tuple[str, list[str]]] = [
    (
        "purpose",
        [
            r"목적",
            r"궁극적",
            r"지향점",
            r"위해서?(?:\s|$)",
            r"위한\s",
            r"지향한다",
            r"실현하고자",
        ],
    ),
    (
        "definition",
        [
            r"을\s*말한다",
            r"를\s*말한다",
            r"을\s*뜻한다",
            r"를\s*뜻한다",
            r"이란\b",
            r"란\s",
            r"의미한다",
            r"이다\b",
        ],
    ),
    (
        "value",
        [
            r"가치를?\s*(?:창출|추구|중요|키우)",
            r"핵심\s*(?:동력|가치|원천)",
            r"경쟁력의?\s*원천",
            r"원동력",
            r"행복을?\s*(?:키워|추구|만들|창출)",
            r"지속\s*가능",
        ],
    ),
    (
        "principle",
        [
            r"해야\s*한다",
            r"하여야\s*한다",
            r"어야\s*한다",
            r"추구한다",
            r"실천한다",
            r"노력한다",
            r"장려한다",
            r"조성한다",
            r"갖추어야",
            r"필수적이다",
        ],
    ),
    (
        "stance",
        [
            r"믿음",
            r"믿습니다",
            r"확신",
            r"할\s*것이(?:다|라)",
            r"될\s*것이(?:다|라)",
            r"줄\s*것이(?:다|라)",
            r"할\s*수\s*있다",
            r"될\s*수\s*있다",
            r"나간다",
            r"나갈\s*것",
        ],
    ),
]

# Subject 추출용 키워드 (claim text에서 주제 후보)
_SUBJECT_KEYWORDS = [
    "SKMS",
    "SK",
    "SUPEX",
    "VWBE",
    "To-be Model",
    "Better Company",
    "CbA",
    "KPI",
    "SDGs",
    "구성원 행복",
    "구성원",
    "사회적 가치",
    "경제적 가치",
    "이해관계자 행복",
    "이해관계자",
    "기업문화",
    "패기",
    "리더",
    "회사",
    "경영철학",
    "경영",
    "기업",
    "조직",
    "평가",
    "보상",
    "협력",
    "역량",
    "환경",
]


# ---------------------------------------------------------------------------
# Sentence splitter
# ---------------------------------------------------------------------------


def _split_sentences(text: str) -> list[dict]:
    """텍스트를 문장 단위로 분할하여 (text, start_offset) 쌍을 반환한다.

    분할 기준:
      - 마침표(.) + 공백/줄바꿈
      - 줄바꿈 2개 이상 (단락 구분)

    짧은 문장(10자 미만)은 이전 문장에 병합한다.
    """
    # 줄바꿈 정규화
    normalized = text.replace("\r\n", "\n")

    # 단락 + 문장 분할
    # 먼저 2줄 이상 줄바꿈으로 단락 분리
    paragraphs = re.split(r"\n{2,}", normalized)

    sentences = []
    current_offset = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            # offset 계산을 위해 원본에서 위치 찾기
            idx = text.find("\n\n", current_offset)
            if idx >= 0:
                current_offset = idx + 2
            continue

        # 문장 분할 (마침표 + 공백)
        # 숫자 뒤 마침표는 분할하지 않음 (예: "1." "2.")
        parts = re.split(r"(?<=[^0-9])\.\s+", para)

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # 원본에서 위치 찾기
            start = text.find(part, current_offset)
            if start < 0:
                # 분할 과정에서 약간 달라질 수 있으므로 현재 offset 사용
                start = current_offset

            sentences.append(
                {
                    "text": part,
                    "start": start,
                    "end": start + len(part),
                }
            )
            current_offset = start + len(part)

    # 짧은 문장 병합 (10자 미만)
    merged = []
    for sent in sentences:
        if merged and len(sent["text"]) < 10:
            # 이전 문장에 병합
            prev = merged[-1]
            prev["text"] = prev["text"] + ". " + sent["text"]
            prev["end"] = sent["end"]
        else:
            merged.append(sent)

    return merged


# ---------------------------------------------------------------------------
# Claim classifier
# ---------------------------------------------------------------------------


def _classify_claim_type(text: str) -> str:
    """문장의 claim_type을 키워드 패턴으로 분류한다."""
    for claim_type, patterns in _CLAIM_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, text):
                return claim_type
    return "principle"  # 기본값: 경영철학 문서의 대부분은 원칙


def _extract_subject(text: str) -> str:
    """문장에서 주제(subject)를 추출한다."""
    # 긴 키워드부터 매칭 (longest match first)
    sorted_keywords = sorted(_SUBJECT_KEYWORDS, key=len, reverse=True)
    for keyword in sorted_keywords:
        if keyword in text:
            return keyword
    # 매칭 없으면 첫 명사구 (은/는 앞의 단어)
    match = re.search(r"(\S+?)(?:은|는|이|가)\s", text)
    if match:
        return match.group(1)
    return "일반"


# ---------------------------------------------------------------------------
# Claim builder
# ---------------------------------------------------------------------------


def load_14th_quotes(quotes_path: str) -> list[dict]:
    """quotes.jsonl에서 2020-14차 quotes만 로드한다."""
    path = Path(quotes_path)
    if not path.exists():
        print(f"Error: {quotes_path} 파일이 없습니다.", file=sys.stderr)
        sys.exit(1)

    quotes = []
    with open(path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                print(
                    f"경고: quotes.jsonl line {line_num} 파싱 오류: {e}",
                    file=sys.stderr,
                )
                continue
            if obj.get("edition_id") == "2020-14차":
                quotes.append(obj)
    return quotes


def build_claims(
    quotes: list[dict],
    raw_text: str | None = None,
) -> list[dict]:
    """14차 quotes에서 claim 단위를 추출한다.

    Args:
        quotes: 14차 quote 목록
        raw_text: SKMSraw.txt 원문 (span 정확도 향상용, 없으면 quote 내부 offset 사용)
    """
    claims = []
    claim_counter = 0
    # raw_text에서 검색 시 이전 검색 위치를 기록 (순차 탐색 최적화)
    raw_search_offset = 0

    for quote in quotes:
        quote_id = quote.get("quote_id", "")
        doc_id = "SKMS-2020-14"
        year = 2020
        edition = "2020-14차"
        quote_text = quote.get("text", "")
        quote_span = quote.get("char_span", [0, 0])

        sentences = _split_sentences(quote_text)

        for sent in sentences:
            text = sent["text"].strip()

            # 너무 짧은 문장 제외 (내용이 없는 제목/번호만)
            if len(text) < 20:
                continue

            # 순수 숫자/번호 라인 제외
            if re.match(r"^\d+[\.\)]\s*$", text):
                continue

            # 연도/날짜만 있는 라인 제외
            if re.match(r"^\d{4}년\s*\d{1,2}월\s*$", text.strip()):
                continue

            claim_counter += 1
            claim_type = _classify_claim_type(text)
            subject = _extract_subject(text)

            # span 계산: raw_text가 있으면 직접 검색, 없으면 quote 내부 offset 사용
            if raw_text:
                # claim text의 앞 30자로 검색 (마침표 분할로 인한 미세 차이 허용)
                search_key = text[:30]
                pos = raw_text.find(search_key, max(0, raw_search_offset - 500))
                if pos >= 0:
                    claim_start = pos
                    claim_end = pos + len(text)
                    raw_search_offset = claim_end
                else:
                    # 전체 범위에서 재검색
                    pos = raw_text.find(search_key)
                    if pos >= 0:
                        claim_start = pos
                        claim_end = pos + len(text)
                    else:
                        # fallback: quote 내부 offset
                        claim_start = quote_span[0] + sent["start"]
                        claim_end = quote_span[0] + sent["end"]
            else:
                claim_start = quote_span[0] + sent["start"]
                claim_end = quote_span[0] + sent["end"]

            claim = {
                "claim_id": f"CLM-2020-{claim_counter:04d}",
                "doc_id": doc_id,
                "year": year,
                "edition": edition,
                "claim_type": claim_type,
                "subject": subject,
                "text": text,
                "span": [claim_start, claim_end],
                "quote_id": quote_id,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
            claims.append(claim)

    return claims


def write_claims(claims: list[dict], output_path: str) -> None:
    """claims를 JSONL로 저장한다."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        for claim in claims:
            f.write(json.dumps(claim, ensure_ascii=False) + "\n")

    print(f"[build_claims] {len(claims)}개 claim 저장: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="2020-14차 Claim 단위 추출기 (PR-6)")
    parser.add_argument(
        "--quotes",
        default="data/processed/quotes.jsonl",
        help="quotes.jsonl 경로",
    )
    parser.add_argument(
        "--output",
        default="data/processed/claims.jsonl",
        help="출력 파일 경로",
    )
    parser.add_argument(
        "--raw-text",
        default="SKMSraw.txt",
        help="SKMSraw.txt 경로 (span 정확도 향상용)",
    )
    args = parser.parse_args()

    # 14차 quotes 로드
    quotes = load_14th_quotes(args.quotes)
    print(f"[build_claims] 2020-14차 quotes: {len(quotes)}개")

    if not quotes:
        print("Error: 2020-14차 quotes가 없습니다.", file=sys.stderr)
        sys.exit(1)

    # raw text 로드 (span 정확도 향상)
    raw_text = None
    raw_path = Path(args.raw_text)
    if raw_path.exists():
        with open(raw_path, encoding="utf-8") as f:
            raw_text = f.read()
        print(f"[build_claims] raw text 로드: {len(raw_text)} chars")

    # claim 추출
    claims = build_claims(quotes, raw_text=raw_text)
    print(f"[build_claims] 추출된 claims: {len(claims)}개")

    # 저장
    write_claims(claims, args.output)

    # 요약
    type_counts: dict[str, int] = {}
    subject_counts: dict[str, int] = {}
    for claim in claims:
        ct = claim["claim_type"]
        type_counts[ct] = type_counts.get(ct, 0) + 1
        subj = claim["subject"]
        subject_counts[subj] = subject_counts.get(subj, 0) + 1

    print("\n[요약]")
    print(f"  총 claims: {len(claims)}")
    print("\n  claim_type 분포:")
    for ct, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"    {ct}: {count}개")
    print(f"\n  고유 subject 수: {len(subject_counts)}")
    top_subjects = sorted(subject_counts.items(), key=lambda x: -x[1])[:10]
    print("  상위 subject:")
    for subj, count in top_subjects:
        print(f"    {subj}: {count}개")


if __name__ == "__main__":
    main()
