# SKMS AI Studio 프론트엔드 통합 — 세부 실행 계획

> 작성일: 2026-03-02 | 상태: Phase 4.5 진입
>
> 2026-03-16 업데이트: 현재 운영 프론트 source of truth는 `public/`이다.
> 이 문서의 프론트 파일 경로는 모두 `public/index.html`, `public/styles.css` 기준으로 해석한다.

## 현재 완료 상태

### 이번 세션에서 완료된 작업
| # | 작업 | 커밋 |
|---|------|------|
| 1 | Chat Widget ↔ /api/v2/generate 연동 (판본 필터 포함) | ec42cc1 |
| 2 | Workspace 모달 ↔ /api/v2/generate + /api/content/generate/async | ec42cc1 |
| 3 | CORS 설정 (localhost:5500/5501 추가) | ec42cc1 |
| 4 | 코드 리뷰 반영 (XSS, polling retry, busy reset) | ec42cc1 |
| 5 | 판본 탐색기 오버레이 (GET /api/editions + /api/toc) | aa535f0 |
| 6 | 통합 검색 오버레이 (POST /api/v2/search) | aa535f0 |
| 7 | 네비게이션 활성화 + 판본 필터 전체 연동 | aa535f0 |
| 8 | Content Studio 6종 카드 그리드 + 4단계 생성 모달 | 5bc2596 |
| 9 | SVG 원형 프로그레스 바 + 5단계 파이프라인 시각화 | 5bc2596 |
| 10 | Plan 미리보기 (POST /api/content/plan) | 5bc2596 |

### API 연결 현황 (10/29 엔드포인트)
```
✅ GET  /api/health                                      → 자동 연결 체크
✅ GET  /api/editions                                    → 판본 탐색기 + 필터 드롭다운
✅ GET  /api/toc/{edition_id}                            → 목차 트리
✅ GET  /api/toc?q=                                      → 목차 검색
✅ POST /api/v2/search                                   → 검색 오버레이
✅ POST /api/v2/generate                                 → Chat + Workspace 문서 생성
✅ POST /api/content/plan                                → Content Studio 계획 미리보기
✅ POST /api/content/generate/async                      → Content Studio 비동기 생성
✅ GET  /api/content/status/{req_id}                     → 비동기 폴링
✅ GET  /api/content/download/{req_id}/{filename}        → 파일 다운로드
```

---

## 미완료 작업 — 순차 실행 계획

### ✅ STEP 1: Content Studio 타입별 옵션 폼 (프론트엔드) — 완료
**우선순위:** P0 | **의존성:** 없음

**구현 내용:**
- [x] `studio-modal-body`에 타입별 조건부 렌더링 추가 (`data-for` 속성)
- [x] lecture: 소요시간(15/30/45/60/90분), 테마(Corporate/Education/Seminar), 발표자 노트 토글
- [x] card_news: 카드 수(3-10, range slider), 스타일 선택
- [x] workshop: 소요시간(30/60/90/120분), 스타일, 퀴즈 포함 토글
- [x] visualization: 차트 유형(timeline/mindmap/sankey/radar/comparison/flowchart)
- [x] audio: 소요시간(1-10분, range slider), 스타일(narration/dialogue/podcast)
- [x] quiz: 문항 수(5-20, range slider), 스타일 선택
- [x] `collectTypeOptions()` 함수로 API 요청에 포함
- [x] 백엔드 수정: audio style, viz_type을 opts.style에서 읽도록 변경

**수정 파일:** `public/index.html`, `public/styles.css`, `scripts/lib/content_studio/__init__.py`

---

### ✅ STEP 2: 파일 다운로드 엔드포인트 (백엔드) — 완료
**우선순위:** P0 | **의존성:** 없음

