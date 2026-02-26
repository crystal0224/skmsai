# S07: 테스트 전략 문서

> SKMS Time-Aware RAG Pipeline 테스트 전략 및 커버리지 정책

## 1. 테스트 현황

| 항목 | 수치 |
|------|------|
| 테스트 파일 | 42개 |
| 테스트 함수 | 1,185개 |
| 테스트 코드 | 19,106줄 |
| 프로덕션 코드 | ~8,000줄 |
| 테스트:프로덕션 비율 | ~2.4:1 |

## 2. 테스트 피라미드

```
         /  E2E  \          ← 5% (API 통합, 보안 통합)
        / Integration \      ← 25% (서비스 간 연동)
       /    Unit Tests  \    ← 60% (개별 함수/클래스)
      / Performance/Quality \ ← 10% (벤치마크, 품질 평가)
```

## 3. 테스트 유형별 분류

### 3.1 단위 테스트 (Unit)

| 영역 | 테스트 파일 | 테스트 수 | 주요 검증 |
|------|-----------|-----------|-----------|
| 데이터 모델 | test_quote.py | 25 | QuoteObject 불변성, 검증 |
| DB CRUD | test_quote_repository.py | 24 | 삽입/조회/업데이트/삭제 |
| 검색 | test_search_service.py | 43 | vector/bm25/hybrid/RRF |
| 캐시 | test_query_cache.py | 31 | LRU, TTL, 스레드 안전 |
| 보안 | test_security.py | 50 | Rate Limiter, 입력 살균 |
| 분류 | test_query_classifier.py | 50 | 쿼리 유형 분류 |
| 동의어 | test_synonym_map.py | 41 | 동의어 확장 |
| 타임라인 | test_concept_timeline.py | 39 | 개념 시간축 추적 |
| 렌더링 | test_output_renderer.py | 42 | 출력 포맷팅 |
| 메트릭 | test_metrics_collector.py | 29 | 메트릭 수집/통계 |
| 리랭커 | test_reranker.py | 25 | Cohere/CE 리랭킹 |
| 트레이싱 | test_tracing.py | 16 | 관측성 추적 |

### 3.2 통합 테스트 (Integration)

| 영역 | 테스트 파일 | 테스트 수 | 주요 검증 |
|------|-----------|-----------|-----------|
| 서버 API | test_server.py | 22 | 엔드포인트 응답 |
| API V2 | test_api_v2.py | 20 | V2 검색/생성 |
| TOC API | test_toc_api.py | 35 | 목차 조회/검색 |
| 대시보드 | test_dashboard_api.py | 18 | 메트릭/통계 API |
| 품질 대시보드 | test_quality_dashboard.py | 58 | 품질 보고서 API |
| 인제스트 | test_ingest.py | 32 | 데이터 적재 파이프라인 |
| 배치 | test_batch_update.py | 25 | 배치 업데이트 |

### 3.3 E2E / 보안 통합

| 영역 | 테스트 파일 | 테스트 수 | 주요 검증 |
|------|-----------|-----------|-----------|
| 보안 통합 | test_security.py | 3 | 에러 누출 방지, 검증 에러 |
| 배포 파일 | test_security.py | 4 | Dockerfile, docker-compose |

### 3.4 성능 벤치마크

| 영역 | 테스트 파일 | 테스트 수 | 주요 검증 |
|------|-----------|-----------|-----------|
| 벤치마크 | test_perf_benchmark.py | 15 | SLO 준수 (P95 기준) |

### 3.5 품질 평가

| 영역 | 테스트 파일 | 테스트 수 | 주요 검증 |
|------|-----------|-----------|-----------|
| LLM Judge | test_llm_judge.py | 53 | 4축 평가, 파싱, 임계값 |
| Quality Gate | test_quality_gate.py | 26 | Go/No-Go 판정 |
| Quality Report | test_quality_report.py | 39 | V1 보고서, Golden QA |
| Quality Dashboard | test_quality_dashboard.py | 58 | V2 보고서, 커버리지 |

