# Sub-project 3: Ending Report Card Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the ending report from vertical list to card grid layout with rich SKMS coaching feedback including DNA analysis, specific choice evaluation, and actionable next-game suggestions.

**Architecture:** Rewrite `showReport()` in `public/parktycoon.html`. Replace vertical sections with card grid (header, 3-col gauges, 2x2 stats, TOP3 choices, SKMS coaching). Add `SKMS_COACHING` data array. Replace `calcSKMSAlignment()` with tag-based calculation from `G.skmsChoices`. New CSS for report cards with mobile responsive breakpoints.

**Tech Stack:** Vanilla JS, CSS Grid/Flexbox

---

## Dependencies

- **Sub-project 1 (경영관리 메커닉 강화)** must be complete first:
  - `G.skmsChoices` array must exist in `createInitialState()` (added by Sub-project 1C)
  - `choiceLog` entries must include `skmsTag` field (added by Sub-project 1C)
  - Events must have `skmsTag` on choices (added by Sub-project 1C)
- If implementing standalone (before Sub-1), add temporary fallback: check `G.skmsChoices` existence and fall back to current `calcSKMSAlignment()` if absent.

## File

- **Single file**: `public/parktycoon.html` (~6400 lines)
- **No external dependencies** — vanilla JS/CSS only

## Current State (what gets replaced)

| Component | Current Location | Lines | Status |
|-----------|-----------------|-------|--------|
| Report CSS | Lines 172-192 | 21 lines | Replace |
| `SKMS_INSIGHTS` array | Lines 644-685 | 42 lines | Replace with `SKMS_COACHING` |
| `showReport()` | Lines 4430-4703 | 274 lines | Rewrite |
| `addReportRow()` | Lines 4859-4870 | 12 lines | Remove |
| `addReportBar()` | Lines 4872-4894 | 23 lines | Remove |
| `addReportCheck()` | Lines 4896-4902 | 7 lines | Remove |
| `getManagementStyle()` | Lines 4904-4912 | 9 lines | Keep (unchanged) |
| `calcSKMSAlignment()` | Lines 4914-4927 | 14 lines | Rewrite |
| `getReportText()` | Lines 4708-4722 | 15 lines | Update |
| `captureReport()` | Lines 4756-4855 | 100 lines | Rewrite |
| Mobile CSS | Line 6424 | 1 line | Replace with new breakpoints |

---

## Task 1: New CSS — Report Card Grid & Component Styles

**What:** Replace existing report CSS (lines 172-192) with new card grid layout styles.

