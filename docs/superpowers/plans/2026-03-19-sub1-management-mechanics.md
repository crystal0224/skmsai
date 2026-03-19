# Sub-project 1: Management Mechanics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add forced distribution performance reviews, strategy-based compensation, and SKMS-tagged event dilemmas with follow-up events.

**Architecture:** All changes in single file `public/parktycoon.html`. Modify `openPerfPanel()` for quota system with pending state, replace `openCompPanel()` with strategy cards, add `skmsTag`/`delayed` fields to EVENTS, add FOLLOWUP_EVENTS array, add pendingFollowups check in dayTick().

**Tech Stack:** Vanilla JS, Canvas 2D, Web Audio API

**File:** `/Users/crystal/skmsai/public/parktycoon.html` (6454 lines)

**Verification:** No TDD — visual verification in browser after each task. Open `public/parktycoon.html` directly in browser, start a game, and test each mechanic manually.

---

## Task 1: Add New Game State Fields to `createInitialState()`

**Location:** `createInitialState()` at line ~692 (inside the `state` object literal, before `return state;` at line 762)

**What to add:** Insert three new fields into the state object, after the `pendingModals: []` line (line 752):

- `skmsChoices: []` — Array to record SKMS-tagged event choices. Each entry: `{eventId: string, choiceIdx: number, tag: string, day: number}`
- `pendingFollowups: []` — Queue of delayed follow-up events. Each entry: `{triggerDay: number, event: followupEventObject}`
- `compStrategy: null` — Current compensation strategy. Values: `'performance'` | `'equal'` | `'growth'` | `null`

**Also update save/load:**

In `saveGame()` (line ~6289), add these three fields to the `save` object:
- `skmsChoices: (G.skmsChoices || []).slice(-20)` (keep last 20 for save size)
- `pendingFollowups: G.pendingFollowups || []`
- `compStrategy: G.compStrategy || null`

In `loadGame()` (line ~6328), restore them:
- `G.skmsChoices = save.skmsChoices || [];`
- `G.pendingFollowups = save.pendingFollowups || [];`
- `G.compStrategy = save.compStrategy || null;`

Bump save version from `v: 2` to `v: 3`. Update `hasSavedGame()` to accept both v2 and v3 (backward compat: `if (s.v !== 2 && s.v !== 3) return null;`).

**Steps:**
- [ ] 1.1 Add `skmsChoices`, `pendingFollowups`, `compStrategy` to `createInitialState()` state object
- [ ] 1.2 Update `saveGame()` to persist new fields
- [ ] 1.3 Update `loadGame()` to restore new fields with defaults
- [ ] 1.4 Bump save version to 3, update `hasSavedGame()` for backward compat
- [ ] 1.5 Verify: start new game, check `G.skmsChoices`, `G.pendingFollowups`, `G.compStrategy` exist in console

**Commit:** `feat(game): add skmsChoices, pendingFollowups, compStrategy state fields`

---

## Task 2: Rewrite `openPerfPanel()` with Forced Distribution Quota System

**Location:** `openPerfPanel()` at line ~2880-2981

**Current behavior:** Each worker row has S/A/B/C/D buttons. Clicking a grade button immediately applies will/hap/bonus effects and reloads the panel. No limits on grade counts.

**New behavior:** Pending grades with quota enforcement and a confirm button.

### 2A. Add CSS for quota bar and confirm button

**Location:** Inside the `<style>` block (ends around line ~400). Add after the existing `.mgmt-grade-btn:hover` rule (line ~346):

