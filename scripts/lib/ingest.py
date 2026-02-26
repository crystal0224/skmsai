"""IngestPipeline — 멱등 JSONL → SQLite 적재 파이프라인.

PR-010: content_hash 기반 중복 방지, 배치 적재, 검증.

conn은 외부 주입. commit()은 호출자 책임.
run()은 자체 connection + commit을 관리하는 편의 클래스메서드.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from scripts.lib.db import get_connection, init_db
from scripts.lib.quote import QuoteObject
from scripts.lib.quote_repository import QuoteRepository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result / Error dataclasses (모두 불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IngestError:
    """개별 레코드 변환 실패 정보."""

    line_num: int
    quote_id: str
    message: str


@dataclass(frozen=True)
class IngestVerification:
    """적재 후 DB 상태 검증 결과."""

    db_total: int
    by_edition: tuple[tuple[str, int], ...]
    by_type: tuple[tuple[str, int], ...]
    expected_min: int | None
    passed: bool


@dataclass(frozen=True)
class IngestResult:
    """파이프라인 실행 결과."""

    source_path: str
    total_parsed: int
    converted: int
    inserted: int
    skipped: int
    errors: int
    error_details: tuple[IngestError, ...]
    db_total: int
    by_edition: tuple[tuple[str, int], ...]
    duration_ms: float
    verification_passed: bool = True

    @property
    def success(self) -> bool:
        """에러가 없고 검증도 통과하면 성공."""
        return self.errors == 0 and self.verification_passed


# ---------------------------------------------------------------------------
# IngestPipeline
# ---------------------------------------------------------------------------

_MAX_ERROR_DETAILS = 50


class IngestPipeline:
    """멱등 JSONL → SQLite 적재 파이프라인.

    Important: commit()은 호출자 책임. 이 클래스는 트랜잭션을 관리하지 않는다.
    편의 메서드 run()은 자체 connection + commit을 관리한다.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._repo = QuoteRepository(conn)

    # ------------------------------------------------------------------
    # 1단계: JSONL 로드 + 변환
    # ------------------------------------------------------------------

    def load_jsonl(self, path: Path) -> tuple[list[QuoteObject], list[IngestError]]:
        """JSONL 파일을 파싱하고 QuoteObject 리스트와 에러 리스트를 반환한다.

        Raises:
            FileNotFoundError: 파일이 존재하지 않는 경우
        """
        if not path.exists():
            raise FileNotFoundError(f"JSONL 파일을 찾을 수 없습니다: {path}")

        raw_records: list[tuple[int, dict]] = []
        errors: list[IngestError] = []

        with path.open("r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    raw_records.append((line_num, json.loads(line)))
                except json.JSONDecodeError as e:
                    errors.append(
                        IngestError(
                            line_num=line_num,
                            quote_id="",
                            message=f"JSON 파싱 실패: {e}",
                        )
                    )

        quotes: list[QuoteObject] = []
        for line_num, record in raw_records:
            try:
                quotes.append(QuoteObject.from_legacy(record))
            except (ValueError, KeyError, TypeError) as e:
                errors.append(
                    IngestError(
                        line_num=line_num,
                        quote_id=str(record.get("quote_id", "")),
                        message=str(e),
                    )
                )

        return quotes, errors

    # ------------------------------------------------------------------
    # 2단계: DB 적재 (멱등)
    # ------------------------------------------------------------------

    def ingest(
        self,
        quotes: list[QuoteObject],
        *,
        batch_size: int = 500,
    ) -> tuple[int, int]:
        """quotes를 DB에 멱등 삽입한다.

        Returns:
            (inserted, skipped) tuple
        """
        if not quotes:
            return 0, 0

        total_inserted = 0
        for start in range(0, len(quotes), batch_size):
            batch = quotes[start : start + batch_size]
            total_inserted += self._repo.bulk_upsert(batch)

        skipped = len(quotes) - total_inserted
        return total_inserted, skipped

    # ------------------------------------------------------------------
    # 3단계: 검증
    # ------------------------------------------------------------------

    def verify(self, *, expected_min: int | None = None) -> IngestVerification:
        """적재 후 DB 상태를 검증한다."""
        db_total = self._repo.count_total()
        by_edition = self._repo.count_by_edition()
        by_type = self._repo.count_by_type()

        passed = True
        if expected_min is not None and db_total < expected_min:
            passed = False

        return IngestVerification(
            db_total=db_total,
            by_edition=tuple(sorted(by_edition.items())),
            by_type=tuple(sorted(by_type.items())),
            expected_min=expected_min,
            passed=passed,
        )

    # ------------------------------------------------------------------
    # 편의 메서드: 전체 파이프라인
    # ------------------------------------------------------------------

    @classmethod
    def run(
        cls,
        jsonl_path: Path,
        *,
        db_path: Path | None = None,
        batch_size: int = 500,
        expected_min: int | None = None,
    ) -> IngestResult:
        """JSONL → DB 전체 파이프라인을 실행한다.

        자체 connection을 생성하고 commit/close를 관리한다.
        """
        t0 = time.monotonic()

        init_db(db_path)
        conn = get_connection(db_path)
        try:
            pipeline = cls(conn)

            # 1. Load + transform
            quotes, load_errors = pipeline.load_jsonl(jsonl_path)

            # 2. Ingest
            inserted, skipped = pipeline.ingest(quotes, batch_size=batch_size)
            conn.commit()

            # 3. Verify
            verification = pipeline.verify(expected_min=expected_min)

            duration_ms = (time.monotonic() - t0) * 1000

            return IngestResult(
                source_path=str(jsonl_path),
                total_parsed=len(quotes) + len(load_errors),
                converted=len(quotes),
                inserted=inserted,
                skipped=skipped,
                errors=len(load_errors),
                error_details=tuple(load_errors[:_MAX_ERROR_DETAILS]),
                db_total=verification.db_total,
                by_edition=verification.by_edition,
                duration_ms=duration_ms,
                verification_passed=verification.passed,
            )
        finally:
            conn.close()
