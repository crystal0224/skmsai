"""SearchService + BM25Index 테스트.

PR-011: fake embedding + ephemeral Chroma + in-memory BM25.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

chromadb = pytest.importorskip("chromadb")

from scripts.lib.quote import QuoteObject  # noqa: E402
from scripts.lib.search_types import SearchHit  # noqa: E402
from scripts.lib.vector_store import (  # noqa: E402
    VectorStore,
    make_fake_embedding_fn,
    quote_to_chroma_metadata,
)
from scripts.lib.bm25_index import BM25Index  # noqa: E402
from scripts.lib.search_service import (  # noqa: E402
    HybridConfig,
    SearchService,
    _normalize_bm25_scores,
)
from scripts.lib.synonym_map import SynonymMap  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EMBED_DIM = 128


def _make_quote(index: int = 0, **overrides) -> QuoteObject:
    """테스트용 QuoteObject."""
    text = overrides.get("text", f"인간중심의 경영 테스트 {index}")
    edition_id = overrides.get("edition_id", "2020-14차")
    start_line = overrides.get("start_line", 15200 + index)
    return QuoteObject(
        quote_id=overrides.get("quote_id", f"2020-14차|VWBE|narrative|{index:03d}"),
        text=str(text),
        edition_id=str(edition_id),
        year=int(overrides.get("year", 2020)),
        revision_num=int(overrides.get("revision_num", 14)),
        quote_type=str(overrides.get("quote_type", "narrative")),
        section_path=overrides.get("section_path", ("VWBE Culture",)),
        start_line=int(start_line),
        char_span=overrides.get("char_span", (100, 200)),
        token_count=int(overrides.get("token_count", 20)),
        content_hash=QuoteObject.compute_hash(
            str(text), str(edition_id), int(start_line)
        ),
        quality_flags=overrides.get("quality_flags", ()),
        is_definition=bool(overrides.get("is_definition", False)),
    )


def _seed_vector_store(
    store: VectorStore,
    embed_fn,
    quotes: list[QuoteObject],
) -> None:
    """VectorStore에 quotes를 적재한다."""
    ids = [q.quote_id for q in quotes]
    embeddings = [embed_fn(q.text) for q in quotes]
    documents = [q.text for q in quotes]
    metadatas = [quote_to_chroma_metadata(q) for q in quotes]
    store.upsert(ids, embeddings, documents, metadatas)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def embed_fn():
    return make_fake_embedding_fn(dim=_EMBED_DIM)


@pytest.fixture()
def test_quotes():
    """다양한 edition/type quotes 5건."""
    return [
        _make_quote(
            0,
            text="초판 기업관 정의 텍스트",
            edition_id="1979-초판",
            year=1979,
            revision_num=0,
            quote_type="definition",
            start_line=10,
            is_definition=True,
        ),
        _make_quote(
            1,
            text="초판 인간중심 원칙 텍스트",
            edition_id="1979-초판",
            year=1979,
            revision_num=0,
            quote_type="principle",
            start_line=20,
        ),
        _make_quote(
            2,
            text="14차 VWBE Culture 정의",
            edition_id="2020-14차",
            year=2020,
            revision_num=14,
            quote_type="definition",
            start_line=15200,
            is_definition=True,
        ),
        _make_quote(
            3,
            text="14차 인간중심 경영 서술",
            edition_id="2020-14차",
            year=2020,
            revision_num=14,
            quote_type="narrative",
            start_line=15210,
        ),
        _make_quote(
            4,
            text="14차 체크리스트 항목",
            edition_id="2020-14차",
            year=2020,
            revision_num=14,
            quote_type="checklist",
            start_line=15220,
        ),
    ]


@pytest.fixture()
def vector_store(test_quotes, embed_fn):
    """seed된 ephemeral VectorStore."""
    store = VectorStore.ephemeral("test_search")
    _seed_vector_store(store, embed_fn, test_quotes)
    return store


@pytest.fixture()
def bm25_index(test_quotes):
    """seed된 BM25Index."""
    return BM25Index.from_quotes(test_quotes)


@pytest.fixture()
def service(vector_store, bm25_index, embed_fn):
    """SearchService 인스턴스."""
    return SearchService(
        vector_store=vector_store,
        bm25_index=bm25_index,
        embedding_fn=embed_fn,
    )


# ---------------------------------------------------------------------------
# BM25Index 테스트
# ---------------------------------------------------------------------------


def test_bm25_from_quotes(test_quotes):
    """QuoteObject에서 BM25Index를 생성한다."""
    idx = BM25Index.from_quotes(test_quotes)
    assert idx.size == 5


def test_bm25_search_returns_search_hits(bm25_index):
    """BM25 검색 결과는 SearchHit 리스트."""
    hits = bm25_index.search("인간중심 경영", top_k=3)
    assert len(hits) > 0
    assert all(isinstance(h, SearchHit) for h in hits)
    assert all(h.source == "bm25" for h in hits)


def test_bm25_search_edition_filter(bm25_index):
    """BM25 edition 필터가 적용된다."""
    hits = bm25_index.search("인간중심", top_k=10, edition_filter="1979-초판")
    assert all(h.edition_id == "1979-초판" for h in hits)


def test_bm25_search_type_filter(bm25_index):
    """BM25 type 필터가 적용된다."""
    hits = bm25_index.search("정의 텍스트", top_k=10, type_filter=["definition"])
    assert all(h.quote_type == "definition" for h in hits)


def test_bm25_search_score_positive(bm25_index):
    """BM25 검색 점수는 양수."""
    hits = bm25_index.search("텍스트", top_k=5)
    assert all(h.score > 0 for h in hits)


def test_bm25_save_and_load(bm25_index, tmp_path):
    """BM25 인덱스 저장 + 로드."""
    save_path = tmp_path / "bm25.pkl"
    bm25_index.save(save_path)
    assert save_path.exists()

    loaded = BM25Index.from_path(save_path)
    assert loaded is not None
    assert loaded.size == bm25_index.size

    hits = loaded.search("텍스트", top_k=3)
    assert len(hits) > 0


def test_bm25_from_path_not_found(tmp_path):
    """존재하지 않는 경로 → None."""
    result = BM25Index.from_path(tmp_path / "nonexistent.pkl")
    assert result is None


def test_bm25_search_hit_fields(bm25_index):
    """BM25 SearchHit의 필드가 올바르게 설정된다."""
    hits = bm25_index.search("정의", top_k=1)
    assert hits, "정의 검색 결과가 없습니다"
    hit = hits[0]
    assert isinstance(hit.section_path, tuple)
    assert isinstance(hit.quality_flags, tuple)
    assert hit.content_hash != ""


# ---------------------------------------------------------------------------
# SearchService — vector_search 테스트
# ---------------------------------------------------------------------------


def test_vector_search_returns_hits(service):
    """벡터 검색 결과는 SearchHit 리스트."""
    hits = service.vector_search("인간중심 경영", top_k=3, score_threshold=0.0)
    assert len(hits) > 0
    assert all(isinstance(h, SearchHit) for h in hits)
    assert all(h.source == "vector" for h in hits)


def test_vector_search_edition_filter(service):
    """벡터 검색 edition 필터."""
    hits = service.vector_search(
        "텍스트", top_k=10, edition_filter="1979-초판", score_threshold=0.0
    )
    assert len(hits) > 0
    assert all(h.edition_id == "1979-초판" for h in hits)


def test_vector_search_type_filter(service):
    """벡터 검색 type 필터."""
    hits = service.vector_search(
        "정의", top_k=10, type_filter=["definition"], score_threshold=0.0
    )
    assert len(hits) > 0
    assert all(h.quote_type == "definition" for h in hits)


def test_vector_search_no_embedding_fn():
    """embedding_fn 없으면 빈 리스트."""
    store = VectorStore.ephemeral("empty")
    svc = SearchService(store, embedding_fn=None)
    assert svc.vector_search("test") == []


def test_vector_search_unavailable_store():
    """unavailable store → 빈 리스트."""
    store = VectorStore(None)
    fn = make_fake_embedding_fn(dim=_EMBED_DIM)
    svc = SearchService(store, embedding_fn=fn)
    assert svc.vector_search("test") == []


# ---------------------------------------------------------------------------
# SearchService — bm25_search 테스트
# ---------------------------------------------------------------------------


def test_bm25_search_via_service(service):
    """서비스를 통한 BM25 검색."""
    hits = service.bm25_search("인간중심", top_k=3)
    assert len(hits) > 0
    assert all(h.source == "bm25" for h in hits)


def test_bm25_search_no_index():
    """bm25_index 없으면 빈 리스트."""
    store = VectorStore.ephemeral("empty")
    svc = SearchService(store, bm25_index=None)
    assert svc.bm25_search("test") == []


# ---------------------------------------------------------------------------
# SearchService — hybrid_search 테스트
# ---------------------------------------------------------------------------


def test_hybrid_search_combines_results(service):
    """하이브리드 검색 결과는 hybrid source."""
    hits = service.hybrid_search("인간중심 경영", top_k=3)
    assert len(hits) > 0
    assert all(h.source == "hybrid" for h in hits)


def test_hybrid_search_edition_filter(service):
    """하이브리드 검색 edition 필터."""
    hits = service.hybrid_search("텍스트", top_k=10, edition_filter="2020-14차")
    assert all(h.edition_id == "2020-14차" for h in hits)


def test_hybrid_search_score_positive(service):
    """하이브리드 검색 점수는 양수."""
    hits = service.hybrid_search("텍스트", top_k=3)
    assert all(h.score > 0 for h in hits)


def test_hybrid_search_empty_result():
    """빈 인덱스 → 빈 결과."""
    store = VectorStore.ephemeral("empty")
    svc = SearchService(store, embedding_fn=make_fake_embedding_fn(dim=_EMBED_DIM))
    hits = svc.hybrid_search("test", top_k=5)
    assert hits == []


# ---------------------------------------------------------------------------
# SearchService — search_by_edition 테스트
# ---------------------------------------------------------------------------


def test_search_by_edition_hybrid(service):
    """search_by_edition은 edition 필터된 결과를 반환한다."""
    hits = service.search_by_edition("텍스트", edition_id="2020-14차", top_k=5)
    assert all(h.edition_id == "2020-14차" for h in hits)


def test_search_by_edition_bm25(service):
    """search_by_edition(mode=bm25)는 BM25로 검색한다."""
    hits = service.search_by_edition("텍스트", edition_id="1979-초판", top_k=5, mode="bm25")
    assert all(h.edition_id == "1979-초판" for h in hits)
    assert all(h.source == "bm25" for h in hits)


def test_search_by_edition_vector(service):
    """search_by_edition(mode=vector)는 벡터로 검색한다."""
    hits = service.search_by_edition(
        "텍스트", edition_id="2020-14차", top_k=5, mode="vector"
    )
    assert all(h.edition_id == "2020-14차" for h in hits)
    assert all(h.source == "vector" for h in hits)


# ---------------------------------------------------------------------------
# PR-019: BM25 동의어 확장 테스트
# ---------------------------------------------------------------------------

_SYNONYM_DATA = {
    "synonym_clusters": [
        {
            "name": "VWBE",
            "terms": ["VWBE", "자발적의욕적두뇌활용", "Brain Engagement"],
        },
        {
            "name": "인간중심",
            "terms": ["인간중심", "Human-centered"],
        },
    ],
}


@pytest.fixture()
def synonym_map():
    """테스트용 SynonymMap."""
    return SynonymMap.from_dict(_SYNONYM_DATA)


@pytest.fixture()
def service_with_synonyms(vector_store, bm25_index, embed_fn, synonym_map):
    """SynonymMap이 포함된 SearchService."""
    return SearchService(
        vector_store=vector_store,
        bm25_index=bm25_index,
        embedding_fn=embed_fn,
        synonym_map=synonym_map,
    )


def test_bm25_synonym_expansion(bm25_index, synonym_map):
    """BM25 직접 검색에서 동의어 확장."""
    # "VWBE"로 검색하면 "자발적의욕적두뇌활용" 등이 확장되어 더 넓게 검색
    hits_no_syn = bm25_index.search("VWBE", top_k=5)
    hits_with_syn = bm25_index.search("VWBE", top_k=5, synonym_map=synonym_map)

    # 동의어 확장 시 결과가 같거나 더 많아야 한다
    assert len(hits_with_syn) >= len(hits_no_syn)


def test_bm25_synonym_expansion_no_match(bm25_index, synonym_map):
    """동의어가 없는 쿼리는 원본과 동일."""
    hits_no_syn = bm25_index.search("체크리스트", top_k=5)
    hits_with_syn = bm25_index.search("체크리스트", top_k=5, synonym_map=synonym_map)

    # 동의어 매칭이 없으면 동일한 결과
    assert len(hits_no_syn) == len(hits_with_syn)


def test_bm25_synonym_none_fallback(bm25_index):
    """synonym_map=None은 확장 없이 정상 동작."""
    hits = bm25_index.search("인간중심", top_k=5, synonym_map=None)
    assert len(hits) > 0


def test_service_bm25_with_synonyms(service_with_synonyms):
    """서비스를 통한 BM25 검색에서 동의어 확장 적용."""
    hits = service_with_synonyms.bm25_search("VWBE", top_k=5)
    assert isinstance(hits, list)


def test_service_hybrid_with_synonyms(service_with_synonyms):
    """하이브리드 검색에서도 BM25 동의어 확장 적용."""
    hits = service_with_synonyms.hybrid_search("인간중심", top_k=5)
    assert isinstance(hits, list)


def test_service_no_synonym_map(vector_store, bm25_index, embed_fn):
    """synonym_map 없이도 정상 동작 (backward compatible)."""
    svc = SearchService(
        vector_store=vector_store,
        bm25_index=bm25_index,
        embedding_fn=embed_fn,
    )
    hits = svc.bm25_search("인간중심", top_k=3)
    assert len(hits) > 0


def test_definition_boost_applied(test_quotes):
    """정의 블록 가중치가 적용된다 (type_boost)."""
    type_boost = {"definition": 2.0, "principle": 1.5}
    idx = BM25Index.from_quotes(test_quotes, type_boost=type_boost)

    # "정의 텍스트"는 definition type → 2배 반복 토큰
    hits = idx.search("정의", top_k=5)
    assert len(hits) > 0
    # definition 타입이 상위에 위치해야 함
    top_hit = hits[0]
    assert top_hit.quote_type == "definition"


# ---------------------------------------------------------------------------
# PR-020: HybridConfig 테스트
# ---------------------------------------------------------------------------


def test_hybrid_config_defaults():
    """HybridConfig 기본값."""
    cfg = HybridConfig()
    assert cfg.alpha == 0.6
    assert cfg.rrf_k == 60
    assert cfg.final_top_k == 5
    assert cfg.normalize_scores is True


def test_hybrid_config_is_frozen():
    """HybridConfig는 불변이다."""
    cfg = HybridConfig()
    with pytest.raises(AttributeError):
        cfg.alpha = 0.5  # type: ignore[misc]


def test_hybrid_config_from_dict():
    """dict에서 HybridConfig 생성."""
    data = {"alpha": 0.7, "rrf_k": 40, "final_top_k": 10}
    cfg = HybridConfig.from_dict(data)
    assert cfg.alpha == 0.7
    assert cfg.rrf_k == 40
    assert cfg.final_top_k == 10


def test_hybrid_config_from_dict_partial():
    """일부만 지정하면 나머지는 기본값."""
    cfg = HybridConfig.from_dict({"alpha": 0.8})
    assert cfg.alpha == 0.8
    assert cfg.rrf_k == 60  # default


def test_hybrid_config_from_yaml(tmp_path):
    """YAML에서 HybridConfig 로드."""
    import yaml

    data = {
        "retrieval": {
            "hybrid": {"alpha": 0.5, "rrf_k": 30, "final_top_k": 3},
        }
    }
    path = tmp_path / "retrieval.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f)

    cfg = HybridConfig.from_yaml(path)
    assert cfg.alpha == 0.5
    assert cfg.rrf_k == 30
    assert cfg.final_top_k == 3


def test_hybrid_config_from_yaml_nonexistent():
    """존재하지 않는 YAML → 기본값."""
    cfg = HybridConfig.from_yaml(Path("/nonexistent/retrieval.yaml"))
    assert cfg.alpha == 0.6


# ---------------------------------------------------------------------------
# PR-020: BM25 점수 정규화 테스트
# ---------------------------------------------------------------------------


def _make_search_hit(quote_id: str, score: float) -> SearchHit:
    """테스트용 SearchHit (최소 필드)."""
    return SearchHit(
        quote_id=quote_id,
        text="test",
        score=score,
        edition_id="2020-14차",
        year=2020,
        revision_num=14,
        quote_type="narrative",
        section_path=(),
        source="bm25",
        content_hash="abc",
        quality_flags=(),
    )


def test_normalize_bm25_scores_range():
    """정규화 후 점수가 0~1 범위."""
    hits = [
        _make_search_hit("q1", 10.0),
        _make_search_hit("q2", 5.0),
        _make_search_hit("q3", 1.0),
    ]
    normalized = _normalize_bm25_scores(hits)
    assert normalized[0].score == 1.0  # max → 1.0
    assert normalized[2].score == 0.0  # min → 0.0
    assert 0.0 < normalized[1].score < 1.0


def test_normalize_bm25_scores_same_score():
    """모든 점수가 동일하면 0.5."""
    hits = [
        _make_search_hit("q1", 5.0),
        _make_search_hit("q2", 5.0),
    ]
    normalized = _normalize_bm25_scores(hits)
    assert all(h.score == 0.5 for h in normalized)


def test_normalize_bm25_scores_empty():
    """빈 리스트."""
    assert _normalize_bm25_scores([]) == []


def test_normalize_preserves_fields():
    """정규화가 다른 필드를 변경하지 않는다."""
    hits = [_make_search_hit("q-001", 10.0)]
    normalized = _normalize_bm25_scores(hits)
    assert normalized[0].quote_id == "q-001"
    assert normalized[0].source == "bm25"


# ---------------------------------------------------------------------------
# PR-020: SearchService hybrid_config 통합 테스트
# ---------------------------------------------------------------------------


def test_service_uses_hybrid_config(vector_store, bm25_index, embed_fn):
    """서비스가 HybridConfig를 사용한다."""
    cfg = HybridConfig(alpha=0.8, rrf_k=30, final_top_k=3)
    svc = SearchService(
        vector_store=vector_store,
        bm25_index=bm25_index,
        embedding_fn=embed_fn,
        hybrid_config=cfg,
    )
    assert svc.hybrid_config.alpha == 0.8
    hits = svc.hybrid_search("인간중심")
    assert len(hits) <= 3  # final_top_k=3


def test_service_hybrid_override_params(service):
    """hybrid_search 호출 시 파라미터 오버라이드."""
    hits = service.hybrid_search("인간중심", top_k=2, alpha=0.9, rrf_k=10)
    assert len(hits) <= 2


def test_service_default_hybrid_config(service):
    """기본 HybridConfig가 적용된다."""
    assert service.hybrid_config.alpha == 0.6
    assert service.hybrid_config.normalize_scores is True
