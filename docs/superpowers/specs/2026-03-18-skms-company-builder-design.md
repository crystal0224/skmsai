# SKMS Company Builder — Design Spec

## Overview

Browser-based isometric simulation game where players build a company from scratch, placing departments and facilities on an isometric grid, hiring and developing employees with distinct personality types, activating management policies from the SKMS framework, and balancing three stakeholder metrics (customer satisfaction, employee happiness, social value).

**Entry point:** "PLAY" tab in main site navigation → `public/skms-builder.html` (full-screen, standalone HTML).

**Target audience:** SK Group employees and trainees learning SKMS management philosophy through interactive simulation.

**Core experience:** Players intuitively discover that short-term optimization of one stakeholder metric degrades others, and that SKMS policies (SUPEX, VWBE, etc.) are the tools that create sustainable balance — the central thesis of SKMS.

---

## Game Systems

### 1. Construction System

Isometric grid (40x40 tiles). Players place buildings via a bottom toolbar, ParkTycoon-style.

**Departments (6) — Revenue generators, require employees:**

| Department | Icon | Color | Cost | Revenue | Upkeep | Effect |
|---|---|---|---|---|---|---|
| Production | 🏭 | #FFB74D | $1500 | $30/tick | $8 | Core revenue, needs workers |
| R&D | 🔬 | #7E57C2 | $2500 | $15/tick | $12 | Innovation score ↑, unlocks advanced policies |
| Planning | 📊 | #42A5F5 | $1200 | $5/tick | $6 | +10% efficiency to adjacent departments |
| HR | 👥 | #66BB6A | $1000 | $0 | $5 | Recruitment speed ↑, turnover ↓ |
| Marketing | 📢 | #EF5350 | $1800 | $20/tick | $10 | Customer satisfaction direct boost |
| Social Impact | 🤝 | #26A69A | $2000 | $0 | $8 | Social value ↑, brand reputation |

**Facilities (4) — Support, no direct revenue:**

| Facility | Icon | Color | Cost | Upkeep | Effect |
|---|---|---|---|---|---|
| Cafeteria | 🍽 | #FFF3E0 | $600 | $3 | Employee happiness ↑, hunger reset |
| Wellness Center | 🏋 | #E8F5E9 | $800 | $4 | Employee happiness ↑, turnover ↓ |
| Training Academy | 📚 | #FFF9C4 | $1500 | $6 | Capability growth speed ↑ |
| Corridor | 🛤 | #D7CCC8 | $50 | $0 | Connects buildings, employees walk on these |

**Mechanics:**
- Snap-to-grid placement with green/red ghost preview
- Undo/Redo (Ctrl+Z / Ctrl+Shift+Z)
- Bulldoze tool returns 50% of building cost
- Departments must be adjacent to corridors to function
- Company HQ is pre-placed at grid center (entrance equivalent)

### 2. Employee AI (5 Types)

Employees are small circular characters that walk along corridors, enter departments, and display emotion emojis. Each has two core attributes: **Will (의욕)** and **Capability (역량)**, mapped to a 2x2 matrix plus one special type.

| Type | Will | Capability | Hire Cost | Traits |
|---|---|---|---|---|
| 🔥 Ace | High | High | $500 | Top performer, scout target, high flight risk without satisfaction |
| 🌱 Eager Rookie | High | Low | $150 | Cheap, grows fast with training. Neglect → drifts to Disengaged |
| 🧊 Cynic | Low | High | $350 | Skilled but unmotivated. VWBE culture or rewards → converts to Ace |
| 😴 Disengaged | Low | Low | $100 | Accumulates without management. Education + culture → recoverable |
| ⭐ Leader | Special | Special | $800 | Department head. Influences all employees in same department |

**Type transitions (core mechanic):**
- Training Academy + O.J.T policy: Rookie → Ace (capability growth)
- VWBE Culture + Wellness: Cynic → Ace (will recovery)
- No welfare + excessive pressure: Ace → Cynic (burnout)
- Neglect: Rookie → Disengaged (decay)
- Leader quality affects entire department's will modifier

**Behavior:**
- Spawn at HQ, pathfind (BFS) via corridors to assigned department
- Work timer → produce revenue based on type multiplier
- Visit cafeteria when hunger > threshold
- Show emotion emoji (happy/neutral/stressed/bored/excited) based on state
- Quit (walk to HQ and despawn) when happiness reaches 0

### 3. Stakeholder Balance (3 Metrics)

The central tension. Each metric ranges 0–100. Overall star rating = weighted average.

| Metric | Icon | Color | Boosted by | Damaged by |
|---|---|---|---|---|
| Customer Satisfaction | 👥 | #42A5F5 | Marketing, Production quality, Innovation | Neglecting product, poor reputation |
| Employee Happiness | 💚 | #66BB6A | Welfare, Culture policies, Fair pay, Leaders | Overwork, no facilities, poor leadership |
| Social Value | 🌍 | #26A69A | Social Impact dept, Ethics policy, Social Value Mgmt | Cost-cutting on social programs, scandals |

**Trade-off examples:**
- Maxing Production (overtime) → Customer ↑, Employee ↓
- Heavy Social Impact investment → Social ↑, short-term revenue ↓ → facilities suffer → Employee ↓
- Balanced approach with SKMS policies → all three rise slowly but sustainably

**Star Rating:** 1–5 stars, calculated from: `(customer + employee + social) / 60 + policy_bonus`

### 4. Management Policies (9, Research Tree)

Policies cost money and time to activate. Some have prerequisites. They provide passive bonuses and change how employees and events behave.

