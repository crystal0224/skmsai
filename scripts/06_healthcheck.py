#!/usr/bin/env python3
"""SKMS 파이프라인 Healthcheck — 본격 개발 착수 가능 여부 자동 판정.

5개 PASS 체크를 자동 수행하고, FAIL 시 원인 후보 + 수정 액션을 출력.

Usage:
    python scripts/06_healthcheck.py
    python scripts/06_healthcheck.py --raw data/raw/SKMSraw.txt --sample_k 20
    python scripts/06_healthcheck.py --auto-generate  # 생성물 없으면 자동 생성 시도
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STOPWORDS = frozenset(
    [
        "있다",
        "없다",
        "하다",
        "되다",
        "이다",
        "것이다",
        "한다",
        "된다",
        "위해",
        "대해",
        "따라",
        "통해",
        "그리고",
        "그러나",
        "또한",
        "즉",
        "또는",
        "및",
        "등",
        "위한",
        "대한",
        "있는",
        "없는",
        "하는",
        "되는",
        "이런",
        "저런",
        "그런",
        "같은",
        "모든",
        "각각",
        "때문",
        "경우",
        "이를",
        "이에",
        "것을",
        "것은",
        "것이",
        "수준",
        "필요",
        "해야",
        "위하여",
        "함으로써",
        "있으며",
        "하고",
        "하며",
        "하여",
        "바와",
    ]
)

# docs.jsonl 필수 필드 (실제 스키마 기준)
DOCS_REQUIRED_FIELDS = {"edition_id", "year", "label", "text", "char_span"}

# quotes.jsonl 필수 필드 (실제 스키마 기준)
QUOTES_REQUIRED_FIELDS = {
    "quote_id",
    "edition_id",
    "type",
    "section_path",
    "text",
    "char_span",
    "sha256",
    "quality_flags",
}


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------


class CheckResult:
    """단일 체크 결과를 담는 클래스."""

    __slots__ = ("name", "status", "summary", "details", "fix_actions")

    def __init__(self, name: str) -> None:
        self.name = name
        self.status: str = "PASS"  # PASS | FAIL | WARN
        self.summary: str = ""
        self.details: list[str] = []
        self.fix_actions: list[str] = []

    def fail(self, summary: str, detail: str = "", fix: str = "") -> None:
        self.status = "FAIL"
        self.summary = summary
        if detail:
            self.details.append(detail)
        if fix:
            self.fix_actions.append(fix)

    def warn(self, summary: str, detail: str = "") -> None:
        if self.status != "FAIL":
            self.status = "WARN"
            self.summary = summary
        if detail:
            self.details.append(detail)

    def ok(self, summary: str) -> None:
        if self.status == "PASS":
            self.summary = summary


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def normalize_ws(text: str) -> str:
    """공백 정규화: 연속 공백/탭/줄바꿈을 단일 공백으로."""
    return re.sub(r"\s+", " ", text).strip()


def load_jsonl(path: Path) -> list[dict]:
    """JSONL 파일을 읽어 리스트로 반환."""
    items: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                items.append(json.loads(stripped))
            except json.JSONDecodeError as e:
                raise ValueError(f"JSONL 파싱 오류 (라인 {i}): {e}") from e
    return items


def extract_korean_terms(text: str, min_len: int = 2, max_len: int = 6) -> list[str]:
    """한글 중심 용어 후보를 추출한다."""
    pattern = re.compile(r"[가-힣]{" + str(min_len) + "," + str(max_len) + "}")
    terms = pattern.findall(text)
    return [t for t in terms if t not in STOPWORDS]


# ---------------------------------------------------------------------------
# CHK-1: docs.jsonl 분할 무결성
# ---------------------------------------------------------------------------


def check_docs(docs_path: Path, min_docs: int) -> CheckResult:
    """[CHK-1] docs.jsonl 분할 무결성 검사."""
    result = CheckResult("CHK-1")

    # 파일 존재
    if not docs_path.exists():
        result.fail(
            f"docs.jsonl 파일 없음: {docs_path}",
            fix="python scripts/00_extract_structure.py && python scripts/01_split_docs.py",
        )
        return result

    # JSONL 파싱
    try:
        docs = load_jsonl(docs_path)
    except ValueError as e:
        result.fail(f"docs.jsonl 파싱 실패: {e}")
        return result

    # 문서 수
    if len(docs) < min_docs:
        result.fail(
            f"문서 수 부족: {len(docs)}개 < 최소 {min_docs}개",
            fix="scripts/01_split_docs.py의 분할 로직 또는 structure.json 확인",
        )
        return result

    # 필수 필드
    for i, doc in enumerate(docs):
        missing = DOCS_REQUIRED_FIELDS - set(doc.keys())
        if missing:
            result.fail(
                f"문서 {i}에 필수 필드 누락: {missing}",
                detail=f"edition_id={doc.get('edition_id', '?')}",
                fix="scripts/01_split_docs.py의 출력 스키마 확인",
            )
            return result

    # doc_id(edition_id) 중복
    ids = [d["edition_id"] for d in docs]
    dupes = [eid for eid, cnt in Counter(ids).items() if cnt > 1]
    if dupes:
        result.fail(
            f"edition_id 중복: {dupes}",
            fix="scripts/01_split_docs.py의 edition_id 생성 로직 확인",
        )
        return result

    # content(text) 비어있지 않음
    empty = [d["edition_id"] for d in docs if not d.get("text", "").strip()]
    if empty:
        result.fail(
            f"text가 비어있는 문서: {empty}",
            fix="scripts/01_split_docs.py의 텍스트 슬라이싱 확인",
        )
        return result

    result.ok(f"PASS — {len(docs)}개 문서, 필드 완전, 중복 없음")
    return result


# ---------------------------------------------------------------------------
# CHK-2: toc.json 구조 생성
# ---------------------------------------------------------------------------


def check_toc(toc_path: Path, min_toc_nodes: int) -> CheckResult:
    """[CHK-2] toc.json 구조 검사."""
    result = CheckResult("CHK-2")

    if not toc_path.exists():
        result.fail(
            f"toc.json 파일 없음: {toc_path}",
            fix="python scripts/00_extract_structure.py --toc data/processed/toc.json",
        )
        return result

    try:
        with open(toc_path, encoding="utf-8") as f:
            toc = json.load(f)
    except json.JSONDecodeError as e:
        result.fail(f"toc.json JSON 파싱 실패: {e}")
        return result

    # 배열인지 확인
    if not isinstance(toc, list):
        result.fail(
            "toc.json 최상위가 배열이 아님",
            fix="scripts/00_extract_structure.py의 TOC 출력 형식 확인",
        )
        return result

    if len(toc) == 0:
        result.fail("toc.json이 비어있음")
        return result

    # 개정판별 노드 수 집계
    edition_nodes: dict[str, int] = {}
    for node in toc:
        eid = node.get("edition_id", "unknown")
        if node.get("level", "") != "H0":  # H0은 개정판 자체
            edition_nodes[eid] = edition_nodes.get(eid, 0) + 1

    # 최소 1개 문서에서 min_toc_nodes 이상
    max_nodes = max(edition_nodes.values()) if edition_nodes else 0
    if max_nodes < min_toc_nodes:
        result.fail(
            f"최대 노드 수 {max_nodes} < 최소 {min_toc_nodes}",
            detail=f"개정판별 노드: {edition_nodes}",
            fix="scripts/00_extract_structure.py의 헤더 정규식 확인",
        )
        return result

    # 전부 경고인지 확인 (quality_flag 관련)
    # toc.json에는 quality_flag가 없으므로, 헤더 없는 구간은 structure.json에서 확인
    total_nodes = sum(edition_nodes.values())
    editions_with_nodes = len([e for e, n in edition_nodes.items() if n > 0])

    result.ok(
        f"PASS — {total_nodes}개 노드, {editions_with_nodes}개 개정판 커버, "
        f"최대 {max_nodes}개/판"
    )
    return result


# ---------------------------------------------------------------------------
# CHK-3: quotes.jsonl 기본 생성 및 타입 커버리지
# ---------------------------------------------------------------------------


def check_quotes(quotes_path: Path, min_quotes: int) -> CheckResult:
    """[CHK-3] quotes.jsonl 기본 생성 및 타입 커버리지."""
    result = CheckResult("CHK-3")

    if not quotes_path.exists():
        result.fail(
            f"quotes.jsonl 파일 없음: {quotes_path}",
            fix="python scripts/02_extract_quotes.py",
        )
        return result

    try:
        quotes = load_jsonl(quotes_path)
    except ValueError as e:
        result.fail(f"quotes.jsonl 파싱 실패: {e}")
        return result

    # 최소 quote 수
    if len(quotes) < min_quotes:
        result.fail(
            f"quote 수 부족: {len(quotes)}개 < 최소 {min_quotes}개",
            fix="scripts/02_extract_quotes.py의 추출 규칙 또는 입력 docs.jsonl 확인",
        )
        return result

    # 필수 필드
    for i, q in enumerate(quotes[:20]):  # 처음 20개 샘플 검사
        missing = QUOTES_REQUIRED_FIELDS - set(q.keys())
        if missing:
            result.fail(
                f"quote {i}에 필수 필드 누락: {missing}",
                detail=f"quote_id={q.get('quote_id', '?')}",
                fix="scripts/02_extract_quotes.py의 출력 스키마 확인",
            )
            return result

    # 타입 분포
    type_counts = Counter(q.get("type", "unknown") for q in quotes)
    distinct_types = len(type_counts)
    if distinct_types < 4:
        result.fail(
            f"타입 다양성 부족: {distinct_types}종 < 최소 4종",
            detail=f"분포: {dict(type_counts)}",
            fix="config/pipeline.yaml의 quote_extraction.types 패턴 튜닝",
        )
        return result

    # definition 최소 5개
    def_count = type_counts.get("definition", 0)
    if def_count < 5:
        result.fail(
            f"definition 타입 부족: {def_count}개 < 최소 5개",
            detail=f"분포: {dict(type_counts)}",
            fix="config/pipeline.yaml의 definition 패턴/키워드 확장",
        )
        return result

    type_str = ", ".join(f"{t}={c}" for t, c in type_counts.most_common())
    result.ok(f"PASS — {len(quotes)}개 quote, {distinct_types}종 타입 ({type_str})")
    return result


# ---------------------------------------------------------------------------
# CHK-4: Quote 무결성 (원문 일치)
# ---------------------------------------------------------------------------


def check_quote_integrity(
    quotes_path: Path,
    raw_path: Path,
    sample_k: int,
) -> CheckResult:
    """[CHK-4] 랜덤 샘플 K개의 quote가 원문과 일치하는지 검사."""
    result = CheckResult("CHK-4")

    if not quotes_path.exists():
        result.fail("quotes.jsonl 파일 없음 (CHK-3에서 이미 감지)")
        return result
    if not raw_path.exists():
        result.fail(
            f"원본 파일 없음: {raw_path}",
            fix="data/raw/ 디렉토리에 SKMSraw.txt 배치",
        )
        return result

    try:
        quotes = load_jsonl(quotes_path)
    except ValueError:
        result.fail("quotes.jsonl 파싱 실패 (CHK-3에서 이미 감지)")
        return result

    raw_text = raw_path.read_text(encoding="utf-8")

    # 샘플 선택 (균등 간격)
    step = max(1, len(quotes) // sample_k)
    samples = [quotes[i] for i in range(0, len(quotes), step)][:sample_k]

    mismatches: list[dict] = []
    for q in samples:
        span = q.get("char_span", [])
        if not span or len(span) != 2:
            mismatches.append(
                {
                    "quote_id": q.get("quote_id", "?"),
                    "reason": "char_span 형식 오류",
                }
            )
            continue

        start, end = span
        if start < 0 or end > len(raw_text) or start >= end:
            mismatches.append(
                {
                    "quote_id": q.get("quote_id", "?"),
                    "reason": f"char_span 범위 초과: [{start}, {end}] (raw 길이: {len(raw_text)})",
                }
            )
            continue

        raw_slice = raw_text[start:end]
        quote_text = q.get("text", "")

        # 공백 정규화 후 비교: quote_text가 raw_slice 안에 포함되면 OK
        norm_quote = normalize_ws(quote_text)
        norm_raw = normalize_ws(raw_slice)

        if norm_quote not in norm_raw:
            # 더 상세한 비교: 첫 50자, 마지막 50자
            q_head = norm_quote[:50]
            r_head = norm_raw[:50]
            mismatches.append(
                {
                    "quote_id": q.get("quote_id", "?"),
                    "reason": "텍스트 불일치",
                    "quote_head": q_head,
                    "raw_head": r_head,
                }
            )

    # SHA-256 검증 (샘플 전체)
    sha_fails: list[str] = []
    for q in samples:
        expected_sha = q.get("sha256", "")
        if not expected_sha:
            continue
        actual_sha = hashlib.sha256(q.get("text", "").encode("utf-8")).hexdigest()
        if actual_sha != expected_sha:
            sha_fails.append(q.get("quote_id", "?"))

    if mismatches:
        detail_lines = []
        for m in mismatches:
            detail_lines.append(f"  - {m['quote_id']}: {m['reason']}")
            if "quote_head" in m:
                detail_lines.append(f"    quote: {m['quote_head']}...")
                detail_lines.append(f"    raw:   {m['raw_head']}...")
        result.fail(
            f"원문 불일치: {len(mismatches)}/{len(samples)}건",
            detail="\n".join(detail_lines),
            fix="scripts/02_extract_quotes.py의 char_span 계산 로직 확인",
        )
        return result

    if sha_fails:
        result.fail(
            f"SHA-256 불일치: {len(sha_fails)}건",
            detail=f"quote_ids: {sha_fails}",
            fix="scripts/02_extract_quotes.py의 sha256 계산 확인",
        )
        return result

    result.ok(f"PASS — {len(samples)}건 샘플 모두 원문 일치 + SHA-256 검증 통과")
    return result


# ---------------------------------------------------------------------------
# CHK-5: Temporal Conflict Guardrail 발동 시뮬레이션
# ---------------------------------------------------------------------------


def check_temporal_conflict(quotes_path: Path) -> CheckResult:
    """[CHK-5] definition quote에서 교차 개정판 용어 충돌을 시뮬레이션."""
    result = CheckResult("CHK-5")

    if not quotes_path.exists():
        result.fail("quotes.jsonl 파일 없음 (CHK-3에서 이미 감지)")
        return result

    try:
        quotes = load_jsonl(quotes_path)
    except ValueError:
        result.fail("quotes.jsonl 파싱 실패")
        return result

    # definition quote만 추출
    definitions = [q for q in quotes if q.get("type") == "definition"]
    if not definitions:
        result.warn(
            "WARN — definition quote 0건, 충돌 시뮬레이션 불가",
            detail="definition 패턴 개선 또는 LLM fallback 활성화 권장",
        )
        return result

    # 용어 추출: definition text에서 빈도 상위 용어 후보
    term_editions: dict[str, set[str]] = {}  # term → {edition_id, ...}
    term_quote_ids: dict[str, list[str]] = {}  # term → [quote_id, ...]

    for q in definitions:
        text = q.get("text", "")
        edition = q.get("edition_id", "unknown")
        qid = q.get("quote_id", "?")
        terms = extract_korean_terms(text)

        for term in set(terms):  # 중복 제거
            term_editions.setdefault(term, set()).add(edition)
            term_quote_ids.setdefault(term, []).append(qid)

    # 교차 개정판 충돌 후보: 2개 이상 개정판에 동일 term 등장
    conflicts: list[dict] = []
    for term, editions in term_editions.items():
        if len(editions) >= 2:
            conflicts.append(
                {
                    "term": term,
                    "editions": sorted(editions),
                    "quote_count": len(term_quote_ids[term]),
                }
            )

    # 빈도순 정렬
    conflicts.sort(key=lambda x: x["quote_count"], reverse=True)

    if not conflicts:
        result.warn(
            "WARN — 교차 개정판 용어 충돌 후보 0건 (다른 체크가 PASS면 전체 PASS 허용)",
            detail="definition quote가 단일 개정판에만 집중되거나, " "용어 추출 정밀도 개선 필요",
        )
        return result

    top5 = conflicts[:5]
    detail_lines = [
        f"  - '{c['term']}': {len(c['editions'])}개 개정판 "
        f"({', '.join(c['editions'][:3])}{'...' if len(c['editions']) > 3 else ''}), "
        f"{c['quote_count']}건"
        for c in top5
    ]

    result.ok(
        f"PASS — 충돌 후보 {len(conflicts)}개 검출 "
        f"(상위: {', '.join(c['term'] for c in top5[:3])})"
    )
    result.details.extend(detail_lines)
    return result


# ---------------------------------------------------------------------------
# Auto-generate missing files
# ---------------------------------------------------------------------------


def auto_generate(raw_path: Path) -> list[str]:
    """생성물이 없으면 scripts/00~02를 자동 호출한다."""
    log: list[str] = []
    scripts = [
        ("scripts/00_extract_structure.py", "data/processed/structure.json"),
        ("scripts/01_split_docs.py", "data/processed/docs.jsonl"),
        ("scripts/02_extract_quotes.py", "data/processed/quotes.jsonl"),
    ]

    for script, output in scripts:
        if Path(output).exists():
            log.append(f"  [SKIP] {output} 이미 존재")
            continue

        if not Path(script).exists():
            log.append(f"  [SKIP] {script} 없음, 건너뜀")
            continue

        log.append(f"  [RUN]  {script} 실행 중...")
        try:
            proc = subprocess.run(
                [sys.executable, script],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if proc.returncode == 0:
                log.append(f"  [OK]   {output} 생성 완료")
            else:
                log.append(f"  [ERR]  {script} 실패: {proc.stderr[:200]}")
        except subprocess.TimeoutExpired:
            log.append(f"  [ERR]  {script} 타임아웃 (300초)")
        except Exception as e:
            log.append(f"  [ERR]  {script} 예외: {e}")

    return log


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def format_report(
    results: list[CheckResult],
    auto_gen_log: list[str] | None = None,
) -> str:
    """검사 결과를 포맷팅한다."""
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("SKMS Pipeline Healthcheck Report")
    lines.append(f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 70)

    if auto_gen_log:
        lines.append("\n[Auto-Generate Log]")
        lines.extend(auto_gen_log)

    # 개별 결과
    lines.append("")
    any_fail = False
    for r in results:
        status_icon = {"PASS": "OK", "FAIL": "XX", "WARN": "!!"}[r.status]
        lines.append(f"[{status_icon}] {r.name}: {r.status} — {r.summary}")
        for detail in r.details:
            lines.append(f"     {detail}")
        if r.status == "FAIL":
            any_fail = True

    # Overall
    overall = "FAIL" if any_fail else "PASS"
    lines.append("")
    lines.append("-" * 70)
    lines.append(f"OVERALL: {overall}")
    lines.append("-" * 70)

    # Fix-Next Actions (FAIL일 때만)
    if any_fail:
        lines.append("")
        lines.append("Fix-Next Actions (우선순위순):")
        action_num = 0
        for r in results:
            if r.status == "FAIL":
                for fix in r.fix_actions:
                    action_num += 1
                    lines.append(f"  {action_num}. [{r.name}] {fix}")
                if not r.fix_actions:
                    action_num += 1
                    lines.append(f"  {action_num}. [{r.name}] {r.summary}")
            if action_num >= 5:
                break

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="SKMS 파이프라인 Healthcheck (본격 개발 착수 판정)")
    parser.add_argument(
        "--raw",
        default="data/raw/SKMSraw.txt",
        help="원본 텍스트 경로 (default: data/raw/SKMSraw.txt)",
    )
    parser.add_argument(
        "--docs",
        default="data/processed/docs.jsonl",
        help="docs.jsonl 경로",
    )
    parser.add_argument(
        "--toc",
        default="data/processed/toc.json",
        help="toc.json 경로",
    )
    parser.add_argument(
        "--quotes",
        default="data/processed/quotes.jsonl",
        help="quotes.jsonl 경로",
    )
    parser.add_argument("--min_docs", type=int, default=2, help="최소 문서 수")
    parser.add_argument("--min_quotes", type=int, default=50, help="최소 quote 수")
    parser.add_argument("--min_toc_nodes", type=int, default=5, help="최소 TOC 노드 수")
    parser.add_argument("--sample_k", type=int, default=10, help="원문 대조 샘플 수")
    parser.add_argument(
        "--auto-generate",
        action="store_true",
        help="생성물이 없으면 scripts/00~02를 자동 실행",
    )
    parser.add_argument(
        "--save-report",
        action="store_true",
        help="리포트를 eval/reports/에 저장",
    )
    args = parser.parse_args()

    raw_path = Path(args.raw)
    docs_path = Path(args.docs)
    toc_path = Path(args.toc)
    quotes_path = Path(args.quotes)

    # Auto-generate
    auto_gen_log = None
    if args.auto_generate:
        auto_gen_log = auto_generate(raw_path)

    # 5개 체크 실행
    results: list[CheckResult] = [
        check_docs(docs_path, args.min_docs),
        check_toc(toc_path, args.min_toc_nodes),
        check_quotes(quotes_path, args.min_quotes),
        check_quote_integrity(quotes_path, raw_path, args.sample_k),
        check_temporal_conflict(quotes_path),
    ]

    # 리포트 생성
    report = format_report(results, auto_gen_log)
    print(report)

    # 리포트 저장
    if args.save_report:
        report_dir = Path("eval/reports")
        report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        report_path = report_dir / f"healthcheck_{timestamp}.txt"
        report_path.write_text(report, encoding="utf-8")
        print(f"\n리포트 저장: {report_path}")

    # 종료 코드
    any_fail = any(r.status == "FAIL" for r in results)
    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
