"""IngestPipeline 통합 테스트.

PR-010: load_jsonl, ingest, verify, run 전체 파이프라인 검증.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

# 프로젝트 루트
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.ingest import (  # noqa: E402
    IngestError,
    IngestPipeline,
    IngestResult,
    IngestVerification,
)
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
    migration = _PROJECT_ROOT / "migrations" / "001_quote.sql"
    conn.executescript(migration.read_text(encoding="utf-8"))
    return conn


@pytest.fixture()
def conn():
    c = _get_test_connection()
    c.isolation_level = None  # autocommit
    yield c
    c.close()


@pytest.fixture()
def pipeline(conn):
    return IngestPipeline(conn)


@pytest.fixture()
def repo(conn):
    return QuoteRepository(conn)


def _make_legacy_record(index: int = 0, **overrides) -> dict:
    """유효한 legacy JSONL 레코드를 생성한다."""
    text = overrides.get("text", f"테스트 텍스트 {index}")
    edition_id = overrides.get("edition_id", _DEFAULT_EDITION)
    start_line = overrides.get("start_line", _DEFAULT_START_LINE + index)
    defaults = {
        "quote_id": overrides.get("quote_id", f"2020-14차|VWBE|narrative|{index:03d}"),
        "text": text,
        "edition_id": edition_id,
        "type": overrides.get("type", "narrative"),
        "section_path": overrides.get("section_path", ["VWBE Culture"]),
        "start_line": start_line,
        "char_span": overrides.get("char_span", [100, 200]),
        "token_count": overrides.get("token_count", 20),
        "sha256": QuoteObject.compute_hash(str(text), str(edition_id), int(start_line)),
        "quality_flags": overrides.get("quality_flags", []),
    }
    return defaults


def _write_jsonl(path: Path, records: list[dict]) -> None:
    """레코드 리스트를 JSONL 파일로 작성한다."""
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Dataclass 불변성 테스트
# ---------------------------------------------------------------------------


def test_ingest_error_is_frozen():
    """IngestError는 불변이다."""
    err = IngestError(line_num=1, quote_id="test", message="error")
    with pytest.raises(AttributeError):
        err.message = "changed"  # type: ignore[misc]


def test_ingest_result_is_frozen():
    """IngestResult는 불변이다."""
    result = IngestResult(
        source_path="test.jsonl",
        total_parsed=10,
        converted=8,
        inserted=8,
        skipped=0,
        errors=2,
        error_details=(),
        db_total=8,
        by_edition=(),
        duration_ms=100.0,
    )
    with pytest.raises(AttributeError):
        result.inserted = 99  # type: ignore[misc]


def test_ingest_result_success_true():
    """에러 0이면 success=True."""
    result = IngestResult(
        source_path="",
        total_parsed=5,
        converted=5,
        inserted=5,
        skipped=0,
        errors=0,
        error_details=(),
        db_total=5,
        by_edition=(),
        duration_ms=0,
    )
    assert result.success is True


def test_ingest_result_success_false():
    """에러 > 0이면 success=False."""
    result = IngestResult(
        source_path="",
        total_parsed=5,
        converted=3,
        inserted=3,
        skipped=0,
        errors=2,
        error_details=(),
        db_total=3,
        by_edition=(),
        duration_ms=0,
    )
    assert result.success is False


def test_ingest_verification_is_frozen():
    """IngestVerification은 불변이다."""
    v = IngestVerification(
        db_total=10,
        by_edition=(),
        by_type=(),
        expected_min=None,
        passed=True,
    )
    with pytest.raises(AttributeError):
        v.db_total = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# load_jsonl 테스트
# ---------------------------------------------------------------------------


def test_load_jsonl_valid_records(pipeline, tmp_path):
    """유효한 레코드 5건을 로드한다."""
    records = [_make_legacy_record(i) for i in range(5)]
    path = tmp_path / "quotes.jsonl"
    _write_jsonl(path, records)

    quotes, errors = pipeline.load_jsonl(path)
    assert len(quotes) == 5
    assert len(errors) == 0


def test_load_jsonl_malformed_json(pipeline, tmp_path):
    """잘못된 JSON 라인은 에러로 수집된다."""
    path = tmp_path / "quotes.jsonl"
    with path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(_make_legacy_record(0), ensure_ascii=False) + "\n")
        f.write("NOT VALID JSON\n")
        f.write(json.dumps(_make_legacy_record(1), ensure_ascii=False) + "\n")

    quotes, errors = pipeline.load_jsonl(path)
    assert len(quotes) == 2
    assert len(errors) == 1
    assert errors[0].line_num == 2
    assert "JSON 파싱 실패" in errors[0].message


def test_load_jsonl_missing_required_field(pipeline, tmp_path):
    """필수 필드 누락 레코드는 에러로 수집된다."""
    rec = _make_legacy_record(0)
    del rec["text"]
    path = tmp_path / "quotes.jsonl"
    _write_jsonl(path, [rec])

    quotes, errors = pipeline.load_jsonl(path)
    assert len(quotes) == 0
    assert len(errors) == 1
    assert errors[0].line_num == 1


def test_load_jsonl_empty_file(pipeline, tmp_path):
    """빈 파일은 0건, 0에러."""
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")

    quotes, errors = pipeline.load_jsonl(path)
    assert len(quotes) == 0
    assert len(errors) == 0


def test_load_jsonl_file_not_found(pipeline, tmp_path):
    """존재하지 않는 파일 → FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        pipeline.load_jsonl(tmp_path / "nonexistent.jsonl")