| Policy | Cost | Time | Prereq | Effect |
|---|---|---|---|---|
| Performance Rewards | $500 | 10s | — | Will ↑ for all, but excess → internal competition |
| O.J.T (On-the-Job Training) | $800 | 15s | — | Rookie capability growth 2x |
| Horizontal Communication | $600 | 12s | — | Innovation ↑, decision speed slightly ↓ |
| Coordination | $1000 | 20s | Planning dept | Adjacent department synergy +15% |
| SUPEX Pursuit | $2000 | 30s | R&D dept | Performance ceiling raised for all depts |
| VWBE Culture | $1500 | 25s | HR dept + Wellness | Cynic → Ace conversion rate ↑, voluntary engagement ↑ |
| Social Value Management | $1200 | 20s | Social Impact dept | Social metric growth 2x |
| Ethics Management | $1000 | 15s | — | Crisis event damage reduced 50% |
| SK-Manship | $3000 | 40s | SUPEX + VWBE | Ultimate policy: all metrics +10%, culture level max |

**UI:** Policies shown in a side panel as a simple tree. Activated policies glow. Locked ones show prerequisites.

### 5. Event System

Random events fire every 30–60 game-seconds. Each presents 2–3 choices with different stakeholder impacts. Active policies modify outcomes.

**Sample events:**

| Event | Choices | Policy modifier |
|---|---|---|
| "Key talent received outside offer" | A: Raise salary (cost ↑, employee ↑) / B: Let them go (morale ↓) / C: Counter with growth path (only if VWBE active) | VWBE: option C available |
| "Media reports quality issue" | A: PR response ($, customer ↓ small) / B: Full recall ($$$, customer ↑) / C: Ignore (customer ↓↓) | Ethics Mgmt: damage -50% |
| "Employee burnout wave" | A: Mandatory vacation (productivity ↓ temp) / B: Ignore (turnover ↑↑) | VWBE + Wellness: auto-mitigated |
| "Government social audit" | A: Pass easily (if Social Value > 60) / B: Scramble (cost ↑) / C: Fail (reputation ↓↓) | Social Value Mgmt: auto-pass |
| "Competitor price war" | A: Match prices (revenue ↓) / B: Differentiate (needs R&D + SUPEX) / C: Do nothing (customer ↓) | SUPEX: option B effective |

**UI:** Events appear as a centered modal card with choice buttons. 10-second timer for urgency (or dismiss to auto-pick worst option).

### 6. Economy

- Starting capital: $50,000
- Revenue: departments generate income per tick (modified by employee count and type)
- Costs: building upkeep, employee salaries, policy activation
- Salary: Ace $20/tick, Rookie $8/tick, Cynic $15/tick, Disengaged $5/tick, Leader $30/tick
- Bankruptcy: money hits 0 → warning at $5,000, game over at sustained negative

---

## Visual Design

### Tone & Manner
- **Warm pastel miniature** — tilt-shift feel, soft shadows, rounded shapes
- **Bright daytime-dominant** — subtle day/night cycle (dimming, not dark)
- **Cel-shaded** — 2px outlines on buildings, top-left light source
- **Reference feel:** Two Point Hospital × Mini Motorways

### Color Palette

```
World:
  Grass:           #8BC34A → #C5E1A5 (gradient)
  Ground/Corridor: #D7CCC8 → #BCAAA4
  Sky:             #E3F2FD → #BBDEFB

Departments:       (listed in section 1 above)
Facilities:        (listed in section 1 above)

Employees:
  Ace:             #FF7043
  Eager Rookie:    #66BB6A
  Cynic:           #78909C
  Disengaged:      #BDBDBD
  Leader:          #FFD54F

UI Accents:
  SK Blue:         #0052A2 (HUD titles, policy icons)
  SK Red:          #E4002B (warnings, crisis events)
  Gold:            #FFB830 (achievements, star rating)

Stakeholder Indicators:
  Customer:        #42A5F5
  Employee:        #66BB6A
  Social:          #26A69A
```

### Typography
- Headings: system-ui bold (game HUD)
- Body: system-ui regular
- Monospace numbers: tabular-nums for metrics

### HUD Layout
- **Top bar:** Company name, Money, Employee count, Star rating, 3 stakeholder mini-bars, Day counter, Clock, Speed toggle
- **Bottom bar:** Build toolbar (departments + facilities + bulldoze)
- **Right panel:** Policy tree (collapsible)
- **Bottom-right:** Minimap
- **Center (on event):** Event card with choices

---

## Technical Architecture

Single HTML file (`public/skms-builder.html`), no external dependencies.

- **Rendering:** Canvas 2D, isometric projection
- **Game loop:** requestAnimationFrame with delta-time accumulator
- **Pathfinding:** BFS on corridor/walkable tiles
- **Audio:** Web Audio API (placement SFX, event chime, ambient BGM)
- **State:** Plain JS objects, no framework

---

## Integration with Main Site

- Add "PLAY" link to `public/index.html` navigation bar
- Links to `/skms-builder.html`
- Game has "Back to SKMS" button in top-left returning to index.html
- Standalone file, no shared JS/CSS dependencies with main site

---

## Success Criteria

1. Player can build a functioning company in under 2 minutes
2. Trade-off tension is felt within the first 5 minutes (one metric drops while another rises)
3. SKMS policies have visible, tangible effects on employee behavior and metrics
4. Events force meaningful choices that reference real SKMS concepts
5. Tutorial (3 steps) guides first-time players to build → hire → activate first policy
6. Runs at 60fps on modern browsers, no external dependencies
