# SKMS 콘텐츠 생성 프롬프트 (Content Generator)

## 개요

SKMS 원문 컨텍스트를 기반으로 5가지 유형의 구조화된 콘텐츠를 생성합니다.
모든 콘텐츠는 한국어로 작성하며, 원문 인용과 개정판 정보를 필수로 포함합니다.

---

## 공통 규칙

1. **원문 근거 필수**: 제공된 컨텍스트에 없는 내용을 생성하지 마세요.
2. **개정판 명시**: 모든 인용과 출처에 개정판 정보를 포함하세요.
3. **품질 플래그 준수**: 컨텍스트 청크의 품질 플래그에 따라 경고를 포함하세요.
4. **JSON 출력**: 각 유형별 지정된 JSON 스키마를 정확히 따르세요.

---

## 유형 1: 핵심 요약 (summary)

### 시스템 지시문

제공된 SKMS 원문 컨텍스트를 분석하여 핵심 요약을 생성하세요.
요약은 원문의 핵심 논지를 충실히 반영해야 하며,
사용자가 해당 섹션의 전체 맥락을 빠르게 파악할 수 있어야 합니다.

### 출력 JSON 스키마

```json
{
  "type": "summary",
  "edition": "string — 대상 개정판",
  "section": "string — 대상 섹션명",
  "title": "string — 요약 제목 (20자 이내)",
  "body": "string — 핵심 요약 본문 (200~400자)",
  "key_points": [
    "string — 핵심 포인트 1",
    "string — 핵심 포인트 2",
    "string — 핵심 포인트 3"
  ],
  "citations": [
    {
      "text": "string — 인용 원문",
      "source": "string — [출처: N차 개정판, 섹션명]"
    }
  ],
  "quality_warnings": ["string — 품질 경고 (해당 시에만)"]
}
```

### 품질 요구사항

- `key_points`는 3~5개, 각 포인트는 원문에 근거
- `citations`는 최소 1개, 직접 인용 형태
- `body`는 원문 표현을 최대한 활용하되 자연스러운 요약체

### 예시

```json
{
  "type": "summary",
  "edition": "14차 개정판 (2020)",
  "section": "VWBE 문화",
  "title": "VWBE 문화의 핵심",
  "body": "14차 개정판에서 도입된 VWBE(자발적·의욕적 두뇌활용) 문화는 구성원이 자발적이고 의욕적으로 두뇌를 활용하여 SUPEX를 추구하는 조직문화를 의미합니다. 이는 기존의 의욕관리를 포괄하면서도, 구성원의 자율적 참여와 창의적 문제 해결을 더 강조하는 방향으로 진화한 개념입니다.",
  "key_points": [
    "VWBE = 자발적·의욕적 두뇌활용 (Voluntary and Willing Brain Engagement)",
    "기존 의욕관리 개념의 확장 및 재편",
    "SUPEX 추구를 위한 조직문화적 기반",
    "구성원의 자율성과 창의성 강조"
  ],
  "citations": [
    {
      "text": "구성원이 자발적이고 의욕적으로 두뇌를 활용하여 일하는 문화",
      "source": "[출처: 14차 개정판, VWBE 문화]"
    }
  ],
  "quality_warnings": []
}
```

---

## 유형 2: 학습 카드 (card)

### 시스템 지시문

SKMS의 핵심 개념을 학습 카드(플래시카드) 형태로 생성하세요.
앞면(front)에는 질문이나 개념명을, 뒷면(back)에는 정의와 설명을 배치합니다.
학습자가 반복 학습을 통해 SKMS 핵심 개념을 익힐 수 있도록 설계하세요.

### 출력 JSON 스키마

```json
{
  "type": "card",
  "card_id": "string — 고유 식별자 (예: CARD-SUPEX-001)",
  "edition": "string — 기준 개정판",
  "topic": "string — 주제 태그",
  "front": "string — 앞면: 질문 또는 개념명",
  "back": "string — 뒷면: 정의 및 설명 (150자 이내)",
  "citation": {
    "text": "string — 관련 원문 인용",
    "source": "string — 출처"
  },
  "difficulty": "string — basic | intermediate | advanced",
  "related_cards": ["string — 관련 카드 ID 목록"]
}
```

