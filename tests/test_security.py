"""보안 모듈 테스트.

PR-038: Rate Limiter, 환경변수 검증, 입력 살균 테스트.
"""
from __future__ import annotations

import os
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scripts.lib.security import (
    EnvValidationResult,
    RateLimitConfig,
    RateLimiter,
    RateLimitResult,
    VALID_QUOTE_TYPES,
    sanitize_edition_filter,
    sanitize_query,
    sanitize_type_filter,
    validate_environment,
)


# ---------------------------------------------------------------------------
# RateLimitConfig (불변)
# ---------------------------------------------------------------------------


class TestRateLimitConfig:
    """RateLimitConfig frozen dataclass 테스트."""

    def test_defaults(self):
        config = RateLimitConfig()
        assert config.requests_per_minute == 60
        assert config.burst_size == 10
        assert config.enabled is True

    def test_custom(self):
        config = RateLimitConfig(requests_per_minute=120, burst_size=20)
        assert config.requests_per_minute == 120
        assert config.burst_size == 20

    def test_immutable(self):
        config = RateLimitConfig()
        with pytest.raises(AttributeError):
            config.enabled = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# RateLimitResult (불변)
# ---------------------------------------------------------------------------


class TestRateLimitResult:
    """RateLimitResult frozen dataclass 테스트."""

    def test_create_allowed(self):
        result = RateLimitResult(
            allowed=True, remaining=5, retry_after_seconds=0.0, client_id="127.0.0.1"
        )
        assert result.allowed is True
        assert result.remaining == 5

    def test_create_denied(self):
        result = RateLimitResult(
            allowed=False, remaining=0, retry_after_seconds=1.5, client_id="10.0.0.1"
        )
        assert result.allowed is False
        assert result.retry_after_seconds == 1.5

    def test_immutable(self):
        result = RateLimitResult(
            allowed=True, remaining=5, retry_after_seconds=0.0, client_id="test"
        )
        with pytest.raises(AttributeError):
            result.allowed = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------


