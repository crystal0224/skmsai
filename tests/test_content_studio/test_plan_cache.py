"""PlanCache 테스트 — CC-03: Plan 캐싱 (동일 topic+options → 24h TTL).

캐시 키 결정론성, TTL 만료, 최대 엔트리 퇴거, 무효화, 통계, 스레드 안전성,
그리고 ContentStudio 오케스트레이터와의 통합을 검증한다.
"""
from __future__ import annotations

import threading
import time
from unittest.mock import AsyncMock, patch

import pytest

from scripts.lib.content_studio import ContentStudio, PlanCache
from scripts.lib.content_studio.models import (
    ContentOptions,
    ContentRequest,
    LecturePlan,
    SlidePlan,
    CardNewsPlan,
    CardPlan,
    WorkshopPlan,
    WorkshopPhase,
)
from scripts.lib.content_studio.plan_cache import CacheEntry, CacheStats
from scripts.lib.content_studio.planner import ContentPlanner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_lecture(**overrides: object) -> LecturePlan:
    defaults: dict = {
        "title": "SUPEX 추구의 변천사",
        "subtitle": "30분 강의",
        "duration_min": 30,
        "slides": (
            SlidePlan(index=1, title="소개", layout="title_only"),
            SlidePlan(index=2, title="본론", layout="title_content"),
        ),
        "learning_objectives": ("목표 1", "목표 2"),
    }
    defaults.update(overrides)
    return LecturePlan(**defaults)


def _make_card_news(**overrides: object) -> CardNewsPlan:
    defaults: dict = {
        "title": "VWBE 문화",
        "total_cards": 2,
        "cards": (
            CardPlan(index=1, headline="카드1", body="본문1"),
            CardPlan(index=2, headline="카드2", body="본문2"),
        ),
    }
    defaults.update(overrides)
    return CardNewsPlan(**defaults)


def _default_options() -> ContentOptions:
    return ContentOptions()


def _custom_options(**overrides: object) -> ContentOptions:
    defaults: dict = {
        "duration_min": 45,
        "num_items": 10,
        "edition_filter": "2020-14차",
        "style": "academic",
        "language": "en",
        "include_quiz": True,
        "include_speaker_notes": False,
    }
    defaults.update(overrides)
    return ContentOptions(**defaults)


# ---------------------------------------------------------------------------
# CacheEntry / CacheStats frozen dataclass 테스트
# ---------------------------------------------------------------------------


class TestCacheEntry:
    def test_frozen(self) -> None:
        plan = _make_lecture()
        entry = CacheEntry(plan=plan, created_at=1000.0, cache_key="abc123")
        with pytest.raises(AttributeError):
            entry.plan = _make_lecture(title="변경")  # type: ignore[misc]

    def test_attributes(self) -> None:
        plan = _make_lecture()
        entry = CacheEntry(plan=plan, created_at=1234.5, cache_key="key-1")
        assert entry.plan is plan
        assert entry.created_at == 1234.5
        assert entry.cache_key == "key-1"


class TestCacheStats:
    def test_frozen(self) -> None:
        stats = CacheStats(hits=10, misses=5, evictions=2, size=8, hit_rate=0.67)
        with pytest.raises(AttributeError):
            stats.hits = 20  # type: ignore[misc]

    def test_attributes(self) -> None:
        stats = CacheStats(hits=10, misses=5, evictions=2, size=8, hit_rate=0.67)
        assert stats.hits == 10
        assert stats.misses == 5
        assert stats.evictions == 2
        assert stats.size == 8
        assert stats.hit_rate == pytest.approx(0.67)


# ---------------------------------------------------------------------------
# PlanCache.cache_key 테스트
# ---------------------------------------------------------------------------


