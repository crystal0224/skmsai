"""search_service.py 커버리지 보강 테스트.

TD-006: 미커버 라인 — _build_where 함수 (lines 249-263),
_raw_hit_to_search_hit JSONDecodeError (lines 281-284, 290-293).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import MappingProxyType

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.search_service import (  # noqa: E402
    _build_where,
    _raw_hit_to_search_hit,
)
from scripts.lib.vector_store import RawVectorHit  # noqa: E402


# ---------------------------------------------------------------------------
# _build_where (lines 249-263)
# ---------------------------------------------------------------------------


def test_build_where_no_filters():
    """필터 없으면 None."""
    assert _build_where(None, None) is None


def test_build_where_edition_only():
    """edition_filter만 설정."""
    result = _build_where("2020-14차", None)
    assert result == {"edition_id": {"$eq": "2020-14차"}}


def test_build_where_single_type():
    """type_filter 단일 항목."""
    result = _build_where(None, ["definition"])
    assert result == {"type": {"$eq": "definition"}}


def test_build_where_multiple_types():
    """type_filter 복수 항목."""
    result = _build_where(None, ["definition", "principle"])
    assert result == {"type": {"$in": ["definition", "principle"]}}


def test_build_where_both_filters():
    """edition + type 필터 → $and 조건."""
    result = _build_where("2020-14차", ["definition"])
    assert "$and" in result
    assert len(result["$and"]) == 2


# ---------------------------------------------------------------------------
# _raw_hit_to_search_hit — JSONDecodeError branches (lines 281-284, 290-293)
# ---------------------------------------------------------------------------


def test_raw_hit_section_path_json_decode_error():
    """section_path가 잘못된 JSON → 빈 리스트 (lines 281-282)."""
    hit = RawVectorHit(
        id="q1",
        document="텍스트",
        distance=0.1,
        metadata={
            "edition_id": "2020-14차",
            "type": "definition",
            "section_path": "invalid json{",
            "quality_flags": "[]",
        },
    )
    result = _raw_hit_to_search_hit(hit, 0.9)
    assert result.section_path == ()


def test_raw_hit_section_path_non_string():
    """section_path가 이미 리스트인 경우 (lines 283-284)."""
    hit = RawVectorHit(
        id="q1",
        document="텍스트",
        distance=0.1,
        metadata={
            "edition_id": "2020-14차",
            "type": "definition",
            "section_path": ["인사관리", "기본"],
            "quality_flags": "[]",
        },
    )
    result = _raw_hit_to_search_hit(hit, 0.9)
    assert result.section_path == ("인사관리", "기본")


def test_raw_hit_quality_flags_json_decode_error():
    """quality_flags가 잘못된 JSON → 빈 리스트 (lines 290-291)."""
    hit = RawVectorHit(
        id="q1",
        document="텍스트",
        distance=0.1,
        metadata={
            "edition_id": "2020-14차",
            "type": "definition",
            "section_path": "[]",
            "quality_flags": "not valid json",
        },
    )
    result = _raw_hit_to_search_hit(hit, 0.9)
    assert result.quality_flags == ()


def test_raw_hit_quality_flags_non_string():
    """quality_flags가 이미 리스트인 경우 (lines 292-293)."""
    hit = RawVectorHit(
        id="q1",
        document="텍스트",
        distance=0.1,
        metadata={
            "edition_id": "2020-14차",
            "type": "definition",
            "section_path": "[]",
            "quality_flags": ["ocr_error"],
        },
    )
    result = _raw_hit_to_search_hit(hit, 0.9)
    assert result.quality_flags == ("ocr_error",)


def test_raw_hit_quality_flags_empty_non_string():
    """quality_flags가 None일 때 (line 293 — falsy non-string)."""
    hit = RawVectorHit(
        id="q1",
        document="텍스트",
        distance=0.1,
        metadata={
            "edition_id": "2020-14차",
            "type": "definition",
            "section_path": "[]",
            "quality_flags": None,
        },
    )
    result = _raw_hit_to_search_hit(hit, 0.9)
    assert result.quality_flags == ()


def test_raw_hit_section_path_empty_non_string():
    """section_path가 None일 때 (line 284 — falsy non-string)."""
    hit = RawVectorHit(
        id="q1",
        document="텍스트",
        distance=0.1,
        metadata={
            "edition_id": "2020-14차",
            "type": "definition",
            "section_path": None,
            "quality_flags": "[]",
        },
    )
    result = _raw_hit_to_search_hit(hit, 0.9)
    assert result.section_path == ()


def test_raw_hit_edition_id_no_year():
    """edition_id에서 연도 추출 불가 → year=0."""
    hit = RawVectorHit(
        id="q1",
        document="텍스트",
        distance=0.1,
        metadata={
            "edition_id": "unknown",
            "type": "narrative",
            "section_path": "[]",
            "quality_flags": "[]",
        },
    )
    result = _raw_hit_to_search_hit(hit, 0.5)
    assert result.year == 0
    assert result.revision_num == 0
