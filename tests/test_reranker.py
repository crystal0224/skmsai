"""Reranker 테스트.

PR-021: Cohere + Cross-Encoder 재순위 서비스 단위/통합 테스트.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.reranker import (  # noqa: E402
    CohereReranker,
    CrossEncoderReranker,
    RerankerConfig,
    RerankerResult,
    create_reranker,
)
from scripts.lib.search_types import SearchHit  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hit(quote_id: str, text: str, score: float) -> SearchHit:
    """테스트용 SearchHit 생성."""
    return SearchHit(
        quote_id=quote_id,
        text=text,
        score=score,
        edition_id="2020-14차",
        year=2020,
        revision_num=14,
        quote_type="narrative",
        section_path=("VWBE",),
        source="hybrid",
        content_hash="abc123",
        quality_flags=(),
    )


# ---------------------------------------------------------------------------
# RerankerConfig 테스트
# ---------------------------------------------------------------------------


class TestRerankerConfig:
    """RerankerConfig frozen dataclass 테스트."""

    def test_defaults(self):
        """기본값 확인."""
        cfg = RerankerConfig()
        assert cfg.enabled is False
        assert cfg.backend == "cohere"
        assert cfg.model == "rerank-v3.5"
        assert cfg.top_n == 5
        assert cfg.score_threshold == 0.0

    def test_is_frozen(self):
        """불변이다."""
        cfg = RerankerConfig()
        with pytest.raises(AttributeError):
            cfg.enabled = True  # type: ignore[misc]

    def test_from_dict(self):
        """dict에서 생성."""
        data = {
            "enabled": True,
            "backend": "cross-encoder",
            "model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
            "top_n": 3,
            "score_threshold": 0.1,
        }
        cfg = RerankerConfig.from_dict(data)
        assert cfg.enabled is True
        assert cfg.backend == "cross-encoder"
        assert cfg.model == "cross-encoder/ms-marco-MiniLM-L-6-v2"
        assert cfg.top_n == 3
        assert cfg.score_threshold == 0.1

    def test_from_dict_partial(self):
        """일부만 지정하면 나머지는 기본값."""
        cfg = RerankerConfig.from_dict({"enabled": True})
        assert cfg.enabled is True
        assert cfg.backend == "cohere"  # default

    def test_from_dict_empty(self):
        """빈 dict → 기본값."""
        cfg = RerankerConfig.from_dict({})
        assert cfg.enabled is False

    def test_from_yaml(self, tmp_path):
        """YAML 파일에서 로드."""
        import yaml

        data = {
            "retrieval": {
                "reranker": {
                    "enabled": True,
                    "backend": "cohere",
                    "model": "rerank-v3.5",
                    "top_n": 3,
                },
            }
        }
        path = tmp_path / "retrieval.yaml"
        with open(path, "w") as f:
            yaml.dump(data, f)

        cfg = RerankerConfig.from_yaml(path)
        assert cfg.enabled is True
        assert cfg.top_n == 3

    def test_from_yaml_nonexistent(self):
        """존재하지 않는 YAML → 기본값."""
        cfg = RerankerConfig.from_yaml(Path("/nonexistent/retrieval.yaml"))
        assert cfg.enabled is False


# ---------------------------------------------------------------------------
# RerankerResult 테스트
# ---------------------------------------------------------------------------


class TestRerankerResult:
    """RerankerResult frozen dataclass 테스트."""

    def test_fields(self):
        """필드 접근."""
        result = RerankerResult(index=0, relevance_score=0.95)
        assert result.index == 0
        assert result.relevance_score == 0.95

    def test_is_frozen(self):
        """불변이다."""
        result = RerankerResult(index=0, relevance_score=0.5)
        with pytest.raises(AttributeError):
            result.relevance_score = 0.8  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CohereReranker 테스트
# ---------------------------------------------------------------------------


class TestCohereReranker:
    """CohereReranker 단위 테스트 (mock API)."""

    def test_rerank_returns_reordered_hits(self):
        """Cohere 재순위 결과가 올바르게 반환된다."""
        hits = [
            _hit("q1", "경영 일반 서술", 0.8),
            _hit("q2", "SUPEX 정의와 설명", 0.6),
            _hit("q3", "인간중심 경영의 핵심", 0.7),
        ]

        # Mock Cohere client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.results = [
            MagicMock(index=2, relevance_score=0.95),  # q3 → 1등
            MagicMock(index=0, relevance_score=0.80),  # q1 → 2등
            MagicMock(index=1, relevance_score=0.60),  # q2 → 3등
        ]
        mock_client.rerank.return_value = mock_response

        reranker = CohereReranker(client=mock_client, model="rerank-v3.5")
        result = reranker.rerank("SUPEX란 무엇인가?", hits, top_n=3)

        assert len(result) == 3
        assert result[0].quote_id == "q3"  # 최고 점수
        assert result[1].quote_id == "q1"
        assert result[2].quote_id == "q2"

    def test_rerank_updates_scores(self):
        """재순위 점수로 SearchHit score가 업데이트된다."""
        hits = [_hit("q1", "텍스트 1", 0.5)]

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.results = [
            MagicMock(index=0, relevance_score=0.92),
        ]
        mock_client.rerank.return_value = mock_response

        reranker = CohereReranker(client=mock_client, model="rerank-v3.5")
        result = reranker.rerank("query", hits, top_n=1)

        assert result[0].score == 0.92
        assert result[0].source == "reranked"

    def test_rerank_top_n_limits(self):
        """top_n으로 결과 수를 제한한다."""
        hits = [_hit(f"q{i}", f"텍스트 {i}", 0.5 + i * 0.1) for i in range(5)]

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.results = [
            MagicMock(index=i, relevance_score=0.9 - i * 0.1) for i in range(3)
        ]
        mock_client.rerank.return_value = mock_response

        reranker = CohereReranker(client=mock_client, model="rerank-v3.5")
        result = reranker.rerank("query", hits, top_n=3)

        assert len(result) == 3

    def test_rerank_preserves_hit_fields(self):
        """score/source 외 필드는 보존된다."""
        hit = _hit("q1", "원문 텍스트", 0.5)

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.results = [
            MagicMock(index=0, relevance_score=0.85),
        ]
        mock_client.rerank.return_value = mock_response

        reranker = CohereReranker(client=mock_client, model="rerank-v3.5")
        result = reranker.rerank("query", [hit], top_n=1)

        r = result[0]
        assert r.quote_id == "q1"
        assert r.text == "원문 텍스트"
        assert r.edition_id == "2020-14차"
        assert r.year == 2020
        assert r.section_path == ("VWBE",)
        assert r.content_hash == "abc123"

    def test_rerank_empty_hits(self):
        """빈 입력 → 빈 결과."""
        mock_client = MagicMock()
        reranker = CohereReranker(client=mock_client, model="rerank-v3.5")
        result = reranker.rerank("query", [], top_n=5)
        assert result == []
        mock_client.rerank.assert_not_called()

    def test_rerank_api_error_returns_original(self):
        """API 오류 시 원본 순서 반환 (graceful fallback)."""
        hits = [
            _hit("q1", "텍스트 1", 0.8),
            _hit("q2", "텍스트 2", 0.6),
        ]

        mock_client = MagicMock()
        mock_client.rerank.side_effect = Exception("API 오류")

        reranker = CohereReranker(client=mock_client, model="rerank-v3.5")
        result = reranker.rerank("query", hits, top_n=2)

        # 오류 시 원본 반환
        assert len(result) == 2
        assert result[0].quote_id == "q1"
        assert result[1].quote_id == "q2"

    def test_rerank_score_threshold(self):
        """score_threshold 이하 결과는 제외된다."""
        hits = [
            _hit("q1", "텍스트 1", 0.8),
            _hit("q2", "텍스트 2", 0.6),
            _hit("q3", "텍스트 3", 0.4),
        ]

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.results = [
            MagicMock(index=0, relevance_score=0.90),
            MagicMock(index=1, relevance_score=0.50),
            MagicMock(index=2, relevance_score=0.05),  # below threshold
        ]
        mock_client.rerank.return_value = mock_response

        reranker = CohereReranker(
            client=mock_client, model="rerank-v3.5", score_threshold=0.1
        )
        result = reranker.rerank("query", hits, top_n=3)

        assert len(result) == 2  # q3 제외
        assert all(r.score >= 0.1 for r in result)


# ---------------------------------------------------------------------------
# CrossEncoderReranker 테스트
# ---------------------------------------------------------------------------


class TestCrossEncoderReranker:
    """CrossEncoderReranker 단위 테스트 (mock model)."""

    def test_rerank_returns_reordered_hits(self):
        """Cross-Encoder 재순위 결과."""
        hits = [
            _hit("q1", "경영 일반 서술", 0.8),
            _hit("q2", "SUPEX 정의", 0.6),
            _hit("q3", "인간중심 경영", 0.7),
        ]

        # Mock cross-encoder model
        mock_model = MagicMock()
        # predict returns raw scores for each (query, doc) pair
        mock_model.predict.return_value = [0.3, 0.9, 0.6]  # q2가 최고

        reranker = CrossEncoderReranker(model=mock_model)
        result = reranker.rerank("SUPEX란?", hits, top_n=3)

        assert len(result) == 3
        assert result[0].quote_id == "q2"  # 0.9 최고
        assert result[1].quote_id == "q3"  # 0.6
        assert result[2].quote_id == "q1"  # 0.3

    def test_rerank_normalizes_scores(self):
        """Cross-Encoder 점수가 0~1 범위로 정규화된다."""
        hits = [
            _hit("q1", "텍스트 1", 0.5),
            _hit("q2", "텍스트 2", 0.5),
        ]

        mock_model = MagicMock()
        mock_model.predict.return_value = [-2.0, 3.0]

        reranker = CrossEncoderReranker(model=mock_model)
        result = reranker.rerank("query", hits, top_n=2)

        # sigmoid normalization → 0~1 범위
        assert all(0.0 <= r.score <= 1.0 for r in result)

    def test_rerank_updates_source(self):
        """source가 'reranked'로 변경된다."""
        hits = [_hit("q1", "텍스트", 0.5)]

        mock_model = MagicMock()
        mock_model.predict.return_value = [0.8]

        reranker = CrossEncoderReranker(model=mock_model)
        result = reranker.rerank("query", hits, top_n=1)

        assert result[0].source == "reranked"

    def test_rerank_empty_hits(self):
        """빈 입력 → 빈 결과."""
        mock_model = MagicMock()
        reranker = CrossEncoderReranker(model=mock_model)
        result = reranker.rerank("query", [], top_n=5)
        assert result == []
        mock_model.predict.assert_not_called()

    def test_rerank_error_returns_original(self):
        """모델 오류 시 원본 반환."""
        hits = [_hit("q1", "텍스트", 0.8)]

        mock_model = MagicMock()
        mock_model.predict.side_effect = RuntimeError("모델 오류")

        reranker = CrossEncoderReranker(model=mock_model)
        result = reranker.rerank("query", hits, top_n=1)

        assert len(result) == 1
        assert result[0].quote_id == "q1"

    def test_rerank_score_threshold(self):
        """score_threshold 이하 결과 제외."""
        hits = [
            _hit("q1", "관련 텍스트", 0.8),
            _hit("q2", "무관 텍스트", 0.6),
        ]

        mock_model = MagicMock()
        # sigmoid(5.0) ≈ 0.993, sigmoid(-5.0) ≈ 0.007
        mock_model.predict.return_value = [5.0, -5.0]

        reranker = CrossEncoderReranker(model=mock_model, score_threshold=0.1)
        result = reranker.rerank("query", hits, top_n=2)

        assert len(result) == 1
        assert result[0].quote_id == "q1"


# ---------------------------------------------------------------------------
# create_reranker 팩토리 테스트
# ---------------------------------------------------------------------------


class TestCreateReranker:
    """create_reranker 팩토리 함수 테스트."""

    def test_disabled_returns_none(self):
        """enabled=False → None."""
        cfg = RerankerConfig(enabled=False)
        assert create_reranker(cfg) is None

    def test_cohere_backend_without_key_returns_none(self):
        """COHERE_API_KEY 없으면 None."""
        cfg = RerankerConfig(enabled=True, backend="cohere")
        with patch.dict("os.environ", {}, clear=True):
            result = create_reranker(cfg)
        assert result is None

    def test_cohere_backend_with_key(self):
        """COHERE_API_KEY 있으면 CohereReranker 생성."""
        cfg = RerankerConfig(enabled=True, backend="cohere", model="rerank-v3.5")
        mock_cohere_module = MagicMock()
        mock_client = MagicMock()
        mock_cohere_module.ClientV2.return_value = mock_client

        with (
            patch.dict("os.environ", {"COHERE_API_KEY": "test-key"}),
            patch.dict("sys.modules", {"cohere": mock_cohere_module}),
        ):
            result = create_reranker(cfg)

        assert isinstance(result, CohereReranker)

    def test_cross_encoder_backend(self):
        """cross-encoder 백엔드."""
        cfg = RerankerConfig(
            enabled=True,
            backend="cross-encoder",
            model="cross-encoder/ms-marco-MiniLM-L-6-v2",
        )

        mock_ce_module = MagicMock()
        mock_model = MagicMock()
        mock_ce_module.CrossEncoder.return_value = mock_model

        with patch.dict("sys.modules", {"sentence_transformers": mock_ce_module}):
            result = create_reranker(cfg)

        assert isinstance(result, CrossEncoderReranker)

    def test_unknown_backend_returns_none(self):
        """알 수 없는 백엔드 → None."""
        cfg = RerankerConfig(enabled=True, backend="unknown")
        assert create_reranker(cfg) is None


# ---------------------------------------------------------------------------
# SearchService 통합 테스트 (reranker 포함)
# ---------------------------------------------------------------------------

chromadb = pytest.importorskip("chromadb")

from scripts.lib.bm25_index import BM25Index  # noqa: E402
from scripts.lib.quote import QuoteObject  # noqa: E402
from scripts.lib.search_service import HybridConfig, SearchService  # noqa: E402
from scripts.lib.vector_store import (  # noqa: E402
    VectorStore,
    make_fake_embedding_fn,
    quote_to_chroma_metadata,
)


def _make_quote(index: int = 0, **overrides) -> QuoteObject:
    """테스트용 QuoteObject."""
    text = overrides.get("text", f"인간중심 경영 테스트 {index}")
    edition_id = overrides.get("edition_id", "2020-14차")
    start_line = overrides.get("start_line", 15200 + index)
    return QuoteObject(
        quote_id=overrides.get("quote_id", f"2020-14차|test|narrative|{index:03d}"),
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


@pytest.fixture()
def integration_quotes():
    """통합 테스트용 quotes."""
    return [
        _make_quote(0, text="SUPEX는 Super Excellent 수준을 의미한다"),
        _make_quote(1, text="인간중심의 경영은 사람을 중심으로 한다"),
        _make_quote(2, text="VWBE Culture는 자발적 두뇌활용이다"),
        _make_quote(3, text="합리적 경영의 원칙을 설명한다"),
        _make_quote(4, text="현실을 인식한 경영 접근법이다"),
    ]


@pytest.fixture()
def integration_service(integration_quotes):
    """통합 테스트용 SearchService (reranker 없이)."""
    embed_fn = make_fake_embedding_fn(dim=128)
    store = VectorStore.ephemeral("reranker_test")
    ids = [q.quote_id for q in integration_quotes]
    embeddings = [embed_fn(q.text) for q in integration_quotes]
    documents = [q.text for q in integration_quotes]
    metadatas = [quote_to_chroma_metadata(q) for q in integration_quotes]
    store.upsert(ids, embeddings, documents, metadatas)

    bm25 = BM25Index.from_quotes(integration_quotes)
    # fake embedding → 낮은 score_threshold 필요
    cfg = HybridConfig(score_threshold=0.0)
    return SearchService(
        vector_store=store,
        bm25_index=bm25,
        embedding_fn=embed_fn,
        hybrid_config=cfg,
    )


class TestSearchServiceRerankerIntegration:
    """SearchService + Reranker 통합 테스트."""

    def test_hybrid_search_without_reranker(self, integration_service):
        """reranker 없이 hybrid_search 정상 동작."""
        hits = integration_service.hybrid_search("SUPEX", top_k=3)
        assert len(hits) > 0
        assert all(h.source == "hybrid" for h in hits)

    def test_hybrid_search_with_reranker(self, integration_quotes):
        """reranker가 있으면 재순위가 적용된다."""
        embed_fn = make_fake_embedding_fn(dim=128)
        store = VectorStore.ephemeral("reranker_integ")
        ids = [q.quote_id for q in integration_quotes]
        embeddings = [embed_fn(q.text) for q in integration_quotes]
        documents = [q.text for q in integration_quotes]
        metadatas = [quote_to_chroma_metadata(q) for q in integration_quotes]
        store.upsert(ids, embeddings, documents, metadatas)
        bm25 = BM25Index.from_quotes(integration_quotes)

        # Mock reranker
        mock_reranker = MagicMock()

        def mock_rerank(query, hits, top_n):
            """재순위: 역순으로 반환."""
            reversed_hits = list(reversed(hits[:top_n]))
            return [
                SearchHit(
                    quote_id=h.quote_id,
                    text=h.text,
                    score=0.9 - i * 0.1,
                    edition_id=h.edition_id,
                    year=h.year,
                    revision_num=h.revision_num,
                    quote_type=h.quote_type,
                    section_path=h.section_path,
                    source="reranked",
                    content_hash=h.content_hash,
                    quality_flags=h.quality_flags,
                )
                for i, h in enumerate(reversed_hits)
            ]

        mock_reranker.rerank = mock_rerank

        cfg = HybridConfig(score_threshold=0.0)
        svc = SearchService(
            vector_store=store,
            bm25_index=bm25,
            embedding_fn=embed_fn,
            hybrid_config=cfg,
            reranker=mock_reranker,
        )

        hits = svc.hybrid_search("SUPEX", top_k=3)
        assert len(hits) > 0
        assert all(h.source == "reranked" for h in hits)

    def test_reranker_disabled_skips_rerank(self, integration_quotes):
        """reranker=None이면 재순위를 건너뛴다."""
        embed_fn = make_fake_embedding_fn(dim=128)
        store = VectorStore.ephemeral("no_reranker")
        ids = [q.quote_id for q in integration_quotes]
        embeddings = [embed_fn(q.text) for q in integration_quotes]
        documents = [q.text for q in integration_quotes]
        metadatas = [quote_to_chroma_metadata(q) for q in integration_quotes]
        store.upsert(ids, embeddings, documents, metadatas)
        bm25 = BM25Index.from_quotes(integration_quotes)

        cfg = HybridConfig(score_threshold=0.0)
        svc = SearchService(
            vector_store=store,
            bm25_index=bm25,
            embedding_fn=embed_fn,
            hybrid_config=cfg,
            reranker=None,
        )

        hits = svc.hybrid_search("SUPEX", top_k=3)
        assert len(hits) > 0
        assert all(h.source == "hybrid" for h in hits)

    def test_service_backward_compatible(self, integration_service):
        """기존 SearchService API가 하위 호환된다."""
        # 기존 API 그대로 사용 가능
        vec_hits = integration_service.vector_search("경영", top_k=3, score_threshold=0.0)
        bm25_hits = integration_service.bm25_search("경영", top_k=3)
        hybrid_hits = integration_service.hybrid_search("경영", top_k=3)

        assert isinstance(vec_hits, list)
        assert isinstance(bm25_hits, list)
        assert isinstance(hybrid_hits, list)
