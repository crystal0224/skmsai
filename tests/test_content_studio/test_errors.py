"""Content Studio 에러 계층 테스트.

PR-047 Cross-Cutting: 에러 클래스 검증.
"""
from __future__ import annotations

import pytest

from src.content_studio.errors import (
    AssemblyError,
    AssetError,
    ContentStudioError,
    GenerationError,
    PlanningError,
    PublishError,
)


class TestErrorHierarchy:
    def test_base_error(self):
        err = ContentStudioError("테스트 에러")
        assert str(err) == "테스트 에러"
        assert err.stage == "unknown"

    def test_base_error_with_stage(self):
        err = ContentStudioError("테스트", stage="custom")
        assert err.stage == "custom"

    def test_planning_error(self):
        err = PlanningError("LLM 실패")
        assert isinstance(err, ContentStudioError)
        assert err.stage == "planning"
        assert str(err) == "LLM 실패"

    def test_generation_error(self):
        err = GenerationError("RAG 실패")
        assert isinstance(err, ContentStudioError)
        assert err.stage == "generation"

    def test_asset_error(self):
        err = AssetError("MCP 실패")
        assert isinstance(err, ContentStudioError)
        assert err.stage == "asset_generation"

    def test_assembly_error(self):
        err = AssemblyError("파일 조립 실패")
        assert isinstance(err, ContentStudioError)
        assert err.stage == "assembly"

    def test_publish_error(self):
        err = PublishError("배포 실패")
        assert isinstance(err, ContentStudioError)
        assert err.stage == "publishing"

    def test_all_are_exceptions(self):
        """모든 에러 클래스는 Exception의 서브클래스."""
        for cls in (
            ContentStudioError,
            PlanningError,
            GenerationError,
            AssetError,
            AssemblyError,
            PublishError,
        ):
            err = cls("test")
            assert isinstance(err, Exception)

    def test_catch_by_base(self):
        """기본 클래스로 모든 하위 에러를 캐치할 수 있다."""
        errors = [
            PlanningError("p"),
            GenerationError("g"),
            AssetError("a"),
            AssemblyError("as"),
            PublishError("pu"),
        ]
        for err in errors:
            with pytest.raises(ContentStudioError):
                raise err

    def test_stages_unique(self):
        """각 에러 클래스의 stage는 고유하다."""
        stages = {
            PlanningError("t").stage,
            GenerationError("t").stage,
            AssetError("t").stage,
            AssemblyError("t").stage,
            PublishError("t").stage,
        }
        assert len(stages) == 5
