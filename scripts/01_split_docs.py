#!/usr/bin/env python3
"""개정판별 문서 분할. structure.json + SKMSraw.txt → docs.jsonl

Usage:
    python scripts/01_split_docs.py
    python scripts/01_split_docs.py --structure data/processed/structure.json --raw data/raw/SKMSraw.txt
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="개정판별 문서 분할")
    parser.add_argument(
        "--structure", default="data/processed/structure.json", help="구조 JSON 경로"
    )
    parser.add_argument("--raw", default="data/raw/SKMSraw.txt", help="원본 텍스트 경로")
    parser.add_argument(
        "--output", default="data/processed/docs.jsonl", help="출력 JSONL 경로"
    )
    args = parser.parse_args()

    structure_path = Path(args.structure)
    raw_path = Path(args.raw)
    output_path = Path(args.output)

    if not structure_path.exists():
        print(f"Error: 구조 파일을 찾을 수 없습니다: {structure_path}", file=sys.stderr)
        print("  먼저 00_extract_structure.py를 실행하세요.", file=sys.stderr)
        sys.exit(1)

    if not raw_path.exists():
        print(f"Error: 원본 파일을 찾을 수 없습니다: {raw_path}", file=sys.stderr)
        sys.exit(1)

    with open(structure_path, encoding="utf-8") as f:
        structure = json.load(f)

    raw_text = raw_path.read_text(encoding="utf-8")
    raw_lines = raw_text.splitlines(keepends=True)

    print(f"[01] 구조 로드: {structure['edition_count']}개 개정판", file=sys.stderr)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    total_chars = 0

    with open(output_path, "w", encoding="utf-8") as out:
        for edition in structure["editions"]:
            start_line = edition["start_line"]
            end_line = edition["end_line"]

            # 라인 번호 → 문자 위치 계산
            char_start = sum(len(raw_lines[i]) for i in range(start_line - 1))
            char_end = sum(
                len(raw_lines[i]) for i in range(min(end_line, len(raw_lines)))
            )

            # 텍스트 추출 (라인 기반, 1-indexed)
            text_lines = raw_lines[start_line - 1 : end_line]
            text = "".join(text_lines)
            total_chars += len(text)

            doc = {
                "edition_id": edition["edition_id"],
                "year": edition["year"],
                "label": edition["label"],
                "start_line": start_line,
                "end_line": end_line,
                "char_span": [char_start, char_end],
                "text": text,
                "sections": edition["sections"],
            }

            out.write(json.dumps(doc, ensure_ascii=False) + "\n")

    edition_count = len(structure["editions"])
    print(f"[01] 분할 완료: {edition_count}개 개정판, 총 {total_chars:,}자", file=sys.stderr)
    print(f"[01] 출력: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
