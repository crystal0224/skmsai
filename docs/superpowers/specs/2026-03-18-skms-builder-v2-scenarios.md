# SKMS Company Builder v2 — Scenario & Gameplay Design

## Overview

Upgrade the existing `public/parktycoon.html` from a sandbox builder into a **scenario-driven management simulation** with story, choices, and consequences. The player takes over a struggling company and must apply SKMS principles to save it.

## Scenario 1: "Crisis Company" (위기의 회사)

### Starting State
- Money: $15,000 (bleeding cash)
- Employees: 12 (Disengaged 6, Cynic 4, Rookie 2, Ace 0, Leader 0)
- Customer Satisfaction: 25 / Employee Happiness: 18 / Social Value: 10
- Pre-built: Production (overworked), Marketing (neglected), 2 corridors
- Missing: HR, Academy, Wellness, Cafeteria — zero support infrastructure
- Star rating: 1.2

### Win Condition
Reach star rating 3.0+ and sustain for 30 game-days.

### Fail Condition
Money reaches $0 or all employees quit.

---

## Core Gameplay Systems (Phase 1)

### 1. Employee Speech Bubbles + Visual States

**Speech Bubbles:** Employees periodically show 1-line thoughts based on their state.

Trigger conditions and example lines:
```
Disengaged + no welfare:    "매일 똑같은 하루... 의미가 없다"
Disengaged + academy built: "교육이라도 받을 수 있으면 좋겠는데"
Cynic + no VWBE:           "열심히 해봤자 달라지는 건 없어"
Cynic + VWBE active:       "분위기가 좀 달라졌나? 나도 해볼까"
Rookie + no OJT:           "혼자 배우려니 막막하다"
Rookie + OJT active:       "선배가 알려주니 확실히 다르다!"
Ace considering quit:       "스카우트 제의 왔는데... 고민된다"
Ace + good culture:        "이 회사 오길 잘했어"
Leader good:               "우리 팀이 성장하는 게 보여서 좋다"
Leader overwhelmed:         "관리할 게 너무 많아..."
After pressure event:       "야근 또야? 이력서 업데이트 해야겠다"
After welfare built:        "구내식당 생겼다! 소소하지만 기분 좋네"
Type transition Cynic→Ace:  "다시 한번 제대로 해볼까!"
Type transition Ace→Cynic:  "...더 이상 의미 없는 것 같다"
Quitting:                   "여기까지인 것 같습니다. 안녕히 계세요."
```

**Visual States:**
- Walking speed: Ace 2.0x, Rookie 1.2x, Cynic 0.8x, Disengaged 0.4x
- Color saturation: Ace full, Rookie 90%, Cynic 60%, Disengaged 30%
- Size: Leader 1.3x, Ace 1.0x, others 0.9x
- Quitting: walks to HQ with 😢, fades out

### 2. News Event Cards (외부 환경)

Every 40-60 game-seconds, a news headline appears as a centered modal card.

**Format:**
```
📰 [Headline]
[1-2 line description]

[Choice A] → preview: Customer +X, Employee -Y
[Choice B] → preview: ...
[Choice C] → (only if specific policy active) preview: ...

⏱ 15 second timer — auto-picks worst if dismissed
```

**Event Pool (10 events):**

| # | Headline | Choice A | Choice B | Choice C (conditional) |
|---|----------|----------|----------|----------------------|
| 1 | "핵심 인재 스카우트 제의" | Raise salary (-$2000, emp+10) | Let them go (emp-15, lose 1 ace) | Growth path (VWBE req: emp+5, free) |
| 2 | "언론 품질 이슈 보도" | PR response (-$1000, cust-5) | Full recall (-$3000, cust+10) | Ignore (cust-20) |
| 3 | "구성원 번아웃 경고" | Mandatory vacation (rev-30% 3days) | Ignore (emp-20, 2 quits) | Auto-mitigate (VWBE+Wellness: emp-5) |
| 4 | "정부 사회 감사" | Pass (soc>60: soc+10) | Scramble (-$2000, soc+5) | Fail (soc<30: soc-15, cust-10) |
| 5 | "경쟁사 가격 인하" | Match prices (rev-20%) | Differentiate (SUPEX+RnD: cust+10) | Do nothing (cust-15) |
| 6 | "신입 교육 부재 민원" | Hire trainer (-$1500, rookie growth 2x) | Pair with senior (needs Ace) | Ignore (rookie→disengaged x2) |
| 7 | "지역 사회 봉사 요청" | Participate (-$500, soc+15, emp+5) | Donate only (-$1000, soc+8) | Decline (soc-10) |
| 8 | "노사 갈등 조짐" | Dialogue (Horizontal Comm req: emp+10) | Concession (-$2000, emp+5) | Suppress (emp-25, 3 cynics) |
| 9 | "혁신 프로젝트 기회" | Invest (-$3000, cust+20 delayed) | Pass (nothing) | Fast track (SUPEX: -$1500, cust+15) |
| 10 | "우수 기업 인증 기회" | Apply (all metrics>50: rating+0.5) | Skip | Not eligible (any metric<30: denied) |

### 3. Employee 1:1 Meeting (클릭 상호작용)

Click an employee → meeting panel appears with 3 context-sensitive choices.

**Choice pool by employee type:**

