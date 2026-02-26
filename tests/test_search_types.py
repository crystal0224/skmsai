"""SearchHit 타입 테스트.

PR-011: 불변성, 필드 타입 검증.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.search_types import SearchHit  # noqa: E402


def _make_search_hit(**overrides) -> SearchHit:
    """유효한 기본값으로 SearchHit를 생성한다."""
    defaults = {
        "quote_id": "2020-14차|VWBE|narrative|001",
        "text": "테스트 텍스트",
        "score": 0.85,
        "edition_id": "2020-14차",
        "year": 2020,
        "revision_num": 14,
        "quote_type": "narrative",
        "section_path": ("VWBE Culture",),
        "source": "vector",
        "content_hash": "a" * 64,
        "quality_flags": (),
    }
    defaults.update(overrides)
    return SearchHit(**defaults)


def test_search_hit_is_frozen():
    """SearchHit는 불변이다."""
    hit = _make_search_hit()
    with pytest.raises(AttributeError):
        hit.score = 0.99  # type: ignore[misc]


def test_search_hit_section_path_is_tuple():
    """section_path는 tuple이다."""
    hit = _make_search_hit(section_path=("기업관", "1. 인간중심의 경영"))
    assert isinstance(hit.section_path, tuple)
    assert len(hit.section_path) == 2


def test_search_hit_quality_flags_is_tuple():
    """quality_flags는 tuple이다."""
    hit = _make_search_hit(quality_flags=("ocr_error",))
    assert isinstance(hit.quality_flags, tuple)
    assert hit.quality_flags == ("ocr_error",)


def test_search_hit_fields():
    """모든 필드가 올바르게 설정된다."""
    hit = _make_search_hit(
        score=0.92,
        source="hybrid",
        year=1979,
    )
    assert hit.score == 0.92
    assert hit.source == "hybrid"
    assert hit.year == 1979
