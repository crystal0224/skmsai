# SKMS Time-Aware RAG Pipeline — TODO

> 마지막 업데이트: 2026-02-26
> 전체 39 PR | 완료 27 | 남은 12

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
- [ ] **PR-028** TOC Visualization — 인터랙티브 목차 트리 뷰어
- [ ] **PR-029** LLM-as-Judge — 4축 자동 평가기
- [ ] **PR-030** Golden QA 50 + V1 Quality Report

---

## Phase 3: V2 Production (PR-31 ~ PR-39)

- [ ] **PR-031** Pinecone 마이그레이션 (Chroma → Pinecone)
- [ ] **PR-032** Quiz + Slide 렌더러 추가
- [ ] **PR-033** 프롬프트 최종 튜닝 + 전체 Output 통합 테스트
- [ ] **PR-034** Next.js V2 프로덕션 UI
- [ ] **PR-035** 운영 대시보드 (모니터링 + 사용 통계)
- [ ] **PR-036** 데이터 자동 업데이트 배치 + 인덱스 갱신
- [ ] **PR-037** 성능 최적화 + 부하 테스트
- [ ] **PR-038** 보안 검토 + 프로덕션 배포
- [ ] **PR-039** Golden QA 100 + 최종 품질 대시보드

---

## Gap Checklist (SHOULD 미충족 — 향후 보완)

- [ ] **S01** Phase별 비용 추정
- [ ] **S02** 성능 목표 수치 (P50/P95/P99)
- [ ] **S03** CI/CD 파이프라인 명세
- [ ] **S04** 모니터링/알림 전략 (SLO/SLI)
- [ ] **S07** 테스트 전략 문서