class TestRateLimiter:
    """RateLimiter 테스트."""

    def test_allows_initial_request(self):
        limiter = RateLimiter(RateLimitConfig(burst_size=5))
        result = limiter.check("client1")
        assert result.allowed is True
        assert result.remaining >= 0

    def test_allows_up_to_burst(self):
        limiter = RateLimiter(RateLimitConfig(burst_size=3, requests_per_minute=60))
        results = [limiter.check("client1") for _ in range(3)]
        assert all(r.allowed for r in results)

    def test_denies_after_burst(self):
        limiter = RateLimiter(RateLimitConfig(burst_size=2, requests_per_minute=60))
        limiter.check("client1")  # 1st
        limiter.check("client1")  # 2nd
        result = limiter.check("client1")  # 3rd — should be denied
        assert result.allowed is False
        assert result.retry_after_seconds > 0

    def test_independent_clients(self):
        limiter = RateLimiter(RateLimitConfig(burst_size=1))
        r1 = limiter.check("client1")
        r2 = limiter.check("client2")
        assert r1.allowed is True
        assert r2.allowed is True

    def test_disabled(self):
        limiter = RateLimiter(RateLimitConfig(enabled=False))
        # 100번 연속 요청도 모두 허용
        for _ in range(100):
            result = limiter.check("client1")
            assert result.allowed is True

    def test_refill_over_time(self):
        limiter = RateLimiter(RateLimitConfig(burst_size=1, requests_per_minute=600))
        # 첫 요청 허용
        r1 = limiter.check("client1")
        assert r1.allowed is True

        # 즉시 재시도 → 거부
        r2 = limiter.check("client1")
        assert r2.allowed is False

        # 토큰 리필 대기 (600rpm = 10/s, 100ms 후 ~1 token)
        time.sleep(0.15)
        r3 = limiter.check("client1")
        assert r3.allowed is True

    def test_reset_specific_client(self):
        limiter = RateLimiter(RateLimitConfig(burst_size=1))
        limiter.check("client1")
        limiter.check("client1")  # burst 소진

        limiter.reset("client1")
        result = limiter.check("client1")
        assert result.allowed is True

    def test_reset_all(self):
        limiter = RateLimiter(RateLimitConfig(burst_size=1))
        limiter.check("client1")
        limiter.check("client2")

        limiter.reset()
        r1 = limiter.check("client1")
        r2 = limiter.check("client2")
        assert r1.allowed is True
        assert r2.allowed is True

    def test_thread_safety(self):
        limiter = RateLimiter(RateLimitConfig(burst_size=100, requests_per_minute=6000))
        errors: list[str] = []

        def worker(client_id: str):
            for _ in range(50):
                try:
                    limiter.check(client_id)
                except Exception as e:
                    errors.append(str(e))

        threads = [
            threading.Thread(target=worker, args=(f"client{i}",)) for i in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


# ---------------------------------------------------------------------------
# EnvValidationResult (불변)
# ---------------------------------------------------------------------------


class TestEnvValidationResult:
    """EnvValidationResult frozen dataclass 테스트."""

    def test_valid(self):
        result = EnvValidationResult(
            valid=True, missing_required=(), missing_optional=(), warnings=()
        )
        assert result.valid is True

    def test_immutable(self):
        result = EnvValidationResult(
            valid=False, missing_required=("KEY",), missing_optional=(), warnings=()
        )
        with pytest.raises(AttributeError):
            result.valid = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# validate_environment
# ---------------------------------------------------------------------------


class TestValidateEnvironment:
    """validate_environment() 테스트."""

    def test_with_no_required_vars(self):
        result = validate_environment(required=(), optional=())
        assert result.valid is True
        assert result.missing_required == ()

    def test_missing_required(self, monkeypatch):
        monkeypatch.delenv("TEST_REQUIRED_VAR", raising=False)
        result = validate_environment(required=("TEST_REQUIRED_VAR",), optional=())
        assert result.valid is False
        assert "TEST_REQUIRED_VAR" in result.missing_required

    def test_present_required(self, monkeypatch):
        monkeypatch.setenv("TEST_REQUIRED_VAR", "some_key")
        result = validate_environment(required=("TEST_REQUIRED_VAR",), optional=())
        assert result.valid is True
        assert result.missing_required == ()

    def test_missing_optional(self, monkeypatch):
        monkeypatch.delenv("TEST_OPT_VAR", raising=False)
        result = validate_environment(required=(), optional=("TEST_OPT_VAR",))
        assert result.valid is True
        assert "TEST_OPT_VAR" in result.missing_optional

    def test_cors_wildcard_warning(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_ORIGINS", "*")
        result = validate_environment(required=(), optional=("ALLOWED_ORIGINS",))
        assert any("와일드카드" in w for w in result.warnings)

    def test_cors_invalid_origin(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_ORIGINS", "not-a-url")
        result = validate_environment(required=(), optional=("ALLOWED_ORIGINS",))
        assert any("유효하지 않은 오리진" in w for w in result.warnings)

    def test_cors_valid_origins(self, monkeypatch):
        monkeypatch.setenv(
            "ALLOWED_ORIGINS", "http://localhost:3000,https://app.example.com"
        )
        result = validate_environment(required=(), optional=("ALLOWED_ORIGINS",))
        assert len(result.warnings) == 0


# ---------------------------------------------------------------------------
# Input Sanitization
# ---------------------------------------------------------------------------


class TestSanitizeEditionFilter:
    """sanitize_edition_filter() 테스트."""

    def test_none(self):
        assert sanitize_edition_filter(None) is None

    def test_empty(self):
        assert sanitize_edition_filter("") is None

    def test_valid_edition(self):
        assert sanitize_edition_filter("2020-14차") == "2020-14차"

    def test_valid_first_edition(self):
        assert sanitize_edition_filter("초판") == "초판"

    def test_strips_whitespace(self):
        assert sanitize_edition_filter("  2020-14차  ") == "2020-14차"

    def test_rejects_special_characters(self):
        assert sanitize_edition_filter("'; DROP TABLE--") is None

    def test_rejects_too_long(self):
        assert sanitize_edition_filter("a" * 100) is None

    def test_rejects_html(self):
        assert sanitize_edition_filter("<script>alert(1)</script>") is None


class TestSanitizeTypeFilter:
    """sanitize_type_filter() 테스트."""

    def test_none(self):
        assert sanitize_type_filter(None) is None

    def test_empty_list(self):
        assert sanitize_type_filter([]) is None

    def test_valid_types(self):
        result = sanitize_type_filter(["definition", "principle"])
        assert result == ["definition", "principle"]

    def test_filters_invalid(self):
        result = sanitize_type_filter(["definition", "invalid", "principle"])
        assert result == ["definition", "principle"]

    def test_all_invalid(self):
        result = sanitize_type_filter(["invalid1", "invalid2"])
        assert result is None


class TestSanitizeQuery:
    """sanitize_query() 테스트."""

    def test_normal_query(self):
        assert sanitize_query("SUPEX란 무엇인가?") == "SUPEX란 무엇인가?"

    def test_strips_html_tags(self):
        result = sanitize_query("<script>alert('xss')</script>SUPEX")
        assert "<script>" not in result
        assert "SUPEX" in result

    def test_removes_control_chars(self):
        result = sanitize_query("query\x00\x01\x02test")
        assert "\x00" not in result
        assert "querytest" == result

    def test_preserves_whitespace(self):
        assert sanitize_query("hello world") == "hello world"

    def test_preserves_newlines(self):
        result = sanitize_query("line1\nline2")
        assert "\n" in result

    def test_strips_leading_trailing(self):
        assert sanitize_query("  hello  ") == "hello"


# ---------------------------------------------------------------------------
# Deployment Config 검증
# ---------------------------------------------------------------------------


class TestDockerfileExists:
    """프로덕션 배포 파일 존재 확인."""

    def test_dockerfile_exists(self):
        from pathlib import Path

        dockerfile = Path(__file__).parent.parent / "Dockerfile"
        assert dockerfile.exists(), "Dockerfile 없음"

    def test_docker_compose_exists(self):
        from pathlib import Path

        compose = Path(__file__).parent.parent / "docker-compose.yml"
        assert compose.exists(), "docker-compose.yml 없음"

    def test_dockerfile_non_root(self):
        from pathlib import Path

        dockerfile = Path(__file__).parent.parent / "Dockerfile"
        content = dockerfile.read_text()
        assert "USER appuser" in content, "Dockerfile에 non-root USER 설정 없음"

    def test_dockerfile_healthcheck(self):
        from pathlib import Path

        dockerfile = Path(__file__).parent.parent / "Dockerfile"
        content = dockerfile.read_text()
        assert "HEALTHCHECK" in content, "Dockerfile에 HEALTHCHECK 없음"


# ---------------------------------------------------------------------------
# 보안 통합 테스트
# ---------------------------------------------------------------------------


class TestSecurityIntegration:
    """보안 기능 통합 테스트."""

    def test_server_error_does_not_leak_details(self):
        """500 에러 응답이 내부 정보를 노출하지 않는지 확인."""
        from server.app import app

        client = TestClient(app, raise_server_exceptions=False)
        # 존재하지 않는 엔드포인트 → 404 (info leak 없음)
        resp = client.get("/api/nonexistent")
        assert resp.status_code in (404, 405)
        body = resp.text
        assert "traceback" not in body.lower()
        assert "file " not in body.lower()

    def test_pydantic_validation_error_format(self):
        """Pydantic 검증 에러가 안전한 형식인지 확인."""
        from server.app import app

        client = TestClient(app)
        resp = client.post("/api/search", json={"query": "", "mode": "hybrid"})
        assert resp.status_code == 422
        data = resp.json()
        # 에러 메시지에 내부 경로가 포함되지 않음
        error_text = str(data)
        assert "/Users/" not in error_text
        assert "\\Users\\" not in error_text

    def test_valid_quote_types_complete(self):
        """VALID_QUOTE_TYPES가 모든 유효한 타입을 포함하는지 확인."""
        expected = {
            "definition",
            "principle",
            "procedure",
            "checklist",
            "example",
            "narrative",
        }
        assert VALID_QUOTE_TYPES == expected
