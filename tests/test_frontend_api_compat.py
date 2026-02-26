"""프론트엔드 API 호환성 테스트.

PR-034: Next.js V2 프론트엔드가 사용하는 API 엔드포인트와
서버 모델 간의 스키마 호환성을 검증한다.

프론트엔드 TypeScript 타입 (frontend/src/types/api.ts)이
서버 Pydantic 모델 (server/models.py)과 1:1 대응하는지 확인.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from server.models import (  # noqa: E402
    EditionInfoResponse,
    EditionsListResponse,
    ErrorResponse,
    GenerateRequest,
    GenerateResponse,
    GenerateV2Request,
    GenerateV2Response,
    HealthResponse,
    SearchHitResponse,
    SearchRequest,
    SearchResponse,
    SearchV2Request,
    SearchV2Response,
    TOCNodeResponse,
    TOCResponse,
    TOCSectionSearchResponse,
)


# ---------------------------------------------------------------------------
# 헬퍼: TypeScript 타입 파일에서 인터페이스 필드 추출
# ---------------------------------------------------------------------------


def _load_ts_types() -> str:
    """frontend/src/types/api.ts 내용을 로드한다."""
    path = _PROJECT_ROOT / "frontend" / "src" / "types" / "api.ts"
    if not path.exists():
        pytest.skip("frontend/src/types/api.ts 없음")
    return path.read_text(encoding="utf-8")


def _extract_ts_interface_fields(ts_content: str, interface_name: str) -> set[str]:
    """TypeScript 인터페이스에서 필드명을 추출한다."""
    # export interface Foo { ... } 패턴 매칭
    pattern = (
        rf"export interface {interface_name}(?:\s+extends\s+\w+)?\s*\{{([^}}]+)\}}"
    )
    match = re.search(pattern, ts_content, re.DOTALL)
    if not match:
        return set()

    body = match.group(1)
    fields: set[str] = set()
    for line in body.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        # "fieldName: type" 또는 "fieldName?: type" 패턴
        field_match = re.match(r"(\w+)\??\s*:", line)
        if field_match:
            fields.add(field_match.group(1))
    return fields


def _get_pydantic_fields(model_class: type) -> set[str]:
    """Pydantic 모델에서 필드명을 추출한다."""
    return set(model_class.model_fields.keys())


# ---------------------------------------------------------------------------
# 스키마 호환성 테스트
# ---------------------------------------------------------------------------


class TestApiSchemaCompat:
    """프론트엔드 TS 타입과 서버 Pydantic 모델 간 필드 호환성."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ts_content = _load_ts_types()

    def test_search_hit_fields(self):
        """SearchHit 필드 일치."""
        ts_fields = _extract_ts_interface_fields(self.ts_content, "SearchHit")
        py_fields = _get_pydantic_fields(SearchHitResponse)
        assert (
            ts_fields == py_fields
        ), f"차이: TS={ts_fields - py_fields}, PY={py_fields - ts_fields}"

    def test_search_response_fields(self):
        """SearchResponse 필드 일치."""
        ts_fields = _extract_ts_interface_fields(self.ts_content, "SearchResponse")
        py_fields = _get_pydantic_fields(SearchResponse)
        assert ts_fields == py_fields

    def test_generate_response_fields(self):
        """GenerateResponse 필드 일치."""
        ts_fields = _extract_ts_interface_fields(self.ts_content, "GenerateResponse")
        py_fields = _get_pydantic_fields(GenerateResponse)
        assert ts_fields == py_fields

    def test_generate_v2_response_fields(self):
        """GenerateV2Response — TS에서 extends로 상속하므로 부모+자식 합산."""
        ts_base = _extract_ts_interface_fields(self.ts_content, "GenerateResponse")
        ts_extra = _extract_ts_interface_fields(self.ts_content, "GenerateV2Response")
        ts_all = ts_base | ts_extra
        py_fields = _get_pydantic_fields(GenerateV2Response)
        assert (
            ts_all == py_fields
        ), f"차이: TS={ts_all - py_fields}, PY={py_fields - ts_all}"

    def test_health_response_fields(self):
        """HealthResponse 필드 일치."""
        ts_fields = _extract_ts_interface_fields(self.ts_content, "HealthResponse")
        py_fields = _get_pydantic_fields(HealthResponse)
        assert ts_fields == py_fields

    def test_toc_node_fields(self):
        """TOCNode 필드 일치."""
        ts_fields = _extract_ts_interface_fields(self.ts_content, "TOCNode")
        py_fields = _get_pydantic_fields(TOCNodeResponse)
        assert ts_fields == py_fields

    def test_toc_response_fields(self):
        """TOCResponse 필드 일치."""
        ts_fields = _extract_ts_interface_fields(self.ts_content, "TOCResponse")
        py_fields = _get_pydantic_fields(TOCResponse)
        assert ts_fields == py_fields

    def test_edition_info_fields(self):
        """EditionInfo 필드 일치."""
        ts_fields = _extract_ts_interface_fields(self.ts_content, "EditionInfo")
        py_fields = _get_pydantic_fields(EditionInfoResponse)
        assert ts_fields == py_fields

    def test_editions_list_fields(self):
        """EditionsListResponse 필드 일치."""
        ts_fields = _extract_ts_interface_fields(
            self.ts_content, "EditionsListResponse"
        )
        py_fields = _get_pydantic_fields(EditionsListResponse)
        assert ts_fields == py_fields

    def test_evidence_check_fields(self):
        """EvidenceCheck 필드 일치."""
        from server.models import EvidenceCheckResponse

        ts_fields = _extract_ts_interface_fields(self.ts_content, "EvidenceCheck")
        py_fields = _get_pydantic_fields(EvidenceCheckResponse)
        assert ts_fields == py_fields

    def test_error_response_fields(self):
        """ErrorResponse 필드 일치."""
        ts_fields = _extract_ts_interface_fields(self.ts_content, "ErrorResponse")
        py_fields = _get_pydantic_fields(ErrorResponse)
        assert ts_fields == py_fields


