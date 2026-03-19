# Sub-project 2: Time Compression + Dramatic Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compress game time to 20-30 min play sessions, add immediate visual feedback on event choices, and implement follow-up event chain system.

**Architecture:** All changes in `public/parktycoon.html`. Adjust win thresholds, event timer, quarterly/candidate intervals. Add screen flash overlay, emoji reaction bubbles, gauge delta animations. Add followup event modal (no-choice news format).

**Tech Stack:** Vanilla JS, Canvas 2D, CSS animations

---

## Task 1: Time Compression — Win Thresholds

**What:** Lower the number of days the player must sustain winning metrics.

**Where:** `checkWinLose()` (~line 2280)

- [ ] **1a.** Scenario 1: Change `G.winDays >= 30` to `G.winDays >= 15` (line 2320)
- [ ] **1b.** Scenario 2: Change `G.winDays >= 20` to `G.winDays >= 10` (line 2306)
- [ ] **1c.** Extract magic numbers into named constants at the top of the game logic section for clarity:
  ```js
  var WIN_DAYS_S1 = 15;  // was 30
  var WIN_DAYS_S2 = 10;  // was 20
  ```
  Then use `WIN_DAYS_S1` / `WIN_DAYS_S2` in both the `checkWinLose()` comparisons.

**Verify:** Start scenario 1, use dev console to set `G.rating = 4.0` and fast-forward — game should end at 15 winDays, not 30.

**Commit:** `feat(game): compress win thresholds — 30→15d (S1), 20→10d (S2)`

---

## Task 2: Time Compression — Event Timer Interval

**What:** Events fire more frequently so the player sees 8-10 events in a shorter game.

**Where:** Main game loop, event timer check (~line 1592)

- [ ] **2a.** Change the event timer threshold from `(40 + Math.random() * 20) * 60` to `(20 + Math.random() * 10) * 60`
  - Current code (line 1592): `if (!G.eventActive && G.eventTimer > (40 + Math.random() * 20) * 60)`
  - New: `if (!G.eventActive && G.eventTimer > (20 + Math.random() * 10) * 60)`
  - This roughly halves the time between events.

**Verify:** Play the game — events should appear approximately every 20-30 in-game ticks instead of 40-60.

**Commit:** `feat(game): halve event timer interval for faster pacing`

---

## Task 3: Time Compression — Quarterly Meeting & Candidate Refresh

**What:** Make quarterly meetings and candidate refresh happen every 15 days instead of 30.

**Where:** `dayTick()` (~lines 1706-1713)

- [ ] **3a.** Change candidate refresh from `G.gDay % 30 === 0` to `G.gDay % 15 === 0` (line 1706)
- [ ] **3b.** Change quarterly meeting trigger from `G.gDay % 30 === 0` to `G.gDay % 15 === 0` (line 1709)
- [ ] **3c.** Change quarterly meeting reset from `G.gDay % 30 === 1` to `G.gDay % 15 === 1` (line 1713)

**Verify:** Play — strategy meeting should appear on day 15 instead of day 30. Hiring candidates should refresh on day 15.

**Commit:** `feat(game): quarterly meeting + candidates every 15d (was 30d)`

---

## Task 4: HUD Dynamic Win Threshold Display

**What:** The HUD win counter currently shows `Math.floor(G.winDays) + '/30d'` regardless of scenario. Make it dynamic.

**Where:** `updateHUD()` (~line 2677-2684)

- [ ] **4a.** Replace the hardcoded `/30d` display (line 2680):
  ```js
  // Before:
  winEl.textContent = Math.floor(G.winDays) + '/30d';

  // After:
  var winTarget = G.scenario === 2 ? WIN_DAYS_S2 : WIN_DAYS_S1;
  winEl.textContent = Math.floor(G.winDays) + '/' + winTarget + 'd';
  ```
- [ ] **4b.** Also update the condition check — currently it only checks `G.rating >= 3.0`, but scenario 2 requires all four metrics. Update to show `-` when conditions are not met for the active scenario:
  ```js
  var winMet = (G.scenario === 2)
    ? (G.custSat >= 75 && G.empHap >= 65 && G.socVal >= 60 && G.rating >= 4.0)
    : (G.rating >= 3.0);
  winEl.textContent = winMet ? Math.floor(G.winDays) + '/' + winTarget + 'd' : '-';
  ```

**Verify:** Start scenario 2 — HUD should show `X/10d`. Scenario 1 should show `X/15d`.

