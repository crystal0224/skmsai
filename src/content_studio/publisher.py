"""Publisher 서비스 — 콘텐츠를 다양한 플랫폼에 배포.

PR-048: Publisher Service + Notion/Google Workspace Adapters.

생성된 콘텐츠를 로컬, Notion, Google Workspace 등에 배포한다.
어댑터 레지스트리 패턴으로 배포 대상을 유연하게 확장할 수 있다.

배포 전략:
- "local": 파일이 이미 output/에 있으므로 항상 성공.
- 기타: 등록된 DocumentPublisher 어댑터에 위임.
- 부분 실패 허용: 한 대상이 실패해도 나머지는 계속 진행.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.content_studio.adapters.base import DocumentPublisher

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PublishResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PublishResult:
    """배포 결과 (불변).

    Attributes:
        destination: 배포 대상 이름 (예: "local", "notion", "google_ws").
        url: 배포된 URL (실패 시 None).
        success: 배포 성공 여부.
        error: 에러 메시지 (성공 시 None).
        timestamp: 배포 시각 (ISO 8601).
    """

    destination: str
    url: str | None
    success: bool
    error: str | None
    timestamp: str


# ---------------------------------------------------------------------------
# Publisher
# ---------------------------------------------------------------------------


class Publisher:
    """콘텐츠 배포 서비스.

    어댑터 레지스트리를 통해 다양한 플랫폼에 배포한다.
    "local" 대상은 어댑터 없이 항상 성공으로 처리한다.
    부분 실패 시에도 나머지 대상에 대해 계속 진행한다.
    """

    def __init__(self, adapters: dict[str, DocumentPublisher] | None = None) -> None:
        self._adapters: dict[str, DocumentPublisher] = dict(adapters or {})

    def register(self, name: str, adapter: DocumentPublisher) -> None:
        """어댑터를 레지스트리에 등록한다.

        Args:
            name: 어댑터 이름 (배포 대상 이름과 동일).
            adapter: DocumentPublisher 프로토콜 구현체.
        """
        self._adapters[name] = adapter

    async def publish(
        self,
        result: Any,
        destinations: list[str],
    ) -> tuple[PublishResult, ...]:
        """콘텐츠를 지정된 대상에 배포한다.

        Args:
            result: 배포할 콘텐츠 결과 (ContentResult 등).
            destinations: 배포 대상 이름 목록.

        Returns:
            배포 결과 튜플 (불변). 각 대상에 대한 결과를 포함한다.
        """
        results: list[PublishResult] = []

        for dest in destinations:
            ts = datetime.now(tz=timezone.utc).isoformat()

            if dest == "local":
                results.append(
                    PublishResult(
                        destination="local",
                        url=None,
                        success=True,
                        error=None,
                        timestamp=ts,
                    )
                )
                continue

            adapter = self._adapters.get(dest)
            if adapter is None:
                logger.warning("등록되지 않은 배포 대상: %s", dest)
                results.append(
                    PublishResult(
                        destination=dest,
                        url=None,
                        success=False,
                        error=f"등록되지 않은 배포 대상: {dest}",
                        timestamp=ts,
                    )
                )
                continue

            try:
                content = (
                    result.to_dict() if hasattr(result, "to_dict") else {"data": result}
                )
                metadata = dict(result.metadata) if hasattr(result, "metadata") else {}
                url = await adapter.publish(content, dest, metadata)
                results.append(
                    PublishResult(
                        destination=dest,
                        url=url,
                        success=url is not None,
                        error=None if url is not None else f"{dest} 배포 실패",
                        timestamp=ts,
                    )
                )
            except Exception as exc:
                logger.warning("배포 실패 (%s): %s", dest, exc, exc_info=True)
                results.append(
                    PublishResult(
                        destination=dest,
                        url=None,
                        success=False,
                        error=str(exc),
                        timestamp=ts,
                    )
                )

        return tuple(results)
