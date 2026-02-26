"""CLI: JSONL → SQLite 멱등 적재 파이프라인.

PR-010: content_hash 기반 중복 방지, 배치 적재, 검증.

Usage:
    python scripts/10_ingest.py
    python scripts/10_ingest.py --source data/processed/quotes.jsonl
    python scripts/10_ingest.py --db-path data/skms.db --batch-size 200
    python scripts/10_ingest.py --expected-min 700
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.ingest import IngestPipeline  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="JSONL → SQLite 멱등 적재 파이프라인")
    parser.add_argument(
        "--source",
        type=Path,
        default=_PROJECT_ROOT / "data" / "processed" / "quotes.jsonl",
        help="JSONL 소스 파일 경로 (default: data/processed/quotes.jsonl)",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="SQLite DB 경로 (default: data/skms.db)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="배치 크기 (default: 500)",
    )
    parser.add_argument(
        "--expected-min",
        type=int,
        default=None,
        help="최소 기대 건수 (검증 실패 시 exit 1)",
    )
    args = parser.parse_args()

    result = IngestPipeline.run(
        jsonl_path=args.source,
        db_path=args.db_path,
        batch_size=args.batch_size,
        expected_min=args.expected_min,
    )

    logger.info("Pipeline complete:")
    logger.info("  Source:     %s", result.source_path)
    logger.info("  Parsed:     %d", result.total_parsed)
    logger.info("  Converted:  %d", result.converted)
    logger.info("  Inserted:   %d", result.inserted)
    logger.info("  Skipped:    %d (duplicates)", result.skipped)
    logger.info("  Errors:     %d", result.errors)
    logger.info("  DB Total:   %d", result.db_total)
    logger.info("  Duration:   %.1f ms", result.duration_ms)
    logger.info("  By edition: %s", dict(result.by_edition))

    if result.error_details:
        logger.warning("Error details (first %d):", len(result.error_details))
        for err in result.error_details[:10]:
            logger.warning(
                "  [line %d] %s: %s", err.line_num, err.quote_id, err.message
            )

    if not result.success:
        if not result.verification_passed:
            logger.warning(
                "Verification failed: DB has %d records, expected >= %s",
                result.db_total,
                args.expected_min,
            )
        if result.errors > 0:
            logger.warning("Pipeline completed with %d errors", result.errors)
        sys.exit(1)


if __name__ == "__main__":
    main()