**구현 내용:**
- [x] `GET /api/content/download/{request_id}/{filename}` 엔드포인트 추가
- [x] `FileResponse`로 스트리밍 반환 (`_guess_media_type`으로 MIME 자동 감지)
- [x] request_id UUID 형식 검증 + 파일명 path traversal 방지 (/, \\, .. 차단)
- [x] `Path("output").resolve()` 기반 경로 검증으로 이중 보호
- [x] 프론트엔드 결과 화면에 다운로드 버튼 연결
- [x] 14개 테스트 작성 (성공, 404, path traversal, MIME type)

**수정 파일:**
- `server/routes/content.py` — 다운로드 라우트 + `_guess_media_type` 유틸
- `public/index.html` — 결과 화면 다운로드 버튼
- `public/styles.css` — `.file-download-btn` 스타일
- `tests/test_content_studio/test_download_api.py` — 14개 테스트

---

### STEP 3: 파일 미리보기 컴포넌트 (프론트엔드)
**우선순위:** P1 | **예상 시간:** 3-4시간 | **의존성:** STEP 2

생성 결과를 파일 이름 목록이 아닌, 실제 미리보기로 보여줌.

**작업 내용:**
- [ ] 결과 화면(Step 4)에 타입별 미리보기 컴포넌트 추가
- [ ] PNG/SVG: `<img>` 태그로 인라인 표시 + 이미지 캐러셀
- [ ] HTML (workshop/quiz): `<iframe>` sandbox로 미리보기
- [ ] MP3: `<audio>` 플레이어 컨트롤
- [ ] PPTX/PDF: 첫 페이지 썸네일 + 다운로드 버튼
- [ ] 각 파일에 다운로드 버튼 연결 (STEP 2 엔드포인트 사용)

**수정 파일:** `public/index.html`, `public/styles.css`

---

### STEP 4: MCP 어댑터 실제 API 검증 (백엔드)
**우선순위:** P0 | **예상 시간:** 2-4시간 | **의존성:** API 키 필요

Content Studio의 6개 MCP 어댑터가 모두 mock/fallback으로만 동작 중.

**작업 내용:**
- [ ] NanoBanana (이미지): GEMINI_API_KEY 환경변수 확인 + 실제 호출 테스트
- [ ] AntV Chart (차트): MCP 서버 연동 검증 또는 fallback 강화
- [ ] ElevenLabs (음성): API 키 설정 + 실제 TTS 생성 테스트
- [ ] 각 어댑터의 에러 핸들링 강화 (quota 초과, 네트워크 오류)
- [ ] 스모크 테스트 스크립트 작성: `scripts/test_mcp_live.py`

**수정 파일:**
- `scripts/lib/content_studio/adapters/nano_banana.py`
- `scripts/lib/content_studio/adapters/antv_chart.py`
- `scripts/lib/content_studio/adapters/elevenlabs.py`

---

### STEP 5: Plan 아웃라인 편집 UI (프론트엔드)
**우선순위:** P1 | **예상 시간:** 3-4시간 | **의존성:** STEP 1

현재 Plan 미리보기가 읽기 전용. 사용자가 수정할 수 없음.

**작업 내용:**
- [ ] Plan JSON을 편집 가능한 구조화된 폼으로 변환
- [ ] 슬라이드/카드 항목 드래그 앤 드롭 순서 변경
- [ ] 개별 항목 제목/내용 인라인 편집
- [ ] 항목 추가/삭제 버튼
- [ ] 수정된 plan을 `/api/content/generate`에 전달

**수정 파일:** `public/index.html`, `public/styles.css`

---

### STEP 6: Dashboard 모니터링 뷰 (프론트엔드)
**우선순위:** P2 | **예상 시간:** 3-4시간 | **의존성:** 없음

백엔드의 `/api/dashboard/*` 3개 엔드포인트가 프론트에 미노출.

