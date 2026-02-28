# 시각화 계획 생성

주제: {topic}
시각화 유형: {viz_type}
테마: {theme}
언어: {language}
개정판 범위: {edition_filter}

## 지시사항

위 주제에 대해 SKMS 원문 기반의 시각화 계획을 JSON으로 생성하세요.

## 시각화 유형 설명

- timeline: 시간축 기반 변천사 (개정판별 변화)
- mindmap: 개념 구조 마인드맵
- comparison: 항목 간 비교 차트
- wordcloud: 핵심 용어 워드클라우드
- radar: 다차원 비교 레이더 차트
- sankey: 개념 간 관계 흐름도
- flowchart: 프로세스 흐름도

## 출력 JSON 스키마

```json
{{
  "title": "시각화 제목",
  "viz_type": "{viz_type}",
  "data_description": "시각화할 데이터에 대한 상세 설명",
  "rag_query": "RAG 검색 쿼리",
  "chart_options": {{
    "theme": "{theme}",
    "key1": "value1"
  }}
}}
```

## 규칙

- data_description은 시각화 도구가 데이터를 구성할 수 있도록 충분히 구체적으로 작성
- rag_query는 시각화에 필요한 SKMS 원문 검색 쿼리
- chart_options에 시각화 유형에 맞는 옵션 포함
- JSON만 출력하세요.
