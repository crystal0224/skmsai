"""BM25Index — BM25 키워드 인덱스 래퍼.

PR-011: 기존 pkl 포맷 로드 + QuoteObject 직접 생성 지원.
"""
from __future__ import annotations

import json
import logging
import pickle
import re
from pathlib import Path
from typing import Any

from scripts.lib.quote import QuoteObject
from scripts.lib.search_types import SearchHit

logger = logging.getLogger(__name__)


class BM25Index:
    """BM25 키워드 인덱스 래퍼.

    from_path(): 기존 pkl 파일에서 로드 (dict 기반 quote_map)
    from_quotes(): QuoteObject 리스트에서 직접 생성

    내부적으로 두 포맷을 모두 처리한다.
    """

    def __init__(
        self,
        bm25: Any,
        quote_ids: list[str],
        quote_map: dict[str, Any],
    ) -> None:
        self._bm25 = bm25
        self._quote_ids = quote_ids
        self._quote_map = quote_map

    @classmethod
    def from_path(cls, path: Path) -> BM25Index | None:
        """기존 pkl 파일에서 로드한다.

        주의: pickle.load는 신뢰할 수 있는 로컬 파일에만 사용해야 한다.
        """
        if not path.exists():
            logger.warning("BM25 인덱스 없음: %s", path)
            return None
        with open(path, "rb") as f:
            data = pickle.load(f)
        return cls(
            bm25=data["bm25"],
            quote_ids=data["quote_ids"],
            quote_map=data["quote_map"],
        )

    @classmethod
    def from_quotes(
        cls,
        quotes: list[QuoteObject],
        type_boost: dict[str, float] | None = None,
    ) -> BM25Index:
        """QuoteObject 리스트에서 직접 생성한다."""
        from rank_bm25 import BM25Okapi

        if type_boost is None:
            type_boost = {}

        tokenized_corpus: list[list[str]] = []
        quote_ids: list[str] = []
        quote_map: dict[str, QuoteObject] = {}

        for q in quotes:
            tokens = q.text.split()
            boost = type_boost.get(q.quote_type, 1.0)
            repetitions = round(boost)
            if repetitions > 1:
                tokens = tokens * repetitions
            tokenized_corpus.append(tokens)
            quote_ids.append(q.quote_id)
            quote_map[q.quote_id] = q

        bm25 = BM25Okapi(tokenized_corpus)
        return cls(bm25=bm25, quote_ids=quote_ids, quote_map=quote_map)

    @property
    def size(self) -> int:
        return len(self._quote_ids)

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        edition_filter: str | None = None,
        type_filter: list[str] | None = None,
    ) -> list[SearchHit]:
        """BM25 키워드 검색을 수행한다."""
        if not self._quote_ids:
            return []
        tokens = query.split()
        scores = self._bm25.get_scores(tokens)

        scored = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)

        hits: list[SearchHit] = []
        for idx, score in scored[: top_k * 3]:
            if score <= 0:
                break
            qid = self._quote_ids[idx]
            q = self._quote_map.get(qid)
            if q is None:
                continue

            hit = self._to_search_hit(q, float(score), "bm25")
            if hit is None:
                continue

            # edition filter
            if edition_filter and hit.edition_id != edition_filter:
                continue

            # type filter
            if type_filter and hit.quote_type not in type_filter:
                continue

            hits.append(hit)
            if len(hits) >= top_k:
                break

        return hits

    def save(self, path: Path) -> None:
        """pkl 파일로 저장한다."""
        # QuoteObject → dict 변환 (기존 포맷 호환)
        serializable_map: dict[str, dict] = {}
        for qid, q in self._quote_map.items():
            if isinstance(q, QuoteObject):
                d = q.to_dict()
                # 기존 포맷 키 호환
                d["type"] = d.pop("quote_type")
                d["sha256"] = d.pop("content_hash")
                serializable_map[qid] = d
            else:
                serializable_map[qid] = q

        data = {
            "bm25": self._bm25,
            "quote_ids": self._quote_ids,
            "quote_map": serializable_map,
            "tokenized_corpus": [],  # 재생성 가능하므로 생략
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(data, f)

    @staticmethod
    def _to_search_hit(q: Any, score: float, source: str) -> SearchHit | None:
        """QuoteObject 또는 dict → SearchHit."""
        if isinstance(q, QuoteObject):
            return SearchHit(
                quote_id=q.quote_id,
                text=q.text,
                score=score,
                edition_id=q.edition_id,
                year=q.year,
                revision_num=q.revision_num,
                quote_type=q.quote_type,
                section_path=q.section_path,
                source=source,
                content_hash=q.content_hash,
                quality_flags=q.quality_flags,
            )

        # dict (기존 pkl 포맷)
        if isinstance(q, dict):
            edition_id = q.get("edition_id", "")
            section_raw = q.get("section_path", [])
            if isinstance(section_raw, str):
                try:
                    section_raw = json.loads(section_raw)
                except json.JSONDecodeError:
                    section_raw = []

            flags_raw = q.get("quality_flags", [])
            if isinstance(flags_raw, str):
                try:
                    flags_raw = json.loads(flags_raw)
                except json.JSONDecodeError:
                    flags_raw = []

            year_match = re.match(r"(\d{4})", edition_id)
            year = int(year_match.group(1)) if year_match else 0

            rev_match = re.search(r"(\d+)차", edition_id)
            revision_num = int(rev_match.group(1)) if rev_match else 0

            return SearchHit(
                quote_id=q.get("quote_id", ""),
                text=q.get("text", ""),
                score=score,
                edition_id=edition_id,
                year=year,
                revision_num=revision_num,
                quote_type=q.get("type", q.get("quote_type", "narrative")),
                section_path=tuple(section_raw),
                source=source,
                content_hash=q.get("sha256", q.get("content_hash", "")),
                quality_flags=tuple(flags_raw),
            )

        return None
