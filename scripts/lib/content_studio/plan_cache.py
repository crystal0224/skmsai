"""Plan Cache — 동일 topic+options 조합에 대한 24h TTL 캐시.

CC-03: ContentPlan 캐싱으로 LLM 호출 절약.

동일한 content_type + topic + options 조합이 반복 요청될 때,
캐시된 ContentPlan을 반환하여 불필요한 LLM 호출을 방지한다.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from scripts.lib.content_studio.models import ContentOptions, ContentPlan

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models (frozen)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CacheEntry:
    """캐시 엔트리 — 불변.

    Attributes:
        plan: 캐시된 ContentPlan.
        created_at: 생성 시각 (epoch seconds).
        cache_key: SHA256 해시 키.
    """

    plan: ContentPlan
    created_at: float
    cache_key: str


@dataclass(frozen=True)
class CacheStats:
    """캐시 통계 — 불변.

    Attributes:
        hits: 캐시 히트 수.
        misses: 캐시 미스 수.
        evictions: 퇴거(eviction) 수.
        size: 현재 캐시 엔트리 수.
        hit_rate: 히트율 (0.0 ~ 1.0).
    """

    hits: int
    misses: int
    evictions: int
    size: int
    hit_rate: float


# ---------------------------------------------------------------------------
# PlanCache
# ---------------------------------------------------------------------------


class PlanCache:
    """ContentPlan 캐시 — thread-safe, TTL 기반 만료, LRU 퇴거.

    Args:
        ttl_seconds: 캐시 TTL (기본 86400초 = 24시간).
        max_entries: 최대 캐시 엔트리 수 (기본 100).
    """

    def __init__(
        self,
        ttl_seconds: float = 86400,
        max_entries: int = 100,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds는 양수여야 합니다: {ttl_seconds}")
        if max_entries < 1:
            raise ValueError(f"max_entries는 1 이상이어야 합니다: {max_entries}")

        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    # -----------------------------------------------------------------------
    # Cache key
    # -----------------------------------------------------------------------

    @staticmethod
    def cache_key(
        content_type: str,
        topic: str,
        options: ContentOptions,
    ) -> str:
        """캐시 키 생성 — 결정론적 SHA256 해시.

        동일 입력에 대해 항상 동일한 키를 반환한다.
        options.to_dict()를 sorted JSON으로 직렬화하여 순서에 무관하게 일관된 키를 생성.

        Args:
            content_type: 콘텐츠 유형.
            topic: 주제.
            options: 생성 옵션.

        Returns:
            SHA256 hex digest 문자열.
        """
        options_json = json.dumps(options.to_dict(), sort_keys=True, ensure_ascii=False)
        raw = f"{content_type}:{topic}:{options_json}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # -----------------------------------------------------------------------
    # CRUD
    # -----------------------------------------------------------------------

    def get(self, key: str) -> ContentPlan | None:
        """캐시에서 plan을 조회한다.

        TTL이 만료된 엔트리는 자동 삭제 후 None을 반환한다.

        Args:
            key: 캐시 키.

        Returns:
            캐시된 ContentPlan 또는 None.
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None

            elapsed = time.time() - entry.created_at
            if elapsed >= self._ttl_seconds:
                # TTL 만료 → 삭제
                del self._cache[key]
                self._misses += 1
                logger.debug("캐시 TTL 만료: key=%s (%.0fs)", key[:12], elapsed)
                return None

            self._hits += 1
            logger.debug("캐시 히트: key=%s", key[:12])
            return entry.plan

    def put(self, key: str, plan: ContentPlan) -> None:
        """캐시에 plan을 저장한다.

        max_entries 초과 시 가장 오래된 엔트리를 퇴거한다.

        Args:
            key: 캐시 키.
            plan: 저장할 ContentPlan.
        """
        now = time.time()
        new_entry = CacheEntry(plan=plan, created_at=now, cache_key=key)

        with self._lock:
            # 이미 존재하면 갱신
            self._cache[key] = new_entry

            # max_entries 초과 시 가장 오래된 엔트리 퇴거
            while len(self._cache) > self._max_entries:
                oldest_key = min(
                    self._cache,
                    key=lambda k: self._cache[k].created_at,
                )
                del self._cache[oldest_key]
                self._evictions += 1
                logger.debug("캐시 퇴거: key=%s", oldest_key[:12])

    def invalidate(self, key: str) -> bool:
        """특정 캐시 엔트리를 삭제한다.

        Args:
            key: 삭제할 캐시 키.

        Returns:
            삭제 성공 여부.
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """모든 캐시 엔트리를 삭제한다."""
        with self._lock:
            self._cache.clear()
            logger.debug("캐시 전체 삭제")

    # -----------------------------------------------------------------------
    # Stats
    # -----------------------------------------------------------------------

    def stats(self) -> CacheStats:
        """캐시 통계를 반환한다.

        Returns:
            CacheStats (hits, misses, evictions, size, hit_rate).
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return CacheStats(
                hits=self._hits,
                misses=self._misses,
                evictions=self._evictions,
                size=len(self._cache),
                hit_rate=hit_rate,
            )

    # -----------------------------------------------------------------------
    # Properties
    # -----------------------------------------------------------------------

    @property
    def ttl_seconds(self) -> float:
        return self._ttl_seconds

    @property
    def max_entries(self) -> int:
        return self._max_entries
