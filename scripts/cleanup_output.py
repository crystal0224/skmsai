"""Output 디렉토리 정리 스크립트.

CC-04: output/ 하위의 오래된 파일을 정리하고 디스크 사용량을 보고한다.

Usage:
    python scripts/cleanup_output.py --max-age-days 30
    python scripts/cleanup_output.py --dry-run
    python scripts/cleanup_output.py --report-only
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_AGE_DAYS = 30
DEFAULT_OUTPUT_DIR = "output"
SIZE_WARN_THRESHOLD_BYTES = 1_073_741_824  # 1 GB


# ---------------------------------------------------------------------------
# Result model (frozen dataclass)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CleanupResult:
    """정리 작업 결과."""

    deleted_count: int
    deleted_bytes: int
    skipped_count: int
    total_size_bytes: int
    warnings: tuple[str, ...]


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def _scan_files(output_dir: Path) -> list[Path]:
    """output_dir 하위의 모든 파일을 재귀적으로 수집한다."""
    if not output_dir.exists():
        return []
    return [p for p in output_dir.rglob("*") if p.is_file()]


def _file_age_days(file_path: Path, now: float) -> float:
    """파일의 경과 일수를 반환한다."""
    mtime = file_path.stat().st_mtime
    return (now - mtime) / 86400.0


def cleanup_output(
    output_dir: Path,
    *,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    dry_run: bool = False,
    report_only: bool = False,
) -> CleanupResult:
    """output 디렉토리를 정리한다.

    Args:
        output_dir: 정리 대상 디렉토리.
        max_age_days: 이 일수보다 오래된 파일을 삭제한다.
        dry_run: True이면 삭제하지 않고 보고만 한다.
        report_only: True이면 전체 사용량만 보고한다 (삭제 대상 식별 안 함).

    Returns:
        CleanupResult (frozen dataclass).
    """
    files = _scan_files(output_dir)
    now = time.time()

    total_size_bytes = sum(f.stat().st_size for f in files)
    warnings: list[str] = []

    if total_size_bytes > SIZE_WARN_THRESHOLD_BYTES:
        warnings.append(
            f"output/ 디렉토리 크기가 1GB를 초과합니다: " f"{total_size_bytes / (1024 ** 3):.2f} GB"
        )

    if report_only:
        return CleanupResult(
            deleted_count=0,
            deleted_bytes=0,
            skipped_count=len(files),
            total_size_bytes=total_size_bytes,
            warnings=tuple(warnings),
        )

    deleted_count = 0
    deleted_bytes = 0
    skipped_count = 0

    for file_path in files:
        try:
            age_days = _file_age_days(file_path, now)
        except OSError:
            skipped_count += 1
            continue

        if age_days < max_age_days:
            skipped_count += 1
            continue

        file_size = file_path.stat().st_size

        if dry_run:
            logger.info(
                "[DRY-RUN] 삭제 대상: %s (%.1f일, %d bytes)",
                file_path,
                age_days,
                file_size,
            )
            deleted_count += 1
            deleted_bytes += file_size
        else:
            try:
                file_path.unlink()
                deleted_count += 1
                deleted_bytes += file_size
                logger.info("삭제: %s (%.1f일, %d bytes)", file_path, age_days, file_size)
            except OSError as e:
                logger.warning("삭제 실패: %s — %s", file_path, e)
                skipped_count += 1

    return CleanupResult(
        deleted_count=deleted_count,
        deleted_bytes=deleted_bytes,
        skipped_count=skipped_count,
        total_size_bytes=total_size_bytes,
        warnings=tuple(warnings),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _format_bytes(n: int) -> str:
    """바이트를 사람이 읽기 쉬운 형식으로 변환한다."""
    if n < 1024:
        return f"{n} B"
    if n < 1024**2:
        return f"{n / 1024:.1f} KB"
    if n < 1024**3:
        return f"{n / (1024 ** 2):.1f} MB"
    return f"{n / (1024 ** 3):.2f} GB"


def _build_parser() -> argparse.ArgumentParser:
    """argparse 파서를 구성한다."""
    parser = argparse.ArgumentParser(
        description="output/ 디렉토리의 오래된 파일을 정리합니다.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f"정리 대상 디렉토리 (기본: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=DEFAULT_MAX_AGE_DAYS,
        help=f"이 일수보다 오래된 파일을 삭제 (기본: {DEFAULT_MAX_AGE_DAYS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="삭제하지 않고 보고만 합니다",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="전체 디스크 사용량만 보고합니다",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 진입점."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    output_dir = Path(args.output_dir)
    if not output_dir.exists():
        logger.error("디렉토리가 존재하지 않습니다: %s", output_dir)
        return 1

    mode = (
        "REPORT-ONLY"
        if args.report_only
        else ("DRY-RUN" if args.dry_run else "CLEANUP")
    )
    logger.info("모드: %s | 대상: %s | max-age: %d일", mode, output_dir, args.max_age_days)

    result = cleanup_output(
        output_dir,
        max_age_days=args.max_age_days,
        dry_run=args.dry_run,
        report_only=args.report_only,
    )

    # 결과 출력
    print("\n--- Output Cleanup Report ---")
    print(f"  전체 크기  : {_format_bytes(result.total_size_bytes)}")
    print(f"  삭제 파일  : {result.deleted_count}개 ({_format_bytes(result.deleted_bytes)})")
    print(f"  건너뜀     : {result.skipped_count}개")

    for warning in result.warnings:
        print(f"  [WARNING] {warning}")

    if args.dry_run:
        print("\n  (dry-run 모드: 실제 삭제 없음)")

    print("---\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
