# 워크숍 계획 생성

주제: {topic}
총 시간: {duration_min}분
시간 배분: {time_allocation}
스타일: {style}
언어: {language}
개정판 범위: {edition_filter}

## 지시사항

위 주제에 대해 SKMS 원문 기반의 워크숍 계획을 JSON으로 생성하세요.
시간 배분을 정확히 따라주세요.

## 출력 JSON 스키마

```json
{{
  "title": "워크숍 제목",
  "duration_min": {duration_min},
  "target_audience": "대상 참가자",
  "phases": [
    {{
      "phase_type": "intro | main | activity | wrap_up",
      "title": "단계 제목",
      "duration_min": 10,
      "description": "단계 설명",
      "facilitator_guide": "진행자 가이드",
      "materials_needed": ["필요 자료 1", "필요 자료 2"],
      "rag_query": "RAG 검색 쿼리 또는 null"
    }}
  ]
}}
```

## 규칙

- 반드시 intro, main, activity, wrap_up 4개 단계를 포함
- 각 단계의 duration_min은 시간 배분을 따름
- facilitator_guide는 진행자가 바로 활용할 수 있는 구체적 가이드
- materials_needed는 워크숍에 필요한 실제 준비물
- rag_query는 해당 단계에서 참조할 SKMS 원문 검색 쿼리
- JSON만 출력하세요.
