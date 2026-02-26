"""API 요청/응답 Pydantic 모델.

PR-013: FastAPI 서버 스키마 정의.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Search API
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    """검색 요청."""

    query: str = Field(..., min_length=1, max_length=500, description="검색 질의")
    mode: str = Field(
        default="hybrid",
        pattern="^(hybrid|vector|bm25)$",
        description="검색 모드",
    )
    top_k: int = Field(default=5, ge=1, le=50, description="검색 결과 수")
    edition_filter: str | None = Field(default=None, description="개정판 필터 (예: 2020-14차)")
    type_filter: list[str] | None = Field(
        default=None, description="타입 필터 (예: ['definition', 'principle'])"
    )


class SearchHitResponse(BaseModel):
    """검색 결과 단건."""

    quote_id: str
    text: str
    score: float
    edition_id: str
    year: int
    quote_type: str
    section_path: list[str]
    source: str


class SearchResponse(BaseModel):
    """검색 응답."""

    query: str
    mode: str
    hits: list[SearchHitResponse]
    total: int


# ---------------------------------------------------------------------------
# Generate API
# ---------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    """답변 생성 요청."""

    query: str = Field(..., min_length=1, max_length=1000, description="질의")
    output_type: str | None = Field(
        default=None,
        description="출력 유형 (summary, card, quiz, comparison_table, slide)",
    )
    edition_filter: str | None = Field(default=None, description="개정판 필터")
    top_k: int = Field(default=5, ge=1, le=50, description="검색 결과 수")


class GenerateResponse(BaseModel):
    """답변 생성 응답."""

    query: str
    intent: str
    answer: str
    prompt_name: str
    validation_passed: bool | None
    citations: list[str]
    search_hits_count: int


# ---------------------------------------------------------------------------
# Health API
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """헬스체크 응답."""

    status: str
    version: str
    components: dict[str, bool]


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    """에러 응답."""

    error: str
    detail: str | None = None
