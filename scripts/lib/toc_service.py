"""TOC 서비스 — 개정판별 목차 트리 제공.

PR-014: structure.json에서 로드한 TOC 데이터를 조회하는 서비스.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TOC 데이터 모델 (불변)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TOCNode:
    """목차 노드 (불변)."""

    level: str
    title: str
    line: int
    children: tuple[TOCNode, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TOCNode:
        """dict에서 TOCNode를 생성한다."""
        children = tuple(cls.from_dict(child) for child in data.get("children", []))
        return cls(
            level=data.get("level", "H0"),
            title=data.get("title", ""),
            line=data.get("line", 0),
            children=children,
        )

    def to_dict(self) -> dict[str, Any]:
        """직렬화 가능한 dict로 변환한다."""
        return {
            "level": self.level,
            "title": self.title,
            "line": self.line,
            "children": [child.to_dict() for child in self.children],
        }

    @property
    def node_count(self) -> int:
        """이 노드를 포함한 전체 노드 수."""
        return 1 + sum(child.node_count for child in self.children)


@dataclass(frozen=True)
class EditionInfo:
    """개정판 메타데이터 (불변)."""

    edition_id: str
    year: int
    label: str
    start_line: int
    end_line: int
    section_count: int


@dataclass(frozen=True)
class EditionTOC:
    """개정판별 목차 트리 (불변)."""

    edition_id: str
    year: int
    label: str
    sections: tuple[TOCNode, ...]

    @property
    def node_count(self) -> int:
        """전체 노드 수."""
        return sum(s.node_count for s in self.sections)


# ---------------------------------------------------------------------------
# TOCService
# ---------------------------------------------------------------------------


class TOCService:
    """개정판별 목차 트리를 제공하는 서비스.

    structure.json을 한 번 로드하여 메모리에 캐싱한다.
    """

    def __init__(self) -> None:
        self._editions: dict[str, EditionTOC] = {}
        self._edition_infos: list[EditionInfo] = []
        self._raw_lines: list[str] = []

    @classmethod
    def from_path(cls, path: Path, raw_text_path: Path | None = None) -> TOCService:
        """structure.json 파일에서 TOCService를 생성한다.

        Args:
            path: structure.json 경로.
            raw_text_path: SKMSraw.txt 경로 (섹션 본문 제공용, 옵션).
        """
        service = cls()
        service._load(path)
        if raw_text_path:
            resolved = raw_text_path.resolve()
            if resolved.exists():
                with open(resolved, encoding="utf-8") as f:
                    service._raw_lines = f.readlines()
                logger.info(
                    "원문 로드 완료: %d lines from %s", len(service._raw_lines), resolved
                )
            else:
                logger.warning("원문 파일 없음: %s (resolved: %s)", raw_text_path, resolved)
        return service

    def _load(self, path: Path) -> None:
        """structure.json을 로드한다."""
        if not path.exists():
            logger.warning("structure.json not found: %s", path)
            return

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        editions_raw = data.get("editions", [])
        infos: list[EditionInfo] = []

        for ed in editions_raw:
            edition_id = ed["edition_id"]
            sections = tuple(TOCNode.from_dict(s) for s in ed.get("sections", []))
            edition_toc = EditionTOC(
                edition_id=edition_id,
                year=ed["year"],
                label=ed["label"],
                sections=sections,
            )
            self._editions[edition_id] = edition_toc

            # 총 섹션 수 계산
            total_nodes = edition_toc.node_count
            infos.append(
                EditionInfo(
                    edition_id=edition_id,
                    year=ed["year"],
                    label=ed["label"],
                    start_line=ed.get("start_line", 0),
                    end_line=ed.get("end_line", 0),
                    section_count=total_nodes,
                )
            )

        self._edition_infos = infos
        logger.info(
            "TOC 로드 완료: %d editions, %d total sections",
            len(infos),
            sum(info.section_count for info in infos),
        )

    @property
    def edition_count(self) -> int:
        """로드된 개정판 수."""
        return len(self._edition_infos)

    def list_editions(self) -> tuple[EditionInfo, ...]:
        """전체 개정판 목록을 반환한다."""
        return tuple(self._edition_infos)

    def get_edition_toc(self, edition_id: str) -> EditionTOC | None:
        """특정 개정판의 TOC 트리를 반환한다."""
        return self._editions.get(edition_id)

    def get_section_ids(self) -> tuple[str, ...]:
        """모든 개정판 ID를 반환한다."""
        return tuple(self._editions.keys())

    def get_section_content_from_db(self, edition_id: str, title: str) -> str | None:
        """DB에서 제목과 판본 ID를 기반으로 본문을 직접 조회한다.

        PR-073: DB 기반 원문 조회 기능 추가.
        """
        import sqlite3
        db_path = Path("data/skms.db")
        if not db_path.exists():
            logger.warning("SKMS DB 파일 없음: %s", db_path)
            return None

        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                # 제목이 정확히 일치하거나 부분 일치하는 섹션 조회
                query = "SELECT content FROM sections WHERE edition_id = ? AND title = ? LIMIT 1"
                row = conn.execute(query, (edition_id, title)).fetchone()
                
                if row:
                    return row["content"]
                
                # 정확히 일치하는 게 없으면 LIKE 검색 (부분 일치)
                query_like = "SELECT content FROM sections WHERE edition_id = ? AND title LIKE ? LIMIT 1"
                row_like = conn.execute(query_like, (edition_id, f"%{title}%")).fetchone()
                return row_like["content"] if row_like else None
        except Exception as e:
            logger.error("DB 본문 조회 중 오류 발생: %s", e)
            return None

    def get_section_text(
        self,
        edition_id: str,
        line: int,
        max_lines: int = 100,
    ) -> str | None:
        """섹션 시작 line부터 다음 섹션 직전까지의 원문 텍스트를 반환한다.

        Args:
            edition_id: 개정판 ID.
            line: 섹션 시작 줄 번호 (1-based).
            max_lines: 최대 반환 줄 수.

        Returns:
            원문 텍스트 또는 None (원문 미로드 시).
        """
        if not self._raw_lines:
            return None

        edition = self._editions.get(edition_id)
        if not edition:
            return None

        # 해당 판본의 모든 섹션 line 번호를 수집 (flat)
        all_lines = self._collect_section_lines(edition.sections)
        all_lines.sort()

        # 다음 섹션의 시작 line 찾기
        next_line = None
        for sl in all_lines:
            if sl > line:
                next_line = sl
                break

        # 판본의 end_line을 폴백으로 사용
        edition_info = next(
            (e for e in self._edition_infos if e.edition_id == edition_id), None
        )
        end_bound = (
            next_line
            if next_line
            else (edition_info.end_line if edition_info else line + max_lines)
        )

        # line은 1-based, list는 0-based → 제목 줄 포함
        start_idx = line - 1
        end_idx = min(end_bound - 1, start_idx + max_lines)

        if start_idx >= len(self._raw_lines) or start_idx < 0:
            return ""

        text_lines = self._raw_lines[start_idx:end_idx]
        return "".join(text_lines).strip()

    def _collect_section_lines(self, sections: tuple[TOCNode, ...]) -> list[int]:
        """섹션 트리에서 모든 line 번호를 플랫하게 수집한다."""
        lines: list[int] = []
        for s in sections:
            lines.append(s.line)
            lines.extend(self._collect_section_lines(s.children))
        return lines

    def search_sections(
        self,
        query: str,
        edition_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """섹션 제목으로 검색한다.

        Args:
            query: 검색어 (부분 일치).
            edition_id: 특정 개정판으로 제한 (옵션).

        Returns:
            매칭된 섹션 목록 (edition_id, path, level, title, line).
        """
        results: list[dict[str, Any]] = []
        query_lower = query.lower()

        target_editions = (
            {edition_id: self._editions[edition_id]}
            if edition_id and edition_id in self._editions
            else self._editions
        )

        for eid, edition_toc in target_editions.items():
            for section in edition_toc.sections:
                self._search_node(section, eid, [eid], query_lower, results)

        return results

    def _search_node(
        self,
        node: TOCNode,
        edition_id: str,
        path: list[str],
        query_lower: str,
        results: list[dict[str, Any]],
    ) -> None:
        """노드 트리를 재귀적으로 검색한다."""
        current_path = [*path, node.title]
        if query_lower in node.title.lower():
            results.append(
                {
                    "edition_id": edition_id,
                    "path": current_path,
                    "level": node.level,
                    "title": node.title,
                    "line": node.line,
                }
            )

        for child in node.children:
            self._search_node(child, edition_id, current_path, query_lower, results)
