#!/usr/bin/env python3
"""PR-8: 회귀 테스트 — 최신판 우선 + 혼합 인용 금지 검증.

API KEY 없이 실행 가능 (deterministic 라우팅).
retrieve_quotes의 결과에서 quote_id의 year 집합을 검사한다.

Test A: 최신판 우선 준수
  - 질문: "SKMS에서 경영의 궁극적 목적은?"
  - general_definition 라우팅 → 첫 quote가 2020년 14차

Test B: 혼합 인용 금지
  - 질문: "패기 정의는?"
  - general_definition 라우팅 → definition 타입 quote가 단일 연도

Usage:
    python tests/test_regression.py
"""
from __future__ import annotations

import functools
import json
import os
import sys
from pathlib import Path

# 프로젝트 루트 (절대 경로)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# scripts/ 경로 추가
_SCRIPT_DIR = _PROJECT_ROOT / "scripts"
sys.path.insert(0, str(_SCRIPT_DIR))

from lib.policy import apply_policy_layer, load_policy_config  # noqa: E402
from lib.retrieval import (  # noqa: E402
    edition_sort_key,
    load_bm25_index,
    load_chroma_collection,
    retrieve_quotes,
)
from observability.tracing import load_observability_config, start_trace  # noqa: E402


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _load_infra():
    """인덱스, 설정, 클라이언트를 로드한다 (절대 경로 사용)."""
    import yaml

    def _load_yaml(path: Path) -> dict:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    retrieval_cfg = _load_yaml(_PROJECT_ROOT / "config/retrieval.yaml")
    pipeline_cfg = _load_yaml(_PROJECT_ROOT / "config/pipeline.yaml")
    output_specs = _load_yaml(_PROJECT_ROOT / "config/output_specs.yaml")
    policy_config = load_policy_config(str(_PROJECT_ROOT / "config/policy.yaml"))
    obs_config = load_observability_config(
        str(_PROJECT_ROOT / "config/observability.yaml")
    )

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

    collection = load_chroma_collection(
        _PROJECT_ROOT / "indexes/",
        vector_cfg.get("collection_name", "skms_quotes"),
    )
    bm25_data = load_bm25_index(
        _PROJECT_ROOT / Path(keyword_cfg.get("index_path", "indexes/bm25_index.pkl"))
    )

    openai_key = os.environ.get("OPENAI_API_KEY")
    openai_client = None
    if openai_key:
        try:
            from openai import OpenAI

            openai_client = OpenAI(api_key=openai_key)
        except ImportError:
            pass

    return {
        "collection": collection,
        "bm25_data": bm25_data,
        "openai_client": openai_client,
        "embedding_model": embedding_model,
        "hybrid_cfg": hybrid_cfg,
        "filters_cfg": filters_cfg,
        "vector_cfg": vector_cfg,
        "keyword_cfg": keyword_cfg,
        "output_specs": output_specs,
        "obs_config": obs_config,
        "policy_config": policy_config,
    }


def _run_retrieval(
    query: str,
    intent: str,
    edition_hint: str | None,
    infra: dict,
) -> list[dict]:
    """deterministic 라우팅으로 retrieve_quotes를 실행한다."""
    hybrid_cfg = infra["hybrid_cfg"]
    filters_cfg = infra["filters_cfg"]
    vector_cfg = infra["vector_cfg"]
    keyword_cfg = infra["keyword_cfg"]

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

    policy = apply_policy_layer(intent, base_policy, infra["policy_config"])

    return retrieve_quotes(
        query,
        intent,
        policy,
        top_k=hybrid_cfg.get("final_top_k", 5),
        collection=infra["collection"],
        bm25_data=infra["bm25_data"],
        openai_client=infra["openai_client"],
        embedding_model=infra["embedding_model"],
    )


# ---------------------------------------------------------------------------
# Regression check functions
# ---------------------------------------------------------------------------

# 혼합 인용이 허용되는 intent (변천/비교)
_MIXED_YEAR_ALLOWED_INTENTS = frozenset({"evolution_comparison", "cross_version"})


def check_latest_edition_first(
    results: list[dict],
    expected_first_year: int,
) -> tuple[bool, str]:
    """Test A: 첫 근거 quote가 expected_first_year인지 검사한다.

    Returns:
        (passed, failure_detail)
    """
    if not results:
        return False, "검색 결과 없음"

    first_hit = results[0]
    first_year = first_hit.get("year", 0)
    first_qid = first_hit.get("quote_id", "?")

    if first_year == expected_first_year:
        return True, ""

    return (
        False,
        f"첫 quote {first_qid} (year={first_year}) ≠ " f"expected {expected_first_year}",
    )