Disengaged:
- "어떤 점이 힘든가요?" → reveals hidden issue, small will+5
- "역량 개발 기회를 주겠습니다" → if Academy exists: starts training arc
- "솔직히 개선이 필요합니다" → 50% will+10 (wake-up), 50% will-10 (defensive)

Cynic:
- "당신의 전문성이 필요합니다" → will+10, shows they're valued
- "팀에 어떤 변화가 필요할까요?" → reveals dept problem, trust+
- "성과에 따른 보상을 약속합니다" → if Rewards policy: will+15, else empty promise will-5

Rookie:
- "적응은 잘 되고 있나요?" → will+5, reveals needs
- "멘토를 붙여드리겠습니다" → if Ace in same dept: cap growth 2x
- "어떤 분야에 관심이 있나요?" → reveals aptitude → reassignment hint

Ace:
- "커리어 목표가 뭔가요?" → prevents quit for 30 days
- "리더 역할을 맡아보시겠어요?" → promote to leader (if cap>80)
- "지금 업무 강도는 괜찮은가요?" → reveals burnout risk

Leader:
- "팀 상황은 어떤가요?" → reveals dept-wide morale
- "필요한 지원이 있나요?" → choose: budget/people/policy
- "코칭 역량을 키워봅시다" → if Academy: leader effectiveness+

### 4. Ending Report Card

When win/lose condition is met:

```
╔══════════════════════════════════════════════╗
║          📊 경영 성적표                       ║
╠══════════════════════════════════════════════╣
║                                              ║
║  경영 스타일: "성과 중심 실용주의자"            ║
║  SKMS 정합성: 68%                             ║
║  소요 기간: 87일                               ║
║                                              ║
║  ── 이해관계자 균형 ──                         ║
║  👥 고객 만족:   72  ████████████░░░░        ║
║  💚 구성원 행복: 58  ██████████░░░░░░        ║
║  🌍 사회적 가치: 45  ████████░░░░░░░░       ║
║                                              ║
║  ── 구성원 변화 ──                             ║
║  🔥 에이스 전환:     4명                       ║
║  😴→🔥 회복:        3명                       ║
║  👋 퇴사:           2명                        ║
║  ⭐ 리더 육성:       1명                       ║
║                                              ║
║  ── 당신의 선택 vs SKMS ──                     ║
║  ✅ SUPEX 추구 적시 도입                       ║
║  ❌ 구성원 복지보다 성과를 우선시               ║
║  ⚠️ 사회적 가치 투자 미흡                      ║
║                                              ║
║  "경영의 궁극적 목적은                         ║
║   이해관계자의 행복 극대화이다"                  ║
║  — SKMS 14차 개정판                            ║
║                                              ║
║  [다시 도전]  [결과 공유]                       ║
╚══════════════════════════════════════════════╝
```

**SKMS 정합성 계산:**
- +10% per active SKMS policy (9 policies × 10% = max 90%)
- +5% if employee happiness > 70
- +5% if no employee quit from neglect
- -10% per "ignore" choice on events
- -5% per pressure/suppress choice

### 5. SKMS Policy System (9 policies, research tree)

Right-side collapsible panel. Policies cost money + activation time.

```
┌── SKMS 경영 제도 ──────────────────┐
│                                     │
│  ✅ 성과 보상 체계     $500  [완료]  │
│  ✅ O.J.T 현장교육     $800  [완료]  │
│  🔒 수평적 소통        $600  10s    │
│  🔒 코디네이션         $1000        │
│     └ 필요: 기획부서                │
│  🔒 SUPEX 추구         $2000        │
│     └ 필요: R&D 부서                │
│  🔒 VWBE 문화          $1500        │
│     └ 필요: HR + 복지시설           │
│  🔒 사회적 가치 경영    $1200        │
│     └ 필요: 사회공헌 부서           │
│  🔒 윤리 경영           $1000        │
│  🔒 SK-Manship         $3000        │
│     └ 필요: SUPEX + VWBE           │
│                                     │
└─────────────────────────────────────┘
```

---

## 3D Isometric Rendering

### Cel-shaded look
- Buildings: 3-face isometric box (top, left, right) with distinct lighting
- Top face: brightest (top-left light source)
- Left face: medium shade (receives some light)
- Right face: darkest (shadow side)
- 2px dark outline on all building edges
- Soft drop shadow cast to bottom-right

### Depth enhancements
- Buildings have varying heights by type (departments taller than facilities)
- Employees cast small circular shadows on the ground
- Parallax-like effect: buildings in front partially occlude those behind (painter's algorithm)
- Ground has subtle grid pattern visible on grass
- Corridors are slightly raised from grass level (2px)

### Color palette (warm pastel miniature)
- Grass: gradient #8BC34A → #C5E1A5
- Sky: gradient #E3F2FD → #BBDEFB (day), dimmed at night
- Department colors: as defined in original spec (pastel tones)
- Employee colors by type: Ace #FF7043, Rookie #66BB6A, Cynic #78909C, Disengaged #BDBDBD, Leader #FFD54F

---

## Technical

- Single HTML file, Canvas 2D
- 1 tick = 1 second at 1x speed
- Game speeds: 1x, 2x, 4x
- Scenario start: pre-populated grid with broken company
- Target: playable 20-30 minute experience
