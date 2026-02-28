# 오디오 스크립트 계획 생성

주제: {topic}
총 시간: {duration_min}분
스타일: {style}
화자 수: {speaker_count}명
언어: {language}
개정판 범위: {edition_filter}

## 지시사항

위 주제에 대해 SKMS 원문 기반의 오디오 스크립트 계획을 JSON으로 생성하세요.

## 스타일별 화자 규칙

- narration: narrator 1명 (독백 형태)
- dialogue: host + expert 2명 (대담 형태)
- podcast: host + expert1 + expert2 3명 (팟캐스트 형태)

## 출력 JSON 스키마

```json
{{
  "title": "오디오 제목",
  "style": "{style}",
  "total_duration_min": {duration_min},
  "sections": [
    {{
      "index": 1,
      "speaker": "narrator | host | expert",
      "text": "대본 텍스트",
      "rag_query": "RAG 검색 쿼리 또는 null"
    }}
  ]
}}
```

## 규칙

- 화자는 스타일에 맞는 역할만 사용
- 섹션 수는 내용에 맞게 자연스럽게 구성 (최소 3개)
- 첫 섹션은 인사/소개, 마지막 섹션은 마무리
- text는 자연스러운 구어체
- rag_query는 해당 섹션에서 참조할 SKMS 원문 검색 쿼리
- JSON만 출력하세요.
