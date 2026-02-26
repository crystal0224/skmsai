"""배치 데이터 업데이트 CLI.

PR-036: JSONL → DB → BM25 인덱스 갱신 파이프라인.

Usage:
    python scripts/12_batch_update.py
    python scripts/12_batch_update.py --check-only
    python scripts/12_batch_update.py --dry-run
    python scripts/12_batch_update.py --jsonl data/processed/quotes.jsonl --db-path data/skms.db
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.batch_update import BatchUpdateConfig, BatchUpdateService  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="배치 데이터 업데이트 + 인덱스 갱신")
    parser.add_argument(
        "--jsonl",
        type=Path,
        default=Path("data/processed/quotes.jsonl"),
        help="JSONL 소스 파일 경로",
    )
    parser.add_argument("--db-path", type=Path, default=None, help="SQLite DB 경로")
    parser.add_argument(
        "--index-dir", type=Path, default=Path("indexes"), help="인덱스 출력 디렉토리"
    )
    parser.add_argument("--batch-size", type=int, default=500, help="적재 배치 크기")
    parser.add_argument("--expected-min", type=int, default=None, help="최소 기대 건수")
    parser.add_argument(
        "--quality-exclude",
        nargs="*",
        default=["ocr_error"],
        help="제외할 quality_flags",
    )
    parser.add_argument("--no-bm25", action="store_true", help="BM25 인덱스 갱신 건너뜀")
    parser.add_argument("--dry-run", action="store_true", help="실제 적재 없이 확인만")
    parser.add_argument("--check-only", action="store_true", help="업데이트 필요 여부만 확인")
    args = parser.parse_args()

    config = BatchUpdateConfig(
        jsonl_path=args.jsonl,
        db_path=args.db_path,
        index_dir=args.index_dir,
        batch_size=args.batch_size,
        expected_min=args.expected_min,
        quality_exclude=tuple(args.quality_exclude),
        rebuild_bm25=not args.no_bm25,
        dry_run=args.dry_run,
    )

    service = BatchUpdateService(config)

    if args.check_only:
        has_updates, reason = service.check_for_updates()
        logger.info("업데이트 확인: %s (%s)", "필요" if has_updates else "불필요", reason)
        sys.exit(0 if not has_updates else 1)

    result = service.run()

    # 단계별 결과 출력
    for step in result.steps:
        status = "OK" if step.success else "FAIL"
        logger.info(
            "  [%s] %s (%.0fms): %s",
            status,
            step.name,
            step.duration_ms,
            step.detail,
        )

    logger.info("결과: %s", result.summary)

    if not result.success:
        sys.exit(1)


if __name__ == "__main__":
    main()
