#!/usr/bin/env python3
"""QuoteObject 추출: docs.jsonl → quotes.jsonl

6종 타입(definition, principle, procedure, checklist, example, narrative)을
규칙 기반으로 분류하고, quote_id + sha256 무결성 해시를 생성한다.

Usage:
    python scripts/02_extract_quotes.py
    python scripts/02_extract_quotes.py --input data/processed/docs.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

# ─────────────────────────────────────────────────────────────────────────────
# 타입 상수
# ─────────────────────────────────────────────────────────────────────────────

QUOTE_TYPES = (
    "definition",
    "principle",
    "procedure",
    "checklist",
    "example",
    "narrative",
)


# ─────────────────────────────────────────────────────────────────────────────
# Config 로드
# ─────────────────────────────────────────────────────────────────────────────


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────────────────────────────────────
# 1) 헤더 패턴 컴파일 (config/regex_patterns.yaml 기반)
# ─────────────────────────────────────────────────────────────────────────────


def compile_header_patterns(patterns_cfg: dict) -> list[tuple[str, re.Pattern]]:
    hp = patterns_cfg.get("header_patterns", {})
    result: list[tuple[str, re.Pattern]] = []
    for level in ("H1", "H2", "H3", "H4", "H4b"):
        pat_str = hp.get(level, {}).get("pattern")
        if pat_str:
            result.append((level, re.compile(pat_str)))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 2) 품질 플래그 감지기
# ─────────────────────────────────────────────────────────────────────────────


def build_quality_detectors(quality_flags: dict) -> list[tuple[str, callable]]:
    detectors: list[tuple[str, callable]] = []

    if "ocr_error" in quality_flags:
        indicators = quality_flags["ocr_error"].get("indicators", [])
        detectors.append(
            ("ocr_error", lambda text, ind=indicators: any(i in text for i in ind))
        )

    if "page_header_leak" in quality_flags:
        pat = re.compile(quality_flags["page_header_leak"]["pattern"])
        detectors.append(("page_header_leak", lambda text, p=pat: bool(p.search(text))))

    if "table_broken" in quality_flags:
        indicators = quality_flags["table_broken"].get("indicators", [])
        detectors.append(
            ("table_broken", lambda text, ind=indicators: any(i in text for i in ind))
        )

    if "reference_unresolved" in quality_flags:
        pat = re.compile(quality_flags["reference_unresolved"]["pattern"])
        detectors.append(
            ("reference_unresolved", lambda text, p=pat: bool(p.search(text)))
        )

    return detectors


def detect_quality_flags(text: str, detectors: list[tuple[str, callable]]) -> list[str]:
    return [name for name, fn in detectors if fn(text)]


# ─────────────────────────────────────────────────────────────────────────────
# 3) 타입별 규칙 컴파일
# ─────────────────────────────────────────────────────────────────────────────


class TypeRule:
    """한 가지 quote type의 판정 규칙."""

    __slots__ = (
        "name",
        "priority",
        "min_score",
        "max_chars",
        "split_if_above",
        "compiled_patterns",
        "keywords",
        "min_consecutive",
    )

    def __init__(self, name: str, cfg: dict) -> None:
        self.name = name
        self.priority = cfg.get("priority", 99)
        self.min_score = cfg.get("min_score", 2)
        self.max_chars = cfg.get("max_chars", 1000)
        self.split_if_above = cfg.get("split_if_above", 1500)
        self.compiled_patterns = [re.compile(p) for p in cfg.get("patterns", [])]
        self.keywords = cfg.get("keywords", [])
        self.min_consecutive = cfg.get("min_consecutive_items", 0)

    def match_score(self, text: str) -> int:
        """텍스트에 대한 매칭 점수.

        checklist는 멀티라인 검사: 패턴이 여러 줄에서 매칭되면 줄당 +2.
        나머지 타입은 패턴 존재 여부만 +2, 키워드 +1.
        """
        score = 0
        if self.name == "checklist":
            # 줄 단위로 패턴 매칭 횟수를 센다
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                for pat in self.compiled_patterns:
                    if pat.search(stripped):
                        score += 2
                        break  # 한 줄에 하나만
        else:
            for pat in self.compiled_patterns:
                if pat.search(text):
                    score += 2
            for kw in self.keywords:
                if kw in text:
                    score += 1
        return score


def compile_type_rules(types_cfg: dict) -> list[TypeRule]:
    rules = []
    for name in QUOTE_TYPES:
        cfg = types_cfg.get(name, {})
        rules.append(TypeRule(name, cfg))
    # priority 순 정렬 (낮을수록 먼저)
    rules.sort(key=lambda r: r.priority)
    return rules


# ─────────────────────────────────────────────────────────────────────────────
# 4) 섹션 경로 탐색
# ─────────────────────────────────────────────────────────────────────────────


def get_section_path(sections: list[dict], target_line: int) -> list[str]:
    path: list[str] = []
    _find_path(sections, target_line, path)
    return path


def _find_path(sections: list[dict], target_line: int, path: list[str]) -> bool:
    for i, sec in enumerate(sections):
        next_line = sections[i + 1]["line"] if i + 1 < len(sections) else float("inf")
        if sec["line"] <= target_line < next_line:
            path.append(sec["title"])
            children = sec.get("children", [])
            if children:
                _find_path(children, target_line, path)
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# 5) 텍스트 세그멘테이션 (헤더 경계 기반)
# ─────────────────────────────────────────────────────────────────────────────


def segment_by_headers(
    text: str,
    edition_start_line: int,
    sections: list[dict],
    header_pats: list[tuple[str, re.Pattern]],
    chunking_cfg: dict,
) -> list[dict]:
    """텍스트를 헤더 경계 기반 세그먼트로 분할한다.

    각 세그먼트는 하나의 헤더부터 다음 헤더 직전까지의 텍스트 블록.
    """
    lines = text.splitlines(keepends=True)
    min_tokens = chunking_cfg.get("min_tokens", 100)
    overlap_tokens = chunking_cfg.get("overlap_tokens", 50)

    # 헤더 위치 수집
    header_indices: list[int] = []  # 0-based index in lines
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        for _, regex in header_pats:
            if regex.search(stripped):
                header_indices.append(idx)
                break

    # 세그먼트 경계 결정
    if not header_indices:
        boundaries = [0]
    else:
        boundaries = list(header_indices)
        if boundaries[0] != 0:
            boundaries.insert(0, 0)

    segments: list[dict] = []
    char_offset = 0
    line_char_offsets = []
    running = 0
    for line in lines:
        line_char_offsets.append(running)
        running += len(line)

    for b_idx, start_idx in enumerate(boundaries):
        end_idx = boundaries[b_idx + 1] if b_idx + 1 < len(boundaries) else len(lines)
        seg_lines = lines[start_idx:end_idx]
        seg_text = "".join(seg_lines)

        if not seg_text.strip():
            continue

        abs_line = edition_start_line + start_idx
        section_path = get_section_path(sections, abs_line)
        char_start = (
            line_char_offsets[start_idx] if start_idx < len(line_char_offsets) else 0
        )
        char_end = char_start + len(seg_text)

        segments.append(
            {
                "text": seg_text,
                "start_line": abs_line,
                "char_start": char_start,
                "char_end": char_end,
                "token_count": len(seg_text.split()),
                "section_path": section_path,
            }
        )

    # 너무 작은 세그먼트를 이전 세그먼트에 병합
    merged: list[dict] = []
    for seg in segments:
        if merged and seg["token_count"] < min_tokens:
            prev = merged[-1]
            prev["text"] += seg["text"]
            prev["char_end"] = seg["char_end"]
            prev["token_count"] += seg["token_count"]
        else:
            merged.append(seg)

    return merged


# ─────────────────────────────────────────────────────────────────────────────
# 6) 타입 판정 (규칙 기반)
# ─────────────────────────────────────────────────────────────────────────────


def classify_type(text: str, rules: list[TypeRule]) -> str:
    """텍스트의 quote type을 판정한다.

    priority 순으로 검사하여, min_score 이상인 첫 번째 타입을 채택.
    어떤 타입도 min_score를 넘지 못하면 narrative(fallback).
    """
    for rule in rules:
        if rule.name == "narrative":
            continue
        score = rule.match_score(text)
        if score >= rule.min_score:
            return rule.name

    return "narrative"


# ─────────────────────────────────────────────────────────────────────────────
# 7) 긴 세그먼트 분할
# ─────────────────────────────────────────────────────────────────────────────


def split_if_too_long(
    segment: dict,
    split_threshold: int,
    max_chars: int,
    overlap_tokens: int,
) -> list[dict]:
    """세그먼트 텍스트가 split_threshold를 초과하면 max_chars 단위로 분할."""
    text = segment["text"]
    if len(text) <= split_threshold:
        return [segment]

    lines = text.splitlines(keepends=True)
    parts: list[dict] = []
    current_lines: list[str] = []
    current_len = 0

    for line in lines:
        if current_len + len(line) > max_chars and current_lines:
            part_text = "".join(current_lines)
            parts.append(
                {
                    **segment,
                    "text": part_text,
                    "token_count": len(part_text.split()),
                    "_split": True,
                }
            )
            # 오버랩: 마지막 몇 줄 유지
            overlap_lines = _get_overlap_lines(current_lines, overlap_tokens)
            current_lines = list(overlap_lines)
            current_len = sum(len(l) for l in current_lines)

        current_lines.append(line)
        current_len += len(line)

    if current_lines:
        part_text = "".join(current_lines)
        parts.append(
            {
                **segment,
                "text": part_text,
                "token_count": len(part_text.split()),
                "_split": True,
            }
        )

    return parts


def _get_overlap_lines(lines: list[str], overlap_tokens: int) -> list[str]:
    result: list[str] = []
    token_count = 0
    for line in reversed(lines):
        token_count += len(line.split())
        result.insert(0, line)
        if token_count >= overlap_tokens:
            break
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 8) quote_id + sha256
# ─────────────────────────────────────────────────────────────────────────────


def make_quote_id(
    doc_id: str,
    section_path: list[str],
    quote_type: str,
    seq: int,
    path_sep: str,
    id_sep: str,
) -> str:
    """quote_id: {doc_id}|{chapter_path_joined}|{type}|{seq}"""
    chapter = path_sep.join(section_path) if section_path else "_root"
    return f"{doc_id}{id_sep}{chapter}{id_sep}{quote_type}{id_sep}{seq:03d}"


def compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="QuoteObject 추출 — 6종 타입 분류 + sha256 해시"
    )
    parser.add_argument("--input", default="data/processed/docs.jsonl", help="입력 JSONL")
    parser.add_argument(
        "--output", default="data/processed/quotes.jsonl", help="출력 JSONL"
    )
    parser.add_argument("--config", default="config/regex_patterns.yaml", help="정규식 설정")
    parser.add_argument(
        "--pipeline-config", default="config/pipeline.yaml", help="파이프라인 설정"
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    config_path = Path(args.config)
    pipeline_path = Path(args.pipeline_config)

    if not input_path.exists():
        print(f"Error: 입력 파일 없음: {input_path}", file=sys.stderr)
        print("  먼저 01_split_docs.py를 실행하세요.", file=sys.stderr)
        sys.exit(1)

    patterns_cfg = load_yaml(config_path)
    pipeline_cfg = load_yaml(pipeline_path)

    pipe = pipeline_cfg.get("pipeline", {})
    chunking_cfg = pipe.get("chunking", {})
    quote_cfg = pipe.get("quote_extraction", {})
    types_cfg = quote_cfg.get("types", {})
    id_sep = quote_cfg.get("id_separator", "|")
    path_sep = quote_cfg.get("path_separator", ">")
    overlap_tokens = chunking_cfg.get("overlap_tokens", 50)

    # 컴파일
    header_pats = compile_header_patterns(patterns_cfg)
    quality_detectors = build_quality_detectors(patterns_cfg.get("quality_flags", {}))
    type_rules = compile_type_rules(types_cfg)

    # 타입별 split 설정 조회용 dict
    type_limits: dict[str, dict] = {}
    for rule in type_rules:
        cfg = types_cfg.get(rule.name, {})
        type_limits[rule.name] = {
            "max_chars": cfg.get("max_chars", 1000),
            "split_if_above": cfg.get("split_if_above", 1500),
        }

    # 통계
    total = 0
    flagged = 0
    type_counts: dict[str, int] = {t: 0 for t in QUOTE_TYPES}

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(input_path, encoding="utf-8") as fin, open(
        output_path, "w", encoding="utf-8"
    ) as fout:
        for line in fin:
            doc = json.loads(line)
            edition_id = doc["edition_id"]
            doc_char_start = doc["char_span"][0]
            sections = doc.get("sections", [])

            # 세그멘테이션
            segments = segment_by_headers(
                doc["text"],
                doc["start_line"],
                sections,
                header_pats,
                chunking_cfg,
            )

            # 타입별 seq 카운터 (edition × section_path × type 단위)
            seq_counters: dict[str, int] = {}

            for seg in segments:
                # 먼저 narrative 기준으로 분할 (가장 보수적 길이)
                default_limits = type_limits.get(
                    "narrative", {"max_chars": 1000, "split_if_above": 1500}
                )
                parts = split_if_too_long(
                    seg,
                    default_limits["split_if_above"],
                    default_limits["max_chars"],
                    overlap_tokens,
                )

                for part in parts:
                    # 개별 파트에서 타입 판정 (분할 후 판정)
                    quote_type = classify_type(part["text"], type_rules)

                    # seq 카운터 키
                    path_key = (
                        path_sep.join(part["section_path"])
                        if part["section_path"]
                        else "_root"
                    )
                    counter_key = f"{edition_id}{id_sep}{path_key}{id_sep}{quote_type}"
                    seq_counters[counter_key] = seq_counters.get(counter_key, 0) + 1
                    seq = seq_counters[counter_key]

                    quote_id = make_quote_id(
                        edition_id,
                        part["section_path"],
                        quote_type,
                        seq,
                        path_sep,
                        id_sep,
                    )
                    text = part["text"]
                    sha = compute_sha256(text)
                    flags = detect_quality_flags(text, quality_detectors)

                    quote = {
                        "quote_id": quote_id,
                        "edition_id": edition_id,
                        "type": quote_type,
                        "section_path": part["section_path"],
                        "text": text,
                        "char_span": [
                            doc_char_start + part["char_start"],
                            doc_char_start + part["char_end"],
                        ],
                        "start_line": part["start_line"],
                        "token_count": part["token_count"],
                        "sha256": sha,
                        "quality_flags": flags,
                    }

                    fout.write(json.dumps(quote, ensure_ascii=False) + "\n")
                    total += 1
                    type_counts[quote_type] += 1
                    if flags:
                        flagged += 1

    # 결과 출력
    print(f"[02] 추출 완료: {total}개 QuoteObject", file=sys.stderr)
    for t in QUOTE_TYPES:
        cnt = type_counts[t]
        pct = cnt / max(total, 1) * 100
        print(f"     {t:12s}: {cnt:>5}개 ({pct:5.1f}%)", file=sys.stderr)
    print(
        f"[02] 품질 플래그: {flagged}개 ({flagged / max(total, 1) * 100:.1f}%)",
        file=sys.stderr,
    )
    print(f"[02] 출력: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