**Changes:**
- [ ] 1.1 — Replace `.report-card` width from `480px` to `max-width:700px; width:95vw`
- [ ] 1.2 — Update `.report-card` background to `rgba(255,255,255,0.04)`, border to `1px solid rgba(255,255,255,0.08)`, border-radius `12px`
- [ ] 1.3 — Add `.rpt-header` card style: full-width, `text-align:center`, padding `20px`
- [ ] 1.4 — Add `.rpt-gauges` 3-column layout: `display:flex; gap:12px; justify-content:space-between`
- [ ] 1.5 — Add `.rpt-gauge-col` style: `flex:1; text-align:center`, with inner bar and label
- [ ] 1.6 — Add `.rpt-stats-grid` 2x2 layout: `display:grid; grid-template-columns:1fr 1fr; gap:8px`
- [ ] 1.7 — Add `.rpt-stat-card` style: same card bg/border, `padding:12px; border-radius:10px; text-align:center`
- [ ] 1.8 — Add `.rpt-stat-number`: `font-size:24px; font-weight:800` with color variants `.num-up{color:#4ade80}`, `.num-down{color:#f87171}`, `.num-neutral{color:rgba(255,255,255,0.6)}`
- [ ] 1.9 — Add `.rpt-top3-row`: `display:flex; gap:8px; overflow-x:auto`
- [ ] 1.10 — Add `.rpt-top3-card`: `min-width:140px; flex:1; padding:12px; border-radius:10px`, same card bg/border
- [ ] 1.11 — Add `.rpt-coaching-card`: `background:rgba(255,255,255,0.03); border-left:3px solid; padding:14px; border-radius:0 10px 10px 0; margin-bottom:10px`
- [ ] 1.12 — Add coaching card color variants: `.coaching-good{border-left-color:#4ade80}`, `.coaching-bad{border-left-color:#f59e0b}`, `.coaching-next{border-left-color:#60a5fa}`
- [ ] 1.13 — Add `.rpt-quote`: `font-style:italic; color:rgba(255,255,255,0.5); font-size:11px; margin-top:8px`
- [ ] 1.14 — Add `.rpt-source`: `color:rgba(255,255,255,0.3); font-size:10px; display:block; margin-top:4px`
- [ ] 1.15 — Add `.rpt-dna-bar` styles: label left, horizontal bar with percentage fill, value right
- [ ] 1.16 — Add `.rpt-section-title`: `font-size:13px; font-weight:700; margin-bottom:10px; display:flex; align-items:center; gap:6px`
- [ ] 1.17 — Add mobile `@media (max-width:480px)` breakpoint:
  - `.rpt-stats-grid` → `grid-template-columns:1fr` (1 column)
  - `.rpt-gauges` → `flex-direction:column`
  - `.rpt-top3-row` → horizontal scroll with `flex-wrap:nowrap; -webkit-overflow-scrolling:touch`
  - `.rpt-top3-card` → `min-width:180px`
  - `.report-card` → `padding:20px 14px`
- [ ] 1.18 — Remove old mobile override at line ~6424 (`.report-card{width:95vw;padding:24px 16px}`)
- [ ] 1.19 — Keep `.report-overlay` and `.report-overlay.show` unchanged
- [ ] 1.20 — Keep `.report-btn` and `.report-btn:hover` unchanged

**Verify:** Open game, trigger report (fast-forward or cheat), confirm card renders centered with correct max-width. Check mobile using browser devtools at 375px width.

**Commit:** `feat(game): add report card grid CSS — 3-col gauges, 2x2 stats, coaching card styles`

---

## Task 2: Create SKMS_COACHING Data Array

**What:** Replace `SKMS_INSIGHTS` (lines 644-685) with `SKMS_COACHING` array. New schema provides principle-tagged coaching quotes for the DNA analysis and coaching cards.

**Changes:**
- [ ] 2.1 — Define `SKMS_COACHING` array right after the `EVENTS` array (replacing `SKMS_INSIGHTS` at same location)
- [ ] 2.2 — Schema per entry: `{principle: string, quote: string, source: string, context: string}`
  - `principle`: one of `'human_centered'`, `'supex'`, `'vwbe'`, `'social_value'`, `'rational'`
  - `quote`: SKMS 원문 인용 (Korean)
  - `source`: 출처 (e.g., `'SKMS 14차 개정판, VWBE 문화'`)
  - `context`: 한 단어 키워드 for matching (e.g., `'번아웃'`, `'패자부활'`, `'인재육성'`)
- [ ] 2.3 — Add **human_centered** entries (5):
  - 구성원 행복 / 패자부활 기회 / 인간존중 / 자율성 / 복지
- [ ] 2.4 — Add **supex** entries (5):
  - SUPEX 추구 / 성과 탁월성 / 목표 설정 / 도전적 성과 / 성과 보상
- [ ] 2.5 — Add **vwbe** entries (5):
  - 자발적 두뇌활용 / 역량 개발 / 리스킬링 / 학습 조직 / 자기주도
- [ ] 2.6 — Add **social_value** entries (3):
  - 이해관계자 행복 / ESG / 사회적 책임
- [ ] 2.7 — Add **rational** entries (3):
  - 합리적 의사결정 / 데이터 기반 / 투명 경영
- [ ] 2.8 — Delete old `SKMS_INSIGHTS` array entirely (lines 641-685)
- [ ] 2.9 — Add comment header: `// SKMS COACHING DATA FOR ENDING REPORT`