**Commit:** `fix(game): HUD win counter uses dynamic threshold per scenario`

---

## Task 5: Screen Flash Effect (CSS Overlay)

**What:** After an event choice, flash the entire screen green (positive) or red (negative) for 0.3s.

**Where:** New CSS + new helper function + wire into event choice handler (~line 3737)

- [ ] **5a.** Add CSS for the flash overlay. Insert into the `<style>` block:
  ```css
  #screen-flash {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    pointer-events: none;
    opacity: 0;
    z-index: 9999;
    transition: opacity 0.3s ease-out;
  }
  #screen-flash.positive { background: rgba(34,197,94,0.15); opacity: 1; }
  #screen-flash.negative { background: rgba(220,38,38,0.15); opacity: 1; }
  ```
- [ ] **5b.** Add the DOM element. In the HTML body (near the toast element), add:
  ```html
  <div id="screen-flash"></div>
  ```
- [ ] **5c.** Add helper function `flashScreen(type)`:
  ```js
  function flashScreen(type) {
    var el = document.getElementById('screen-flash');
    el.className = type; // 'positive' or 'negative'
    setTimeout(function() { el.className = ''; }, 300);
  }
  ```
- [ ] **5d.** Determine positive/negative: Create a helper `classifyChoice(choice)` that inspects the choice's `apply` function effects. A simpler approach — check the `preview` text for cost/negative indicators:
  ```js
  function classifyChoiceEffect(preview) {
    // Heuristic: if preview contains 퇴사, -, 감소 without positive terms → negative
    var negTerms = ['퇴사', '-$', '-20', '-15', '-10', '-5', '감소'];
    var posTerms = ['+', '성장', '무료'];
    var negCount = 0, posCount = 0;
    for (var i = 0; i < negTerms.length; i++) if (preview.indexOf(negTerms[i]) >= 0) negCount++;
    for (var i = 0; i < posTerms.length; i++) if (preview.indexOf(posTerms[i]) >= 0) posCount++;
    return posCount >= negCount ? 'positive' : 'negative';
  }
  ```
- [ ] **5e.** Wire into the event choice click handler (line 3737-3744). After `choice.apply(G)`, call:
  ```js
  flashScreen(classifyChoiceEffect(choice.preview));
  ```
- [ ] **5f.** Also wire into `autoPickWorst()` (~line 3774) — always flash negative since it's the worst option:
  ```js
  flashScreen('negative');
  ```

**Verify:** Trigger an event, pick a choice — screen should briefly flash green or red.

**Commit:** `feat(game): screen flash overlay on event choice (green/red 0.3s)`

---

## Task 6: Worker Emoji Reaction Bubbles

**What:** After an event choice, show emoji bubbles (😊/😡/😰) floating above affected workers for 2 seconds.

**Where:** New rendering logic in the canvas draw loop + trigger from event choice handler

- [ ] **6a.** Add a `G.emojiReactions` array to `createInitialState()` (after `pendingModals`, ~line 752):
  ```js
  emojiReactions: []  // [{workerId, emoji, startTime}]
  ```
- [ ] **6b.** Add helper function `showWorkerReactions(emoji, filterFn)`:
  ```js
  function showWorkerReactions(emoji, filterFn) {
    var now = Date.now();
    var targets = G.workers.filter(function(w) { return !w.quitting && (!filterFn || filterFn(w)); });
    // Show on up to 5 random workers if no filter, or all filtered workers
    if (!filterFn && targets.length > 5) {
      targets.sort(function() { return Math.random() - 0.5; });
      targets = targets.slice(0, 5);
    }
    for (var i = 0; i < targets.length; i++) {
      G.emojiReactions.push({ workerId: targets[i].id, emoji: emoji, startTime: now });
    }
  }
  ```
- [ ] **6c.** In the canvas draw loop (where workers are rendered), after drawing each worker, check if there's a matching emoji reaction and draw it:
  ```js
  // Inside the worker draw loop, after drawing the worker sprite:
  for (var ei = 0; ei < G.emojiReactions.length; ei++) {
    var er = G.emojiReactions[ei];
    if (er.workerId === worker.id) {
      var elapsed = Date.now() - er.startTime;
      if (elapsed < 2000) {
        var alpha = 1 - elapsed / 2000;
        var floatY = -10 - (elapsed / 2000) * 20; // float upward
        ctx.globalAlpha = alpha;
        ctx.font = '16px sans-serif';
        ctx.fillText(er.emoji, screenX, screenY + floatY);
        ctx.globalAlpha = 1;
      }
    }
  }
  ```