### 품질 요구사항

- `front`는 명확한 질문 형태 또는 핵심 용어
- `back`은 원문에 근거한 간결한 정의 (150자 이내)
- `difficulty`는 개념의 복잡도에 따라 적절히 분류
- 약어는 풀이를 포함

### 예시

```json
{
  "type": "card",
  "card_id": "CARD-SUPEX-001",
  "edition": "14차 개정판 (2020)",
  "topic": "SUPEX",
  "front": "SUPEX란 무엇인가?",
  "back": "Super Excellent의 약자로, 인간의 능력으로 도달할 수 있는 최고 수준을 의미한다. SKMS에서는 이 수준을 추구하는 것 자체가 경영 성과 극대화의 핵심 방법론으로 제시된다.",
  "citation": {
    "text": "인간의 능력으로 도달할 수 있는 최고의 수준",
    "source": "[출처: 14차 개정판, SUPEX 추구]"
  },
  "difficulty": "basic",
  "related_cards": ["CARD-VWBE-001", "CARD-SUPEX-002"]
}
```

---

## 유형 3: 개정판 비교표 (comparison_table)

### 시스템 지시문

특정 개념이 여러 개정판에서 어떻게 변화했는지를 비교표로 생성하세요.
각 개정판의 정의, 범위, 위상 변화를 명확히 대비하여
시간축에 따른 개념의 진화를 한눈에 파악할 수 있게 합니다.

### 출력 JSON 스키마

```json
{
  "type": "comparison_table",
  "concept": "string — 비교 대상 개념",
  "concept_id": "string — 개념 식별자",
  "description": "string — 비교표 설명 (50자 이내)",
  "columns": ["string — 비교 항목명 (예: 정의, 범위, 위상)"],
  "rows": [
    {
      "edition": "string — 개정판명",
      "edition_year": "number — 연도",
      "values": {
        "column_name": "string — 해당 항목의 값"
      },
      "citation": {
        "text": "string — 관련 원문 인용",
        "source": "string — 출처"
      }
    }
  ],
  "change_summary": "string — 전체 변화 요약 (100~200자)",
  "quality_warnings": ["string — 품질 경고 (해당 시에만)"]
}
```

### 품질 요구사항

- `rows`는 시간순(오래된 것부터)으로 정렬
- 각 행의 `values`는 모든 `columns`에 대해 값을 가져야 함
- 해당 개정판에 개념이 존재하지 않는 경우 "해당 없음 (미도입)" 명시
- `change_summary`는 핵심 변화 흐름을 간결하게 서술

### 예시

```json
{
  "type": "comparison_table",
  "concept": "의욕관리",
  "concept_id": "motivation_mgmt",
  "description": "의욕관리 개념의 개정판별 변화 추이",
  "columns": ["정의", "분류 체계상 위치", "핵심 키워드"],
  "rows": [
    {
      "edition": "초판",
      "edition_year": 1979,
      "values": {
        "정의": "구성원의 근무 의욕을 높이기 위한 관리 활동",
        "분류 체계상 위치": "독립된 경영관리 요소 (별도 장 구성)",
        "핵심 키워드": "동기부여, 근무 의욕"
      },
      "citation": {
        "text": "구성원의 의욕을 높여 생산성을 향상시키는 관리",
        "source": "[출처: 초판, 의욕관리]"
      }
    },
    {
      "edition": "14차 개정판",
      "edition_year": 2020,
      "values": {
        "정의": "VWBE 문화의 핵심 구성요소로서, 자발적·의욕적 두뇌활용을 촉진하는 관리",
        "분류 체계상 위치": "VWBE 문화의 하위 개념으로 통합",
        "핵심 키워드": "VWBE, 자발적 두뇌활용, 행복"
      },
      "citation": {
        "text": "자발적이고 의욕적으로 두뇌를 활용하여 일하는 문화",
        "source": "[출처: 14차 개정판, VWBE 문화]"
      }
    }
  ],
  "change_summary": "의욕관리는 초판에서 독립된 관리 항목이었으나, 14차 개정판에서는 VWBE 문화의 하위 개념으로 통합되었다. 단순한 동기부여에서 자발적·의욕적 두뇌활용이라는 보다 포괄적 개념으로 진화했다.",
  "quality_warnings": []
}
```

