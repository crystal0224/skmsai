# S02: 성능 목표 수치 (SLO)

> SKMS Time-Aware RAG Pipeline 성능 목표 및 벤치마크 결과

## 1. SLO 정의

### API 엔드포인트 응답 시간

| 엔드포인트 | P50 | P95 | P99 | 비고 |
|-----------|-----|-----|-----|------|
| GET /api/health | < 5ms | < 10ms | < 50ms | 헬스체크 (30초 주기) |
| POST /api/search | < 200ms | < 500ms | < 1,000ms | 검색만 (LLM 미포함) |
| POST /api/generate | < 3,000ms | < 5,000ms | < 8,000ms | LLM 생성 포함 |
| GET /api/toc/* | < 50ms | < 100ms | < 200ms | 목차 조회 |
| GET /api/dashboard/* | < 100ms | < 200ms | < 500ms | 대시보드 메트릭 |
| GET /api/quality/* | < 200ms | < 500ms | < 1,000ms | 품질 보고서 |

### 가용성

| 항목 | 목표 | 측정 방법 |
|------|------|-----------|
| 가용성 (Availability) | 99.5% | 월간 업타임 / 총 시간 |
| 에러율 (Error Rate) | < 1% | 5xx 응답 / 총 요청 |
| 헬스체크 성공률 | 99.9% | 연속 실패 3회 시 알림 |

## 2. 내부 컴포넌트 성능 벤치마크

### 검색 (tests/test_perf_benchmark.py 기준)

| 컴포넌트 | 데이터 규모 | SLO (P95) | 벤치마크 결과 | 상태 |
|----------|-----------|-----------|-------------|------|
| BM25 검색 | 500 quotes | < 50ms | PASS | OK |
| BM25 + 필터 | 500 quotes | < 50ms | PASS | OK |
| RRF Fusion | 20+20 hits | < 5ms | PASS | OK |
| RRF Fusion (대규모) | 100+100 hits | < 10ms | PASS | OK |

### 캐시 (QueryCache)

| 연산 | SLO (P95) | 벤치마크 결과 | 상태 |
|------|-----------|-------------|------|
| Cache Put | < 1ms | PASS | OK |
| Cache Hit | < 0.5ms | PASS | OK |
| Cache Miss | < 0.5ms | PASS | OK |
| Cache Key 생성 | < 0.5ms | PASS | OK |
| Cache Speedup | > 2x vs BM25 | PASS | OK |

### DB 연산 (SQLite)

| 연산 | 데이터 규모 | SLO (P95) | 벤치마크 결과 | 상태 |
|------|-----------|-----------|-------------|------|
| COUNT(*) | 500 rows | < 5ms | PASS | OK |
| find_by_edition() | 500 rows | < 10ms | PASS | OK |
| find_all() | 500 rows | < 50ms | PASS | OK |
| bulk_upsert() | 500 rows | < 200ms | PASS | OK |

### 메트릭 수집

| 연산 | 데이터 규모 | SLO (P95) | 벤치마크 결과 | 상태 |
|------|-----------|-----------|-------------|------|
| record() | 단건 | < 0.1ms | PASS | OK |
| get_metrics() | 5,000 records | < 50ms | PASS | OK |

## 3. LLM 응답 시간 (외부 의존)

| 모델 | 용도 | 예상 P50 | 예상 P95 | 비고 |
|------|------|---------|---------|------|
| Sonnet (라우팅) | 쿼리 분류 | 500ms | 1,500ms | 출력 ~100 tokens |
| Sonnet (생성) | 답변 | 2,000ms | 4,000ms | 출력 ~1,000 tokens |
| text-embedding-3-large | 임베딩 | 100ms | 300ms | 단건 |

> LLM 응답 시간은 네트워크 상태와 API 부하에 따라 가변적.
> Anthropic API의 rate limit (RPM)을 고려한 부하 분산 필요.

## 4. 처리량 (Throughput)

| 항목 | 목표 | 제약 요인 |
|------|------|-----------|
| 동시 요청 | 10 req/s | uvicorn 워커 2개 |
| 일 최대 처리량 | 50,000 req/day | API rate limit |
| Rate Limit | 60 req/min (per client) | Token Bucket |
| Burst | 10 req (per client) | 버킷 크기 |

## 5. 성능 모니터링

### 수집 메트릭
- 엔드포인트별 지연 시간 (P50/P95/P99/mean/min/max)
- 요청 성공률 / 에러율
- 시간대별 요청 수 (hourly)
- 상태 코드 분포

### 대시보드 API
- `GET /api/dashboard/metrics?window=3600` — 실시간 메트릭
- `GET /api/dashboard/stats?window=86400` — 사용 통계

### 알림 기준
- P95 응답 시간 > SLO의 150% → Warning
- P95 응답 시간 > SLO의 200% → Critical
- 에러율 > 5% (5분 윈도우) → Critical
- 헬스체크 연속 실패 3회 → Critical
