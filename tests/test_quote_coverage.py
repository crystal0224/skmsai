"""quote.py 커버리지 보강 테스트.

TD-006: 미커버 라인 — _parse_year/_parse_revision fallback,
QuoteObject validation edge cases.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.quote import QuoteObject, _parse_year, _parse_revision  # noqa: E402


# ---------------------------------------------------------------------------
# _parse_year fallback (lines 48-51)
# ---------------------------------------------------------------------------


def test_parse_year_known_edition():
    """알려진 edition_id → 연도 반환."""
    assert _parse_year("2020-14차") == 2020
    assert _parse_year("1979-초판") == 1979


def test_parse_year_unknown_with_year_prefix():
    """미등록 edition_id에서 연도 추출 (line 49-50)."""
    assert _parse_year("1985-특별판") == 1985


def test_parse_year_no_year():
    """연도 없는 문자열 → ValueError (line 51)."""
    with pytest.raises(ValueError, match="연도를 추출할 수 없습니다"):
        _parse_year("unknown")


# ---------------------------------------------------------------------------
# _parse_revision fallback (lines 58-63)
# ---------------------------------------------------------------------------


def test_parse_revision_known_edition():
    """알려진 edition_id → 차수 반환."""
    assert _parse_revision("2020-14차") == 14
    assert _parse_revision("1979-초판") == 0


def test_parse_revision_unknown_with_revision():
    """미등록 edition_id에서 차수 추출 (lines 58-60)."""
    assert _parse_revision("1983-3차") == 3


def test_parse_revision_unknown_choban():
    """미등록이지만 '초판' 포함 → 0 (lines 61-62)."""
    assert _parse_revision("1975-초판") == 0


def test_parse_revision_no_match():
    """차수 추출 불가 → ValueError (line 63)."""
    with pytest.raises(ValueError, match="차수를 추출할 수 없습니다"):
        _parse_revision("unknown")


# ---------------------------------------------------------------------------
# QuoteObject validation — additional edge cases
# ---------------------------------------------------------------------------


def _make_quote_kwargs(**overrides):
    """유효한 기본값 + 오버라이드."""
    text = str(overrides.get("text", "테스트 텍스트"))
    edition_id = str(overrides.get("edition_id", "2020-14차"))
    start_line = int(overrides.get("start_line", 100))
    defaults = {
        "quote_id": "2020-14차|test|narrative|001",
        "text": text,
        "edition_id": edition_id,
        "year": 2020,
        "revision_num": 14,
        "quote_type": "narrative",
        "section_path": ("테스트",),
        "start_line": start_line,
        "char_span": (0, 50),
        "token_count": 10,
        "content_hash": QuoteObject.compute_hash(text, edition_id, start_line),
    }
    defaults.update(overrides)
    return defaults


def test_validation_empty_edition_id():
    """빈 edition_id → ValueError (line 112)."""
    with pytest.raises(ValueError, match="edition_id"):
        QuoteObject(**_make_quote_kwargs(edition_id=""))


def test_validation_revision_num_negative():
    """revision_num < 0 → ValueError (line 116)."""
    with pytest.raises(ValueError, match="revision_num"):
        QuoteObject(**_make_quote_kwargs(revision_num=-1))


def test_validation_char_span_wrong_length():
    """char_span 길이 != 2 → ValueError (line 122)."""
    with pytest.raises(ValueError, match="char_span"):
        QuoteObject(**_make_quote_kwargs(char_span=(0, 10, 20)))
