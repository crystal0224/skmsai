# Content Studio 사용 가이드

> SKMS 기반 교육 콘텐츠 자동 생성 시스템

## 개요

Content Studio는 SKMS(SK Management System) 원문을 기반으로 6가지 유형의 교육 콘텐츠를 자동 생성하는 파이프라인입니다.

### 지원 콘텐츠 유형

| 유형 | 설명 | 출력 형식 |
|------|------|-----------|
| `lecture` | PPTX 슬라이드 기반 강의자료 | PPTX, HTML |
| `card_news` | 소셜 미디어용 이미지 카드 세트 | PNG, HTML |
| `workshop` | 워크숍 진행자 가이드 | HTML, PDF |
| `visualization` | 개념 시각화 (타임라인, 관계도) | SVG, PNG, HTML |
| `audio` | 교육용 오디오 (나레이션, 대화) | MP3, HTML |
| `quiz` | 4지선다 학습 확인 퀴즈 | HTML, PDF |

## 5단계 파이프라인

```
ContentPlanner → ContentGenerator → AssetGenerator → FileAssembler → Publisher
     (LLM)          (RAG 검색)        (MCP 어댑터)      (파일 조립)     (배포)
```

1. **ContentPlanner**: LLM을 사용하여 주제 → 아웃라인(Plan) 생성
2. **ContentGenerator**: RAG(검색 + 생성)으로 본문 콘텐츠 생성
3. **AssetGenerator**: MCP 어댑터를 통해 이미지/차트/오디오 에셋 생성
4. **FileAssembler**: 콘텐츠 + 에셋 → 최종 파일(PPTX/HTML/PNG) 조립
5. **Publisher**: 사내 플랫폼(Notion, Google Workspace 등)에 배포

## API 사용법

### REST API

```bash
# 서버 시작
python -m uvicorn src.api.main:app --reload
```

#### GET /api/content/types — 지원 유형 목록

```bash
curl http://localhost:8000/api/content/types
```

응답:
```json
{
  "types": [
    {
      "type": "lecture",
      "label": "강의자료",
      "description": "PPTX 슬라이드 기반 강의자료 (발표자 노트 포함)",
      "output_formats": ["pptx", "html"]
    }
  ],
  "total": 6
}
```

#### POST /api/content/plan — Plan 미리보기

```bash
curl -X POST http://localhost:8000/api/content/plan \
  -H "Content-Type: application/json" \
  -d '{
    "content_type": "lecture",
    "topic": "SUPEX 추구의 변천사",
    "options": {"duration_min": 30}
  }'
```

#### POST /api/content/generate — 전체 콘텐츠 생성

```bash
curl -X POST http://localhost:8000/api/content/generate \
  -H "Content-Type: application/json" \
  -d '{
    "content_type": "lecture",
    "topic": "인간중심경영",
    "options": {
      "duration_min": 20,
      "edition_filter": "2020-14차",
      "style": "professional",
      "include_speaker_notes": true
    }
  }'
```

응답:
```json
{
  "content_type": "lecture",
  "topic": "인간중심경영",
  "files": [
    {
      "file_type": "pptx",
      "file_path": "output/lectures/인간중심경영-2026-02-28.pptx",
      "file_name": "인간중심경영-2026-02-28.pptx",
      "size_bytes": 45230
    }
  ],
  "citations": ["q-001", "q-015"],
  "metadata": {
    "content_type": "lecture",
    "total_elapsed_ms": 1523.4
  }
}
```

### Python API

```python
from scripts.lib.content_studio import ContentStudio
from scripts.lib.content_studio.models import ContentRequest, ContentOptions

# 초기화
studio = ContentStudio.create(
    llm_client=my_llm,
    search_service=my_search,
    generation_service=my_gen,
    output_dir="output",
)

# Plan 미리보기
request = ContentRequest(
    content_type="lecture",
    topic="SUPEX 추구",
    options=ContentOptions(duration_min=30),
)
plan = await studio.plan_only(request)
print(plan.to_dict())

# 전체 생성
result = await studio.generate(request)
for f in result.files:
    print(f"생성됨: {f.file_path} ({f.size_bytes} bytes)")
```

## 옵션 (ContentOptions)

| 옵션 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `duration_min` | int | 30 | 강의/워크숍/오디오 시간(분) |
| `num_items` | int | 5 | 슬라이드/카드/문항 수 |
| `edition_filter` | str | None | 특정 개정판만 참조 (예: "2020-14차") |
| `style` | str | "professional" | 시각 스타일 |
| `language` | str | "ko" | 출력 언어 |
| `include_quiz` | bool | False | 강의자료에 퀴즈 포함 |
| `include_speaker_notes` | bool | True | 발표자 노트 포함 |

## 에러 처리

Content Studio는 파이프라인 단계별 에러 계층을 제공합니다:

```
ContentStudioError (base)
├── PlanningError     — Plan 생성 실패
├── GenerationError   — RAG 콘텐츠 생성 실패
├── AssetError        — 이미지/차트/오디오 생성 실패
├── AssemblyError     — 파일 조립 실패
└── PublishError      — 배포 실패
```

각 에러는 `stage` 속성으로 실패 단계를 식별할 수 있습니다:

```python
try:
    result = await studio.generate(request)
except PlanningError as e:
    print(f"Plan 실패: {e}")
except ContentStudioError as e:
    print(f"[{e.stage}] 실패: {e}")
```

## 출력 디렉토리 구조

```
output/
├── lectures/          # 강의자료 PPTX/HTML
├── cardnews/          # 카드뉴스 PNG/HTML
├── workshops/         # 워크숍 HTML
├── visualizations/    # 시각화 SVG/PNG/HTML
├── audio/             # 오디오 MP3/HTML
├── quizzes/           # 퀴즈 HTML
└── assets/            # 캐시된 에셋 파일
```