**Verify:** No JS errors on page load. `typeof SKMS_COACHING` returns `'object'` in console. Array length 21.

**Commit:** `feat(game): add SKMS_COACHING data array — 21 principle-tagged quotes replacing SKMS_INSIGHTS`

---

## Task 3: Rewrite calcSKMSAlignment() — Tag-Based Calculation

**What:** Replace the current policy-count-based `calcSKMSAlignment()` (lines 4914-4927) with a new function that calculates alignment from `G.skmsChoices` tags.

**Changes:**
- [ ] 3.1 — New `calcSKMSAlignment()` function:
  ```
  If G.skmsChoices exists and has entries:
    - Count choices per principle tag
    - Each principle contributes 20% (5 principles = 100%)
    - Per principle score = (count_for_principle / total_choices) * 100
    - Overall alignment = weighted average across 5 principles, capped at 100
    - Bonus: +5 per active policy (up to +30), -5 per ignoreCount
  Else (fallback for pre-Sub-1 compatibility):
    - Use old calculation (policy count * 10, empHap bonus, etc.)
  ```
- [ ] 3.2 — Add new helper `calcDNABreakdown()` that returns `{human_centered: N, supex: N, vwbe: N, social_value: N, rational: N}` as percentages (0-100 each)
  - Logic: count `G.skmsChoices` entries per tag, normalize to 0-100 scale
  - If no choices, return all zeros
  - Used by both the alignment calculation and the DNA radar display
- [ ] 3.3 — Ensure `clamp(0, 100, score)` still used on final result
- [ ] 3.4 — Keep `getManagementStyle()` unchanged (it uses G.empHap/custSat/socVal/policies, not skmsChoices)

**Verify:** Console-test with mock `G.skmsChoices = [{tag:'human_centered'},{tag:'supex'},{tag:'vwbe'}]`, confirm `calcSKMSAlignment()` returns reasonable value. Also verify fallback when `G.skmsChoices` is empty/undefined.

**Commit:** `feat(game): rewrite calcSKMSAlignment — tag-based calculation with DNA breakdown`

---

## Task 4: Rewrite showReport() — Header Card

**What:** Replace the title/subtitle/style section (lines 4430-4463) with a single full-width header card.

**Changes:**
- [ ] 4.1 — Keep initial setup: `stopBGM()`, sound effects, overlay clear, card element creation
- [ ] 4.2 — Create `.rpt-header` div containing:
  - Row 1: Win/Lose icon + "경영 성적표" title + star rating (`G.rating.toFixed(1) + ' ⭐'`) + "Day " + `G.gDay`
  - Row 2: Management style badge (from `getManagementStyle()`) + "SKMS 정합성 " + `calcSKMSAlignment()` + "%"
- [ ] 4.3 — Star rating: inline with title, right-aligned
- [ ] 4.4 — Day count: small text, right side of row 1
- [ ] 4.5 — Style badge: `display:inline-block; padding:4px 14px; border-radius:12px; background:rgba(255,184,48,0.15); color:#FFB830`
- [ ] 4.6 — Win state: green tint header border-top `3px solid #4ade80`; Lose state: red tint `3px solid #f87171`

**Verify:** Trigger report in win and lose states. Header shows all 5 data points in compact layout.

**Commit:** `feat(game): report header card — win/lose, rating, style, alignment, day count`

---

## Task 5: Rewrite Stakeholder Section — 3-Column Horizontal Gauges

**What:** Replace vertical bar list (lines 4466-4474) with 3 side-by-side gauge columns.

**Changes:**
- [ ] 5.1 — Create `.rpt-gauges` container with 3 `.rpt-gauge-col` children
- [ ] 5.2 — Each column: emoji icon + label on top, horizontal bar in middle, value number below
  - 고객: `👥`, color `var(--cust)` or `#42A5F5`, value `Math.round(G.custSat)`
  - 직원: `💚`, color `var(--emp)` or `#66BB6A`, value `Math.round(G.empHap)`
  - 사회: `🌍`, color `var(--soc)` or `#26A69A`, value `Math.round(G.socVal)`
