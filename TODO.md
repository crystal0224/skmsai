# SKMS Time-Aware RAG Pipeline — TODO

> 마지막 업데이트: 2026-02-27
> Phase 0~3 완료 (39 PR) | Phase 4 Content Studio 진행 중

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

- [ ] **PR-040** Content Studio 데이터 모델 + 설정
  - `scripts/lib/content_studio/models.py`: 전체 데이터 모델 (frozen dataclass)
    - ContentRequest, ContentOptions, ContentResult, GeneratedFile, GeneratedAsset
    - LecturePlan, SlidePlan (index, title, layout, key_points, rag_query, asset_type, asset_prompt, speaker_notes)
    - CardNewsPlan, CardPlan (headline, body, source_quote, image_prompt, text_overlay)
    - WorkshopPlan, WorkshopPhase (phase_type, facilitator_guide, materials_needed)
    - AudioPlan, ScriptSection (speaker, text)
  - `scripts/lib/content_studio/__init__.py`: ContentStudio 오케스트레이터 클래스
  - `config/content_studio.yaml`: 전체 설정 (MCP 서버, 콘텐츠 유형별 옵션)
  - 테스트: 모델 직렬화/역직렬화, 불변성, YAML 로드, 기본값 검증
  - 예상: ~30 tests

- [ ] **PR-041** MCP 어댑터 기반 + 나노바나나2 어댑터
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

- [ ] **PR-042** AntV Chart 어댑터 + ElevenLabs 어댑터
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

### Step 2: 핵심 파이프라인 (PR-43 ~ PR-46)

- [ ] **PR-043** ContentPlanner — 주제→아웃라인 생성
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
  - 테스트: 유형별 아웃라인 생성 (mock LLM), 슬라이드 수 산출, 옵션 적용
  - 예상: ~35 tests

- [ ] **PR-044** ContentGenerator — 아웃라인→본문 생성
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

- [ ] **PR-045** AssetGenerator — 이미지/차트/오디오 생성
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

- [ ] **PR-046** FileAssembler — PPTX/PDF/HTML 조립
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

### Step 3: API + 통합 (PR-47 ~ PR-49)

- [ ] **PR-047** Content Studio 오케스트레이터 + API
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
  - `server/app.py` 수정: ContentStudio 서비스 + 라우터 등록
  - 테스트: API 엔드포인트 테스트, 오케스트레이터 통합 테스트
  - 예상: ~25 tests

- [ ] **PR-048** Publisher — Notion + Google Workspace 배포
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

- [ ] **PR-049** End-to-End 통합 테스트 + 문서화
  - 전체 파이프라인 E2E 테스트 (mock LLM + mock MCP):
    - 강의자료 30분 → PPTX (슬라이드 15장, 이미지 3장, 차트 1개)
    - 카드뉴스 5장 → PNG 5개 (1080x1080)
    - 워크숍 60분 → PDF (진행자 가이드 + 활동지)
    - 오디오 5분 → MP3 (2인 대화)
    - 개념 시각화 → SVG (마인드맵)
  - 성능 벤치마크: 콘텐츠 유형별 생성 시간 측정
  - MCP 서버 설치/설정 가이드 문서
  - README.md 업데이트 (Content Studio 섹션)
  - 예상: ~20 tests

### Step 4: 고도화 (PR-50 ~ PR-52)

- [ ] **PR-050** 강의자료 고도화 — 템플릿 + 브랜딩
  - PPTX 마스터 템플릿 시스템:
    - 기본 기업 템플릿 (SK 블루/레드 계열)
    - 교육용 템플릿 (밝은 톤, 큰 폰트)
    - 세미나용 템플릿 (격식 있는 디자인)
  - 슬라이드 전환 효과 + 애니메이션 (python-pptx 지원 범위)
  - 슬라이드 레이아웃 자동 선택 (콘텐츠 양에 따라)
  - 목차 슬라이드 자동 생성
  - 테스트: 템플릿 적용 검증, 레이아웃 자동 선택
  - 예상: ~20 tests

- [ ] **PR-051** 카드뉴스 + 시각화 고도화
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

- [ ] **PR-052** React Content Studio UI (향후 과제)
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
| PR-047 오케스트레이터+API | ~25 | 1451 |
| PR-048 Publisher | ~20 | 1471 |
| PR-049 E2E 통합 | ~20 | 1491 |
| PR-050 강의자료 고도화 | ~20 | 1511 |
| PR-051 카드뉴스+시각화 | ~20 | 1531 |
| PR-052 React UI | (향후) | - |
