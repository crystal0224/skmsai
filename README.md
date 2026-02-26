# SKMS Time-Aware RAG Pipeline

SK경영관리체계(SKMS) 원문 텍스트(초판 1979 ~ 14차 개정판 2020, 15,330줄)를 대상으로 한 **시간 인식(Time-Aware) RAG 파이프라인**이다. 개정판 경계를 자동 감지하고, 판별 간 개념 변화를 추적하며, 인용 기반 응답을 생성한다.

---

## 디렉토리 구조

```
skmsai/
├── data/
│   ├── raw/
│   │   └── SKMSraw.txt          # 원본 텍스트 (심볼릭 링크, 15,330줄)
│   └── processed/               # 파이프라인 출력물
│       ├── structure.json       #   개정판 경계 + 헤더 트리
│       ├── docs.jsonl           #   개정판별 문서 청크
│       └── quotes.jsonl         #   QuoteObject 목록
├── config/
│   ├── regex_patterns.yaml      # 개정판 경계 정규식, 헤더 패턴, 품질 플래그
│   ├── pipeline.yaml            # 파이프라인 단계, 청킹 설정, 임베딩 설정
│   ├── retrieval.yaml           # 벡터/키워드/하이브리드 검색, 질의 라우팅
│   └── output_specs.yaml        # 5가지 출력 유형 스키마
├── prompts/
│   ├── router.md                # 질의 유형 분류 (4가지)
│   ├── answer.md                # 인용 기반 응답 생성
│   └── content_gen.md           # 5가지 출력 유형별 콘텐츠 생성
├── guardrails/
│   ├── conflict_rules.yaml      # 시간적 충돌 감지 규칙
│   └── quality_rules.yaml       # 품질 플래그, 응답 검증 규칙
├── eval/
│   └── questions.seed.jsonl     # 평가용 QA 20개 (질의 유형별 5개)
├── scripts/
│   ├── 00_extract_structure.py  # Step 0: 구조 추출
│   ├── 01_split_docs.py         # Step 1: 문서 분할
│   ├── 02_extract_quotes.py     # Step 2: 인용 청크 추출
│   ├── 03_build_indexes.py      # Step 3: 인덱스 구축
│   ├── 04_retrieve_and_answer.py # Step 4: RAG 질의응답 (v2: Temporal Conflict Guardrail)
│   ├── 05_eval_run.py           # Step 5: 품질 평가
│   └── 06_healthcheck.py        # Step 6: 파이프라인 자동 점검
├── indexes/                     # 생성 산출물: chroma/, bm25_index.pkl, meta.json
├── requirements.txt
└── README.md
```

---

## 사전 요구사항

| 항목 | 요구사항 |
|------|----------|
| Python | 3.10 이상 |
| OpenAI API Key | 임베딩 생성용 (`text-embedding-3-large`) |
| Anthropic API Key | LLM 응답 생성용 |

---

## 설치 및 환경 설정

```bash
# 가상환경 생성 및 활성화
python -m venv .venv
source .venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# API 키 환경변수 설정
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

---

## 파이프라인 실행 순서

**반드시 순서대로 실행한다.** 각 단계는 이전 단계의 출력물에 의존한다.

### Step 0: 구조 추출

```bash
python scripts/00_extract_structure.py
```

- **입력**: `data/raw/SKMSraw.txt`
- **출력**: `data/processed/structure.json`
- **설명**: 개정판 경계를 감지하고 6단계 헤더 계층(H0~H5)을 파싱하여 문서 구조 트리를 생성한다.

### Step 1: 문서 분할

```bash
python scripts/01_split_docs.py
```

- **입력**: `data/raw/SKMSraw.txt`, `data/processed/structure.json`
- **출력**: `data/processed/docs.jsonl`
- **설명**: 개정판별로 문서를 분할하고 메타데이터(개정판명, 연도, 헤더 경로)를 부착한다.

### Step 2: 인용 청크 추출

```bash
python scripts/02_extract_quotes.py
```

- **입력**: `data/processed/docs.jsonl`
- **출력**: `data/processed/quotes.jsonl`
- **설명**: 의미 단위 기반 청킹으로 QuoteObject를 생성한다. 품질 플래그(OCR 오류, 표 깨짐 등)를 자동 부착한다.

### Step 3: 인덱스 구축

```bash
python scripts/03_build_indexes.py
```

- **입력**: `data/processed/quotes.jsonl`
- **출력**: `indexes/chroma/`, `indexes/bm25_index.pkl`, `indexes/meta.json`
- **설명**: Chroma 벡터 인덱스(OpenAI 임베딩)와 BM25 키워드 인덱스를 구축한다.

### Step 4: RAG 질의응답

```bash
# 대화형 모드
python scripts/04_retrieve_and_answer.py