New CSS classes to add:
- `.perf-quota-bar` — Container for the quota status display at panel top. Use `display:flex; gap:6px; padding:8px 12px; background:rgba(255,255,255,0.03); border-radius:6px; margin-bottom:8px; flex-wrap:wrap; align-items:center; font-size:10px; color:rgba(255,255,255,0.5);`
- `.perf-quota-item` — Each quota segment (S, A, B, C, D). Use `display:flex; gap:2px; align-items:center;`
- `.perf-quota-item.over` — When quota exceeded. Add `color:#f87171; font-weight:700;`
- `.perf-quota-item.under` — When minimum not met (C/D). Add `color:#fbbf24; font-weight:700;`
- `.perf-quota-item.ok` — Within limits. Add `color:#4ade80;`
- `.perf-confirm-btn` — The confirm button. Use `width:100%; margin-top:10px; padding:10px; border:1px solid rgba(74,222,128,0.3); border-radius:8px; background:rgba(74,222,128,0.1); color:#4ade80; font-size:13px; font-weight:700; cursor:pointer; font-family:inherit; transition:all .15s;`
- `.perf-confirm-btn:hover` — `background:rgba(74,222,128,0.2);`
- `.perf-confirm-btn:disabled` — `opacity:0.3; cursor:not-allowed; color:rgba(255,255,255,0.3); border-color:rgba(255,255,255,0.1); background:rgba(255,255,255,0.03);`
- `.perf-warning` — Warning text when C/D quota not met. `font-size:10px; color:#fbbf24; text-align:center; padding:4px 0;`

### 2B. Rewrite the function body

Replace the entire `openPerfPanel()` function. The new implementation:

1. **Initialize `pendingGrades` map** (local to this panel instance): `var pendingGrades = {};` — Maps workerId to grade object.

2. **Pre-populate** from any existing `w.perfGrade` so the panel shows current state.

3. **Render quota bar** at the top of the panel, showing:
   - `S: {count}/{max} | A: {count}/{max} | B: {count}/- | C: {count}/{min}+ | D: {count}/{min}+`
   - Max for S: `Math.floor(workers.length * 0.2)` (20%)
   - Max for A: `Math.floor(workers.length * 0.3)` (30%)
   - B: unlimited
   - Min for C: `Math.max(1, Math.ceil(workers.length * 0.1))` (10%)
   - Min for D: `Math.max(1, Math.ceil(workers.length * 0.1))` (10%)

4. **Render worker rows** — same layout as current (emoji+id, dept, will bar, cap bar, hap bar, current pending grade, grade buttons). But clicking a grade button:
   - Stores in `pendingGrades[w.id] = gradeObj` instead of applying immediately
   - Disables the button if quota for that grade is already full (S/A max reached)
   - Re-renders the quota bar and button states (call a local `refreshPanel()` function)
   - Highlight the selected grade button with active styling

5. **Render confirm button** at the bottom:
   - Text: "평가 확정" with a checkmark
   - **Disabled** if: (a) not all workers have a pending grade, OR (b) C count < C min, OR (c) D count < D min
   - Show warning text below quota bar when C/D minimums not met: "C/D 등급 최소 배정 필요"

6. **Confirm button click handler:**
   - Iterate `pendingGrades`, for each worker:
     - Set `w.perfGrade = grade.g`
     - Push to `w.perfHistory`
     - Apply `w.will += grade.will`, `w.happiness += grade.hap` (clamped 0-100)
     - If `grade.bonus > 0`: `G.money -= grade.bonus` (company pays the bonus — deduct from treasury)
     - If `grade.pip`: `w.pipActive = true; w.pipDays = 30;`
   - Show toast summarizing results
   - Close panel
   - Call `updateHUD()` and `saveGame()`

