# SKMS Time-Aware RAG Pipeline — TODO

> 마지막 업데이트: 2026-02-28
> Phase 0~3 완료 (39 PR) | Phase 4 PR-040~052 + Cross-Cutting 완료 (1793 tests, frontend build OK)

---

## Phase 0: Data Foundation (완료)

- [x] **PR-001** Project Scaffold — repo init, pyproject.toml
- [x] **PR-002** OpenAPI Spec + API Schema Design
- [x] **PR-003** Data Diagnosis + Edition Splitter
- [x] **PR-004** Section Parser (6-Level H0-H5) — TOCNode Tree JSON
- [x] **PR-005** Semantic Chunker + Quality Flagger
- [x] **PR-006** Embedding Benchmark — 모델 비교 평가
- [x] **PR-007** Prompt v0 — Quote-Anchored Base Template + Smoke Test + Security Hardening
- [x] **PR-008** Eval Framework + Regression Tests (113 tests, 6/6 smoke)

### PR-1~8 산출물 요약
| 산출물 | 파일/경로 | 비고 |
|--------|-----------|------|
| 원문 분리 | `scripts/00_extract_structure.py`, `01_split_docs.py` | 12개 개정판 |
| QuoteObject 추출 | `scripts/02_extract_quotes.py` | 714개 quotes |
| 인덱스 빌드 | `scripts/03_build_indexes.py` | Chroma + BM25 |
| 검색+생성 | `scripts/04_retrieve_and_answer.py` | Hybrid search → LLM |
| 평가 프레임워크 | `scripts/05_eval_run.py` | 22 seed questions |
| 헬스체크 | `scripts/06_healthcheck.py` | 인프라 검증 |
| 정책 레이어 | `scripts/lib/policy.py` | 5종 intent routing |
| 출력 검증 | `scripts/lib/output_validator.py` | Pydantic v2 스키마 |
| 검색 통합 | `scripts/lib/retrieval.py` | retrieve_quotes() |
| 테스트 | `tests/` (7 files, 113 functions) | 전체 PASS |

---

## Phase 1: Foundation + MVP Core (PR-9 ~ PR-16)

- [x] **PR-009** QuoteObject Schema + DB Migration
  - QuoteObject frozen dataclass (13 fields, content_hash 멱등성)
  - SQLite DDL + 5 indexes + CHECK constraints
  - QuoteRepository CRUD + bulk_upsert
  - JSONL → DB 마이그레이션 스크립트
  - 48 tests (22 unit + 26 integration)

- [x] **PR-010** Ingestion Pipeline — 멱등 데이터 적재
  - IngestPipeline: load_jsonl → ingest → verify 3단계
  - content_hash 기반 중복 방지, 배치 적재
  - IngestResult + IngestVerification frozen dataclass
  - 32 tests

- [x] **PR-011** Vector Store (Chroma) + BM25 Index + SearchService
  - VectorStore: Chroma 래퍼 (from_path/ephemeral, upsert, query)
  - BM25Index: from_path/from_quotes, 개정판/타입 필터 검색
  - SearchService: vector/bm25/hybrid(RRF) 검색, search_by_edition
  - SearchHit frozen dataclass (표준화된 검색 결과)
  - 11_build_indexes_from_db.py: DB 소스 인덱스 구축 CLI
  - 38 tests

- [x] **PR-012** Generation Service + QueryRouter
  - GenerationService: context formatting → LLM 호출 → 출력 검증 + 재시도
  - QueryRouter: 5가지 intent 분류 (LLM 기반), 동적 top_k 조정
  - GenerationConfig: YAML 기반 설정 (model, max_tokens, prompts_dir)
  - format_context(), detect_temporal_conflicts()
  - 62 tests (28 router + 34 generation)

- [x] **PR-013** FastAPI Server + Middleware
  - FastAPI 앱: CORS (환경변수 기반), 로깅 미들웨어, 글로벌 에러 핸들러
  - AppState: DI (SearchService + GenerationService)
  - Pydantic v2 요청/응답 모델 (Literal output_type 검증)
  - GET /api/health (503 when not ready), POST /api/search, POST /api/generate
  - 22 tests

- [x] **PR-014** TOC API — 개정판별 목차 트리 제공
  - TOCService: structure.json → 12개 개정판 목차 트리 (불변 데이터 모델)
  - GET /api/editions, GET /api/toc/{edition_id}, GET /api/toc?q=검색
  - 35 tests (20 service + 15 API)

- [x] **PR-015** Streamlit MVP UI
  - 3-탭 UI: 검색 (hybrid/vector/bm25), 답변 생성, 개정판 목차 브라우저
  - API 클라이언트 (에러 핸들링, timeout), 환경변수 기반 엔드포인트 설정
  - 14 tests

- [x] **PR-016** MVP Quality Gate — Go/No-Go 판정
  - QualityGate: results.jsonl → 4축 통계 → 통과율 기반 판정
  - EvalResult/AxisStats/QualityReport frozen dataclasses
  - Markdown/JSON 보고서 생성
  - 26 tests

---

## Phase 2: V1 Production (PR-17 ~ PR-30)

- [x] **PR-017** Synonym Map — 동의어 매핑 (≥80쌍)
  - config/synonyms.yaml: 56 클러스터, 185 용어, 230 양방향 쌍
  - SynonymMap/SynonymCluster frozen dataclass (불변)
  - from_yaml/from_dict, get_cluster, get_synonyms, expand_terms, expand_query
  - _normalize: 소문자+공백/하이픈/마침표 제거로 변형 자동 매칭
  - 41 tests (단위 + 통합)
- [x] **PR-018** Concept-Timeline Map — 개념별 시계열 추적 (30+개)
  - config/concept_timeline.yaml: 35 개념, 6 카테고리, 12 개정판(1979-2020)
  - ConceptTimeline/ConceptInfo/EditionStatus frozen dataclass (불변)
  - from_yaml, get_concept, get_by_category/edition, search_concepts, get_evolution_summary
  - 개정판별 상태: introduced/maintained/modified/renamed/removed
  - 39 tests (단위 + 실제 YAML 통합)
- [x] **PR-019** BM25 Index 고도화 — 정의 블록 가중 + 동의어 확장
  - BM25Index.search(): synonym_map 파라미터 추가, expand_query로 동의어 확장
  - SearchService: synonym_map 주입, bm25_search/hybrid_search에서 자동 확장
  - 기존 type_boost (definition: 2.0) + 동의어 확장 결합
  - 하위 호환: synonym_map=None이면 기존 동작 유지
  - 8 new tests (총 477 PASS)
- [x] **PR-020** Hybrid Retrieval — Vector + BM25 RRF 융합
  - HybridConfig frozen dataclass: alpha, rrf_k, final_top_k 등 YAML 기반 설정
  - BM25 점수 정규화: min-max scaling (0~1), 동일 점수 시 0.5
  - hybrid_search: config 기본값 + 호출 시 오버라이드 지원
  - 하위 호환: hybrid_config=None → 기본값 사용
  - 13 new tests (총 490 PASS)
- [x] **PR-021** Reranker — Cohere + Cross-Encoder 재순위
  - RerankerConfig frozen dataclass: enabled, backend, model, top_n, score_threshold
  - CohereReranker: Cohere Rerank API 기반, API 오류 시 graceful fallback
  - CrossEncoderReranker: sentence-transformers 기반, sigmoid 정규화 (0~1)
  - Reranker Protocol + create_reranker 팩토리 (환경변수/패키지 자동 감지)
  - SearchService.hybrid_search() optional reranker step 통합
  - 하위 호환: reranker=None → 기존 동작 유지
  - 31 new tests (총 521 PASS)
