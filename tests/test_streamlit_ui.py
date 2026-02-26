"""Streamlit MVP UI 테스트.

PR-015: UI 헬퍼 함수 + API 클라이언트 테스트.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

pytest.importorskip("streamlit")
pytest.importorskip("requests")

from ui.streamlit_app import (  # noqa: E402
    API_BASE,
    OUTPUT_TYPES,
    QUOTE_TYPES,
    SEARCH_MODES,
    _api_get,
    _api_post,
    _is_json,
)


# ---------------------------------------------------------------------------
# _is_json 테스트
# ---------------------------------------------------------------------------


def test_is_json_valid():
    """유효한 JSON."""
    assert _is_json('{"key": "value"}') is True


def test_is_json_array():
    """JSON 배열."""
    assert _is_json("[1, 2, 3]") is True


def test_is_json_invalid():
    """유효하지 않은 JSON."""
    assert _is_json("not json") is False


def test_is_json_empty():
    """빈 문자열."""
    assert _is_json("") is False


def test_is_json_none():
    """None."""
    assert _is_json(None) is False


# ---------------------------------------------------------------------------
# _api_get 테스트
# ---------------------------------------------------------------------------


@patch("ui.streamlit_app.requests.get")
@patch("ui.streamlit_app.st")
def test_api_get_success(mock_st, mock_get):
    """정상적인 GET 요청."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"status": "ok"}
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    result = _api_get("/health")
    assert result == {"status": "ok"}
    mock_get.assert_called_once_with(f"{API_BASE}/health", params=None, timeout=30)


@patch("ui.streamlit_app.requests.get")
@patch("ui.streamlit_app.st")
def test_api_get_with_params(mock_st, mock_get):
    """파라미터가 포함된 GET 요청."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"total": 5}
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    result = _api_get("/toc", params={"q": "인간중심"})
    assert result == {"total": 5}
    mock_get.assert_called_once_with(
        f"{API_BASE}/toc", params={"q": "인간중심"}, timeout=30
    )


@patch("ui.streamlit_app.requests.get")
@patch("ui.streamlit_app.st")
def test_api_get_error(mock_st, mock_get):
    """GET 요청 실패 시 None 반환."""
    import requests

    mock_get.side_effect = requests.RequestException("Connection refused")

    result = _api_get("/health")
    assert result is None
    mock_st.error.assert_called_once()


# ---------------------------------------------------------------------------
# _api_post 테스트
# ---------------------------------------------------------------------------


@patch("ui.streamlit_app.requests.post")
@patch("ui.streamlit_app.st")
def test_api_post_success(mock_st, mock_post):
    """정상적인 POST 요청."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"query": "test", "total": 1, "hits": []}
    mock_resp.raise_for_status.return_value = None
    mock_post.return_value = mock_resp

    result = _api_post("/search", {"query": "test"})
    assert result["query"] == "test"
    mock_post.assert_called_once_with(
        f"{API_BASE}/search", json={"query": "test"}, timeout=60
    )


@patch("ui.streamlit_app.requests.post")
@patch("ui.streamlit_app.st")
def test_api_post_error(mock_st, mock_post):
    """POST 요청 실패 시 None 반환."""
    import requests

    mock_post.side_effect = requests.RequestException("API error")

    result = _api_post("/search", {"query": "test"})
    assert result is None
    mock_st.error.assert_called_once()


# ---------------------------------------------------------------------------
# Constants 테스트
# ---------------------------------------------------------------------------


def test_search_modes():
    """검색 모드 상수."""
    assert "hybrid" in SEARCH_MODES
    assert "vector" in SEARCH_MODES
    assert "bm25" in SEARCH_MODES
    assert len(SEARCH_MODES) == 3


def test_output_types():
    """출력 유형 상수."""
    assert "summary" in OUTPUT_TYPES
    assert "card" in OUTPUT_TYPES
    assert len(OUTPUT_TYPES) == 5


def test_quote_types():
    """인용 타입 상수."""
    assert "definition" in QUOTE_TYPES
    assert "narrative" in QUOTE_TYPES
    assert len(QUOTE_TYPES) == 6


def test_api_base_default():
    """기본 API URL."""
    assert "localhost" in API_BASE
    assert "/api" in API_BASE