- [ ] 5.3 — Bar: height `10px`, border-radius `5px`, background `rgba(255,255,255,0.08)`, fill width = `value%`
- [ ] 5.4 — Value: `font-size:20px; font-weight:800` centered below bar
- [ ] 5.5 — Section title: "이해관계자 균형" with emoji

**Verify:** Three columns render horizontally on desktop, stack vertically on 375px mobile.

**Commit:** `feat(game): report stakeholder gauges — 3-column horizontal layout`

---

## Task 6: Rewrite Employee Changes — 2x2 Card Grid

**What:** Replace the 4-row text list (lines 4477-4486) with a 2x2 grid of stat cards with big numbers.

**Changes:**
- [ ] 6.1 — Create `.rpt-stats-grid` container
- [ ] 6.2 — Four `.rpt-stat-card` children:
  - **에이스 전환**: icon `🔥`, value `G.totalAceTransitions`, label `에이스 전환`, always green (`#4ade80`) if > 0
  - **시니크 회복**: icon `😒→🔥`, value `G.totalCynicRecoveries`, label `회복`, green if > 0
  - **리더 육성**: icon `⭐`, value `G.totalLeaderPromotions`, label `리더 육성`, green if > 0
  - **퇴사**: icon `👋`, value `G.totalQuits`, label `퇴사`, red (`#f87171`) if > 0, neutral if 0
- [ ] 6.3 — Number display: `font-size:24px; font-weight:800` with "명" suffix in smaller text
- [ ] 6.4 — Color coding: use `.num-up` for positive metrics, `.num-down` for 퇴사, `.num-neutral` for zero values
- [ ] 6.5 — Section title: "구성원 변화"

**Verify:** Four cards in 2x2 grid. Numbers render large with correct colors. On mobile, 1-column stack.

**Commit:** `feat(game): report employee stats — 2x2 card grid with color-coded numbers`

---

## Task 7: Add TOP 3 Choices Section

**What:** New section showing the 3 most impactful player choices as horizontal cards.

**Changes:**
- [ ] 7.1 — Add helper `getTop3Choices()`:
  - Iterate `G.choiceLog` entries
  - For each entry, look up the event in `EVENTS` by `event` id
  - Score impact by counting the choice's `apply` function effects (estimate from `preview` text: sum absolute values of numeric effects mentioned)
  - Simple heuristic: choices with more `G.` mutations = higher impact, or use order (later events = more dramatic)
  - Fallback: if < 3 logged choices, show what's available; if 0, hide section entirely
- [ ] 7.2 — Simpler alternative impact scoring (recommended): use index position — later choices in `choiceLog` tend to be more impactful, but prefer choices where `choice !== 'auto'` (player actually chose)
- [ ] 7.3 — Create `.rpt-top3-row` container with up to 3 `.rpt-top3-card` children
- [ ] 7.4 — Each card shows:
  - Event headline (truncated to ~20 chars)
  - Choice text (from `EVENTS[id].choices[choiceIdx].text`)
  - Key effect preview (first line of `preview` field, truncated)
- [ ] 7.5 — Handle `choice === 'auto'` entries: show "시간 초과" in muted text
- [ ] 7.6 — Section title: "핵심 선택 TOP 3" with `🎯` icon
- [ ] 7.7 — Mobile: horizontal scroll with `-webkit-overflow-scrolling:touch`

**Verify:** Play through 3+ events, trigger report. Three cards show with event names and choices. Scroll works on mobile.

**Commit:** `feat(game): report TOP 3 choices section — horizontal impact cards`

---

## Task 8: Build SKMS Coaching Section

**What:** The main new feature — rich SKMS coaching feedback with DNA analysis, 잘한점, 아쉬운점, 다음시도.

