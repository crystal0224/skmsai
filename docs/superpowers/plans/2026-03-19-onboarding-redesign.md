# Onboarding Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the 2-page onboarding in SKMS Company Builder to show a dramatic Before→SKMS→After diverging paths layout (page 1) and scenario-dominant selection (page 2), with enhanced animations, particles, and onboarding BGM.

**Architecture:** Single-file change to `public/parktycoon.html`. Replace `showOnboarding()` contents while preserving its structure (slides array, navigation, save/continue). Existing `drawIsoChar()` is reused across multiple canvases. New CSS keyframes added to the `<style>` block. New `startOnboardingBGM()` function added alongside existing BGM system.

**Tech Stack:** Vanilla JS, Canvas 2D API, CSS keyframes, Web Audio API (procedural BGM)

**Spec:** `docs/superpowers/specs/2026-03-19-onboarding-redesign-design.md`

**Security note:** This file is a standalone game HTML. All scenario card content is hardcoded developer strings (not user input). DOM construction uses `textContent` for text and `createElement`/`appendChild` for structure. The only `innerHTML` usage is for the SKMS copy line with `<br>` and `<span>` tags — these are static developer strings with no user input path.

---

### Task 1: Add new CSS styles for onboarding redesign

**Files:**
- Modify: `public/parktycoon.html:195-247` (CSS `<style>` block, onboarding section)

- [ ] **Step 1: Add new keyframes and layout classes**

After the existing `@keyframes glowPulse` (line 202), add:

```css
@keyframes skms-pulse{0%,100%{box-shadow:0 0 20px rgba(0,82,162,0.2)}50%{box-shadow:0 0 40px rgba(0,82,162,0.5)}}
@keyframes fadeInUp{from{transform:translateY(20px);opacity:0}to{transform:translateY(0);opacity:1}}
@keyframes bounceIn{0%{transform:translateY(30px);opacity:0}60%{transform:translateY(-6px);opacity:1}100%{transform:translateY(0)}}
@keyframes shakeIn{0%{transform:translateX(-8px);opacity:0}25%{transform:translateX(6px)}50%{transform:translateX(-4px);opacity:1}75%{transform:translateX(2px)}100%{transform:translateX(0)}}
@keyframes twinkle{0%,100%{opacity:0}50%{opacity:1}}
.slide1-layout{display:flex;align-items:center;justify-content:center;gap:16px;width:100%;position:relative;padding:8px 0}
.skms-panel{width:150px;flex:0 0 auto;background:linear-gradient(180deg,#0f172a,#1e293b);border-radius:14px;padding:16px 12px;border:2px solid rgba(96,165,250,0.4);text-align:center;animation:skms-pulse 2.5s infinite}
.after-area{width:140px;flex:0 0 auto;display:flex;flex-direction:column;gap:8px}
.success-path{background:rgba(34,197,94,0.08);border:1.5px solid rgba(34,197,94,0.25);border-radius:10px;padding:8px;text-align:center}
.failure-path{background:rgba(220,38,38,0.06);border:1.5px solid rgba(220,38,38,0.15);border-radius:10px;padding:8px;text-align:center}
.sc-card-new{flex:1;padding:20px;border-radius:12px;border:2px solid #E2E8F0;background:#FAFAFA;cursor:pointer;transition:all .2s ease-out;display:flex;flex-direction:column;align-items:center;gap:8px}
.sc-card-new:hover{transform:translateY(-3px);box-shadow:0 8px 24px rgba(0,0,0,0.08)}
.sc-card-new.active{border-color:#0052A2;background:linear-gradient(135deg,#EBF2FA,#F0F7FF);box-shadow:0 4px 20px rgba(0,82,162,0.12)}
.play-strip{display:flex;align-items:center;gap:12px;padding:8px 14px;border-radius:8px;background:rgba(0,82,162,0.04);border:1px solid rgba(0,82,162,0.08);margin-top:8px}
.play-strip .strip-label{font-size:10px;font-weight:800;color:#0052A2;white-space:nowrap}
.play-strip .strip-steps{display:flex;gap:6px;flex:1;justify-content:center;align-items:center}
.play-strip .strip-chip{background:rgba(0,82,162,0.06);padding:5px 10px;border-radius:5px;font-size:9px;color:#4B5563}
.play-strip .strip-arrow{color:#94A3B8;font-size:12px}
.difficulty-badge{margin-top:4px;padding:3px 10px;border-radius:5px;font-size:9px;font-weight:600}
```

- [ ] **Step 2: Add mobile responsive overrides**

