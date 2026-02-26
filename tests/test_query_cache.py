"""QueryCache 단위 테스트.

PR-037: 검색 쿼리 캐시 + 성능 최적화.
"""
from __future__ import annotations

import threading
import time

import pytest

from scripts.lib.query_cache import (
    CacheEntry,
    CacheStats,
    QueryCache,
    build_cache_key,
)


# ---------------------------------------------------------------------------
# CacheEntry (불변)
# ---------------------------------------------------------------------------


class TestCacheEntry:
    """CacheEntry frozen dataclass 테스트."""

    def test_create(self):
        entry = CacheEntry(
            key="abc123",
            value=[1, 2, 3],
            created_at=1000.0,
            hit_count=5,
        )
        assert entry.key == "abc123"
        assert entry.value == [1, 2, 3]
        assert entry.hit_count == 5

    def test_immutable(self):
        entry = CacheEntry(key="test", value="data", created_at=0.0)
        with pytest.raises(AttributeError):
            entry.key = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CacheStats (불변)
# ---------------------------------------------------------------------------


class TestCacheStats:
    """CacheStats frozen dataclass 테스트."""

    def test_create(self):
        stats = CacheStats(
            total_requests=100,
            hits=80,
            misses=20,
            hit_rate=0.8,
            size=50,
            max_size=256,
            evictions=5,
        )
        assert stats.hit_rate == 0.8
        assert stats.evictions == 5

    def test_immutable(self):
        stats = CacheStats(
            total_requests=0,
            hits=0,
            misses=0,
            hit_rate=0.0,
            size=0,
            max_size=0,
            evictions=0,
        )
        with pytest.raises(AttributeError):
            stats.hits = 10  # type: ignore[misc]


# ---------------------------------------------------------------------------
# QueryCache — basic get/put
# ---------------------------------------------------------------------------


class TestQueryCacheBasic:
    """QueryCache 기본 get/put 테스트."""

    def test_empty_cache(self):
        cache = QueryCache()
        found, value = cache.get("nonexistent")
        assert found is False
        assert value is None

    def test_put_and_get(self):
        cache = QueryCache()
        cache.put("key1", {"data": "hello"})
        found, value = cache.get("key1")
        assert found is True
        assert value == {"data": "hello"}

    def test_overwrite(self):
        cache = QueryCache()
        cache.put("key1", "old")
        cache.put("key1", "new")
        found, value = cache.get("key1")
        assert found is True
        assert value == "new"

    def test_size(self):
        cache = QueryCache()
        assert cache.size == 0
        cache.put("k1", "v1")
        assert cache.size == 1
        cache.put("k2", "v2")
        assert cache.size == 2

    def test_various_value_types(self):
        cache = QueryCache()
        cache.put("str", "hello")
        cache.put("int", 42)
        cache.put("list", [1, 2, 3])
        cache.put("dict", {"a": 1})
        cache.put("none", None)

        for key, expected in [
            ("str", "hello"),
            ("int", 42),
            ("list", [1, 2, 3]),
            ("dict", {"a": 1}),
            ("none", None),
        ]:
            found, value = cache.get(key)
            assert found is True
            assert value == expected


# ---------------------------------------------------------------------------
# QueryCache — LRU eviction
# ---------------------------------------------------------------------------


class TestQueryCacheLRU:
    """QueryCache LRU eviction 테스트."""

    def test_eviction_on_max_size(self):
        cache = QueryCache(max_size=3)
        cache.put("k1", "v1")
        cache.put("k2", "v2")
        cache.put("k3", "v3")
        assert cache.size == 3

        # 4번째 삽입 → k1 퇴출
        cache.put("k4", "v4")
        assert cache.size == 3
        found, _ = cache.get("k1")
        assert found is False
        found, _ = cache.get("k4")
        assert found is True

    def test_lru_access_prevents_eviction(self):
        cache = QueryCache(max_size=3)
        cache.put("k1", "v1")
        cache.put("k2", "v2")
        cache.put("k3", "v3")

        # k1을 접근하면 LRU에서 최신으로 이동
        cache.get("k1")

        # k4 삽입 → k2 퇴출 (가장 오래된 미접근 항목)
        cache.put("k4", "v4")
        found_k1, _ = cache.get("k1")
        found_k2, _ = cache.get("k2")
        assert found_k1 is True
        assert found_k2 is False

    def test_eviction_count(self):
        cache = QueryCache(max_size=2)
        cache.put("k1", "v1")
        cache.put("k2", "v2")
        cache.put("k3", "v3")  # k1 퇴출
        cache.put("k4", "v4")  # k2 퇴출

        stats = cache.get_stats()
        assert stats.evictions == 2


# ---------------------------------------------------------------------------
# QueryCache — TTL
# ---------------------------------------------------------------------------


class TestQueryCacheTTL:
    """QueryCache TTL 만료 테스트."""

    def test_ttl_expiry(self):
        cache = QueryCache(ttl_seconds=0.1)  # 100ms TTL
        cache.put("key", "value")

        # 즉시 조회 → 존재
        found, _ = cache.get("key")
        assert found is True

        # TTL 만료 후 → 없음
        time.sleep(0.15)
        found, _ = cache.get("key")
        assert found is False

    def test_ttl_refresh_on_put(self):
        cache = QueryCache(ttl_seconds=0.2)
        cache.put("key", "value1")
        time.sleep(0.1)

        # 갱신으로 TTL 리셋
        cache.put("key", "value2")
        time.sleep(0.15)

        # 마지막 put 기준 0.15초 < 0.2초 → 유효
        found, value = cache.get("key")
        assert found is True
        assert value == "value2"