def test_load_jsonl_blank_lines_ignored(pipeline, tmp_path):
    """빈 줄은 무시된다."""
    path = tmp_path / "quotes.jsonl"
    with path.open("w", encoding="utf-8") as f:
        f.write("\n")
        f.write(json.dumps(_make_legacy_record(0), ensure_ascii=False) + "\n")
        f.write("\n\n")
        f.write(json.dumps(_make_legacy_record(1), ensure_ascii=False) + "\n")
        f.write("\n")

    quotes, errors = pipeline.load_jsonl(path)
    assert len(quotes) == 2
    assert len(errors) == 0


def test_load_jsonl_error_has_quote_id(pipeline, tmp_path):
    """변환 에러에 quote_id가 기록된다."""
    rec = _make_legacy_record(0)
    rec["type"] = "INVALID_TYPE"
    path = tmp_path / "quotes.jsonl"
    _write_jsonl(path, [rec])

    quotes, errors = pipeline.load_jsonl(path)
    assert len(errors) == 1
    assert errors[0].quote_id == rec["quote_id"]


# ---------------------------------------------------------------------------
# ingest 테스트
# ---------------------------------------------------------------------------


def test_ingest_new_records(pipeline, repo, tmp_path):
    """새 레코드가 모두 삽입된다."""
    records = [_make_legacy_record(i) for i in range(5)]
    path = tmp_path / "quotes.jsonl"
    _write_jsonl(path, records)

    quotes, _ = pipeline.load_jsonl(path)
    inserted, skipped = pipeline.ingest(quotes)

    assert inserted == 5
    assert skipped == 0
    assert repo.count_total() == 5


def test_ingest_idempotent(pipeline, repo, tmp_path):
    """동일 데이터 재적재 → 추가 삽입 없음."""
    records = [_make_legacy_record(i) for i in range(3)]
    path = tmp_path / "quotes.jsonl"
    _write_jsonl(path, records)

    quotes, _ = pipeline.load_jsonl(path)
    inserted1, skipped1 = pipeline.ingest(quotes)
    assert inserted1 == 3
    assert skipped1 == 0

    inserted2, skipped2 = pipeline.ingest(quotes)
    assert inserted2 == 0
    assert skipped2 == 3
    assert repo.count_total() == 3


def test_ingest_partial_duplicate(pipeline, repo, tmp_path):
    """일부 중복, 일부 새 레코드."""
    # 먼저 3건 삽입
    records_a = [_make_legacy_record(i) for i in range(3)]
    path_a = tmp_path / "a.jsonl"
    _write_jsonl(path_a, records_a)
    quotes_a, _ = pipeline.load_jsonl(path_a)
    pipeline.ingest(quotes_a)

    # 5건 (기존 3 + 새 2)
    records_b = [_make_legacy_record(i) for i in range(5)]
    path_b = tmp_path / "b.jsonl"
    _write_jsonl(path_b, records_b)
    quotes_b, _ = pipeline.load_jsonl(path_b)
    inserted, skipped = pipeline.ingest(quotes_b)

    assert inserted == 2
    assert skipped == 3
    assert repo.count_total() == 5


