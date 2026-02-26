"""QuoteRepository 통합 테스트 (SQLite in-memory).

PR-009: CRUD, upsert 멱등성, CHECK 제약, 인덱스 검증.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

# 프로젝트 루트
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.db import init_db  # noqa: E402
from scripts.lib.quote import QuoteObject  # noqa: E402
from scripts.lib.quote_repository import QuoteRepository  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DEFAULT_TEXT = "SKMS는 인간중심의 경영을 지향한다."
_DEFAULT_EDITION = "2020-14차"
_DEFAULT_START_LINE = 15200


def _get_test_connection() -> sqlite3.Connection:
    """in-memory SQLite 연결 + 마이그레이션."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    # 마이그레이션 실행
    migration = _PROJECT_ROOT / "migrations" / "001_quote.sql"
    conn.executescript(migration.read_text(encoding="utf-8"))
    return conn


@pytest.fixture()
def conn():
    """테스트용 in-memory DB 연결."""
    c = _get_test_connection()
    yield c
    c.close()


@pytest.fixture()
def repo(conn):
    """QuoteRepository 인스턴스.

    Note: QuoteRepository는 commit()을 호출하지 않는다.
    테스트에서 conn.commit()을 수동 호출하거나
    autocommit 모드를 사용한다.
    """
    # in-memory DB에서는 autocommit이 자연스러움
    conn.isolation_level = None  # autocommit mode
    return QuoteRepository(conn)


def _make_quote(**overrides) -> QuoteObject:
    """유효한 기본값으로 QuoteObject를 생성한다."""
    text = str(overrides.get("text", _DEFAULT_TEXT))
    edition_id = str(overrides.get("edition_id", _DEFAULT_EDITION))
    start_line = int(overrides.get("start_line", _DEFAULT_START_LINE))
    defaults = {
        "quote_id": "2020-14차|VWBE|narrative|001",
        "text": text,
        "edition_id": edition_id,
        "year": 2020,
        "revision_num": 14,
        "quote_type": "narrative",
        "section_path": ("VWBE Culture",),
        "start_line": start_line,
        "char_span": (100, 200),
        "token_count": 20,
        "content_hash": QuoteObject.compute_hash(text, edition_id, start_line),
        "quality_flags": (),
        "is_definition": False,
    }
    defaults.update(overrides)
    return QuoteObject(**defaults)


# ---------------------------------------------------------------------------
# 1. 마이그레이션 검증
# ---------------------------------------------------------------------------


def test_migration_creates_table(conn):
    """001_quote.sql 실행 후 quotes 테이블이 존재한다."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='quotes'"
    ).fetchone()
    assert row is not None
    assert row["name"] == "quotes"


def test_migration_creates_indexes(conn):
    """5개 인덱스가 모두 생성된다."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='quotes'"
    ).fetchall()
    names = {row["name"] for row in rows}
    expected = {
        "idx_quotes_edition",
        "idx_quotes_year",
        "idx_quotes_type",
        "idx_quotes_content_hash",
        "idx_quotes_definition",
    }
    assert expected.issubset(names)


def test_migration_idempotent(conn):
    """같은 마이그레이션을 2번 실행해도 에러가 없다."""
    migration = _PROJECT_ROOT / "migrations" / "001_quote.sql"
    sql = migration.read_text(encoding="utf-8")
    conn.executescript(sql)  # 2nd run
    row = conn.execute("SELECT COUNT(*) FROM quotes").fetchone()
    assert row[0] == 0


# ---------------------------------------------------------------------------
# 2. CREATE (단건 삽입)
# ---------------------------------------------------------------------------


def test_create_single_quote(repo):
    """단건 INSERT 후 조회 가능."""
    q = _make_quote()
    result = repo.create(q)
    assert result.quote_id == q.quote_id

    found = repo.find_by_id(q.quote_id)
    assert found is not None
    assert found.text == q.text
    assert found.edition_id == q.edition_id
    assert found.year == 2020
    assert found.content_hash == q.content_hash


def test_create_duplicate_content_hash_raises(repo):
    """동일 content_hash 중복 INSERT → IntegrityError."""
    q1 = _make_quote()
    repo.create(q1)

    q2 = _make_quote(quote_id="2020-14차|VWBE|narrative|999")
    with pytest.raises(sqlite3.IntegrityError):
        repo.create(q2)


# ---------------------------------------------------------------------------
# 3. UPSERT (멱등 삽입)
# ---------------------------------------------------------------------------


