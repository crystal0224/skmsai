"""Content Studio MCP 어댑터 베이스 프로토콜 정의.

PR-041: MCP Adapter Base.

모든 MCP 어댑터가 구현해야 할 Protocol 인터페이스를 정의한다.
- MCPAdapter: 공통 (가용성 확인, 헬스체크)
- ImageGenerator: 이미지 생성/편집
- ChartGenerator: 차트/시각화 생성
- AudioGenerator: TTS 오디오 생성
- DocumentPublisher: 문서 배포
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from scripts.lib.content_studio.models import GeneratedAsset


# ---------------------------------------------------------------------------
# MCPAdapter (공통 베이스)
# ---------------------------------------------------------------------------


@runtime_checkable
class MCPAdapter(Protocol):
    """MCP 어댑터 공통 인터페이스.

    모든 어댑터는 가용성 확인과 헬스체크를 지원해야 한다.
    """

    async def is_available(self) -> bool:
        """어댑터가 사용 가능한지 확인한다."""
        ...

    async def health_check(self) -> dict[str, Any]:
        """어댑터 상태를 반환한다.

        Returns:
            {"status": "ok"|"error", "adapter": str, ...} 형태.
        """
        ...


# ---------------------------------------------------------------------------
# ImageGenerator
# ---------------------------------------------------------------------------


@runtime_checkable
class ImageGenerator(MCPAdapter, Protocol):
    """이미지 생성 어댑터 인터페이스.

    프롬프트 기반 이미지 생성 및 편집을 지원한다.
    API 오류 시 None을 반환하고 경고 로그를 남긴다.
    """

    async def generate_image(
        self,
        prompt: str,
        width: int,
        height: int,
        style: str,
    ) -> GeneratedAsset | None:
        """프롬프트로 이미지를 생성한다.

        Args:
            prompt: 이미지 생성 프롬프트.
            width: 이미지 너비 (px).
            height: 이미지 높이 (px).
            style: 시각 스타일 (예: "professional", "casual").

        Returns:
            생성된 에셋 또는 None (실패 시).
        """
        ...

    async def edit_image(
        self,
        image_path: str,
        edit_prompt: str,
    ) -> GeneratedAsset | None:
        """기존 이미지를 편집한다.

        Args:
            image_path: 원본 이미지 경로.
            edit_prompt: 편집 프롬프트.

        Returns:
            편집된 에셋 또는 None (실패 시).
        """
        ...


# ---------------------------------------------------------------------------
# ChartGenerator
# ---------------------------------------------------------------------------


@runtime_checkable
class ChartGenerator(MCPAdapter, Protocol):
    """차트/시각화 생성 어댑터 인터페이스.

    AntV 등을 통해 데이터 시각화를 생성한다.
    """

    async def generate_chart(
        self,
        chart_type: str,
        data: dict[str, Any],
        options: dict[str, Any],
    ) -> GeneratedAsset | None:
        """차트를 생성한다.

        Args:
            chart_type: 차트 유형 (bar, line, pie, radar 등).
            data: 차트 데이터.
            options: 차트 옵션 (테마, 색상, 크기 등).

        Returns:
            생성된 에셋 또는 None (실패 시).
        """
        ...


# ---------------------------------------------------------------------------
# AudioGenerator
# ---------------------------------------------------------------------------


@runtime_checkable
class AudioGenerator(MCPAdapter, Protocol):
    """오디오 생성 어댑터 인터페이스.

    ElevenLabs 등을 통해 TTS 오디오를 생성한다.
    """

    async def text_to_speech(
        self,
        text: str,
        voice: str,
        language: str,
    ) -> GeneratedAsset | None:
        """텍스트를 음성으로 변환한다.

        Args:
            text: 변환할 텍스트.
            voice: 음성 ID 또는 이름.
            language: 언어 코드 (예: "ko", "en").

        Returns:
            생성된 에셋 또는 None (실패 시).
        """
        ...


# ---------------------------------------------------------------------------
# DocumentPublisher
# ---------------------------------------------------------------------------


@runtime_checkable
class DocumentPublisher(MCPAdapter, Protocol):
    """문서 배포 어댑터 인터페이스.

    생성된 콘텐츠를 사내 플랫폼에 배포한다.
    """

    async def publish(
        self,
        content: dict[str, Any],
        destination: str,
        metadata: dict[str, Any],
    ) -> str | None:
        """콘텐츠를 배포한다.

        Args:
            content: 배포할 콘텐츠 데이터.
            destination: 배포 대상 (URL, 경로 등).
            metadata: 배포 메타데이터 (제목, 작성자 등).

        Returns:
            배포 URL 또는 None (실패 시).
        """
        ...
