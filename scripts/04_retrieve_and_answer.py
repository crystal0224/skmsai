#!/usr/bin/env python3
"""대화형 RAG 파이프라인: 질의 라우팅 → 하이브리드 검색 → Temporal Conflict 감지 → 답변 생성.

v3: 5대 개발과제 통합
  - Task 1: type 기반 검색 필터 (Chroma where + BM25 필터)
  - Task 2: section_path 기반 범위 필터 (섹션 접두사 매칭)
  - Task 3: 동적 top_k (content_generation 의도별 규모 조정)
  - Task 4: 텍스트 → char_span 역추적 (원문 위치 검색)
  - Task 5: content_gen.md 통합 (콘텐츠 생성 전용 프롬프트)

v2: Temporal Conflict Guardrail 적용
  - 5가지 Intent 분류 (A~E)
  - 의도별 검색 후처리 정책
  - 동일 개념 다중 정의 충돌 감지
  - quote_id 목록 필수 출력

Usage:
    python scripts/04_retrieve_and_answer.py                          # 대화형 모드
    python scripts/04_retrieve_and_answer.py --query "SUPEX란 무엇인가?"  # 단일 질의
    python scripts/04_retrieve_and_answer.py --lookup "경영의 궁극적 목적은 구성원의 행복"  # 원문 위치 검색
    python scripts/04_retrieve_and_answer.py --query "SUPEX란?" --canonical  # canonical 기준 응답
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from pathlib import Path

import yaml

# Ensure scripts/ is on sys.path for lib/observability imports
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.canonical import (  # noqa: E402
    format_canonical_context,
    load_canonical_store,
)
from lib.output_validator import validate_content_output  # noqa: E402
from lib.policy import apply_policy_layer, load_policy_config  # noqa: E402
from lib.retrieval import (  # noqa: E402
    EDITION_ORDER,
    bm25_search,
    edition_sort_key,
    load_bm25_index,
    load_chroma_collection,
    retrieve_quotes,
)
from observability.tracing import (  # noqa: E402
    flush,
    load_observability_config,
    start_trace,
    traceable,
)


# ---------------------------------------------------------------------------
# Config loaders
# ---------------------------------------------------------------------------


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Edition display helper (EDITION_ORDER + edition_sort_key from lib.retrieval)
# ---------------------------------------------------------------------------


def edition_display_name(edition_id: str) -> str:
    """개정판 ID를 표시용 이름으로 변환한다."""
    # "2020-14차" → "14차 개정판(2020)"
    # "1979-초판" → "초판(1979)"
    parts = edition_id.split("-", 1)
    if len(parts) == 2:
        year, name = parts
        if name == "초판":
            return f"초판({year})"
        return f"{name} 개정판({year})"
    return edition_id


# ---------------------------------------------------------------------------
# Query routing (v3: 5 intents + type_filter + section_filter)
# ---------------------------------------------------------------------------


@traceable("skms_router")
def route_query(query: str, router_prompt: str, client) -> dict:
    """LLM을 사용하여 질의 의도를 분류한다.

    v3: type_filter, section_filter 필드 추가
    """
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=router_prompt,
        messages=[{"role": "user", "content": query}],
    )
    text = message.content[0].text.strip()

    # JSON 파싱 시도
    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        result = json.loads(text)
        # v1 호환: query_type → intent
        if "query_type" in result and "intent" not in result:
            result["intent"] = result.pop("query_type")
        # v3 필드 기본값 보장
        result.setdefault("type_filter", None)
        result.setdefault("section_filter", None)
        return result
    except (json.JSONDecodeError, IndexError):
        return {
            "intent": "open_ended",
            "confidence": 0.5,
            "edition_hint": None,
            "output_type": None,
            "type_filter": None,
            "section_filter": None,
            "reasoning": "JSON 파싱 실패, open_ended로 분류",
        }


# ---------------------------------------------------------------------------
# Dynamic top_k (v3: Task 3)
# ---------------------------------------------------------------------------


def parse_count_from_query(query: str) -> int:
    """질의에서 생성 갯수 힌트를 추출한다.

    예: "5장의 카드" → 5, "퀴즈 3개" → 3, "10문제" → 10
    """
    match = re.search(r"(\d+)\s*(장|개|매|건|문제|문항|슬라이드|페이지)", query)
    if match:
        return min(int(match.group(1)), 20)  # 최대 20개로 제한
    return 3  # 기본값


def compute_dynamic_top_k(
    intent: str,
    output_type: str | None,
    query: str,
    base_top_k: int,
) -> int:
    """content_generation 의도에서 요청 규모에 따라 top_k를 동적 조정한다.

    - card: 카드 수 × 3 (하나의 카드에 여러 quote 필요)
    - quiz: 문제 수 × 3 (정답 + 오답 근거)
    - slide: 슬라이드 수 × 2
    - comparison_table: 최소 12 (다수 개정판 커버리지)
    - summary: 최소 8
    - 기타 의도: base_top_k 그대로
    """
    if intent != "content_generation":
        return base_top_k

    count = parse_count_from_query(query)

    if output_type == "card":
        return max(base_top_k, count * 3)
    elif output_type == "quiz":
        return max(base_top_k, count * 3)
    elif output_type == "slide":
        return max(base_top_k, count * 2)
    elif output_type == "comparison_table":
        return max(base_top_k, 12)
    else:  # summary 등
        return max(base_top_k, 8)


# ---------------------------------------------------------------------------
# Temporal Conflict Detection
# ---------------------------------------------------------------------------


def detect_temporal_conflicts(hits: list[dict]) -> dict:
    """검색 결과에서 시간축 충돌을 감지한다.

    조건: definition 타입 quote가 2개 이상의 개정판에 걸쳐 존재하면 충돌.

    Returns:
        {
            "has_conflict": bool,
            "conflicting_editions": [edition_id, ...],
            "definition_count": int,
            "edition_definitions": {edition_id: [hit, ...], ...},
        }
    """
    edition_defs: dict[str, list[dict]] = {}

    for h in hits:
        quote_type = h.get("type", "narrative")
        if quote_type == "definition":
            edition_id = h.get("edition", "unknown")
            edition_defs.setdefault(edition_id, []).append(h)

    conflicting_editions = sorted(
        [e for e in edition_defs if edition_defs[e]],
        key=edition_sort_key,
    )

    total_defs = sum(len(defs) for defs in edition_defs.values())

    return {
        "has_conflict": len(conflicting_editions) >= 2,
        "conflicting_editions": conflicting_editions,
        "definition_count": total_defs,
        "edition_definitions": edition_defs,
    }


# ---------------------------------------------------------------------------
# Text lookup (v3: Task 4 - 텍스트 → char_span 역추적)
# ---------------------------------------------------------------------------


def find_text_in_quotes(
    search_text: str,
    bm25_data: dict,
    threshold: float = 0.4,
    max_results: int = 5,
) -> list[dict]:
    """사용자 입력 텍스트와 가장 유사한 quote를 검색한다.

    Phase 1: 정확 부분 문자열 매칭 (가장 빠름)
    Phase 2: BM25 검색 + fuzzy 재점수 (대체 검색)
    """
    if not bm25_data:
        return []

    quote_map = bm25_data.get("quote_map", {})

    # Phase 1: 정확 부분 문자열 매칭 (검색 텍스트가 quote 내에 포함되는 경우만)
    exact_matches: list[dict] = []
    for qid, q in quote_map.items():
        text = q.get("text", "")
        if search_text in text:
            exact_matches.append(_make_lookup_hit(qid, q, 1.0, "exact_substring"))

    if exact_matches:
        exact_matches.sort(key=lambda h: len(h["text"]), reverse=True)
        return exact_matches[:max_results]

    # Phase 2: BM25로 후보 추출 + 부분 매칭 재점수
    # SequenceMatcher.ratio()는 길이 차이가 큰 문자열 쌍에서 과소 평가하므로
    # 검색 텍스트 기준 매칭 비율(partial ratio)을 사용한다.
    bm25_hits = bm25_search(
        bm25_data, search_text, top_k=max_results * 3, edition_filter=None
    )

    search_len = len(search_text)
    for hit in bm25_hits:
        qid = hit["quote_id"]
        q_data = quote_map.get(qid, {})
        text = q_data.get("text", "")
        if not text or not search_len:
            hit["fuzzy_score"] = 0.0
            continue
        matcher = difflib.SequenceMatcher(None, search_text, text)
        matching_chars = sum(block.size for block in matcher.get_matching_blocks())
        # 검색 텍스트 대비 매칭 비율 (quote가 길어도 불이익 없음)
        hit["fuzzy_score"] = matching_chars / search_len

    bm25_hits.sort(key=lambda h: h.get("fuzzy_score", 0), reverse=True)
    return [h for h in bm25_hits if h.get("fuzzy_score", 0) >= threshold][:max_results]


def _make_lookup_hit(qid: str, q: dict, score: float, match_type: str) -> dict:
    """텍스트 검색 결과 hit 객체를 생성한다."""
    char_span = q.get("char_span", [0, 0])
    return {
        "quote_id": qid,
        "text": q.get("text", ""),
        "score": score,
        "source": f"lookup_{match_type}",
        "metadata": {
            "edition_id": q.get("edition_id", ""),
            "type": q.get("type", "narrative"),
            "section_path": json.dumps(q.get("section_path", []), ensure_ascii=False),
            "char_span_start": char_span[0] if len(char_span) > 0 else 0,
            "char_span_end": char_span[1] if len(char_span) > 1 else 0,
            "start_line": q.get("start_line", 0),
            "quality_flags": json.dumps(q.get("quality_flags", []), ensure_ascii=False),
        },
    }


def expand_section_quotes(
    section_prefix: str,
    bm25_data: dict,
    edition_filter: str | None = None,
    max_results: int = 10,
) -> list[dict]:
    """동일 section_path 접두사 하위의 모든 quote를 수집한다.

    예: section_prefix="인사관리" → 인사관리 하위 모든 quote 반환
    """
    if not bm25_data:
        return []

    quote_map = bm25_data.get("quote_map", {})
    hits: list[dict] = []

    type_priority = {
        "definition": 0,
        "principle": 1,
        "example": 2,
        "checklist": 3,
        "procedure": 4,
        "narrative": 5,
    }

    for qid, q in quote_map.items():
        sp = q.get("section_path", [])
        if not any(section_prefix in s for s in sp):
            continue
        if edition_filter and q.get("edition_id") != edition_filter:
            continue

        hits.append(_make_lookup_hit(qid, q, 0.5, "section_expand"))

    # 타입 우선순위 → 개정판 순으로 정렬
    hits.sort(
        key=lambda h: (
            type_priority.get(h["metadata"]["type"], 5),
            edition_sort_key(h["metadata"]["edition_id"]),
        )
    )

    return hits[:max_results]


# ---------------------------------------------------------------------------
# Context formatting (v2: quote_id + metadata block)
# ---------------------------------------------------------------------------


def format_context(
    hits: list[dict],
    intent: str,
    conflict_info: dict,
    output_type: str | None,
    output_specs: dict | None,
) -> str:
    """검색 결과를 answer.md 프롬프트의 컨텍스트 형식으로 포맷팅한다."""
    parts: list[str] = []

    # [METADATA] 블록
    metadata_block = (
        f"[METADATA]\n"
        f"intent: {intent}\n"
        f"temporal_conflict: {'true' if conflict_info['has_conflict'] else 'false'}\n"
        f"conflicting_editions: {json.dumps(conflict_info['conflicting_editions'], ensure_ascii=False)}\n"
        f"output_type: {output_type or 'null'}\n"
    )

    # content_generation이면 output_specs 포함
    if intent == "content_generation" and output_type and output_specs:
        spec = output_specs.get("output_types", {}).get(output_type, {})
        if spec:
            metadata_block += f"output_specs: {json.dumps(spec, ensure_ascii=False)}\n"
        else:
            metadata_block += "output_specs: null\n"
    else:
        metadata_block += "output_specs: null\n"

    parts.append(metadata_block)

    # [CHUNK n] 블록들 (retrieve_quotes 표준 dict 사용)
    for i, hit in enumerate(hits, start=1):
        edition = hit.get("edition", "unknown")
        chapter_path = hit.get("chapter_path", [])
        section = " > ".join(chapter_path) if chapter_path else "unknown"
        quality_flags = hit.get("quality_flags", [])
        quote_type = hit.get("type", "narrative")

        part = (
            f"[CHUNK {i}]\n"
            f"quote_id: {hit['quote_id']}\n"
            f"edition: {edition}\n"
            f"section: {section}\n"
            f"type: {quote_type}\n"
            f"quality_flags: {quality_flags}\n"
            f"---\n"
            f"{hit['text']}\n"
        )
        parts.append(part)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Answer generation (v3: intent-based prompt selection)
# ---------------------------------------------------------------------------


@traceable("skms_answer")
def generate_answer(
    query: str,
    context: str,
    system_prompt: str,
    client,
) -> str:
    """LLM을 사용하여 컨텍스트 기반 답변을 생성한다.

    v3: system_prompt를 동적으로 받아 intent에 따라 answer.md 또는 content_gen.md 사용
    """
    user_message = f"## 질의\n\n{query}\n\n## 컨텍스트\n\n{context}"

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return message.content[0].text


# ---------------------------------------------------------------------------
# Quote ID extraction
# ---------------------------------------------------------------------------


def extract_quote_ids(hits: list[dict]) -> list[str]:
    """검색 결과에서 quote_id 목록을 추출한다."""
    return [h["quote_id"] for h in hits if h.get("quote_id")]


# ---------------------------------------------------------------------------
# Text lookup mode (v3: Task 4 - CLI --lookup)
# ---------------------------------------------------------------------------


def run_text_lookup(
    search_text: str,
    bm25_data: dict,
) -> None:
    """텍스트 역추적 모드: 원문 위치와 섹션 컨텍스트를 출력한다."""
    print(
        f"\n[텍스트 검색] 입력: \"{search_text[:80]}{'...' if len(search_text) > 80 else ''}\""
    )
    print("=" * 60)

    # Phase 1: 유사 quote 검색
    matches = find_text_in_quotes(search_text, bm25_data, threshold=0.3, max_results=5)

    if not matches:
        print("\n검색 결과가 없습니다. 입력 텍스트를 확인해주세요.")
        return

    print(f"\n[매칭 결과] {len(matches)}건\n")

    for i, hit in enumerate(matches, start=1):
        meta = hit.get("metadata", {})
        edition = meta.get("edition_id", "unknown")
        section_path = meta.get("section_path", "[]")
        quote_type = meta.get("type", "narrative")
        score = hit.get("fuzzy_score", hit.get("score", 0))

        # section_path 파싱
        if isinstance(section_path, str):
            try:
                sp_list = json.loads(section_path)
                section = " > ".join(sp_list)
            except json.JSONDecodeError:
                section = section_path
        else:
            section = " > ".join(section_path)

        print(f"  [{i}] 유사도: {score:.2f} | {edition} | {section}")
        print(f"      타입: {quote_type}")
        print(f"      quote_id: {hit['quote_id']}")

        # char_span 정보
        cs_start = meta.get("char_span_start", 0)
        cs_end = meta.get("char_span_end", 0)
        start_line = meta.get("start_line", 0)
        if cs_start or cs_end:
            print(f"      char_span: [{cs_start}, {cs_end}] | 시작줄: {start_line}")

        # 텍스트 미리보기
        text_preview = hit["text"][:200].replace("\n", " ")
        print(f"      원문: {text_preview}{'...' if len(hit['text']) > 200 else ''}")
        print()

    # Phase 2: 최상위 매칭의 섹션 컨텍스트 확장
    best_match = matches[0]
    best_meta = best_match.get("metadata", {})
    best_section = best_meta.get("section_path", "[]")

    if isinstance(best_section, str):
        try:
            sp_list = json.loads(best_section)
        except json.JSONDecodeError:
            sp_list = []
    else:
        sp_list = best_section

    if sp_list:
        section_prefix = sp_list[0]  # 최상위 섹션명
        print(f"[섹션 컨텍스트] '{section_prefix}' 하위 관련 quote:")
        print("-" * 40)

        related = expand_section_quotes(
            section_prefix,
            bm25_data,
            edition_filter=best_meta.get("edition_id"),
            max_results=5,
        )
        for j, rel in enumerate(related, start=1):
            rel_meta = rel.get("metadata", {})
            rel_section = rel_meta.get("section_path", "[]")
            if isinstance(rel_section, str):
                try:
                    rel_sp = json.loads(rel_section)
                    rel_section_str = " > ".join(rel_sp)
                except json.JSONDecodeError:
                    rel_section_str = rel_section
            else:
                rel_section_str = " > ".join(rel_section)

            print(
                f"  {j}. [{rel_meta.get('type', '?')}] {rel_section_str}"
                f" — {rel['quote_id']}"
            )
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="SKMS 대화형 RAG 파이프라인 (v3)")
    parser.add_argument("--query", type=str, default=None, help="단일 질의 (미지정 시 대화형 모드)")
    parser.add_argument(
        "--lookup", type=str, default=None, help="텍스트 역추적 모드: 원문 위치와 섹션 컨텍스트를 검색"
    )
    parser.add_argument(
        "--output-type", default=None, help="출력 유형 (content_generation 시)"
    )
    parser.add_argument("--index-dir", default="indexes/", help="인덱스 디렉토리")
    parser.add_argument("--retrieval-config", default="config/retrieval.yaml")
    parser.add_argument("--pipeline-config", default="config/pipeline.yaml")
    parser.add_argument("--output-specs", default="config/output_specs.yaml")
    parser.add_argument(
        "--canonical",
        action="store_true",
        default=False,
        help="canonical 기준 응답 모드 (2020-14차 기본 정의 우선)",
    )
    args = parser.parse_args()

    # API 키 확인
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    if not anthropic_key and not args.lookup:
        print("Error: ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.", file=sys.stderr)
        sys.exit(1)

    # 설정 로드
    retrieval_cfg = load_yaml(Path(args.retrieval_config))
    pipeline_cfg = load_yaml(Path(args.pipeline_config))
    output_specs = load_yaml(Path(args.output_specs))

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

    # 관측 설정 로드
    obs_config = load_observability_config()

    # 정책 설정 로드
    policy_config = load_policy_config()

    # PR-5: canonical store 로드
    canonical_store = load_canonical_store() if args.canonical else None
    if canonical_store and canonical_store.count > 0:
        print(
            f"[canonical] {canonical_store.count}개 canonical 항목 로드",
            file=sys.stderr,
        )

    # 프롬프트 로드
    router_prompt = load_prompt(Path("prompts/router.md"))
    answer_prompt = load_prompt(Path("prompts/answer.md"))

    # Task 5: content_gen.md 프롬프트 로드
    content_gen_path = Path("prompts/content_gen.md")
    if content_gen_path.exists():
        content_gen_prompt = load_prompt(content_gen_path)
    else:
        print(
            "[04] 경고: content_gen.md 없음 — content_generation 의도에 answer_prompt로 대체합니다.",
            file=sys.stderr,
        )
        content_gen_prompt = answer_prompt

    # 인덱스 로드
    index_dir = Path(args.index_dir)
    bm25_data = load_bm25_index(
        Path(keyword_cfg.get("index_path", "indexes/bm25_index.pkl"))
    )

    # Task 4: --lookup 모드 (API 키 없이도 동작)
    if args.lookup:
        if not bm25_data:
            print(
                "Error: BM25 인덱스가 필요합니다. 먼저 03_build_indexes.py를 실행하세요.",
                file=sys.stderr,
            )
            sys.exit(1)
        run_text_lookup(args.lookup, bm25_data)
        return

    # API 클라이언트 초기화 (lookup 이외 모드)
    try:
        import anthropic
        from openai import OpenAI
    except ImportError as e:
        print(f"Error: 필요한 패키지가 없습니다: {e}", file=sys.stderr)
        sys.exit(1)

    anthropic_client = anthropic.Anthropic(api_key=anthropic_key)
    openai_client = OpenAI(api_key=openai_key) if openai_key else None

    collection = load_chroma_collection(
        index_dir, vector_cfg.get("collection_name", "skms_quotes")
    )

    def process_query(query: str) -> None:
        """단일 질의를 처리한다."""
        with start_trace(query, obs_config) as trace:
            # ─── 1. 질의 라우팅 (Intent 분류) ───
            route_result = route_query(query, router_prompt, anthropic_client)
            intent = route_result.get("intent", "open_ended")
            edition_hint = route_result.get("edition_hint")
            confidence = route_result.get("confidence", 0.0)
            output_type = route_result.get("output_type") or args.output_type

            # v3: type_filter, section_filter 파싱
            type_filter = route_result.get("type_filter")
            section_filter = route_result.get("section_filter")

            # type_filter 유효성 검증
            valid_types = {
                "definition",
                "principle",
                "procedure",
                "checklist",
                "example",
                "narrative",
            }
            if type_filter:
                type_filter = [t for t in type_filter if t in valid_types]
                if not type_filter:
                    type_filter = None

            print(
                f"\n[라우팅] 의도: {intent} | 확신도: {confidence:.2f}"
                f" | 개정판: {edition_hint or '전체'}"
                f" | 출력: {output_type or '기본'}"
                f" | 타입필터: {type_filter or '전체'}"
                f" | 섹션필터: {section_filter or '전체'}",
                file=sys.stderr,
            )

            # [관측] 라우터 결과 기록
            trace.log_router(
                intent=intent,
                confidence=confidence,
                edition_hint=edition_hint,
                output_type=output_type,
                type_filter=type_filter,
                section_filter=section_filter,
            )

            # ─── 2. 동적 top_k 계산 (Task 3) ───
            base_top_k = hybrid_cfg.get("final_top_k", 5)
            final_top_k = compute_dynamic_top_k(intent, output_type, query, base_top_k)

            if final_top_k != base_top_k:
                print(
                    f"[동적 top_k] {base_top_k} → {final_top_k}"
                    f" (의도: {intent}, 출력: {output_type})",
                    file=sys.stderr,
                )

            # ─── 3. 검색 정책 구성 ───
            vec_top_k = vector_cfg.get("top_k", 10)
            bm25_top_k = keyword_cfg.get("top_k", 10)

            # 동적 top_k에 비례하여 검색 범위도 확대
            if final_top_k > base_top_k:
                scale = final_top_k / base_top_k
                vec_top_k = int(vec_top_k * scale)
                bm25_top_k = int(bm25_top_k * scale)

            base_policy = {
                "edition_hint": edition_hint,
                "edition_filter": filters_cfg.get("edition_filter"),
                "type_filter": type_filter,
                "section_filter": section_filter,
                "alpha": hybrid_cfg.get("alpha", 0.6),
                "rrf_k": hybrid_cfg.get("rrf_k", 60),
                "score_threshold": vector_cfg.get("score_threshold", 0.5),
                "vec_top_k": vec_top_k,
                "bm25_top_k": bm25_top_k,
                "latest_first": False,
            }

            # PR-4: 정책 레이어 적용 (latest_first 강제, 개정판 폴백 등)
            policy = apply_policy_layer(intent, base_policy, policy_config)

            if policy.get("latest_first"):
                print(
                    f"[정책] latest_first=True, "
                    f"edition_filter={policy.get('edition_filter')}",
                    file=sys.stderr,
                )

            # [관측] 검색 정책 기록
            trace.log_policy(policy)

            # ─── 4. 하이브리드 검색 (retrieve_quotes 단일 엔트리) ───
            results = retrieve_quotes(
                query,
                intent,
                policy,
                top_k=final_top_k,
                collection=collection,
                bm25_data=bm25_data,
                openai_client=openai_client,
                embedding_model=embedding_model,
            )

            if not results:
                print("\n검색 결과가 없습니다. 인덱스를 먼저 구축했는지 확인하세요.")
                return

            # [관측] 검색 결과 기록 (privacy-safe)
            trace.log_retrieval(results)

            # ─── 5. Temporal Conflict 감지 ───
            conflict_info = detect_temporal_conflicts(results)

            if conflict_info["has_conflict"]:
                editions_str = ", ".join(
                    edition_display_name(e)
                    for e in conflict_info["conflicting_editions"]
                )
                print(
                    f"[충돌] 시간축 충돌 감지: {conflict_info['definition_count']}개 정의,"
                    f" 개정판: {editions_str}",
                    file=sys.stderr,
                )

            # ─── 5.5. PR-5: Canonical 기준 정의 삽입 ───
            canonical_prefix = ""
            if canonical_store and intent in (
                "general_definition",
                "open_ended",
            ):
                canonical_hit = canonical_store.lookup(query)
                if canonical_hit:
                    canonical_prefix = format_canonical_context(canonical_hit)
                    print(
                        f"[canonical] 매칭: {canonical_hit['subject']}"
                        f" ({canonical_hit['canonical_id']})",
                        file=sys.stderr,
                    )

            # ─── 6. 컨텍스트 포맷팅 ───
            context = format_context(
                results,
                intent=intent,
                conflict_info=conflict_info,
                output_type=output_type,
                output_specs=output_specs,
            )

            # canonical 기준 정의가 있으면 컨텍스트 앞에 삽입
            if canonical_prefix:
                context = canonical_prefix + "\n" + context

            # [관측] 프롬프트 메타데이터 기록
            if intent == "content_generation":
                selected_prompt = content_gen_prompt
                prompt_name = "content_gen.md"
                print("[프롬프트] content_gen.md 사용", file=sys.stderr)
            else:
                selected_prompt = answer_prompt
                prompt_name = "answer.md"

            trace.log_prompt(context, prompt_name)

            # ─── 7. 답변 생성 (Task 5: intent별 프롬프트 분기) ───
            answer = generate_answer(query, context, selected_prompt, anthropic_client)

            # [관측] 응답 메타데이터 기록
            trace.log_response(answer)

            # ─── 7.5. PR-7: 콘텐츠 생성 출력 스키마 검증 ───
            if intent == "content_generation" and output_type:
                validation = validate_content_output(answer, output_type)
                trace.log_validation(validation.to_dict())

                if not validation.passed:
                    print(
                        f"[검증] 스키마 검증 실패 ({output_type}): "
                        f"{'; '.join(validation.errors[:2])}",
                        file=sys.stderr,
                    )
                    # 재생성 1회 시도 — 정적 힌트만 사용 (prompt injection 방지)
                    retry_hint = (
                        f"\n\n[시스템] 이전 응답이 {output_type} JSON 스키마를 "
                        f"충족하지 못했습니다. "
                        f"올바른 JSON 형식으로 다시 생성해 주세요."
                    )
                    retry_context = context + retry_hint
                    retry_answer = generate_answer(
                        query,
                        retry_context,
                        selected_prompt,
                        anthropic_client,
                    )
                    trace.log_response(retry_answer)

                    # 재검증
                    retry_validation = validate_content_output(
                        retry_answer, output_type
                    )
                    trace.log_validation(retry_validation.to_dict())

                    if retry_validation.passed:
                        answer = retry_answer
                        print(
                            f"[검증] 재시도 성공 — {output_type} 스키마 통과",
                            file=sys.stderr,
                        )
                    else:
                        # 재시도도 실패 — 원본 answer를 그대로 반환
                        print(
                            f"[검증] 재시도 후에도 스키마 검증 실패. " f"검증 미통과 응답을 반환합니다.",
                            file=sys.stderr,
                        )
                else:
                    print(
                        f"[검증] {output_type} 스키마 통과",
                        file=sys.stderr,
                    )

            print(f"\n{answer}")

            # ─── 8. 검색 결과 참고 정보 (표준화된 dict 사용) ───
            quote_ids = extract_quote_ids(results)
            print("\n---")
            print(f"검색 결과 출처 ({len(results)}개 청크):")
            for hit in results:
                section_str = (
                    " > ".join(hit["chapter_path"]) if hit["chapter_path"] else "[]"
                )
                print(
                    f"  - [{hit['edition']}] {section_str} ({hit['type']}) — {hit['quote_id']}"
                )

            if len(quote_ids) < 2:
                print(
                    "\n⚠ 단일 출처 경고: 1개 이하의 quote만 참조되었습니다." " 추가 검색이 권장됩니다.",
                    file=sys.stderr,
                )

    # 실행
    try:
        if args.query:
            process_query(args.query)
        else:
            print("SKMS Time-Aware RAG 파이프라인 v3")
            print(
                "  (Temporal Conflict Guardrail + Type/Section Filter + Dynamic top_k)"
            )
            print("질의를 입력하세요 (종료: Ctrl+C)\n")
            try:
                while True:
                    query = input("SKMS> ").strip()
                    if not query:
                        continue
                    process_query(query)
                    print()
            except (KeyboardInterrupt, EOFError):
                print("\n종료합니다.")
    finally:
        flush()


if __name__ == "__main__":
    main()
