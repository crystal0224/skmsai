"""JSONL → SQLite 마이그레이션 스크립트.

PR-009: 기존 data/processed/quotes.jsonl을 SQLite DB로 적재.

Usage:
    python scripts/migrate_quotes_to_db.py [--db-path data/skms.db]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.db import get_connection, init_db  # noqa: E402
from scripts.lib.quote import QuoteObject  # noqa: E402
from scripts.lib.quote_repository import QuoteRepository  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def load_legacy_quotes(jsonl_path: Path) -> list[dict]:
    """quotes.jsonl에서 레코드를 로드한다."""
    records: list[dict] = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                logger.warning("JSON 파싱 실패 (line %d): %s", line_num, e)
    return records


def migrate(db_path: Path | None = None) -> dict[str, int]:
    """quotes.jsonl → SQLite DB 마이그레이션.

    Returns:
        {"total": N, "inserted": M, "skipped": K, "errors": E}
    """
    jsonl_path = _PROJECT_ROOT / "data" / "processed" / "quotes.jsonl"
    if not jsonl_path.exists():
        logger.error("quotes.jsonl not found: %s", jsonl_path)
        return {"total": 0, "inserted": 0, "skipped": 0, "errors": 0}

    # DB 초기화
    init_db(db_path)

    # 레코드 로드
    records = load_legacy_quotes(jsonl_path)
    logger.info("Loaded %d records from %s", len(records), jsonl_path)

    # 변환
    quotes: list[QuoteObject] = []
    errors = 0
    error_details: list[str] = []

    for i, record in enumerate(records):
        try:
            quotes.append(QuoteObject.from_legacy(record))
        except (ValueError, KeyError) as e:
            errors += 1
            detail = f"[{i+1}] {record.get('quote_id', '?')}: {e}"
            error_details.append(detail)
            if errors <= 5:
                logger.warning("변환 실패: %s", detail)

    # 일괄 적재 (멱등) — try/finally로 연결 누수 방지
    conn = get_connection(db_path)
    try:
        repo = QuoteRepository(conn)
        inserted = repo.bulk_upsert(quotes)
        conn.commit()
        skipped = len(quotes) - inserted
        total = len(records)
    finally:
        conn.close()

    result = {
        "total": total,
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
    }

    logger.info("Migration complete: %s", result)
    if error_details:
        logger.info("Error details (first 10):")
        for d in error_details[:10]:
            logger.info("  %s", d)

    # 검증: DB 카운트
    conn2 = get_connection(db_path)
    try:
        repo2 = QuoteRepository(conn2)
        db_count = repo2.count_total()
        by_edition = repo2.count_by_edition()
        by_type = repo2.count_by_type()
    finally:
        conn2.close()

    logger.info("DB total: %d", db_count)
    logger.info("By edition: %s", by_edition)
    logger.info("By type: %s", by_type)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="JSONL → SQLite migration")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="SQLite DB path (default: data/skms.db)",
    )
    args = parser.parse_args()
    result = migrate(args.db_path)

    if result["errors"] > 0:
        logger.warning("Migration completed with %d errors", result["errors"])
        sys.exit(1)
    else:
        logger.info("Migration successful: %d quotes inserted", result["inserted"])


if __name__ == "__main__":
    main()