def test_upsert_new_record(repo):
    """새 레코드 upsert → 삽입."""
    q = _make_quote()
    repo.upsert(q)
    assert repo.count_total() == 1


def test_upsert_duplicate_idempotent(repo):
    """동일 content_hash 재 upsert → 건너뜀 (카운트 불변)."""
    q = _make_quote()
    repo.upsert(q)
    repo.upsert(q)
    assert repo.count_total() == 1


def test_bulk_upsert(repo):
    """다건 멱등 삽입."""
    quotes = [
        _make_quote(
            quote_id=f"2020-14차|VWBE|narrative|{i:03d}",
            text=f"텍스트 {i}",
            start_line=100 + i,
        )
        for i in range(5)
    ]
    inserted = repo.bulk_upsert(quotes)
    assert inserted == 5
    assert repo.count_total() == 5

    # 재삽입 → 추가 없음 (멱등)
    inserted2 = repo.bulk_upsert(quotes)
    assert inserted2 == 0
    assert repo.count_total() == 5


# ---------------------------------------------------------------------------
# 4. READ (조회)
# ---------------------------------------------------------------------------


def _seed_multiple(repo) -> list[QuoteObject]:
    """다양한 edition/type 데이터를 시드한다."""
    quotes = [
        _make_quote(
            quote_id="1979-초판|기업관|narrative|001",
            edition_id="1979-초판",
            year=1979,
            revision_num=0,
            quote_type="narrative",
            text="초판 텍스트 1",
            start_line=10,
        ),
        _make_quote(
            quote_id="1979-초판|기업관|definition|001",
            edition_id="1979-초판",
            year=1979,
            revision_num=0,
            quote_type="definition",
            text="초판 정의 1",
            start_line=20,
            is_definition=True,
        ),
        _make_quote(
            quote_id="2020-14차|VWBE|narrative|001",
            edition_id="2020-14차",
            year=2020,
            revision_num=14,
            quote_type="narrative",
            text="14차 텍스트 1",
            start_line=15200,
        ),
        _make_quote(
            quote_id="2020-14차|VWBE|definition|001",
            edition_id="2020-14차",
            year=2020,
            revision_num=14,
            quote_type="definition",
            text="14차 정의 1",
            start_line=15220,
            is_definition=True,
        ),
        _make_quote(
            quote_id="2020-14차|VWBE|checklist|001",
            edition_id="2020-14차",
            year=2020,
            revision_num=14,
            quote_type="checklist",
            text="14차 체크리스트 1",
            start_line=15240,
        ),
    ]
    repo.bulk_upsert(quotes)
    return quotes


def test_find_by_id(repo):
    """quote_id로 단건 조회."""
    _seed_multiple(repo)
    found = repo.find_by_id("1979-초판|기업관|narrative|001")
    assert found is not None
    assert found.year == 1979


def test_find_by_id_not_found(repo):
    """존재하지 않는 quote_id → None."""
    assert repo.find_by_id("nonexistent") is None


def test_find_by_content_hash(repo):
    """content_hash로 조회."""
    q = _make_quote()
    repo.create(q)
    found = repo.find_by_content_hash(q.content_hash)
    assert found is not None
    assert found.quote_id == q.quote_id


def test_find_by_edition(repo):
    """edition_id별 조회."""
    _seed_multiple(repo)
    results = repo.find_by_edition("1979-초판")
    assert len(results) == 2
    assert all(r.edition_id == "1979-초판" for r in results)


def test_find_definitions(repo):
    """is_definition=True만 조회."""
    _seed_multiple(repo)
    defs = repo.find_definitions()
    assert len(defs) == 2
    assert all(d.is_definition for d in defs)


def test_find_by_type(repo):
    """quote_type별 조회."""
    _seed_multiple(repo)
    checklists = repo.find_by_type("checklist")
    assert len(checklists) == 1
    assert checklists[0].quote_type == "checklist"


# ---------------------------------------------------------------------------
# 5. COUNT / AGGREGATE
# ---------------------------------------------------------------------------


def test_count_total(repo):
    """전체 건수."""
    _seed_multiple(repo)
    assert repo.count_total() == 5


def test_count_by_edition(repo):
    """edition별 건수."""
    _seed_multiple(repo)
    counts = repo.count_by_edition()
    assert counts["1979-초판"] == 2
    assert counts["2020-14차"] == 3


def test_count_by_type(repo):
    """type별 건수."""
    _seed_multiple(repo)
    counts = repo.count_by_type()
    assert counts["narrative"] == 2
    assert counts["definition"] == 2
    assert counts["checklist"] == 1