# ---------------------------------------------------------------------------
# QueryCache — invalidate / clear
# ---------------------------------------------------------------------------


class TestQueryCacheInvalidate:
    """QueryCache invalidate/clear 테스트."""

    def test_invalidate_existing(self):
        cache = QueryCache()
        cache.put("key", "value")
        result = cache.invalidate("key")
        assert result is True
        found, _ = cache.get("key")
        assert found is False

    def test_invalidate_nonexistent(self):
        cache = QueryCache()
        result = cache.invalidate("nonexistent")
        assert result is False

    def test_clear(self):
        cache = QueryCache()
        cache.put("k1", "v1")
        cache.put("k2", "v2")
        cache.clear()
        assert cache.size == 0
        found, _ = cache.get("k1")
        assert found is False


# ---------------------------------------------------------------------------
# QueryCache — stats
# ---------------------------------------------------------------------------


class TestQueryCacheStats:
    """QueryCache 통계 테스트."""

    def test_initial_stats(self):
        cache = QueryCache(max_size=128)
        stats = cache.get_stats()
        assert stats.total_requests == 0
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.hit_rate == 0.0
        assert stats.size == 0
        assert stats.max_size == 128

    def test_stats_after_operations(self):
        cache = QueryCache()
        cache.put("k1", "v1")
        cache.get("k1")  # hit
        cache.get("k1")  # hit
        cache.get("k2")  # miss

        stats = cache.get_stats()
        assert stats.total_requests == 3
        assert stats.hits == 2
        assert stats.misses == 1
        assert stats.hit_rate == pytest.approx(0.6667, abs=0.001)

    def test_reset_stats(self):
        cache = QueryCache()
        cache.put("k1", "v1")
        cache.get("k1")
        cache.get("k2")
        cache.reset_stats()

        stats = cache.get_stats()
        assert stats.total_requests == 0
        assert stats.hits == 0
        assert stats.misses == 0
        # 캐시 데이터는 유지
        assert stats.size == 1


# ---------------------------------------------------------------------------
# QueryCache — thread safety
# ---------------------------------------------------------------------------


class TestQueryCacheThreadSafety:
    """QueryCache thread-safety 테스트."""

    def test_concurrent_put_get(self):
        cache = QueryCache(max_size=100)
        errors: list[str] = []

        def writer(thread_id: int):
            for i in range(50):
                cache.put(f"t{thread_id}_k{i}", f"v{i}")

        def reader(thread_id: int):
            for i in range(50):
                try:
                    cache.get(f"t{thread_id}_k{i}")
                except Exception as e:
                    errors.append(str(e))

        threads = []
        for t in range(4):
            threads.append(threading.Thread(target=writer, args=(t,)))
            threads.append(threading.Thread(target=reader, args=(t,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_stats(self):
        cache = QueryCache()
        stop = threading.Event()
        errors: list[str] = []

        def writer():
            for i in range(100):
                cache.put(f"k{i}", f"v{i}")

        def stats_reader():
            while not stop.is_set():
                try:
                    cache.get_stats()
                except Exception as e:
                    errors.append(str(e))

        writer_t = threading.Thread(target=writer)
        reader_t = threading.Thread(target=stats_reader)

        reader_t.start()
        writer_t.start()
        writer_t.join()
        stop.set()
        reader_t.join()

        assert len(errors) == 0


# ---------------------------------------------------------------------------
# build_cache_key
# ---------------------------------------------------------------------------


class TestBuildCacheKey:
    """build_cache_key 유틸리티 함수 테스트."""

    def test_deterministic(self):
        key1 = build_cache_key("SUPEX란 무엇인가?", mode="hybrid", top_k=5)
        key2 = build_cache_key("SUPEX란 무엇인가?", mode="hybrid", top_k=5)
        assert key1 == key2

    def test_different_query(self):
        key1 = build_cache_key("SUPEX란?")
        key2 = build_cache_key("인간중심 경영이란?")
        assert key1 != key2

    def test_different_mode(self):
        key1 = build_cache_key("query", mode="hybrid")
        key2 = build_cache_key("query", mode="vector")
        assert key1 != key2

    def test_different_top_k(self):
        key1 = build_cache_key("query", top_k=5)
        key2 = build_cache_key("query", top_k=10)
        assert key1 != key2

    def test_edition_filter(self):
        key1 = build_cache_key("query", edition_filter="2020-14차")
        key2 = build_cache_key("query", edition_filter=None)
        assert key1 != key2

    def test_type_filter_order_independent(self):
        key1 = build_cache_key("query", type_filter=["definition", "principle"])
        key2 = build_cache_key("query", type_filter=["principle", "definition"])
        assert key1 == key2

    def test_key_length(self):
        key = build_cache_key("test query")
        assert len(key) == 32  # SHA-256 truncated to 32 chars

    def test_extra_params(self):
        key1 = build_cache_key("query", extra={"alpha": 0.6})
        key2 = build_cache_key("query", extra={"alpha": 0.8})
        assert key1 != key2

    def test_korean_query(self):
        key = build_cache_key("SUPEX 추구 방법론은 무엇인가?")
        assert len(key) == 32
        # 한글 쿼리도 일관된 키 생성
        key2 = build_cache_key("SUPEX 추구 방법론은 무엇인가?")
        assert key == key2