class TestCacheKey:
    def test_deterministic(self) -> None:
        """동일 입력 → 동일 키."""
        opts = _default_options()
        key1 = PlanCache.cache_key("lecture", "SUPEX", opts)
        key2 = PlanCache.cache_key("lecture", "SUPEX", opts)
        assert key1 == key2

    def test_different_content_type(self) -> None:
        opts = _default_options()
        key_lecture = PlanCache.cache_key("lecture", "SUPEX", opts)
        key_quiz = PlanCache.cache_key("quiz", "SUPEX", opts)
        assert key_lecture != key_quiz

    def test_different_topic(self) -> None:
        opts = _default_options()
        key1 = PlanCache.cache_key("lecture", "SUPEX", opts)
        key2 = PlanCache.cache_key("lecture", "VWBE 문화", opts)
        assert key1 != key2

    def test_different_options(self) -> None:
        opts1 = _default_options()
        opts2 = _custom_options()
        key1 = PlanCache.cache_key("lecture", "SUPEX", opts1)
        key2 = PlanCache.cache_key("lecture", "SUPEX", opts2)
        assert key1 != key2

    def test_sha256_format(self) -> None:
        key = PlanCache.cache_key("lecture", "SUPEX", _default_options())
        assert len(key) == 64  # SHA256 hex digest
        assert all(c in "0123456789abcdef" for c in key)

    def test_korean_topic(self) -> None:
        """한국어 주제도 결정론적 키 생성."""
        opts = _default_options()
        key1 = PlanCache.cache_key("lecture", "인간중심의 경영 원칙", opts)
        key2 = PlanCache.cache_key("lecture", "인간중심의 경영 원칙", opts)
        assert key1 == key2


# ---------------------------------------------------------------------------
# PlanCache 기본 CRUD 테스트
# ---------------------------------------------------------------------------


class TestPlanCacheCRUD:
    def test_put_and_get(self) -> None:
        cache = PlanCache(ttl_seconds=3600)
        plan = _make_lecture()
        key = "test-key-001"

        cache.put(key, plan)
        result = cache.get(key)

        assert result is plan

    def test_get_nonexistent_returns_none(self) -> None:
        cache = PlanCache()
        assert cache.get("nonexistent") is None

    def test_put_overwrites_existing(self) -> None:
        cache = PlanCache()
        plan1 = _make_lecture(title="첫 번째")
        plan2 = _make_lecture(title="두 번째")
        key = "same-key"

        cache.put(key, plan1)
        cache.put(key, plan2)
        result = cache.get(key)

        assert result is plan2

    def test_different_plan_types(self) -> None:
        """LecturePlan, CardNewsPlan 등 다양한 타입 캐싱."""
        cache = PlanCache()
        lecture = _make_lecture()
        card_news = _make_card_news()

        cache.put("lecture-key", lecture)
        cache.put("card-news-key", card_news)

        assert cache.get("lecture-key") is lecture
        assert cache.get("card-news-key") is card_news


# ---------------------------------------------------------------------------
# TTL 만료 테스트
# ---------------------------------------------------------------------------


class TestTTLExpiry:
    def test_expired_entry_returns_none(self) -> None:
        cache = PlanCache(ttl_seconds=0.1)  # 100ms TTL
        plan = _make_lecture()
        key = "ttl-test"

        cache.put(key, plan)
        time.sleep(0.15)  # TTL 초과 대기
        result = cache.get(key)

        assert result is None

    def test_valid_entry_returns_plan(self) -> None:
        cache = PlanCache(ttl_seconds=10)
        plan = _make_lecture()
        key = "ttl-valid"

        cache.put(key, plan)
        result = cache.get(key)

        assert result is plan

    def test_expired_entry_is_removed(self) -> None:
        """만료된 엔트리 조회 후 캐시 사이즈 감소."""
        cache = PlanCache(ttl_seconds=0.1)
        plan = _make_lecture()
        key = "ttl-remove"

        cache.put(key, plan)
        assert cache.stats().size == 1

        time.sleep(0.15)
        cache.get(key)  # triggers removal
        assert cache.stats().size == 0


# ---------------------------------------------------------------------------
# 최대 엔트리 퇴거 테스트
# ---------------------------------------------------------------------------


class TestMaxEntriesEviction:
    def test_evicts_oldest_when_full(self) -> None:
        cache = PlanCache(max_entries=3)

        plans = [_make_lecture(title=f"강의 {i}") for i in range(4)]

        # 시간 차이를 두고 삽입
        for i, plan in enumerate(plans[:3]):
            cache.put(f"key-{i}", plan)

        assert cache.stats().size == 3
        assert cache.stats().evictions == 0

        # 4번째 삽입 → 가장 오래된 key-0 퇴거
        cache.put("key-3", plans[3])

        assert cache.stats().size == 3
        assert cache.stats().evictions == 1
        assert cache.get("key-0") is None  # 퇴거됨
        assert cache.get("key-3") is plans[3]  # 신규

    def test_evicts_multiple_if_needed(self) -> None:
        """max_entries=2에 이미 2개 있는 상태에서 1개 추가 → 1개 퇴거."""
        cache = PlanCache(max_entries=2)

        cache.put("a", _make_lecture(title="A"))
        cache.put("b", _make_lecture(title="B"))
        cache.put("c", _make_lecture(title="C"))

        assert cache.stats().size == 2
        assert cache.stats().evictions == 1


