#!/usr/bin/env python3
"""2020년 14차 기반 Canonical View 생성기 (PR-5).

14차 개정판 quotes에서 주제(subject)별 canonical 항목을 추출하여
data/processed/canonical_2020.jsonl에 저장한다.

사람이 손볼 수 있도록 초안 형태로 생성한다:
  - 각 항목은 1~3개의 quote_id를 참조
  - summary_ko는 2~4문장으로 해당 주제의 핵심 내용을 요약
  - claim_type은 목적/가치/원칙/정의/지향점 중 하나

Usage:
    python scripts/build_canonical.py
    python scripts/build_canonical.py --output data/processed/canonical_2020.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Subject extraction mapping
# ---------------------------------------------------------------------------

# 14차 quotes에서 추출 가능한 주제 목록과 매핑 규칙.
# 각 항목: (canonical_id, subject, claim_type, quote_indices(0-based), summary_ko)
# quote_indices는 14차 quotes 배열의 인덱스 (0~16)
#
# 이 매핑은 사람이 수정 가능한 초안이다.

_CANONICAL_ENTRIES: list[dict] = [
    {
        "canonical_id": "CAN-2020-001",
        "subject": "경영의 궁극적 목적",
        "claim_type": "목적",
        "quote_indices": [3, 0],
        "summary_ko": (
            "SK 경영의 궁극적 목적은 구성원 행복이다. "
            "구성원은 SK를 구성하는 주체로서 조직화된 힘으로 전체 행복을 지속적으로 "
            "키워나가며, 각자의 행복이 더 커질 수 있다는 믿음을 갖고 실천한다."
        ),
    },
    {
        "canonical_id": "CAN-2020-002",
        "subject": "구성원 행복",
        "claim_type": "가치",
        "quote_indices": [3, 4],
        "summary_ko": (
            "구성원 행복은 SK 경영활동의 궁극적 목적이자 최상위 가치이다. "
            "SK는 구성원이 지속적으로 행복을 추구하기 위한 터전이자 기반으로서 "
            "안정과 성장을 이루어 영구히 존속·발전해야 한다."
        ),
    },
    {
        "canonical_id": "CAN-2020-003",
        "subject": "사회적 가치",
        "claim_type": "정의",
        "quote_indices": [3, 7],
        "summary_ko": (
            "이해관계자 행복을 위해 회사가 창출하는 모든 가치가 곧 사회적 가치이다. "
            "SK는 사회적 가치 창출을 통해 경제적 가치와 더불어 이해관계자의 신뢰와 지지를 "
            "확보하며, 사회적 가치 기반의 비즈니스 모델 혁신을 추구한다."
        ),
    },
    {
        "canonical_id": "CAN-2020-004",
        "subject": "VWBE (자발적·의욕적 두뇌활용)",
        "claim_type": "정의",
        "quote_indices": [4, 5],
        "summary_ko": (
            "VWBE는 자발적(Voluntarily)이고 의욕적(Willingly)인 두뇌활용(Brain Engagement)을 "
            "뜻한다. 구성원 전체 행복을 지속적으로 키워 나가면 개인의 행복이 더 커질 수 있다는 "
            "믿음으로 실천할 때 VWBE가 발현되며, 이는 SK 경영의 핵심 철학이자 방법론이다."
        ),
    },
    {
        "canonical_id": "CAN-2020-005",
        "subject": "SUPEX 추구",
        "claim_type": "원칙",
        "quote_indices": [4, 0],
        "summary_ko": (
            "SUPEX(Super Excellent)는 인간 능력으로 도달 가능한 최고 수준을 뜻한다. "
            "VWBE한 구성원은 SUPEX 추구를 통해 구성원 행복과 이해관계자 행복을 "
            "지속적으로 창출해 나가며, 이는 SK 경영의 실행 원리이다."
        ),
    },
    {
        "canonical_id": "CAN-2020-006",
        "subject": "패기",
        "claim_type": "정의",
        "quote_indices": [5, 13],
        "summary_ko": (
            "패기는 자발적·의욕적 두뇌활용(VWBE)이 외부로 발현되는 모습이다. "
            "패기 있는 구성원은 스스로 동기부여하여 문제를 제기하고, 높은 목표에 도전하며, "
            "기존의 틀을 깨는 과감한 실행으로 더 높은 성과를 낸다."
        ),
    },
    {
        "canonical_id": "CAN-2020-007",
        "subject": "패기 실천 환경",
        "claim_type": "원칙",
        "quote_indices": [5],
        "summary_ko": (
            "패기 실천 환경은 구성원 스스로 조성할 때 가장 효과적이다. "
            "구성원은 패기 실천을 위한 조직과 제도·시스템을 스스로 디자인하며, "
            "행복을 저해하는 요소를 적극적으로 개선해 나간다."
        ),
    },
    {
        "canonical_id": "CAN-2020-008",
        "subject": "SKMS의 역할",
        "claim_type": "정의",
        "quote_indices": [2, 0],
        "summary_ko": (
            "SKMS는 경영의 기본 방향을 제시하며, SK의 경영철학과 이를 현실 경영에 "
            "구현하는 방법론을 담고 있다. SKMS를 토대로 한 경영활동과 기업문화의 정착이 "
            "SK의 지속적 성장과 발전에 매우 큰 역할을 하였다."
        ),
    },
    {
        "canonical_id": "CAN-2020-009",
        "subject": "기업문화",
        "claim_type": "원칙",
        "quote_indices": [2, 10],
        "summary_ko": (
            "기업문화는 구성원의 힘을 하나로 결집시키고, 기업경영에 필요한 시스템을 "
            "구축·운영하는 토대이다. 강하고 우수한 기업문화를 구축하고 지속적으로 "
            "진화시키는 것은 회사의 성장과 발전에 중요한 경쟁력의 원천이 된다."
        ),
    },
    {
        "canonical_id": "CAN-2020-010",
        "subject": "구성원과 SK",
        "claim_type": "원칙",
        "quote_indices": [1],
        "summary_ko": (
            "SK 구성원은 SK에서 함께할 때 더 행복해질 수 있다는 믿음을 가지고 "
            "SK를 선택한 사람들이다. 모든 SK 구성원은 SK 경영철학에 대한 확신과 "
            "열정으로 이를 실천한다."
        ),
    },
    {
        "canonical_id": "CAN-2020-011",
        "subject": "회사의 존속·발전",
        "claim_type": "원칙",
        "quote_indices": [1, 3],
        "summary_ko": (
            "회사는 조직화된 힘을 통해 가용자원을 효과적으로 활용하여 최대한의 가치를 "
            "창출하는 공동체이다. 회사는 지속적인 안정과 성장을 이루어 영구히 존속·발전해야 "
            "하며, 이를 위해 스스로 경영능력과 생존 기반을 갖추어야 한다."
        ),
    },
    {
        "canonical_id": "CAN-2020-012",
        "subject": "이해관계자 행복",
        "claim_type": "지향점",
        "quote_indices": [3, 4],
        "summary_ko": (
            "구성원 행복이 지속 가능하려면 이해관계자의 행복 역시 지속 가능해야 한다. "
            "SK는 이해관계자 간 행복이 조화와 균형을 이루도록 노력하며, "
            "장기적으로 현재와 미래의 행복을 동시에 고려한다."
        ),
    },
    {
        "canonical_id": "CAN-2020-013",
        "subject": "SUPEX Company",
        "claim_type": "정의",
        "quote_indices": [8, 9],
        "summary_ko": (
            "SUPEX Company는 지속적인 경제적 가치, 사회적 가치, 구성원 행복을 "
            "창출하는 회사를 말한다. 이를 위해 회사는 끊임없이 변하는 환경에 유연하게 "
            "대응하면서 경영 전략을 수립하고 실행해야 한다."
        ),
    },
    {
        "canonical_id": "CAN-2020-014",
        "subject": "To-be Model",
        "claim_type": "원칙",
        "quote_indices": [6, 7, 8],
        "summary_ko": (
            "SUPEX 목표를 달성하기 위해 To-be Model을 체계적으로 수립하고 실행한다. "
            "To-be Model은 SUPEX Company Image와 Better Company 목표, 실행전략, "
            "KPI, 평가·보상, VWBE 문화 조성 등으로 구성된다. "
            "각 회사가 업종 특성과 환경 변화를 반영하여 스스로 설계·운영한다."
        ),
    },
    {
        "canonical_id": "CAN-2020-015",
        "subject": "경제적 가치 창출",
        "claim_type": "원칙",
        "quote_indices": [8, 14],
        "summary_ko": (
            "회사는 기존 사업의 혁신을 통해 새로운 경제적 가치를 창출하고, "
            "지속 가능한 성장을 위한 기반을 마련한다. 경제적 가치와 사회적 가치를 "
            "동등하게 중요하게 여기며, 양자의 선순환을 추구한다."
        ),
    },
    {
        "canonical_id": "CAN-2020-016",
        "subject": "평가·보상 체계",
        "claim_type": "원칙",
        "quote_indices": [11],
        "summary_ko": (
            "SUPEX 목표 달성을 위한 평가와 보상 체계는 구성원의 동기부여와 "
            "성과 창출에 큰 영향을 미친다. 회사는 공정하고 투명한 평가 체계를 통해 "
            "구성원의 기여를 인정하고 적절한 보상으로 의욕과 참여를 촉진한다."
        ),
    },
    {
        "canonical_id": "CAN-2020-017",
        "subject": "KPI 체계",
        "claim_type": "원칙",
        "quote_indices": [11, 6],
        "summary_ko": (
            "회사는 SUPEX 목표를 달성하기 위한 중요한 성과 지표(KPI)를 설정하고 "
            "체계적으로 관리한다. KPI는 경제적 가치, 사회적 가치, 구성원 행복을 "
            "측정하는 지표로, 회사의 전략적 목표와 밀접하게 연관되어 있다."
        ),
    },
    {
        "canonical_id": "CAN-2020-018",
        "subject": "리더십",
        "claim_type": "원칙",
        "quote_indices": [12],
        "summary_ko": (
            "리더는 구성원의 잠재력을 최대한 발휘할 수 있도록 지원하고 성장을 "
            "돕는 역할을 한다. 명확한 목표와 방향을 제시하며, 구성원이 자발적으로 "
            "참여하고 도전할 수 있는 환경을 조성해야 한다."
        ),
    },
    {
        "canonical_id": "CAN-2020-019",
        "subject": "협력과 팀워크",
        "claim_type": "원칙",
        "quote_indices": [12, 15],
        "summary_ko": (
            "구성원 간의 협력과 팀워크는 SUPEX 목표 달성에 필수적이다. "
            "구성원은 상호 신뢰와 존중을 바탕으로 협력하며, 공동의 목표를 향해 "
            "함께 노력하여 조직의 시너지를 극대화한다."
        ),
    },
    {
        "canonical_id": "CAN-2020-020",
        "subject": "VWBE 문화",
        "claim_type": "가치",
        "quote_indices": [10, 9],
        "summary_ko": (
            "VWBE 문화는 SK의 고유한 기업문화로서 지속적인 성장의 원동력이 된다. "
            "구성원 스스로 패기 실천 환경을 조성하고, 행복을 저해하는 요소를 "
            "개선해 나가는 과정을 통해 VWBE 문화는 더욱 강화된다."
        ),
    },
    {
        "canonical_id": "CAN-2020-021",
        "subject": "지속적인 개선",
        "claim_type": "원칙",
        "quote_indices": [13],
        "summary_ko": (
            "구성원은 현재에 안주하지 않고 지속적으로 개선과 발전을 추구해야 한다. "
            "이를 통해 회사는 변화하는 시장 환경에 신속하게 대응하고, "
            "새로운 성장 기회를 포착할 수 있다."
        ),
    },
    {
        "canonical_id": "CAN-2020-022",
        "subject": "환경·사회적 책임",
        "claim_type": "원칙",
        "quote_indices": [14, 16],
        "summary_ko": (
            "SK는 환경 보호와 사회적 책임을 다하기 위해 노력한다. "
            "환경보호, 고용 창출, 삶의 질 제고, 지역사회 기여 등 다양한 역할을 수행하며, "
            "지속 가능한 발전 목표(SDGs)를 달성하기 위해 노력한다."
        ),
    },
    {
        "canonical_id": "CAN-2020-023",
        "subject": "구성원 역량 개발",
        "claim_type": "원칙",
        "quote_indices": [15],
        "summary_ko": (
            "SK는 구성원의 지속적인 성장을 지원하기 위해 다양한 교육 프로그램과 "
            "개발 기회를 제공한다. 이를 통해 구성원은 자신의 역량을 향상시키고, "
            "회사의 발전에 기여할 수 있는 능력을 갖추게 된다."
        ),
    },
    {
        "canonical_id": "CAN-2020-024",
        "subject": "Better Company 목표",
        "claim_type": "원칙",
        "quote_indices": [6],
        "summary_ko": (
            "Better Company 목표는 각각 CbA(Currently by Ability) 수준으로 설정하며, "
            "경제적 가치, 사회적 가치, 구성원 행복을 키우는 다양한 요소를 "
            "종합적으로 고려하여 수립한다."
        ),
    },
    {
        "canonical_id": "CAN-2020-025",
        "subject": "SK 경영철학",
        "claim_type": "지향점",
        "quote_indices": [0, 2, 10],
        "summary_ko": (
            "SK 경영의 지향점은 지속 가능한 구성원 행복이며, VWBE를 통한 SUPEX 추구로 "
            "이를 실현한다. SKMS는 SK의 모든 구성원이 공통의 목표를 가지고 "
            "자발적·의욕적으로 경영활동에 참여하도록 장려하는 경영철학이다."
        ),
    },
]


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


def load_14th_quotes(quotes_path: str) -> list[dict]:
    """quotes.jsonl에서 2020-14차 quotes만 로드한다."""
    path = Path(quotes_path)
    if not path.exists():
        print(f"Error: {quotes_path} 파일이 없습니다.", file=sys.stderr)
        sys.exit(1)

    quotes = []
    with open(path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                print(
                    f"경고: quotes.jsonl line {line_num} JSON 파싱 오류: {e}",
                    file=sys.stderr,
                )
                continue
            if obj.get("edition_id") == "2020-14차":
                quotes.append(obj)
    return quotes


_VALID_CLAIM_TYPES = {"목적", "가치", "원칙", "정의", "지향점"}


def build_canonical(quotes: list[dict]) -> list[dict]:
    """14차 quotes와 매핑 규칙으로 canonical 항목을 생성한다."""
    canonical_items = []

    for entry in _CANONICAL_ENTRIES:
        if entry["claim_type"] not in _VALID_CLAIM_TYPES:
            raise ValueError(
                f"{entry['canonical_id']}: 유효하지 않은 claim_type "
                f"'{entry['claim_type']}'"
            )
        quote_ids = []
        for idx in entry["quote_indices"]:
            if idx < len(quotes):
                qid = quotes[idx].get("quote_id")
                if qid:
                    quote_ids.append(qid)
                else:
                    print(
                        f"경고: quotes[{idx}]에 quote_id 없음",
                        file=sys.stderr,
                    )

        if not quote_ids:
            print(
                f"경고: {entry['canonical_id']} ({entry['subject']}) — "
                f"quote_id를 매핑할 수 없습니다 (indices: {entry['quote_indices']})",
                file=sys.stderr,
            )
            continue

        item = {
            "canonical_id": entry["canonical_id"],
            "subject": entry["subject"],
            "claim_type": entry["claim_type"],
            "quote_ids": quote_ids[:3],  # 최대 3개
            "summary_ko": entry["summary_ko"],
            "doc_id": "SKMS-2020-14",
            "year": 2020,
            "edition": "2020-14차",
        }
        canonical_items.append(item)

    return canonical_items


def write_canonical(items: list[dict], output_path: str) -> None:
    """canonical 항목을 JSONL로 저장한다."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[build_canonical] {len(items)}개 canonical 항목 저장: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="2020-14차 Canonical View 생성기 (PR-5)")
    parser.add_argument(
        "--quotes",
        default="data/processed/quotes.jsonl",
        help="quotes.jsonl 경로",
    )
    parser.add_argument(
        "--output",
        default="data/processed/canonical_2020.jsonl",
        help="출력 파일 경로",
    )
    args = parser.parse_args()

    # 14차 quotes 로드
    quotes = load_14th_quotes(args.quotes)
    print(f"[build_canonical] 2020-14차 quotes: {len(quotes)}개")

    if not quotes:
        print("Error: 2020-14차 quotes가 없습니다.", file=sys.stderr)
        sys.exit(1)

    # canonical 항목 생성
    items = build_canonical(quotes)
    print(f"[build_canonical] 생성된 canonical 항목: {len(items)}개")

    # 저장
    write_canonical(items, args.output)

    # 요약
    claim_types = {}
    for item in items:
        ct = item["claim_type"]
        claim_types[ct] = claim_types.get(ct, 0) + 1

    print("\n[요약]")
    print(f"  총 항목: {len(items)}")
    for ct, count in sorted(claim_types.items()):
        print(f"  {ct}: {count}개")
    print(f"  참조된 quote_id 수: {sum(len(i['quote_ids']) for i in items)}")


if __name__ == "__main__":
    main()
