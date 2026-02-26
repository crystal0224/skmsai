"""배치 데이터 업데이트 + 인덱스 갱신 서비스.

PR-036: JSONL → DB 적재 → BM25 인덱스 갱신 파이프라인.

전체 파이프라인을 단일 진입점으로 통합하고, 각 단계별 결과를 추적한다.
벡터 인덱스는 외부 API 의존으로 별도 트리거 방식 유지.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from scripts.lib.db import connection, get_connection, init_db
from scripts.lib.ingest import IngestPipeline, IngestResult
from scripts.lib.quote import QuoteObject
from scripts.lib.quote_repository import QuoteRepository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Immutable result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StepResult:
    """개별 단계 실행 결과."""

    name: str
    success: bool
    duration_ms: float
    detail: str
    records_affected: int = 0


@dataclass(frozen=True)
class IndexRefreshResult:
    """인덱스 갱신 결과."""

    bm25_indexed: int
    bm25_path: str
    duration_ms: float
    success: bool
    error: str = ""


@dataclass(frozen=True)
class BatchUpdateResult:
    """배치 업데이트 전체 결과."""

    steps: tuple[StepResult, ...]
    total_duration_ms: float
    ingest_result: IngestResult | None
    index_result: IndexRefreshResult | None
    db_total_before: int
    db_total_after: int
    net_new_quotes: int
    success: bool

    @property
    def summary(self) -> str:
        """요약 문자열."""
        status = "SUCCESS" if self.success else "FAILED"
        parts = [
            f"[{status}]",
            f"duration={self.total_duration_ms:.0f}ms",
            f"before={self.db_total_before}",
            f"after={self.db_total_after}",
            f"net_new={self.net_new_quotes}",
        ]
        if self.index_result and self.index_result.success:
            parts.append(f"bm25={self.index_result.bm25_indexed}")
        return " | ".join(parts)


@dataclass(frozen=True)
class BatchUpdateConfig:
    """배치 업데이트 설정."""

    jsonl_path: Path = field(
        default_factory=lambda: Path("data/processed/quotes.jsonl")
    )
    db_path: Path | None = None
    index_dir: Path = field(default_factory=lambda: Path("indexes"))
    batch_size: int = 500
    expected_min: int | None = None
    quality_exclude: tuple[str, ...] = ("ocr_error",)
    type_boost: tuple[tuple[str, float], ...] = (
        ("definition", 2.0),
        ("principle", 1.5),
    )
    rebuild_bm25: bool = True
    dry_run: bool = False


# ---------------------------------------------------------------------------
# BatchUpdateService
# ---------------------------------------------------------------------------


class BatchUpdateService:
    """배치 데이터 업데이트 + 인덱스 갱신 서비스.

    3단계 파이프라인:
    1. JSONL → DB 적재 (멱등, content_hash 기반)
    2. BM25 인덱스 갱신
    3. 메타데이터 저장
    """

    def __init__(self, config: BatchUpdateConfig | None = None) -> None:
        self._config = config or BatchUpdateConfig()

    @property
    def config(self) -> BatchUpdateConfig:
        return self._config

    def run(self) -> BatchUpdateResult:
        """전체 파이프라인을 실행한다."""
        t0 = time.monotonic()
        steps: list[StepResult] = []
        ingest_result: IngestResult | None = None
        index_result: IndexRefreshResult | None = None
        db_total_before = 0
        db_total_after = 0
        overall_success = True

        # Step 1: DB 초기화 + 현재 상태 확인
        step_result, db_total_before = self._step_check_db()
        steps.append(step_result)
        if not step_result.success:
            overall_success = False

        # Step 2: JSONL → DB 적재
        if overall_success:
            step_result, ingest_result = self._step_ingest()
            steps.append(step_result)
            if not step_result.success:
                overall_success = False

        # Step 3: 적재 후 DB 상태 확인
        if overall_success:
            step_result, db_total_after = self._step_verify_db()
            steps.append(step_result)
        else:
            db_total_after = db_total_before

        # Step 4: BM25 인덱스 갱신
        if overall_success and self._config.rebuild_bm25:
            step_result, index_result = self._step_rebuild_bm25()
            steps.append(step_result)
            if not step_result.success:
                overall_success = False

        # Step 5: 메타데이터 저장
        if overall_success:
            step_result = self._step_save_meta(db_total_after, index_result)
            steps.append(step_result)

        total_ms = (time.monotonic() - t0) * 1000

        result = BatchUpdateResult(
            steps=tuple(steps),
            total_duration_ms=round(total_ms, 1),
            ingest_result=ingest_result,
            index_result=index_result,
            db_total_before=db_total_before,
            db_total_after=db_total_after,
            net_new_quotes=db_total_after - db_total_before,
            success=overall_success,
        )
        logger.info("배치 업데이트 완료: %s", result.summary)
        return result

    def check_for_updates(self) -> tuple[bool, str]:
        """JSONL 파일에 새로운 데이터가 있는지 확인한다.

        Returns:
            (has_updates, reason) tuple
        """
        jsonl_path = self._config.jsonl_path
        if not jsonl_path.exists():
            return False, f"JSONL 파일 없음: {jsonl_path}"

        # JSONL 라인 수 확인
        line_count = 0
        with jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    line_count += 1

        if line_count == 0:
            return False, "JSONL 파일이 비어 있음"

        # DB 현재 quote 수 확인
        init_db(self._config.db_path)
        conn = get_connection(self._config.db_path)
        try:
            repo = QuoteRepository(conn)
            db_count = repo.count_total()
        finally:
            conn.close()

        if line_count > db_count:
            return (
                True,
                f"JSONL={line_count}, DB={db_count} (차이: {line_count - db_count})",
            )

        return False, f"JSONL={line_count}, DB={db_count} (변경 없음)"

    # ------------------------------------------------------------------
    # Private steps
    # ------------------------------------------------------------------

    def _step_check_db(self) -> tuple[StepResult, int]:
        """DB 초기화 + 현재 상태 확인."""
        t0 = time.monotonic()
        try:
            init_db(self._config.db_path)
            conn = get_connection(self._config.db_path)
            try:
                repo = QuoteRepository(conn)
                db_total = repo.count_total()
            finally:
                conn.close()

            ms = (time.monotonic() - t0) * 1000
            return (
                StepResult(
                    name="check_db",
                    success=True,
                    duration_ms=round(ms, 1),
                    detail=f"DB 현재 {db_total}건",
                    records_affected=db_total,
                ),
                db_total,
            )
        except Exception as e:
            ms = (time.monotonic() - t0) * 1000
            logger.error("DB 초기화 실패: %s", e)
            return (
                StepResult(
                    name="check_db",
                    success=False,
                    duration_ms=round(ms, 1),
                    detail=f"DB 초기화 실패: {e}",
                ),
                0,
            )

    def _step_ingest(self) -> tuple[StepResult, IngestResult | None]:
        """JSONL → DB 적재."""
        t0 = time.monotonic()
        cfg = self._config

        if cfg.dry_run:
            ms = (time.monotonic() - t0) * 1000
            return (
                StepResult(
                    name="ingest",
                    success=True,
                    duration_ms=round(ms, 1),
                    detail="dry_run 모드: 적재 건너뜀",
                ),
                None,
            )

        try:
            result = IngestPipeline.run(
                cfg.jsonl_path,
                db_path=cfg.db_path,
                batch_size=cfg.batch_size,
                expected_min=cfg.expected_min,
            )
            ms = (time.monotonic() - t0) * 1000
            detail = (
                f"파싱={result.total_parsed}, 변환={result.converted}, "
                f"삽입={result.inserted}, 건너뜀={result.skipped}, "
                f"에러={result.errors}"
            )
            return (
                StepResult(
                    name="ingest",
                    success=result.success,
                    duration_ms=round(ms, 1),
                    detail=detail,
                    records_affected=result.inserted,
                ),
                result,
            )
        except Exception as e:
            ms = (time.monotonic() - t0) * 1000
            logger.error("적재 실패: %s", e)
            return (
                StepResult(
                    name="ingest",
                    success=False,
                    duration_ms=round(ms, 1),
                    detail=f"적재 실패: {e}",
                ),
                None,
            )

    def _step_verify_db(self) -> tuple[StepResult, int]:
        """적재 후 DB 상태 확인."""
        t0 = time.monotonic()
        try:
            conn = get_connection(self._config.db_path)
            try:
                repo = QuoteRepository(conn)
                db_total = repo.count_total()
                by_edition = repo.count_by_edition()
            finally:
                conn.close()

            edition_summary = ", ".join(
                f"{eid}={cnt}" for eid, cnt in sorted(by_edition.items())
            )
            ms = (time.monotonic() - t0) * 1000
            return (
                StepResult(
                    name="verify_db",
                    success=True,
                    duration_ms=round(ms, 1),
                    detail=f"DB 총 {db_total}건 ({edition_summary})",
                    records_affected=db_total,
                ),
                db_total,
            )
        except Exception as e:
            ms = (time.monotonic() - t0) * 1000
            logger.error("DB 검증 실패: %s", e)
            return (
                StepResult(
                    name="verify_db",
                    success=False,
                    duration_ms=round(ms, 1),
                    detail=f"DB 검증 실패: {e}",
                ),
                0,
            )

    def _step_rebuild_bm25(self) -> tuple[StepResult, IndexRefreshResult | None]:
        """BM25 인덱스 갱신."""
        t0 = time.monotonic()
        cfg = self._config

        if cfg.dry_run:
            ms = (time.monotonic() - t0) * 1000
            return (
                StepResult(
                    name="rebuild_bm25",
                    success=True,
                    duration_ms=round(ms, 1),
                    detail="dry_run 모드: 인덱스 갱신 건너뜀",
                ),
                None,
            )

        try:
            conn = get_connection(cfg.db_path)
            try:
                repo = QuoteRepository(conn)
                quotes = repo.find_excluding_flags(list(cfg.quality_exclude))
            finally:
                conn.close()

            if not quotes:
                ms = (time.monotonic() - t0) * 1000
                return (
                    StepResult(
                        name="rebuild_bm25",
                        success=False,
                        duration_ms=round(ms, 1),
                        detail="갱신 대상 quote 없음",
                    ),
                    None,
                )

            from scripts.lib.bm25_index import BM25Index

            type_boost = dict(cfg.type_boost)
            bm25 = BM25Index.from_quotes(quotes, type_boost=type_boost)
            bm25_path = cfg.index_dir / "bm25_index.pkl"
            cfg.index_dir.mkdir(parents=True, exist_ok=True)
            bm25.save(bm25_path)

            ms = (time.monotonic() - t0) * 1000
            idx_result = IndexRefreshResult(
                bm25_indexed=bm25.size,
                bm25_path=str(bm25_path),
                duration_ms=round(ms, 1),
                success=True,
            )
            return (
                StepResult(
                    name="rebuild_bm25",
                    success=True,
                    duration_ms=round(ms, 1),
                    detail=f"BM25 갱신: {bm25.size}건",
                    records_affected=bm25.size,
                ),
                idx_result,
            )
        except Exception as e:
            ms = (time.monotonic() - t0) * 1000
            logger.error("BM25 갱신 실패: %s", e)
            idx_result = IndexRefreshResult(
                bm25_indexed=0,
                bm25_path="",
                duration_ms=round(ms, 1),
                success=False,
                error=str(e),
            )
            return (
                StepResult(
                    name="rebuild_bm25",
                    success=False,
                    duration_ms=round(ms, 1),
                    detail=f"BM25 갱신 실패: {e}",
                ),
                idx_result,
            )

    def _step_save_meta(
        self,
        db_total: int,
        index_result: IndexRefreshResult | None,
    ) -> StepResult:
        """갱신 메타데이터를 저장한다."""
        t0 = time.monotonic()
        try:
            meta = {
                "source": "batch_update",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "db_total": db_total,
                "bm25_indexed": index_result.bm25_indexed if index_result else 0,
                "quality_exclude": list(self._config.quality_exclude),
                "type_boost": dict(self._config.type_boost),
            }
            meta_path = self._config.index_dir / "meta.json"
            self._config.index_dir.mkdir(parents=True, exist_ok=True)
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            ms = (time.monotonic() - t0) * 1000
            return StepResult(
                name="save_meta",
                success=True,
                duration_ms=round(ms, 1),
                detail=f"메타 저장: {meta_path}",
            )
        except Exception as e:
            ms = (time.monotonic() - t0) * 1000
            logger.error("메타 저장 실패: %s", e)
            return StepResult(
                name="save_meta",
                success=False,
                duration_ms=round(ms, 1),
                detail=f"메타 저장 실패: {e}",
            )
