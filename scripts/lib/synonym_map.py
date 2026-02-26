"""SynonymMap — 동의어 매핑 서비스.

PR-017: SKMS 검색 확장을 위한 동의어 그룹 관리.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SynonymCluster:
    """동의어 그룹 (불변)."""

    name: str
    terms: tuple[str, ...]


@dataclass(frozen=True)
class SynonymMap:
    """동의어 매핑 서비스 (불변).

    YAML 기반 동의어 클러스터를 로드하고,
    주어진 텍스트에 포함된 동의어를 확장한다.
    """

    clusters: tuple[SynonymCluster, ...]
    _term_to_cluster: dict[str, int]  # normalized term → cluster index

    @classmethod
    def from_yaml(cls, path: Path) -> SynonymMap:
        """YAML 파일에서 동의어 맵을 로드한다."""
        import yaml

        if not path.exists():
            logger.warning("동의어 파일 없음: %s", path)
            return cls(clusters=(), _term_to_cluster={})

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SynonymMap:
        """dict에서 동의어 맵을 생성한다."""
        raw_clusters = data.get("synonym_clusters", [])
        clusters: list[SynonymCluster] = []
        term_to_cluster: dict[str, int] = {}

        for i, raw in enumerate(raw_clusters):
            name = raw.get("name", f"cluster_{i}")
            terms = tuple(raw.get("terms", []))
            clusters.append(SynonymCluster(name=name, terms=terms))

            for term in terms:
                normalized = _normalize(term)
                if normalized in term_to_cluster:
                    logger.warning(
                        "동의어 중복: '%s' (cluster '%s' vs '%s')",
                        term,
                        clusters[term_to_cluster[normalized]].name,
                        name,
                    )
                term_to_cluster[normalized] = i

        return cls(clusters=tuple(clusters), _term_to_cluster=term_to_cluster)

    @classmethod
    def empty(cls) -> SynonymMap:
        """빈 SynonymMap을 생성한다."""
        return cls(clusters=(), _term_to_cluster={})

    @property
    def cluster_count(self) -> int:
        """동의어 그룹 수."""
        return len(self.clusters)

    @property
    def term_count(self) -> int:
        """등록된 고유 용어 수."""
        return len(self._term_to_cluster)

    @property
    def pair_count(self) -> int:
        """양방향 동의어 쌍 수."""
        return sum(len(c.terms) * (len(c.terms) - 1) // 2 for c in self.clusters)

    def get_cluster(self, term: str) -> SynonymCluster | None:
        """용어가 속한 클러스터를 반환한다."""
        normalized = _normalize(term)
        idx = self._term_to_cluster.get(normalized)
        if idx is None:
            return None
        return self.clusters[idx]

    def get_synonyms(self, term: str) -> tuple[str, ...]:
        """용어의 동의어를 반환한다 (자신 제외)."""
        cluster = self.get_cluster(term)
        if cluster is None:
            return ()
        normalized = _normalize(term)
        return tuple(t for t in cluster.terms if _normalize(t) != normalized)

    def expand_terms(self, terms: list[str]) -> list[str]:
        """용어 리스트를 동의어로 확장한다.

        원본 용어를 유지하고, 동의어를 추가한다.
        중복은 제거한다.
        """
        seen: set[str] = set()
        expanded: list[str] = []

        for term in terms:
            normalized = _normalize(term)
            if normalized not in seen:
                seen.add(normalized)
                expanded.append(term)

            # 동의어 추가
            synonyms = self.get_synonyms(term)
            for syn in synonyms:
                syn_normalized = _normalize(syn)
                if syn_normalized not in seen:
                    seen.add(syn_normalized)
                    expanded.append(syn)

        return expanded

    def expand_query(self, query: str) -> str:
        """검색 쿼리를 동의어로 확장한다.

        쿼리 내 토큰/구문 중 동의어가 있는 것을 찾아 확장한다.
        원본 쿼리 뒤에 동의어를 추가하는 방식.
        """
        additions: list[str] = []
        seen_clusters: set[int] = set()

        # 정규화된 쿼리 (공백/하이픈/마침표 제거)
        query_lower = query.lower()
        query_normalized = _normalize(query)

        # 1. 먼저 전체 쿼리에서 멀티워드 용어 매칭
        for idx, cluster in enumerate(self.clusters):
            if idx in seen_clusters:
                continue
            for term in cluster.terms:
                term_norm = _normalize(term)
                # 원본 쿼리 또는 정규화된 쿼리에서 매칭
                if term_norm in query_normalized or term.lower() in query_lower:
                    seen_clusters.add(idx)
                    for syn in cluster.terms:
                        syn_norm = _normalize(syn)
                        if syn_norm not in query_normalized:
                            additions.append(syn)
                    break

        # 2. 단일 토큰 매칭
        tokens = query.split()
        for token in tokens:
            normalized = _normalize(token)
            idx = self._term_to_cluster.get(normalized)
            if idx is not None and idx not in seen_clusters:
                seen_clusters.add(idx)
                cluster = self.clusters[idx]
                for syn in cluster.terms:
                    syn_norm = _normalize(syn)
                    if syn_norm != normalized and syn_norm not in query_normalized:
                        additions.append(syn)

        if not additions:
            return query

        return query + " " + " ".join(additions)


def _normalize(term: str) -> str:
    """용어를 정규화한다 (소문자, 공백 제거)."""
    return term.lower().replace(" ", "").replace("-", "").replace(".", "")
