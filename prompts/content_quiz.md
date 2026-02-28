# 퀴즈 문항 계획 생성

주제: {topic}
총 문항 수: {num_questions}개
난이도별 문항 수: {question_counts}
난이도 분포: {difficulty_distribution}
언어: {language}
개정판 범위: {edition_filter}

## 지시사항

위 주제에 대해 SKMS 원문 기반의 퀴즈 계획을 JSON으로 생성하세요.

## 출력 JSON 스키마

```json
{{
  "title": "퀴즈 제목",
  "total_questions": {num_questions},
  "questions": [
    {{
      "index": 1,
      "question_text": "문제 텍스트",
      "choices": ["선택지 A", "선택지 B", "선택지 C", "선택지 D"],
      "correct_answer": 0,
      "explanation": "정답 해설",
      "difficulty": "easy | medium | hard",
      "source_quote": "출처 quote_id"
    }}
  ],
  "difficulty_distribution": {difficulty_distribution}
}}
```

## 규칙

- 문항 수는 정확히 {num_questions}개
- 난이도별 문항 수를 따름: {question_counts}
- 4지선다 형태, choices는 정확히 4개
- correct_answer는 0-based 인덱스 (0~3)
- explanation은 원문 기반 해설
- 오답 선택지는 SKMS 내 실제 용어를 활용하여 그럴듯하게 구성
- JSON만 출력하세요.