def test_ingest_batch_size(pipeline, repo, tmp_path):
    """batch_size가 전체보다 작아도 정상 동작."""
    records = [_make_legacy_record(i) for i in range(7)]
    path = tmp_path / "quotes.jsonl"
    _write_jsonl(path, records)

    quotes, _ = pipeline.load_jsonl(path)
    inserted, skipped = pipeline.ingest(quotes, batch_size=3)

    assert inserted == 7
    assert skipped == 0
    assert repo.count_total() == 7


def test_ingest_empty_list(pipeline, repo):
    """빈 리스트 → 0건 삽입."""
    inserted, skipped = pipeline.ingest([])
    assert inserted == 0
    assert skipped == 0
    assert repo.count_total() == 0


# ---------------------------------------------------------------------------
# verify 테스트
# ---------------------------------------------------------------------------


def test_verify_total_count(pipeline, repo, tmp_path):
    """검증: 전체 건수 확인."""
    records = [_make_legacy_record(i) for i in range(5)]
    path = tmp_path / "quotes.jsonl"
    _write_jsonl(path, records)
    quotes, _ = pipeline.load_jsonl(path)
    pipeline.ingest(quotes)

    v = pipeline.verify()
    assert v.db_total == 5
    assert v.passed is True


def test_verify_by_edition(pipeline, tmp_path):
    """검증: edition별 건수."""
    records = [
        _make_legacy_record(0, edition_id="1979-초판", start_line=10),
        _make_legacy_record(1, edition_id="1979-초판", start_line=20),
        _make_legacy_record(2, edition_id="2020-14차", start_line=15200),
    ]
    path = tmp_path / "quotes.jsonl"
    _write_jsonl(path, records)
    quotes, _ = pipeline.load_jsonl(path)
    pipeline.ingest(quotes)

    v = pipeline.verify()
    edition_dict = dict(v.by_edition)
    assert edition_dict["1979-초판"] == 2
    assert edition_dict["2020-14차"] == 1


def test_verify_expected_min_pass(pipeline, repo, tmp_path):
    """expected_min 충족 → passed=True."""
    records = [_make_legacy_record(i) for i in range(5)]
    path = tmp_path / "quotes.jsonl"
    _write_jsonl(path, records)
    quotes, _ = pipeline.load_jsonl(path)
    pipeline.ingest(quotes)

    v = pipeline.verify(expected_min=3)
    assert v.passed is True


def test_verify_expected_min_fail(pipeline, repo, tmp_path):
    """expected_min 미달 → passed=False."""
    records = [_make_legacy_record(i) for i in range(2)]
    path = tmp_path / "quotes.jsonl"
    _write_jsonl(path, records)
    quotes, _ = pipeline.load_jsonl(path)
    pipeline.ingest(quotes)

    v = pipeline.verify(expected_min=10)
    assert v.passed is False


def test_verify_by_type(pipeline, tmp_path):
    """검증: type별 건수."""
    records = [
        _make_legacy_record(0, type="narrative"),
        _make_legacy_record(1, type="definition"),
        _make_legacy_record(2, type="definition"),
    ]
    path = tmp_path / "quotes.jsonl"
    _write_jsonl(path, records)
    quotes, _ = pipeline.load_jsonl(path)
    pipeline.ingest(quotes)

    v = pipeline.verify()
    type_dict = dict(v.by_type)
    assert type_dict["narrative"] == 1
    assert type_dict["definition"] == 2


# ---------------------------------------------------------------------------
# run() 통합 테스트
# ---------------------------------------------------------------------------


def test_run_full_pipeline(tmp_path):
    """run() 전체 파이프라인 성공."""
    records = [_make_legacy_record(i) for i in range(5)]
    jsonl_path = tmp_path / "quotes.jsonl"
    _write_jsonl(jsonl_path, records)
    db_path = tmp_path / "test.db"

    result = IngestPipeline.run(jsonl_path=jsonl_path, db_path=db_path)

    assert result.total_parsed == 5
    assert result.converted == 5
    assert result.inserted == 5
    assert result.skipped == 0
    assert result.errors == 0
    assert result.db_total == 5
    assert result.success is True
    assert result.duration_ms > 0