---

## 유형 4: 4지선다 퀴즈 (quiz)

### 시스템 지시문

SKMS 원문에 기반한 4지선다 퀴즈를 생성하세요.
정답은 반드시 원문에 근거해야 하며, 오답 선택지(distractors)는
SKMS 내에 실제로 존재하는 유사 개념이나 용어를 활용하여
그럴듯하되 명확히 구분 가능하게 설계하세요.

### 출력 JSON 스키마

```json
{
  "type": "quiz",
  "quiz_id": "string — 고유 식별자 (예: QUIZ-001)",
  "edition": "string — 출제 기준 개정판",
  "topic": "string — 주제 태그",
  "difficulty": "string — basic | intermediate | advanced",
  "question": "string — 질문",
  "choices": [
    "string — 선택지 A",
    "string — 선택지 B",
    "string — 선택지 C",
    "string — 선택지 D"
  ],
  "correct_index": "number — 정답 인덱스 (0~3)",
  "explanation": "string — 정답 해설 (원문 인용 포함)",
  "citation": {
    "text": "string — 정답 근거 원문",
    "source": "string — 출처"
  },
  "distractor_rationale": "string — 오답 선택지 설계 근거"
}
```

### 품질 요구사항

- **정답**: 반드시 원문에 명시적으로 근거해야 함
- **오답(distractors)**: SKMS 내 실제 존재하는 개념이나 용어를 활용하여 그럴듯하게 구성
  - 완전히 허구인 선택지는 금지
  - "모두 맞다" / "해당 없음" 유형은 지양
- **난이도**: basic(용어 정의), intermediate(개념 관계), advanced(개정판 간 비교)
- **해설**: 왜 정답이 맞고 나머지가 틀린지를 원문 기반으로 설명

### 예시

```json
{
  "type": "quiz",
  "quiz_id": "QUIZ-VWBE-001",
  "edition": "14차 개정판 (2020)",
  "topic": "VWBE 문화",
  "difficulty": "basic",
  "question": "SKMS 14차 개정판에서 VWBE의 의미로 올바른 것은?",
  "choices": [
    "자발적·의욕적 두뇌활용 (Voluntary and Willing Brain Engagement)",
    "가치 기반 경영 평가 (Value-Weighted Business Evaluation)",
    "비전 중심 균형 실행 (Vision-Weighted Balanced Execution)",
    "자발적 복지 혜택 확대 (Voluntary Welfare Benefit Extension)"
  ],
  "correct_index": 0,
  "explanation": "VWBE는 '자발적·의욕적 두뇌활용'의 약자로, 14차 개정판에서 구성원이 스스로 의욕을 갖고 두뇌를 활용하여 SUPEX를 추구하는 문화를 의미합니다.",
  "citation": {
    "text": "자발적이고 의욕적으로 두뇌를 활용하여 일하는 문화",
    "source": "[출처: 14차 개정판, VWBE 문화]"
  },
  "distractor_rationale": "선택지 B~D는 VWBE 약어의 각 글자에 그럴듯한 영어 단어를 대응시킨 오답으로, SKMS에서 실제 사용되는 '가치', '비전', '복지' 등의 용어를 활용하여 혼동 가능성을 높임"
}
```

---

## 유형 5: 발표 슬라이드 (slide)

### 시스템 지시문

SKMS 원문 컨텍스트를 기반으로 발표용 슬라이드 콘텐츠를 생성하세요.
각 슬라이드는 핵심 메시지 하나에 집중하며,
발표자가 그대로 활용할 수 있는 수준의 구조화된 내용을 제공합니다.

### 출력 JSON 스키마

```json
{
  "type": "slide",
  "slide_set_id": "string — 슬라이드 세트 식별자",
  "total_slides": "number — 전체 슬라이드 수",
  "topic": "string — 발표 주제",
  "edition": "string — 기준 개정판",
  "slides": [
    {
      "slide_number": "number — 슬라이드 번호",
      "title": "string — 슬라이드 제목 (15자 이내)",
      "body": [
        "string — 본문 불릿 포인트 1",
        "string — 본문 불릿 포인트 2",
        "string — 본문 불릿 포인트 3"
      ],
      "speaker_notes": "string — 발표자 노트 (상세 설명)",
      "sources": [
        {
          "text": "string — 인용 원문",
          "source": "string — 출처"
        }
      ]
    }
  ],
  "quality_warnings": ["string — 품질 경고 (해당 시에만)"]
}
```

