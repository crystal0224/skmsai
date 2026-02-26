"""SQLite connection management for SKMS project.

Provides thread-safe connection factory and migration runner.
All connections use WAL mode and enforce foreign keys.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

# ---------------------------------------------------------------------------
# Project root: scripts/lib/db.py → go up 2 levels
# ---------------------------------------------------------------------------

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

_DEFAULT_DB_PATH: Path = PROJECT_ROOT / "data" / "skms.db"


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Return a configured sqlite3.Connection with Row factory.

    Args:
        db_path: Path to the SQLite database file.
                 Defaults to ``data/skms.db`` relative to project root.

    Returns:
        sqlite3.Connection with WAL journal mode, foreign keys enabled,
        Row factory, and check_same_thread=False for testing.
    """
    resolved = Path(db_path) if db_path is not None else _DEFAULT_DB_PATH
    resolved.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(resolved), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def connection(
    db_path: str | Path | None = None,
) -> Generator[sqlite3.Connection, None, None]:
    """Context manager that auto-commits on success and always closes.

    Usage::

        with connection() as conn:
            conn.execute("INSERT INTO quotes ...")
            # auto-commits when the block exits normally
            # rolls back on exception
    """
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str | Path | None = None) -> None:
    """Run all SQL migrations in ``migrations/`` directory, ordered by filename.

    Migration files are expected to be named with a numeric prefix for
    deterministic ordering (e.g. ``001_quote.sql``, ``002_embedding.sql``).

    Each migration is executed inside the connection's context manager
    so it auto-commits on success.

    Args:
        db_path: Path to the SQLite database file.
                 Defaults to ``data/skms.db`` relative to project root.
    """
    migrations_dir = PROJECT_ROOT / "migrations"
    if not migrations_dir.is_dir():
        return

    sql_files = sorted(migrations_dir.glob("*.sql"))
    if not sql_files:
        return

    with connection(db_path) as conn:
        for sql_file in sql_files:
            sql = sql_file.read_text(encoding="utf-8")
            conn.executescript(sql)
