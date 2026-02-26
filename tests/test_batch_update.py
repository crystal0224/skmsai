"""BatchUpdateService 테스트.

PR-036: 배치 데이터 업데이트 + 인덱스 갱신 테스트.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from scripts.lib.batch_update import (
    BatchUpdateConfig,
    BatchUpdateResult,
    BatchUpdateService,
    IndexRefreshResult,
    StepResult,
)
from scripts.lib.db import get_connection, init_db
from scripts.lib.quote import QuoteObject


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_quote(
    *,
    quote_id: str = "test|q|001",
    text: str = "테스트 인용문입니다.",
    edition_id: str = "2020-14차",
    year: int = 2020,
    revision_num: int = 14,
    quote_type: str = "definition",
    section_path: tuple[str, ...] = ("경영", "인간중심"),
    start_line: int = 100,
) -> QuoteObject:
    """테스트용 QuoteObject를 생성한다."""
    content_hash = QuoteObject.compute_hash(text, edition_id, start_line)
    return QuoteObject(
        quote_id=quote_id,
        text=text,
        edition_id=edition_id,
        year=year,
        revision_num=revision_num,
        quote_type=quote_type,
        section_path=section_path,
        start_line=start_line,
        char_span=(0, len(text)),
        token_count=len(text.split()),
        content_hash=content_hash,
        quality_flags=(),
        is_definition=quote_type == "definition",
    )


def _make_jsonl(path: Path, quotes: list[QuoteObject]) -> None:
    """QuoteObject 리스트를 JSONL 파일로 저장한다."""
    with path.open("w", encoding="utf-8") as f:
        for q in quotes:
            record = {
                "quote_id": q.quote_id,
                "text": q.text,
                "edition_id": q.edition_id,
                "year": q.year,
                "type": q.quote_type,
                "section_path": list(q.section_path),
                "start_line": q.start_line,
                "char_span": list(q.char_span),
                "token_count": q.token_count,
                "sha256": q.content_hash,
                "quality_flags": list(q.quality_flags),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


@pytest.fixture()
def tmp_dir(tmp_path: Path) -> Path:
    """테스트용 임시 디렉토리."""
    return tmp_path


@pytest.fixture()
def db_path(tmp_dir: Path) -> Path:
    """테스트용 DB 경로."""
    path = tmp_dir / "test.db"
    init_db(path)
    return path


@pytest.fixture()
def sample_quotes() -> list[QuoteObject]:
    """테스트용 QuoteObject 리스트."""
    return [
        _make_quote(
            quote_id="2020-14차|경영|definition|001",
            text="SUPEX는 Super Excellent 수준을 의미한다.",
            edition_id="2020-14차",
            year=2020,
            start_line=100,
        ),
        _make_quote(
            quote_id="2020-14차|경영|principle|002",
            text="인간의 능력을 극대화하는 것이 경영의 핵심이다.",
            edition_id="2020-14차",
            year=2020,
            quote_type="principle",
            start_line=200,
        ),
        _make_quote(
            quote_id="2016-13차|경영|definition|001",
            text="SUPEX란 인간이 도달할 수 있는 최고 수준이다.",
            edition_id="2016-13차",
            year=2016,
            revision_num=13,
            start_line=300,
        ),
    ]


@pytest.fixture()
def jsonl_path(tmp_dir: Path, sample_quotes: list[QuoteObject]) -> Path:
    """테스트용 JSONL 파일."""
    path = tmp_dir / "quotes.jsonl"
    _make_jsonl(path, sample_quotes)
    return path


@pytest.fixture()
def index_dir(tmp_dir: Path) -> Path:
    """테스트용 인덱스 디렉토리."""
    path = tmp_dir / "indexes"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# StepResult (불변)
# ---------------------------------------------------------------------------


class TestStepResult:
    """StepResult frozen dataclass 테스트."""

    def test_create(self):
        step = StepResult(
            name="check_db",
            success=True,
            duration_ms=42.0,
            detail="DB 현재 100건",
            records_affected=100,
        )
        assert step.name == "check_db"
        assert step.success is True
        assert step.records_affected == 100

    def test_immutable(self):
        step = StepResult(name="test", success=True, duration_ms=1.0, detail="ok")
        with pytest.raises(AttributeError):
            step.name = "other"  # type: ignore[misc]

    def test_default_records(self):
        step = StepResult(name="test", success=True, duration_ms=1.0, detail="ok")
        assert step.records_affected == 0


# ---------------------------------------------------------------------------
# IndexRefreshResult (불변)
# ---------------------------------------------------------------------------


class TestIndexRefreshResult:
    """IndexRefreshResult frozen dataclass 테스트."""

    def test_create(self):
        result = IndexRefreshResult(
            bm25_indexed=100,
            bm25_path="/tmp/bm25.pkl",
            duration_ms=500.0,
            success=True,
        )
        assert result.bm25_indexed == 100
        assert result.success is True

    def test_immutable(self):
        result = IndexRefreshResult(
            bm25_indexed=0, bm25_path="", duration_ms=0.0, success=False, error="fail"
        )
        with pytest.raises(AttributeError):
            result.success = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# BatchUpdateResult (불변)
# ---------------------------------------------------------------------------


class TestBatchUpdateResult:
    """BatchUpdateResult frozen dataclass 테스트."""

    def test_summary_success(self):
        result = BatchUpdateResult(
            steps=(),
            total_duration_ms=1000.0,
            ingest_result=None,
            index_result=IndexRefreshResult(
                bm25_indexed=100,
                bm25_path="/tmp/bm25.pkl",
                duration_ms=200.0,
                success=True,
            ),
            db_total_before=50,
            db_total_after=75,
            net_new_quotes=25,
            success=True,
        )
        assert "[SUCCESS]" in result.summary
        assert "net_new=25" in result.summary
        assert "bm25=100" in result.summary

    def test_summary_failure(self):
        result = BatchUpdateResult(
            steps=(),
            total_duration_ms=100.0,
            ingest_result=None,
            index_result=None,
            db_total_before=50,
            db_total_after=50,
            net_new_quotes=0,
            success=False,
        )
        assert "[FAILED]" in result.summary

    def test_immutable(self):
        result = BatchUpdateResult(
            steps=(),
            total_duration_ms=100.0,
            ingest_result=None,
            index_result=None,
            db_total_before=0,
            db_total_after=0,
            net_new_quotes=0,
            success=True,
        )
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# BatchUpdateConfig (불변)
# ---------------------------------------------------------------------------


class TestBatchUpdateConfig:
    """BatchUpdateConfig frozen dataclass 테스트."""

    def test_defaults(self):
        config = BatchUpdateConfig()
        assert config.batch_size == 500
        assert config.rebuild_bm25 is True
        assert config.dry_run is False
        assert config.quality_exclude == ("ocr_error",)

    def test_custom(self):
        config = BatchUpdateConfig(
            batch_size=100,
            dry_run=True,
            rebuild_bm25=False,
        )
        assert config.batch_size == 100
        assert config.dry_run is True
        assert config.rebuild_bm25 is False

    def test_immutable(self):
        config = BatchUpdateConfig()
        with pytest.raises(AttributeError):
            config.batch_size = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# BatchUpdateService — check_for_updates
# ---------------------------------------------------------------------------


class TestCheckForUpdates:
    """BatchUpdateService.check_for_updates() 테스트."""

    def test_no_jsonl_file(self, db_path: Path, tmp_dir: Path):
        config = BatchUpdateConfig(
            jsonl_path=tmp_dir / "nonexistent.jsonl",
            db_path=db_path,
        )
        service = BatchUpdateService(config)
        has_updates, reason = service.check_for_updates()
        assert has_updates is False
        assert "파일 없음" in reason

    def test_empty_jsonl(self, db_path: Path, tmp_dir: Path):
        empty_path = tmp_dir / "empty.jsonl"
        empty_path.write_text("")
        config = BatchUpdateConfig(jsonl_path=empty_path, db_path=db_path)
        service = BatchUpdateService(config)
        has_updates, reason = service.check_for_updates()
        assert has_updates is False
        assert "비어 있음" in reason

    def test_has_updates(
        self,
        db_path: Path,
        jsonl_path: Path,
        index_dir: Path,
    ):
        config = BatchUpdateConfig(
            jsonl_path=jsonl_path,
            db_path=db_path,
            index_dir=index_dir,
        )
        service = BatchUpdateService(config)
        has_updates, reason = service.check_for_updates()
        # DB가 비어있고 JSONL에 3건 → 업데이트 필요
        assert has_updates is True
        assert "차이" in reason

    def test_no_updates_when_db_full(
        self,
        db_path: Path,
        jsonl_path: Path,
        sample_quotes: list[QuoteObject],
        index_dir: Path,
    ):
        # 먼저 DB에 데이터 적재
        from scripts.lib.ingest import IngestPipeline

        IngestPipeline.run(
            jsonl_path,
            db_path=db_path,
            batch_size=500,
        )

        config = BatchUpdateConfig(
            jsonl_path=jsonl_path,
            db_path=db_path,
            index_dir=index_dir,
        )
        service = BatchUpdateService(config)
        has_updates, reason = service.check_for_updates()
        assert has_updates is False
        assert "변경 없음" in reason


# ---------------------------------------------------------------------------
# BatchUpdateService — run (full pipeline)
# ---------------------------------------------------------------------------


class TestBatchUpdateRun:
    """BatchUpdateService.run() 전체 파이프라인 테스트."""

    def test_full_pipeline(
        self,
        db_path: Path,
        jsonl_path: Path,
        index_dir: Path,
    ):
        config = BatchUpdateConfig(
            jsonl_path=jsonl_path,
            db_path=db_path,
            index_dir=index_dir,
        )
        service = BatchUpdateService(config)
        result = service.run()

        assert result.success is True
        assert result.db_total_before == 0
        assert result.db_total_after == 3
        assert result.net_new_quotes == 3
        assert result.total_duration_ms > 0

        # 단계별 확인
        step_names = [s.name for s in result.steps]
        assert "check_db" in step_names
        assert "ingest" in step_names
        assert "verify_db" in step_names
        assert "rebuild_bm25" in step_names
        assert "save_meta" in step_names

        # 모든 단계 성공
        for step in result.steps:
            assert step.success is True, f"Step {step.name} failed: {step.detail}"

    def test_idempotent_rerun(
        self,
        db_path: Path,
        jsonl_path: Path,
        index_dir: Path,
    ):
        config = BatchUpdateConfig(
            jsonl_path=jsonl_path,
            db_path=db_path,
            index_dir=index_dir,
        )
        service = BatchUpdateService(config)

        # 첫 번째 실행
        result1 = service.run()
        assert result1.success is True
        assert result1.net_new_quotes == 3

        # 두 번째 실행 (멱등)
        result2 = service.run()
        assert result2.success is True
        assert result2.net_new_quotes == 0
        assert result2.db_total_before == 3
        assert result2.db_total_after == 3

    def test_dry_run(
        self,
        db_path: Path,
        jsonl_path: Path,
        index_dir: Path,
    ):
        config = BatchUpdateConfig(
            jsonl_path=jsonl_path,
            db_path=db_path,
            index_dir=index_dir,
            dry_run=True,
        )
        service = BatchUpdateService(config)
        result = service.run()

        assert result.success is True
        assert result.net_new_quotes == 0
        assert result.ingest_result is None
        assert result.index_result is None

    def test_no_bm25_rebuild(
        self,
        db_path: Path,
        jsonl_path: Path,
        index_dir: Path,
    ):
        config = BatchUpdateConfig(
            jsonl_path=jsonl_path,
            db_path=db_path,
            index_dir=index_dir,
            rebuild_bm25=False,
        )
        service = BatchUpdateService(config)
        result = service.run()

        assert result.success is True
        assert result.index_result is None
        step_names = [s.name for s in result.steps]
        assert "rebuild_bm25" not in step_names

    def test_ingest_result_available(
        self,
        db_path: Path,
        jsonl_path: Path,
        index_dir: Path,
    ):
        config = BatchUpdateConfig(
            jsonl_path=jsonl_path,
            db_path=db_path,
            index_dir=index_dir,
        )
        service = BatchUpdateService(config)
        result = service.run()

        assert result.ingest_result is not None
        assert result.ingest_result.converted == 3
        assert result.ingest_result.inserted == 3

    def test_index_result_available(
        self,
        db_path: Path,
        jsonl_path: Path,
        index_dir: Path,
    ):
        config = BatchUpdateConfig(
            jsonl_path=jsonl_path,
            db_path=db_path,
            index_dir=index_dir,
        )
        service = BatchUpdateService(config)
        result = service.run()

        assert result.index_result is not None
        assert result.index_result.success is True
        assert result.index_result.bm25_indexed == 3

    def test_meta_json_saved(
        self,
        db_path: Path,
        jsonl_path: Path,
        index_dir: Path,
    ):
        config = BatchUpdateConfig(
            jsonl_path=jsonl_path,
            db_path=db_path,
            index_dir=index_dir,
        )
        service = BatchUpdateService(config)
        service.run()

        meta_path = index_dir / "meta.json"
        assert meta_path.exists()
        with meta_path.open() as f:
            meta = json.load(f)
        assert meta["source"] == "batch_update"
        assert meta["db_total"] == 3
        assert meta["bm25_indexed"] == 3

    def test_bm25_index_file_created(
        self,
        db_path: Path,
        jsonl_path: Path,
        index_dir: Path,
    ):
        config = BatchUpdateConfig(
            jsonl_path=jsonl_path,
            db_path=db_path,
            index_dir=index_dir,
        )
        service = BatchUpdateService(config)
        result = service.run()

        bm25_path = index_dir / "bm25_index.pkl"
        assert bm25_path.exists()
        assert result.index_result is not None
        assert result.index_result.bm25_path == str(bm25_path)


# ---------------------------------------------------------------------------
# BatchUpdateService — error handling
# ---------------------------------------------------------------------------


class TestBatchUpdateErrors:
    """BatchUpdateService 에러 처리 테스트."""

    def test_missing_jsonl(self, db_path: Path, index_dir: Path, tmp_dir: Path):
        config = BatchUpdateConfig(
            jsonl_path=tmp_dir / "nonexistent.jsonl",
            db_path=db_path,
            index_dir=index_dir,
        )
        service = BatchUpdateService(config)
        result = service.run()

        # JSONL 없으면 ingest 단계 실패
        assert result.success is False
        ingest_step = next((s for s in result.steps if s.name == "ingest"), None)
        assert ingest_step is not None
        assert ingest_step.success is False

    def test_incremental_update(
        self,
        db_path: Path,
        tmp_dir: Path,
        index_dir: Path,
    ):
        """기존 데이터에 새 데이터 추가."""
        # 초기 데이터 적재
        quotes1 = [
            _make_quote(
                quote_id="2020-14차|경영|definition|001",
                text="초기 데이터입니다.",
                start_line=100,
            ),
        ]
        jsonl1 = tmp_dir / "quotes1.jsonl"
        _make_jsonl(jsonl1, quotes1)

        config1 = BatchUpdateConfig(
            jsonl_path=jsonl1,
            db_path=db_path,
            index_dir=index_dir,
        )
        result1 = BatchUpdateService(config1).run()
        assert result1.success is True
        assert result1.db_total_after == 1

        # 추가 데이터가 포함된 JSONL
        quotes2 = quotes1 + [
            _make_quote(
                quote_id="2020-14차|경영|principle|002",
                text="추가 데이터입니다.",
                quote_type="principle",
                start_line=200,
            ),
        ]
        jsonl2 = tmp_dir / "quotes2.jsonl"
        _make_jsonl(jsonl2, quotes2)

        config2 = BatchUpdateConfig(
            jsonl_path=jsonl2,
            db_path=db_path,
            index_dir=index_dir,
        )
        result2 = BatchUpdateService(config2).run()
        assert result2.success is True
        assert result2.db_total_before == 1
        assert result2.db_total_after == 2
        assert result2.net_new_quotes == 1
