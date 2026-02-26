"""QuoteRepository — QuoteObject CRUD + 멱등 upsert.

PR-009: QuoteObject Schema + DB Migration.

SQLite 기반 데이터 접근 레이어. 모든 반환값은 불변 QuoteObject.
upsert는 content_hash 기반 ON CONFLICT으로 멱등성 보장.

Note: 이 클래스는 commit()을 호출하지 않는다.
호출자가 트랜잭션 경계를 직접 관리해야 한다.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

from scripts.lib.quote import QuoteObject

logger = logging.getLogger(__name__)


class QuoteRepository:
    """QuoteObject SQLite 저장소.

    모든 메서드는 불변 QuoteObject를 반환한다.
    connection은 외부에서 주입하여 트랜잭션 제어 가능.

    Important: commit()은 호출자 책임. 이 클래스는 트랜잭션을 관리하지 않는다.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Create / Upsert
    # ------------------------------------------------------------------

    _INSERT_SQL = """
        INSERT INTO quotes (
            quote_id, text, edition_id, year, revision_num,
            quote_type, section_path, start_line,
            char_span_start, char_span_end, token_count,
            content_hash, quality_flags, is_definition
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    _UPSERT_SQL = """
        INSERT OR IGNORE INTO quotes (
            quote_id, text, edition_id, year, revision_num,
            quote_type, section_path, start_line,
            char_span_start, char_span_end, token_count,
            content_hash, quality_flags, is_definition
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    def create(self, quote: QuoteObject) -> QuoteObject:
        """INSERT 단건. content_hash 중복 시 IntegrityError 발생."""
        self._conn.execute(self._INSERT_SQL, self._to_params(quote))
        logger.info(
            "quote.created",
            extra={
                "quote_id": quote.quote_id,
                "edition_id": quote.edition_id,
                "content_hash": quote.content_hash,
            },
        )
        return quote

    def upsert(self, quote: QuoteObject) -> QuoteObject:
        """INSERT OR IGNORE on content_hash conflict.

        동일 content_hash가 이미 존재하면 삽입을 건너뛴다 (멱등).
        반환값은 항상 입력 QuoteObject (불변이므로 동일).
        """
        cursor = self._conn.execute(self._UPSERT_SQL, self._to_params(quote))
        if cursor.rowcount == 0:
            logger.info(
                "quote.duplicate_skipped",
                extra={"content_hash": quote.content_hash},
            )
        else:
            logger.info(
                "quote.created",
                extra={
                    "quote_id": quote.quote_id,
                    "content_hash": quote.content_hash,
                },
            )
        return quote

    def bulk_upsert(self, quotes: list[QuoteObject]) -> int:
        """다건 멱등 삽입. 실제 삽입된 건수를 반환한다.

        executemany의 rowcount는 신뢰할 수 없으므로
        삽입 전/후 COUNT(*)를 비교하여 정확한 삽입 건수를 산출.
        """
        count_before = self.count_total()
        params_list = [self._to_params(q) for q in quotes]
        self._conn.executemany(self._UPSERT_SQL, params_list)
        count_after = self.count_total()
        inserted = count_after - count_before
        logger.info(
            "quote.bulk_upsert",
            extra={"total": len(quotes), "inserted": inserted},
        )
        return inserted

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def find_by_id(self, quote_id: str) -> QuoteObject | None:
        """quote_id로 단건 조회."""
        row = self._conn.execute(
            "SELECT * FROM quotes WHERE quote_id = ?", (quote_id,)
        ).fetchone()
        if row is None:
            return None
        return self._from_row(row)

    def find_by_content_hash(self, content_hash: str) -> QuoteObject | None:
        """content_hash로 단건 조회."""
        row = self._conn.execute(
            "SELECT * FROM quotes WHERE content_hash = ?", (content_hash,)
        ).fetchone()
        if row is None:
            return None
        return self._from_row(row)

    def find_by_edition(
        self, edition_id: str, *, limit: int = 1000
    ) -> list[QuoteObject]:
        """edition_id로 다건 조회."""
        rows = self._conn.execute(
            "SELECT * FROM quotes WHERE edition_id = ? ORDER BY start_line LIMIT ?",
            (edition_id, limit),
        ).fetchall()
        return [self._from_row(r) for r in rows]

    def find_definitions(self, *, limit: int = 1000) -> list[QuoteObject]:
        """is_definition=True인 인용만 조회."""
        rows = self._conn.execute(
            "SELECT * FROM quotes WHERE is_definition = 1 ORDER BY year, start_line LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._from_row(r) for r in rows]

    def find_by_type(self, quote_type: str, *, limit: int = 1000) -> list[QuoteObject]:
        """quote_type으로 다건 조회."""
        rows = self._conn.execute(
            "SELECT * FROM quotes WHERE quote_type = ? ORDER BY year, start_line LIMIT ?",
            (quote_type, limit),
        ).fetchall()
        return [self._from_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Count / Aggregate
    # ------------------------------------------------------------------

    def count_total(self) -> int:
        """전체 건수."""
        row = self._conn.execute("SELECT COUNT(*) FROM quotes").fetchone()
        return row[0]

    def count_by_edition(self) -> dict[str, int]:
        """edition_id별 건수."""
        rows = self._conn.execute(
            "SELECT edition_id, COUNT(*) FROM quotes GROUP BY edition_id ORDER BY year"
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    def count_by_type(self) -> dict[str, int]:
        """quote_type별 건수."""
        rows = self._conn.execute(
            "SELECT quote_type, COUNT(*) FROM quotes GROUP BY quote_type"
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_by_id(self, quote_id: str) -> bool:
        """quote_id로 단건 삭제. 삭제 성공 시 True."""
        cursor = self._conn.execute(
            "DELETE FROM quotes WHERE quote_id = ?", (quote_id,)
        )
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("quote.deleted", extra={"quote_id": quote_id})
        return deleted

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_params(quote: QuoteObject) -> tuple[Any, ...]:
        """QuoteObject → SQLite INSERT 파라미터 tuple."""
        return (
            quote.quote_id,
            quote.text,
            quote.edition_id,
            quote.year,
            quote.revision_num,
            quote.quote_type,
            json.dumps(list(quote.section_path), ensure_ascii=False),
            quote.start_line,
            quote.char_span[0],
            quote.char_span[1],
            quote.token_count,
            quote.content_hash,
            json.dumps(list(quote.quality_flags), ensure_ascii=False),
            int(quote.is_definition),
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> QuoteObject:
        """sqlite3.Row → QuoteObject."""
        return QuoteObject(
            quote_id=row["quote_id"],
            text=row["text"],
            edition_id=row["edition_id"],
            year=row["year"],
            revision_num=row["revision_num"],
            quote_type=row["quote_type"],
            section_path=tuple(json.loads(row["section_path"])),
            start_line=row["start_line"],
            char_span=(row["char_span_start"], row["char_span_end"]),
            token_count=row["token_count"],
            content_hash=row["content_hash"],
            quality_flags=tuple(json.loads(row["quality_flags"])),
            is_definition=bool(row["is_definition"]),
        )
