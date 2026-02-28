"""Root-level test fixtures shared across all test directories.

Provides common fixtures used by any test module in the project.
"""
from __future__ import annotations

import pytest
from pathlib import Path


@pytest.fixture
def tmp_output_dir(tmp_path: Path) -> Path:
    """Create a temporary output directory for tests that produce files.

    Returns a Path to a freshly created 'output' subdirectory inside
    pytest's tmp_path. Cleaned up automatically after test completion.
    """
    out = tmp_path / "output"
    out.mkdir()
    return out
