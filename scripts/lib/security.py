"""보안 강화 모듈.

PR-038: Rate Limiter, 환경변수 검증, 입력 살균.

Thread-safe rate limiter + 프로덕션 환경 검증.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Immutable types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RateLimitConfig:
    """Rate limit 설정 (불변)."""

    requests_per_minute: int = 60
    burst_size: int = 10
    enabled: bool = True


@dataclass(frozen=True)
class RateLimitResult:
    """Rate limit 판정 결과 (불변)."""

    allowed: bool
    remaining: int
    retry_after_seconds: float
    client_id: str


@dataclass(frozen=True)
class EnvValidationResult:
    """환경변수 검증 결과 (불변)."""

    valid: bool
    missing_required: tuple[str, ...]
    missing_optional: tuple[str, ...]
    warnings: tuple[str, ...]


# ---------------------------------------------------------------------------
# Rate Limiter (Token Bucket)
# ---------------------------------------------------------------------------


class RateLimiter:
    """Token Bucket 기반 Rate Limiter.

    클라이언트(IP)별로 독립적인 버킷을 관리한다.
    """

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self._config = config or RateLimitConfig()
        self._lock = threading.Lock()
        # client_id → (tokens, last_refill_time)
        self._buckets: dict[str, list[float]] = defaultdict(
            lambda: [float(self._config.burst_size), time.time()]
        )

    @property
    def config(self) -> RateLimitConfig:
        return self._config

    def check(self, client_id: str) -> RateLimitResult:
        """요청 허용 여부를 판정한다."""
        if not self._config.enabled:
            return RateLimitResult(
                allowed=True,
                remaining=self._config.burst_size,
                retry_after_seconds=0.0,
                client_id=client_id,
            )

        with self._lock:
            bucket = self._buckets[client_id]
            tokens = bucket[0]
            last_refill = bucket[1]

            now = time.time()
            elapsed = now - last_refill
            refill_rate = self._config.requests_per_minute / 60.0
            new_tokens = min(
                self._config.burst_size,
                tokens + elapsed * refill_rate,
            )

            bucket[1] = now

            if new_tokens >= 1.0:
                bucket[0] = new_tokens - 1.0
                return RateLimitResult(
                    allowed=True,
                    remaining=int(bucket[0]),
                    retry_after_seconds=0.0,
                    client_id=client_id,
                )

            bucket[0] = new_tokens
            retry_after = (1.0 - new_tokens) / refill_rate if refill_rate > 0 else 60.0
            return RateLimitResult(
                allowed=False,
                remaining=0,
                retry_after_seconds=round(retry_after, 2),
                client_id=client_id,
            )

    def reset(self, client_id: str | None = None) -> None:
        """버킷을 초기화한다."""
        with self._lock:
            if client_id:
                if client_id in self._buckets:
                    del self._buckets[client_id]
            else:
                self._buckets.clear()


# ---------------------------------------------------------------------------
# Environment Validation
# ---------------------------------------------------------------------------

REQUIRED_ENV_VARS = ("OPENAI_API_KEY",)

OPTIONAL_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "PINECONE_API_KEY",
    "COHERE_API_KEY",
    "ALLOWED_ORIGINS",
)


def validate_environment(
    *,
    required: tuple[str, ...] = REQUIRED_ENV_VARS,
    optional: tuple[str, ...] = OPTIONAL_ENV_VARS,
) -> EnvValidationResult:
    """환경변수 설정을 검증한다.

    Returns:
        EnvValidationResult with missing vars and warnings.
    """
    missing_required: list[str] = []
    missing_optional: list[str] = []
    warnings: list[str] = []

    for var in required:
        value = os.environ.get(var)
        if not value:
            missing_required.append(var)

    for var in optional:
        value = os.environ.get(var)
        if not value:
            missing_optional.append(var)

    # CORS 설정 검증
    origins = os.environ.get("ALLOWED_ORIGINS", "")
    if origins:
        for origin in origins.split(","):
            origin = origin.strip()
            if origin == "*":
                warnings.append("ALLOWED_ORIGINS에 와일드카드(*) 사용 — 프로덕션에서는 비추천")
            elif not origin.startswith(("http://", "https://")):
                warnings.append(f"ALLOWED_ORIGINS에 유효하지 않은 오리진: {origin!r}")

    valid = len(missing_required) == 0

    return EnvValidationResult(
        valid=valid,
        missing_required=tuple(missing_required),
        missing_optional=tuple(missing_optional),
        warnings=tuple(warnings),
    )


# ---------------------------------------------------------------------------
# Input Sanitization
# ---------------------------------------------------------------------------

# 허용된 개정판 ID 패턴: "YYYY-N차" 또는 "초판" 등
_EDITION_PATTERN = re.compile(r"^[\w가-힣\-\.\s]{1,50}$")

# 허용된 타입 목록
VALID_QUOTE_TYPES = frozenset(
    {
        "definition",
        "principle",
        "procedure",
        "checklist",
        "example",
        "narrative",
    }
)


def sanitize_edition_filter(value: str | None) -> str | None:
    """edition_filter 입력을 검증한다.

    Returns:
        검증된 값 또는 None (유효하지 않은 경우).
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not _EDITION_PATTERN.match(value):
        logger.warning("유효하지 않은 edition_filter 입력: %r", value[:50])
        return None
    return value


def sanitize_type_filter(values: list[str] | None) -> list[str] | None:
    """type_filter 입력을 검증한다.

    Returns:
        유효한 타입만 포함된 리스트 또는 None.
    """
    if values is None:
        return None
    valid = [v for v in values if v in VALID_QUOTE_TYPES]
    return valid if valid else None


def sanitize_query(query: str) -> str:
    """쿼리 문자열을 살균한다.

    HTML 태그, 제어 문자를 제거한다.
    """
    # 제어 문자 제거 (탭, 줄바꿈은 허용)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", query)
    # HTML 태그 제거
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    return cleaned.strip()
