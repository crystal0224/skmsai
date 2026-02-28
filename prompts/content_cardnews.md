# 카드뉴스 계획 생성

주제: {topic}
카드 수: {num_cards}장
스타일: {style}
언어: {language}
개정판 범위: {edition_filter}

## 지시사항

위 주제에 대해 SKMS 원문 기반의 카드뉴스 계획을 JSON으로 생성하세요.

## 출력 JSON 스키마

```json
{{
  "title": "카드뉴스 시리즈 제목",
  "total_cards": {num_cards},
  "cards": [
    {{
      "index": 1,
      "headline": "카드 제목 (짧게)",
      "body": "본문 (2~3줄)",
      "source_quote": "출처 quote_id",
      "image_prompt": "이미지 생성 프롬프트",
      "text_overlay": "이미지 위 텍스트 오버레이 또는 null"
    }}
  ],
  "image_size": [1080, 1080]
}}
```

## 규칙

- 카드 수는 정확히 {num_cards}장
- 첫 카드는 표지 (시리즈 제목 + 핵심 이미지)
- 마지막 카드는 마무리 (핵심 요약 + CTA)
- headline은 15자 이내
- body는 2~3줄, 원문 근거
- image_prompt는 시각적으로 전문적인 이미지를 생성할 수 있는 프롬프트
- JSON만 출력하세요.
