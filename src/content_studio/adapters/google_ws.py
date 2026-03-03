"""Google Workspace 문서 배포 어댑터.

PR-048: Google Drive 기반 콘텐츠 배포.

Google Drive에 파일을 업로드하고 공유 링크를 생성한다.
DocumentPublisher 프로토콜을 구현한다.

현재 mock 구현: 실제 Google API 통합은 추후 진행.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GoogleWSConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GoogleWSConfig:
    """Google Workspace 어댑터 설정 (불변).

    Attributes:
        credentials_path: 서비스 계정 JSON 키 파일 경로.
        folder_id: 업로드 대상 Drive 폴더 ID.
        auto_convert: Google Docs 형식으로 자동 변환 여부.
    """

    credentials_path: str = ""
    folder_id: str = ""
    auto_convert: bool = True


# ---------------------------------------------------------------------------
# GoogleWorkspaceAdapter
# ---------------------------------------------------------------------------


class GoogleWorkspaceAdapter:
    """Google Workspace 문서 배포 어댑터.

    Google Drive API를 통해 파일을 업로드한다.
    DocumentPublisher 프로토콜을 구현한다.

    현재 mock 구현: URL만 생성하고 실제 API 호출은 하지 않는다.
    """

    def __init__(self, config: GoogleWSConfig | None = None) -> None:
        self._config = config or GoogleWSConfig()

    async def is_available(self) -> bool:
        """credentials 파일이 존재하는지 확인한다."""
        if not self._config.credentials_path:
            return False
        return Path(self._config.credentials_path).exists()

    async def health_check(self) -> dict[str, Any]:
        """어댑터 상태를 반환한다."""
        available = await self.is_available()
        return {
            "status": "ok" if available else "error",
            "adapter": "google_ws",
            "has_credentials": bool(self._config.credentials_path),
            "folder_id": self._config.folder_id,
            "auto_convert": self._config.auto_convert,
        }

    async def publish(
        self,
        content: dict[str, Any],
        destination: str,
        metadata: dict[str, Any],
    ) -> str | None:
        """콘텐츠를 Google Drive에 업로드한다.

        Args:
            content: 배포할 콘텐츠 데이터.
            destination: 배포 대상 식별자.
            metadata: 배포 메타데이터 (제목, 작성자 등).

        Returns:
            Google Drive 파일 URL 또는 None (실패 시).
        """
        if not await self.is_available():
            logger.warning("Google Workspace credentials가 설정되지 않았습니다")
            return None

        try:
            # Mock: 콘텐츠 해시 기반 파일 ID 생성
            content_str = str(sorted(content.items())) if content else ""
            file_hash = hashlib.sha256(content_str.encode()).hexdigest()[:16]
            url = f"https://drive.google.com/file/d/{file_hash}"

            logger.info("Google Drive 업로드 완료: %s", url)
            return url

        except Exception:
            logger.warning("Google Drive 업로드 실패", exc_info=True)
            return None
