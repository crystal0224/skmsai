"""Visualization Data Transforms -- AntV 차트용 데이터 변환.

PR-051: Card News Series + Visualization Data Transforms.

SKMS 도메인 데이터를 AntV 차트 포맷으로 변환하는 함수 3종:
- build_timeline_data: 개정 연혁 타임라인
- build_network_data: 경영요소 관계도
- build_sankey_data: 개념 진화 산키 다이어그램
"""
from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Timeline: SKMS 개정 연혁
# ---------------------------------------------------------------------------


def build_timeline_data() -> dict[str, Any]:
    """SKMS 개정 연혁 타임라인 데이터를 생성한다.

    Returns:
        AntV timeline 차트 구조 (chart_type, title, data).
    """
    return {
        "chart_type": "timeline",
        "title": "SKMS 개정 연혁",
        "data": [
            {
                "year": 1979,
                "edition": "초판",
                "label": "SKMS 초판 제정",
                "category": "foundation",
            },
            {"year": 1981, "edition": "1차", "label": "1차 개정", "category": "revision"},
            {"year": 1988, "edition": "5차", "label": "5차 개정", "category": "revision"},
            {"year": 1989, "edition": "6차", "label": "6차 개정", "category": "revision"},
            {"year": 1990, "edition": "7차", "label": "7차 개정", "category": "revision"},
            {"year": 1995, "edition": "8차", "label": "8차 개정", "category": "revision"},
            {"year": 1997, "edition": "9차", "label": "9차 개정", "category": "revision"},
            {"year": 1998, "edition": "10차", "label": "SUPEX 도입", "category": "major"},
            {"year": 2004, "edition": "11차", "label": "11차 개정", "category": "revision"},
            {"year": 2008, "edition": "12차", "label": "12차 개정", "category": "revision"},
            {"year": 2016, "edition": "13차", "label": "13차 개정", "category": "revision"},
            {
                "year": 2020,
                "edition": "14차",
                "label": "VWBE 문화 도입",
                "category": "major",
            },
        ],
    }


# ---------------------------------------------------------------------------
# Network: SKMS 경영요소 관계도
# ---------------------------------------------------------------------------


def build_network_data() -> dict[str, Any]:
    """SKMS 경영요소 관계도 네트워크 데이터를 생성한다.

    Returns:
        AntV network graph 구조 (chart_type, title, nodes, edges).
    """
    return {
        "chart_type": "network",
        "title": "SKMS 경영요소 관계도",
        "nodes": [
            # 정적 요소 (10개)
            {"id": "planning", "label": "기획관리", "category": "static"},
            {"id": "hr", "label": "인사관리", "category": "static"},
            {"id": "org", "label": "조직관리", "category": "static"},
            {"id": "finance", "label": "재무관리", "category": "static"},
            {"id": "sales", "label": "판매관리", "category": "static"},
            {"id": "production", "label": "생산관리", "category": "static"},
            {"id": "rnd", "label": "연구개발관리", "category": "static"},
            {"id": "purchase", "label": "구매관리", "category": "static"},
            {"id": "admin", "label": "사무관리", "category": "static"},
            {"id": "pr", "label": "PR관리", "category": "static"},
            # 동적 요소 (5개)
            {"id": "motivation", "label": "의욕관리", "category": "dynamic"},
            {"id": "capability", "label": "관리역량관리", "category": "dynamic"},
            {"id": "coordination", "label": "코디네이션관리", "category": "dynamic"},
            {"id": "communication", "label": "커뮤니케이션관리", "category": "dynamic"},
            {"id": "sk_manship", "label": "SK-Manship", "category": "dynamic"},
        ],
        "edges": [
            # 동적 -> 정적 관계 (핵심 연결)
            {"source": "motivation", "target": "hr", "weight": 3},
            {"source": "capability", "target": "planning", "weight": 2},
            {"source": "coordination", "target": "org", "weight": 3},
            {"source": "communication", "target": "admin", "weight": 2},
            {"source": "sk_manship", "target": "hr", "weight": 2},
            {"source": "sk_manship", "target": "motivation", "weight": 3},
            {"source": "coordination", "target": "production", "weight": 2},
            {"source": "capability", "target": "rnd", "weight": 2},
        ],
    }


# ---------------------------------------------------------------------------
# Sankey: SKMS 개념 진화
# ---------------------------------------------------------------------------


def build_sankey_data() -> dict[str, Any]:
    """SKMS 개념 진화 산키 다이어그램 데이터를 생성한다.

    Returns:
        AntV sankey 구조 (chart_type, title, nodes, links).
    """
    return {
        "chart_type": "sankey",
        "title": "SKMS 개념 진화",
        "nodes": [
            {"id": "mgmt_1979", "label": "경영관리 (1979)"},
            {"id": "supex_1998", "label": "SUPEX 추구 (1998)"},
            {"id": "vwbe_2020", "label": "VWBE 문화 (2020)"},
            {"id": "human_1979", "label": "인간위주경영 (1979)"},
            {"id": "human_2020", "label": "인간중심경영 (2020)"},
            {"id": "rational_1979", "label": "합리적 경영 (1979)"},
            {"id": "rational_2020", "label": "합리적 경영 (2020)"},
        ],
        "links": [
            {
                "source": "mgmt_1979",
                "target": "supex_1998",
                "value": 5,
                "status": "evolved",
            },
            {
                "source": "supex_1998",
                "target": "vwbe_2020",
                "value": 5,
                "status": "evolved",
            },
            {
                "source": "human_1979",
                "target": "human_2020",
                "value": 3,
                "status": "renamed",
            },
            {
                "source": "rational_1979",
                "target": "rational_2020",
                "value": 3,
                "status": "maintained",
            },
        ],
    }