- [ ] **6d.** Clean up expired reactions. In the main game loop (or at the start of draw), prune old entries:
  ```js
  var now = Date.now();
  G.emojiReactions = G.emojiReactions.filter(function(r) { return now - r.startTime < 2000; });
  ```
- [ ] **6e.** Wire into event choice handler. After `choice.apply(G)` and `flashScreen()`, determine the appropriate emoji and call `showWorkerReactions()`:
  ```js
  // Positive choice → happy faces on random workers
  // Negative choice → sad/angry on random workers
  var effectType = classifyChoiceEffect(choice.preview);
  showWorkerReactions(effectType === 'positive' ? '😊' : '😡');
  ```
  For specific events that affect specific worker types (e.g., burnout affecting disengaged), use a filter:
  ```js
  // Special cases can be handled by event id if desired
  if (G.currentEvent.id === 'burnout') {
    showWorkerReactions('😰', function(w) { return w.type === 'disengaged' || w.type === 'cynic'; });
  }
  ```

**Verify:** Trigger an event, choose — emoji bubbles should float up from workers and fade out over 2s.

**Commit:** `feat(game): worker emoji reaction bubbles after event choices`

---

## Task 7: Gauge Delta Animation

**What:** When metrics change after an event choice, show `+12▲` (green) or `-8▼` (red) floating text near the HUD gauge bars.

**Where:** New CSS animation + new function + wire into event choice handler

- [ ] **7a.** Add CSS for floating delta numbers:
  ```css
  .gauge-delta {
    position: absolute;
    font-size: 13px;
    font-weight: bold;
    pointer-events: none;
    animation: floatUp 1.5s ease-out forwards;
    z-index: 100;
  }
  .gauge-delta.positive { color: #4ade80; }
  .gauge-delta.negative { color: #f87171; }
  @keyframes floatUp {
    0% { opacity: 1; transform: translateY(0); }
    100% { opacity: 0; transform: translateY(-24px); }
  }
  ```
- [ ] **7b.** Add helper function `showGaugeDelta(gaugeId, delta)` that creates a temporary DOM element:
  ```js
  function showGaugeDelta(gaugeId, delta) {
    if (delta === 0) return;
    var gauge = document.getElementById(gaugeId);
    if (!gauge) return;
    var el = document.createElement('span');
    el.className = 'gauge-delta ' + (delta > 0 ? 'positive' : 'negative');
    el.textContent = (delta > 0 ? '+' + delta + '▲' : delta + '▼');
    // Position relative to gauge element
    gauge.style.position = 'relative';
    el.style.position = 'absolute';
    el.style.right = '-4px';
    el.style.top = '-14px';
    gauge.appendChild(el);
    setTimeout(function() { if (el.parentNode) el.parentNode.removeChild(el); }, 1500);
  }
  ```
- [ ] **7c.** Snapshot metrics before applying the choice, then diff after. In the event choice click handler (line 3737), wrap the apply call:
  ```js
  // Before apply
  var prevMetrics = {
    custSat: G.custSat, empHap: G.empHap, socVal: G.socVal,
    money: G.money, rating: G.rating
  };
  choice.apply(G);
  // After apply — show deltas
  var deltas = {
    custSat: Math.round(G.custSat - prevMetrics.custSat),
    empHap: Math.round(G.empHap - prevMetrics.empHap),
    socVal: Math.round(G.socVal - prevMetrics.socVal),
    money: Math.round(G.money - prevMetrics.money)
  };
  if (deltas.custSat) showGaugeDelta('hud-cust', deltas.custSat);
  if (deltas.empHap) showGaugeDelta('hud-emp', deltas.empHap);
  if (deltas.socVal) showGaugeDelta('hud-soc', deltas.socVal);
  if (deltas.money) showGaugeDelta('hud-money', deltas.money);
  ```
- [ ] **7d.** Verify the gauge element IDs match actual HUD IDs in the DOM. Search for `id='hud-cust'` etc. and adjust if needed.

**Verify:** Pick an event choice — floating `+10▲` or `-$2000▼` numbers should appear near the relevant HUD gauges and fade out.

**Commit:** `feat(game): gauge delta animations (+N▲/-N▼) after event choices`

