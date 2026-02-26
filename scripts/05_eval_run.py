#!/usr/bin/env python3
"""자동 품질 평가: eval/questions.seed.jsonl → eval/results.jsonl

LLM-as-Judge로 4축 평가: relevance, faithfulness, quote_accuracy, temporal_correctness
PR-8: 회귀 테스트 — quote_id year 집합 기반 regression_checks 검증

Usage:
    python scripts/05_eval_run.py
    python scripts/05_eval_run.py --limit 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

# Ensure scripts/ is on sys.path for lib/observability imports
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.retrieval import (  # noqa: E402
    bm25_search,
    hybrid_fusion,
    load_bm25_index,
    load_chroma_collection,
    vector_search,
)
from observability.tracing import flush, traceable  # noqa: E402


JUDGE_SYSTEM_PROMPT = """\
당신은 SKMS(SK경영관리체계) RAG 시스템의 품질 평가자입니다.
사용자의 질의, 시스템 답변, 검색된 컨텍스트를 분석하여 4가지 축으로 평가하세요.

## 평가 축

1. **relevance** (1-5): 답변이 질의에 얼마나 관련 있는가?
   - 5: 질의의 모든 측면에 완벽하게 답변
   - 3: 부분적으로 관련 있으나 핵심 누락
   - 1: 완전히 무관한 답변

2. **faithfulness** (1-5): 답변이 제공된 컨텍스트에 얼마나 충실한가?
   - 5: 모든 내용이 컨텍스트에 근거
   - 3: 일부 내용이 컨텍스트에 없는 추측
   - 1: 대부분 환각(hallucination)

3. **quote_accuracy** (1-5): 인용이 정확하고 형식을 갖추었는가?
   - 5: 모든 인용이 정확하고 [출처: N차 개정판, 섹션] 형식 준수
   - 3: 인용이 있으나 형식 불완전
   - 1: 인용 없음 또는 부정확

4. **temporal_correctness** (1-5): 개정판 맥락이 올바르게 처리되었는가?
   - 5: 개정판 간 구분이 명확하고 시간축 충돌 적절히 안내
   - 3: 개정판 정보 있으나 일부 혼동
   - 1: 개정판 구분 없이 혼합

## 출력 형식

반드시 아래 JSON으로만 응답하세요:

```json
{
  "relevance": <1-5>,
  "faithfulness": <1-5>,
  "quote_accuracy": <1-5>,
  "temporal_correctness": <1-5>,
  "reasoning": "평가 근거를 2-3문장으로"
}
```
"""


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_questions(path: Path) -> list[dict]:
    questions: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                questions.append(json.loads(line))
    return questions


def run_rag_pipeline(
    query: str,
    collection,
    bm25_data: dict | None,
    openai_client,
    anthropic_client,
    retrieval_cfg: dict,
    pipeline_cfg: dict,
    router_prompt: str,
    answer_prompt: str,
) -> tuple[str, list[dict]]:
    """단일 질의에 대해 RAG 파이프라인을 실행하고 (answer, hits)를 반환한다."""
    ret = retrieval_cfg.get("retrieval", {})
    vector_cfg = ret.get("vector", {})
    keyword_cfg = ret.get("keyword", {})
    hybrid_cfg = ret.get("hybrid", {})

    embedding_model = (
        pipeline_cfg.get("pipeline", {})
        .get("embedding", {})
        .get("model", "text-embedding-3-large")
    )

    # 검색 (lib.retrieval 공유 모듈 사용)
    vec_hits = vector_search(
        collection,
        query,
        openai_client,
        embedding_model=embedding_model,
        top_k=vector_cfg.get("top_k", 10),
        score_threshold=vector_cfg.get("score_threshold", 0.5),
        edition_filter=None,
    )
    bm25_hits = bm25_search(
        bm25_data,
        query,
        top_k=keyword_cfg.get("top_k", 10),
        edition_filter=None,
    )

    final_hits = hybrid_fusion(
        vec_hits,
        bm25_hits,
        alpha=hybrid_cfg.get("alpha", 0.6),
        rrf_k=hybrid_cfg.get("rrf_k", 60),
        final_top_k=hybrid_cfg.get("final_top_k", 5),
    )

    if not final_hits:
        return "검색 결과가 없습니다.", []

    context = _format_context(final_hits)
    user_message = f"## 질의\n\n{query}\n\n## 컨텍스트\n\n{context}"

    message = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=answer_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    answer = message.content[0].text
    return answer, final_hits


@traceable("skms_judge")
def judge_answer(
    query: str,
    answer: str,
    context_hits: list[dict],
    anthropic_client,
) -> dict:
    """LLM-as-Judge로 답변을 4축 평가한다."""
    context_summary = "\n".join(
        f"- [{h.get('metadata', {}).get('edition_id', '?')}] {h['text'][:200]}..."
        for h in context_hits
    )

    user_message = (
        f"## 질의\n{query}\n\n"
        f"## 시스템 답변\n{answer}\n\n"
        f"## 검색된 컨텍스트 (요약)\n{context_summary}"
    )

    message = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=JUDGE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    text = message.content[0].text.strip()

    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return json.loads(text)
    except (json.JSONDecodeError, IndexError):
        return {
            "relevance": 0,
            "faithfulness": 0,
            "quote_accuracy": 0,
            "temporal_correctness": 0,
            "reasoning": f"JSON 파싱 실패: {text[:200]}",
        }


# ---------------------------------------------------------------------------
# Eval-specific context formatting (검색 함수는 lib.retrieval에서 import)
# ---------------------------------------------------------------------------


def _format_context(hits):
    parts = []
    for i, hit in enumerate(hits, start=1):
        meta = hit.get("metadata", {})
        edition = meta.get("edition_id", "unknown")
        section = meta.get("section_path", "[]")
        flags = meta.get("quality_flags", "[]")
        if isinstance(section, str):
            try:
                sl = json.loads(section)
                section = " > ".join(sl) if sl else "unknown"
            except json.JSONDecodeError:
                pass
        if isinstance(flags, str):
            try:
                flags = json.loads(flags)
            except json.JSONDecodeError:
                flags = []
        parts.append(
            f"[CHUNK {i}]\nedition: {edition}\nsection: {section}\n"
            f"quality_flags: {flags}\n---\n{hit['text']}\n"
        )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# PR-8: Regression checks — quote_id year 집합 검사
# ---------------------------------------------------------------------------

# 혼합 인용이 허용되는 intent (변천/비교)
_MIXED_YEAR_ALLOWED_INTENTS = frozenset({"evolution_comparison", "cross_version"})


def _check_latest_edition_first(
    hits: list[dict],
    expected_first_year: int,
) -> tuple[bool, list[str]]:
    """첫 근거 quote가 expected_first_year인지 검사한다.

    Returns:
        (passed, offending_quote_ids)
    """
    if not hits:
        return False, ["(검색 결과 없음)"]

    first_hit = hits[0]
    first_year = _extract_year(first_hit)
    first_qid = _extract_quote_id(first_hit)

    if first_year == expected_first_year:
        return True, []

    return False, [first_qid]


def _check_no_mixed_definitions(
    hits: list[dict],
    query_type: str,
) -> tuple[bool, list[str]]:
    """definition 타입 quote가 단일 연도에서만 인용되는지 검사한다.

    evolution_comparison/cross_version은 혼합 허용.

    Returns:
        (passed, offending_quote_ids)
    """
    if query_type in _MIXED_YEAR_ALLOWED_INTENTS:
        return True, []

    # definition 타입 quote만 추출
    def_hits = [h for h in hits if _extract_type(h) == "definition"]

    if len(def_hits) == 0:
        return True, []

    def_years = {_extract_year(h) for h in def_hits}

    if len(def_years) <= 1:
        return True, []

    # 혼합을 일으킨 quote_id 목록
    return False, [_extract_quote_id(h) for h in def_hits]


def _extract_year(hit: dict) -> int:
    """hit에서 year를 추출한다 (표준 dict 또는 metadata dict 호환)."""
    if "year" in hit:
        return hit["year"]
    meta = hit.get("metadata", {})
    edition_id = meta.get("edition_id", "")
    # "2020-14차" → 2020
    parts = edition_id.split("-", 1)
    try:
        return int(parts[0])
    except (ValueError, IndexError):
        return 0


def _extract_type(hit: dict) -> str:
    """hit에서 quote type을 추출한다."""
    if "type" in hit:
        return hit["type"]
    return hit.get("metadata", {}).get("type", "narrative")


def _extract_quote_id(hit: dict) -> str:
    """hit에서 quote_id를 추출한다."""
    return hit.get("quote_id", hit.get("id", "?"))


def run_regression_checks(
    question: dict,
    hits: list[dict],
) -> dict:
    """질문의 regression_checks를 실행하고 결과를 반환한다.

    Returns:
        {
            "regression_passed": bool,
            "regression_failures": [
                {"type": str, "offending_quote_ids": [str], "description": str},
                ...
            ]
        }
    """
    checks = question.get("regression_checks", [])
    if not checks:
        return {"regression_passed": True, "regression_failures": []}

    query_type = question.get("query_type", "open_ended")
    failures: list[dict] = []

    for check in checks:
        ctype = check["type"]
        description = check.get("description", ctype)

        if ctype == "latest_edition_first":
            if "expected_first_year" not in check:
                failures.append(
                    {
                        "type": ctype,
                        "description": "seed data 오류: expected_first_year 필드 누락",
                        "offending_quote_ids": [],
                    }
                )
                continue
            expected_year = check["expected_first_year"]
            passed, offenders = _check_latest_edition_first(hits, expected_year)
        elif ctype == "no_mixed_definitions":
            passed, offenders = _check_no_mixed_definitions(hits, query_type)
        else:
            passed, offenders = False, [f"(알 수 없는 check: {ctype})"]

        if not passed:
            failures.append(
                {
                    "type": ctype,
                    "description": description,
                    "offending_quote_ids": offenders,
                }
            )

    return {
        "regression_passed": len(failures) == 0,
        "regression_failures": failures,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="SKMS RAG 자동 품질 평가")
    parser.add_argument("--input", default="eval/questions.seed.jsonl", help="평가 질의 파일")
    parser.add_argument("--output", default="eval/results.jsonl", help="결과 출력 파일")
    parser.add_argument("--limit", type=int, default=None, help="처리할 질의 수 제한")
    parser.add_argument("--index-dir", default="indexes/", help="인덱스 디렉토리")
    parser.add_argument("--retrieval-config", default="config/retrieval.yaml")
    parser.add_argument("--pipeline-config", default="config/pipeline.yaml")
    args = parser.parse_args()

    # API 키 확인
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    if not anthropic_key:
        print("Error: ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.", file=sys.stderr)
        sys.exit(1)

    try:
        import anthropic
        from openai import OpenAI
    except ImportError as e:
        print(f"Error: 필요한 패키지가 없습니다: {e}", file=sys.stderr)
        sys.exit(1)

    anthropic_client = anthropic.Anthropic(api_key=anthropic_key)
    openai_client = OpenAI(api_key=openai_key) if openai_key else None

    # 설정 로드
    retrieval_cfg = load_yaml(Path(args.retrieval_config))
    pipeline_cfg = load_yaml(Path(args.pipeline_config))

    # 프롬프트 로드
    router_prompt = Path("prompts/router.md").read_text(encoding="utf-8")
    answer_prompt = Path("prompts/answer.md").read_text(encoding="utf-8")

    # 인덱스 로드 (lib.retrieval 공유 함수 사용)
    index_dir = Path(args.index_dir)
    vector_cfg = retrieval_cfg.get("retrieval", {}).get("vector", {})
    keyword_cfg = retrieval_cfg.get("retrieval", {}).get("keyword", {})

    collection = load_chroma_collection(
        index_dir, vector_cfg.get("collection_name", "skms_quotes")
    )
    bm25_data = load_bm25_index(
        Path(keyword_cfg.get("index_path", "indexes/bm25_index.pkl"))
    )

    # 평가 질의 로드
    questions = load_questions(Path(args.input))
    if args.limit:
        questions = questions[: args.limit]

    print(f"[05] 평가 시작: {len(questions)}개 질의", file=sys.stderr)

    # 임계값 (quality_rules.yaml에서)
    thresholds = {
        "faithfulness": 4.0,
        "relevance": 3.5,
        "quote_accuracy": 3.5,
        "temporal_correctness": 3.5,
    }

    results: list[dict] = []
    scores_agg = {
        "relevance": [],
        "faithfulness": [],
        "quote_accuracy": [],
        "temporal_correctness": [],
    }
    pass_count = 0

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    for i, q in enumerate(questions, start=1):
        print(f"\r[05] 진행: {i}/{len(questions)} - {q['id']}", file=sys.stderr, end="")

        # RAG 실행
        answer, hits = run_rag_pipeline(
            q["query"],
            collection,
            bm25_data,
            openai_client,
            anthropic_client,
            retrieval_cfg,
            pipeline_cfg,
            router_prompt,
            answer_prompt,
        )

        # 평가
        judge_result = judge_answer(q["query"], answer, hits, anthropic_client)

        scores = {
            "relevance": judge_result.get("relevance", 0),
            "faithfulness": judge_result.get("faithfulness", 0),
            "quote_accuracy": judge_result.get("quote_accuracy", 0),
            "temporal_correctness": judge_result.get("temporal_correctness", 0),
        }

        judge_passed = all(scores[k] >= thresholds[k] for k in thresholds)

        # PR-8: regression checks (quote_id year 집합 검사)
        regression = run_regression_checks(q, hits)
        passed = judge_passed and regression["regression_passed"]

        result = {
            "id": q["id"],
            "query": q["query"],
            "query_type": q["query_type"],
            "answer": answer,
            "scores": scores,
            "passed": passed,
            "judge_passed": judge_passed,
            "judge_reasoning": judge_result.get("reasoning", ""),
            "regression_passed": regression["regression_passed"],
            "regression_failures": regression["regression_failures"],
        }
        results.append(result)

        for k in scores_agg:
            scores_agg[k].append(scores[k])
        if passed:
            pass_count += 1

    # 결과 저장
    with open(output_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 요약 출력
    print(f"\n\n{'='*60}", file=sys.stderr)
    print("SKMS RAG 평가 결과 요약", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"총 질의: {len(questions)}개", file=sys.stderr)
    print(
        f"통과: {pass_count}/{len(questions)} ({pass_count/max(len(questions),1)*100:.1f}%)",
        file=sys.stderr,
    )
    print(f"\n{'축':<25} {'평균':>6} {'최소':>6} {'최대':>6}", file=sys.stderr)
    print(f"{'-'*45}", file=sys.stderr)
    for k in ["relevance", "faithfulness", "quote_accuracy", "temporal_correctness"]:
        vals = scores_agg[k]
        if vals:
            avg = sum(vals) / len(vals)
            mn = min(vals)
            mx = max(vals)
            print(f"{k:<25} {avg:>6.2f} {mn:>6.1f} {mx:>6.1f}", file=sys.stderr)

    # PR-8: 회귀 테스트 실패 리포트
    regression_failures = [r for r in results if not r.get("regression_passed", True)]
    if regression_failures:
        print(f"\n[회귀 테스트 실패] {len(regression_failures)}건:", file=sys.stderr)
        for r in regression_failures:
            print(f"  {r['id']}: {r['query']}", file=sys.stderr)
            for fail in r.get("regression_failures", []):
                qids = ", ".join(fail.get("offending_quote_ids", []))
                print(
                    f"    - [{fail['type']}] {fail['description']}"
                    f" | 위반 quote_id: {qids}",
                    file=sys.stderr,
                )
    else:
        # regression_checks가 있는 질의만 카운트
        regression_count = sum(
            1
            for r in results
            if "regression_passed" in r
            and any(q.get("regression_checks") for q in questions if q["id"] == r["id"])
        )
        if regression_count > 0:
            print(
                f"\n[회귀 테스트] {regression_count}건 모두 PASS",
                file=sys.stderr,
            )

    print(f"\n[05] 결과 저장: {output_path}", file=sys.stderr)
    flush()


if __name__ == "__main__":
    main()
