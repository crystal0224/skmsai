# S04: 모니터링/알림 전략

> SKMS Time-Aware RAG Pipeline SLO/SLI 모니터링 및 알림 설계

## 1. 모니터링 아키텍처

```
[FastAPI App] → [MetricsCollector] → [Dashboard API] → [대시보드 UI]
      ↓                                      ↓
[Health Check] ← [Docker/k8s]       [알림 엔진] → [Slack/Email]
      ↓
[Observability] → [Langfuse/LangSmith] (선택)
```

## 2. SLI (Service Level Indicators)

### 요청 레벨 SLI

| SLI | 측정 방법 | 수집 주기 |
|-----|-----------|-----------|
| 응답 시간 (P50/P95/P99) | MetricsCollector (in-memory) | 실시간 |
| 에러율 | status_code >= 500 비율 | 실시간 |
| 처리량 | requests/minute | 1분 |
| 가용성 | 성공 응답 / 총 요청 | 1분 |

### 컴포넌트 레벨 SLI

| 컴포넌트 | SLI | 측정 방법 |
|----------|-----|-----------|
| API 서버 | 헬스체크 성공률 | GET /api/health (30초 주기) |
| 검색 서비스 | 검색 지연 시간 | SearchService 호출 타이머 |
| 생성 서비스 | LLM 응답 시간 | GenerationService 호출 타이머 |
| 캐시 | 히트율 | QueryCache.get_stats() |
| DB | 쿼리 시간 | QuoteRepository 호출 타이머 |

## 3. SLO (Service Level Objectives)

| 카테고리 | SLO | 측정 윈도우 | 에러 버짓 |
|----------|-----|------------|-----------|
| 가용성 | 99.5% | 월간 | 3.6시간/월 |
| 검색 응답 시간 | P95 < 500ms | 5분 롤링 | - |
| 생성 응답 시간 | P95 < 5,000ms | 5분 롤링 | - |
| 에러율 | < 1% | 5분 롤링 | - |
| 헬스체크 | 연속 실패 < 3회 | 실시간 | - |

## 4. 현재 구현된 모니터링

### 4.1 헬스체크 엔드포인트
- **경로**: `GET /api/health`
- **파일**: `server/routes/health.py`
- **동작**: 초기화 전 503, 정상 시 200 + 컴포넌트 상태
- **컴포넌트**: search_service, generation_service, toc_service

### 4.2 메트릭 수집기
- **파일**: `scripts/lib/metrics_collector.py`
- **방식**: Thread-safe in-memory 원형 버퍼 (최대 10,000 레코드)
- **수집 항목**: endpoint, method, status_code, duration_ms
- **제외 경로**: `/api/dashboard/*` (자기 참조 방지)

### 4.3 대시보드 API
| 엔드포인트 | 용도 | 기본 윈도우 |
|-----------|------|------------|
| GET /api/dashboard/metrics | 지연 시간 통계 (P50/P95/P99) | 1시간 |
| GET /api/dashboard/stats | 사용 통계 (RPM, 상태 분포) | 24시간 |
| GET /api/dashboard/health-detail | 상세 컴포넌트 상태 | 실시간 |

### 4.4 관측성 (Observability)
- **설정 파일**: `config/observability.yaml`
- **백엔드**: Langfuse (자동 감지) → LangSmith → 로컬 폴백
- **추적 필드**: quote_id, doc_id, year, edition, type, score, span, sha256
- **개인정보**: raw text 저장 비활성화 (기본값)

## 5. 알림 규칙

### Critical (즉시 대응)

| 조건 | 알림 채널 | 대응 |
|------|-----------|------|
| 헬스체크 3회 연속 실패 | Slack + Email | 서버 재시작 확인 |
| 에러율 > 5% (5분 윈도우) | Slack + Email | 로그 확인, 필요 시 롤백 |
| P95 > SLO의 200% | Slack | 부하/병목 분석 |
| API 키 만료/인증 실패 | Email | 키 교체 |

### Warning (모니터링)

| 조건 | 알림 채널 | 대응 |
|------|-----------|------|
| P95 > SLO의 150% | Slack | 추이 관찰 |
| 캐시 히트율 < 10% | Slack | 캐시 설정 검토 |
| 디스크 사용률 > 80% | Email | 로그/데이터 정리 |
| 메모리 사용률 > 80% | Slack | 메모리 누수 점검 |

### Info (일간 리포트)

| 항목 | 주기 | 내용 |
|------|------|------|
| 일간 요약 | 매일 09:00 | 총 요청, 에러율, P95, 상위 쿼리 |
| 주간 품질 | 매주 월 | QualityGate 통과율, 축별 추이 |
| 월간 비용 | 매월 1일 | API 호출 수, 예상 비용 |

## 6. 대시보드 구성 (향후)

### 실시간 대시보드 패널

1. **트래픽**: 분당 요청 수 (실시간 그래프)
2. **지연 시간**: P50/P95/P99 (실시간 게이지)
3. **에러율**: 5분 롤링 (빨/노/초 표시)
4. **컴포넌트 상태**: search/generation/toc (초록/빨강)
5. **캐시 효율**: 히트율 + 총 엔트리 수

### 분석 대시보드 패널

6. **시간대별 트래픽**: 24시간 히스토그램
7. **상위 엔드포인트**: 요청 수 TOP 5
8. **상태 코드 분포**: 200/4xx/5xx 파이 차트
9. **품질 점수**: 4축 평균 + 통과율 추이

## 7. 인시던트 대응 절차

```
1. 알림 수신 (Slack/Email)
2. 헬스체크 확인: GET /api/health
3. 메트릭 확인: GET /api/dashboard/metrics
4. 로그 확인: docker logs skms-api
5. 원인 분류:
   a. API 제공사 장애 → 대기 또는 폴백
   b. 서버 과부하 → 스케일업 또는 Rate Limit 강화
   c. 코드 버그 → 롤백 후 핫픽스
6. 복구 확인: 헬스체크 + 스모크 테스트
7. 포스트모템 작성
```
