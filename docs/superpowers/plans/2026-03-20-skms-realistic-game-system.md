# SKMS 현실감 있는 경영 시뮬레이션 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SKMS 원칙이 게임 메커닉에 유기적으로 녹아든 현실감 있는 경영 시뮬레이션 구축 — 타운홀 미팅, 의욕관리, 조직문화 진단, Better Company 목표, SKMS 가이드 + 13개 SKMS 기반 이벤트

**Architecture:** `public/parktycoon.html` 단일 파일. 새 게임 스탯 4개 (`vwbeLevel`, `trust`, `courage`, `coordination`)를 `createInitialState()`에 추가. 경영관리 탭에 5개 패널 함수 추가. EVENTS 배열에 13개 이벤트 추가. 이벤트 선택 시 새 스탯 자동 반영.

**Tech Stack:** Vanilla JS, CSS, Canvas 2D

---

## Sub-project A: 게임 스탯 + 경영관리 탭 확장 (Tasks 1-6)
## Sub-project B: SKMS 기반 이벤트 13개 (Tasks 7-8)

---

## Task 1: 새 게임 스탯 추가

**Where:** `createInitialState()` (~line 916), `saveGame()`, `loadGame()`

- [ ] **1a.** `createInitialState()`에 4개 스탯 추가 (after `emojiReactions`, ~line 981):
  ```js
  // SKMS culture stats (internal, shown in 조직문화 진단 panel only)
  vwbeLevel: 20,     // 0-100, VWBE 문화 수준
  trust: 30,         // 0-100, 조직 신뢰도
  courage: 20,       // 0-100, 패기 수준
  coordination: 25,  // 0-100, 부서 간 협력 수준
  // Better Company quarterly goal
  quarterGoal: null,  // {metric:'empHap'|'custSat'|'socVal', target:70, reward:2000}
  quarterProgress: 0, // days meeting goal
  // Town hall
  lastTownHall: 0,   // last day town hall was held
  ```

- [ ] **1b.** `saveGame()`에 새 필드 직렬화 추가
- [ ] **1c.** `loadGame()`에 새 필드 역직렬화 추가 (fallback 기본값)
- [ ] **1d.** 이벤트 선택 시 스탯 자동 반영 — `showEventModal()` 내 choice 클릭 핸들러에서 skmsTag에 따라:
  - `human_centered` → trust +3, empHap bonus
  - `vwbe` → vwbeLevel +5, courage +3
  - `supex` → courage +5, custSat bonus
  - `social_value` → trust +3, socVal bonus
  - `rational` → coordination +2
  - 태그 없음 (무시/압박) → trust -5, courage -3

**Commit:** `feat(game): add vwbeLevel, trust, courage, coordination stats + auto-update on event choice`

---

## Task 2: 타운홀 미팅 기능

**Where:** 경영관리 탭 mgmtItems 배열 + 새 함수 `openTownHallPanel()`

- [ ] **2a.** mgmtItems에 추가: `{emoji: '🏛️', label: '타운홀', fn: openTownHallPanel}`

- [ ] **2b.** `openTownHallPanel()` 함수 생성:
  - 패널 UI: "전 구성원 타운홀 미팅" 제목
  - 쿨다운: 10일에 1회만 가능 (`G.gDay - G.lastTownHall >= 10`)
  - 비용: $500
  - 효과 선택 (3개 중 1개):
    - "솔직한 대화" → empHap +8, trust +10, vwbeLevel +5
    - "비전 공유" → courage +10, coordination +8, custSat +3
    - "고충 처리" → empHap +12, trust +5, laborTension -10
  - 실행 시: `G.lastTownHall = G.gDay`, money -= 500, 선택 효과 적용
  - SKMS 인용: "구성원은 상호 신뢰와 존중을 바탕으로 협력" (15246)
  - 쿨다운 중이면 "D-N 후 가능" 표시

**Commit:** `feat(game): add town hall meeting — 3 agenda options, 10-day cooldown`

---

## Task 3: 의욕관리 패널

**Where:** 새 함수 `openMotivationPanel()`

- [ ] **3a.** mgmtItems에 추가: `{emoji: '🔥', label: '의욕관리', fn: openMotivationPanel}`

