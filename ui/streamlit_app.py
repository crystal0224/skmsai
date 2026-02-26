"""SKMS Time-Aware RAG — Streamlit MVP UI.

PR-015: 검색/생성/목차 통합 인터페이스.

Usage:
    streamlit run ui/streamlit_app.py
"""
from __future__ import annotations

import json
import os

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_BASE = os.environ.get("SKMS_API_URL", "http://localhost:8000/api")

SEARCH_MODES = {"hybrid": "하이브리드", "vector": "벡터", "bm25": "BM25"}
OUTPUT_TYPES = {
    "summary": "요약",
    "card": "지식 카드",
    "quiz": "퀴즈",
    "comparison_table": "비교표",
    "slide": "슬라이드",
}
QUOTE_TYPES = [
    "definition",
    "principle",
    "procedure",
    "checklist",
    "example",
    "narrative",
]


# ---------------------------------------------------------------------------
# API Client
# ---------------------------------------------------------------------------


def _api_get(path: str, params: dict | None = None) -> dict | None:
    """API GET 요청."""
    try:
        resp = requests.get(f"{API_BASE}{path}", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        st.error(f"API 요청 실패: {e}")
        return None


def _api_post(path: str, payload: dict) -> dict | None:
    """API POST 요청."""
    try:
        resp = requests.post(f"{API_BASE}{path}", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        st.error(f"API 요청 실패: {e}")
        return None


# ---------------------------------------------------------------------------
# Page: 검색
# ---------------------------------------------------------------------------


def render_search_page() -> None:
    """검색 탭을 렌더링한다."""
    st.header("검색")

    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input("검색어", placeholder="예: SUPEX란 무엇인가?", key="search_query")
    with col2:
        mode = st.selectbox(
            "검색 모드", list(SEARCH_MODES.keys()), format_func=lambda x: SEARCH_MODES[x]
        )

    col3, col4, col5 = st.columns(3)
    with col3:
        top_k = st.slider("결과 수 (top_k)", 1, 20, 5)
    with col4:
        edition_filter = st.text_input(
            "개정판 필터", placeholder="예: 2020-14차", key="search_edition"
        )
    with col5:
        type_filter = st.multiselect("타입 필터", QUOTE_TYPES)

    if st.button("검색", type="primary", key="search_btn"):
        if not query:
            st.warning("검색어를 입력해주세요.")
            return

        payload = {
            "query": query,
            "mode": mode,
            "top_k": top_k,
        }
        if edition_filter:
            payload["edition_filter"] = edition_filter
        if type_filter:
            payload["type_filter"] = type_filter

        with st.spinner("검색 중..."):
            data = _api_post("/search", payload)

        if data:
            st.subheader(f"검색 결과 ({data['total']}건)")
            for i, hit in enumerate(data["hits"], start=1):
                with st.expander(
                    f"[{i}] {hit['quote_id']} (score: {hit['score']:.3f})",
                    expanded=i <= 3,
                ):
                    st.markdown(f"**개정판**: {hit['edition_id']} ({hit['year']})")
                    st.markdown(f"**유형**: {hit['quote_type']}")
                    st.markdown(f"**위치**: {' > '.join(hit['section_path'])}")
                    st.markdown(f"**출처**: {hit['source']}")
                    st.markdown("---")
                    st.markdown(hit["text"])


# ---------------------------------------------------------------------------
# Page: 생성
# ---------------------------------------------------------------------------


def render_generate_page() -> None:
    """생성 탭을 렌더링한다."""
    st.header("답변 생성")

    query = st.text_area(
        "질의", placeholder="예: SUPEX의 의미와 역사적 변화를 설명해주세요", height=100, key="gen_query"
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        output_type = st.selectbox(
            "출력 유형",
            [None, *OUTPUT_TYPES.keys()],
            format_func=lambda x: "일반 답변" if x is None else OUTPUT_TYPES[x],
        )
    with col2:
        edition_filter = st.text_input(
            "개정판 필터", placeholder="예: 2020-14차", key="gen_edition"
        )
    with col3:
        top_k = st.slider("참조 문서 수", 1, 20, 5, key="gen_top_k")

    if st.button("생성", type="primary", key="gen_btn"):
        if not query:
            st.warning("질의를 입력해주세요.")
            return

        payload = {
            "query": query,
            "top_k": top_k,
        }
        if output_type:
            payload["output_type"] = output_type
        if edition_filter:
            payload["edition_filter"] = edition_filter

        with st.spinner("답변 생성 중... (LLM 호출)"):
            data = _api_post("/generate", payload)

        if data:
            st.subheader("답변")

            # 메타데이터
            meta_cols = st.columns(4)
            meta_cols[0].metric("의도", data["intent"])
            meta_cols[1].metric("프롬프트", data["prompt_name"])
            meta_cols[2].metric("참조 문서", data["search_hits_count"])
            validation = data.get("validation_passed")
            meta_cols[3].metric(
                "검증",
                "통과" if validation is True else "실패" if validation is False else "N/A",
            )

            st.markdown("---")

            # 답변 내용
            if output_type and _is_json(data["answer"]):
                st.json(json.loads(data["answer"]))
            else:
                st.markdown(data["answer"])

            # 인용
            if data["citations"]:
                with st.expander(f"인용 ({len(data['citations'])}건)"):
                    for cid in data["citations"]:
                        st.code(cid)


# ---------------------------------------------------------------------------
# Page: 목차
# ---------------------------------------------------------------------------


def render_toc_page() -> None:
    """목차 탭을 렌더링한다."""
    st.header("개정판 목차")

    # 개정판 목록 로드
    editions_data = _api_get("/editions")
    if not editions_data:
        st.info("API 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.")
        return

    editions = editions_data["editions"]

    # 개정판 선택
    edition_labels = {
        e["edition_id"]: f"{e['edition_id']} ({e['year']}, {e['section_count']}개 섹션)"
        for e in editions
    }
    selected = st.selectbox(
        "개정판 선택",
        list(edition_labels.keys()),
        format_func=lambda x: edition_labels[x],
    )

    if selected:
        # 목차 트리 로드
        toc_data = _api_get(f"/toc/{selected}")
        if toc_data:
            st.subheader(f"{toc_data['label']} 개정판 목차 ({toc_data['node_count']}개 노드)")

            for section in toc_data["sections"]:
                _render_toc_node(section, indent=0)

    # 섹션 검색
    st.markdown("---")
    st.subheader("섹션 검색")
    search_query = st.text_input("섹션 제목 검색", placeholder="예: 인간중심", key="toc_search")

    if search_query:
        search_data = _api_get("/toc", params={"q": search_query})
        if search_data and search_data["total"] > 0:
            st.write(f"검색 결과: {search_data['total']}건")
            for r in search_data["results"]:
                st.markdown(
                    f"- **{r['title']}** ({r['edition_id']}, {r['level']}) — "
                    f"`{' > '.join(r['path'])}`"
                )
        elif search_data:
            st.info("검색 결과가 없습니다.")


def _render_toc_node(node: dict, indent: int) -> None:
    """목차 노드를 재귀적으로 렌더링한다."""
    level = node["level"]
    title = node["title"]
    children = node.get("children", [])

    prefix = "  " * indent
    level_markers = {
        "H1": "##",
        "H2": "###",
        "H3": "####",
        "H4": "#####",
        "H4b": "#####",
    }
    marker = level_markers.get(level, "######")

    if children:
        with st.expander(f"{prefix}{title} ({level})", expanded=indent < 1):
            for child in children:
                _render_toc_node(child, indent + 1)
    else:
        st.markdown(f"{prefix}- {title} `{level}`")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_json(text: str) -> bool:
    """문자열이 JSON인지 확인한다."""
    try:
        json.loads(text)
        return True
    except (json.JSONDecodeError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Streamlit 앱 메인."""
    st.set_page_config(
        page_title="SKMS RAG",
        page_icon="📚",
        layout="wide",
    )

    st.title("SKMS Time-Aware RAG")
    st.caption("SK경영체계 시간축 인식 검색 + 생성 시스템")

    # 서버 상태 확인
    health = _api_get("/health")
    if health:
        status = health["status"]
        if status == "ok":
            st.sidebar.success(f"서버 상태: {status} (v{health['version']})")
        else:
            st.sidebar.warning(f"서버 상태: {status}")

        components = health.get("components", {})
        for name, ready in components.items():
            icon = "✅" if ready else "❌"
            st.sidebar.text(f"  {icon} {name}")
    else:
        st.sidebar.error("서버에 연결할 수 없습니다")
        st.sidebar.caption(f"API URL: {API_BASE}")

    # 탭
    tab_search, tab_generate, tab_toc = st.tabs(["🔍 검색", "✨ 생성", "📋 목차"])

    with tab_search:
        render_search_page()

    with tab_generate:
        render_generate_page()

    with tab_toc:
        render_toc_page()


if __name__ == "__main__":
    main()