After the existing mobile `@media` onboard rules (line 295), add:

```css
@media(max-width:768px){
  .slide1-layout{flex-direction:column;gap:12px}
  .skms-panel{width:90%}
  .after-area{width:90%;flex-direction:row}
  .success-path,.failure-path{flex:1}
}
```

- [ ] **Step 3: Verify CSS parses — open file in browser**

Open `public/parktycoon.html` in browser, check no CSS parse errors in DevTools console.

- [ ] **Step 4: Commit**

```bash
git add public/parktycoon.html
git commit -m "feat(onboarding): add CSS for redesigned layout, keyframes, scenario cards"
```

---

### Task 2: Add onboarding BGM function

**Files:**
- Modify: `public/parktycoon.html:997` (after `stopBGM()` function)

- [ ] **Step 1: Add `startOnboardingBGM()` and `stopOnboardingBGM()` functions**

Insert after `function stopBGM()` (line 997):

```javascript
// --- Onboarding BGM (slower, dreamier) ---
var onbBgmActive = false, onbBgmTimer = null;
function startOnboardingBGM() {
  if (!G.audioCtx || onbBgmActive) return;
  onbBgmActive = true;
  var chords = [
    [261, 329, 392, 494],  // Cmaj7
    [349, 440, 523, 659],  // Fmaj7
    [220, 261, 329, 392],  // Am7
    [196, 247, 294, 392],  // G
  ];
  var ci = 0, ni = 0;
  function playNote() {
    if (!onbBgmActive) return;
    var chord = chords[ci];
    var note = chord[ni % chord.length];
    if (G.audioCtx) {
      var o = G.audioCtx.createOscillator();
      var g = G.audioCtx.createGain();
      o.type = 'sine';
      o.frequency.value = note;
      g.gain.setValueAtTime(0.012, G.audioCtx.currentTime);
      g.gain.exponentialRampToValueAtTime(0.001, G.audioCtx.currentTime + 1.8);
      o.connect(g); g.connect(G.audioCtx.destination);
      o.start(); o.stop(G.audioCtx.currentTime + 1.8);
      // Dreamy pad (octave below, very quiet)
      var o2 = G.audioCtx.createOscillator();
      var g2 = G.audioCtx.createGain();
      o2.type = 'sine';
      o2.frequency.value = note / 2;
      g2.gain.setValueAtTime(0.006, G.audioCtx.currentTime);
      g2.gain.exponentialRampToValueAtTime(0.001, G.audioCtx.currentTime + 2.5);
      o2.connect(g2); g2.connect(G.audioCtx.destination);
      o2.start(); o2.stop(G.audioCtx.currentTime + 2.5);
    }
    ni++;
    if (ni >= chord.length) { ni = 0; ci = (ci + 1) % chords.length; }
    onbBgmTimer = setTimeout(playNote, 600 + Math.random() * 150);
  }
  playNote();
}
function stopOnboardingBGM() { onbBgmActive = false; if (onbBgmTimer) clearTimeout(onbBgmTimer); }
```

- [ ] **Step 2: Verify no syntax errors**

Open browser, check console. The functions exist but are not called yet.

- [ ] **Step 3: Commit**

```bash
git add public/parktycoon.html
git commit -m "feat(onboarding): add dreamy onboarding BGM (slower tempo, lower volume)"
```

---

### Task 3: Rewrite Slide 1 — Before / SKMS / After diverging paths

**Files:**
- Modify: `public/parktycoon.html:5340-5620` (inside `showOnboarding()`, Slide 1 section)

This is the largest task. Replace the existing Slide 1 content (canvas preview + scenario cards) with the new 3-column layout.

- [ ] **Step 1: Define character data sets (replace leftChars/rightChars)**

Replace the existing `leftChars` and `rightChars` arrays (lines ~5351-5360) with three sets:

```javascript
var beforeChars = [
  {col:'#BDBDBD',size:0.7,label:'무기력',bubble:'매일 똑같은 하루...'},
  {col:'#78909C',size:0.9,label:'냉소파',bubble:'해봤자 달라지는 건 없어'},
  {col:'#66BB6A',size:0.6,label:'신입',bubble:'뭐부터 해야 할지...'}
];
var successChars = [
  {col:'#66BB6A',size:0.8,label:'회복',bubble:'다시 해볼게요!'},
  {col:'#FF7043',size:1.0,label:'에이스',bubble:'성과 내고 있어요!'},
  {col:'#FFD54F',size:1.2,label:'리더',bubble:'SUPEX 추구!'}
];
var failChars = [
  {col:'#BDBDBD',size:0.5,label:'퇴사',bubble:'더는 못하겠어요...'},
  {col:'#9E9E9E',size:0.4,label:'잔류',bubble:'...'}
];
```

