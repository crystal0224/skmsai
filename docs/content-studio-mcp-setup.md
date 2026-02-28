# Content Studio MCP 서버 설정 가이드

> Content Studio에서 사용하는 MCP(Model Context Protocol) 어댑터 설치 및 설정 방법

## 아키텍처

Content Studio는 **하이브리드 아키텍처**를 사용합니다:
- **빌트인 Python**: 텍스트/파일 처리 (Plan, Generate, Assemble)
- **MCP 어댑터**: 시각 자료 생성 (이미지, 차트, 오디오)

```
ContentStudio
├── [Built-in] ContentPlanner (LLM)
├── [Built-in] ContentGenerator (RAG)
├── [MCP] AssetGenerator
│   ├── NanoBanana2 → 이미지 생성
│   ├── AntV Chart  → 차트/시각화
│   └── ElevenLabs  → TTS 오디오
├── [Built-in] FileAssembler
└── [MCP] Publisher
    ├── Notion → Notion DB 배포
    └── Google WS → Drive 업로드
```

## MCP 어댑터 목록

### 1. NanoBanana2 (이미지 생성)

카드뉴스, 강의자료 이미지를 생성합니다.

**설정:**
```python
from scripts.lib.content_studio.adapters import NanoBananaAdapter, NanoBananaConfig

config = NanoBananaConfig(
    endpoint="http://localhost:8080/api/generate",  # MCP 서버 URL
    api_key="your-api-key",                          # API 키 (선택)
    default_style="professional",                     # 기본 스타일
)
adapter = NanoBananaAdapter(config)
```

**환경 변수:**
```bash
NANO_BANANA_ENDPOINT=http://localhost:8080/api/generate
NANO_BANANA_API_KEY=your-api-key
```

**가용성 확인:**
```python
available = await adapter.is_available()  # endpoint 설정 여부
health = await adapter.health_check()     # {"status": "ok", "adapter": "nano_banana"}
```

### 2. AntV Chart (차트/시각화)

타임라인, 네트워크 그래프, 산키 다이어그램 등을 생성합니다.

**설정:**
```python
from scripts.lib.content_studio.adapters import AntVChartAdapter, AntVChartConfig

config = AntVChartConfig(
    endpoint="http://localhost:3000/api/chart",
    theme="corporate",
    default_width=800,
    default_height=600,
)
adapter = AntVChartAdapter(config)
```

**지원 차트 유형:**
- `bar`, `line`, `pie`, `radar` — 기본 차트
- `timeline` — 개정판 연혁
- `network` — 경영요소 관계도
- `sankey` — 개념 진화

### 3. ElevenLabs (TTS 오디오)

교육용 오디오 나레이션, 대화, 팟캐스트를 생성합니다.

**설정:**
```python
from scripts.lib.content_studio.adapters import ElevenLabsAdapter, ElevenLabsConfig

config = ElevenLabsConfig(
    api_key="your-elevenlabs-key",
    default_voice_id="korean-female-1",
    default_language="ko",
)
adapter = ElevenLabsAdapter(config)
```

**환경 변수:**
```bash
ELEVENLABS_API_KEY=your-api-key
ELEVENLABS_VOICE_ID=korean-female-1
```

## ContentStudio에 어댑터 연결

```python
from scripts.lib.content_studio import ContentStudio

studio = ContentStudio.create(
    llm_client=my_llm,
    search_service=my_search,
    generation_service=my_gen,
    image_generator=nano_banana_adapter,   # NanoBanana2
    chart_generator=antv_adapter,          # AntV Chart
    audio_generator=elevenlabs_adapter,    # ElevenLabs
    output_dir="output",
)
```

## 어댑터 없이 실행 (Fallback 모드)

MCP 어댑터가 없어도 Content Studio는 동작합니다:
- 이미지 → HTML 텍스트 fallback
- 차트 → HTML placeholder
- 오디오 → HTML 스크립트 텍스트

```python
# 어댑터 없이 초기화 — fallback 모드
studio = ContentStudio.create(
    llm_client=my_llm,
    search_service=my_search,
    generation_service=my_gen,
    output_dir="output",
)
# 이미지/차트/오디오는 HTML fallback으로 생성됨
```

## Protocol 인터페이스

모든 어댑터는 Protocol 기반으로 설계되어 커스텀 구현이 가능합니다:

```python
from scripts.lib.content_studio.adapters.base import (
    ImageGenerator,    # generate_image(), edit_image()
    ChartGenerator,    # generate_chart()
    AudioGenerator,    # text_to_speech()
    DocumentPublisher, # publish()
)
```

커스텀 어댑터 예시:
```python
class MyImageAdapter:
    async def is_available(self) -> bool:
        return True

    async def health_check(self) -> dict:
        return {"status": "ok", "adapter": "my_adapter"}

    async def generate_image(self, prompt, width, height, style):
        # 커스텀 이미지 생성 로직
        ...

    async def edit_image(self, image_path, edit_prompt):
        # 커스텀 이미지 편집 로직
        ...
```

## 문제 해결

### MCP 서버 연결 실패
```
WARNING: NanoBanana endpoint 미설정 → 이미지 생성 비활성
```
→ 환경 변수 또는 config에 endpoint URL 확인

### 에셋 생성 실패
```
WARNING: 이미지 생성 실패 (slide 2): ConnectionError
```
→ MCP 서버 상태 확인, `adapter.health_check()` 실행

### 캐시 문제
에셋은 SHA256 해시 기반으로 캐시됩니다. 캐시 초기화:
```bash
rm -rf output/assets/
```
