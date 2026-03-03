# 강의자료 슬라이드 계획 생성

주제: {topic}
총 시간: {duration_min}분
슬라이드 수: {slide_count}장
스타일: {style}
언어: {language}
개정판 범위: {edition_filter}
발표자 노트 포함: {include_speaker_notes}

## 지시사항

위 주제에 대해 SKMS 원문 기반의 강의자료 슬라이드 계획을 JSON으로 생성하세요.

## 출력 JSON 스키마

```json
{{
  "title": "강의 제목",
  "subtitle": "부제",
  "duration_min": {duration_min},
  "slides": [
    {{
      "index": 1,
      "title": "슬라이드 제목",
      "layout": "title_content | title_only | section_header",
      "key_points": ["핵심 포인트 1", "핵심 포인트 2"],
      "rag_query": "RAG 검색 쿼리"
    }}
  ],
  "learning_objectives": ["학습 목표 1", "학습 목표 2", "학습 목표 3"]
}}
```

## 규칙

- 슬라이드 수는 정확히 {slide_count}장
- 첫 슬라이드는 title_only 레이아웃 (표지)
- 마지막 슬라이드는 section_header 레이아웃 (요약/Q&A)
- learning_objectives는 3개
- key_points는 슬라이드당 2~3개 (간결하게)
- rag_query는 해당 슬라이드 내용을 검색할 수 있는 구체적인 쿼리
- JSON만 출력하세요. 설명이나 코드 펜스 없이 순수 JSON만 반환하세요.
