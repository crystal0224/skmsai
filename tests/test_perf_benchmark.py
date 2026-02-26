"""성능 벤치마크 테스트.

PR-037: 핵심 서비스 성능 측정 + 캐시 효과 검증.

pytest로 실행되며, 각 벤치마크는 반복 실행 후 통계를 기록한다.
실패 기준(SLO)은 아직 적용하지 않으며, 참고용 벤치마크.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

from scripts.lib.bm25_index import BM25Index
from scripts.lib.db import get_connection, init_db
from scripts.lib.metrics_collector import MetricsCollector, _compute_latency
from scripts.lib.query_cache import QueryCache, build_cache_key
from scripts.lib.quote import QuoteObject
from scripts.lib.quote_repository import QuoteRepository
from scripts.lib.search_service import SearchService, HybridConfig, _rrf_fusion
from scripts.lib.search_types import SearchHit
from scripts.lib.vector_store import VectorStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_quote(
    idx: int, edition: str = "2020-14차", qtype: str = "definition"
) -> QuoteObject:
    """벤치마크용 QuoteObject 생성."""
    text = f"SKMS 벤치마크 인용문 #{idx}. 인간의 능력을 극대화하여 SUPEX를 추구한다."
    return QuoteObject(
        quote_id=f"{edition}|bench|{qtype}|{idx:03d}",
        text=text,
        edition_id=edition,
        year=int(edition[:4]),
        revision_num=14,
        quote_type=qtype,
        section_path=("경영", "벤치마크"),
        start_line=idx * 10 + 1,
        char_span=(0, len(text)),
        token_count=len(text.split()),
        content_hash=QuoteObject.compute_hash(text, edition, idx * 10 + 1),
        quality_flags=(),
        is_definition=qtype == "definition",
    )


def _make_search_hit(idx: int, source: str = "vector") -> SearchHit:
    """벤치마크용 SearchHit 생성."""
    return SearchHit(
        quote_id=f"2020-14차|bench|definition|{idx:03d}",
        text=f"벤치마크 인용문 #{idx}",
        score=1.0 - idx * 0.01,
        edition_id="2020-14차",
        year=2020,
        revision_num=14,
        quote_type="definition",
        section_path=("경영",),
        source=source,
        content_hash=f"hash{idx:03d}",
        quality_flags=(),
    )


def _timeit(fn, iterations: int = 100) -> list[float]:
    """함수를 반복 실행하고 각 소요 시간(ms)을 반환."""
    times: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        times.append(elapsed_ms)
    return times


# ---------------------------------------------------------------------------
# BM25 벤치마크
# ---------------------------------------------------------------------------


class TestBM25Benchmark:
    """BM25 검색 성능 벤치마크."""

    @pytest.fixture()
    def bm25_index(self) -> BM25Index:
        """벤치마크용 BM25 인덱스 (500 quotes)."""
        quotes = [_make_quote(i) for i in range(500)]
        return BM25Index.from_quotes(quotes)

    def test_bm25_search_latency(self, bm25_index: BM25Index):
        """BM25 검색 p95 < 50ms (500 quotes 기준)."""
        durations = _timeit(
            lambda: bm25_index.search("SUPEX 추구", top_k=10),
            iterations=50,
        )
        stats = _compute_latency(durations)
        assert stats.p95 < 50.0, f"BM25 p95={stats.p95:.1f}ms > 50ms"

    def test_bm25_search_with_filter(self, bm25_index: BM25Index):
        """BM25 필터 검색 p95 < 50ms."""
        durations = _timeit(
            lambda: bm25_index.search("인간중심 경영", top_k=10, edition_filter="2020-14차"),
            iterations=50,
        )
        stats = _compute_latency(durations)
        assert stats.p95 < 50.0, f"BM25 filter p95={stats.p95:.1f}ms > 50ms"


# ---------------------------------------------------------------------------
# RRF Fusion 벤치마크
# ---------------------------------------------------------------------------


class TestRRFFusionBenchmark:
    """RRF 융합 성능 벤치마크."""

    def test_rrf_fusion_latency(self):
        """RRF 융합 p95 < 5ms (20+20 hits)."""
        vec_hits = [_make_search_hit(i, "vector") for i in range(20)]
        bm25_hits = [_make_search_hit(i + 10, "bm25") for i in range(20)]

        durations = _timeit(
            lambda: _rrf_fusion(vec_hits, bm25_hits, 0.6, 60, 10),
            iterations=100,
        )
        stats = _compute_latency(durations)
        assert stats.p95 < 5.0, f"RRF p95={stats.p95:.1f}ms > 5ms"

    def test_rrf_fusion_large(self):
        """RRF 융합 대규모 (100+100 hits) p95 < 10ms."""
        vec_hits = [_make_search_hit(i, "vector") for i in range(100)]
        bm25_hits = [_make_search_hit(i + 50, "bm25") for i in range(100)]

        durations = _timeit(
            lambda: _rrf_fusion(vec_hits, bm25_hits, 0.6, 60, 20),
            iterations=50,
        )
        stats = _compute_latency(durations)
        assert stats.p95 < 10.0, f"RRF large p95={stats.p95:.1f}ms > 10ms"


# ---------------------------------------------------------------------------
# QueryCache 벤치마크
# ---------------------------------------------------------------------------


class TestQueryCacheBenchmark:
    """QueryCache 성능 벤치마크."""

    def test_cache_put_latency(self):
        """캐시 put p95 < 1ms."""
        cache = QueryCache(max_size=1000)
        durations = _timeit(
            lambda: cache.put(
                build_cache_key(f"query_{time.perf_counter_ns()}"),
                [_make_search_hit(i) for i in range(10)],
            ),
            iterations=200,
        )
        stats = _compute_latency(durations)
        assert stats.p95 < 1.0, f"Cache put p95={stats.p95:.2f}ms > 1ms"

    def test_cache_get_hit_latency(self):
        """캐시 hit p95 < 0.5ms."""
        cache = QueryCache()
        key = build_cache_key("SUPEX란 무엇인가?")
        cache.put(key, [_make_search_hit(i) for i in range(10)])

        durations = _timeit(lambda: cache.get(key), iterations=500)
        stats = _compute_latency(durations)
        assert stats.p95 < 0.5, f"Cache hit p95={stats.p95:.3f}ms > 0.5ms"

    def test_cache_get_miss_latency(self):
        """캐시 miss p95 < 0.5ms."""
        cache = QueryCache()
        durations = _timeit(
            lambda: cache.get("nonexistent_key"),
            iterations=500,
        )
        stats = _compute_latency(durations)
        assert stats.p95 < 0.5, f"Cache miss p95={stats.p95:.3f}ms > 0.5ms"

    def test_cache_key_generation_latency(self):
        """캐시 키 생성 p95 < 0.5ms."""
        durations = _timeit(
            lambda: build_cache_key(
                "SUPEX 추구 방법론은 무엇인가?",
                mode="hybrid",
                top_k=10,
                edition_filter="2020-14차",
                type_filter=["definition", "principle"],
            ),
            iterations=500,
        )
        stats = _compute_latency(durations)
        assert stats.p95 < 0.5, f"Cache key gen p95={stats.p95:.3f}ms > 0.5ms"

    def test_cache_speedup_ratio(self):
        """캐시 히트가 BM25 검색보다 빠른지 검증."""
        quotes = [_make_quote(i) for i in range(200)]
        bm25 = BM25Index.from_quotes(quotes)

        # 캐시 없이 검색
        no_cache_times = _timeit(
            lambda: bm25.search("SUPEX 추구", top_k=10),
            iterations=20,
        )

        # 캐시로 검색
        cache = QueryCache()
        key = build_cache_key("SUPEX 추구", mode="bm25", top_k=10)
        results = bm25.search("SUPEX 추구", top_k=10)
        cache.put(key, results)

        cache_times = _timeit(lambda: cache.get(key), iterations=20)

        no_cache_mean = sum(no_cache_times) / len(no_cache_times)
        cache_mean = sum(cache_times) / len(cache_times)

        # 캐시가 최소 2배 빨라야 함
        assert (
            cache_mean < no_cache_mean / 2
        ), f"Cache ({cache_mean:.3f}ms) not 2x faster than search ({no_cache_mean:.3f}ms)"


# ---------------------------------------------------------------------------
# QuoteRepository 벤치마크
# ---------------------------------------------------------------------------


class TestQuoteRepositoryBenchmark:
    """QuoteRepository 성능 벤치마크."""

    @pytest.fixture()
    def repo_with_data(self, tmp_path: Path) -> QuoteRepository:
        """500 quotes가 적재된 QuoteRepository."""
        db_path = tmp_path / "bench.db"
        init_db(db_path)
        conn = get_connection(db_path)
        repo = QuoteRepository(conn)

        quotes = [_make_quote(i) for i in range(500)]
        repo.bulk_upsert(quotes)
        conn.commit()
        return repo

    def test_count_total_latency(self, repo_with_data: QuoteRepository):
        """COUNT(*) p95 < 5ms."""
        durations = _timeit(
            lambda: repo_with_data.count_total(),
            iterations=100,
        )
        stats = _compute_latency(durations)
        assert stats.p95 < 5.0, f"count_total p95={stats.p95:.1f}ms > 5ms"

    def test_find_by_edition_latency(self, repo_with_data: QuoteRepository):
        """개정판 검색 p95 < 10ms."""
        durations = _timeit(
            lambda: repo_with_data.find_by_edition("2020-14차"),
            iterations=50,
        )
        stats = _compute_latency(durations)
        assert stats.p95 < 10.0, f"find_by_edition p95={stats.p95:.1f}ms > 10ms"

    def test_find_all_latency(self, repo_with_data: QuoteRepository):
        """전체 조회 p95 < 50ms (500건)."""
        durations = _timeit(
            lambda: repo_with_data.find_all(),
            iterations=20,
        )
        stats = _compute_latency(durations)
        assert stats.p95 < 50.0, f"find_all p95={stats.p95:.1f}ms > 50ms"

    def test_bulk_upsert_latency(self, tmp_path: Path):
        """bulk_upsert 500건 p95 < 200ms."""
        db_path = tmp_path / "bench_upsert.db"
        init_db(db_path)
        conn = get_connection(db_path)
        repo = QuoteRepository(conn)
        quotes = [_make_quote(i) for i in range(500)]

        durations = _timeit(
            lambda: repo.bulk_upsert(quotes),
            iterations=5,
        )
        stats = _compute_latency(durations)
        conn.close()
        assert stats.p95 < 200.0, f"bulk_upsert p95={stats.p95:.1f}ms > 200ms"


# ---------------------------------------------------------------------------
# MetricsCollector 벤치마크
# ---------------------------------------------------------------------------


class TestMetricsCollectorBenchmark:
    """MetricsCollector 성능 벤치마크."""

    def test_record_latency(self):
        """메트릭 기록 p95 < 0.1ms."""
        mc = MetricsCollector()
        durations = _timeit(
            lambda: mc.record("/api/search", "POST", 200, 10.0),
            iterations=1000,
        )
        stats = _compute_latency(durations)
        assert stats.p95 < 0.1, f"record p95={stats.p95:.4f}ms > 0.1ms"

    def test_get_metrics_latency(self):
        """메트릭 조회 p95 < 50ms (5000 records)."""
        mc = MetricsCollector(max_records=5000)
        for i in range(5000):
            mc.record(f"/api/ep{i%10}", "POST", 200 if i % 5 else 500, float(i))

        durations = _timeit(lambda: mc.get_metrics(), iterations=20)
        stats = _compute_latency(durations)
        assert stats.p95 < 50.0, f"get_metrics p95={stats.p95:.1f}ms > 50ms"