---

## Task 8: Follow-up Event Data — `FOLLOWUP_EVENTS` Array

**What:** Define the follow-up event data as specified in the design doc.

**Where:** New constant array, placed near the `EVENTS` array (~after line 690, before `createInitialState`)

- [ ] **8a.** Add `FOLLOWUP_EVENTS` constant:
  ```js
  var FOLLOWUP_EVENTS = {
    'talent_scout_retain': {
      id: 'talent_scout_retain',
      headline: '인재 유지 성공',
      body: '연봉 인상 결정 이후, 에이스 직원이 회사에 남기로 했습니다. 팀 사기가 올라갔습니다.',
      effects: { empHap: 10 },
      sourceEvent: 'talent_scout'
    },
    'talent_scout_lost': {
      id: 'talent_scout_lost',
      headline: '팀 사기 저하',
      body: '에이스 직원을 보내준 뒤, 남은 팀원들의 사기가 눈에 띄게 떨어졌습니다.',
      effects: { empHap: -10 },
      sourceEvent: 'talent_scout'
    },
    'burnout_recovery': {
      id: 'burnout_recovery',
      headline: '직원 복귀, 의욕 회복',
      body: '강제 휴가 조치 후, 번아웃 직원들이 활력을 되찾아 복귀했습니다.',
      effects: { empHap: 10 },
      sourceEvent: 'burnout'
    },
    'burnout_spread': {
      id: 'burnout_spread',
      headline: '번아웃 확산',
      body: '번아웃을 무시한 결과, 추가 직원 2명이 무기력 상태로 전환되었습니다.',
      effects: { empHap: -10 },
      sourceEvent: 'burnout'
    },
    'ai_anxiety': {
      id: 'ai_anxiety',
      headline: '남은 직원 불안 확산',
      body: 'AI 구조조정 감원 이후, 남은 직원들 사이에서 "나도 잘리나" 불안이 퍼지고 있습니다.',
      effects: { empHap: -10 },
      sourceEvent: 'ai_replacement'
    },
    'ai_reskill_success': {
      id: 'ai_reskill_success',
      headline: 'AI 역량 확보 성공',
      body: '리스킬링 투자가 결실을 맺어 직원들이 AI 역량을 갖추게 되었습니다.',
      effects: { empHap: 8, custSat: 5 },
      sourceEvent: 'ai_replacement'
    },
    'quiet_quitting_hope': {
      id: 'quiet_quitting_hope',
      headline: '변화의 조짐',
      body: '1:1 면담과 커리어 패스 제시 이후, 무기력했던 직원에게서 변화가 보이기 시작합니다.',
      effects: { empHap: 5 },
      sourceEvent: 'quiet_quitting'
    },
    'quiet_quitting_exit': {
      id: 'quiet_quitting_exit',
      headline: '조용한 퇴사 시작',
      body: '방치한 결과, 조용히 이력서를 돌리던 직원 2명이 퇴사했습니다.',
      effects: { empHap: -15 },
      sourceEvent: 'quiet_quitting'
    }
  };
  ```

**Verify:** Console — `Object.keys(FOLLOWUP_EVENTS).length` should return 8.

**Commit:** `feat(game): add FOLLOWUP_EVENTS data (8 follow-up scenarios)`

---

## Task 9: Follow-up State & Triggering Infrastructure

**What:** Add `G.pendingFollowups` to game state, and process pending followups in `dayTick()`.

**Where:** `createInitialState()` (~line 692) and `dayTick()` (~line 1634)

- [ ] **9a.** Add to `createInitialState()` (after `pendingModals`, ~line 752):
  ```js
  pendingFollowups: []  // [{triggerDay: number, eventId: string}]
  ```
- [ ] **9b.** In `dayTick()`, after the buff countdown section (~line 1703) and before the candidate refresh, add follow-up processing:
  ```js
  // Process pending follow-up events
  var triggered = [];
  for (var fi = G.pendingFollowups.length - 1; fi >= 0; fi--) {
    if (G.pendingFollowups[fi].triggerDay <= G.gDay) {
      triggered.push(G.pendingFollowups[fi]);
      G.pendingFollowups.splice(fi, 1);
    }
  }
  for (var ti = 0; ti < triggered.length; ti++) {
    var fu = FOLLOWUP_EVENTS[triggered[ti].eventId];
    if (fu) {
      showFollowupModal(fu);
    }
  }
  ```
  Note: If multiple followups trigger on the same day, they queue. Use `G.pendingModals` or show sequentially.