**Changes:**
- [ ] 8.1 — Create coaching section container with title "📖 SKMS 경영 코칭"
- [ ] 8.2 — **DNA Analysis sub-card** ("🎯 당신의 경영 DNA"):
  - Call `calcDNABreakdown()` to get 5-principle percentages
  - Determine dominant style name from highest 1-2 principles (e.g., "인간중심 성장형")
  - DNA style name mapping: pick top 2 principles → combine Korean labels
    - `human_centered` = "인간중심", `supex` = "성과추구", `vwbe` = "자기주도", `social_value` = "사회가치", `rational` = "합리경영"
  - Render 5 horizontal bars (`.rpt-dna-bar`): label + bar fill + percentage text
  - Bar colors: `human_centered=#4ade80, supex=#f59e0b, vwbe=#60a5fa, social_value=#26A69A, rational=#a78bfa`
- [ ] 8.3 — **잘한 점 card** (`.coaching-good`):
  - Find best SKMS-aligned choice: filter `G.choiceLog` for entries with `skmsTag`, pick one with positive effects
  - If `G.skmsChoices` not available, fallback: show generic positive feedback if `G.empHap >= 60`
  - Display: event headline → chosen option text → short-term / long-term effect summary
  - Add matching SKMS quote from `SKMS_COACHING` (filter by principle tag)
  - Show source in `.rpt-source`
- [ ] 8.4 — **아쉬운 점 card** (`.coaching-bad`):
  - Find worst choice: entry with `choice === 'auto'` (timeout) or known negative patterns (pressureCount, ignoreCount)
  - If no bad choices found, show generic "아쉬운 점이 없습니다" in muted text
  - Display: event headline → choice text → negative impact
  - Add "💡" suggestion: what facility/policy could have unlocked a better option
  - Add SKMS quote for the violated principle
- [ ] 8.5 — **다음에 시도해보세요 card** (`.coaching-next`):
  - Determine weakest metric: `Math.min(G.custSat, G.empHap, G.socVal)` → which one
  - Map to recommended department + policy combo:
    - Low custSat → "R&D 부서 + 고객중심 정책"
    - Low empHap → "HR 부서 + VWBE 정책 + Wellness 시설"
    - Low socVal → "Social Impact 부서 + 사회적 가치 경영 정책"
  - If DNA breakdown shows a principle below 20% → mention it as area to explore
- [ ] 8.6 — Handle edge cases:
  - No events experienced (very short game): show simplified feedback
  - All metrics high: show congratulatory "다음에 시도" suggesting harder scenario
  - No `G.skmsChoices` (pre-Sub-1): fall back to old `SKMS_INSIGHTS`-style display

**Verify:** Play full game with varied choices. Coaching section shows DNA bars, 잘한점 with quote, 아쉬운점 with suggestion, 다음시도 with specific recommendation. Test with 0 events case.

**Commit:** `feat(game): SKMS coaching section — DNA radar, 잘한점/아쉬운점/다음시도 cards`

---

## Task 9: Update Share/Copy Functions for New Layout

**What:** Update `getReportText()`, `captureReport()`, `shareTwitter()`, `shareLinkedIn()` to reflect new report structure.

**Changes:**
- [ ] 9.1 — Update `getReportText()` to include:
  - Win/lose + style + SKMS alignment + rating + day count (existing, keep)
  - DNA top principle name (new)
  - TOP 3 choice headlines (new)
  - Format: compact for Twitter (280 char limit)
- [ ] 9.2 — Rewrite `captureReport()` canvas rendering:
  - Match new card grid layout in canvas draw
  - Header section with win/lose + rating + alignment
  - 3-column gauge bars
  - 2x2 stat boxes
  - DNA bars (simplified — just the top 2 principles as text)
  - SKMS quote at bottom
  - Watermark
- [ ] 9.3 — Alternatively (simpler): use `html2canvas` CDN for pixel-perfect capture
  - Add `<script src="https://html2canvas.hertzen.com/dist/html2canvas.min.js">` in head
  - Replace manual canvas code with `html2canvas(cardEl).then(canvas => { ... })`
  - Fallback: if html2canvas not loaded, show "이미지 저장 기능을 사용할 수 없습니다" toast