def check_no_mixed_definitions(
    results: list[dict],
    intent: str,
) -> tuple[bool, str]:
    """Test B: definition 타입 quote가 단일 연도에서만 인용되는지 검사한다.

    evolution_comparison intent는 혼합 허용.

    Returns:
        (passed, failure_detail)
    """
    if intent in _MIXED_YEAR_ALLOWED_INTENTS:
        return True, "evolution intent — 혼합 허용"

    # definition 타입 quote만 추출
    def_hits = [h for h in results if h.get("type") == "definition"]

    if len(def_hits) == 0:
        # definition 타입이 없으면 principle 등으로 답 — 혼합 검사 대상 아님
        return True, "definition 타입 quote 없음 (검사 skip)"

    def_years = {h.get("year", 0) for h in def_hits}
    def_qids = [h.get("quote_id", "?") for h in def_hits]

    if len(def_years) <= 1:
        return True, ""

    # 어떤 quote_id들이 혼합을 일으키는지 명시
    year_to_qids: dict[int, list[str]] = {}
    for h in def_hits:
        y = h.get("year", 0)
        year_to_qids.setdefault(y, []).append(h.get("quote_id", "?"))

    detail_parts = []
    for y, qids in sorted(year_to_qids.items()):
        detail_parts.append(f"{y}년: [{', '.join(qids)}]")

    return (
        False,
        f"definition 타입이 {len(def_years)}개 연도에서 혼합됨 — " + "; ".join(detail_parts),
    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


_REGRESSION_CASES = [
    {
        "id": "q-r01",
        "name": "Test A: 최신판 우선 준수",
        "query": "SKMS에서 경영의 궁극적 목적은?",
        "intent": "general_definition",
        "edition_hint": None,
        "checks": [
            {
                "type": "latest_edition_first",
                "expected_first_year": 2020,
            },
        ],
    },
    {
        "id": "q-r02",
        "name": "Test B: 혼합 인용 금지",
        "query": "패기 정의는?",
        "intent": "general_definition",
        "edition_hint": None,
        "checks": [
            {
                "type": "no_mixed_definitions",
            },
        ],
    },
]


def _run_check(
    check: dict,
    results: list[dict],
    intent: str,
) -> tuple[bool, str]:
    """단일 regression check를 실행한다."""
    ctype = check["type"]

    if ctype == "latest_edition_first":
        return check_latest_edition_first(
            results,
            check["expected_first_year"],
        )
    elif ctype == "no_mixed_definitions":
        return check_no_mixed_definitions(results, intent)
    else:
        return False, f"알 수 없는 check type: {ctype}"


# ---------------------------------------------------------------------------
# Test functions (pytest/직접 실행 호환)
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _get_infra() -> dict:
    """인프라를 한 번만 로드한다 (테스트 간 공유)."""
    return _load_infra()


def test_latest_edition_first():
    """Test A: 최신판 우선 — 첫 근거 quote가 2020년 14차."""
    infra = _get_infra()
    tc = _REGRESSION_CASES[0]

    results = _run_retrieval(tc["query"], tc["intent"], tc["edition_hint"], infra)
    assert len(results) > 0, "검색 결과 없음"

    for check in tc["checks"]:
        passed, detail = _run_check(check, results, tc["intent"])
        if not passed:
            quote_summary = ", ".join(
                f"{h['quote_id']}(year={h.get('year')})" for h in results[:3]
            )
            raise AssertionError(
                f"[{tc['id']}] {tc['name']}: {detail}\n"
                f"  첫 3개 quote: {quote_summary}"
            )

    print(
        f"  PASS: {tc['name']} — "
        f"첫 quote: {results[0]['quote_id']} (year={results[0].get('year')})"
    )


def test_no_mixed_definitions():
    """Test B: 혼합 인용 금지 — definition 타입 quote가 단일 연도."""
    infra = _get_infra()
    tc = _REGRESSION_CASES[1]

    results = _run_retrieval(tc["query"], tc["intent"], tc["edition_hint"], infra)
    assert len(results) > 0, "검색 결과 없음"

    for check in tc["checks"]:
        passed, detail = _run_check(check, results, tc["intent"])
        if not passed:
            quote_summary = ", ".join(
                f"{h['quote_id']}(type={h.get('type')}, year={h.get('year')})"
                for h in results
            )
            raise AssertionError(
                f"[{tc['id']}] {tc['name']}: {detail}\n" f"  전체 quote: {quote_summary}"
            )

    # 결과 요약 출력
    def_hits = [h for h in results if h.get("type") == "definition"]
    if def_hits:
        years = sorted({h.get("year", 0) for h in def_hits})
        print(f"  PASS: {tc['name']} — " f"definition {len(def_hits)}개, year={years}")
    else:
        all_years = sorted({h.get("year", 0) for h in results})
        print(
            f"  PASS: {tc['name']} — "
            f"definition 타입 없음, 전체 {len(results)}건 year={all_years}"
        )


def test_mixed_years_allowed_for_evolution():
    """변천 비교 intent에서는 혼합 연도가 허용되는지 검증."""
    infra = _get_infra()

    results = _run_retrieval(
        "패기 개념이 연도별로 어떻게 변해?",
        "evolution_comparison",
        None,
        infra,
    )
    assert len(results) > 0, "검색 결과 없음"

    passed, detail = check_no_mixed_definitions(results, "evolution_comparison")
    assert passed, f"evolution_comparison에서 혼합 허용이 동작하지 않음: {detail}"

    years = sorted({h.get("year", 0) for h in results})
    print(f"  PASS: evolution 혼합 허용 — {len(results)}건 year={years}")


def test_seed_file_regression_entries():
    """eval/questions.seed.jsonl에 회귀 테스트 항목이 존재하는지 검증."""
    seed_path = _PROJECT_ROOT / "eval/questions.seed.jsonl"
    assert seed_path.exists(), "eval/questions.seed.jsonl 없음"

    questions: list[dict] = []
    with open(seed_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                questions.append(json.loads(line))

    regression_ids = {q["id"] for q in questions if q["id"].startswith("q-r")}
    assert "q-r01" in regression_ids, "q-r01 (최신판 우선) 누락"
    assert "q-r02" in regression_ids, "q-r02 (혼합 인용 금지) 누락"

    # regression_checks 필드 존재 검증
    for q in questions:
        if q["id"].startswith("q-r"):
            assert "regression_checks" in q, f"{q['id']}: regression_checks 필드 누락"
            for rc in q["regression_checks"]:
                assert "type" in rc, f"{q['id']}: check type 누락"

    print(f"  PASS: seed file 회귀 항목 {len(regression_ids)}개 검증")


def test_check_functions_with_synthetic_data():
    """회귀 검사 함수들을 합성 데이터로 검증."""
    # latest_edition_first — 통과
    hits_ok = [
        {"quote_id": "2020-14차|_root|principle|001", "year": 2020, "type": "principle"},
        {"quote_id": "2016-13차|_root|principle|001", "year": 2016, "type": "principle"},
    ]
    passed, _ = check_latest_edition_first(hits_ok, 2020)
    assert passed, "2020 첫 hit이면 통과해야 함"

    # latest_edition_first — 실패
    hits_old = [
        {"quote_id": "2016-13차|_root|principle|001", "year": 2016, "type": "principle"},
        {"quote_id": "2020-14차|_root|principle|001", "year": 2020, "type": "principle"},
    ]
    passed, detail = check_latest_edition_first(hits_old, 2020)
    assert not passed, "2016 첫 hit이면 실패해야 함"
    assert "2016-13차|_root|principle|001" in detail

    # no_mixed_definitions — 통과 (단일 연도)
    hits_single = [
        {"quote_id": "q1", "year": 2020, "type": "definition"},
        {"quote_id": "q2", "year": 2020, "type": "definition"},
    ]
    passed, _ = check_no_mixed_definitions(hits_single, "general_definition")
    assert passed, "단일 연도 definition은 통과해야 함"

    # no_mixed_definitions — 실패 (혼합)
    hits_mixed = [
        {"quote_id": "q-old", "year": 1998, "type": "definition"},
        {"quote_id": "q-new", "year": 2020, "type": "definition"},
    ]
    passed, detail = check_no_mixed_definitions(hits_mixed, "general_definition")
    assert not passed, "혼합 연도 definition은 실패해야 함"
    assert "q-old" in detail
    assert "q-new" in detail

    # no_mixed_definitions — evolution은 혼합 허용
    passed, _ = check_no_mixed_definitions(hits_mixed, "evolution_comparison")
    assert passed, "evolution_comparison은 혼합 허용해야 함"

    # no_mixed_definitions — definition 없으면 skip
    hits_no_def = [
        {"quote_id": "q1", "year": 1998, "type": "principle"},
        {"quote_id": "q2", "year": 2020, "type": "narrative"},
    ]
    passed, _ = check_no_mixed_definitions(hits_no_def, "general_definition")
    assert passed, "definition 타입 없으면 통과해야 함"

    # 빈 결과
    passed, detail = check_latest_edition_first([], 2020)
    assert not passed
    assert "검색 결과 없음" in detail

    # no_mixed_definitions — cross_version도 혼합 허용
    passed, _ = check_no_mixed_definitions(hits_mixed, "cross_version")
    assert passed, "cross_version도 혼합 허용해야 함"

    # 알 수 없는 check type
    passed, detail = _run_check({"type": "nonexistent"}, [], "general_definition")
    assert not passed
    assert "알 수 없는 check type" in detail

    print("  PASS: 합성 데이터 검증 (9 케이스)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("[PR-8] 회귀 테스트 — 최신판 우선 + 혼합 인용 금지")
    print("=" * 60)

    tests = [
        test_seed_file_regression_entries,
        test_check_functions_with_synthetic_data,
        test_latest_edition_first,
        test_no_mixed_definitions,
        test_mixed_years_allowed_for_evolution,
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

    print(f"\n{'=' * 60}")
    print(f"결과: {passed} PASS, {failed} FAIL / {len(tests)} total")

    if failed > 0:
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