- [ ] **9c.** Handle save/load — add `pendingFollowups` to save/load serialization. In the save function (~line 6297), add:
  ```js
  pendingFollowups: G.pendingFollowups || []
  ```
  In the load function (~line 6335), add:
  ```js
  G.pendingFollowups = save.pendingFollowups || [];
  ```

**Verify:** In console, push `{triggerDay: G.gDay + 1, eventId: 'burnout_recovery'}` to `G.pendingFollowups`, advance a day — followup modal should appear.

**Commit:** `feat(game): pendingFollowups queue + dayTick processing`

---

## Task 10: Follow-up Event Modal UI

**What:** A news-style popup modal for follow-up events — no choices, just headline + body + "확인" button + "📰 후속" badge.

**Where:** New function `showFollowupModal(fu)`

- [ ] **10a.** Create `showFollowupModal(followupEvent)` function:
  ```js
  function showFollowupModal(fu) {
    sfxEvent();
    var overlay = document.getElementById('event-overlay');
    while (overlay.firstChild) overlay.removeChild(overlay.firstChild);

    var card = document.createElement('div');
    card.className = 'event-card';

    // Badge
    var badge = document.createElement('div');
    badge.className = 'event-tag';
    badge.textContent = '📰 후속';
    badge.style.background = 'rgba(251,191,36,0.2)';
    badge.style.color = '#FCD34D';
    card.appendChild(badge);

    // Headline
    var headline = document.createElement('div');
    headline.className = 'event-headline';
    headline.textContent = fu.headline;
    card.appendChild(headline);

    // Source reference
    var sourceRef = document.createElement('div');
    sourceRef.style.cssText = 'font-size:11px;color:rgba(255,255,255,0.4);margin-bottom:8px;';
    var sourceEvt = EVENTS.find(function(e) { return e.id === fu.sourceEvent; });
    sourceRef.textContent = "지난 '" + (sourceEvt ? sourceEvt.headline : fu.sourceEvent) + "' 결정의 결과입니다";
    card.appendChild(sourceRef);

    // Body
    var body = document.createElement('div');
    body.className = 'event-desc';
    body.textContent = fu.body;
    card.appendChild(body);

    // Apply effects
    if (fu.effects) {
      if (fu.effects.empHap) G.empHap = clamp(0, 100, G.empHap + fu.effects.empHap);
      if (fu.effects.custSat) G.custSat = clamp(0, 100, G.custSat + fu.effects.custSat);
      if (fu.effects.socVal) G.socVal = clamp(0, 100, G.socVal + fu.effects.socVal);
      if (fu.effects.money) G.money += fu.effects.money;
    }

    // Effects summary line
    var effectLine = document.createElement('div');
    effectLine.style.cssText = 'font-size:12px;margin:8px 0;color:rgba(255,255,255,0.6);';
    var parts = [];
    if (fu.effects.empHap) parts.push('직원행복 ' + (fu.effects.empHap > 0 ? '+' : '') + fu.effects.empHap);
    if (fu.effects.custSat) parts.push('고객만족 ' + (fu.effects.custSat > 0 ? '+' : '') + fu.effects.custSat);
    if (fu.effects.socVal) parts.push('사회가치 ' + (fu.effects.socVal > 0 ? '+' : '') + fu.effects.socVal);
    if (fu.effects.money) parts.push('자금 ' + (fu.effects.money > 0 ? '+$' : '-$') + Math.abs(fu.effects.money));
    effectLine.textContent = parts.join(' | ');
    card.appendChild(effectLine);

    // OK button
    var btn = document.createElement('button');
    btn.className = 'event-choice';
    btn.textContent = '확인';
    btn.addEventListener('click', function() {
      overlay.classList.remove('show');
      // Show gauge deltas for followup effects
      if (fu.effects.empHap) showGaugeDelta('hud-emp', fu.effects.empHap);
      if (fu.effects.custSat) showGaugeDelta('hud-cust', fu.effects.custSat);
      if (fu.effects.socVal) showGaugeDelta('hud-soc', fu.effects.socVal);
      if (fu.effects.money) showGaugeDelta('hud-money', fu.effects.money);
      // Flash
      var isPositive = (fu.effects.empHap || 0) + (fu.effects.custSat || 0) + (fu.effects.socVal || 0) > 0;
      flashScreen(isPositive ? 'positive' : 'negative');
      updateHUD();
      addHistoryEntry(fu.headline, '📰 후속', '📰');
      saveGame();
    });
    card.appendChild(btn);

    overlay.appendChild(card);
    overlay.classList.add('show');
  }
  ```
