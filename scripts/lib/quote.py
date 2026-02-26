"""QuoteObject — SKMS 인용 객체 불변 도메인 모델.

PR-009: QuoteObject Schema + DB Migration.

모든 필드는 불변(frozen). 컬렉션은 tuple 사용.
content_hash(SHA-256)로 멱등성(idempotency) 보장.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Edition mapping — year/revision_num extraction from edition_id string
# ---------------------------------------------------------------------------

# (year, revision_num) — 2차~4차는 OCR 원본에 미수록.
_EDITION_META: dict[str, tuple[int, int]] = {
    "1979-초판": (1979, 0),
    "1981-1차": (1981, 1),
    # 2차~4차 개정판 없음 (OCR 원본 미존재)
    "1988-5차": (1988, 5),
    "1989-6차": (1989, 6),
    "1990-7차": (1990, 7),
    "1995-8차": (1995, 8),
    "1997-9차": (1997, 9),
    "1998-10차": (1998, 10),
    "2004-11차": (2004, 11),
    "2008-12차": (2008, 12),
    "2016-13차": (2016, 13),
    "2020-14차": (2020, 14),
}

# 유효 타입 집합 (02_extract_quotes.py에서 추출하는 6종)
VALID_QUOTE_TYPES: frozenset[str] = frozenset(
    {"narrative", "definition", "checklist", "principle", "example", "procedure"}
)


def _parse_year(edition_id: str) -> int:
    """edition_id 문자열에서 연도를 추출한다."""
    if edition_id in _EDITION_META:
        return _EDITION_META[edition_id][0]
    match = re.match(r"(\d{4})", edition_id)
    if match:
        return int(match.group(1))
    raise ValueError(f"edition_id에서 연도를 추출할 수 없습니다: {edition_id!r}")


def _parse_revision(edition_id: str) -> int:
    """edition_id 문자열에서 개정 차수를 추출한다."""
    if edition_id in _EDITION_META:
        return _EDITION_META[edition_id][1]
    rev_match = re.search(r"(\d+)차", edition_id)
    if rev_match:
        return int(rev_match.group(1))
    if "초판" in edition_id:
        return 0
    raise ValueError(f"edition_id에서 차수를 추출할 수 없습니다: {edition_id!r}")


# ---------------------------------------------------------------------------
# QuoteObject — 불변 도메인 모델
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QuoteObject:
    """SKMS 인용 객체 — 불변 도메인 모델.

    Attributes:
        quote_id:     고유 식별자 (예: "1979-초판|기업관|narrative|001")
        text:         인용 원문
        edition_id:   개정판 식별자 (예: "1979-초판", "2020-14차")
        year:         출판 연도 (예: 1979, 2020)
        revision_num: 개정 차수 (초판=0, 1차=1, ..., 14차=14)
        quote_type:   인용 유형 (narrative, definition, checklist 등 6종)
        section_path: 섹션 경로 (tuple, 예: ("기업관", "1. 인간중심의 경영"))
        start_line:   시작 라인 (1-based)
        char_span:    문자 오프셋 범위 (start, end)
        token_count:  토큰 수
        content_hash: SHA-256 해시 (멱등성 키)
        quality_flags: 품질 플래그 (tuple)
        is_definition: 정의 블록 여부
    """

    quote_id: str
    text: str
    edition_id: str
    year: int
    revision_num: int
    quote_type: str
    section_path: tuple[str, ...]
    start_line: int
    char_span: tuple[int, int]
    token_count: int
    content_hash: str
    quality_flags: tuple[str, ...] = field(default_factory=tuple)
    is_definition: bool = False

    def __post_init__(self) -> None:
        """생성 시 불변 제약 조건을 검증한다."""
        if not self.quote_id:
            raise ValueError("quote_id는 빈 문자열일 수 없습니다")
        if not self.text:
            raise ValueError("text는 빈 문자열일 수 없습니다")
        if not self.edition_id:
            raise ValueError("edition_id는 빈 문자열일 수 없습니다")
        if self.year < 1979 or self.year > 2100:
            raise ValueError(f"year 범위 초과: {self.year}")
        if self.revision_num < 0 or self.revision_num > 30:
            raise ValueError(f"revision_num 범위 초과: {self.revision_num}")
        if self.quote_type not in VALID_QUOTE_TYPES:
            raise ValueError(f"유효하지 않은 quote_type: {self.quote_type!r}")
        if self.start_line < 1:
            raise ValueError(f"start_line은 1 이상이어야 합니다: {self.start_line}")
        if len(self.char_span) != 2:
            raise ValueError(f"char_span은 (start, end) 2-tuple이어야 합니다")
        if self.char_span[0] < 0 or self.char_span[1] < self.char_span[0]:
            raise ValueError(
                f"char_span 범위 오류: start={self.char_span[0]}, end={self.char_span[1]}"
            )
        if not self.content_hash or len(self.content_hash) != 64:
            raise ValueError(
                f"content_hash는 64자 SHA-256 해시여야 합니다: "
                f"len={len(self.content_hash) if self.content_hash else 0}"
            )

    @staticmethod
    def compute_hash(text: str, edition_id: str, start_line: int) -> str:
        """결정론적 content_hash를 생성한다.

        동일 입력에 대해 항상 동일한 해시 반환 (멱등성).
        """
        raw = f"{text}|{edition_id}|{start_line}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """JSON 직렬화 가능한 dict로 변환한다."""
        return {
            "quote_id": self.quote_id,
            "text": self.text,
            "edition_id": self.edition_id,
            "year": self.year,
            "revision_num": self.revision_num,
            "quote_type": self.quote_type,
            "section_path": list(self.section_path),
            "start_line": self.start_line,
            "char_span": list(self.char_span),
            "token_count": self.token_count,
            "content_hash": self.content_hash,
            "quality_flags": list(self.quality_flags),
            "is_definition": self.is_definition,
        }

    @classmethod
    def from_legacy(cls, record: dict[str, Any]) -> QuoteObject:
        """기존 quotes.jsonl 레코드를 QuoteObject로 변환한다.

        Legacy fields → QuoteObject mapping:
          quote_id     → quote_id (그대로)
          edition_id   → edition_id (그대로) + year, revision_num (파생)
          type         → quote_type
          section_path → section_path (list → tuple)
          text         → text
          char_span    → char_span (list → tuple)
          start_line   → start_line
          token_count  → token_count
          sha256       → content_hash
          quality_flags→ quality_flags (list → tuple)
          (파생)       → is_definition (type == "definition")
        """
        _REQUIRED = {
            "edition_id",
            "type",
            "text",
            "start_line",
            "quote_id",
            "char_span",
        }
        missing = _REQUIRED - record.keys()
        if missing:
            raise ValueError(f"legacy record에 필수 필드가 없습니다: {missing}")

        edition_id = record["edition_id"]
        quote_type = record["type"]
        text = record["text"]
        start_line = record["start_line"]

        # content_hash: 기존 sha256 사용 또는 새로 계산
        content_hash = record.get("sha256") or cls.compute_hash(
            text, edition_id, start_line
        )

        return cls(
            quote_id=record["quote_id"],
            text=text,
            edition_id=edition_id,
            year=_parse_year(edition_id),
            revision_num=_parse_revision(edition_id),
            quote_type=quote_type,
            section_path=tuple(record.get("section_path", ())),
            start_line=start_line,
            char_span=tuple(record["char_span"]),
            token_count=record.get("token_count", 0),
            content_hash=content_hash,
            quality_flags=tuple(record.get("quality_flags", ())),
            is_definition=(quote_type == "definition"),
        )

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> QuoteObject:
        """DB 행(dict)에서 QuoteObject를 복원한다."""
        return cls(
            quote_id=row["quote_id"],
            text=row["text"],
            edition_id=row["edition_id"],
            year=row["year"],
            revision_num=row["revision_num"],
            quote_type=row["quote_type"],
            section_path=tuple(json.loads(row["section_path"])),
            start_line=row["start_line"],
            char_span=(row["char_span_start"], row["char_span_end"]),
            token_count=row["token_count"],
            content_hash=row["content_hash"],
            quality_flags=tuple(json.loads(row["quality_flags"])),
            is_definition=bool(row["is_definition"]),
        )
