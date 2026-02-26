"""SearchHit — 검색 결과 표준 반환 타입.

PR-011: Vector Store + Search API.

retrieval.py의 dict 반환 형식과 별도. PR-013 FastAPI에서 정규 포맷을 선택한다.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchHit:
    """검색 결과 단건 — 불변.

    Attributes:
        quote_id:     고유 식별자
        text:         인용 원문
        score:        검색 점수 (0~1)
        edition_id:   개정판 식별자
        year:         출판 연도
        revision_num: 개정 차수
        quote_type:   인용 유형
        section_path: 섹션 경로
        source:       검색 소스 ("vector" | "bm25" | "hybrid")
        content_hash: SHA-256 해시
        quality_flags: 품질 플래그
    """

    quote_id: str
    text: str
    score: float
    edition_id: str
    year: int
    revision_num: int
    quote_type: str
    section_path: tuple[str, ...]
    source: str
    content_hash: str
    quality_flags: tuple[str, ...]