- [x] **PR-022** Query Router — 4-Type 질의 분류 (≥90%)
  - QueryClassifier: 규칙 기반 4-Type 분류 (single_version, cross_version, definition, open_ended)
  - ClassificationResult frozen dataclass (query_type, confidence, edition_hint, reasoning)
  - 분류 우선순위: cross_version → single_version → definition → open_ended
  - edition_hint 자동 추출 (N차, 초판, 연도 패턴)
  - evaluate_accuracy(): seed questions 기반 정확도 측정
  - INTENT_TO_QUERY_TYPE: 기존 5-intent → 4-type 매핑 (하위 호환)
  - Seed questions (22건) 전체 정확도 ≥90% 달성
  - 50 new tests (총 571 PASS)
- [x] **PR-023** Temporal Conflict Guardrail — 시간축 충돌 방어
  - TemporalGuardrail: 4-rule 충돌 감지 서비스 (TC-001~TC-004)
  - TC-001: 정의 변경 감지 (다중 개정판 definition quote)
  - TC-002: 개념 소멸 감지 (concept_timeline 기반, is_active=False)
  - TC-003: 개념 신설 감지 (edition_hint < first_edition)
  - TC-004: 용어 변경 감지 (renamed 상태 개정판)
  - KnownConflict: guardrails/conflict_rules.yaml 사전 충돌 매칭
  - GuardrailConfig: enabled, max_warnings, fail_mode
  - 경고 중복 제거 (rule_id + concept 기준)
  - 31 new tests (총 602 PASS)
- [x] **PR-024** Evidence Coverage + Hallucination Filter
  - EvidenceFilter: quote_id 인용 검증 + 커버리지 점수 + 환각 지표 감지
  - EvidenceCheckResult/EvidenceFilterConfig frozen dataclass (불변)
  - _compute_coverage(): 4자 이상 구문 기반 근거 매칭률 추정
  - _check_edition_references(): 개정판 참조 검증 (hit_editions 대조)
  - _detect_hallucination_indicators(): 일반론/조항번호/날짜/백분율 패턴 감지
  - EvidenceFilterConfig: min_coverage, max_invalid_quotes, check_editions, check_hallucination
  - 32 new tests (총 634 PASS)
- [x] **PR-025** Cross-version Comparison — 개정판 간 비교 프롬프트
  - CrossVersionComparisonService: 개정판별 그룹화 + 비교 컨텍스트 생성
  - EditionGroup/ComparisonContext/ComparisonConfig frozen dataclass (불변)
  - _group_by_edition(): definition/narrative 분리, 텍스트 잘림
  - _lookup_evolution(): ConceptTimeline 진화 요약 통합
  - format_comparison_prompt(): LLM 프롬프트용 구조화된 비교 포맷
  - EDITION_ORDER: 15개 개정판 시간순 정렬 매핑
  - 38 new tests (총 672 PASS)
- [x] **PR-026** Output Renderer 3-type — summary/card/comparison_table
  - OutputRenderer: summary/card/comparison_table Markdown 렌더러
  - RenderResult frozen dataclass (불변)
  - render_summary(): 제목+본문+핵심포인트+출처
  - render_card()/render_card_list(): Q&A 카드 + 카드 목록
  - render_comparison_table(): 개정판 비교표 + 진화 요약 + 출처 중복 제거
  - render(): output_type 기반 자동 디스패치 (JSON 추출 + 파싱 + 렌더링)
  - 26 new tests (총 698 PASS)
- [x] **PR-027** API v2 — Hybrid Search + Generate v2
  - POST /api/v2/search: 근거 검증 + 개정판 비교 통합 검색
  - POST /api/v2/generate: 근거 검증 + 렌더링 통합 답변 생성
  - V2 Pydantic 모델: SearchV2Request/Response, GenerateV2Request/Response
  - EvidenceCheckResponse, ComparisonResponse, EditionGroupResponse
  - AppState v2: EvidenceFilter + CrossVersionComparisonService 초기화
  - 하위 호환: v1 엔드포인트 유지, v2는 /api/v2/ 경로
  - 20 new tests (총 718 PASS)
- [x] **PR-028** TOC Visualization — 인터랙티브 목차 트리 뷰어
  - TOCVisualization: Markdown 트리 렌더링 + 경로 탐색 + 통계 + 비교
  - TreeStats/BreadcrumbItem/EditionComparison frozen dataclass (불변)
  - render_tree(): +/- 마커, max_depth 제한, 레벨/줄번호 표시
  - render_breadcrumb(): 줄번호 → 경로(breadcrumb) 탐색
  - get_tree_stats(): 전체 노드/최대 깊이/레벨별 카운트/리프 수
  - compare_editions(): H1/H2 기준 공통/차이 분석 + 통계 비교표
  - 26 new tests (총 744 PASS)
- [x] **PR-029** LLM-as-Judge — 4축 자동 평가기
  - LLMClient Protocol: DI용 LLM API 추상화 (테스트 시 mock 교체)
  - JudgeConfig frozen dataclass: 모델, 토큰, 임계값, 시스템 프롬프트 설정
  - JudgeScore frozen dataclass: 4축 점수 + reasoning + to_dict/mean_score
  - AxisResult frozen dataclass: 축별 통과 결과 (점수/임계값/passed)
  - JudgeResult frozen dataclass: 전체 평가 결과 + to_eval_dict (QualityGate 호환)
  - LLMJudge 서비스: evaluate() 단건 + evaluate_batch() 배치 평가
  - format_judge_context(): SearchHit/dict 호환 컨텍스트 포맷팅
  - parse_judge_response(): JSON/코드블록 파싱 + 점수 클램핑
  - check_thresholds(): DEFAULT_THRESHOLDS 기반 축별 통과 판정
  - JUDGE_SYSTEM_PROMPT: 05_eval_run.py 프롬프트 정형화
  - 53 new tests (총 797 PASS)
- [x] **PR-030** Golden QA 50 + V1 Quality Report
  - eval/questions.golden_v1.jsonl: 50 Golden QA (4 유형, 3 난이도, 5 회귀검사)
  - GoldenQuestion frozen dataclass: id, query, query_type, difficulty, regression_checks
  - QueryTypeBreakdown/DifficultyBreakdown frozen dataclass (유형별/난이도별 분석)
  - V1QualityReport frozen dataclass (전체 보고서 + 유형별 + 난이도별 + 회귀 통계)
  - load_golden_questions(): JSONL 로드 + 파싱
  - compute_query_type_breakdowns(): 유형별 분석 (축별 통계 포함)
  - compute_difficulty_breakdowns(): 난이도별 분석
  - generate_v1_report(): QualityGate 통합 V1 보고서 생성
  - format_v1_report_markdown(): Markdown 보고서 (개요/축별/유형별/난이도별/실패목록)
  - format_v1_report_json(): JSON 직렬화
  - 39 new tests (총 836 PASS)

---

## Phase 3: V2 Production (PR-31 ~ PR-39)

- [x] **PR-031** Pinecone 마이그레이션 (Chroma → Pinecone)
- [x] **PR-032** Quiz + Slide 렌더러 추가
- [x] **PR-033** 프롬프트 최종 튜닝 + 전체 Output 통합 테스트
- [x] **PR-034** Next.js V2 프로덕션 UI
- [x] **PR-035** 운영 대시보드 (모니터링 + 사용 통계)
- [x] **PR-036** 데이터 자동 업데이트 배치 + 인덱스 갱신
- [x] **PR-037** 성능 최적화 + 부하 테스트
- [x] **PR-038** 보안 검토 + 프로덕션 배포
  - RateLimiter: Token Bucket 알고리즘, 클라이언트별 독립 버킷, thread-safe
  - EnvValidationResult: 필수/선택 환경변수 검증, CORS 와일드카드 경고
  - 입력 살균: sanitize_query (HTML/제어문자 제거), sanitize_edition_filter (regex), sanitize_type_filter (whitelist)
  - Dockerfile: python:3.10-slim, non-root appuser, HEALTHCHECK, uvicorn 2 workers
  - docker-compose.yml: api(8000) + frontend(3000), 헬스체크 의존성
  - 50 new tests (총 1127 PASS)
