"""Notion 문서 배포 어댑터.

PR-048: Notion API 기반 콘텐츠 배포.

Notion 데이터베이스에 콘텐츠를 페이지로 생성한다.
DocumentPublisher 프로토콜을 구현한다.

현재 mock 구현: 실제 Notion API 통합은 추후 진행.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# NotionConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NotionConfig:
    """Notion 어댑터 설정 (불변).

    Attributes:
        api_key: Notion Integration API 키.
        database_id: 대상 데이터베이스 ID.
        workspace_name: 워크스페이스 이름.
    """

    api_key: str = ""
    database_id: str = ""
    workspace_name: str = "SKMS"


# ---------------------------------------------------------------------------
# NotionAdapter
# ---------------------------------------------------------------------------


class NotionAdapter:
    """Notion 문서 배포 어댑터.

    Notion API를 통해 콘텐츠를 데이터베이스 페이지로 생성한다.
    DocumentPublisher 프로토콜을 구현한다.

    현재 mock 구현: URL만 생성하고 실제 API 호출은 하지 않는다.
    """

    def __init__(self, config: NotionConfig | None = None) -> None:
        self._config = config or NotionConfig()

    async def is_available(self) -> bool:
        """API 키가 설정되어 있는지 확인한다."""
        return bool(self._config.api_key)

    async def health_check(self) -> dict[str, Any]:
        """어댑터 상태를 반환한다."""
        available = await self.is_available()
        return {
            "status": "ok" if available else "error",
            "adapter": "notion",
            "has_api_key": bool(self._config.api_key),
            "database_id": self._config.database_id,
            "workspace_name": self._config.workspace_name,
        }

    async def publish(
        self,
        content: dict[str, Any],
        destination: str,
        metadata: dict[str, Any],
    ) -> str | None:
        """콘텐츠를 Notion 데이터베이스에 배포한다.

        Args:
            content: 배포할 콘텐츠 데이터.
            destination: 배포 대상 식별자.
            metadata: 배포 메타데이터 (제목, 작성자 등).

        Returns:
            Notion 페이지 URL 또는 None (실패 시).
        """
        if not await self.is_available():
            logger.warning("Notion API 키가 설정되지 않았습니다")
            return None

        try:
            # Mock: 콘텐츠 해시 기반 페이지 ID 생성
            content_str = str(sorted(content.items())) if content else ""
            page_hash = hashlib.sha256(content_str.encode()).hexdigest()[:12]
            url = f"https://notion.so/{self._config.database_id}/page-{page_hash}"

            logger.info("Notion 배포 완료: %s", url)
            return url

        except Exception:
            logger.warning("Notion 배포 실패", exc_info=True)
            return None
