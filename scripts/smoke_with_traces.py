#!/usr/bin/env python3
"""PR-3: 관측 PoC 스모크 러너 — Q1~Q6 실행 + trace_id 수집 + 리포트 생성.

ANTHROPIC_API_KEY 없이 실행 가능 (deterministic 라우팅).
각 질의마다 PipelineTrace를 생성하여 trace_id와 단계별 이벤트를 수집하고,
Markdown 리포트를 eval/reports/smoke_with_traces_YYYYMMDD_HHMM.md에 저장한다.

Usage:
    python scripts/smoke_with_traces.py
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from pathlib import Path

# 프로젝트 루트로 이동
project_root = Path(__file__).resolve().parent.parent
os.chdir(project_root)

# scripts/ 경로 추가
sys.path.insert(0, str(project_root / "scripts"))
from importlib import import_module

from lib.policy import apply_policy_layer, load_policy_config
from lib.retrieval import (
    edition_sort_key,
    load_bm25_index,
    load_chroma_collection,
    retrieve_quotes,
)
from observability.tracing import load_observability_config, start_trace

# 04 모듈에서 도메인 함수 import
mod = import_module("04_retrieve_and_answer")
load_yaml = mod.load_yaml
detect_temporal_conflicts = mod.detect_temporal_conflicts
format_context = mod.format_context
extract_quote_ids = mod.extract_quote_ids


# ---------------------------------------------------------------------------
# 표준 필드 (PR-1 DoD)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Q1~Q6 테스트 케이스
# ---------------------------------------------------------------------------

TEST_CASES = [
    {
        "id": "Q1",
        "query": "1979년 초판에서 인사관리 정의만 보여줘.",
        "route": {
            "intent": "specific_time",
            "confidence": 0.95,
            "edition_hint": "초판",
            "output_type": None,
        },
        "verify": "edition_filter",
    },
    {
        "id": "Q2",
        "query": "인사관리 정의가 뭐야?",
        "route": {
            "intent": "general_definition",
            "confidence": 0.92,
            "edition_hint": None,
            "output_type": None,
        },
        "verify": "latest_first",
    },
    {
        "id": "Q3",
        "query": "패기 개념이 연도별로 어떻게 변해?",
        "route": {
            "intent": "evolution_comparison",
            "confidence": 0.95,
            "edition_hint": None,
            "output_type": None,
        },
        "verify": "chronological",
    },
    {
        "id": "Q4",
        "query": "SUPEX란 무엇인가?",
        "route": {
            "intent": "general_definition",
            "confidence": 0.93,
            "edition_hint": None,
            "output_type": None,
        },
        "verify": "latest_first",
    },
    {
        "id": "Q5",
        "query": "10차 개정판에서 SUPEX 추구의 구체적 프로세스는?",
        "route": {
            "intent": "specific_time",
            "confidence": 0.94,
            "edition_hint": "10차",
            "output_type": None,
        },
        "verify": "edition_filter",
    },
    {
        "id": "Q6",
        "query": "SKMS에서 가장 일관되게 강조하는 핵심 가치는 무엇인가?",
        "route": {
            "intent": "open_ended",
            "confidence": 0.88,
            "edition_hint": None,
            "output_type": None,
        },
        "verify": "open_ended",
    },
]


# ---------------------------------------------------------------------------
# 검증 함수들
# ---------------------------------------------------------------------------


def _check_common(results: list[dict], quote_ids: list[str]) -> dict[str, bool]:
    """공통 검증: 결과 존재, quote_id, 표준 필드."""
    checks: dict[str, bool] = {}
    checks["retrieval_ok"] = len(results) > 0
    checks["quote_ids_present"] = len(quote_ids) >= 1

    for hit in results:
        missing = REQUIRED_FIELDS - set(hit.keys())
        if missing:
            checks["standard_fields"] = False
            break
    else:
        checks["standard_fields"] = True

    return checks


def _check_edition_filter(
    results: list[dict],
    edition_hint: str,
) -> dict[str, bool]:
    """specific_time: edition_hint에 맞는 결과 존재 여부."""
    has_match = any(edition_hint in hit.get("edition", "") for hit in results)
    return {"edition_filter_ok": has_match}


def _check_latest_first(results: list[dict]) -> dict[str, bool]:
    """general_definition: 최신판 우선 정렬 + 첫 quote가 최신 가용 판."""
    edition_ids = [hit.get("edition", "") for hit in results]
    sort_keys = [edition_sort_key(eid) for eid in edition_ids]
    checks: dict[str, bool] = {
        "latest_first_order": sort_keys == sorted(sort_keys, reverse=True),
        "multi_edition": len(set(edition_ids)) >= 1,
    }
    # PR-4 DoD: 첫 quote가 결과 중 최신 판에서 나와야 함
    # (14차에 해당 콘텐츠가 없으면 폴백 → 가용 최신판이 기준)
    if results:
        first_key = sort_keys[0]
        max_key = max(sort_keys)
        checks["first_hit_is_latest"] = first_key == max_key
    return checks


def _check_chronological(results: list[dict]) -> dict[str, bool]:
    """evolution_comparison: 연대순 정렬 + 다중 개정판."""
    edition_ids = [hit.get("edition", "") for hit in results]
    sort_keys = [edition_sort_key(eid) for eid in edition_ids]
    return {
        "chronological_order": sort_keys == sorted(sort_keys),
        "multi_edition": len(set(edition_ids)) >= 2,
    }


def _check_open_ended(results: list[dict]) -> dict[str, bool]:
    """open_ended: latest_first 적용, 최신판 우선."""
    edition_ids = [hit.get("edition", "") for hit in results]
    sort_keys = [edition_sort_key(eid) for eid in edition_ids]
    return {
        "has_results": len(results) >= 1,
        "latest_first_order": sort_keys == sorted(sort_keys, reverse=True),
    }


VERIFY_FNS = {
    "edition_filter": lambda results, tc: _check_edition_filter(
        results,
        tc["route"]["edition_hint"],
    ),
    "latest_first": lambda results, _tc: _check_latest_first(results),
    "chronological": lambda results, _tc: _check_chronological(results),
    "open_ended": lambda results, _tc: _check_open_ended(results),
}


# ---------------------------------------------------------------------------
# 단일 테스트 실행
# ---------------------------------------------------------------------------


def run_single(
    tc: dict,
    *,
    collection,
    bm25_data: dict,
    openai_client,
    embedding_model: str,
    hybrid_cfg: dict,
    filters_cfg: dict,
    vector_cfg: dict,
    keyword_cfg: dict,
    output_specs: dict,
    obs_config: dict,
    policy_config: dict,
) -> dict:
    """하나의 테스트 케이스를 실행하고 결과를 반환한다."""
    qid = tc["id"]
    query = tc["query"]
    route = tc["route"]
    intent = route["intent"]
    edition_hint = route.get("edition_hint")
    output_type = route.get("output_type")

    start_ts = time.time()

    # --- Trace 시작 ---
    with start_trace(query, obs_config) as trace:
        # 1. 라우터 기록
        trace.log_router(
            intent=intent,
            confidence=route["confidence"],
            edition_hint=edition_hint,
            output_type=output_type,
        )

        # 2. 검색 정책 (PR-4: 정책 레이어 적용)
        base_policy = {
            "edition_hint": edition_hint,
            "edition_filter": filters_cfg.get("edition_filter"),
            "type_filter": None,
            "section_filter": None,
            "alpha": hybrid_cfg.get("alpha", 0.6),
            "rrf_k": hybrid_cfg.get("rrf_k", 60),
            "score_threshold": vector_cfg.get("score_threshold", 0.5),
            "vec_top_k": vector_cfg.get("top_k", 10),
            "bm25_top_k": keyword_cfg.get("top_k", 10),
            "latest_first": False,
        }
        policy = apply_policy_layer(intent, base_policy, policy_config)
        trace.log_policy(policy)

        # 3. 검색
        results = retrieve_quotes(
            query,
            intent,
            policy,
            top_k=hybrid_cfg.get("final_top_k", 5),
            collection=collection,
            bm25_data=bm25_data,
            openai_client=openai_client,
            embedding_model=embedding_model,
        )
        trace.log_retrieval(results)

        # 4. 컨텍스트 포맷팅 (프롬프트 길이 기록용)
        if results:
            conflict_info = detect_temporal_conflicts(results)
            context = format_context(
                results,
                intent=intent,
                conflict_info=conflict_info,
                output_type=output_type,
                output_specs=output_specs,
            )
            trace.log_prompt(context, "answer.md")
        else:
            conflict_info = {
                "has_conflict": False,
                "conflicting_editions": [],
                "definition_count": 0,
                "edition_definitions": {},
            }

        # (LLM 응답 생성은 스킵 — API 키 불필요)
        trace.log_response("")  # 빈 응답 기록

    elapsed = time.time() - start_ts

    # --- 검증 ---
    quote_ids = extract_quote_ids(results) if results else []
    checks = _check_common(results, quote_ids)

    verify_fn = VERIFY_FNS.get(tc["verify"])
    if verify_fn:
        checks.update(verify_fn(results, tc))

    verdict = "PASS" if all(checks.values()) else "FAIL"

    # --- 콘솔 출력 ---
    status_icon = "PASS" if verdict == "PASS" else "FAIL"
    print(
        f"  {status_icon}: {qid} [{intent}] "
        f"{len(results)}건 {elapsed:.2f}s "
        f"trace={trace.trace_id[:8]}..."
    )

    return {
        "id": qid,
        "query": query,
        "intent": intent,
        "edition_hint": edition_hint,
        "latest_first": policy.get("latest_first", False),
        "verdict": verdict,
        "checks": checks,
        "hit_count": len(results),
        "quote_id_count": len(quote_ids),
        "temporal_conflict": conflict_info["has_conflict"],
        "trace_id": trace.trace_id,
        "trace_steps": len(trace.steps),
        "elapsed_s": round(elapsed, 2),
        "editions": sorted(
            set(h.get("edition", "") for h in results),
            key=edition_sort_key,
        ),
    }


# ---------------------------------------------------------------------------
# Markdown 리포트 생성
# ---------------------------------------------------------------------------


def generate_report(
    results: list[dict],
    report_path: Path,
    run_timestamp: str,
) -> str:
    """Markdown 리포트를 생성하여 파일에 저장한다."""
    total = len(results)
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    failed = total - passed
    overall = "PASS" if failed == 0 else "FAIL"

    lines: list[str] = []
    lines.append(f"# SKMS RAG Smoke Test Report (with Traces)")
    lines.append("")
    lines.append(f"- **Timestamp**: {run_timestamp}")
    lines.append(f"- **Result**: {passed}/{total} PASS")
    lines.append(f"- **Overall**: {overall}")
    lines.append("")

    # 요약 테이블
    lines.append("## Summary")
    lines.append("")
    lines.append("| # | Query | Intent | Hits | Verdict | trace_id |")
    lines.append("|---|-------|--------|------|---------|----------|")
    for r in results:
        verdict_mark = "PASS" if r["verdict"] == "PASS" else "**FAIL**"
        query_short = r["query"][:40] + ("..." if len(r["query"]) > 40 else "")
        lines.append(
            f"| {r['id']} | {query_short} "
            f"| {r['intent']} | {r['hit_count']} "
            f"| {verdict_mark} | `{r['trace_id'][:12]}...` |"
        )
    lines.append("")

    # 상세 결과
    lines.append("## Detail")
    lines.append("")
    for r in results:
        verdict_mark = "PASS" if r["verdict"] == "PASS" else "FAIL"
        lines.append(f"### {r['id']}: {verdict_mark}")
        lines.append("")
        lines.append(f"- **Query**: {r['query']}")
        lines.append(f"- **Intent**: {r['intent']}")
        lines.append(f"- **Edition hint**: {r['edition_hint'] or 'None'}")
        lines.append(f"- **latest_first**: {r.get('latest_first', False)}")
        lines.append(f"- **trace_id**: `{r['trace_id']}`")
        lines.append(f"- **Trace steps**: {r['trace_steps']}")
        lines.append(f"- **Hits**: {r['hit_count']}")
        lines.append(f"- **Quote IDs**: {r['quote_id_count']}")
        lines.append(
            f"- **Editions**: {', '.join(r['editions']) if r['editions'] else 'None'}"
        )
        lines.append(f"- **Temporal conflict**: {r['temporal_conflict']}")
        lines.append(f"- **Elapsed**: {r['elapsed_s']}s")
        lines.append("")

        # 검증 항목
        lines.append("| Check | Result |")
        lines.append("|-------|--------|")
        for check_name, check_val in r["checks"].items():
            status = "PASS" if check_val else "FAIL"
            lines.append(f"| {check_name} | {status} |")
        lines.append("")

    content = "\n".join(lines)

    # 파일 저장
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(content, encoding="utf-8")

    return content


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    print(f"[PR-3] SKMS Smoke Test with Traces")
    print(f"Timestamp: {run_timestamp}")
    print("=" * 60)

    # --- 설정 로드 ---
    retrieval_cfg = load_yaml(Path("config/retrieval.yaml"))
    pipeline_cfg = load_yaml(Path("config/pipeline.yaml"))
    output_specs = load_yaml(Path("config/output_specs.yaml"))
    obs_config = load_observability_config()
    policy_config = load_policy_config()

    retrieval = retrieval_cfg.get("retrieval", {})
    vector_cfg = retrieval.get("vector", {})
    keyword_cfg = retrieval.get("keyword", {})
    hybrid_cfg = retrieval.get("hybrid", {})
    filters_cfg = retrieval.get("filters", {})

    embedding_model = (
        pipeline_cfg.get("pipeline", {})
        .get("embedding", {})
        .get("model", "text-embedding-3-large")
    )

    # --- 인덱스 로드 ---
    collection = load_chroma_collection(
        Path("indexes/"), vector_cfg.get("collection_name", "skms_quotes")
    )
    bm25_data = load_bm25_index(
        Path(keyword_cfg.get("index_path", "indexes/bm25_index.pkl"))
    )

    # --- OpenAI 클라이언트 ---
    openai_key = os.environ.get("OPENAI_API_KEY")
    openai_client = None
    if openai_key:
        try:
            from openai import OpenAI

            openai_client = OpenAI(api_key=openai_key)
        except ImportError:
            print("[경고] openai 패키지 없음 — 벡터 검색 비활성화", file=sys.stderr)

    # --- Q1~Q6 실행 ---
    all_results: list[dict] = []
    for tc in TEST_CASES:
        result = run_single(
            tc,
            collection=collection,
            bm25_data=bm25_data,
            openai_client=openai_client,
            embedding_model=embedding_model,
            hybrid_cfg=hybrid_cfg,
            filters_cfg=filters_cfg,
            vector_cfg=vector_cfg,
            keyword_cfg=keyword_cfg,
            output_specs=output_specs,
            obs_config=obs_config,
            policy_config=policy_config,
        )
        all_results.append(result)

    # --- 리포트 생성 ---
    report_path = Path(f"eval/reports/smoke_with_traces_{file_timestamp}.md")
    generate_report(all_results, report_path, run_timestamp)

    # --- 전체 요약 ---
    total = len(all_results)
    passed = sum(1 for r in all_results if r["verdict"] == "PASS")
    print(f"\n{'=' * 60}")
    print(f"Result: {passed}/{total} PASS")
    print(f"Report: {report_path}")

    # trace_id 목록
    print(f"\nTrace IDs:")
    for r in all_results:
        print(f"  {r['id']}: {r['trace_id']}")

    if passed < total:
        sys.exit(1)
    print(f"\nALL PASS")


if __name__ == "__main__":
    main()
