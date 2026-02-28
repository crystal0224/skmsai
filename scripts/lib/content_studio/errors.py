"""Content Studio 전용 예외 클래스 계층.

PR-047 Cross-Cutting: 파이프라인 각 단계별 전용 예외.
"""
from __future__ import annotations


class ContentStudioError(Exception):
    """Content Studio 기본 예외."""

    def __init__(self, message: str, stage: str = "unknown") -> None:
        self.stage = stage
        super().__init__(message)


class PlanningError(ContentStudioError):
    """LLM 아웃라인 생성 실패."""

    def __init__(self, message: str) -> None:
        super().__init__(message, stage="planning")


class GenerationError(ContentStudioError):
    """RAG 검색/콘텐츠 생성 실패."""

    def __init__(self, message: str) -> None:
        super().__init__(message, stage="generation")


class AssetError(ContentStudioError):
    """MCP 어댑터 호출 실패."""

    def __init__(self, message: str) -> None:
        super().__init__(message, stage="asset_generation")


class AssemblyError(ContentStudioError):
    """파일 조립 실패."""

    def __init__(self, message: str) -> None:
        super().__init__(message, stage="assembly")


class PublishError(ContentStudioError):
    """배포 실패."""

    def __init__(self, message: str) -> None:
        super().__init__(message, stage="publishing")
