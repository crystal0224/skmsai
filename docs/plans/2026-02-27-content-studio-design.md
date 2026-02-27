# SKMS Content Studio — 설계 문서

> 작성일: 2026-02-27
> 상태: 승인됨

## 1. 개요

### 목적
SKMS RAG 파이프라인 위에 **콘텐츠 생성 레이어**를 추가하여, HR/교육담당자가 SKMS 기반 교육 자료를 자동 생성할 수 있게 한다.

### 주 사용자
- SK그룹 HR/교육담당자
- SKMS 교육 프로그램 기획자

### 배포 채널
- 사내 플랫폼 (Notion, Google Workspace, LMS)

### 우선순위
1. 강의자료 (PPTX) — 최우선
2. 카드뉴스 (PNG 세트)
3. 워크숍 시나리오 (PDF)
4. 개념 시각화 (SVG/PNG)
5. 오디오 요약 (MP3)
6. 학습 퀴즈 (PDF/HTML)

### UI (향후 과제)
- React 별도 페이지로 구현 (현 단계에서는 API + CLI만)

---

## 2. 아키텍처

### 접근법: 하이브리드 (C)
- 텍스트 구조화 + 파일 변환: **내장 Python 코드**
- 이미지/차트/오디오: **MCP 외부 서비스**
- 배포: **MCP 외부 서비스**

### 시스템 구성도

```
┌─ Content Studio ──────────────────────────────────────────────────┐
│                                                                    │
│  [1. ContentPlanner]          [2. ContentGenerator]                │
│   - 주제 분석                   - SKMS RAG 검색                    │
│   - 콘텐츠 구조 설계             - LLM 콘텐츠 생성                  │
│   - 슬라이드/카드 아웃라인        - JSON 스키마 검증                  │
│                                                                    │
│  [3. AssetGenerator]          [4. FileAssembler]                   │
│   - 나노바나나2 (이미지)         - python-pptx (PPTX)               │
│   - AntV Chart (차트/그래프)     - markdown→PDF                     │
│   - ElevenLabs (오디오)          - HTML (카드뉴스)                   │
│                                                                    │
│  [5. Publisher]                                                    │
│   - Notion MCP                                                     │
│   - Google Workspace MCP                                           │
│   - 로컬 파일 저장                                                  │
│                                                                    │
├─ MCP Adapters ────────────────────────────────────────────────────┤
│  NanoBananaAdapter │ AntVChartAdapter │ ElevenLabsAdapter          │
│  NotionAdapter     │ GoogleWorkspaceAdapter                        │
└────────────────────────────────────────────────────────────────────┘
         ↕                    ↕
   SKMS RAG (기존)      MCP Servers (외부)
```

### 5개 핵심 컴포넌트

| # | 컴포넌트 | 역할 | 내장/MCP |
|---|---------|------|---------|
| 1 | ContentPlanner | 주제→아웃라인 (슬라이드 N장, 카드 N장 등) | 내장 (LLM) |
| 2 | ContentGenerator | 아웃라인→본문 (기존 RAG + 프롬프트) | 내장 (기존 확장) |
| 3 | AssetGenerator | 이미지/차트/오디오 생성 | MCP 외부 |
| 4 | FileAssembler | 최종 파일 조립 (PPTX, PDF, HTML) | 내장 (Python) |
| 5 | Publisher | 사내 플랫폼 배포 | MCP 외부 |

---

## 3. 데이터 모델

모든 모델은 frozen dataclass (불변).

### 3.1 공통

```python
@dataclass(frozen=True)
class ContentRequest:
    content_type: str          # lecture, card_news, workshop, visualization, audio, quiz
    topic: str                 # "SUPEX 추구의 변천사"
    options: ContentOptions    # 유형별 옵션

@dataclass(frozen=True)
class ContentOptions:
    duration_min: int | None = None        # 강의/워크숍 시간(분)
    num_items: int | None = None           # 슬라이드/카드 수
    edition_filter: str | None = None      # 특정 개정판 제한
    style: str = "professional"            # 시각 스타일
    language: str = "ko"                   # 출력 언어
    include_quiz: bool = False             # 학습 퀴즈 포함 여부
    include_speaker_notes: bool = True     # 발표자 노트 포함

@dataclass(frozen=True)
class ContentResult:
    content_type: str
    topic: str
    files: tuple[GeneratedFile, ...]       # 생성된 파일 목록
    citations: tuple[str, ...]             # 사용된 quote_id
    metadata: dict                         # 생성 메타데이터
    plan: ContentPlan                      # 사용된 계획

@dataclass(frozen=True)
class GeneratedFile:
    file_type: str             # pptx, png, pdf, svg, mp3, html
    file_path: str             # 로컬 경로
    file_name: str             # 파일명
    size_bytes: int

@dataclass(frozen=True)
class GeneratedAsset:
    asset_type: str            # image, chart, audio
    file_path: str
    prompt_used: str
    width: int | None = None
    height: int | None = None
    metadata: dict = field(default_factory=dict)
```

