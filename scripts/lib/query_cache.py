"""검색 쿼리 캐시.

PR-037: 동일 쿼리에 대한 검색 결과 캐싱으로 응답 시간 최적화.

Thread-safe LRU 캐시. TTL 기반 만료로 stale 데이터 방지.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Immutable types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CacheEntry:
    """캐시 항목 (불변)."""

    key: str
    value: Any
    created_at: float
    hit_count: int = 0


@dataclass(frozen=True)
class CacheStats:
    """캐시 통계 스냅샷 (불변)."""

    total_requests: int
    hits: int
    misses: int
    hit_rate: float
    size: int
    max_size: int
    evictions: int


# ---------------------------------------------------------------------------
# QueryCache
# ---------------------------------------------------------------------------


class QueryCache:
    """Thread-safe LRU 캐시 with TTL.

    동일한 쿼리+파라미터 조합에 대해 이전 결과를 캐시한다.
    TTL(Time-To-Live) 이후 항목은 자동 만료.
    """

    def __init__(
        self,
        max_size: int = 256,
        ttl_seconds: float = 300.0,
    ) -> None:
        """
        Args:
            max_size: 최대 캐시 항목 수.
            ttl_seconds: 캐시 항목 TTL (기본 5분).
        """
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._total_requests = 0

    @property
    def size(self) -> int:
        """현재 캐시 크기."""
        with self._lock:
            return len(self._cache)

    def get(self, key: str) -> tuple[bool, Any]:
        """캐시에서 값을 조회한다.

        Returns:
            (found, value) tuple. found가 False이면 value는 None.
        """
        with self._lock:
            self._total_requests += 1

            if key not in self._cache:
                self._misses += 1
                return False, None

            value, created_at = self._cache[key]

            # TTL 만료 확인
            if time.time() - created_at > self._ttl_seconds:
                del self._cache[key]
                self._misses += 1
                return False, None

            # LRU: 최근 접근으로 이동
            self._cache.move_to_end(key)
            self._hits += 1
            return True, value

    def put(self, key: str, value: Any) -> None:
        """캐시에 값을 저장한다."""
        with self._lock:
            if key in self._cache:
                # 기존 항목 갱신
                self._cache[key] = (value, time.time())
                self._cache.move_to_end(key)
                return

            # LRU eviction
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
                self._evictions += 1

            self._cache[key] = (value, time.time())

    def invalidate(self, key: str) -> bool:
        """특정 키를 무효화한다.

        Returns:
            삭제 성공 여부.
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """캐시를 전부 비운다."""
        with self._lock:
            self._cache.clear()

    def get_stats(self) -> CacheStats:
        """캐시 통계 스냅샷을 반환한다."""
        with self._lock:
            total = self._total_requests
            hits = self._hits
            misses = self._misses
            hit_rate = hits / total if total > 0 else 0.0
            return CacheStats(
                total_requests=total,
                hits=hits,
                misses=misses,
                hit_rate=round(hit_rate, 4),
                size=len(self._cache),
                max_size=self._max_size,
                evictions=self._evictions,
            )

    def reset_stats(self) -> None:
        """통계만 초기화한다 (캐시 데이터는 유지)."""
        with self._lock:
            self._hits = 0
            self._misses = 0
            self._evictions = 0
            self._total_requests = 0


# ---------------------------------------------------------------------------
# Cache key builder
# ---------------------------------------------------------------------------


def build_cache_key(
    query: str,
    *,
    mode: str = "hybrid",
    top_k: int = 5,
    edition_filter: str | None = None,
    type_filter: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """검색 파라미터로부터 캐시 키를 생성한다.

    동일한 입력은 항상 동일한 키를 반환한다 (deterministic).
    """
    key_parts = {
        "q": query,
        "m": mode,
        "k": top_k,
        "ef": edition_filter or "",
        "tf": sorted(type_filter) if type_filter else [],
    }
    if extra:
        key_parts["x"] = extra

    key_json = json.dumps(key_parts, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(key_json.encode("utf-8")).hexdigest()[:32]
