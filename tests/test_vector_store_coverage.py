"""vector_store.py 커버리지 보강 테스트.

TD-006: 미커버 라인 — from_path 에러 경로 (lines 48-50, 57-66).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.vector_store import VectorStore  # noqa: E402


# ---------------------------------------------------------------------------
# VectorStore.from_path — chromadb ImportError (lines 48-50)
# ---------------------------------------------------------------------------


def test_from_path_no_chromadb(tmp_path):
    """chromadb 패키지 없으면 None 컬렉션 반환 (lines 48-50)."""
    with patch.dict("sys.modules", {"chromadb": None}):
        # importlib 캐시 우회를 위해 직접 실행
        store = VectorStore.from_path(tmp_path / "indexes")
    assert store.is_available is False
    assert store.count() == 0


# ---------------------------------------------------------------------------
# VectorStore.from_path — chroma path 없음 (lines 53-55)
# ---------------------------------------------------------------------------


def test_from_path_chroma_dir_missing(tmp_path):
    """chroma 서브디렉토리가 없으면 None 컬렉션 (lines 53-55)."""
    chromadb = pytest.importorskip("chromadb")
    index_dir = tmp_path / "indexes"
    index_dir.mkdir()
    # indexes/chroma 디렉토리 없음
    store = VectorStore.from_path(index_dir)
    assert store.is_available is False


# ---------------------------------------------------------------------------
# VectorStore.from_path — collection 없으면 새로 생성 (lines 57-66)
# ---------------------------------------------------------------------------


def test_from_path_creates_collection_on_miss(tmp_path):
    """컬렉션이 없으면 create_collection 호출 (lines 60-66)."""
    chromadb = pytest.importorskip("chromadb")

    chroma_dir = tmp_path / "indexes" / "chroma"
    chroma_dir.mkdir(parents=True)

    # PersistentClient로 빈 DB 생성 (컬렉션 없음)
    client = chromadb.PersistentClient(path=str(chroma_dir))
    # 컬렉션이 없는 상태에서 from_path 호출
    store = VectorStore.from_path(tmp_path / "indexes", "nonexistent_collection")

    # 컬렉션이 새로 생성되어 available
    assert store.is_available is True
    assert store.count() == 0


# ---------------------------------------------------------------------------
# VectorStore.from_path — path ends with 'chroma' (line 52)
# ---------------------------------------------------------------------------


def test_from_path_direct_chroma_path(tmp_path):
    """path가 이미 'chroma'로 끝나면 그대로 사용 (line 52)."""
    chromadb = pytest.importorskip("chromadb")

    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir()

    store = VectorStore.from_path(chroma_dir, "test_direct")
    assert store.is_available is True


# ---------------------------------------------------------------------------
# VectorStore.from_path — existing collection (line 59)
# ---------------------------------------------------------------------------


def test_from_path_existing_collection(tmp_path):
    """기존 컬렉션이 있으면 get_collection 성공 (line 59)."""
    chromadb = pytest.importorskip("chromadb")

    chroma_dir = tmp_path / "indexes" / "chroma"
    chroma_dir.mkdir(parents=True)

    # 미리 컬렉션 생성
    client = chromadb.PersistentClient(path=str(chroma_dir))
    client.create_collection(
        name="existing_col",
        metadata={"hnsw:space": "cosine"},
    )

    store = VectorStore.from_path(tmp_path / "indexes", "existing_col")
    assert store.is_available is True