# ---------------------------------------------------------------------------
# invalidate / clear 테스트
# ---------------------------------------------------------------------------


class TestInvalidateAndClear:
    def test_invalidate_existing(self) -> None:
        cache = PlanCache()
        cache.put("key-1", _make_lecture())

        result = cache.invalidate("key-1")
        assert result is True
        assert cache.get("key-1") is None

    def test_invalidate_nonexistent(self) -> None:
        cache = PlanCache()
        result = cache.invalidate("nonexistent")
        assert result is False

    def test_clear(self) -> None:
        cache = PlanCache()
        for i in range(5):
            cache.put(f"key-{i}", _make_lecture(title=f"강의 {i}"))

        assert cache.stats().size == 5
        cache.clear()
        assert cache.stats().size == 0

    def test_clear_empty_cache(self) -> None:
        cache = PlanCache()
        cache.clear()  # no error
        assert cache.stats().size == 0


# ---------------------------------------------------------------------------
# 통계 추적 테스트
# ---------------------------------------------------------------------------


class TestStatsTracking:
    def test_initial_stats(self) -> None:
        cache = PlanCache()
        stats = cache.stats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.evictions == 0
        assert stats.size == 0
        assert stats.hit_rate == 0.0

    def test_hit_tracking(self) -> None:
        cache = PlanCache()
        cache.put("key", _make_lecture())

        cache.get("key")  # hit
        cache.get("key")  # hit

        stats = cache.stats()
        assert stats.hits == 2
        assert stats.misses == 0
        assert stats.hit_rate == pytest.approx(1.0)

    def test_miss_tracking(self) -> None:
        cache = PlanCache()

        cache.get("missing-1")  # miss
        cache.get("missing-2")  # miss

        stats = cache.stats()
        assert stats.hits == 0
        assert stats.misses == 2
        assert stats.hit_rate == 0.0

    def test_mixed_hit_miss(self) -> None:
        cache = PlanCache()
        cache.put("exists", _make_lecture())

        cache.get("exists")  # hit
        cache.get("missing")  # miss
        cache.get("exists")  # hit
        cache.get("also-missing")  # miss

        stats = cache.stats()
        assert stats.hits == 2
        assert stats.misses == 2
        assert stats.hit_rate == pytest.approx(0.5)

    def test_eviction_counting(self) -> None:
        cache = PlanCache(max_entries=1)
        cache.put("a", _make_lecture(title="A"))
        cache.put("b", _make_lecture(title="B"))  # evicts a

        assert cache.stats().evictions == 1

    def test_ttl_expiry_counts_as_miss(self) -> None:
        cache = PlanCache(ttl_seconds=0.1)
        cache.put("key", _make_lecture())

        cache.get("key")  # hit
        time.sleep(0.15)
        cache.get("key")  # miss (expired)

        stats = cache.stats()
        assert stats.hits == 1
        assert stats.misses == 1