# 단일 질의
python scripts/04_retrieve_and_answer.py --query "SUPEX란 무엇인가?"
```

- **설명**: 하이브리드 검색(벡터 + BM25)으로 관련 인용문을 검색하고, 인용 기반 응답을 생성한다.

### Step 5: 품질 평가

```bash
# 전체 평가
python scripts/05_eval_run.py

# 일부만 평가 (처음 5개)
python scripts/05_eval_run.py --limit 5
```

- **입력**: `eval/questions.seed.jsonl`
- **출력**: `eval/results.jsonl`
- **설명**: 시드 질문에 대해 파이프라인을 실행하고 응답 품질을 자동 평가한다.

---

## 빠른 시작

```bash
# 환경 설정
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."

# 전체 파이프라인 실행 (Step 0~3)
python scripts/00_extract_structure.py
python scripts/01_split_docs.py
python scripts/02_extract_quotes.py
python scripts/03_build_indexes.py

# 대화형 질의응답
python scripts/04_retrieve_and_answer.py

# 단일 질의
python scripts/04_retrieve_and_answer.py --query "SUPEX란 무엇인가?"

# 품질 평가 (처음 5개만)
python scripts/05_eval_run.py --limit 5
```

---

## 설정 파일 안내

| 파일 | 역할 |
|------|------|
| `config/regex_patterns.yaml` | 개정판 경계 정규식(A/B/C형), 6단계 헤더 패턴(H0~H5), 정의 블록 감지, 품질 플래그 마커 |
| `config/pipeline.yaml` | 파이프라인 단계 정의, 청킹 전략(semantic, max 512 토큰), 임베딩 모델 설정 |
| `config/retrieval.yaml` | 벡터/키워드/하이브리드 검색 설정, RRF 파라미터, 질의 라우팅 규칙 |
| `config/output_specs.yaml` | 5가지 출력 유형(summary, card, comparison_table, quiz, slide) 스키마 |
| `guardrails/conflict_rules.yaml` | 개정판 간 시간적 충돌 감지 규칙 |
| `guardrails/quality_rules.yaml` | 응답 품질 검증 규칙, 인용 필수 조건 |

---

## 데이터 모델: QuoteObject (v2)

파이프라인의 핵심 데이터 단위는 `QuoteObject`이다. `quotes.jsonl`의 각 줄이 하나의 QuoteObject에 해당한다.

```json
{
  "quote_id": "1998-10차|인사관리>인적 요소의 중요성|definition|001",
  "edition_id": "1998-10차",
  "type": "definition",
  "section_path": ["인사관리", "인적 요소의 중요성"],
  "text": "인간중심의 경영이란 경영의 주체인 인간을 중시하는 경영을 뜻한다.",
  "char_span": [412500, 413200],
  "start_line": 11800,
  "token_count": 28,
  "sha256": "a1b2c3d4...",
  "quality_flags": []
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `quote_id` | string | 고유 ID (`{edition_id}\|{section_path}\|{type}\|{seq}`) |
| `edition_id` | string | 개정판 ID (`{year}-{name}`) |
| `type` | string | 6종: `definition`, `principle`, `procedure`, `checklist`, `example`, `narrative` |
| `section_path` | string[] | 헤더 경로 배열 |
| `text` | string | 원문 텍스트 |
| `char_span` | int[2] | 원본 파일 기준 `[시작문자, 종료문자]` |
| `start_line` | int | 원본 파일 시작 줄 번호 |
| `token_count` | int | 공백 기준 토큰 수 |
| `sha256` | string | 텍스트 SHA-256 해시 (무결성 검증) |
| `quality_flags` | string[] | 품질 플래그 (`ocr_error`, `table_broken`, `page_header_leak`, `reference_unresolved`, `draft_content`) |

---

## 질의 유형 — Intent (v2)

질의 라우터가 사용자 질문을 5가지 Intent로 분류하고, 의도별 검색/응답 전략을 적용한다.

| Intent | 코드 | 설명 | 검색 정책 |
|--------|------|------|----------|
| A | `specific_time` | 특정 개정판/연도 질의 | edition 필터 강제 |
| B | `general_definition` | 일반 정의 질의 (연도 미지정) | 최신판 우선 + 변천 안내 |
| C | `evolution_comparison` | 변천/비교 질의 | 전체 개정판 연대순 + 비교표 |
| D | `content_generation` | 콘텐츠 생성 (카드/퀴즈/슬라이드) | output_specs 준수 |
| E | `open_ended` | 일반 탐색 | 기본 하이브리드 검색 |

### Temporal Conflict Guardrail (v2)

동일 개념의 definition 타입 quote가 2개 이상의 개정판에 걸쳐 존재하면:
- `temporal_conflict=true` 플래그 자동 설정
- "개정판별 정의 차이" 비교 테이블 자동 삽입
- 모든 답변에 quote_id 목록 필수 출력 (최소 2개)

---

## 출력 유형 (Output Types)

응답 생성 시 5가지 출력 형식 중 하나를 선택할 수 있다.

| 유형 | 설명 | 용도 |
|------|------|------|
| `summary` | 핵심 내용 요약 | 빠른 이해, 브리핑 |
| `card` | 지식 카드 (플래시카드) | 학습, 복습 |
| `comparison_table` | 개정판 간 비교표 | 개념 변화 추적, 분석 |
| `quiz` | 4지선다 퀴즈 | 교육, 평가 |
| `slide` | 발표 슬라이드 구조 | 프레젠테이션, 강의 |

---

## Healthcheck (자동 점검)

파이프라인 전체 생성물의 건전성을 자동 검사한다. **본격 개발 착수 전 반드시 PASS 확인**할 것.

### 실행 방법

```bash
# 기본 실행 (기본 경로, 기본 임계값)
python scripts/06_healthcheck.py

# 전체 옵션 지정
python scripts/06_healthcheck.py \
  --raw data/raw/SKMSraw.txt \
  --docs data/processed/docs.jsonl \
  --toc data/processed/toc.json \
  --quotes data/processed/quotes.jsonl \
  --min_docs 2 \
  --min_quotes 50 \
  --min_toc_nodes 5 \
  --sample_k 20

# 생성물 없으면 자동 생성 + 검사
python scripts/06_healthcheck.py --auto-generate

# 리포트 파일로 저장
python scripts/06_healthcheck.py --save-report
# → eval/reports/healthcheck_YYYYMMDD_HHMM.txt
```

### 5개 체크 항목

| 체크 | 검사 내용 | PASS 기준 |
|------|----------|----------|
| CHK-1 | docs.jsonl 분할 무결성 | 2+개 문서, 필수 필드, ID 중복 없음, text 비어있지 않음 |
| CHK-2 | toc.json 구조 생성 | JSON 파싱 가능, 1+개 문서에 5+ 노드 |
| CHK-3 | quotes.jsonl 타입 커버리지 | 50+개 quote, 4+종 타입, definition 5+개 |
| CHK-4 | Quote 원문 일치 (char_span) | K개 샘플의 텍스트가 원문과 일치 + SHA-256 검증 |
| CHK-5 | Temporal Conflict 시뮬레이션 | 교차 개정판 용어 충돌 후보 1+개 검출 (0이면 WARN) |

### 기대 출력 예시

```
======================================================================
SKMS Pipeline Healthcheck Report
Timestamp: 2026-02-26 03:13:42
======================================================================

[OK] CHK-1: PASS — 12개 문서, 필드 완전, 중복 없음
[OK] CHK-2: PASS — 2979개 노드, 12개 개정판 커버, 최대 953개/판
[OK] CHK-3: PASS — 715개 quote, 6종 타입 (narrative=296, checklist=194, ...)
[OK] CHK-4: PASS — 10건 샘플 모두 원문 일치 + SHA-256 검증 통과
[OK] CHK-5: PASS — 충돌 후보 1816개 검출 (상위: 말한다, 관리, 정의)

----------------------------------------------------------------------
OVERALL: PASS
----------------------------------------------------------------------
```

FAIL 시에는 `Fix-Next Actions` 섹션에 우선순위순 수정 가이드가 자동 출력된다.

### 종료 코드

| OVERALL | 종료 코드 | 의미 |
|---------|----------|------|
| PASS | `0` | 개발 착수 가능 |
| FAIL | `1` | 수정 필요 (Fix-Next Actions 참고) |