### 3.2 강의자료 (Lecture)

```python
@dataclass(frozen=True)
class LecturePlan:
    title: str
    subtitle: str
    duration_min: int
    slides: tuple[SlidePlan, ...]
    learning_objectives: tuple[str, ...]

@dataclass(frozen=True)
class SlidePlan:
    index: int                          # 1-based
    title: str
    layout: str                         # title_only, title_content, title_content_image, comparison, section_header
    key_points: tuple[str, ...]         # 3~5개
    rag_query: str                      # RAG 검색에 사용할 쿼리
    edition_filter: str | None          # 특정 개정판 제한
    asset_type: str | None              # image, chart, None
    asset_prompt: str | None            # 이미지/차트 생성 프롬프트
    speaker_notes: str | None           # 발표자 노트
```

### 3.3 카드뉴스 (CardNews)

```python
@dataclass(frozen=True)
class CardNewsPlan:
    title: str
    total_cards: int
    cards: tuple[CardPlan, ...]
    image_size: tuple[int, int]         # (1080, 1080) 기본

@dataclass(frozen=True)
class CardPlan:
    index: int
    headline: str                       # 카드 제목 (짧게)
    body: str                           # 본문 (2~3줄)
    source_quote: str                   # 출처 quote_id
    image_prompt: str                   # 나노바나나2 프롬프트
    text_overlay: str | None            # 이미지 위 텍스트 오버레이
```

### 3.4 워크숍 시나리오 (Workshop)

```python
@dataclass(frozen=True)
class WorkshopPlan:
    title: str
    duration_min: int
    target_audience: str
    phases: tuple[WorkshopPhase, ...]

@dataclass(frozen=True)
class WorkshopPhase:
    phase_type: str                     # intro, main, activity, wrap_up
    title: str
    duration_min: int
    description: str
    facilitator_guide: str              # 진행자 가이드
    materials_needed: tuple[str, ...]   # 필요 자료
    rag_query: str | None               # RAG 검색 쿼리
```

### 3.5 오디오 (Audio)

```python
@dataclass(frozen=True)
class AudioPlan:
    title: str
    style: str                          # narration, dialogue, podcast
    total_duration_min: int
    sections: tuple[ScriptSection, ...]

@dataclass(frozen=True)
class ScriptSection:
    index: int
    speaker: str                        # narrator, host, expert
    text: str
    rag_query: str | None
```

---

## 4. MCP 어댑터 인터페이스

### 4.1 공통 Protocol

```python
class MCPAdapter(Protocol):
    async def is_available(self) -> bool: ...
    async def health_check(self) -> dict: ...

class ImageGenerator(MCPAdapter):
    async def generate_image(
        self, prompt: str, width: int, height: int, style: str
    ) -> GeneratedAsset: ...
    async def edit_image(
        self, image_path: str, edit_prompt: str
    ) -> GeneratedAsset: ...

class ChartGenerator(MCPAdapter):
    async def generate_chart(
        self, chart_type: str, data: dict, options: dict
    ) -> GeneratedAsset: ...

class AudioGenerator(MCPAdapter):
    async def text_to_speech(
        self, text: str, voice: str, language: str
    ) -> GeneratedAsset: ...

class DocumentPublisher(MCPAdapter):
    async def publish(
        self, content: dict, destination: str, metadata: dict
    ) -> str: ...  # 배포 URL 반환
```

### 4.2 MCP 서버 목록

| 순위 | MCP 서버 | 어댑터 | 용도 |
|------|---------|--------|------|
| P0 | Nano-Banana-MCP (ConechoAI) | NanoBananaAdapter | 이미지 생성 (나노바나나2) |
| P0 | Office-PowerPoint-MCP | PowerPointAdapter | PPTX 고급 제어 (대안) |
| P0 | AntV mcp-server-chart | AntVChartAdapter | 차트 26종 + 마인드맵 |
| P1 | ElevenLabs MCP | ElevenLabsAdapter | TTS 오디오 생성 |
| P1 | markdown2pdf-mcp | PdfAdapter | PDF 변환 |
| P2 | Notion MCP | NotionAdapter | Notion 배포 |
| P2 | Google Workspace MCP | GoogleWorkspaceAdapter | Google 배포 |

