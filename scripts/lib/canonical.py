"""Canonical View 조회 모듈 (PR-5).

canonical_2020.jsonl에서 subject 기반으로 canonical 항목을 조회한다.
'기본 정의 질문' 응답 모드에서 사용된다.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Canonical store
# ---------------------------------------------------------------------------


class CanonicalStore:
    """Canonical 항목을 로드하고 subject 기반으로 조회한다.

    immutable: 로드 후 내부 데이터를 변경하지 않는다.
    """

    def __init__(self, items: list[dict]) -> None:
        self._items: tuple[dict, ...] = tuple(items)
        # subject → item 인덱스 (정확 일치 조회용)
        self._by_subject: dict[str, int] = {}
        # subject 키워드 → item 인덱스 목록 (부분 일치 조회용)
        self._keywords: dict[str, list[int]] = {}

        for i, item in enumerate(items):
            subject = item.get("subject", "")
            self._by_subject[subject] = i

            # 키워드 인덱스 (2글자 이상 토큰)
            for token in subject.replace("·", " ").replace("/", " ").split():
                token = token.strip("()")
                if len(token) >= 2:
                    self._keywords.setdefault(token, []).append(i)

    @classmethod
    def load(cls, path: str = "data/processed/canonical_2020.jsonl") -> CanonicalStore:
        """JSONL 파일에서 canonical 항목을 로드한다.

        파일이 없으면 빈 store를 반환한다 (graceful degradation).
        """
        filepath = Path(path)
        if not filepath.exists():
            return cls([])

        items = []
        with open(filepath, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(
                        f"[canonical] 경고: JSON 파싱 오류 (line {line_num}): {e}",
                        file=sys.stderr,
                    )
        return cls(items)

    @property
    def count(self) -> int:
        """저장된 canonical 항목 수."""
        return len(self._items)

    def lookup(self, query: str) -> dict | None:
        """질의에서 canonical 항목을 조회한다.

        조회 우선순위:
          1. subject 정확 일치
          2. subject가 query에 포함 (긴 subject 우선)
          3. query에 subject 키워드가 포함

        Returns:
            매칭된 canonical 항목 dict (새 복사본), 없으면 None
        """
        if not self._items:
            return None

        # 1. 정확 일치
        for subject, idx in self._by_subject.items():
            if subject == query:
                return copy.deepcopy(self._items[idx])

        # 2. subject가 query에 포함 (긴 subject 우선)
        matches = []
        for subject, idx in self._by_subject.items():
            if subject in query:
                matches.append((len(subject), idx))
        if matches:
            matches.sort(reverse=True)  # 긴 subject 우선
            return copy.deepcopy(self._items[matches[0][1]])

        # 3. 키워드 기반 (가장 많은 키워드 매칭)
        scores: dict[int, int] = {}
        for token, indices in self._keywords.items():
            if token in query:
                for idx in indices:
                    scores[idx] = scores.get(idx, 0) + 1

        if scores:
            best_idx = max(scores, key=lambda k: scores[k])
            return copy.deepcopy(self._items[best_idx])

        return None

    def lookup_by_id(self, canonical_id: str) -> dict | None:
        """canonical_id로 항목을 조회한다."""
        for item in self._items:
            if item.get("canonical_id") == canonical_id:
                return copy.deepcopy(item)
        return None

    def all_items(self) -> list[dict]:
        """모든 canonical 항목을 반환한다 (새 리스트)."""
        return [copy.deepcopy(item) for item in self._items]

    def subjects(self) -> list[str]:
        """모든 subject를 반환한다."""
        return list(self._by_subject.keys())


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def load_canonical_store(
    path: str = "data/processed/canonical_2020.jsonl",
) -> CanonicalStore:
    """Canonical store를 로드한다. 파일 없으면 빈 store 반환."""
    return CanonicalStore.load(path)


def format_canonical_context(item: dict) -> str:
    """Canonical 항목을 컨텍스트 문자열로 포맷한다.

    retrieve_quotes 결과와 함께 프롬프트에 삽입할 수 있는 형태.
    """
    lines = [
        f"[Canonical 기준 정의 — {item.get('subject', 'unknown')}]",
        f"claim_type: {item.get('claim_type', 'unknown')}",
        f"edition: {item.get('edition', 'unknown')} (doc_id: {item.get('doc_id', 'unknown')})",
        f"quote_ids: {', '.join(item.get('quote_ids', []))}",
        "",
        item.get("summary_ko", ""),
        "",
    ]
    return "\n".join(lines)