- [ ] **Step 2: Build the 3-column Slide 1 DOM structure**

Replace the existing Slide 1 build code (from `var s1 = document.createElement('div')` through `slides.push(s1)`, which includes `previewLabel`, `previewWrap`, `scenarioLabel`, and `scenarios`) with the new 3-column flexbox layout:

Build order:
1. `s1` div with class `onboard-slide active`
2. Label: "🎮 SKMS 경영이 만드는 변화"
3. `layout` div with class `slide1-layout`
4. Before column: `beforeWrap` div containing title "BEFORE", subtitle "무기력한 조직", and `beforeCanvas` (280x340, background `rgba(254,226,226,0.5)`)
5. SKMS panel: `skmsPanel` div with class `skms-panel` containing "⚡ YOUR TURN" header (#FFD54F), "SKMS" title (#60a5fa, 18px), 🎮 icon (28px), and copy text "당신의 경영이 [운명] 을 바꿉니다" (운명 in #FFD54F, 15px). Use safe DOM building — create a text node for "당신의 경영이", a `<br>`, a `<span>` with textContent "운명" styled gold, and another text node "을 바꿉니다".
6. After area: `afterArea` div with class `after-area` containing:
   - `successDiv` (class `success-path`): title "✅ SUPEX 달성" (#22c55e), `successCanvas` (140x130), label "직원 행복 + 성과 📈"
   - `failDiv` (class `failure-path`): title "❌ 경영 실패" (#ef4444), `failCanvas` (140x130), label "이직 러시 + 파산 💀"
7. SVG overlay: `arrowSvg` with `position:absolute;inset:0;pointer-events:none`
8. Append all to `s1`, push to `slides`

Get canvas contexts: `beforeCtx`, `successCtx`, `failCtx`.

- [ ] **Step 3: Replace `drawPreview()` with new multi-canvas render loop**

Replace the existing `drawPreview()` function with three separate draw functions:

**`drawBeforeCanvas()`**: Clears `beforeCtx`, draws red-tinted particles (zone='before'), draws `beforeChars` using `drawIsoChar(beforeCtx, ...)`, draws decline line (polyline from y=240 to y=262) and 📉 label.

**`drawSuccessCanvas()`**: Clears `successCtx`, draws green/gold particles (zone='success'), draws `successChars` using `drawIsoChar(successCtx, ...)`, draws twinkle stars near leader (every 90 frames, 30-frame burst, sine-based alpha).

**`drawFailCanvas()`**: Clears `failCtx`, draws falling dust particles (zone='fail', reversed vy for downward drift), draws `failChars` using `drawIsoChar(failCtx, ...)`.

**`drawPreview()`**: Calls all three, increments `previewFrame` and `speakTimer`, cycles `speakingIdx` over 8 characters (3+3+2).

**Particle system**: Initialize 20 particles, each with `{x, y, vx, vy, size, opacity, zone}`. Zones: 8 'before', 6 'success', 6 'fail'. Particles wrap around canvas edges.

- [ ] **Step 4: Update `drawIsoChar` to accept context parameter (DO THIS BEFORE Steps 2-3)**

**Important:** This step must be done first, before replacing Slide 1 content. Steps 1-5 are atomic — do not test between individual steps; test after all are complete.

Change function signature from `drawIsoChar(cx, cy, ch, isSpeaking, isDark)` to `drawIsoChar(ctx, cx, cy, ch, isSpeaking, isDark)`.

Inside the function body:
- Replace all `pCtx` references with `ctx` (~30 occurrences)
- Replace `previewCanvas.width` with `ctx.canvas.width`
- Replace `previewCanvas.height` with `ctx.canvas.height`

- [ ] **Step 4b: Verify no stale references remain**

Search entire file for `pCtx`, `previewCanvas`, and `previewWrap`. After the full rewrite (Steps 1-5), NONE of these should remain. The old standalone `startBtn` click handler (line ~5797) is also removed — it's replaced by `startNewGame()` called via the nav button.

- [ ] **Step 5: Add SVG arrows after layout renders**

Use `setTimeout(fn, 100)` to allow DOM layout to compute positions, then:
1. Get `getBoundingClientRect()` for `layout`, `skmsPanel`, `beforeWrap`, `successDiv`, `failDiv`
2. Calculate relative coordinates (subtract layout rect origin)
3. Create SVG `<defs>` with three markers: `arrG` (#22c55e), `arrR` (#ef4444), `arrW` (#64748b)
4. Draw `<line>` from Before right edge to SKMS left edge (dashed, #64748b, marker-end arrW)
5. Draw `<path>` quadratic curve from SKMS right to Success center (green, marker-end arrG)
6. Draw `<path>` quadratic curve from SKMS right to Failure center (red, marker-end arrR)
7. Set SVG `viewBox` to layout dimensions

- [ ] **Step 6: Visually verify Slide 1**

Open in browser — onboarding should show:
- Before (left): 3 gray characters with speech bubbles cycling, red particles, decline line
- SKMS (center): pulsing blue panel with "YOUR TURN" / 🎮 / "운명을 바꿉니다"
- After (right-top): 3 colorful characters, green/gold particles, twinkle stars
- After (right-bottom): 2 faded characters, dust particles falling
- SVG arrows connecting them

- [ ] **Step 7: Commit**

```bash
git add public/parktycoon.html
git commit -m "feat(onboarding): page 1 — diverging paths with multi-canvas, particles, SVG arrows"
```

---

### Task 4: Rewrite Slide 2 — Scenario cards + play strip

**Files:**
- Modify: `public/parktycoon.html` (inside `showOnboarding()`, Slide 2 section, lines ~5833-5900)

- [ ] **Step 1: Replace Slide 2 content**

Replace the existing Slide 2 build code (from `var s2 = document.createElement('div')` through `slides.push(s2)`, which includes the 3-step flow with `steps` array and flow div building loop) with:

1. `s2` div, class `onboard-slide`
2. Title: "📋 시나리오를 선택하세요" (16px bold, centered)
3. `scRow` flex container (gap:12px)
4. **Scenario 1 card** (`sc1`, class `sc-card-new active`): Build with createElement — inline `style.background = 'linear-gradient(180deg, rgba(248,113,113,0.12), rgba(248,113,113,0.04))'`, 🔥 icon (32px div), title "위기의 회사" (#f87171, 13px bold), description "무너져가는 회사의 CEO로 부임하여 조직을 살려라!" (10px), difficulty badge "난이도: ★★★" (red-tinted). All text via `textContent`.
5. **Scenario 2 card** (`sc2`, class `sc-card-new`): inline `style.background = 'linear-gradient(180deg, rgba(96,165,250,0.12), rgba(96,165,250,0.04))'`, 🤖 icon, title "AI 혁신 시대" (#60a5fa), description "안정된 회사에 AI 혁신을 도입하여 초일류 기업으로!", difficulty "난이도: ★★☆" (blue-tinted).
6. **Play strip**: div class `play-strip` with `strip-label` "🎮 플레이" + `strip-steps` containing chips "① 조직 세우고", "② 사람 키우고", "③ 위기 넘기세요" separated by "→" arrows.
7. `selectScenario(num)` function: toggles `sc1`/`sc2` active class.
8. Click listeners on `sc1` and `sc2`.

- [ ] **Step 2: Visually verify Slide 2**

Navigate to page 2 — should show:
- Two large scenario cards with difficulty badges
- Bottom play strip
- Card click toggles active state

- [ ] **Step 3: Commit**

```bash
git add public/parktycoon.html
git commit -m "feat(onboarding): page 2 — scenario-dominant cards with play strip"
```

---

### Task 5: Wire up onboarding BGM + overlay click handler

**Files:**
- Modify: `public/parktycoon.html` (inside `showOnboarding()`, overlay setup and start button handlers)

- [ ] **Step 1: Add BGM trigger on first overlay interaction**

At the top of `showOnboarding()`, after the overlay clear logic (line ~5316), add:

```javascript
// BGM: start on first user interaction (browser autoplay policy)
var onbBgmStarted = false;
function tryStartOnbBGM() {
  if (onbBgmStarted) return;
  onbBgmStarted = true;
  initAudio();
  startOnboardingBGM();
  overlay.removeEventListener('click', tryStartOnbBGM);
  overlay.removeEventListener('touchstart', tryStartOnbBGM);
}
overlay.addEventListener('click', tryStartOnbBGM);
overlay.addEventListener('touchstart', tryStartOnbBGM);
```

- [ ] **Step 2: Stop onboarding BGM in all start/continue handlers**

In the `startNewGame()` function, add `stopOnboardingBGM();` before `startBGM();`.

Same for `continueBtn`, `pendingContBtn`, and `navContBtn` click handlers — add `stopOnboardingBGM();` before each `startBGM();` call.

**Note:** The old standalone `startBtn` (line ~5797) is removed during the Slide 1/2 rewrite — its functionality is replaced by `startNewGame()` called via the nav `nextBtn` on the last slide. Verify `startBtn` no longer exists after Tasks 3-4.

- [ ] **Step 3: Verify BGM plays**

Open in browser:
1. Click anywhere on onboarding overlay → dreamy ambient notes start (slower than game BGM)
2. Click "경영 시작" → BGM transitions to normal game tempo
3. Click "이어하기" (if save exists) → same BGM transition

- [ ] **Step 4: Commit**

```bash
git add public/parktycoon.html
git commit -m "feat(onboarding): onboarding BGM starts on first click, transitions to game BGM"
```

---

### Task 6: Verify clean replacement and test all flows

**Files:**
- Modify: `public/parktycoon.html` (verify no dead code remains)

**Note:** Tasks 3-4 perform full replacements (not additions alongside old code), so most old code is already gone. This task verifies completeness.

- [ ] **Step 1: Search for stale references**

Search the file for: `pCtx`, `previewCanvas`, `previewWrap`, `leftChars`, `rightChars`, `svg1`, `svg2`, `onboard-flow`. None of these should remain inside `showOnboarding()`. If any are found, delete them.

- [ ] **Step 2: Search for old startBtn**

Verify the old standalone `startBtn` (the one outside the nav system) is removed. The nav `nextBtn` calling `startNewGame()` is the only start path now.

- [ ] **Step 3: Verify all navigation flows work**

Test in browser:
1. Fresh load → Page 1 (diverging paths) → "다음" → Page 2 (scenarios) → "🎬 경영 시작!" → game starts with correct scenario
2. Page dots click → slides switch correctly
3. "이전" / "다음" works
4. Scenario selection persists across slide switches
5. Saved game: "이어하기" button loads saved state correctly

- [ ] **Step 4: Verify mobile layout**

DevTools → 375px viewport:
- Slide 1: 3-column stacks vertically
- Slide 2: scenario cards still side-by-side
- Navigation buttons accessible

- [ ] **Step 5: Commit**

```bash
git add public/parktycoon.html
git commit -m "refactor(onboarding): remove dead code from old onboarding layout"
```

---

### Task 7: Final polish — entrance animations

**Files:**
- Modify: `public/parktycoon.html` (inside `showOnboarding()`, animation timing)

- [ ] **Step 1: Add staggered entrance animations to Slide 1 elements**

After building the Slide 1 layout (before `slides.push(s1)`), set initial opacity 0 and CSS animation on each element:

- `beforeWrap`: `fadeInUp 0.8s ease-out 0.2s forwards`
- `skmsPanel`: `fadeInUp 0.6s ease-out 0.5s forwards, skms-pulse 2.5s 1.1s infinite`
- `successDiv`: `bounceIn 0.6s ease-out 0.8s forwards`
- `failDiv`: `shakeIn 0.6s ease-out 1.0s forwards`

- [ ] **Step 2: Add entrance animation to Slide 2 on navigation**

In the `goToSlide()` function, when `idx === 1` (Slide 2), re-trigger:
- `sc1`: `fadeInUp 0.4s ease-out 0.1s forwards`
- `sc2`: `fadeInUp 0.4s ease-out 0.2s forwards`
- `strip`: `fadeInUp 0.3s ease-out 0.4s forwards`

- [ ] **Step 3: Final visual check**

Open in browser:
- Page 1: Before fades in → SKMS slides up with pulse → Success bounces → Failure shakes
- Navigate to Page 2: Cards stagger in → strip fades last
- BGM plays throughout
- All particles animate smoothly
- No console errors

- [ ] **Step 4: Commit**

```bash
git add public/parktycoon.html
git commit -m "feat(onboarding): entrance animations — stagger, bounce, shake for dramatic reveal"
```

---

### Commit Summary

| # | Message | Content |
|---|---------|---------|
| 1 | `feat(onboarding): add CSS for redesigned layout` | New keyframes + layout classes |
| 2 | `feat(onboarding): add dreamy onboarding BGM` | `startOnboardingBGM()` function |
| 3 | `feat(onboarding): page 1 — diverging paths` | Multi-canvas, particles, SVG arrows |
| 4 | `feat(onboarding): page 2 — scenario cards + play strip` | New Slide 2 content |
| 5 | `feat(onboarding): onboarding BGM wiring` | Click handler, transition logic |
| 6 | `refactor(onboarding): remove dead code` | Clean up old layout code |
| 7 | `feat(onboarding): entrance animations` | Stagger, bounce, shake animations |