## 4. 테스트 원칙

### 4.1 불변 데이터 모델
- 모든 도메인 모델은 `@dataclass(frozen=True)` 사용
- 각 모델에 `test_immutable` 테스트 필수 (AttributeError 검증)

### 4.2 격리 (Isolation)
- SQLite 테스트: `tmp_path` 활용, 파일 시스템 격리
- ChromaDB 테스트: `EphemeralClient` 사용, 메모리 내 격리
- API 테스트: `TestClient` + mock AppState
- 환경변수: `monkeypatch.setenv/delenv`

### 4.3 결정론적 (Deterministic)
- LLM 호출 없음: 모든 테스트에서 mock/fake 사용
- 시간 의존 테스트: `time.sleep` 최소화 (0.15s 이하)
- 랜덤 의존 없음: 고정 시드 또는 결정적 해시

### 4.4 빠른 실행
- 전체 테스트 스위트: < 10초 (1,185 테스트)
- 개별 테스트: < 100ms (성능 벤치마크 제외)
- CI 통과 시간 목표: < 60초

## 5. 커버리지 정책

### 목표 커버리지: 80%+

| 모듈 | 예상 커버리지 | 근거 |
|------|-------------|------|
| scripts/lib/ | > 90% | 핵심 비즈니스 로직, 모든 public 함수 테스트 |
| server/routes/ | > 85% | 모든 엔드포인트 + 에러 케이스 |
| server/models.py | > 95% | Pydantic 모델 검증 |
| config/ | N/A | YAML 설정 파일, 테스트 불요 |

### 커버리지 도구
```bash
# 커버리지 측정 (향후 CI 통합)
python -m pytest tests/ --cov=scripts/lib --cov=server --cov-report=term-missing
```

## 6. 테스트 실행 가이드

### 전체 실행
```bash
python -m pytest tests/ -v --tb=short
```

### 카테고리별 실행
```bash
# 보안 테스트만
python -m pytest tests/test_security.py -v

# 성능 벤치마크만
python -m pytest tests/test_perf_benchmark.py -v

# API 통합 테스트만
python -m pytest tests/test_server.py tests/test_api_v2.py tests/test_toc_api.py -v

# 품질 관련 테스트만
python -m pytest tests/test_quality_*.py tests/test_llm_judge.py -v
```

### 새 PR 테스트 체크리스트
1. [ ] 새 기능에 대한 테스트 작성 (TDD 권장)
2. [ ] 기존 테스트 전체 통과 확인
3. [ ] 테스트 수 미감소 확인 (현재 기준: 1,185)
4. [ ] 불변성 테스트 포함 (frozen dataclass 사용 시)
5. [ ] 에러 케이스 테스트 포함

## 7. Golden QA 평가 체계

### 문항 구성
| 항목 | V1 | V2 | 합계 |
|------|----|----|------|
| 문항 수 | 50 | 50 | 100 |
| 질의 유형 | 4종 | 4종 | 4종 |
| 난이도 | 3단계 | 3단계 | 3단계 |
| 회귀 검사 | 4건 | 3건 | 7건 |
| 개정판 커버리지 | 7/7 | 7/7 | 7/7 (100%) |

### 평가 축 (4축)
1. **relevance** (관련성): 질의에 대한 답변의 관련도 — 기준 3.5
2. **faithfulness** (충실성): 검색 컨텍스트에 대한 충실도 — 기준 4.0
3. **quote_accuracy** (인용 정확도): 원문 인용의 정확성 — 기준 3.5
4. **temporal_correctness** (시간축 정확도): 개정판 맥락 처리 — 기준 3.5

### 품질 게이트 기준
- 통과율 임계값: **80%**
- 종합 등급: A(90+) / B(80+) / C(70+) / D(60+) / F