# ---------------------------------------------------------------------------
# 스레드 안전성 테스트
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_put_and_get(self) -> None:
        """여러 스레드에서 동시에 put/get 수행해도 오류 없음."""
        cache = PlanCache(max_entries=50)
        errors: list[Exception] = []
        barrier = threading.Barrier(10)

        def worker(thread_id: int) -> None:
            try:
                barrier.wait(timeout=5)
                for i in range(20):
                    key = f"thread-{thread_id}-{i}"
                    plan = _make_lecture(title=f"Thread {thread_id} Plan {i}")
                    cache.put(key, plan)
                    result = cache.get(key)
                    # result는 plan이거나 None (퇴거됨)일 수 있음
                    if result is not None:
                        assert result.title == f"Thread {thread_id} Plan {i}"
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == [], f"Thread errors: {errors}"

    def test_concurrent_stats(self) -> None:
        """stats()도 동시 접근에 안전."""
        cache = PlanCache()
        cache.put("key", _make_lecture())
        errors: list[Exception] = []

        def reader() -> None:
            try:
                for _ in range(50):
                    stats = cache.stats()
                    assert stats.size >= 0
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert errors == []

    def test_concurrent_invalidate(self) -> None:
        """동시 invalidate도 안전."""
        cache = PlanCache()
        for i in range(20):
            cache.put(f"key-{i}", _make_lecture(title=f"Plan {i}"))
        errors: list[Exception] = []

        def invalidator(start: int) -> None:
            try:
                for i in range(start, start + 10):
                    cache.invalidate(f"key-{i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=invalidator, args=(0,)),
            threading.Thread(target=invalidator, args=(10,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert errors == []
        assert cache.stats().size == 0


# ---------------------------------------------------------------------------
# Constructor validation 테스트
# ---------------------------------------------------------------------------


class TestConstructorValidation:
    def test_invalid_ttl(self) -> None:
        with pytest.raises(ValueError, match="ttl_seconds"):
            PlanCache(ttl_seconds=0)

    def test_negative_ttl(self) -> None:
        with pytest.raises(ValueError, match="ttl_seconds"):
            PlanCache(ttl_seconds=-1)

    def test_invalid_max_entries(self) -> None:
        with pytest.raises(ValueError, match="max_entries"):
            PlanCache(max_entries=0)

    def test_properties(self) -> None:
        cache = PlanCache(ttl_seconds=3600, max_entries=50)
        assert cache.ttl_seconds == 3600
        assert cache.max_entries == 50


# ---------------------------------------------------------------------------
# ContentStudio 통합 테스트 (mock planner, cache hit → LLM 스킵)
# ---------------------------------------------------------------------------


class MockLLMClient:
    """테스트용 LLM 클라이언트."""

    def __init__(self) -> None:
        self.call_count = 0

    async def generate(self, prompt: str) -> str:
        self.call_count += 1
        return """{
            "title": "테스트 강의",
            "subtitle": "서브타이틀",
            "duration_min": 30,
            "slides": [
                {"index": 1, "title": "소개", "layout": "title_only"},
                {"index": 2, "title": "본론", "layout": "title_content"}
            ],
            "learning_objectives": ["목표1"]
        }"""


class TestCacheIntegrationWithStudio:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_llm(self) -> None:
        """캐시 히트 시 LLM 호출을 건너뛰는지 검증."""
        llm = MockLLMClient()
        plan_cache = PlanCache(ttl_seconds=3600)
        planner = ContentPlanner(llm_client=llm, config={})

        studio = ContentStudio(planner=planner, plan_cache=plan_cache)

        request = ContentRequest(
            content_type="lecture",
            topic="SUPEX 추구",
            options=ContentOptions(duration_min=30),
        )

        # 첫 번째 호출 → LLM 호출 발생
        plan1 = await studio.plan_only(request)
        assert llm.call_count == 1

        # 두 번째 호출 → 캐시 히트, LLM 호출 없음
        plan2 = await studio.plan_only(request)
        assert llm.call_count == 1  # 여전히 1

        # 동일 plan 반환
        assert plan1.title == plan2.title

        # 캐시 통계 확인
        stats = plan_cache.stats()
        assert stats.hits == 1
        assert stats.misses == 1  # 첫 조회 시 miss

    @pytest.mark.asyncio
    async def test_different_request_triggers_llm(self) -> None:
        """다른 요청은 캐시 미스 → LLM 호출."""
        llm = MockLLMClient()
        plan_cache = PlanCache(ttl_seconds=3600)
        planner = ContentPlanner(llm_client=llm, config={})

        studio = ContentStudio(planner=planner, plan_cache=plan_cache)

        request1 = ContentRequest(
            content_type="lecture",
            topic="SUPEX 추구",
            options=ContentOptions(duration_min=30),
        )
        request2 = ContentRequest(
            content_type="lecture",
            topic="VWBE 문화",
            options=ContentOptions(duration_min=30),
        )

        await studio.plan_only(request1)
        await studio.plan_only(request2)

        assert llm.call_count == 2

    @pytest.mark.asyncio
    async def test_no_cache_backward_compatible(self) -> None:
        """plan_cache=None이면 항상 LLM 호출."""
        llm = MockLLMClient()
        planner = ContentPlanner(llm_client=llm, config={})

        studio = ContentStudio(planner=planner, plan_cache=None)
        assert not studio.has_plan_cache

        request = ContentRequest(
            content_type="lecture",
            topic="SUPEX 추구",
            options=ContentOptions(duration_min=30),
        )

        await studio.plan_only(request)
        await studio.plan_only(request)

        assert llm.call_count == 2

    @pytest.mark.asyncio
    async def test_has_plan_cache_property(self) -> None:
        studio_with = ContentStudio(plan_cache=PlanCache())
        studio_without = ContentStudio(plan_cache=None)

        assert studio_with.has_plan_cache is True
        assert studio_without.has_plan_cache is False

    @pytest.mark.asyncio
    async def test_plan_cache_property_returns_instance(self) -> None:
        cache = PlanCache()
        studio = ContentStudio(plan_cache=cache)
        assert studio.plan_cache is cache
