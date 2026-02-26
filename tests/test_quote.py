#!/usr/bin/env python3
"""lib/quote.py 단위 테스트 (QuoteObject 모델).

Usage:
    python -m pytest tests/test_quote.py
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

# Ensure scripts/ is on sys.path
_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPT_DIR))

from lib.quote import QuoteObject, VALID_QUOTE_TYPES  # noqa: E402

import pytest  # noqa: E402


# ---------------------------------------------------------------------------
# Helper — sensible defaults for QuoteObject construction
# ---------------------------------------------------------------------------

_DEFAULT_TEXT = "인간은 기업의 가장 중요한 자산이다."
_DEFAULT_EDITION = "1979-초판"
_DEFAULT_START_LINE = 42


def _make_quote(**overrides: object) -> QuoteObject:
    """유효한 기본값으로 QuoteObject를 생성하고, overrides로 특정 필드를 덮어쓴다."""
    defaults: dict[str, object] = {
        "quote_id": "1979-초판|기업관|narrative|001",
        "text": _DEFAULT_TEXT,
        "edition_id": _DEFAULT_EDITION,
        "year": 1979,
        "revision_num": 0,
        "quote_type": "narrative",
        "section_path": ("기업관", "1. 인간중심의 경영"),
        "start_line": _DEFAULT_START_LINE,
        "char_span": (0, 50),
        "token_count": 12,
        "content_hash": QuoteObject.compute_hash(
            str(overrides.get("text", _DEFAULT_TEXT)),
            str(overrides.get("edition_id", _DEFAULT_EDITION)),
            int(overrides.get("start_line", _DEFAULT_START_LINE)),
        ),
        "quality_flags": (),
        "is_definition": False,
    }
    defaults.update(overrides)
    return QuoteObject(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. 생성 / 속성 접근
# ---------------------------------------------------------------------------


def test_create_valid_quote():
    """유효한 인자로 QuoteObject를 생성하고 모든 속성을 검증한다."""
    q = _make_quote()

    assert q.quote_id == "1979-초판|기업관|narrative|001"
    assert q.text == _DEFAULT_TEXT
    assert q.edition_id == "1979-초판"
    assert q.year == 1979
    assert q.revision_num == 0
    assert q.quote_type == "narrative"
    assert q.section_path == ("기업관", "1. 인간중심의 경영")
    assert q.start_line == 42
    assert q.char_span == (0, 50)
    assert q.token_count == 12
    assert len(q.content_hash) == 64
    assert q.quality_flags == ()
    assert q.is_definition is False


# ---------------------------------------------------------------------------
# 2. 불변성 (frozen dataclass)
# ---------------------------------------------------------------------------


def test_frozen_immutability():
    """frozen dataclass이므로 필드 변경 시 FrozenInstanceError가 발생한다."""
    q = _make_quote()

    with pytest.raises(dataclasses.FrozenInstanceError):
        q.text = "다른 텍스트"  # type: ignore[misc]

    with pytest.raises(dataclasses.FrozenInstanceError):
        q.year = 2020  # type: ignore[misc]

    with pytest.raises(dataclasses.FrozenInstanceError):
        q.quote_type = "definition"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 3–6. compute_hash 결정론성/차별성
# ---------------------------------------------------------------------------


def test_compute_hash_deterministic():
    """동일 입력 → 동일 해시 (멱등성)."""
    h1 = QuoteObject.compute_hash("텍스트", "1979-초판", 10)
    h2 = QuoteObject.compute_hash("텍스트", "1979-초판", 10)
    assert h1 == h2
    assert len(h1) == 64


def test_compute_hash_different_text():
    """텍스트가 다르면 해시가 달라야 한다."""
    h1 = QuoteObject.compute_hash("텍스트A", "1979-초판", 10)
    h2 = QuoteObject.compute_hash("텍스트B", "1979-초판", 10)
    assert h1 != h2


def test_compute_hash_different_edition():
    """edition_id가 다르면 해시가 달라야 한다."""
    h1 = QuoteObject.compute_hash("동일", "1979-초판", 10)
    h2 = QuoteObject.compute_hash("동일", "2020-14차", 10)
    assert h1 != h2


def test_compute_hash_different_line():
    """start_line이 다르면 해시가 달라야 한다."""
    h1 = QuoteObject.compute_hash("동일", "1979-초판", 10)
    h2 = QuoteObject.compute_hash("동일", "1979-초판", 20)
    assert h1 != h2


# ---------------------------------------------------------------------------
# 7. to_dict 라운드트립
# ---------------------------------------------------------------------------


def test_to_dict_roundtrip():
    """to_dict()가 올바른 키를 반환하고, tuple은 list로 변환된다."""
    q = _make_quote(
        section_path=("기업관", "2. 합리적 경영"),
        quality_flags=("ocr_artifact",),
    )
    d = q.to_dict()

    expected_keys = {
        "quote_id",
        "text",
        "edition_id",
        "year",
        "revision_num",
        "quote_type",
        "section_path",
        "start_line",
        "char_span",
        "token_count",
        "content_hash",
        "quality_flags",
        "is_definition",
    }
    assert set(d.keys()) == expected_keys

    # tuple → list 변환 확인
    assert isinstance(d["section_path"], list)
    assert d["section_path"] == ["기업관", "2. 합리적 경영"]
    assert isinstance(d["char_span"], list)
    assert d["char_span"] == [0, 50]
    assert isinstance(d["quality_flags"], list)
    assert d["quality_flags"] == ["ocr_artifact"]

    # 원본 값 보존
    assert d["quote_id"] == q.quote_id
    assert d["text"] == q.text
    assert d["year"] == q.year
    assert d["is_definition"] is False


# ---------------------------------------------------------------------------
# 8–11. from_legacy
# ---------------------------------------------------------------------------


def _make_legacy_record(**overrides: object) -> dict:
    """기본 legacy record를 생성한다."""
    text = str(overrides.get("text", _DEFAULT_TEXT))
    edition_id = str(overrides.get("edition_id", "1979-초판"))
    start_line = int(overrides.get("start_line", 42))
    defaults: dict[str, object] = {
        "quote_id": "1979-초판|기업관|narrative|001",
        "text": text,
        "edition_id": edition_id,
        "type": "narrative",
        "section_path": ["기업관", "1. 인간중심의 경영"],
        "start_line": start_line,
        "char_span": [0, 50],
        "token_count": 12,
        "sha256": QuoteObject.compute_hash(text, edition_id, start_line),
        "quality_flags": [],
    }
    defaults.update(overrides)
    return defaults


def test_from_legacy_basic():
    """legacy record → QuoteObject 변환 시 모든 필드가 올바르게 매핑된다."""
    rec = _make_legacy_record()
    q = QuoteObject.from_legacy(rec)

    assert q.quote_id == rec["quote_id"]
    assert q.text == rec["text"]
    assert q.edition_id == "1979-초판"
    assert q.year == 1979
    assert q.revision_num == 0
    assert q.quote_type == "narrative"
    assert q.section_path == ("기업관", "1. 인간중심의 경영")
    assert q.start_line == 42
    assert q.char_span == (0, 50)
    assert q.token_count == 12
    assert q.content_hash == rec["sha256"]
    assert q.quality_flags == ()
    assert q.is_definition is False


def test_from_legacy_type_to_is_definition():
    """type='definition' → is_definition=True."""
    rec = _make_legacy_record(type="definition")
    q = QuoteObject.from_legacy(rec)

    assert q.quote_type == "definition"
    assert q.is_definition is True


def test_from_legacy_non_definition():
    """type='narrative' → is_definition=False."""
    rec = _make_legacy_record(type="narrative")
    q = QuoteObject.from_legacy(rec)

    assert q.quote_type == "narrative"
    assert q.is_definition is False


def test_from_legacy_all_editions():
    """12개 알려진 edition_id에 대해 year와 revision_num이 올바르게 파싱된다."""
    expected = {
        "1979-초판": (1979, 0),
        "1981-1차": (1981, 1),
        "1988-5차": (1988, 5),
        "1989-6차": (1989, 6),
        "1990-7차": (1990, 7),
        "1995-8차": (1995, 8),
        "1997-9차": (1997, 9),
        "1998-10차": (1998, 10),
        "2004-11차": (2004, 11),
        "2008-12차": (2008, 12),
        "2016-13차": (2016, 13),
        "2020-14차": (2020, 14),
    }

    for edition_id, (exp_year, exp_rev) in expected.items():
        rec = _make_legacy_record(edition_id=edition_id)
        q = QuoteObject.from_legacy(rec)
        assert q.year == exp_year, f"{edition_id}: year={q.year}, expected={exp_year}"
        assert (
            q.revision_num == exp_rev
        ), f"{edition_id}: revision_num={q.revision_num}, expected={exp_rev}"


# ---------------------------------------------------------------------------
# 12–18. 검증 (Validation)
# ---------------------------------------------------------------------------


def test_validation_empty_quote_id():
    """빈 quote_id → ValueError."""
    with pytest.raises(ValueError, match="quote_id"):
        _make_quote(quote_id="")


def test_validation_empty_text():
    """빈 text → ValueError."""
    with pytest.raises(ValueError, match="text"):
        _make_quote(text="")


def test_validation_invalid_year():
    """year=1900 → ValueError (범위 초과)."""
    with pytest.raises(ValueError, match="year"):
        _make_quote(year=1900)


def test_validation_invalid_type():
    """유효하지 않은 quote_type → ValueError."""
    with pytest.raises(ValueError, match="quote_type"):
        _make_quote(quote_type="invalid")


def test_validation_invalid_start_line():
    """start_line=0 → ValueError."""
    with pytest.raises(ValueError, match="start_line"):
        _make_quote(start_line=0)


def test_validation_invalid_char_span():
    """char_span의 end < start → ValueError."""
    with pytest.raises(ValueError, match="char_span"):
        _make_quote(char_span=(50, 10))


def test_validation_invalid_content_hash():
    """64자가 아닌 content_hash → ValueError."""
    with pytest.raises(ValueError, match="content_hash"):
        _make_quote(content_hash="abc123")


# ---------------------------------------------------------------------------
# 19–20. 컬렉션 불변성 (tuple 보장)
# ---------------------------------------------------------------------------


def test_quality_flags_immutable():
    """quality_flags는 tuple이어야 한다 (list 아님)."""
    q = _make_quote(quality_flags=("ocr_artifact", "short_text"))
    assert isinstance(q.quality_flags, tuple)
    assert q.quality_flags == ("ocr_artifact", "short_text")


def test_section_path_immutable():
    """section_path는 tuple이어야 한다 (list 아님)."""
    q = _make_quote(section_path=("기업관", "1. 인간중심의 경영", "가. 경영 이념"))
    assert isinstance(q.section_path, tuple)
    assert len(q.section_path) == 3


# ---------------------------------------------------------------------------
# 21. from_db_row
# ---------------------------------------------------------------------------


def test_from_db_row():
    """DB 행(dict)에서 QuoteObject를 복원한다 (section_path/quality_flags는 JSON 문자열)."""
    content_hash = QuoteObject.compute_hash(_DEFAULT_TEXT, "2020-14차", 100)
    row = {
        "quote_id": "2020-14차|VWBE|definition|005",
        "text": _DEFAULT_TEXT,
        "edition_id": "2020-14차",
        "year": 2020,
        "revision_num": 14,
        "quote_type": "definition",
        "section_path": '["VWBE Culture", "자발적 두뇌활용"]',
        "start_line": 100,
        "char_span_start": 10,
        "char_span_end": 60,
        "token_count": 15,
        "content_hash": content_hash,
        "quality_flags": '["ocr_artifact"]',
        "is_definition": 1,
    }

    q = QuoteObject.from_db_row(row)

    assert q.quote_id == "2020-14차|VWBE|definition|005"
    assert q.text == _DEFAULT_TEXT
    assert q.edition_id == "2020-14차"
    assert q.year == 2020
    assert q.revision_num == 14
    assert q.quote_type == "definition"
    assert q.section_path == ("VWBE Culture", "자발적 두뇌활용")
    assert isinstance(q.section_path, tuple)
    assert q.start_line == 100
    assert q.char_span == (10, 60)
    assert q.token_count == 15
    assert q.content_hash == content_hash
    assert q.quality_flags == ("ocr_artifact",)
    assert isinstance(q.quality_flags, tuple)
    assert q.is_definition is True


# ---------------------------------------------------------------------------
# 22. from_legacy 필수 키 누락 검증
# ---------------------------------------------------------------------------


def test_from_legacy_missing_required_key():
    """필수 키가 누락된 legacy record → ValueError."""
    rec = _make_legacy_record()
    del rec["text"]
    with pytest.raises(ValueError, match="필수 필드"):
        QuoteObject.from_legacy(rec)
