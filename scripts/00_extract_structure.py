#!/usr/bin/env python3
"""SKMS 원문에서 개정판 경계 + 헤더 계층을 추출하고 toc.json을 생성한다.

출력:
  - data/processed/structure.json : 개정판 경계 + 중첩 헤더 트리
  - data/processed/toc.json       : 플랫 TOC (탐색/UI용)

Usage:
    python scripts/00_extract_structure.py
    python scripts/00_extract_structure.py --input data/raw/SKMSraw.txt
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

# ─────────────────────────────────────────────────────────────────────────────
# Config 로드
# ─────────────────────────────────────────────────────────────────────────────


def load_patterns(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────────────────────────────────────
# 1) 개정판 경계 감지
# ─────────────────────────────────────────────────────────────────────────────


def detect_editions(lines: list[str], patterns: dict) -> list[dict]:
    """type_a + type_b 정규식으로 개정판 경계를 감지한다."""
    edition_pats = patterns["edition_patterns"]
    compiled: list[tuple[str, re.Pattern]] = []
    for name in ("type_a", "type_b"):
        if name in edition_pats:
            compiled.append((name, re.compile(edition_pats[name]["pattern"])))

    editions: list[dict] = []
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        for pat_name, regex in compiled:
            m = regex.search(stripped)
            if m:
                info = _parse_edition(stripped, pat_name, i)
                if info:
                    editions.append(info)
                break

    # 중복 제거 (같은 라인 번호)
    seen: set[int] = set()
    deduped: list[dict] = []
    for ed in editions:
        if ed["start_line"] not in seen:
            seen.add(ed["start_line"])
            deduped.append(ed)

    # end_line 계산
    for i, ed in enumerate(deduped):
        ed["end_line"] = (
            deduped[i + 1]["start_line"] - 1 if i + 1 < len(deduped) else len(lines)
        )

    return deduped


def _parse_edition(text: str, pat_type: str, line_no: int) -> dict | None:
    if pat_type == "type_a":
        year_m = re.search(r"(\d{4})년", text)
        label_m = re.search(r"(초판|\d+차)", text)
        if not year_m or not label_m:
            return None
        year = int(year_m.group(1))
        label = label_m.group(1)
    elif pat_type == "type_b":
        num_m = re.search(r"(\d+)차", text)
        year_m = re.search(r"(\d{4})", text)
        if not num_m or not year_m:
            return None
        year = int(year_m.group(1))
        label = f"{num_m.group(1)}차"
    else:
        return None

    return {
        "edition_id": f"{year}-{label}",
        "year": year,
        "label": label,
        "start_line": line_no,
        "end_line": -1,
        "match_type": pat_type,
        "raw_text": text.strip(),
        "sections": [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2) 헤더 파싱 (H1~H4b, 5단계)
# ─────────────────────────────────────────────────────────────────────────────

LEVEL_ORDER = {"H1": 1, "H2": 2, "H3": 3, "H4": 4, "H4b": 4}


def compile_header_patterns(patterns: dict) -> list[tuple[str, re.Pattern]]:
    """header_patterns에서 pattern 필드가 있는 것만 컴파일한다."""
    hp = patterns.get("header_patterns", {})
    result: list[tuple[str, re.Pattern]] = []
    for level in ("H1", "H2", "H3", "H4", "H4b"):
        cfg = hp.get(level, {})
        pat_str = cfg.get("pattern")
        if pat_str:
            result.append((level, re.compile(pat_str)))
    return result


def parse_headers(
    lines: list[str],
    editions: list[dict],
    header_pats: list[tuple[str, re.Pattern]],
) -> None:
    """각 개정판 내에서 헤더 계층을 파싱하여 sections에 채운다."""
    for edition in editions:
        start = edition["start_line"]
        end = edition["end_line"]
        stack: list[dict] = []

        for line_no in range(start, min(end + 1, len(lines) + 1)):
            text = lines[line_no - 1].strip()
            if not text:
                continue

            for level, regex in header_pats:
                if regex.search(text):
                    # [Phase 11] 제목에 본문이 결합된 형태 처리 (1. 제목: 본문)
                    clean_title = text
                    if ":" in text:
                        parts = text.split(":", 1)
                        # 제목 부분이 너무 길지 않고(패턴 매칭 부위), 뒤에 충분한 내용이 있다면 분리
                        if len(parts[0]) < 100: 
                            clean_title = parts[0].strip()
                    
                    section = {
                        "level": level,
                        "title": clean_title,
                        "line": line_no,
                        "children": [],
                    }
                    _insert_section(edition["sections"], stack, section, level)
                    break


def _insert_section(
    root: list[dict],
    stack: list[dict],
    new: dict,
    level: str,
) -> None:
    new_depth = LEVEL_ORDER.get(level, 99)
    while stack and LEVEL_ORDER.get(stack[-1]["level"], 99) >= new_depth:
        stack.pop()
    if stack:
        stack[-1]["children"].append(new)
    else:
        root.append(new)
    stack.append(new)


# ─────────────────────────────────────────────────────────────────────────────
# 3) 헤더 갭 감지 (header_gap_suspect)
# ─────────────────────────────────────────────────────────────────────────────


def detect_header_gaps(
    lines: list[str],
    editions: list[dict],
    header_pats: list[tuple[str, re.Pattern]],
    threshold: int,
) -> list[dict]:
    """헤더 없이 threshold 줄 이상 연속되는 구간을 반환한다."""
    gaps: list[dict] = []

    for edition in editions:
        start = edition["start_line"]
        end = edition["end_line"]
        last_header_line = start

        for line_no in range(start, min(end + 1, len(lines) + 1)):
            text = lines[line_no - 1].strip()
            if not text:
                continue

            is_header = any(regex.search(text) for _, regex in header_pats)
            if is_header:
                gap = line_no - last_header_line
                if gap > threshold:
                    gaps.append(
                        {
                            "edition_id": edition["edition_id"],
                            "start_line": last_header_line,
                            "end_line": line_no,
                            "gap_lines": gap,
                        }
                    )
                last_header_line = line_no

        # 마지막 헤더 이후 ~ 개정판 끝
        final_gap = end - last_header_line
        if final_gap > threshold:
            gaps.append(
                {
                    "edition_id": edition["edition_id"],
                    "start_line": last_header_line,
                    "end_line": end,
                    "gap_lines": final_gap,
                }
            )

    return gaps


# ─────────────────────────────────────────────────────────────────────────────
# 4) TOC 생성 (플랫 리스트)
# ─────────────────────────────────────────────────────────────────────────────


def build_toc(editions: list[dict]) -> list[dict]:
    """중첩 섹션 트리를 플랫 TOC 리스트로 변환한다."""
    toc: list[dict] = []

    for edition in editions:
        # 개정판 자체를 TOC 항목으로
        toc.append(
            {
                "level": "H0",
                "title": edition["raw_text"],
                "edition_id": edition["edition_id"],
                "line": edition["start_line"],
                "path": [edition["edition_id"]],
            }
        )
        # 하위 섹션을 재귀적으로 플랫화
        _flatten_sections(
            edition["sections"],
            toc,
            edition["edition_id"],
            path_prefix=[edition["edition_id"]],
        )

    return toc


def _flatten_sections(
    sections: list[dict],
    toc: list[dict],
    edition_id: str,
    path_prefix: list[str],
) -> None:
    for section in sections:
        current_path = path_prefix + [section["title"]]
        toc.append(
            {
                "level": section["level"],
                "title": section["title"],
                "edition_id": edition_id,
                "line": section["line"],
                "path": current_path,
            }
        )
        if section.get("children"):
            _flatten_sections(section["children"], toc, edition_id, current_path)


# ─────────────────────────────────────────────────────────────────────────────
# 유틸리티
# ─────────────────────────────────────────────────────────────────────────────


def count_sections(sections: list[dict]) -> int:
    total = len(sections)
    for s in sections:
        total += count_sections(s.get("children", []))
    return total


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SKMS 개정판 경계 + 헤더 구조 파싱 → structure.json + toc.json"
    )
    parser.add_argument("--input", default="data/raw/SKMSraw.txt", help="원본 텍스트")
    parser.add_argument(
        "--output", default="data/processed/structure.json", help="구조 JSON"
    )
    parser.add_argument("--toc", default="data/processed/toc.json", help="TOC JSON")
    parser.add_argument("--config", default="config/regex_patterns.yaml", help="정규식 설정")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    toc_path = Path(args.toc)
    config_path = Path(args.config)

    for path, label in [(input_path, "입력 파일"), (config_path, "설정 파일")]:
        if not path.exists():
            print(f"Error: {label}을 찾을 수 없습니다: {path}", file=sys.stderr)
            sys.exit(1)

    patterns = load_patterns(config_path)
    lines = input_path.read_text(encoding="utf-8").splitlines()
    print(f"[00] 원본 로드: {len(lines):,}줄", file=sys.stderr)

    # ── 개정판 경계 감지 ──
    editions = detect_editions(lines, patterns)
    print(f"[00] 개정판 감지: {len(editions)}개", file=sys.stderr)
    for ed in editions:
        span = ed["end_line"] - ed["start_line"] + 1
        print(
            f"     {ed['edition_id']:>12}  L{ed['start_line']:>5}–{ed['end_line']:>5}  ({span:>5}줄)",
            file=sys.stderr,
        )

    # ── 헤더 파싱 ──
    header_pats = compile_header_patterns(patterns)
    parse_headers(lines, editions, header_pats)

    total_sections = sum(count_sections(ed["sections"]) for ed in editions)
    print(f"[00] 전체 헤더: {total_sections}개", file=sys.stderr)

    # ── 헤더 갭 감지 ──
    gap_threshold = (
        patterns.get("quality_flags", {})
        .get("header_gap_suspect", {})
        .get("threshold_lines", 200)
    )
    header_gaps = detect_header_gaps(lines, editions, header_pats, gap_threshold)
    print(f"[00] 헤더 갭 (>{gap_threshold}줄): {len(header_gaps)}곳", file=sys.stderr)
    for g in header_gaps:
        print(
            f"     {g['edition_id']:>12}  L{g['start_line']:>5}–{g['end_line']:>5}  ({g['gap_lines']}줄)",
            file=sys.stderr,
        )

    # ── structure.json 저장 ──
    structure = {
        "source_file": str(input_path),
        "total_lines": len(lines),
        "edition_count": len(editions),
        "total_sections": total_sections,
        "header_gaps": header_gaps,
        "editions": editions,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(structure, f, ensure_ascii=False, indent=2)
    print(f"[00] 출력: {output_path}", file=sys.stderr)

    # ── toc.json 저장 ──
    toc = build_toc(editions)
    toc_path.parent.mkdir(parents=True, exist_ok=True)
    with open(toc_path, "w", encoding="utf-8") as f:
        json.dump(toc, f, ensure_ascii=False, indent=2)
    print(f"[00] TOC: {toc_path} ({len(toc)}개 항목)", file=sys.stderr)


if __name__ == "__main__":
    main()