- [x] **PR-039** Golden QA 100 + 최종 품질 대시보드
  - Golden QA V2: 50개 추가 (g-051~g-100), 총 100개 (4유형, 3난이도, 7개정판 커버)
  - quality_dashboard.py: V2QualityReport, EditionCoverage, QualitySummary (frozen)
  - 커버리지 분석: 7개 개정판 100% 커버, compute_coverage_score
  - 축별 품질 요약: 약한 유형 자동 탐지, 권장사항 생성
  - 종합 등급: A/B/C/D/F (통과율 50% + 커버리지 25% + 회귀 25%)
  - Quality API: /api/quality/report, /coverage, /summary 3개 엔드포인트
  - 58 new tests (총 1185 PASS)

---

## Gap Checklist (SHOULD — 완료)

- [x] **S01** Phase별 비용 추정 → `docs/S01-cost-estimation.md`
- [x] **S02** 성능 목표 수치 (P50/P95/P99) → `docs/S02-performance-targets.md`
- [x] **S03** CI/CD 파이프라인 명세 → `docs/S03-cicd-pipeline.md`
- [x] **S04** 모니터링/알림 전략 (SLO/SLI) → `docs/S04-monitoring-alerting.md`
- [x] **S07** 테스트 전략 문서 → `docs/S07-testing-strategy.md`

---

## Phase 4: Content Studio (PR-40 ~ PR-52)

> 설계 문서: `docs/plans/2026-02-27-content-studio-design.md`
> 아키텍처: 하이브리드 (텍스트/파일=내장 Python, 시각/배포=MCP 외부)
> 주 사용자: HR/교육담당자 | 우선 콘텐츠: 강의자료 PPT
> UI: React 별도 페이지 (향후 과제)

### Step 1: 기반 구조 (PR-40 ~ PR-42)

- [x] **PR-040** Content Studio 데이터 모델 + 설정
  - `scripts/lib/content_studio/models.py`: 전체 데이터 모델 (frozen dataclass)
    - ContentRequest, ContentOptions, ContentResult, GeneratedFile, GeneratedAsset
    - LecturePlan, SlidePlan (index, title, layout, key_points, rag_query, asset_type, asset_prompt, speaker_notes)
    - CardNewsPlan, CardPlan (headline, body, source_quote, image_prompt, text_overlay)
    - WorkshopPlan, WorkshopPhase (phase_type, facilitator_guide, materials_needed)
    - AudioPlan, ScriptSection (speaker, text)
    - VisualizationPlan (viz_type, data_structure, chart_options)
    - QuizPlan, QuizQuestion (question_text, choices, correct_answer, explanation, difficulty)
  - `scripts/lib/content_studio/__init__.py`: ContentStudio 오케스트레이터 클래스
  - `config/content_studio.yaml`: 전체 설정 (MCP 서버, 콘텐츠 유형별 옵션)
  - 테스트: 모델 직렬화/역직렬화, 불변성, YAML 로드, 기본값 검증
  - 예상: ~30 tests
  - **세부 과제:**
    - [ ] 공통 모델 정의 (ContentRequest, ContentOptions, ContentResult, GeneratedFile, GeneratedAsset)
    - [ ] 강의자료 모델 (LecturePlan, SlidePlan) + layout enum 검증
    - [ ] 카드뉴스 모델 (CardNewsPlan, CardPlan) + image_size 기본값 (1080x1080)
    - [ ] 워크숍 모델 (WorkshopPlan, WorkshopPhase) + phase_type enum 검증
    - [ ] 오디오 모델 (AudioPlan, ScriptSection) + style enum (narration/dialogue/podcast)
    - [ ] 시각화 모델 (VisualizationPlan) + viz_type enum (timeline/mindmap/comparison/radar/sankey)
    - [ ] 퀴즈 모델 (QuizPlan, QuizQuestion) + difficulty enum (easy/medium/hard)
    - [ ] ContentPlan 유니온 타입: LecturePlan | CardNewsPlan | WorkshopPlan | AudioPlan | VisualizationPlan | QuizPlan
    - [ ] 모든 모델에 to_dict() / from_dict() 직렬화 메서드
    - [ ] content_studio.yaml 작성 (MCP 서버 설정, 유형별 기본값, output_dir)
    - [ ] YAML 로더: `load_content_studio_config(path) → dict` + 스키마 검증
    - [ ] `__init__.py` ContentStudio 클래스 스켈레톤 (create 메서드 시그니처만)
    - [ ] 테스트: frozen 불변성, 필수 필드 누락 시 TypeError, 기본값 적용, YAML 로드

- [x] **PR-041** MCP 어댑터 기반 + 나노바나나2 어댑터
  - `scripts/lib/content_studio/adapters/base.py`: MCPAdapter Protocol 정의
    - MCPAdapter: is_available(), health_check()
    - ImageGenerator: generate_image(prompt, width, height, style) → GeneratedAsset
    - ChartGenerator: generate_chart(chart_type, data, options) → GeneratedAsset
    - AudioGenerator: text_to_speech(text, voice, language) → GeneratedAsset
    - DocumentPublisher: publish(content, destination, metadata) → URL
  - `scripts/lib/content_studio/adapters/nano_banana.py`: 나노바나나2 어댑터
    - NanoBananaAdapter(ImageGenerator) 구현
    - Gemini API 직접 호출 (google-generativeai SDK)
    - generate_image(): 프롬프트 → 이미지 파일 저장 → GeneratedAsset
    - edit_image(): 기존 이미지 + 편집 프롬프트 → 수정된 이미지
    - 해상도 설정: 512px, 1K, 2K, 4K
    - 비율 지원: 16:9 (PPT), 1:1 (카드뉴스), 9:16 (스토리)
    - Graceful fallback: API 실패 시 None 반환 (이미지 없이 진행)
    - 파일 저장: output/assets/nano-banana-{timestamp}-{id}.png
  - MCP 서버 설치 가이드: Nano-Banana-MCP (ConechoAI/Nano-Banana-MCP)
    - `npm install nano-banana-mcp`
    - Claude Code MCP 설정 JSON
    - GEMINI_API_KEY 환경변수 설정
  - 테스트: mock API로 이미지 생성/편집, fallback, 파일 저장 검증
  - 예상: ~25 tests
  - **세부 과제:**
    - [ ] MCPAdapter Protocol 정의 (is_available, health_check — async)
    - [ ] ImageGenerator Protocol 정의 (generate_image, edit_image)
    - [ ] ChartGenerator Protocol 정의 (generate_chart)
    - [ ] AudioGenerator Protocol 정의 (text_to_speech)
    - [ ] DocumentPublisher Protocol 정의 (publish)
    - [ ] NanoBananaAdapter 클래스 구현 (google-generativeai SDK 래핑)
    - [ ] 해상도 매핑 딕셔너리: {"512": (512,512), "1K": (1024,1024), "2K": (2048,2048), "4K": (4096,4096)}
    - [ ] 비율 매핑: {"16:9": (1920,1080), "1:1": (1080,1080), "9:16": (1080,1920)}
    - [ ] output/assets/ 디렉토리 자동 생성 (존재하지 않으면)
    - [ ] 파일명 생성 유틸: `nano-banana-{timestamp}-{uuid4[:8]}.png`
    - [ ] Graceful fallback: API 타임아웃(30s) / 인증 실패 / 네트워크 오류 → None + 로그
    - [ ] requirements.txt에 `google-generativeai>=0.8` 추가
    - [ ] 테스트: mock Gemini API → 정상 이미지 생성, 편집, 해상도별, fallback 3종