- [ ] **3b.** `openMotivationPanel()` 함수:
  - 직원 타입별 카드 (에이스/시니크/신입/무기력/리더)
  - 각 카드: 인원수, 평균 의욕 (의욕 = worker.will 또는 타입별 기본값)
  - 액션 버튼 per 타입:
    - 에이스: "도전 과제 부여" $300 → courage +5, 에이스 1명 리더 전환 확률 +20%
    - 시니크: "1:1 면담" $200 → trust +3, 시니크 1명 → 신입 전환 (VWBE 정책 필요)
    - 신입: "멘토 배정" $400 → 신입 성장 2배 10일 (OJT 정책 필요, 에이스 1명 이상)
    - 무기력: "특별 관리" $500 → 무기력 1명 → 신입 전환 (HR 부서 필요)
    - 리더: "리더십 개발" $600 → trust +5, coordination +5
  - SKMS 인용: "구성원 행복에 영향을 미치는 다양한 요소를 파악하고 측정" (15173)

**Commit:** `feat(game): add motivation management panel with per-type actions`

---

## Task 4: 조직문화 진단 패널

**Where:** 새 함수 `openCulturePanel()`

- [ ] **4a.** mgmtItems에 추가: `{emoji: '📊', label: '조직문화', fn: openCulturePanel}`

- [ ] **4b.** `openCulturePanel()` 함수:
  - 4개 게이지 바: VWBE 수준, 패기도, 신뢰도, 협력도
  - 각 바: 라벨 + 수치 + 프로그레스 바 (색상: 0-30 빨강, 31-60 노랑, 61-100 초록)
  - "최근 변화" 섹션: choiceLog 최근 3개에서 어떤 스탯이 변했는지
  - "추천 액션" 2개 (가장 낮은 스탯 기반):
    - vwbeLevel 낮음 → "제안 활동 시작" $300, vwbeLevel +10
    - trust 낮음 → "타운홀 미팅 개최" (타운홀로 이동)
    - courage 낮음 → "도전 과제 부여" $300, courage +10
    - coordination 낮음 → "부서 교류회" $400, coordination +10
  - SKMS 인용: "강하고 우수한 기업문화를 구축하고 지속적으로 진화시키는 것은 경쟁력의 원천" (15107)

**Commit:** `feat(game): add culture diagnostic panel with 4 gauges + recommended actions`

---

## Task 5: Better Company 분기 목표

**Where:** `dayTick()` 내 분기 로직 (~15일마다) + 새 함수 `showBetterCompanyGoal()`

- [ ] **5a.** `dayTick()`에서 `G.gDay % 15 === 0 && !G.quarterGoal` 일 때 `showBetterCompanyGoal()` 호출

- [ ] **5b.** `showBetterCompanyGoal()` — 3개 목표 중 선택:
  - "💚 구성원 행복 집중" → empHap 70+ 유지 5일 → 보상 $2000 + 별점 +0.2
  - "👥 고객 가치 집중" → custSat 70+ 유지 5일 → 보상 $2000 + 별점 +0.2
  - "🌍 사회적 가치 집중" → socVal 60+ 유지 5일 → 보상 $2000 + 별점 +0.2
  - 선택 시 `G.quarterGoal = {metric, target, reward}`, `G.quarterProgress = 0`
  - UI: 모달, SKMS 인용 "Better Company 목표를 반복적으로 달성하면서 SUPEX Company를 구현" (15161)

- [ ] **5c.** `dayTick()`에서 목표 진행 체크:
  - `G.quarterGoal` 존재 시, 해당 metric >= target이면 `G.quarterProgress++`
  - `G.quarterProgress >= 5`이면 보상 지급 + 토스트 + `G.quarterGoal = null`
  - 15일(다음 분기) 도래 시 미달성이면 토스트 "목표 미달성 — 다음 기회에" + 리셋

- [ ] **5d.** HUD에 목표 표시: win 카운터 옆에 작은 아이콘 (목표 활성 시)

**Commit:** `feat(game): Better Company quarterly goals — choose focus, track progress, earn rewards`

---

## Task 6: SKMS 원칙 가이드

**Where:** 경영 정책 버튼 옆 + 새 함수 `openSKMSGuide()`