- [ ] **10b.** Handle conflict with regular events: If `G.eventActive` is true when a followup triggers, defer it (re-push with triggerDay+1). Add this guard in the dayTick processing from Task 9.

**Verify:** Manually trigger a followup modal — should show yellow "📰 후속" badge, source reference, body text, effect summary, and single "확인" button.

**Commit:** `feat(game): follow-up event modal UI (📰 badge, no-choice format)`

---

## Task 11: Wire Follow-up Triggering into Event Choice Handler

**What:** When a player picks an event choice that has follow-up consequences, schedule the follow-up.

**Where:** Event choice click handler (~line 3737) and `EVENTS` array choices

- [ ] **11a.** Add `delayed` field to relevant event choices in the `EVENTS` array. Modify existing choice objects:

  **talent_scout** (line ~508):
  - Choice 0 (연봉 인상): add `delayed: {days: 3, eventId: 'talent_scout_retain'}`
  - Choice 1 (보내주기): add `delayed: {days: 3, eventId: 'talent_scout_lost'}`

  **burnout** (line ~526):
  - Choice 0 (강제 휴가): add `delayed: {days: 5, eventId: 'burnout_recovery'}`
  - Choice 1 (무시): add `delayed: {days: 4, eventId: 'burnout_spread'}`

  **ai_replacement** — find this event in EVENTS:
  - Choice for 감원: add `delayed: {days: 3, eventId: 'ai_anxiety'}`
  - Choice for 리스킬링: add `delayed: {days: 5, eventId: 'ai_reskill_success'}`

  **quiet_quitting** — find this event:
  - Choice for 1:1+커리어: add `delayed: {days: 4, eventId: 'quiet_quitting_hope'}`
  - Choice for 무시: add `delayed: {days: 3, eventId: 'quiet_quitting_exit'}`

- [ ] **11b.** In the event choice click handler (line 3737-3744), after `choice.apply(G)`, check for delayed field and push to pendingFollowups:
  ```js
  if (choice.delayed) {
    G.pendingFollowups.push({
      triggerDay: G.gDay + choice.delayed.days,
      eventId: choice.delayed.eventId
    });
  }
  ```
- [ ] **11c.** Also handle `autoPickWorst()` — if the auto-picked worst choice has a `delayed` field, push it too (~line 3774):
  ```js
  if (lastValid.delayed) {
    G.pendingFollowups.push({
      triggerDay: G.gDay + lastValid.delayed.days,
      eventId: lastValid.delayed.eventId
    });
  }
  ```

**Verify:** Trigger `talent_scout` event → pick "연봉 인상" → wait 3 in-game days → "인재 유지 성공" followup modal should appear.

**Commit:** `feat(game): wire delayed followups into event choices (8 chains)`

---

## Task 12: Enhanced Toast for Event Outcomes

**What:** After an event choice, the toast message should include a brief numeric summary of what changed.

**Where:** Event choice handler + `showToast()` call

- [ ] **12a.** Build a summary string from the metric deltas computed in Task 7. After computing deltas, construct a toast line:
  ```js
  var summaryParts = [];
  if (deltas.empHap) summaryParts.push('행복 ' + (deltas.empHap > 0 ? '+' : '') + deltas.empHap);
  if (deltas.custSat) summaryParts.push('고객 ' + (deltas.custSat > 0 ? '+' : '') + deltas.custSat);
  if (deltas.socVal) summaryParts.push('사회 ' + (deltas.socVal > 0 ? '+' : '') + deltas.socVal);
  if (deltas.money) summaryParts.push((deltas.money > 0 ? '+$' : '-$') + Math.abs(deltas.money));
  if (summaryParts.length > 0) {
    showToast(summaryParts.join(', '), deltas.money >= 0 && deltas.empHap >= 0 ? 'success' : 'warn');
  }
  ```
- [ ] **12b.** This replaces the current pattern where only specific events show toasts. The summary toast fires for every event choice.

**Verify:** Pick any event choice — toast should show e.g. "행복 +10, -$2000".

**Commit:** `feat(game): summary toast with metric deltas after every event choice`

---