**작업 내용:**
- [ ] 네비게이션에 "DASHBOARD" 링크 추가 (또는 관리자 전용)
- [ ] Dashboard 오버레이 구현
- [ ] 서비스 상태 카드 (search/generation/toc/content_studio 가용 여부)
- [ ] 요청 메트릭 표시 (총 요청, 성공률, p95 레이턴시)
- [ ] 시간별 요청 추이 차트 (간단한 CSS bar chart)
- [ ] Quality 요약 (전체 등급, 합격률, 커버리지)

**연결 엔드포인트:**
- `GET /api/dashboard/metrics`
- `GET /api/dashboard/stats`
- `GET /api/dashboard/health-detail`
- `GET /api/quality/summary`

---

### STEP 7: Publisher 실제 구현 — Notion/Google Workspace (백엔드)
**우선순위:** P2 | **예상 시간:** 3-4시간 | **의존성:** STEP 2

현재 mock 구현만 있음. 실제 API 연동 필요.

**작업 내용:**
- [ ] Notion: `notion-client` SDK로 페이지 생성 + 파일 업로드
- [ ] Google Workspace: `google-api-python-client`로 Drive 업로드 + Docs 생성
- [ ] 각 Publisher에 OAuth 토큰 관리 추가
- [ ] Content Studio 생성 결과에 "Notion에 발행" / "Drive에 저장" 버튼 연결
- [ ] 테스트 추가

**수정 파일:**
- `scripts/lib/content_studio/adapters/notion.py`
- `scripts/lib/content_studio/adapters/google_ws.py`
- `public/index.html` (결과 화면에 발행 버튼)

---

### STEP 8: Tech Debt 해소 (TD-001, TD-005)
**우선순위:** P2 | **예상 시간:** 7-10시간 | **의존성:** 없음

**TD-001: 디렉토리 구조 통합**
- `scripts/lib/content_studio/` → `src/content_studio/`로 이동
- 모든 import 경로 업데이트
- CI 설정 업데이트

**TD-005: E2E 테스트 격리**
- pytest-tmp-files 또는 Docker 기반 격리 환경 구축
- 파일 시스템 의존 테스트 분리

---

### STEP 9: E2E 통합 테스트 (프론트엔드 ↔ 백엔드)
**우선순위:** P1 | **예상 시간:** 3-4시간 | **의존성:** STEP 1~3

**작업 내용:**
- [ ] Playwright 또는 Cypress 설정
- [ ] Chat 위젯 E2E: 메시지 전송 → 응답 표시
- [ ] Content Studio E2E: 타입 선택 → 옵션 입력 → 생성 → 결과 확인
- [ ] 검색 E2E: 키워드 입력 → 필터 적용 → 결과 표시
- [ ] 판본 탐색 E2E: 판본 선택 → 목차 트리 확인
- [ ] 에러 시나리오: 서버 미응답, 네트워크 오류

---

## 실행 순서 요약

```
STEP 1 ─── Content Studio 타입별 옵션 폼  ──── [P0, ✅ 완료]
  │
STEP 2 ─── 파일 다운로드 엔드포인트  ────────── [P0, ✅ 완료]
  │
STEP 3 ─── 파일 미리보기 컴포넌트  ──────────── [P1, 3-4h, 프론트]
  │
STEP 4 ─── MCP 어댑터 실제 API 검증  ────────── [P0, 2-4h, 백엔드]
  │
STEP 5 ─── Plan 아웃라인 편집 UI  ───────────── [P1, 3-4h, 프론트]
  │
STEP 6 ─── Dashboard 모니터링 뷰  ───────────── [P2, 3-4h, 프론트]
  │
STEP 7 ─── Publisher 실제 구현  ──────────────── [P2, 3-4h, 백엔드]
  │
STEP 8 ─── Tech Debt (TD-001, TD-005)  ──────── [P2, 7-10h, 리팩토링]
  │
STEP 9 ─── E2E 통합 테스트  ─────────────────── [P1, 3-4h, 테스트]
```

**MVP까지 (STEP 1-4):** ~10시간
**베타까지 (STEP 1-7):** ~22시간
**전체 완료 (STEP 1-9):** ~32시간