# ---------------------------------------------------------------------------
# API 엔드포인트 존재 여부 테스트
# ---------------------------------------------------------------------------


class TestApiEndpoints:
    """프론트엔드 api-client.ts가 호출하는 엔드포인트가 서버에 존재하는지 확인."""

    @pytest.fixture(autouse=True)
    def setup(self):
        api_client_path = _PROJECT_ROOT / "frontend" / "src" / "lib" / "api-client.ts"
        if not api_client_path.exists():
            pytest.skip("api-client.ts 없음")
        self.api_client = api_client_path.read_text(encoding="utf-8")

    def test_health_endpoint(self):
        """GET /api/health 호출."""
        assert '"/health"' in self.api_client

    def test_search_endpoint(self):
        """POST /api/search 호출."""
        assert '"/search"' in self.api_client

    def test_generate_v2_endpoint(self):
        """POST /api/v2/generate 호출."""
        assert '"/v2/generate"' in self.api_client

    def test_editions_endpoint(self):
        """GET /api/editions 호출."""
        assert '"/editions"' in self.api_client

    def test_toc_endpoint(self):
        """GET /api/toc/{editionId} 호출."""
        assert "/toc/" in self.api_client


# ---------------------------------------------------------------------------
# OutputType 호환성 테스트
# ---------------------------------------------------------------------------


class TestOutputTypeCompat:
    """프론트엔드 OutputType과 서버 OutputType이 동일한지 확인."""

    def test_output_types_match(self):
        """5종 출력 타입 일치."""
        from server.models import OutputType as ServerOutputType

        ts_content = _load_ts_types()
        # TypeScript에서 OutputType union 추출
        ts_types: set[str] = set()
        for match in re.finditer(
            r'"(\w+)"', ts_content.split("export type OutputType")[1].split(";")[0]
        ):
            ts_types.add(match.group(1))

        # Pydantic Literal에서 추출
        py_types = set(ServerOutputType.__args__)

        assert (
            ts_types == py_types
        ), f"차이: TS={ts_types - py_types}, PY={py_types - ts_types}"

    def test_search_mode_match(self):
        """검색 모드 일치."""
        ts_content = _load_ts_types()
        ts_modes: set[str] = set()
        for match in re.finditer(
            r'"(\w+)"', ts_content.split("export type SearchMode")[1].split(";")[0]
        ):
            ts_modes.add(match.group(1))

        expected = {"hybrid", "vector", "bm25"}
        assert ts_modes == expected