7. **Closing panel without confirming** (existing closeMgmtPanel): pendingGrades is simply discarded (it's a local variable, GC handles it).

**Steps:**
- [ ] 2.1 Add new CSS classes for quota bar, confirm button, warning
- [ ] 2.2 Implement quota calculation helper: `calcPerfQuotas(workers)` returning `{sMax, aMax, cMin, dMin}`
- [ ] 2.3 Rewrite `openPerfPanel()` with pending grades map, quota bar, grade buttons with quota enforcement
- [ ] 2.4 Add confirm button with validation (all graded, C/D minimums met)
- [ ] 2.5 Implement confirm handler: batch apply effects, deduct bonus from G.money
- [ ] 2.6 Verify: open perf panel, assign grades, check quota bar updates, confirm and check effects

**Commit:** `feat(game): forced distribution performance review with quota system`

---

## Task 3: Rewrite `openCompPanel()` with Strategy Cards

**Location:** `openCompPanel()` at line ~2983-3075

**Current behavior:** Per-worker salary multiplier buttons (1.1x, 1.2x, 1.3x, freeze). Individual worker rows.

**New behavior:** 3 strategy cards, one-click selection per quarter.

### 3A. Add CSS for strategy cards

**Location:** After the perf panel CSS added in Task 2.

New CSS classes:
- `.comp-cards` — Container. `display:flex; gap:8px; padding:4px 0;`
- `.comp-card` — Individual card. `flex:1; padding:12px 10px; border:1px solid rgba(255,255,255,0.08); border-radius:10px; background:rgba(255,255,255,0.03); cursor:pointer; transition:all .15s; text-align:center;`
- `.comp-card:hover` — `background:rgba(255,255,255,0.06); border-color:rgba(255,255,255,0.15);`
- `.comp-card.active` — Currently selected strategy. `border-color:rgba(255,184,48,0.4); background:rgba(255,184,48,0.08);`
- `.comp-card.disabled` — Not a quarter meeting day, read-only. `opacity:0.5; cursor:not-allowed;`
- `.comp-card-icon` — Emoji. `font-size:24px; margin-bottom:6px;`
- `.comp-card-name` — Strategy name. `font-size:12px; font-weight:700; color:rgba(255,255,255,0.9); margin-bottom:4px;`
- `.comp-card-desc` — Effect summary. `font-size:9px; color:rgba(255,255,255,0.4); line-height:1.4;`
- `.comp-card-badge` — "현재 적용 중" badge. `display:inline-block; padding:2px 6px; background:rgba(255,184,48,0.15); color:#FFB830; border-radius:4px; font-size:8px; font-weight:700; margin-top:6px;`
- `.comp-footer` — Bottom section with cost preview. `margin-top:10px; padding-top:8px; border-top:1px solid rgba(255,255,255,0.1); font-size:11px; color:rgba(255,255,255,0.5);`
- `.comp-readonly-notice` — Message shown outside quarter meeting. `text-align:center; padding:8px; font-size:10px; color:rgba(255,255,255,0.3); background:rgba(255,255,255,0.02); border-radius:6px; margin-bottom:8px;`

### 3B. Define strategy data

Add a `COMP_STRATEGIES` constant array near the existing `EVENTS` array (around line ~640, after SKMS_INSIGHTS):

```
COMP_STRATEGIES = [
  {
    id: 'performance',
    name: '성과연동형',
    icon: '🎯',
    desc: 'S/A등급: 보너스 $80/$40\nC/D등급: 동결\n에이스 유지↑, 시니크 불만↑',
    skmsLink: 'SUPEX 추구',
    apply: function(G) { ... }
  },
  {
    id: 'equal',
    name: '균등분배형',
    icon: '⚖️',
    desc: '전원 의욕+3, 행복+5\n조직 안정↑\n에이스 이탈 위험(10%/분기)',
    skmsLink: '인간중심',
    apply: function(G) { ... }
  },
  {
    id: 'growth',
    name: '역량투자형',
    icon: '🌱',
    desc: '전원 역량+8, 보너스 없음\n장기 성장↑, 단기 만족↓',
    skmsLink: 'VWBE',
    apply: function(G) { ... }
  }
]
```

**Strategy apply functions (called in dayTick when strategy changes or at quarter):**
- `performance`: For each alive worker, if `perfGrade === 'S'` give bonus $80, if `'A'` give $40. Deduct from `G.money`. Aces get `will+5`. Cynics get `will-3, happiness-3`.
- `equal`: For each alive worker, `will += 3, happiness += 5`. But 10% chance per ace per quarter to trigger ace departure warning.
- `growth`: For each alive worker, `capability += 8`. No bonus.

### 3C. Rewrite `openCompPanel()`

Replace the entire function body:

1. **Check if quarter meeting day:** `var isQuarterDay = (G.gDay % 15 === 0);` (spec says 15 days per quarter for Sub-project 2, but for now use 30 days to match current quarterly cycle — this will be updated in Sub-project 2).
   - Actually, use `G.gDay % 30 === 0` for now, consistent with existing `showStrategyMeeting()` cadence.

2. **Show read-only notice** if not a quarter meeting day and a strategy is already set: "전략 변경은 분기 회의(매 30일)에서만 가능합니다. 다음 회의: Day {next}"

3. **Render 3 strategy cards** horizontally:
   - Each card shows: icon, name, effect description, SKMS connection subtitle
   - If `G.compStrategy === card.id`, show "현재 적용 중" badge and `.active` class
   - If not quarter day AND strategy already chosen, add `.disabled` class and disable click

4. **Card click handler:**
   - Show a confirmation dialog (simple overlay or use existing showToast pattern with a modal):
     - "'{name}' 전략을 적용하시겠습니까? 기존 개인별 연봉은 1.0x로 리셋됩니다."
     - OK / Cancel buttons
   - On confirm:
     - Set `G.compStrategy = strategy.id`
     - Reset all workers' `salaryLevel` to 1.0
     - Apply the strategy's immediate effects
     - Show toast: "보상 전략: {name} 적용됨"
     - Close panel, updateHUD(), saveGame()

5. **Footer:** Show estimated monthly labor cost based on current strategy, and a one-line description of the SKMS connection.

### 3D. Apply strategy effects in dayTick()

**Location:** Inside `dayTick()` (line ~1634), after the buff countdown section (around line 1703) and before the hiring candidate refresh:

Add a block that applies ongoing strategy effects once per day:
- If `G.compStrategy === 'equal'`: Check if this is a quarter boundary (`G.gDay % 30 === 0`). If so, for each ace worker, `if (Math.random() < 0.1)` queue a departure warning toast.
- `performance` and `growth` strategies apply their main effects at the point of selection (in the confirm handler). Ongoing effects are minimal.

**Steps:**
- [ ] 3.1 Add CSS for strategy cards, badges, footer, read-only notice
- [ ] 3.2 Define `COMP_STRATEGIES` constant array with 3 strategy objects
- [ ] 3.3 Rewrite `openCompPanel()` with card layout, active badge, disabled state
- [ ] 3.4 Add confirmation dialog on card click with salary reset logic
- [ ] 3.5 Add ongoing strategy effects check in `dayTick()`
- [ ] 3.6 Verify: open comp panel, select strategy, check effects applied, verify read-only outside quarter

**Commit:** `feat(game): strategy-based compensation with 3 SKMS-linked options`

---

## Task 4: Add `skmsTag` to EVENTS Choices

**Location:** `EVENTS` array at line ~503-639 (15 events, each with 3 choices)

**What to change:** Add a `skmsTag` field to each choice object across all 15 events. The tag is an internal identifier — never shown in UI. Values: `'human_centered'`, `'supex'`, `'vwbe'`, `'social_value'`, `'rational'`.

**Tag assignments for all 15 events:**

| Event | Choice 0 | Choice 1 | Choice 2 |
|-------|----------|----------|----------|
| talent_scout | `rational` (연봉 인상 방어) | `null` (포기 — no SKMS tag) | `vwbe` (성장 경로 제시) |
| quality_issue | `rational` (PR 대응) | `human_centered` (전량 리콜 — 고객 보호) | `null` (무시) |
| burnout | `human_centered` (강제 휴가) | `null` (무시) | `vwbe` (자동 완화) |
| gov_audit | `social_value` (통과) | `rational` (급히 준비) | `null` (불합격) |
| price_war | `rational` (가격 맞추기) | `supex` (차별화) | `null` (관망) |
| training_complaint | `rational` (트레이너 고용) | `vwbe` (선배 배치) | `null` (무시) |
| community_service | `social_value` (참여) | `social_value` (기부만) | `null` (거절) |
| labor_conflict | `human_centered` (대화) | `rational` (양보) | `null` (억압) |
| innovation | `supex` (투자) | `null` (패스) | `supex` (빠른 추진) |
| certification | `social_value` (신청) | `null` (건너뛰기) | `null` (부적격) |
| ai_replacement | `human_centered` (AI+인간 협업) | `null` (감원) | `vwbe` (리스킬링) |
| quiet_quitting | `human_centered` (1:1 면담) | `rational` (성과급 강화) | `vwbe` (VWBE 전환) |
| gen_z_burnout | `human_centered` (주4일제) | `human_centered` (멘탈 헬스) | `null` (업무량 재조정만) |
| esg_pressure | `social_value` (ESG 조직 신설) | `null` (보고서만) | `social_value` (사회적 가치 확대) |
| data_breach | `rational` (즉시 공개+보상) | `null` (축소 발표) | `rational` (윤리경영 기반 대응) |

**Implementation:** For each choice object in EVENTS, add `skmsTag: 'tag_name'` or omit the field (treat missing as no tag). Example:
```
{text:'연봉 인상으로 방어', preview:'...', skmsTag:'rational', apply:function(G){...}}
```

**Record in G.skmsChoices:** Modify the event choice click handler in `showEventModal()` (line ~3737-3739). After `G.choiceLog.push(...)`, add:
```
if (choice.skmsTag) {
  G.skmsChoices.push({
    eventId: G.currentEvent.id,
    choiceIdx: idx,
    tag: choice.skmsTag,
    day: G.gDay
  });
}
```

**Steps:**
- [ ] 4.1 Add `skmsTag` to talent_scout, quality_issue, burnout choices (events 0-2)
- [ ] 4.2 Add `skmsTag` to gov_audit, price_war, training_complaint choices (events 3-5)
- [ ] 4.3 Add `skmsTag` to community_service, labor_conflict, innovation choices (events 6-8)
- [ ] 4.4 Add `skmsTag` to certification, ai_replacement, quiet_quitting choices (events 9-11)
- [ ] 4.5 Add `skmsTag` to gen_z_burnout, esg_pressure, data_breach choices (events 12-14)
- [ ] 4.6 Update `showEventModal()` click handler to record skmsTag in `G.skmsChoices`
- [ ] 4.7 Verify: trigger an event, pick a tagged choice, check `G.skmsChoices` in console

**Commit:** `feat(game): add skmsTag to all 15 event choices for SKMS alignment tracking`

---

## Task 5: Add FOLLOWUP_EVENTS Array

**Location:** After the `EVENTS` array (line ~639) and before `SKMS_INSIGHTS` (line ~644). Insert a new constant.

**Define `FOLLOWUP_EVENTS`** — a map (object) keyed by followup ID:

```
var FOLLOWUP_EVENTS = {
  talent_keep_success: {
    id: 'talent_keep_success',
    headline: '인재 유지 성공',
    body: '연봉 인상으로 핵심 인재를 지켰습니다. 팀 사기가 올라갑니다.',
    effects: {empHap: 0, will: 10},
    sourceEvent: 'talent_scout'
  },
  talent_lose_morale: {
    id: 'talent_lose_morale',
    headline: '팀 사기 저하',
    body: '에이스 직원의 이탈로 남은 팀원들의 사기가 떨어졌습니다.',
    effects: {empHap: -10},
    sourceEvent: 'talent_scout'
  },
  burnout_recovery: {
    id: 'burnout_recovery',
    headline: '직원 복귀, 의욕 회복',
    body: '강제 휴가 후 직원이 재충전하여 복귀했습니다. 의욕이 크게 올랐습니다.',
    effects: {will: 20},
    sourceEvent: 'burnout'
  },
  burnout_spread: {
    id: 'burnout_spread',
    headline: '번아웃 확산',
    body: '방치된 번아웃이 팀 전체로 퍼졌습니다. 추가 직원이 무기력해졌습니다.',
    effects: {empHap: -10, convertDisengaged: 2},
    sourceEvent: 'burnout'
  },
  ai_layoff_anxiety: {
    id: 'ai_layoff_anxiety',
    headline: '남은 직원 불안 확산',
    body: 'AI 구조조정 이후 남은 직원들이 "다음은 나인가" 불안에 떨고 있습니다.',
    effects: {will: -10, quitRisk: true},
    sourceEvent: 'ai_replacement'
  },
  ai_reskill_success: {
    id: 'ai_reskill_success',
    headline: 'AI 역량 확보 성공',
    body: '리스킬링 프로그램으로 구성원들이 AI 시대 역량을 갖추었습니다.',
    effects: {capability: 15, convertAce: 2},
    sourceEvent: 'ai_replacement'
  },
  quiet_quit_change: {
    id: 'quiet_quit_change',
    headline: '변화의 조짐',
    body: '1:1 면담과 커리어 경로 제시가 효과를 보기 시작했습니다.',
    effects: {convertRookie: 1},
    sourceEvent: 'quiet_quitting'
  },
  quiet_quit_exodus: {
    id: 'quiet_quit_exodus',
    headline: '조용한 퇴사 시작',
    body: '방치된 무기력이 실제 퇴사로 이어졌습니다. 2명이 떠났습니다.',
    effects: {quitCount: 2},
    sourceEvent: 'quiet_quitting'
  }
};
```

**Add `delayed` field to specific EVENTS choices:**

In the EVENTS array, add a `delayed` field to the relevant choices:

| Event | Choice | delayed value |
|-------|--------|---------------|
| talent_scout | choice 0 (연봉 인상) | `{days: 3, followupId: 'talent_keep_success'}` |
| talent_scout | choice 1 (보내주기) | `{days: 3, followupId: 'talent_lose_morale'}` |
| burnout | choice 0 (강제 휴가) | `{days: 5, followupId: 'burnout_recovery'}` |
| burnout | choice 1 (무시) | `{days: 4, followupId: 'burnout_spread'}` |
| ai_replacement | choice 1 (감원) | `{days: 3, followupId: 'ai_layoff_anxiety'}` |
| ai_replacement | choice 2 (리스킬링) | `{days: 5, followupId: 'ai_reskill_success'}` |
| quiet_quitting | choice 0 (1:1 면담) | `{days: 4, followupId: 'quiet_quit_change'}` |
| quiet_quitting | choice 1 (성과급 강화) | — (no followup for this choice) |
| quiet_quitting | choice 2 (VWBE 전환) | — (no followup, VWBE effect is immediate) |

Wait — spec says choice 1 "무시" gets followup. Let me re-check. The spec table maps:
- quiet_quitting: "1:1+커리어" → followup. "무시" → followup "조용한 퇴사 시작"

But in current code, quiet_quitting choices are: [0] 1:1 면담, [1] 성과급 강화, [2] VWBE 문화 전환. There's no "무시" choice. The closest is if the timer expires (autoPickWorst). For this plan, assign the "조용한 퇴사" followup to autoPickWorst for this event, OR skip it since the spec's "무시" doesn't exist as an explicit choice. **Decision:** Add the followup to choice index when timer expires in `autoPickWorst()` — this is complex. Instead, just assign followups to the choices that exist and match the spec intent:

| Event | Choice idx | delayed value |
|-------|------------|---------------|
| talent_scout | 0 | `{days: 3, followupId: 'talent_keep_success'}` |
| talent_scout | 1 | `{days: 3, followupId: 'talent_lose_morale'}` |
| burnout | 0 | `{days: 5, followupId: 'burnout_recovery'}` |
| burnout | 1 | `{days: 4, followupId: 'burnout_spread'}` |
| ai_replacement | 1 | `{days: 3, followupId: 'ai_layoff_anxiety'}` |
| ai_replacement | 2 | `{days: 5, followupId: 'ai_reskill_success'}` |
| quiet_quitting | 0 | `{days: 4, followupId: 'quiet_quit_change'}` |

**Update `showEventModal()` click handler** (line ~3737): After recording choiceLog and skmsChoices, check if the choice has a `delayed` field:
```
if (choice.delayed) {
  var followup = FOLLOWUP_EVENTS[choice.delayed.followupId];
  if (followup) {
    G.pendingFollowups.push({
      triggerDay: G.gDay + choice.delayed.days,
      event: followup
    });
  }
}
```

**Steps:**
- [ ] 5.1 Define `FOLLOWUP_EVENTS` object with 8 follow-up events (after EVENTS array)
- [ ] 5.2 Add `delayed` field to talent_scout choices 0 and 1
- [ ] 5.3 Add `delayed` field to burnout choices 0 and 1
- [ ] 5.4 Add `delayed` field to ai_replacement choices 1 and 2
- [ ] 5.5 Add `delayed` field to quiet_quitting choice 0
- [ ] 5.6 Update `showEventModal()` click handler to queue followup events
- [ ] 5.7 Verify: trigger talent_scout event, pick choice 0, check `G.pendingFollowups` has entry

**Commit:** `feat(game): add FOLLOWUP_EVENTS and delayed field for event chain reactions`

---

## Task 6: Process Pending Followups in `dayTick()`

**Location:** Inside `dayTick()` function (line ~1634). Add a new section after the buff countdown block (after line ~1703, before the hiring candidate refresh at line ~1705).

### 6A. Add followup processing logic

```
// --- Pending followup events ---
if (G.pendingFollowups.length > 0) {
  var triggered = [];
  var remaining = [];
  for (var fi = 0; fi < G.pendingFollowups.length; fi++) {
    if (G.pendingFollowups[fi].triggerDay <= G.gDay) {
      triggered.push(G.pendingFollowups[fi].event);
    } else {
      remaining.push(G.pendingFollowups[fi]);
    }
  }
  G.pendingFollowups = remaining;
  for (var ti = 0; ti < triggered.length; ti++) {
    showFollowupModal(triggered[ti]);
  }
}
```

Note: If multiple followups trigger on the same day, queue them in `G.pendingModals` to avoid overlapping modals. Or show them sequentially with a small delay.

### 6B. Add `showFollowupModal()` function

**Location:** After `showEventModal()` (line ~3753).

Create a new function `showFollowupModal(followupEvt)`:

1. Pause game: `G.gSpeed = 0;`
2. Use the same `event-overlay` element
3. Create a card with:
   - A badge at top: "📰 후속 보도" styled with `background:rgba(251,191,36,0.15); color:#fbbf24; padding:3px 8px; border-radius:4px; font-size:10px; font-weight:700; display:inline-block; margin-bottom:8px;`
   - Headline: `followupEvt.headline` (same `.event-headline` class)
   - Body text: `followupEvt.body` (same `.event-desc` class)
   - Source reference: "지난 '{sourceEventHeadline}' 결정의 결과입니다" in `font-size:10px; color:rgba(255,255,255,0.3); font-style:italic; margin-top:8px;` — look up the source event headline from EVENTS by matching `followupEvt.sourceEvent`.
   - Single "확인" button (no choices) styled like an event choice button but centered.

4. **"확인" click handler:** Apply effects from `followupEvt.effects`:
   - `empHap`: add to `G.empHap` (clamped 0-100)
   - `will`: add to all alive workers' `will` (clamped 0-100)
   - `capability`: add to all alive workers' `capability` (clamped 0-100)
   - `custSat`: add to `G.custSat` (clamped 0-100)
   - `socVal`: add to `G.socVal` (clamped 0-100)
   - `convertDisengaged`: call `convertRandom(G, 'rookie', 'disengaged', N)` for N workers
   - `convertAce`: call `convertRandom(G, 'rookie', 'ace', N)` for N workers
   - `convertRookie`: call `convertRandom(G, 'disengaged', 'rookie', N)` for N workers
   - `quitCount`: call `quitRandom(G, N)`
   - `quitRisk`: for each alive worker, `if (Math.random() < 0.15) w.will -= 5` (subtle attrition)
   - Add history entry: `addHistoryEntry(followupEvt.headline, '후속 보도', '📰');`
   - Close overlay, resume game speed, updateHUD(), saveGame()

### 6C. Handle multiple followups on same day

If multiple followups trigger on the same day, queue them through `G.pendingModals`:
```
for (var ti = 0; ti < triggered.length; ti++) {
  G.pendingModals.push({type: 'followup', data: triggered[ti]});
}
```

Then in the existing `pendingModals` processing code (find where it checks `G.pendingModals`), add a case for `type === 'followup'` that calls `showFollowupModal(modal.data)`.

**Steps:**
- [ ] 6.1 Add followup processing block in `dayTick()` after buff countdowns
- [ ] 6.2 Implement `showFollowupModal()` with headline, body, source reference, confirm button
- [ ] 6.3 Implement effects application in confirm handler (empHap, will, capability, conversions, quits)
- [ ] 6.4 Add "📰 후속" badge styling
- [ ] 6.5 Handle multiple same-day followups via `G.pendingModals` queue
- [ ] 6.6 Verify: manually set `G.pendingFollowups = [{triggerDay: G.gDay + 1, event: FOLLOWUP_EVENTS.burnout_recovery}]` in console, advance day, check modal appears

**Commit:** `feat(game): followup event processing in dayTick with news modal`

---

## Task 7: Replace `calcSKMSAlignment()` with Tag-Based Calculation

**Location:** `calcSKMSAlignment()` at line ~4914-4927

**Current logic:** Score based on active policy count, empHap, totalQuits, ignoreCount, pressureCount. Simple additive formula.

**New logic:** Based on `G.skmsChoices` tag distribution across 5 SKMS principles.

**New implementation:**

1. Count choices by tag from `G.skmsChoices`:
   ```
   var tagCounts = {human_centered:0, supex:0, vwbe:0, social_value:0, rational:0};
   var totalTagged = 0;
   for (var i = 0; i < G.skmsChoices.length; i++) {
     var tag = G.skmsChoices[i].tag;
     if (tagCounts[tag] !== undefined) {
       tagCounts[tag]++;
       totalTagged++;
     }
   }
   ```

2. Calculate per-principle alignment (0-100%):
   - Each principle's score = `(tagCounts[principle] / maxPossibleForPrinciple) * 100`
   - But since we don't track "max possible," use relative scoring:
     - If no choices made yet, fall back to old formula (policy count based) for smooth early game
     - If choices made, weight each principle by how many tagged choices exist for it vs total tagged choices

3. **Weighted average formula:**
   ```
   if (totalTagged === 0) {
     // Fallback: old formula for early game
     var score = Object.keys(G.activePolicies).length * 8;
     if (G.empHap > 70) score += 10;
     if (G.totalQuits <= 2) score += 5;
     score -= G.ignoreCount * 8;
     return clamp(0, 100, score);
   }
   // Each of 5 principles has equal weight (20%)
   var principleScore = 0;
   var principles = ['human_centered', 'supex', 'vwbe', 'social_value', 'rational'];
   for (var p = 0; p < principles.length; p++) {
     // Presence score: did the player ever choose this principle?
     // More choices = higher alignment for that principle
     var pScore = Math.min(100, tagCounts[principles[p]] * 33); // 1 choice=33%, 2=66%, 3+=100%
     principleScore += pScore * 0.2; // each principle worth 20%
   }
   // Bonus for policy count (minor)
   principleScore += Math.min(15, Object.keys(G.activePolicies).length * 2);
   // Penalty for ignoring events
   principleScore -= G.ignoreCount * 5;
   return clamp(0, 100, Math.round(principleScore));
   ```

4. **Also export per-principle breakdown** for use in ending report (Sub-project 3). Add a new function `calcSKMSBreakdown()` returning:
   ```
   {
     human_centered: percentage,
     supex: percentage,
     vwbe: percentage,
     social_value: percentage,
     rational: percentage,
     overall: overallPercentage
   }
   ```
   `calcSKMSAlignment()` will call `calcSKMSBreakdown().overall`.

**Update call sites:** The function signature stays the same (returns a number 0-100), so all existing callers (lines 4452, 4797, 6388) continue to work unchanged.

**Steps:**
- [ ] 7.1 Implement `calcSKMSBreakdown()` with per-principle tag counting and scoring
- [ ] 7.2 Rewrite `calcSKMSAlignment()` to use `calcSKMSBreakdown().overall`
- [ ] 7.3 Add early-game fallback when `G.skmsChoices` is empty
- [ ] 7.4 Verify: play through 3-4 events with different tags, check alignment % changes appropriately
- [ ] 7.5 Verify: ending report still shows SKMS alignment correctly

**Commit:** `feat(game): tag-based SKMS alignment calculation replacing policy-count formula`

---

## Summary

| Task | Description | Lines Affected | Estimated Changes |
|------|-------------|---------------|-------------------|
| 1 | Game state fields | ~692-762, ~6289-6360 | +15 lines |
| 2 | Perf panel rewrite | ~2880-2981, ~330-350 (CSS) | ~200 lines (replace ~100) |
| 3 | Comp panel rewrite | ~2983-3075, CSS, ~640 | ~200 lines (replace ~90) |
| 4 | skmsTag on events | ~503-639, ~3737 | ~50 lines modified |
| 5 | FOLLOWUP_EVENTS + delayed | after ~639, ~503-639 | +80 lines |
| 6 | dayTick + followup modal | ~1703, after ~3753 | +100 lines |
| 7 | calcSKMSAlignment rewrite | ~4914-4927 | ~50 lines (replace ~13) |

**Total estimated:** ~650 net new lines, ~200 lines replaced. File grows from ~6454 to ~6900 lines.

**Implementation order:** Tasks 1 → 4 → 5 → 2 → 3 → 6 → 7 (state fields first, then data changes, then UI, then processing, then calculation).

**Commits:** 7 commits, one per task. Each commit should leave the game playable.