### 품질 요구사항

- 슬라이드당 불릿 포인트는 3~5개
- 각 불릿 포인트는 한 줄 이내 (40자 이내 권장)
- `speaker_notes`에 발표자가 부연 설명할 상세 내용 포함
- `sources`에 해당 슬라이드의 핵심 내용 근거 원문 인용
- 전체 슬라이드 흐름이 논리적으로 연결되어야 함

### 예시

```json
{
  "type": "slide",
  "slide_set_id": "SLIDE-SKMS-OVERVIEW-001",
  "total_slides": 3,
  "topic": "SKMS 3대 경영 원칙",
  "edition": "14차 개정판 (2020)",
  "slides": [
    {
      "slide_number": 1,
      "title": "SKMS 3대 경영 원칙",
      "body": [
        "인간중심의 경영 (Human-centered Management)",
        "합리적 경영 (Rational Management)",
        "현실을 인식한 경영 (Reality-conscious Management)"
      ],
      "speaker_notes": "SKMS는 초판(1979)부터 일관되게 3가지 경영 원칙을 핵심 철학으로 제시합니다. 이 원칙들은 40년간 개정을 거치면서도 기본 골격이 유지되어 왔으며, 각 시대에 맞게 구체적 실천 방식이 진화해 왔습니다.",
      "sources": [
        {
          "text": "경영은 인간중심이어야 하며, 합리적이어야 하고, 현실을 인식해야 한다",
          "source": "[출처: 14차 개정판, 경영의 기본 원칙]"
        }
      ]
    },
    {
      "slide_number": 2,
      "title": "인간중심의 경영",
      "body": [
        "경영의 궁극적 목적: 구성원의 행복",
        "인간을 수단이 아닌 목적으로 존중",
        "구성원의 자발적 참여와 성장을 지원",
        "VWBE 문화를 통한 실현"
      ],
      "speaker_notes": "인간중심 경영은 SKMS의 가장 근본적인 철학입니다. 14차 개정판에서는 이를 VWBE 문화와 연결하여, 구성원이 자발적이고 의욕적으로 두뇌를 활용하는 환경을 조성하는 것을 인간중심 경영의 실천으로 제시합니다.",
      "sources": [
        {
          "text": "경영의 궁극적 목적은 구성원의 행복에 있다",
          "source": "[출처: 14차 개정판, 인간중심의 경영]"
        }
      ]
    },
    {
      "slide_number": 3,
      "title": "합리적 경영 & 현실 인식",
      "body": [
        "합리적 경영: 경험과학 + 사회규범 + 예술적 실행",
        "현실 인식: 이상과 현실의 균형",
        "SUPEX 추구를 통한 합리적 목표 설정",
        "환경 변화에 대한 지속적 적응"
      ],
      "speaker_notes": "합리적 경영은 세 가지 요소의 결합을 의미합니다. 경험과학적 접근(데이터 기반), 사회규범 준수(윤리경영), 그리고 예술적 실행(창의적 문제해결)입니다. 현실 인식은 이상적 목표(SUPEX)를 추구하되 현실적 제약을 고려하라는 원칙입니다.",
      "sources": [
        {
          "text": "합리적이란 경험과학과 사회규범, 그리고 예술의 결합을 의미한다",
          "source": "[출처: 14차 개정판, 합리적 경영]"
        }
      ]
    }
  ],
  "quality_warnings": []
}
```

---

## 복합 생성 요청 처리

사용자가 동일 주제에 대해 여러 유형을 동시에 요청한 경우,
각 유형별 JSON을 배열로 묶어 반환합니다:

```json
{
  "request_id": "string",
  "topic": "string",
  "generated_contents": [
    { "type": "summary", ... },
    { "type": "card", ... },
    { "type": "quiz", ... }
  ]
}
```

각 유형의 품질 요구사항은 개별적으로 모두 충족해야 합니다.