def test_run_idempotent(tmp_path):
    """run() 재실행 → 추가 삽입 없음."""
    records = [_make_legacy_record(i) for i in range(3)]
    jsonl_path = tmp_path / "quotes.jsonl"
    _write_jsonl(jsonl_path, records)
    db_path = tmp_path / "test.db"

    result1 = IngestPipeline.run(jsonl_path=jsonl_path, db_path=db_path)
    assert result1.inserted == 3

    result2 = IngestPipeline.run(jsonl_path=jsonl_path, db_path=db_path)
    assert result2.inserted == 0
    assert result2.skipped == 3
    assert result2.db_total == 3


def test_run_with_errors(tmp_path):
    """에러가 있는 파일도 유효 레코드는 적재된다."""
    jsonl_path = tmp_path / "quotes.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(_make_legacy_record(0), ensure_ascii=False) + "\n")
        f.write("INVALID JSON LINE\n")
        f.write(json.dumps(_make_legacy_record(1), ensure_ascii=False) + "\n")
    db_path = tmp_path / "test.db"

    result = IngestPipeline.run(jsonl_path=jsonl_path, db_path=db_path)

    assert result.converted == 2
    assert result.inserted == 2
    assert result.errors == 1
    assert result.success is False
    assert len(result.error_details) == 1


def test_run_file_not_found(tmp_path):
    """존재하지 않는 파일 → FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        IngestPipeline.run(
            jsonl_path=tmp_path / "nope.jsonl",
            db_path=tmp_path / "test.db",
        )


# ---------------------------------------------------------------------------
# QuoteRepository 추가 메서드 테스트
# ---------------------------------------------------------------------------


def test_find_all(repo, pipeline, tmp_path):
    """find_all은 전체 레코드를 반환한다."""
    records = [_make_legacy_record(i) for i in range(5)]
    path = tmp_path / "quotes.jsonl"
    _write_jsonl(path, records)
    quotes, _ = pipeline.load_jsonl(path)
    pipeline.ingest(quotes)

    all_quotes = repo.find_all()
    assert len(all_quotes) == 5


def test_find_all_limit(repo, pipeline, tmp_path):
    """find_all(limit=N)은 최대 N건만 반환한다."""
    records = [_make_legacy_record(i) for i in range(5)]
    path = tmp_path / "quotes.jsonl"
    _write_jsonl(path, records)
    quotes, _ = pipeline.load_jsonl(path)
    pipeline.ingest(quotes)

    limited = repo.find_all(limit=3)
    assert len(limited) == 3


def test_find_excluding_flags(repo, pipeline, tmp_path):
    """quality_flags에 지정 플래그가 있는 레코드를 제외한다."""
    records = [
        _make_legacy_record(0, quality_flags=[]),
        _make_legacy_record(1, quality_flags=["ocr_error"]),
        _make_legacy_record(2, quality_flags=["short_text"]),
        _make_legacy_record(3, quality_flags=["ocr_error", "short_text"]),
        _make_legacy_record(4, quality_flags=[]),
    ]
    path = tmp_path / "quotes.jsonl"
    _write_jsonl(path, records)
    quotes, _ = pipeline.load_jsonl(path)
    pipeline.ingest(quotes)

    filtered = repo.find_excluding_flags(["ocr_error"])
    assert len(filtered) == 3  # 0, 2, 4

    filtered2 = repo.find_excluding_flags(["ocr_error", "short_text"])
    assert len(filtered2) == 2  # 0, 4


def test_find_excluding_flags_empty_list(repo, pipeline, tmp_path):
    """빈 exclude_flags → 전체 반환."""
    records = [_make_legacy_record(i, quality_flags=["ocr_error"]) for i in range(3)]
    path = tmp_path / "quotes.jsonl"
    _write_jsonl(path, records)
    quotes, _ = pipeline.load_jsonl(path)
    pipeline.ingest(quotes)

    all_q = repo.find_excluding_flags([])
    assert len(all_q) == 3