### 4.3 Graceful Fallback

모든 MCP 어댑터는 실패 시 fallback:
- 나노바나나2 실패 → 이미지 없이 텍스트만 슬라이드
- AntV 실패 → 표(table) 텍스트로 대체
- ElevenLabs 실패 → 스크립트 텍스트만 출력
- Notion/Google 실패 → 로컬 파일 저장

---

## 5. 콘텐츠 유형별 파이프라인

### 5.1 강의자료 PPT (최우선)

```
사용자: "SUPEX 추구의 변천사 30분 강의"
   ↓
[ContentPlanner]
   1. query_type 분석 → cross_version
   2. duration_min(30) → slides 수 산출 (30÷2 = 15장)
   3. LLM으로 아웃라인 생성:
      - S1: 표지 (제목, 부제, 날짜)
      - S2: 학습 목표
      - S3-S4: 개념 정의 (edition_filter: 10차)
      - S5-S10: 시대별 변천 (각 개정판)
      - S11: 비교표
      - S12: 토론 주제
      - S13: 요약 + 출처
   ↓
[ContentGenerator]
   - 슬라이드별 RAG 검색 (rag_query + edition_filter)
   - slide_list JSON 생성
   - EvidenceFilter 검증
   ↓
[AssetGenerator]
   - S1 표지: 나노바나나2 (기업 이미지 + 제목 텍스트)
   - S11 비교표: AntV (타임라인 차트)
   - S5-S10 삽화: 나노바나나2 (시대별 개념 시각화)
   ↓
[FileAssembler]
   - python-pptx로 PPTX 생성
   - 레이아웃 적용 (16:9, 기업 테마)
   - 발표자 노트에 상세 설명 + quote_id 출처
   - 이미지 삽입 (표지, 삽화, 차트)
   ↓
[Publisher]
   - output/lectures/supex-변천사-2026-02-27.pptx
```

### 5.2 카드뉴스

```
사용자: "VWBE 문화 카드뉴스 5장"
   ↓
[ContentPlanner] → 카드 5장 아웃라인
[ContentGenerator] → RAG 검색 → card_list JSON
[AssetGenerator] → 나노바나나2로 각 카드 이미지 (한국어 텍스트 포함, 4K)
[FileAssembler] → PNG 세트 (1080x1080)
[Publisher] → output/cardnews/vwbe-문화-2026-02-27/
```

### 5.3 워크숍 시나리오

```
사용자: "인간중심 경영 팀빌딩 워크숍 60분"
   ↓
[ContentPlanner] → 4단계 활동 구조 (도입/본론/활동/마무리)
[ContentGenerator] → RAG 검색 → 시나리오 텍스트 + quiz JSON
[AssetGenerator] → 나노바나나2 (활동 시트), AntV (그룹워크 차트)
[FileAssembler] → PDF (진행자 가이드 + 참가자 활동지)
[Publisher] → output/workshops/인간중심경영-워크숍-2026-02-27.pdf
```

### 5.4 개념 시각화

```
사용자: "SKMS 3대 기본 철학 마인드맵"
   ↓
[ContentPlanner] → 시각화 유형 선택 (mindmap)
[ContentGenerator] → RAG 검색 → 구조화된 데이터
[AssetGenerator] → AntV Chart (마인드맵 SVG)
[Publisher] → output/visualizations/3대철학-마인드맵.svg
```

### 5.5 오디오 요약

```
사용자: "SKMS 40년 변천사 5분 요약 팟캐스트"
   ↓
[ContentPlanner] → 대화형 스크립트 구조 (진행자+해설자)
[ContentGenerator] → RAG 검색 → 스크립트 텍스트
[AssetGenerator] → ElevenLabs TTS (2인 대화)
[Publisher] → output/audio/skms-40년-변천사.mp3
```

---

## 6. 설정 파일

### config/content_studio.yaml

