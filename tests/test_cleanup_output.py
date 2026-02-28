"""Output 디렉토리 정리 스크립트 테스트.

CC-04: scripts/cleanup_output.py 단위 테스트.
"""
from __future__ import annotations

import os
import time

import pytest

from scripts.cleanup_output import (
    CleanupResult,
    DEFAULT_MAX_AGE_DAYS,
    SIZE_WARN_THRESHOLD_BYTES,
    cleanup_output,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_file(path, content: str = "data", age_days: float = 0) -> None:
    """파일을 생성하고, age_days만큼 과거 시점으로 mtime을 설정한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    if age_days > 0:
        old_time = time.time() - (age_days * 86400)
        os.utime(path, (old_time, old_time))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCleanupOldFiles:
    """오래된 파일 삭제 테스트."""

    def test_cleanup_old_files(self, tmp_path):
        """max_age_days보다 오래된 파일만 삭제한다."""
        old_file = tmp_path / "old.txt"
        new_file = tmp_path / "new.txt"
        _create_file(old_file, "old content", age_days=40)
        _create_file(new_file, "new content", age_days=5)

        result = cleanup_output(tmp_path, max_age_days=30)

        assert result.deleted_count == 1
        assert result.deleted_bytes == len("old content")
        assert result.skipped_count == 1
        assert not old_file.exists()
        assert new_file.exists()

    def test_cleanup_nested_old_files(self, tmp_path):
        """하위 디렉토리의 오래된 파일도 삭제한다."""
        sub = tmp_path / "subdir" / "deep"
        old_file = sub / "expired.log"
        _create_file(old_file, "x" * 100, age_days=60)

        result = cleanup_output(tmp_path, max_age_days=30)

        assert result.deleted_count == 1
        assert result.deleted_bytes == 100
        assert not old_file.exists()

    def test_nothing_to_delete(self, tmp_path):
        """삭제 대상이 없으면 deleted_count=0."""
        _create_file(tmp_path / "recent.txt", "fresh", age_days=1)

        result = cleanup_output(tmp_path, max_age_days=30)

        assert result.deleted_count == 0
        assert result.skipped_count == 1

    def test_empty_directory(self, tmp_path):
        """빈 디렉토리에서 실행해도 정상 동작."""
        result = cleanup_output(tmp_path, max_age_days=30)

        assert result.deleted_count == 0
        assert result.skipped_count == 0
        assert result.total_size_bytes == 0


class TestDryRun:
    """dry-run 모드 테스트."""

    def test_dry_run_no_delete(self, tmp_path):
        """dry-run 모드에서는 파일을 삭제하지 않는다."""
        old_file = tmp_path / "old.txt"
        _create_file(old_file, "keep me", age_days=60)

        result = cleanup_output(tmp_path, max_age_days=30, dry_run=True)

        assert result.deleted_count == 1  # 삭제 '대상' 수
        assert result.deleted_bytes == len("keep me")
        assert old_file.exists()  # 실제로는 삭제되지 않음

    def test_dry_run_skips_recent(self, tmp_path):
        """dry-run에서도 최신 파일은 건너뛴다."""
        _create_file(tmp_path / "new.txt", "fresh", age_days=1)

        result = cleanup_output(tmp_path, max_age_days=30, dry_run=True)

        assert result.deleted_count == 0
        assert result.skipped_count == 1


class TestReportOnly:
    """report-only 모드 테스트."""

    def test_report_only(self, tmp_path):
        """report-only 모드에서는 전체 사용량만 보고한다."""
        _create_file(tmp_path / "a.txt", "aaa", age_days=60)
        _create_file(tmp_path / "b.txt", "bb", age_days=1)

        result = cleanup_output(tmp_path, report_only=True)

        assert result.deleted_count == 0
        assert result.deleted_bytes == 0
        assert result.skipped_count == 2
        assert result.total_size_bytes == 5  # 3 + 2
        # 파일이 그대로 존재
        assert (tmp_path / "a.txt").exists()
        assert (tmp_path / "b.txt").exists()


class TestWarnLargeDirectory:
    """대용량 디렉토리 경고 테스트."""

    def test_warn_large_directory(self, tmp_path, monkeypatch):
        """total_size_bytes > 1GB이면 경고를 포함한다."""
        big_file = tmp_path / "big.bin"
        big_file.write_bytes(b"x" * 1024)  # 실제로 1GB 파일은 만들지 않음

        # SIZE_WARN_THRESHOLD_BYTES를 낮춰서 경고를 발생시킨다
        monkeypatch.setattr(
            "scripts.cleanup_output.SIZE_WARN_THRESHOLD_BYTES",
            512,
        )

        result = cleanup_output(tmp_path, report_only=True)

        assert len(result.warnings) == 1
        assert "1GB" in result.warnings[0]

    def test_no_warn_small_directory(self, tmp_path):
        """총 크기가 1GB 미만이면 경고가 없다."""
        _create_file(tmp_path / "small.txt", "tiny")

        result = cleanup_output(tmp_path, report_only=True)

        assert len(result.warnings) == 0


class TestCleanupResultFrozen:
    """CleanupResult 불변성 테스트."""

    def test_cleanup_result_frozen(self):
        """CleanupResult는 frozen dataclass이므로 수정 불가."""
        result = CleanupResult(
            deleted_count=1,
            deleted_bytes=100,
            skipped_count=2,
            total_size_bytes=300,
            warnings=("test warning",),
        )

        with pytest.raises(AttributeError):
            result.deleted_count = 99  # type: ignore[misc]

    def test_cleanup_result_fields(self):
        """모든 필드가 올바르게 설정된다."""
        result = CleanupResult(
            deleted_count=3,
            deleted_bytes=1024,
            skipped_count=5,
            total_size_bytes=2048,
            warnings=("w1", "w2"),
        )

        assert result.deleted_count == 3
        assert result.deleted_bytes == 1024
        assert result.skipped_count == 5
        assert result.total_size_bytes == 2048
        assert result.warnings == ("w1", "w2")
