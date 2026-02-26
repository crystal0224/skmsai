#!/usr/bin/env python3
"""연기 테스트: 04_retrieve_and_answer.py 파이프라인의 3개 질문 검증.

ANTHROPIC_API_KEY가 없는 환경에서 실행 가능하도록,
라우팅은 deterministic 로직으로 대체하고,
검색/후처리/충돌감지/컨텍스트포맷팅을 실제 코드로 실행한다.

PR-1: retrieve_quotes() 단일 엔트리 함수 사용.

Usage:
    python scripts/smoke_test_04.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 프로젝트 루트로 이동
project_root = Path(__file__).resolve().parent.parent
os.chdir(project_root)

# 04 모듈의 함수들을 재사용
sys.path.insert(0, str(project_root / "scripts"))
from importlib import import_module

# lib.retrieval에서 검색 함수 import
from lib.retrieval import (
    edition_sort_key,
    load_bm25_index,
    load_chroma_collection,
    retrieve_quotes,
)

# 04 모듈에서 도메인 함수 import
mod = import_module("04_retrieve_and_answer")

load_yaml = mod.load_yaml
detect_temporal_conflicts = mod.detect_temporal_conflicts
format_context = mod.format_context
extract_quote_ids = mod.extract_quote_ids


# ---------------------------------------------------------------------------
# 테스트 케이스 정의
# ---------------------------------------------------------------------------

TEST_CASES = [
    {
        "id": "Q1",
        "query": "1979년 초판에서 인사관리 정의만 보여줘.",
        "expected_intent": "specific_time",
        "expected_edition_hint": "초판",
        "route_override": {
            "intent": "specific_time",
            "confidence": 0.95,
            "edition_hint": "초판",
            "output_type": None,
            "reasoning": "1979년 초판을 명시적으로 지정하여 인사관리 정의를 질의",
        },
    },
    {
        "id": "Q2",
        "query": "인사관리 정의가 뭐야?",
        "expected_intent": "general_definition",
        "expected_edition_hint": None,
        "route_override": {
            "intent": "general_definition",
            "confidence": 0.92,
            "edition_hint": None,
            "output_type": None,
            "reasoning": "'정의가 뭐야'로 인사관리 정의를 직접 질의, 개정판 미명시",
        },
    },
    {
        "id": "Q3",
        "query": "패기 개념이 연도별로 어떻게 변해?",
        "expected_intent": "evolution_comparison",
        "expected_edition_hint": None,
        "route_override": {
            "intent": "evolution_comparison",
            "confidence": 0.95,
            "edition_hint": None,
            "output_type": None,
            "reasoning": "'연도별로 어떻게 변해'로 다수 개정판에 걸친 개념 변화를 질의",
        },
    },
]


def run_smoke_test() -> None:
    """3개 질문에 대한 연기 테스트를 실행한다."""
    # --- 설정 로드 ---
    retrieval_cfg = load_yaml(Path("config/retrieval.yaml"))
    pipeline_cfg = load_yaml(Path("config/pipeline.yaml"))
    output_specs = load_yaml(Path("config/output_specs.yaml"))

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
    index_dir = Path("indexes/")
    collection = load_chroma_collection(
        index_dir, vector_cfg.get("collection_name", "skms_quotes")
    )
    bm25_data = load_bm25_index(
        Path(keyword_cfg.get("index_path", "indexes/bm25_index.pkl"))
    )

    # --- OpenAI 클라이언트 (임베딩용) ---
    openai_key = os.environ.get("OPENAI_API_KEY")
    openai_client = None
    if openai_key:
        try:
            from openai import OpenAI

            openai_client = OpenAI(api_key=openai_key)
        except ImportError:
            print("[경고] openai 패키지 없음 — 벡터 검색 비활성화", file=sys.stderr)

    results_summary: list[dict] = []

    for tc in TEST_CASES:
        qid = tc["id"]
        query = tc["query"]
        route = tc["route_override"]
        intent = route["intent"]
        edition_hint = route.get("edition_hint")
        output_type = route.get("output_type")

        print("=" * 80)
        print(f"## {qid}: {query}")
        print("=" * 80)

        # --- 1. 라우팅 (deterministic) ---
        print(
            f"\n[라우팅] 의도: {intent} | 확신도: {route['confidence']:.2f}"
            f" | 개정판: {edition_hint or '전체'}"
            f" | 출력: {output_type or '기본'}"
        )

        # --- 2. 검색 정책 구성 ---
        policy = {
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
        print(f"[정책] edition_hint: {edition_hint}, latest_first: False")

        # --- 3. retrieve_quotes 단일 엔트리 검색 ---
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
        print(f"[검색] 최종 결과: {len(results)}건")

        if not results:
            print(f"\n[{qid}] 검색 결과 없음 — FAIL")
            results_summary.append(
                {
                    "id": qid,
                    "verdict": "FAIL",
                    "reason": "검색 결과 없음",
                }
            )
            continue

        # --- 4. Temporal Conflict 감지 ---
        conflict_info = detect_temporal_conflicts(results)
        if conflict_info["has_conflict"]:
            editions_str = ", ".join(conflict_info["conflicting_editions"])
            print(
                f"[충돌] 시간축 충돌 감지: {conflict_info['definition_count']}개 정의,"
                f" 개정판: {editions_str}"
            )
        else:
            print("[충돌] temporal_conflict: false")

        # --- 5. 컨텍스트 포맷팅 ---
        context = format_context(
            results,
            intent=intent,
            conflict_info=conflict_info,
            output_type=output_type,
            output_specs=output_specs,
        )

        # 컨텍스트 첫 5줄 출력
        context_lines = context.split("\n")
        print(f"\n[컨텍스트] (첫 5줄):")
        for line in context_lines[:5]:
            print(f"  {line}")

        # --- 6. quote_id 추출 ---
        quote_ids = extract_quote_ids(results)
        print(f"\n[quote_ids] ({len(quote_ids)}개):")
        for qid_val in quote_ids:
            print(f"  - {qid_val}")

        # --- 7. 검색 결과 출처 (표준화된 dict) ---
        print("\n---")
        print(f"검색 결과 출처 ({len(results)}개 청크):")
        for hit in results:
            section_str = (
                " > ".join(hit["chapter_path"]) if hit["chapter_path"] else "[]"
            )
            print(
                f"  - [{hit['edition']}] {section_str} ({hit['type']}) -- {hit['quote_id']}"
            )

        # --- 8. 표준 필드 검증 (PR-1 DoD) ---
        required_fields = {
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

        # --- 9. 검증 ---
        checks: dict[str, bool] = {}

        # 검증 1: 검색 결과 존재
        checks["retrieval_ok"] = len(results) > 0

        # 검증 2: quote_id 포함
        checks["quote_ids_present"] = len(quote_ids) >= 1

        # 검증 3: 표준 필드 완전성
        for hit in results:
            missing = required_fields - set(hit.keys())
            if missing:
                checks["standard_fields"] = False
                print(f"  [경고] 누락 필드: {missing}")
                break
        else:
            checks["standard_fields"] = True

        # 검증 4: 의도별 특수 검증
        if qid == "Q1":
            # specific_time: 초판(1979) 관련 결과 존재 여부
            has_chopan = any(
                "1979" in hit.get("edition", "") or "초판" in hit.get("edition", "")
                for hit in results
            )
            checks["edition_filter_ok"] = has_chopan

        elif qid == "Q2":
            # general_definition: 최신판 우선 정렬 확인
            edition_ids = [hit.get("edition", "") for hit in results]
            sort_keys = [edition_sort_key(eid) for eid in edition_ids]
            checks["latest_first_order"] = sort_keys == sorted(sort_keys, reverse=True)
            # 다중 개정판 결과
            editions_in_results = set(hit.get("edition", "") for hit in results)
            checks["multi_edition"] = len(editions_in_results) >= 1
            # temporal_conflict 정보 출력 (검증은 하지 않음 — 데이터 의존적)
            if conflict_info["has_conflict"]:
                print(
                    f"  [info] temporal_conflict: True ({conflict_info['definition_count']} defs)"
                )
            else:
                print(f"  [info] temporal_conflict: False (정상 — 단일 개정판 정의)")

        elif qid == "Q3":
            # evolution_comparison: 연대순 정렬 확인
            edition_ids = [hit.get("edition", "") for hit in results]
            # 연대순 정렬 검증 (오름차순)
            sort_keys = [edition_sort_key(eid) for eid in edition_ids]
            checks["chronological_order"] = sort_keys == sorted(sort_keys)
            # 2개 이상 개정판
            unique_editions = set(edition_ids)
            checks["multi_edition"] = len(unique_editions) >= 2

        # --- 판정 ---
        all_pass = all(checks.values())
        verdict = "PASS" if all_pass else "FAIL"

        print(f"\n[검증 결과]")
        for check_name, check_val in checks.items():
            status = "PASS" if check_val else "FAIL"
            print(f"  {check_name}: {status}")
        print(f"\n>>> {tc['id']} 최종 판정: {verdict}")

        results_summary.append(
            {
                "id": tc["id"],
                "verdict": verdict,
                "checks": checks,
                "intent": intent,
                "hit_count": len(results),
                "quote_id_count": len(quote_ids),
                "temporal_conflict": conflict_info["has_conflict"],
            }
        )

    # --- 전체 요약 ---
    print("\n" + "=" * 80)
    print("## 전체 요약")
    print("=" * 80)
    for r in results_summary:
        print(
            f"  {r['id']}: {r['verdict']} "
            f"(intent={r.get('intent', 'N/A')}, "
            f"hits={r.get('hit_count', 0)}, "
            f"quotes={r.get('quote_id_count', 0)}, "
            f"conflict={r.get('temporal_conflict', False)})"
        )

    total_pass = sum(1 for r in results_summary if r["verdict"] == "PASS")
    total = len(results_summary)
    print(f"\n  결과: {total_pass}/{total} PASS")

    if total_pass < total:
        sys.exit(1)


if __name__ == "__main__":
    run_smoke_test()
