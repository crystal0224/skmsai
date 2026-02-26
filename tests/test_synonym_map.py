"""SynonymMap 테스트.

PR-017: 동의어 매핑 서비스 단위/통합 테스트.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.synonym_map import (  # noqa: E402
    SynonymCluster,
    SynonymMap,
    _normalize,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_data() -> dict:
    """테스트용 동의어 데이터."""
    return {
        "synonym_clusters": [
            {
                "name": "SUPEX",
                "terms": ["SUPEX", "Super Excellent", "수펙스", "최고수준"],
            },
            {
                "name": "VWBE",
                "terms": [
                    "VWBE",
                    "자발적의욕적두뇌활용",
                    "Voluntary Brain Engagement",
                ],
            },
            {
                "name": "커뮤니케이션",
                "terms": ["커뮤니케이션", "Communication", "의사소통"],
            },
        ],
    }


@pytest.fixture()
def synonym_map(sample_data) -> SynonymMap:
    """테스트용 SynonymMap."""
    return SynonymMap.from_dict(sample_data)


# ---------------------------------------------------------------------------
# _normalize 테스트
# ---------------------------------------------------------------------------


def test_normalize_lowercase():
    """소문자 변환."""
    assert _normalize("SUPEX") == "supex"


def test_normalize_remove_spaces():
    """공백 제거."""
    assert _normalize("Super Excellent") == "superexcellent"


def test_normalize_remove_hyphens():
    """하이픈 제거."""
    assert _normalize("SK-Manship") == "skmanship"


def test_normalize_remove_dots():
    """마침표 제거."""
    assert _normalize("O.J.T.") == "ojt"


def test_normalize_combined():
    """복합 정규화."""
    assert _normalize("O.J.T Training") == "ojttraining"


# ---------------------------------------------------------------------------
# SynonymCluster 테스트
# ---------------------------------------------------------------------------


def test_cluster_is_frozen():
    """SynonymCluster는 불변이다."""
    cluster = SynonymCluster(name="test", terms=("a", "b"))
    with pytest.raises(AttributeError):
        cluster.name = "changed"  # type: ignore[misc]


def test_cluster_fields():
    """SynonymCluster 필드 접근."""
    cluster = SynonymCluster(name="SUPEX", terms=("SUPEX", "수펙스"))
    assert cluster.name == "SUPEX"
    assert len(cluster.terms) == 2


# ---------------------------------------------------------------------------
# SynonymMap.from_dict 테스트
# ---------------------------------------------------------------------------


def test_from_dict_cluster_count(synonym_map):
    """클러스터 수."""
    assert synonym_map.cluster_count == 3


def test_from_dict_term_count(synonym_map):
    """용어 수."""
    assert synonym_map.term_count == 10


def test_from_dict_pair_count(synonym_map):
    """동의어 쌍 수."""
    # SUPEX: 4C2=6, VWBE: 3C2=3, 커뮤니케이션: 3C2=3 → 12
    assert synonym_map.pair_count == 12


def test_from_dict_empty():
    """빈 데이터."""
    sm = SynonymMap.from_dict({})
    assert sm.cluster_count == 0
    assert sm.term_count == 0


def test_from_dict_no_terms():
    """terms 없는 클러스터."""
    data = {"synonym_clusters": [{"name": "empty"}]}
    sm = SynonymMap.from_dict(data)
    assert sm.cluster_count == 1
    assert sm.term_count == 0


# ---------------------------------------------------------------------------
# SynonymMap.empty 테스트
# ---------------------------------------------------------------------------


def test_empty():
    """빈 SynonymMap."""
    sm = SynonymMap.empty()
    assert sm.cluster_count == 0
    assert sm.term_count == 0
    assert sm.pair_count == 0


# ---------------------------------------------------------------------------
# SynonymMap.from_yaml 테스트
# ---------------------------------------------------------------------------


def test_from_yaml(tmp_path):
    """YAML 파일 로드."""
    import yaml

    data = {
        "synonym_clusters": [
            {"name": "test", "terms": ["A", "B", "C"]},
        ],
    }
    path = tmp_path / "synonyms.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True)

    sm = SynonymMap.from_yaml(path)
    assert sm.cluster_count == 1
    assert sm.term_count == 3


def test_from_yaml_nonexistent():
    """존재하지 않는 파일은 빈 맵."""
    sm = SynonymMap.from_yaml(Path("/nonexistent/synonyms.yaml"))
    assert sm.cluster_count == 0


# ---------------------------------------------------------------------------
# SynonymMap.get_cluster 테스트
# ---------------------------------------------------------------------------


def test_get_cluster_exact(synonym_map):
    """정확한 용어 매칭."""
    cluster = synonym_map.get_cluster("SUPEX")
    assert cluster is not None
    assert cluster.name == "SUPEX"


def test_get_cluster_case_insensitive(synonym_map):
    """대소문자 무관."""
    cluster = synonym_map.get_cluster("supex")
    assert cluster is not None
    assert cluster.name == "SUPEX"


def test_get_cluster_with_spaces(synonym_map):
    """공백이 포함된 용어."""
    cluster = synonym_map.get_cluster("Super Excellent")
    assert cluster is not None
    assert cluster.name == "SUPEX"


def test_get_cluster_korean(synonym_map):
    """한글 용어."""
    cluster = synonym_map.get_cluster("수펙스")
    assert cluster is not None
    assert cluster.name == "SUPEX"


def test_get_cluster_not_found(synonym_map):
    """없는 용어는 None."""
    assert synonym_map.get_cluster("존재하지않는용어") is None


def test_get_cluster_normalized_match(synonym_map):
    """정규화된 매칭 (공백 변이)."""
    # "자발적의욕적두뇌활용" and "자발적 의욕적 두뇌활용" should match same cluster
    c1 = synonym_map.get_cluster("자발적의욕적두뇌활용")
    c2 = synonym_map.get_cluster("자발적 의욕적 두뇌활용")
    assert c1 is not None
    assert c2 is not None
    assert c1.name == c2.name == "VWBE"


# ---------------------------------------------------------------------------
# SynonymMap.get_synonyms 테스트
# ---------------------------------------------------------------------------


def test_get_synonyms(synonym_map):
    """동의어 반환 (자신 제외)."""
    synonyms = synonym_map.get_synonyms("SUPEX")
    assert "SUPEX" not in synonyms
    assert "Super Excellent" in synonyms
    assert "수펙스" in synonyms
    assert "최고수준" in synonyms
    assert len(synonyms) == 3


def test_get_synonyms_korean(synonym_map):
    """한글 동의어."""
    synonyms = synonym_map.get_synonyms("의사소통")
    assert "커뮤니케이션" in synonyms
    assert "Communication" in synonyms
    assert len(synonyms) == 2


def test_get_synonyms_not_found(synonym_map):
    """없는 용어는 빈 튜플."""
    assert synonym_map.get_synonyms("없는용어") == ()


# ---------------------------------------------------------------------------
# SynonymMap.expand_terms 테스트
# ---------------------------------------------------------------------------


def test_expand_terms_basic(synonym_map):
    """용어 확장."""
    expanded = synonym_map.expand_terms(["SUPEX"])
    assert "SUPEX" in expanded
    assert "Super Excellent" in expanded
    assert "수펙스" in expanded
    assert "최고수준" in expanded


def test_expand_terms_no_match(synonym_map):
    """매칭 없으면 원본 유지."""
    expanded = synonym_map.expand_terms(["관계없는단어"])
    assert expanded == ["관계없는단어"]


def test_expand_terms_dedup(synonym_map):
    """중복 제거."""
    expanded = synonym_map.expand_terms(["SUPEX", "supex"])
    # "SUPEX"와 "supex"는 정규화하면 동일 → 하나만 포함
    normalized = [_normalize(t) for t in expanded]
    assert len(normalized) == len(set(normalized))


def test_expand_terms_multiple_clusters(synonym_map):
    """여러 클러스터의 용어 동시 확장."""
    expanded = synonym_map.expand_terms(["SUPEX", "의사소통"])
    assert "수펙스" in expanded
    assert "커뮤니케이션" in expanded


def test_expand_terms_preserves_order(synonym_map):
    """원본 용어가 먼저 나온다."""
    expanded = synonym_map.expand_terms(["의사소통"])
    assert expanded[0] == "의사소통"


# ---------------------------------------------------------------------------
# SynonymMap.expand_query 테스트
# ---------------------------------------------------------------------------


def test_expand_query_basic(synonym_map):
    """쿼리 확장."""
    result = synonym_map.expand_query("SUPEX란 무엇인가")
    assert "SUPEX란 무엇인가" in result
    assert "Super Excellent" in result
    assert "수펙스" in result


def test_expand_query_no_match(synonym_map):
    """매칭 없으면 원본 유지."""
    query = "관계없는 질의"
    assert synonym_map.expand_query(query) == query


def test_expand_query_multiword_match(synonym_map):
    """멀티워드 용어 매칭."""
    result = synonym_map.expand_query("Super Excellent 추구 방법")
    assert "SUPEX" in result
    assert "수펙스" in result


def test_expand_query_korean_match(synonym_map):
    """한글 토큰 매칭."""
    result = synonym_map.expand_query("의사소통이란 무엇인가")
    assert "커뮤니케이션" in result
    assert "Communication" in result


def test_expand_query_preserves_original(synonym_map):
    """원본 쿼리 보존."""
    query = "SUPEX의 정의"
    result = synonym_map.expand_query(query)
    assert result.startswith(query)


def test_expand_query_empty():
    """빈 맵은 원본 반환."""
    sm = SynonymMap.empty()
    assert sm.expand_query("테스트") == "테스트"


# ---------------------------------------------------------------------------
# SynonymMap 불변성 테스트
# ---------------------------------------------------------------------------


def test_synonym_map_is_frozen(synonym_map):
    """SynonymMap은 불변이다."""
    with pytest.raises(AttributeError):
        synonym_map.clusters = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 실제 synonyms.yaml 통합 테스트
# ---------------------------------------------------------------------------


def test_load_actual_synonyms_yaml():
    """실제 config/synonyms.yaml 로드."""
    path = _PROJECT_ROOT / "config" / "synonyms.yaml"
    if not path.exists():
        pytest.skip("config/synonyms.yaml not found")

    sm = SynonymMap.from_yaml(path)
    assert sm.cluster_count >= 40
    assert sm.pair_count >= 80


def test_actual_yaml_supex_cluster():
    """실제 YAML에서 SUPEX 클러스터."""
    path = _PROJECT_ROOT / "config" / "synonyms.yaml"
    if not path.exists():
        pytest.skip("config/synonyms.yaml not found")

    sm = SynonymMap.from_yaml(path)
    cluster = sm.get_cluster("SUPEX")
    assert cluster is not None
    assert "Super Excellent" in cluster.terms
    assert "수펙스" in cluster.terms


def test_actual_yaml_vwbe_cluster():
    """실제 YAML에서 VWBE 클러스터."""
    path = _PROJECT_ROOT / "config" / "synonyms.yaml"
    if not path.exists():
        pytest.skip("config/synonyms.yaml not found")

    sm = SynonymMap.from_yaml(path)
    cluster = sm.get_cluster("VWBE")
    assert cluster is not None
    assert "자발적의욕적두뇌활용" in cluster.terms or "자발적 의욕적 두뇌활용" in cluster.terms


def test_actual_yaml_expand_supex():
    """실제 YAML에서 SUPEX 쿼리 확장."""
    path = _PROJECT_ROOT / "config" / "synonyms.yaml"
    if not path.exists():
        pytest.skip("config/synonyms.yaml not found")

    sm = SynonymMap.from_yaml(path)
    result = sm.expand_query("SUPEX란 무엇인가")
    assert "수펙스" in result


def test_actual_yaml_no_duplicate_terms():
    """실제 YAML에서 정규화 후 중복 용어가 없다."""
    path = _PROJECT_ROOT / "config" / "synonyms.yaml"
    if not path.exists():
        pytest.skip("config/synonyms.yaml not found")

    sm = SynonymMap.from_yaml(path)
    all_normalized: dict[str, str] = {}
    duplicates: list[str] = []
    for cluster in sm.clusters:
        for term in cluster.terms:
            n = _normalize(term)
            if n in all_normalized:
                duplicates.append(
                    f"'{term}' (cluster '{cluster.name}') == " f"'{all_normalized[n]}'"
                )
            else:
                all_normalized[n] = f"{term} ({cluster.name})"

    assert duplicates == [], f"중복 용어 발견: {duplicates}"
