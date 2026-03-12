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
      "governing_message": "이 슬라이드에서 전달할 핵심 결론 (한 문장)",
      "layout": "title_content | title_only | title_content_image | comparison | section_header",
      "key_points": ["핵심 포인트 1", "핵심 포인트 2"],
      "rag_query": "RAG 검색 쿼리",
      "design_hint": "시각적 구성 의도 (예: '좌우 1:1 대비', '중앙 키워드 강조', '상하 3단 레이아웃', '타임라인형 프로세스')",
      "asset_type": "image | chart | null",
      "asset_prompt": "이미지/차트 생성 프롬프트",
      "speaker_notes": "발표자가 참고할 부연 설명 (1~2문장)"
    }}
    ...
    - governing_message는 해당 슬라이드의 내용을 관통하는 '핵심 결론'을 전문적인 어조의 명사형 종결문으로 작성

}}
```

## 규칙

- 슬라이드 수는 정확히 {slide_count}장
- 첫 슬라이드는 title_only 레이아웃 (표지)
- 마지막 슬라이드는 section_header 레이아웃 (요약/Q&A)
- design_hint는 전문가 수준의 시각적 가이드라인을 1문장으로 제시
- asset_type과 asset_prompt를 활용하여 시각 자료가 필요한 슬라이드 지정
- learning_objectives는 3개
- key_points는 슬라이드당 2~3개 (간결하게)
- rag_query는 해당 슬라이드 내용을 검색할 수 있는 구체적인 쿼리
- speaker_notes는 발표자가 참고할 부연 설명 (1~2문장, 청중에게 보이지 않음)
- JSON만 출력하세요. 설명이나 코드 펜스 없이 순수 JSON만 반환하세요.