- [x] **PR-042** AntV Chart 어댑터 + ElevenLabs 어댑터
  - `scripts/lib/content_studio/adapters/antv_chart.py`: AntV 차트 어댑터
    - AntVChartAdapter(ChartGenerator) 구현
    - 차트 유형: timeline, mindmap, comparison, wordcloud, radar, sankey, flowchart
    - generate_chart(): 데이터 + 옵션 → SVG/PNG 파일
    - 테마 지원: classic, dark, light
    - SKMS 특화: 개정판 타임라인, 개념 마인드맵, 경영요소 레이더
  - `scripts/lib/content_studio/adapters/elevenlabs.py`: ElevenLabs 어댑터
    - ElevenLabsAdapter(AudioGenerator) 구현
    - text_to_speech(): 텍스트 + 음성 → MP3 파일
    - 한국어 음성 지원
    - 멀티스피커: narrator, host, expert 역할별 음성 설정
    - 오디오 합성: 여러 섹션 → 단일 MP3 파일
  - MCP 서버 설치 가이드: AntV mcp-server-chart, ElevenLabs MCP
  - Graceful fallback: 각각 텍스트 표/스크립트로 대체
  - 테스트: mock API로 차트/오디오 생성, fallback 검증
  - 예상: ~30 tests
  - **세부 과제:**
    - [ ] AntVChartAdapter 클래스 스켈레톤 (ChartGenerator Protocol 준수)
    - [ ] chart_type 검증: 허용 목록 (timeline, mindmap, comparison, wordcloud, radar, sankey, flowchart)
    - [ ] 차트 데이터 구조 변환: SKMS 데이터 → AntV 입력 포맷 (유형별 JSON 스키마)
    - [ ] SVG/PNG 파일 저장: output/assets/chart-{type}-{timestamp}.{ext}
    - [ ] SKMS 특화 헬퍼: edition_timeline_data(), concept_mindmap_data(), element_radar_data()
    - [ ] AntV fallback: 차트 생성 실패 시 Markdown 표 텍스트 반환
    - [ ] ElevenLabsAdapter 클래스 구현 (AudioGenerator Protocol 준수)
    - [ ] 음성 설정 매핑: {"narrator": "korean-female-01", "host": "korean-male-01", "expert": "korean-male-02"}
    - [ ] 멀티섹션 합성: 여러 ScriptSection → pydub로 MP3 연결 (또는 ElevenLabs API 합성)
    - [ ] ElevenLabs fallback: TTS 실패 시 스크립트 텍스트 PDF 반환
    - [ ] 테스트: mock AntV → chart_type별 생성, 테마 적용, fallback
    - [ ] 테스트: mock ElevenLabs → TTS 생성, 멀티스피커, 합성, fallback

### Step 2: 핵심 파이프라인 (PR-43 ~ PR-46)

- [x] **PR-043** ContentPlanner — 주제→아웃라인 생성
  - `scripts/lib/content_studio/planner.py`: ContentPlanner 서비스
    - plan_lecture(topic, duration_min, options) → LecturePlan
      - query_type 분석 (single_version/cross_version/definition/open_ended)
      - duration → slides 수 산출 (minutes_per_slide 설정 기반)
      - LLM으로 아웃라인 생성 (제목, 키포인트, RAG 쿼리, 에셋 유형)
      - 학습 목표 3~5개 자동 생성
    - plan_card_news(topic, num_cards, options) → CardNewsPlan
      - 카드별 headline/body/image_prompt 생성
      - 출처 quote_id 사전 매핑
    - plan_workshop(topic, duration_min, options) → WorkshopPlan
      - 4단계 활동 구조 (도입 10% / 본론 40% / 활동 30% / 마무리 20%)
      - 단계별 진행자 가이드 + 필요 자료
    - plan_audio(topic, duration_min, style, options) → AudioPlan
      - narration/dialogue/podcast 스타일별 구조
      - 섹션별 speaker + text 구조
    - plan_visualization(topic, viz_type, options) → VisualizationPlan
    - plan_quiz(topic, num_questions, options) → QuizPlan
  - 프롬프트 템플릿:
    - `prompts/content_lecture.md`: 강의자료 아웃라인 생성 프롬프트
    - `prompts/content_cardnews.md`: 카드뉴스 구조 생성 프롬프트
    - `prompts/content_workshop.md`: 워크숍 시나리오 프롬프트
    - `prompts/content_audio.md`: 오디오 스크립트 프롬프트
    - `prompts/content_visualization.md`: 시각화 데이터 구조 프롬프트
    - `prompts/content_quiz.md`: 퀴즈 생성 프롬프트
  - 테스트: 유형별 아웃라인 생성 (mock LLM), 슬라이드 수 산출, 옵션 적용
  - 예상: ~35 tests
  - **세부 과제:**
    - [ ] ContentPlanner 클래스 (LLM 클라이언트 DI, config 주입)
    - [ ] plan_lecture(): QueryClassifier로 query_type 판별 → 슬라이드 수 = duration_min ÷ minutes_per_slide
    - [ ] plan_lecture(): LLM 호출 → JSON 파싱 → LecturePlan 변환 (파싱 실패 시 재시도 1회)
    - [ ] plan_lecture(): 학습 목표 자동 생성 (3~5개, topic + key_points 기반)
    - [ ] plan_card_news(): LLM 호출 → CardNewsPlan 변환, num_cards 범위 검증 (3~10)
    - [ ] plan_workshop(): 4단계 시간 배분 로직 (intro 10%, main 40%, activity 30%, wrap_up 20%)
    - [ ] plan_audio(): style별 구조 분기 (narration=단독, dialogue=2인, podcast=3인)
    - [ ] plan_visualization(): viz_type 검증 + 데이터 구조 생성
    - [ ] plan_quiz(): difficulty_distribution 적용 (easy 30%, medium 50%, hard 20%)
    - [ ] 프롬프트 템플릿 6개 작성 (content_lecture.md ~ content_quiz.md)
    - [ ] 프롬프트에 기존 RAG 컨텍스트 포맷 재사용 (format_context 호환)
    - [ ] 옵션 기본값 적용 로직: content_studio.yaml → ContentOptions 오버라이드
    - [ ] edition_filter 옵션: 특정 개정판 제한 시 rag_query에 필터 적용
    - [ ] 테스트: 6개 유형별 mock LLM 아웃라인 생성 + 슬라이드 수 계산 + 옵션 적용 + 파싱 실패 재시도

- [x] **PR-044** ContentGenerator — 아웃라인→본문 생성
  - `scripts/lib/content_studio/generator.py`: ContentGenerator 서비스
    - generate_lecture_content(plan: LecturePlan, search_svc, gen_svc) → LectureContent
      - 슬라이드별 RAG 검색 (rag_query + edition_filter)
      - slide_list JSON 생성 (기존 GenerationService 활용)
      - EvidenceFilter 검증
      - 발표자 노트 생성 (상세 설명 + quote_id 출처)
    - generate_card_news_content(plan: CardNewsPlan, search_svc, gen_svc) → CardNewsContent
      - 카드별 RAG 검색 → card_list JSON
    - generate_workshop_content(plan: WorkshopPlan, search_svc, gen_svc) → WorkshopContent
      - 단계별 RAG 검색 → 시나리오 텍스트 + 퀴즈
    - generate_audio_content(plan: AudioPlan, search_svc, gen_svc) → AudioContent
      - 섹션별 RAG 검색 → 스크립트 텍스트
    - 공통: 기존 SearchService.hybrid_search() + GenerationService.generate() 래핑
    - 근거 검증: EvidenceFilter.check() 통합
    - 시간축 충돌: TemporalGuardrail 경고 포함
  - 테스트: mock SearchService/GenerationService로 콘텐츠 생성, 근거 검증
  - 예상: ~30 tests
  - **세부 과제:**
    - [ ] ContentGenerator 클래스 (SearchService, GenerationService, EvidenceFilter, TemporalGuardrail DI)
    - [ ] LectureContent frozen dataclass 정의 (slides: tuple[SlideContent], citations, warnings)
    - [ ] SlideContent frozen dataclass (title, body_text, key_points, quote_ids, speaker_notes)
    - [ ] generate_lecture_content(): 슬라이드별 순차 RAG 검색 → 본문 생성 → 검증
    - [ ] 슬라이드별 발표자 노트: 본문 3~5줄 + "출처: quote_id_xxx (10차, p.123)" 형식
    - [ ] CardNewsContent frozen dataclass 정의 (cards: tuple[CardContent], citations)
    - [ ] generate_card_news_content(): 카드별 RAG → body 텍스트 + quote_id 매핑
    - [ ] WorkshopContent frozen dataclass (phases: tuple[PhaseContent], quiz_questions)
    - [ ] generate_workshop_content(): 단계별 RAG → 시나리오 텍스트 + 선택적 퀴즈 생성
    - [ ] AudioContent frozen dataclass (sections: tuple[SectionContent], total_word_count)
    - [ ] generate_audio_content(): 섹션별 RAG → 대본 텍스트 (WPM 기반 시간 추정)
    - [ ] 공통: EvidenceFilter.check() → 커버리지 < min_coverage 시 warning 추가
    - [ ] 공통: TemporalGuardrail.check() → TC-001~004 경고를 metadata에 포함
    - [ ] 배치 최적화: 동일 edition_filter 슬라이드들은 RAG 검색 1회로 합치기
    - [ ] 테스트: mock 서비스로 4개 유형 콘텐츠 생성, 근거 검증 경고, 시간축 충돌 경고