- [ ] 9.4 — If keeping manual canvas: at minimum update dimensions (`cw = 700` instead of `480`) and add new sections
- [ ] 9.5 — Update `shareTwitter()` and `shareLinkedIn()` — no structural changes needed, they use `getReportText()`

**Verify:** Click "이미지 저장" — downloads PNG matching visual report. Click "텍스트 복사" — clipboard text includes DNA and TOP 3 info. Twitter/LinkedIn share opens correctly.

**Commit:** `feat(game): update share/copy functions for new report layout`

---

## Task 10: Clean Up Old Report Code

**What:** Remove deprecated functions and CSS that are no longer referenced.

**Changes:**
- [ ] 10.1 — Delete `addReportRow()` function (lines 4859-4870)
- [ ] 10.2 — Delete `addReportBar()` function (lines 4872-4894)
- [ ] 10.3 — Delete `addReportCheck()` function (lines 4896-4902)
- [ ] 10.4 — Remove old CSS classes no longer used: `.report-row`, `.report-check`, `.report-quote`, `.skms-verdict`, `.skms-quote`, `.choice-log-item`, `.choice-log-event`, `.choice-log-choice`
- [ ] 10.5 — Remove old "인재 관리 분석" section from showReport (people management analysis is superseded by coaching section)
- [ ] 10.6 — Remove old "선택 vs SKMS" checklist section (replaced by coaching cards)
- [ ] 10.7 — Remove old "당신의 선택이 만든 결과" log section (replaced by TOP 3 cards)
- [ ] 10.8 — Remove old "SKMS 경영철학 피드백" section that used `SKMS_INSIGHTS` (replaced by coaching)
- [ ] 10.9 — Remove old SKMS quote block at bottom (integrated into coaching cards)
- [ ] 10.10 — Verify no remaining references to deleted functions (search for `addReportRow`, `addReportBar`, `addReportCheck`, `SKMS_INSIGHTS` in file)
- [ ] 10.11 — Verify total line count reduction: old report ~274 lines → new should be similar or slightly larger due to coaching complexity, but CSS should be cleaner

**Verify:** Full search for orphaned references. Game loads without errors. Report renders completely.

**Commit:** `refactor(game): remove old report helpers and CSS — addReportRow/Bar/Check, SKMS_INSIGHTS`

---

## Verification Checklist

After all 10 tasks:

- [ ] Game loads without JS errors
- [ ] Report triggers correctly on win (all 3 gauges sustained) and lose (bankrupt / metrics collapse)
- [ ] Header card shows: icon, title, star rating, day count, style badge, SKMS alignment %
- [ ] 3-column gauges render with correct colors and values
- [ ] 2x2 stat grid shows 4 metrics with correct color coding
- [ ] TOP 3 section shows actual player choices (or hides if < 1 choice)
- [ ] Coaching DNA shows 5 principle bars with percentages
- [ ] 잘한 점 card has green left border, SKMS quote, source
- [ ] 아쉬운 점 card has amber left border, suggestion with 💡
- [ ] 다음 시도 card has blue left border, specific dept+policy recommendation
- [ ] Share buttons work: Twitter, LinkedIn, copy, image save
- [ ] Mobile (375px): 2-col → 1-col, TOP3 horizontal scroll, gauges stack
- [ ] No orphaned CSS classes or JS functions
- [ ] `calcSKMSAlignment()` works with and without `G.skmsChoices` (backward compat)

## Estimated Size

- **CSS**: ~60 new lines (replacing ~21)
- **SKMS_COACHING data**: ~100 lines (replacing ~42)
- **showReport() rewrite**: ~280 lines (replacing ~274)
- **calcSKMSAlignment() + calcDNABreakdown()**: ~40 lines (replacing ~14)
- **getTop3Choices()**: ~30 new lines
- **Share function updates**: ~20 lines modified
- **Removed code**: ~80 lines (old helpers + old CSS)
- **Net change**: +150 lines approximately