- [ ] **6a.** 상단 바 또는 경영 정책 패널 내에 "📖 SKMS" 버튼 추가

- [ ] **6b.** `openSKMSGuide()` — 탭 형태:
  - 4개 탭: [인간중심] [SUPEX] [VWBE] [사회가치]
  - 각 탭:
    - SKMS 원문 인용 (2020 14차)
    - "게임에서의 의미" — 어떤 메커닉과 연결되는지
    - 현재 수치 표시 (관련 스탯)
  - 데이터:
    - 인간중심: "SK 경영의 궁극적 목적은 구성원 행복이다" → empHap, trust
    - SUPEX: "최고의 경쟁력을 보유하고 장기적 생존 조건을 확보" → custSat, rating
    - VWBE: "자발적·의욕적 두뇌활용이 곧 패기" → vwbeLevel, courage
    - 사회가치: "이해관계자 행복을 위해 회사가 창출하는 모든 가치" → socVal, coordination

**Commit:** `feat(game): SKMS philosophy guide with 4 principle tabs + current stats`

---

## Task 7: SKMS 기반 이벤트 7개 (카테고리 A+B)

**Where:** `EVENTS` 배열 끝에 추가 + `FOLLOWUP_EVENTS`에 관련 후속 이벤트

**이벤트 목록:**

1. **bottom_up_proposal** — "바닥에서 올라온 제안": 신입이 프로세스 개선안 제출
2. **failed_project_leader** — "실패한 프로젝트의 팀장": 도전적 프로젝트 실패 후 처우
3. **silent_meeting** — "아무도 손 안 드는 회의": 전략회의 무응답
4. **overtime_culture** — "야근이 미덕인가": 야근 문화 vs 결과 중심
5. **supplier_pressure** — "납품사 단가 인하": 수익 vs 파트너 행복
6. **factory_relocation** — "공장 이전 vs 지역 고용": 효율 vs 사회 가치
7. **quarter_vs_rnd** — "분기 실적 vs 장기 R&D": 단기 vs 장기

- [ ] **7a.** 7개 이벤트를 EVENTS 배열에 추가 (각 3개 선택지, skmsTag, delayed 포함)
- [ ] **7b.** 관련 FOLLOWUP_EVENTS 4개 추가
- [ ] **7c.** 이벤트 설명에 SKMS 원문 인용 포함 (edition, line number)

**Commit:** `feat(game): add 7 SKMS-rooted events — VWBE dilemmas + stakeholder balance`

---

## Task 8: SKMS 기반 이벤트 6개 (카테고리 C+D)

**이벤트 목록:**

8. **leader_first** — "리더가 먼저": 위기 상황 솔선수범
9. **together_apart** — "따로 또 같이": 자회사 간 협력
10. **successor_development** — "후계자 육성": 에이스→리더 전환
11. **better_company_event** — "Better Company 도전": 혁신 목표 도전 이벤트
12. **innovation_dilemma** — "혁신의 딜레마": 파괴적 혁신 vs 점진적 개선
13. **global_opportunity** — "글로벌 진출": 해외 진출 기회

- [ ] **8a.** 6개 이벤트를 EVENTS 배열에 추가
- [ ] **8b.** 관련 FOLLOWUP_EVENTS 3개 추가
- [ ] **8c.** 기존 이벤트 5개 설명 개선 (SKMS 인용 추가)

**Commit:** `feat(game): add 6 SKMS leadership + SUPEX events, improve 5 existing events`

---

## Summary

| Task | 내용 | 크기 |
|------|------|------|
| 1 | 새 스탯 4개 + 자동 반영 | S |
| 2 | 타운홀 미팅 | M |
| 3 | 의욕관리 패널 | M |
| 4 | 조직문화 진단 | M |
| 5 | Better Company 분기 목표 | M |
| 6 | SKMS 가이드 | S |
| 7 | SKMS 이벤트 7개 | L |
| 8 | SKMS 이벤트 6개 + 기존 개선 | L |

**Total: 8 tasks, ~8 commits**

Tasks 1-6은 순차 (스탯 → 패널들 → 가이드). Tasks 7-8은 1 이후 병렬 가능.