- [x] **PR-045** AssetGenerator — 이미지/차트/오디오 생성
  - `scripts/lib/content_studio/asset_generator.py`: AssetGenerator 서비스
    - generate_assets(plan, content) → list[GeneratedAsset]
      - plan의 asset_type/asset_prompt를 읽고 적절한 어댑터 호출
      - 이미지: NanoBananaAdapter.generate_image()
      - 차트: AntVChartAdapter.generate_chart()
      - 오디오: ElevenLabsAdapter.text_to_speech()
    - 강의자료 에셋:
      - 표지 이미지: 나노바나나2 (제목 텍스트 + 기업 이미지, 16:9)
      - 삽화: 나노바나나2 (개념 시각화, 슬라이드별)
      - 차트: AntV (타임라인, 비교표, 마인드맵)
    - 카드뉴스 에셋:
      - 각 카드: 나노바나나2 (한국어 텍스트 포함, 1:1, 4K)
    - 워크숍 에셋:
      - 활동 시트: 나노바나나2 (양식 이미지)
      - 결과 차트: AntV (그룹워크 집계)
    - 에셋 캐싱: 동일 프롬프트 → 기존 파일 재사용 (content_hash 기반)
    - Graceful fallback: 각 어댑터 실패 시 에셋 없이 진행
  - 테스트: mock 어댑터로 에셋 생성, 캐싱, fallback 검증
  - 예상: ~25 tests
  - **세부 과제:**
    - [ ] AssetGenerator 클래스 (ImageGenerator, ChartGenerator, AudioGenerator DI — 모두 Optional)
    - [ ] generate_assets(): plan에서 asset_type/asset_prompt 추출 → 어댑터 디스패치
    - [ ] 디스패치 매핑: {"image": ImageGenerator, "chart": ChartGenerator, "audio": AudioGenerator}
    - [ ] 어댑터 가용성 확인: adapter.is_available() → False면 스킵 + warning 로그
    - [ ] 에셋 캐싱: SHA256(prompt + width + height + style) → output/assets/ 에서 기존 파일 조회
    - [ ] 캐시 히트 시 기존 GeneratedAsset 반환 (API 호출 절약)
    - [ ] 강의자료: 표지(16:9) + 슬라이드별 삽화(16:9) + 차트 에셋 분리 생성
    - [ ] 카드뉴스: 카드별 1:1 이미지, text_overlay가 있으면 프롬프트에 포함
    - [ ] 워크숍: 활동 시트 이미지 + 결과 집계 차트
    - [ ] 병렬 생성: 독립적인 에셋들은 asyncio.gather()로 동시 생성 (API rate limit 주의)
    - [ ] Graceful fallback: 개별 에셋 실패해도 전체 파이프라인은 계속 (실패 목록 반환)
    - [ ] 테스트: mock 어댑터 → 정상 생성, 캐시 히트, 부분 실패 fallback, 전체 어댑터 미가용