# ---------------------------------------------------------------------------
# 6. DELETE
# ---------------------------------------------------------------------------


def test_delete_by_id(repo):
    """삭제 후 카운트 감소."""
    _seed_multiple(repo)
    assert repo.count_total() == 5

    deleted = repo.delete_by_id("1979-초판|기업관|narrative|001")
    assert deleted is True
    assert repo.count_total() == 4


def test_delete_nonexistent(repo):
    """존재하지 않는 ID 삭제 → False."""
    assert repo.delete_by_id("nonexistent") is False


# ---------------------------------------------------------------------------
# 7. CHECK 제약 조건 (DB 레벨)
# ---------------------------------------------------------------------------


def test_check_year_overflow(conn):
    """year=1900 → CHECK 제약 위반."""
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO quotes (
                quote_id, text, edition_id, year, revision_num,
                quote_type, section_path, start_line,
                char_span_start, char_span_end, token_count,
                content_hash, quality_flags, is_definition
            ) VALUES (
                'test', 'text', 'ed', 1900, 0,
                'narrative', '[]', 1,
                0, 10, 5,
                ?, '[]', 0
            )""",
            ("a" * 64,),
        )


def test_check_invalid_quote_type(conn):
    """유효하지 않은 quote_type → CHECK 제약 위반."""
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO quotes (
                quote_id, text, edition_id, year, revision_num,
                quote_type, section_path, start_line,
                char_span_start, char_span_end, token_count,
                content_hash, quality_flags, is_definition
            ) VALUES (
                'test', 'text', 'ed', 2020, 14,
                'INVALID_TYPE', '[]', 1,
                0, 10, 5,
                ?, '[]', 0
            )""",
            ("b" * 64,),
        )


def test_check_start_line_zero(conn):
    """start_line=0 → CHECK 제약 위반."""
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO quotes (
                quote_id, text, edition_id, year, revision_num,
                quote_type, section_path, start_line,
                char_span_start, char_span_end, token_count,
                content_hash, quality_flags, is_definition
            ) VALUES (
                'test', 'text', 'ed', 2020, 14,
                'narrative', '[]', 0,
                0, 10, 5,
                ?, '[]', 0
            )""",
            ("c" * 64,),
        )


def test_check_char_span_end_lt_start(conn):
    """char_span_end < char_span_start → CHECK 제약 위반."""
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO quotes (
                quote_id, text, edition_id, year, revision_num,
                quote_type, section_path, start_line,
                char_span_start, char_span_end, token_count,
                content_hash, quality_flags, is_definition
            ) VALUES (
                'test', 'text', 'ed', 2020, 14,
                'narrative', '[]', 1,
                50, 10, 5,
                ?, '[]', 0
            )""",
            ("d" * 64,),
        )


# ---------------------------------------------------------------------------
# 8. 불변성 — 반환된 QuoteObject는 frozen
# ---------------------------------------------------------------------------


def test_returned_quote_is_frozen(repo):
    """Repository에서 반환된 QuoteObject는 불변이다."""
    import dataclasses

    q = _make_quote()
    repo.create(q)
    found = repo.find_by_id(q.quote_id)
    assert found is not None

    with pytest.raises(dataclasses.FrozenInstanceError):
        found.text = "변경 시도"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 9. Section path / quality flags JSON 직렬화
# ---------------------------------------------------------------------------


def test_section_path_json_roundtrip(repo):
    """section_path가 JSON으로 저장되고 tuple로 복원된다."""
    q = _make_quote(
        section_path=("기업관", "1. 인간중심의 경영", "가. 기업 이념"),
    )
    repo.create(q)
    found = repo.find_by_id(q.quote_id)
    assert found is not None
    assert found.section_path == ("기업관", "1. 인간중심의 경영", "가. 기업 이념")
    assert isinstance(found.section_path, tuple)


def test_quality_flags_json_roundtrip(repo):
    """quality_flags가 JSON으로 저장되고 tuple로 복원된다."""
    q = _make_quote(
        quote_id="2020-14차|VWBE|narrative|002",
        text="품질 플래그 테스트",
        start_line=15300,
        quality_flags=("ocr_error", "short_text"),
    )
    repo.create(q)
    found = repo.find_by_id(q.quote_id)
    assert found is not None
    assert found.quality_flags == ("ocr_error", "short_text")
    assert isinstance(found.quality_flags, tuple)