```yaml
content_studio:
  output_dir: "output"

  mcp_servers:
    nano_banana:
      enabled: true
      model: "gemini-3.1-flash-image-preview"
      default_resolution: "1K"
      default_style: "professional"

    antv_chart:
      enabled: true
      chart_types: [timeline, mindmap, comparison, wordcloud, radar, sankey]
      theme: "classic"

    elevenlabs:
      enabled: false
      voice: "korean-female-01"
      model: "eleven_multilingual_v2"

    notion:
      enabled: false
      database_id: ""

    google_workspace:
      enabled: false

  lecture:
    min_slides: 5
    max_slides: 30
    minutes_per_slide: 2
    default_layout: "title_content_image"
    aspect_ratio: "16:9"

  card_news:
    min_cards: 3
    max_cards: 10
    image_size: [1080, 1080]

  workshop:
    default_duration_min: 60
    phases: [intro, main, activity, wrap_up]

  audio:
    max_duration_min: 10
    default_style: "narration"

  quiz:
    min_questions: 5
    max_questions: 20
    difficulty_distribution: {easy: 0.3, medium: 0.5, hard: 0.2}
```

---

## 7. 파일 구조

```
scripts/lib/
├── content_studio/
│   ├── __init__.py              # ContentStudio 메인 오케스트레이터
│   ├── models.py                # 데이터 모델 (frozen dataclass)
│   ├── planner.py               # ContentPlanner
│   ├── generator.py             # ContentGenerator (기존 RAG 래핑)
│   ├── assembler.py             # FileAssembler (PPTX, PDF, HTML)
│   ├── publisher.py             # Publisher
│   └── adapters/
│       ├── __init__.py
│       ├── base.py              # MCPAdapter Protocol
│       ├── nano_banana.py       # 나노바나나2 어댑터
│       ├── antv_chart.py        # AntV Chart 어댑터
│       ├── elevenlabs.py        # ElevenLabs 어댑터
│       ├── notion.py            # Notion 어댑터
│       └── google_ws.py         # Google Workspace 어댑터

server/routes/
├── content.py                   # Content Studio API

prompts/
├── content_lecture.md           # 강의자료 프롬프트
├── content_cardnews.md          # 카드뉴스 프롬프트
├── content_workshop.md          # 워크숍 프롬프트
├── content_audio.md             # 오디오 스크립트 프롬프트
├── content_visualization.md     # 시각화 프롬프트

config/
├── content_studio.yaml          # Content Studio 설정

output/                          # 생성된 콘텐츠
├── lectures/
├── cardnews/
├── workshops/
├── visualizations/
├── audio/
└── assets/                      # 중간 에셋 (이미지, 차트)

tests/
├── test_content_studio/
│   ├── test_models.py
│   ├── test_planner.py
│   ├── test_generator.py
│   ├── test_assembler.py
│   ├── test_publisher.py
│   └── test_adapters/
│       ├── test_nano_banana.py
│       ├── test_antv_chart.py
│       └── test_elevenlabs.py
```

---

## 8. API 엔드포인트

### POST /api/content/generate

```python
class ContentGenerateRequest(BaseModel):
    content_type: Literal["lecture", "card_news", "workshop", "visualization", "audio", "quiz"]
    topic: str
    options: dict = {}  # 유형별 옵션

class ContentGenerateResponse(BaseModel):
    request_id: str
    content_type: str
    topic: str
    plan: dict                    # 생성된 계획 (아웃라인)
    files: list[FileInfo]         # 생성된 파일 목록
    citations: list[str]          # 사용된 quote_id
    generation_time_sec: float
```

### GET /api/content/types

사용 가능한 콘텐츠 유형 + 옵션 스키마 반환.

### GET /api/content/status/{request_id}

비동기 생성 시 진행 상태 조회.

---

## 9. 테스트 전략

- 모든 데이터 모델: 직렬화/역직렬화 + 불변성 테스트
- Planner: 주제별 아웃라인 생성 정확성 (mock LLM)
- Generator: 기존 RAG 통합 테스트 (mock SearchService)
- Assembler: PPTX/PDF/HTML 파일 생성 + 구조 검증
- Adapters: MCP 호출 mock + fallback 동작 확인
- API: 엔드포인트 요청/응답 스키마 검증
- 목표: 80%+ 커버리지

---

## 10. 의존성 추가

```
# requirements.txt 추가분
python-pptx>=0.6.21          # PPTX 생성
google-generativeai>=0.8     # 나노바나나2 API (직접 호출 fallback)
```

MCP 서버는 별도 프로세스로 실행 (requirements.txt에 미포함).