## Task 13: Follow-up Effects on Workers (Specific Mechanics)

**What:** Some followups need to do more than adjust gauges — they need to change worker types or trigger quits.

**Where:** `showFollowupModal()` effects processing

- [ ] **13a.** Extend `FOLLOWUP_EVENTS` entries with a `specialEffect` function where needed:
  - `talent_scout_lost`: `specialEffect: function(G) { convertRandom(G, 'rookie', 'cynic', 1); }` — convert 1 rookie to cynic
  - `burnout_spread`: `specialEffect: function(G) { convertRandom(G, 'rookie', 'disengaged', 2); }` — 2 become disengaged
  - `ai_anxiety`: `specialEffect: function(G) { /* mark random workers with increased quit risk, or will-10 for all */ var ws = G.workers.filter(function(w){return !w.quitting;}); for(var i=0;i<ws.length;i++) ws[i].will = Math.max(0, (ws[i].will||50) - 10); }`
  - `ai_reskill_success`: `specialEffect: function(G) { convertRandom(G, 'rookie', 'ace', 2); }` — 2 rookies become ace
  - `quiet_quitting_hope`: `specialEffect: function(G) { convertRandom(G, 'disengaged', 'rookie', 1); }`
  - `quiet_quitting_exit`: `specialEffect: function(G) { quitRandom(G, 2); }`

- [ ] **13b.** Add helper `convertRandom(G, fromType, toType, count)` if not already present:
  ```js
  function convertRandom(G, fromType, toType, count) {
    var candidates = G.workers.filter(function(w) { return w.type === fromType && !w.quitting; });
    candidates.sort(function() { return Math.random() - 0.5; });
    for (var i = 0; i < Math.min(count, candidates.length); i++) {
      candidates[i].type = toType;
    }
  }
  ```
- [ ] **13c.** In `showFollowupModal()`, after applying gauge effects, call `specialEffect` if present:
  ```js
  if (fu.specialEffect) fu.specialEffect(G);
  ```

**Verify:** Trigger `burnout` → pick "무시" → wait 4 days → followup fires → check that 2 workers became disengaged.

**Commit:** `feat(game): follow-up special effects (type conversions, quits)`

---

## Task 14: Integration Testing & Polish

**What:** End-to-end playthrough to verify all sub-project 2 features work together.

- [ ] **14a.** Play a full scenario 1 game and verify:
  - Win threshold is 15 days (not 30)
  - Events fire roughly twice as often
  - Quarterly meeting appears on day 15
  - HUD shows `X/15d`
  - At least 1 followup event fires
  - Screen flashes on event choices
  - Emoji reactions appear on workers
  - Gauge deltas float near HUD bars
  - Toast shows metric summary
- [ ] **14b.** Play scenario 2 and verify:
  - Win threshold is 10 days
  - HUD shows `X/10d`
  - All four metrics must be met for counter to advance
- [ ] **14c.** Test edge cases:
  - Multiple followups triggering on the same day
  - Followup triggering while another event is active (should defer)
  - Auto-pick (timeout) with delayed choices
  - Save/load preserves pendingFollowups
- [ ] **14d.** Visual polish: Adjust timing/colors if flash is too harsh, emoji too small, delta text overlapping gauges, etc.

**Commit:** `fix(game): sub-project 2 integration polish and edge cases`

---

## Summary

| Task | Description | Estimated Size |
|------|-------------|---------------|
| 1 | Win thresholds 30→15, 20→10 | XS |
| 2 | Event timer interval halved | XS |
| 3 | Quarterly/candidate 30→15 days | XS |
| 4 | HUD dynamic threshold display | S |
| 5 | Screen flash overlay (CSS + JS) | S |
| 6 | Worker emoji reaction bubbles | M |
| 7 | Gauge delta animation (+N▲/-N▼) | M |
| 8 | FOLLOWUP_EVENTS data array | S |
| 9 | pendingFollowups state + dayTick | S |
| 10 | Follow-up modal UI (📰 badge) | M |
| 11 | Wire delayed fields into choices | S |
| 12 | Enhanced toast with deltas | XS |
| 13 | Follow-up special effects | M |
| 14 | Integration test + polish | M |

**Total: 14 tasks, ~7 commits**

Tasks 1-4 can be done as one commit (time compression). Tasks 5-7 can be done as one commit (dramatic feedback). Tasks 8-11 can be grouped (followup system). Task 12-13 are additive. Task 14 is verification.