- [x] **PR-046** FileAssembler — PPTX/PDF/HTML 조립
  - `scripts/lib/content_studio/assembler.py`: FileAssembler 서비스
    - assemble_lecture(content, assets) → GeneratedFile (PPTX)
      - python-pptx로 PPTX 생성
      - 슬라이드 레이아웃 5종:
        - title_only: 표지/섹션 구분
        - title_content: 제목 + 본문 (기본)
        - title_content_image: 제목 + 본문 + 우측 이미지
        - comparison: 좌/우 비교 (개정판 비교용)
        - section_header: 중간 챕터 구분
      - 16:9 비율, 기업 테마 (배경, 폰트, 색상)
      - 발표자 노트에 상세 설명 + quote_id 출처
      - 이미지/차트 자동 삽입 (위치/크기 계산)
      - 마지막 슬라이드: 전체 출처 목록
    - assemble_card_news(content, assets) → tuple[GeneratedFile] (PNG 세트)
      - 나노바나나2가 전체 카드 이미지를 생성한 경우 → 그대로 사용
      - 이미지 없는 경우 → HTML → PNG 변환 (fallback)
    - assemble_workshop(content, assets) → GeneratedFile (PDF)
      - Markdown → PDF 변환
      - 진행자 가이드 + 참가자 활동지 분리
      - 활동 시트 이미지 삽입
    - assemble_audio(content, assets) → GeneratedFile (MP3)
      - ElevenLabs 오디오 섹션 합성 → 단일 MP3
      - 오디오 없는 경우 → 스크립트 PDF (fallback)
    - assemble_visualization(content, assets) → GeneratedFile (SVG/PNG)
      - AntV 차트 그대로 사용
    - 파일 저장 규칙:
      - output/{content_type}/{topic}-{date}.{ext}
      - 에셋: output/assets/{type}-{timestamp}-{id}.{ext}
  - 의존성: python-pptx>=0.6.21
  - 테스트: PPTX 구조 검증 (슬라이드 수, 레이아웃, 노트), PDF 생성, 파일 경로
  - 예상: ~35 tests
  - **세부 과제:**
    - [ ] FileAssembler 클래스 (output_dir 설정, 기업 테마 config)
    - [ ] PPTX 기업 테마 정의: 색상 팔레트 (SK 블루 #0052A2, 서브컬러), 폰트 (맑은고딕/Pretendard)
    - [ ] 슬라이드 레이아웃 5종 구현:
      - [ ] title_only: 배경 이미지 + 중앙 제목/부제 + 날짜
      - [ ] title_content: 상단 제목 + 본문 텍스트 (bullet points)
      - [ ] title_content_image: 좌측 텍스트(60%) + 우측 이미지(40%) 분할
      - [ ] comparison: 좌/우 2컬럼 비교 (개정판 비교에 최적화)
      - [ ] section_header: 챕터 구분 슬라이드 (큰 제목 + 챕터 번호)
    - [ ] 이미지 삽입 로직: asset → slide 매핑 (index 기반), 크기 자동 조정 (max 가로 50%)
    - [ ] 발표자 노트: slide.notes_slide.notes_text_frame 에 텍스트 삽입
    - [ ] 마지막 슬라이드: 사용된 전체 quote_id + 개정판 출처 목록 자동 생성
    - [ ] 파일 경로 생성: output/lectures/{sanitized_topic}-{YYYY-MM-DD}.pptx
    - [ ] assemble_card_news(): 에셋 이미지 있으면 복사, 없으면 HTML→PNG fallback
    - [ ] assemble_workshop(): Markdown 텍스트 → PDF 변환 (markdown2pdf 또는 reportlab)
    - [ ] assemble_audio(): MP3 섹션들 합성 (pydub) 또는 스크립트 PDF fallback
    - [ ] assemble_visualization(): SVG/PNG 에셋 파일 복사 + 메타데이터
    - [ ] assemble_quiz(): 퀴즈 문항 → PDF (문제지 + 정답지 분리)
    - [ ] output 디렉토리 자동 생성 (lectures/, cardnews/, workshops/, audio/, visualizations/, quizzes/)
    - [ ] requirements.txt에 `python-pptx>=0.6.21` 추가
    - [ ] 테스트: PPTX 구조 검증 (슬라이드 수/레이아웃/노트), 이미지 삽입, 출처 슬라이드, 파일 경로 규칙

### Step 3: API + 통합 (PR-47 ~ PR-49)

- [x] **PR-047** Content Studio 오케스트레이터 + API
  - `scripts/lib/content_studio/__init__.py`: ContentStudio 메인 클래스
    - create(request: ContentRequest) → ContentResult
      - 1. plan = planner.plan_{type}(topic, options)
      - 2. content = generator.generate_{type}_content(plan, search_svc, gen_svc)
      - 3. assets = asset_generator.generate_assets(plan, content)
      - 4. files = assembler.assemble_{type}(content, assets)
      - 5. result = ContentResult(files, citations, metadata, plan)
    - from_config(yaml_path, search_svc, gen_svc) → ContentStudio (팩토리)
  - `server/routes/content.py`: FastAPI 엔드포인트
    - POST /api/content/generate: 콘텐츠 생성 (동기)
    - GET /api/content/types: 사용 가능한 콘텐츠 유형 + 옵션 스키마
    - POST /api/content/plan: 아웃라인만 생성 (미리보기용)
    - GET /api/content/status/{request_id}: 비동기 생성 시 진행 상태 조회
  - `server/app.py` 수정: ContentStudio 서비스 + 라우터 등록
  - 테스트: API 엔드포인트 테스트, 오케스트레이터 통합 테스트
  - 예상: ~25 tests
  - **세부 과제:**
    - [ ] ContentStudio.create(): 5단계 파이프라인 오케스트레이션 (plan → generate → assets → assemble → result)
    - [ ] content_type → plan_method 디스패치 매핑 (6개 유형)
    - [ ] content_type → generate_method 디스패치 매핑 (6개 유형)
    - [ ] content_type → assemble_method 디스패치 매핑 (6개 유형)
    - [ ] from_config() 팩토리: YAML → ContentStudio (SearchService, GenerationService 주입)
    - [ ] 단계별 진행 상태 추적: PipelineProgress frozen dataclass (stage, percent, message)
    - [ ] 생성 메타데이터: 소요시간, RAG 검색 횟수, 에셋 생성 수, LLM 호출 수
    - [ ] Pydantic 모델: ContentGenerateRequest, ContentGenerateResponse, ContentPlanResponse
    - [ ] POST /api/content/generate: ContentStudio.create() 호출 → 파일 경로 + 메타데이터 반환
    - [ ] GET /api/content/types: 6개 유형 + 각 유형의 옵션 JSON Schema 반환
    - [ ] POST /api/content/plan: planner만 호출 → 아웃라인 JSON 반환 (미리보기/편집용)
    - [ ] GET /api/content/status/{request_id}: 비동기 생성 진행 상태 (향후 비동기 전환 대비)
    - [ ] server/app.py 수정: AppState에 ContentStudio 추가 + lifespan에서 초기화
    - [ ] server/routes/content.py: closure-based DI 패턴 (기존 라우터와 일관성)
    - [ ] 에러 처리: LLM 실패, MCP 실패, 파일 I/O 실패 각각 적절한 HTTP 상태 코드
    - [ ] 테스트: 오케스트레이터 통합 (mock 전체), API 엔드포인트 4개, 에러 케이스

- [x] **PR-048** Publisher — Notion + Google Workspace 배포
  - `scripts/lib/content_studio/publisher.py`: Publisher 서비스
    - publish(result: ContentResult, destinations: list[str]) → list[PublishResult]
    - PublishResult(destination, url, success, error)
  - `scripts/lib/content_studio/adapters/notion.py`: Notion 어댑터
    - NotionAdapter(DocumentPublisher) 구현
    - 교육자료 DB에 페이지 생성 + 파일 첨부
  - `scripts/lib/content_studio/adapters/google_ws.py`: Google Workspace 어댑터
    - GoogleWorkspaceAdapter(DocumentPublisher) 구현
    - Google Drive 업로드 + Google Slides 변환
  - MCP 서버 설치: Notion MCP, Google Workspace MCP
  - Graceful fallback: 실패 시 로컬 파일만 유지
  - 테스트: mock MCP로 배포 흐름, fallback 검증
  - 예상: ~20 tests
  - **세부 과제:**
    - [ ] Publisher 클래스 (어댑터 레지스트리: dict[str, DocumentPublisher])
    - [ ] PublishResult frozen dataclass (destination, url, success, error, timestamp)
    - [ ] publish(): destinations 순회 → 각 어댑터 호출 → 결과 수집
    - [ ] "local" destination: 항상 성공 (output/ 디렉토리에 파일 이미 존재)
    - [ ] NotionAdapter: Notion API로 교육자료 DB에 페이지 생성 + PPTX/PDF 파일 첨부
    - [ ] NotionAdapter: 페이지 속성 매핑 (제목, 콘텐츠 유형, 생성일, 주제, 출처 수)
    - [ ] GoogleWorkspaceAdapter: Google Drive 폴더에 파일 업로드
    - [ ] GoogleWorkspaceAdapter: PPTX → Google Slides 자동 변환 옵션
    - [ ] 배포 결과 로깅: 성공/실패 + URL + 소요시간
    - [ ] Graceful fallback: 개별 destination 실패해도 나머지 계속 진행
    - [ ] 테스트: mock Notion API → 페이지 생성 성공/실패, mock Google Drive → 업로드 성공/실패

- [x] **PR-049** End-to-End 통합 테스트 + 문서화
  - 전체 파이프라인 E2E 테스트 (mock LLM + mock MCP):
    - 강의자료 30분 → PPTX (슬라이드 15장, 이미지 3장, 차트 1개)
    - 카드뉴스 5장 → PNG 5개 (1080x1080)
    - 워크숍 60분 → PDF (진행자 가이드 + 활동지)
    - 오디오 5분 → MP3 (2인 대화)
    - 개념 시각화 → SVG (마인드맵)
    - 학습 퀴즈 10문항 → PDF (문제지 + 정답지)
  - 성능 벤치마크: 콘텐츠 유형별 생성 시간 측정
  - MCP 서버 설치/설정 가이드 문서
  - README.md 업데이트 (Content Studio 섹션)
  - 예상: ~20 tests
  - **세부 과제:**
    - [ ] E2E 테스트 fixture: MockLLMClient + MockSearchService + MockAdapters 통합 setup
    - [ ] E2E 강의자료: topic → PPTX 파일 존재 + 슬라이드 수 검증 + 발표자 노트 존재
    - [ ] E2E 카드뉴스: topic → PNG 5개 존재 + 파일 크기 > 0
    - [ ] E2E 워크숍: topic → PDF 존재 + 4단계 구조 포함
    - [ ] E2E 오디오: topic → MP3 또는 스크립트 PDF 존재
    - [ ] E2E 시각화: topic → SVG/PNG 존재
    - [ ] E2E 퀴즈: topic → PDF 존재 + 문항 수 검증
    - [ ] 성능 벤치마크: 유형별 생성 시간 (target: 강의 <60s, 카드뉴스 <30s, 기타 <45s with mock)
    - [ ] MCP 서버 설치 가이드: `docs/content-studio-mcp-setup.md`
    - [ ] README.md 업데이트: Content Studio 개요, API 사용법, CLI 예시
    - [ ] .gitignore에 `output/` 디렉토리 추가 (생성 파일 제외)

### Step 4: 고도화 (PR-50 ~ PR-52)

- [x] **PR-050** 강의자료 고도화 — 템플릿 + 브랜딩
  - PPTX 마스터 템플릿 시스템:
    - 기본 기업 템플릿 (SK 블루/레드 계열)
    - 교육용 템플릿 (밝은 톤, 큰 폰트)
    - 세미나용 템플릿 (격식 있는 디자인)
  - 슬라이드 전환 효과 + 애니메이션 (python-pptx 지원 범위)
  - 슬라이드 레이아웃 자동 선택 (콘텐츠 양에 따라)
  - 목차 슬라이드 자동 생성
  - 테스트: 템플릿 적용 검증, 레이아웃 자동 선택
  - 예상: ~20 tests
  - **세부 과제:**
    - [ ] PPTX 마스터 템플릿 3종 .pptx 파일 생성 (config/templates/)
    - [ ] 템플릿 선택 로직: style 옵션 → 템플릿 매핑 (corporate/education/seminar)
    - [ ] 레이아웃 자동 선택: key_points 수 ≤3 → title_content, >3 → title_content_image, 비교 주제 → comparison
    - [ ] 목차 슬라이드: LecturePlan.slides에서 section_header 추출 → 목차 자동 생성 (2번째 슬라이드)
    - [ ] 슬라이드 번호 + 푸터 (회사명 / 날짜 / 페이지) 자동 삽입
    - [ ] 색상 팔레트 YAML: config/pptx_themes.yaml (3종 테마별 primary/secondary/accent/bg)
    - [ ] 테스트: 템플릿 3종 적용, 레이아웃 자동 선택 5개 케이스, 목차 슬라이드 생성

- [x] **PR-051** 카드뉴스 + 시각화 고도화
  - 카드뉴스 시리즈 테마:
    - "오늘의 SKMS" (일간 카드 1장)
    - "SKMS 깊이 읽기" (주간 시리즈 5장)
    - "개정판 비교" (2장 Before/After)
  - 시각화 고도화:
    - 개정판 타임라인 (12개 개정판 + 주요 변화)
    - 경영요소 관계 그래프 (정적/동적 요소 네트워크)
    - 개념 진화 산키 다이어그램 (renamed/removed 추적)
  - 나노바나나2 스타일 가이드: 기업 시각 톤앤매너 통일
  - 테스트: 시리즈 생성, 시각화 데이터 구조 검증
  - 예상: ~20 tests
  - **세부 과제:**
    - [ ] 카드뉴스 시리즈 모델: SeriesConfig frozen dataclass (series_name, card_count, schedule)
    - [ ] 3종 시리즈 프리셋: daily_skms (1장), deep_read (5장), edition_compare (2장)
    - [ ] 시리즈별 이미지 프롬프트 템플릿: 통일된 비주얼 톤 (색상, 레이아웃, 폰트 스타일)
    - [ ] 개정판 타임라인 데이터: concept_timeline.yaml → AntV timeline 입력 JSON 변환
    - [ ] 경영요소 관계 그래프: 정적 10개 + 동적 5개 요소 → 네트워크 그래프 데이터
    - [ ] 개념 진화 산키: renamed/removed 상태 추적 → sankey 다이어그램 데이터
    - [ ] 나노바나나2 스타일 가이드: config/nano_banana_style.yaml (색상 톤, 구도, 금지 요소)
    - [ ] 테스트: 시리즈 3종 생성, 타임라인/그래프/산키 데이터 구조 검증

- [x] **PR-052** React Content Studio UI
  - `frontend/src/pages/ContentStudio.tsx`: 메인 페이지
    - 콘텐츠 유형 선택 (6종 카드 UI)
    - 주제 입력 + 옵션 설정
    - 아웃라인 미리보기 + 편집
    - 생성 진행 상태 표시
    - 결과 미리보기 + 다운로드
  - `frontend/src/components/content/`:
    - ContentTypeSelector: 유형 선택 카드 그리드
    - OutlineEditor: 아웃라인 편집 (드래그&드롭 순서 변경)
    - SlidePreview: PPTX 미리보기 (썸네일)
    - CardNewsPreview: 카드뉴스 이미지 캐러셀
    - GenerationProgress: 단계별 진행 상태 바
  - API 연동: /api/content/plan → 미리보기 → /api/content/generate
  - 상태 관리: React Query (서버 상태) + Zustand (UI 상태)
  - 반응형 디자인: 데스크톱 우선 (HR담당자 환경)
  - **세부 과제:**
    - [ ] ContentStudio.tsx 페이지 레이아웃 (3단계 위저드: 유형 선택 → 옵션 설정 → 생성)
    - [ ] ContentTypeSelector: 6종 카드 (아이콘 + 제목 + 설명 + 예상 시간)
    - [ ] OptionForm: content_type별 동적 폼 (duration, num_items, edition_filter, style 등)
    - [ ] OutlineEditor: /api/content/plan 호출 → JSON 렌더링 → 드래그&드롭 순서 변경
    - [ ] GenerationProgress: WebSocket 또는 polling으로 5단계 진행 상태 바
    - [ ] ResultViewer: 파일 미리보기 (PPTX 썸네일, PNG 캐러셀, PDF 뷰어) + 다운로드 버튼
    - [ ] React Query: useContentTypes(), useContentPlan(topic, type), useContentGenerate()
    - [ ] Zustand store: selectedType, options, plan, generationStatus
    - [ ] 에러 핸들링: 생성 실패 시 에러 메시지 + 재시도 버튼
    - [ ] 반응형: 1280px+ 2컬럼 (옵션 좌측 / 미리보기 우측), 768px~ 단일 컬럼

### MCP 서버 설치 체크리스트

- [ ] **나노바나나2** (P0 — 이미지 생성)
  - 설치: `npm install nano-banana-mcp` 또는 Gemini API 직접 사용
  - 설정: GEMINI_API_KEY 환경변수
  - MCP config: `{"mcpServers": {"nano-banana": {"command": "npx", "args": ["nano-banana-mcp"], "env": {"GEMINI_API_KEY": "..."}}}}`
  - 테스트: `generate_image("test prompt", 512, 512, "professional")`

- [ ] **AntV Chart** (P0 — 차트/그래프)
  - 설치: `npm install @anthropic/mcp-server-chart` 또는 별도 설정
  - GitHub: antvis/mcp-server-chart (3,700+ stars)
  - 지원 차트: timeline, mindmap, comparison, wordcloud, radar, sankey, flowchart
  - 테스트: 타임라인 차트 1개 생성

- [ ] **ElevenLabs** (P1 — 오디오)
  - 설치: `npm install @anthropic/elevenlabs-mcp` 또는 공식 SDK
  - GitHub: elevenlabs/elevenlabs-mcp (1,200+ stars)
  - 설정: ELEVENLABS_API_KEY 환경변수
  - 무료 tier: 10K credits/month
  - 테스트: 한국어 TTS 30초 생성

- [ ] **markdown2pdf** (P1 — PDF)
  - 설치: `npm install markdown2pdf-mcp`
  - GitHub: 2b3pro/markdown2pdf-mcp
  - 테스트: Markdown → PDF 변환

- [ ] **Notion** (P2 — 배포)
  - 설치: `npm install @modelcontextprotocol/server-notion`
  - GitHub: makenotion/notion-mcp-server (3,900+ stars)
  - 설정: NOTION_API_KEY + database_id
  - 테스트: 테스트 페이지 생성

- [ ] **Google Workspace** (P2 — 배포)
  - 설치: `npm install google-workspace-mcp`
  - GitHub: taylorwilsdon/google_workspace_mcp (1,600+ stars)
  - 설정: OAuth 2.1 인증
  - 테스트: Google Drive 파일 업로드

### 의존성 추가 (requirements.txt)

```
python-pptx>=0.6.21          # PPTX 생성
google-generativeai>=0.8     # 나노바나나2 API (직접 호출 fallback)
```

### 예상 테스트 수

| PR | 테스트 | 누적 |
|----|--------|------|
| PR-040 모델+설정 | ~30 | 1246 |
| PR-041 나노바나나2 | ~25 | 1271 |
| PR-042 AntV+ElevenLabs | ~30 | 1301 |
| PR-043 Planner | ~35 | 1336 |
| PR-044 Generator | ~30 | 1366 |
| PR-045 AssetGenerator | ~25 | 1391 |
| PR-046 FileAssembler | ~35 | 1426 |
| PR-047 오케스트레이터+API | 38 | 1573 |
| PR-047+ Cross-Cutting | 9 | 1583 |
| PR-048 Publisher | 26 | 1609 |
| PR-049 E2E 통합 | 17 | 1626 |
| PR-050 강의자료 고도화 | 18 | 1644 |
| PR-051 카드뉴스+시각화 | 21+26 | 1691 |
| PR-051+ (agent extra) | 11 | 1702 |
| PR-052 React UI | 0 (frontend) | 1702 |

---

## Cross-Cutting Concerns (Phase 4 공통)

> Phase 4 전체에 걸쳐 적용해야 할 횡단 관심사

### 비동기 처리 전략
- [x] 콘텐츠 생성은 LLM + MCP 호출로 수십 초 소요 → 비동기 처리 구현
  - [x] Phase 4 Step 1~2: 동기 처리 (단순한 구현 우선)
  - [x] Phase 4 Step 3: BackgroundTasks 기반 비동기 전환 (`POST /api/content/generate/async`)
  - [x] request_id 발급 → `GET /api/content/status/{request_id}` 폴링
  - [ ] 향후: WebSocket 기반 실시간 진행 상태 push (PR-052 React UI와 연동)

### 에러 처리 + 로깅
- [x] Content Studio 전용 예외 클래스 계층:
  - [x] `ContentStudioError` (기본)
  - [x] `PlanningError` (LLM 아웃라인 생성 실패)
  - [x] `GenerationError` (RAG 검색/콘텐츠 생성 실패)
  - [x] `AssetError` (MCP 어댑터 호출 실패)
  - [x] `AssemblyError` (파일 조립 실패)
  - [x] `PublishError` (배포 실패)
- [x] 단계별 로깅: 각 파이프라인 단계 시작/완료/실패 + 소요시간
- [x] MetricsCollector 확장: content_studio 관련 메트릭 수집 (생성 횟수, 유형별 분포, 실패율)

### 캐싱 전략
- [x] LLM 아웃라인 캐싱: 동일 topic + options → 캐시된 plan 반환 (TTL 24h)
- [ ] RAG 검색 캐싱: 기존 QueryCache 재사용 (동일 rag_query → 캐시)
- [ ] 에셋 캐싱: content_hash 기반 (PR-045에서 구현)
- [ ] 최종 파일 캐싱은 하지 않음 (항상 새로 생성 — 사용자가 편집할 수 있으므로)

### 보안
- [x] ContentRequest 입력 검증: topic 길이 제한 (max 200자), 특수문자 살균
- [x] 파일 경로 검증: path traversal 방지 (../ 차단)
- [ ] MCP API 키 관리: 환경변수 전용 (코드에 하드코딩 금지)
- [ ] 생성된 파일 접근 제어: output/ 디렉토리 권한 설정

### output 디렉토리 관리
- [x] .gitignore에 `output/` 추가
- [x] output 디렉토리 자동 정리: 30일 이상 된 파일 삭제 스크립트 (`scripts/cleanup_output.py`)
- [x] 디스크 용량 모니터링: output/ 총 크기 > 1GB 시 경고

---

## Technical Debt / Backlog

> Phase 0~3에서 누적된 기술 부채 + Phase 4 진행 중 발견될 수 있는 항목

### 코드 품질
- [ ] **TD-001** scripts/lib/ → src/ 디렉토리 통합 검토
  - 현재: 핵심 서비스가 `scripts/lib/`에, API가 `server/`에 분리
  - 개선안: `src/` 통합 또는 `scripts/lib/` → Python 패키지화
  - 우선순위: LOW (Phase 4 완료 후)
- [ ] **TD-002** 타입 힌트 강화
  - 일부 dict 반환 함수에 TypedDict 또는 frozen dataclass 적용
  - 특히 config 로딩 함수들 (현재 dict 반환)
- [ ] **TD-003** async/await 전면 도입 검토
  - 현재: SearchService, GenerationService 동기 호출
  - Content Studio: MCP 어댑터는 async (불일치)
  - 검토: asyncio.to_thread()로 래핑 vs 전면 async 전환

### 테스트
- [x] **TD-004** 테스트 fixture 중복 해소
  - `tests/conftest.py` + `tests/test_content_studio/conftest.py` 통합 완료
  - 3개 테스트 파일에서 ~262줄 중복 코드 제거
- [ ] **TD-005** E2E 테스트 실행 환경 격리
  - 현재: 테스트에서 실제 DB/파일 생성 가능 (tmp 디렉토리 사용하나 불완전)
  - 개선: pytest-tmp-files 또는 Docker 기반 격리
- [ ] **TD-006** 커버리지 93% → 95% 목표
  - 현재: 1216 tests, 93.33%
  - 미커버 영역: 일부 에러 핸들링 분기, edge case

### 인프라
- [x] **TD-007** CI/CD 파이프라인 Phase 4 확장
  - `.github/workflows/ci.yml`: Python tests + coverage + frontend build
  - `.github/workflows/content-studio-tests.yml`: Content Studio 경로 필터 워크플로우
- [ ] **TD-008** Docker 이미지 Phase 4 업데이트
  - python-pptx, google-generativeai 의존성 추가
  - output/ 볼륨 마운트 설정
- [ ] **TD-009** 모니터링 확장
  - Content Studio 메트릭: 생성 요청 수, 유형별 분포, 평균 생성 시간, 실패율
  - MCP 어댑터 헬스체크: /api/health에 MCP 서버 상태 포함

---

## Phase 5: 향후 로드맵 (Phase 4 완료 후)

> Phase 4 Content Studio 완료 후 검토할 확장 기능

### 5.1 사용자 경험 개선
- [ ] **아웃라인 편집**: 생성된 plan을 사용자가 수정 → 수정된 plan으로 콘텐츠 재생성
- [ ] **부분 재생성**: 특정 슬라이드/카드만 재생성 (전체 재생성 비용 절감)
- [ ] **이력 관리**: 생성된 콘텐츠 버전 관리 (이전 버전 비교/복원)
- [ ] **즐겨찾기 주제**: 자주 사용하는 주제/옵션 프리셋 저장

### 5.2 콘텐츠 확장
- [ ] **동영상 생성**: 슬라이드 + 오디오 → MP4 영상 (ffmpeg 기반)
- [ ] **인터랙티브 콘텐츠**: H5P 또는 SCORM 패키지 생성 (LMS 연동)
- [ ] **다국어 지원**: 한국어 → 영어/중국어 자동 번역 (해외 법인용)
- [ ] **맞춤형 퀴즈**: 적응형 문항 (이전 답변 기반 난이도 조정)

### 5.3 플랫폼 연동
- [ ] **LMS 직접 배포**: mySUNI / SK University LMS API 연동
- [ ] **Slack/Teams 알림**: 콘텐츠 생성 완료 시 채널 알림
- [ ] **스케줄링**: 정기 콘텐츠 생성 (매주 카드뉴스 자동 발행)
- [ ] **분석 대시보드**: 생성된 콘텐츠 사용 통계 (조회수, 다운로드, 피드백)

### 5.4 RAG 파이프라인 고도화
- [ ] **SKMS 15차 대응**: 차기 개정판 발행 시 자동 반영 파이프라인
- [ ] **외부 자료 연동**: SKMS 이외 SK그룹 자료 (ESG 보고서, 연간보고서) RAG 통합
- [ ] **사용자 피드백 루프**: 생성 품질에 대한 사용자 평가 → 프롬프트/파이프라인 자동 개선
