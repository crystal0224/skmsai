"""E2E test fixtures — serves the frontend on a local HTTP server."""

import http.server
import threading

import pytest

# Skip entire e2e directory when pytest-playwright is not installed
# (provides the 'page' fixture required by all E2E tests)
_pw = pytest.importorskip(
    "pytest_playwright", reason="pytest-playwright not installed — skipping E2E tests"
)


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Suppress request logging in test output."""

    def log_message(self, format, *args):
        pass


@pytest.fixture(scope="session")
def frontend_server():
    """Start an HTTP server for everline-studio-clone/ on port 5500.

    Yields the base URL. Server shuts down after the test session.
    """
    import os

    directory = os.path.join(
        os.path.dirname(__file__), "..", "..", "everline-studio-clone"
    )
    directory = os.path.abspath(directory)

    handler = lambda *args, **kwargs: _QuietHandler(
        *args, directory=directory, **kwargs
    )

    server = http.server.HTTPServer(("127.0.0.1", 5500), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield "http://localhost:5500"

    server.shutdown()


@pytest.fixture(scope="session")
def base_url(frontend_server):
    """Expose base_url for individual tests (session-scoped for pytest-playwright)."""
    return frontend_server
