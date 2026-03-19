# SKMS Company Builder — Onboarding Redesign

**Date**: 2026-03-19
**Status**: Approved
**Scope**: `public/parktycoon.html` — `showOnboarding()` function (lines ~5313–6000)

## Problem

현재 온보딩 2페이지의 핵심 문제:

1. **SKMS 화살표가 너무 작음** — 36px 이모지 `➡` + 13px 텍스트. 게임의 핵심 메커닉(플레이어의 경영 선택)인데 시각적 존재감이 없음
2. **After가 단일 결과** — "SKMS 적용 = 무조건 좋아짐"으로 읽혀서 긴장감 없음. 실패 가능성이 안 보임
3. **페이지 1에 시나리오 선택이 섞여 있음** — Before/After와 시나리오 선택이 한 페이지에 있어서 둘 다 임팩트가 약함
4. **캔버스(1060x260)가 납작** — 캐릭터+말풍선이 빽빽하고 극적 대비가 부족

## Design

### Page 1 — "SKMS 경영이 만드는 변화" (화면 꽉 채움)

**레이아웃: 갈림길(Diverging Paths)**

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  BEFORE  │     │   SKMS   │     │ ✅ 성공   │
│          │ ──→ │          │ ──↗ │  SUPEX!  │
│ 무기력한  │     │ YOUR TURN│     ├──────────┤
│ 캐릭터들  │     │          │ ──↘ │ ❌ 실패   │
│ (회색,작) │     │ 극적질문  │     │  파산💀   │
└──────────┘     └──────────┘     └──────────┘
```

**Before 영역 (좌측)**
- 무기력한 캐릭터 3명: 회색/반투명, 작은 사이즈
- 캐릭터: 무기력(#BDBDBD), 냉소파(#78909C), 신입(#66BB6A, 작게)
- 말풍선 순환 (기존 캔버스 애니메이션 유지)
- 하락 그래프 라인 + "📉" 표시
- 배경: 붉은 틴트 (rgba(254,226,226,0.5))

**SKMS 분기점 (중앙) — 컨트롤 패널 + 극적 질문**
- "⚡ YOUR TURN" 골드 헤더
- 카드형 패널: `background: linear-gradient(180deg, #0f172a, #1e293b)`, `border: 2px solid rgba(96,165,250,0.4)`, `box-shadow: 0 0 30px rgba(0,82,162,0.3)`
- "SKMS" 타이틀 (#60a5fa, bold)
- 🎮 게임패드 이모지 (크게)
- **"당신의 경영이 운명을 바꿉니다"** — 핵심 카피. "운명"은 골드(#FFD54F)로 강조
- 펄스 애니메이션 (glow 효과)

**After 영역 (우측) — 성공/실패 분기**

성공 경로 (상단):
- 배경: `rgba(34,197,94,0.08)`, 테두리: `rgba(34,197,94,0.25)`
- "✅ SUPEX 달성" 헤더
- 성장한 캐릭터 3명: 컬러풀, 큰 사이즈 (회복 #66BB6A, 에이스 #FF7043, 리더 #FFD54F with golden glow)
- "직원 행복 + 성과 📈"

실패 경로 (하단):
- 배경: `rgba(220,38,38,0.06)`, 테두리: `rgba(220,38,38,0.15)`
- "❌ 경영 실패" 헤더
- 줄어든 캐릭터 2명: 반투명, 매우 작게 (opacity 0.2~0.4)
- "이직 러시 + 파산 💀"

**DOM 구조 (3-column flexbox)**:
```
div.onboard-slide.active (Slide 1)
  div.slide1-layout (display:flex; align-items:center; justify-content:center; gap:12px; height:100%; position:relative)
    canvas#before-canvas   (width:280, height:340, flex:0 0 auto)  ← Before 캐릭터 전용
    div.skms-panel         (width:140px, flex:0 0 auto)            ← SKMS DOM 패널
    div.after-area         (width:140px, flex:0 0 auto; display:flex; flex-direction:column; gap:8px)
      div.success-path     ← 성공 캐릭터 (canvas 280x130 내장)
      div.failure-path     ← 실패 캐릭터 (canvas 280x130 내장)
    svg.diverge-arrows     (position:absolute; inset:0; pointer-events:none)
```

**캔버스 사이즈**:
- Before 캔버스: `280 x 340` (기존 1060x260에서 세로 확대, Before 전용)
- After 성공 캔버스: `140 x 130` (성공 캐릭터 3명)
- After 실패 캔버스: `140 x 130` (실패 캐릭터 2명)
- 모든 캔버스에서 `drawIsoChar()` 재사용 (각 캔버스의 getContext('2d')를 전달)

**SVG 분기 화살표**:
- SVG가 `.slide1-layout` 위에 absolute로 오버레이
- SKMS 패널 우측 → 성공 박스 좌측: `M {skmsRight},{skmsTop} Q {mid},{successCenterY} {afterLeft},{successCenterY}` (초록 #22c55e, stroke-width:2, 위로 커브)
- SKMS 패널 우측 → 실패 박스 좌측: `M {skmsRight},{skmsBottom} Q {mid},{failCenterY} {afterLeft},{failCenterY}` (빨강 #ef4444, stroke-width:2, 아래로 커브)
- 화살표 끝: marker-end (삼각형 6x4)
- 좌표는 JS에서 DOM 요소의 offsetLeft/offsetTop으로 동적 계산

**애니메이션 (생동감 강화)**:
- 기존 캐릭터 bobble + 말풍선 순환 유지 (requestAnimationFrame 루프)
- SKMS 패널: CSS `@keyframes skms-pulse { 0%,100% { box-shadow: 0 0 20px rgba(0,82,162,0.2) } 50% { box-shadow: 0 0 40px rgba(0,82,162,0.5) } }` duration `2.5s infinite`
- Before→SKMS 화살표: 점선 dash (stroke-dasharray: 4 3), 색상 #64748b
- **배경 파티클**: 캔버스 뒤에 떠다니는 작은 원 15~20개 (opacity 0.05~0.15, 크기 2~6px, 느린 상승 + 좌우 사인파 드리프트). Before 쪽은 회색/붉은 파티클, After 성공 쪽은 초록/골드 파티클, 실패 쪽은 붉은 파티클
- **캐릭터 입장 애니메이션**: 슬라이드 진입 시 캐릭터들이 아래에서 위로 fade-in (stagger 0.1s 간격). Before는 느리게(0.8s), After 성공은 탄력있게(bounce easing), After 실패는 흔들리며(shake) 등장
- **성공 경로 반짝임**: 성공 캐릭터 리더(#FFD54F) 주변에 작은 별 파티클 3~4개가 간헐적으로 반짝임 (twinkle, 2~3초 주기)
- **실패 경로 낙하**: 실패 캐릭터 위에 작은 빗금/먼지 파티클이 느리게 떨어짐

**BGM (온보딩 중 재생)**:
- 브라우저 자동재생 정책: 사용자 첫 클릭/터치 시 `initAudio()` + 온보딩 전용 BGM 시작
- 온보딩 오버레이에 `click` 이벤트 리스너 추가 (한 번만 실행): 클릭 시 `initAudio()` 호출 후 온보딩 BGM 시작
- **온보딩 전용 BGM**: 기존 `startBGM()`의 코드 진행(Cmaj7→Fmaj7→Am7→G)을 재사용하되, 볼륨을 더 낮게 (gain 0.012), 템포를 더 느리게 (interval 600~700ms) 하여 몽환적/기대감 있는 분위기
- 게임 시작 시 온보딩 BGM → 게임 BGM으로 자연스럽게 전환 (stopBGM → startBGM)

### Page 2 — "시나리오 선택" (시나리오 중심 + 하단 플레이 요약)

**시나리오 카드 (대형, 화면 주인공)**

시나리오 1 — 위기의 회사 🔥:
- 배경: `linear-gradient(180deg, rgba(248,113,113,0.12), rgba(248,113,113,0.04))`
- 테두리: `2px solid rgba(248,113,113,0.3)`
- 아이콘: 🔥 (32px)
- 제목: "위기의 회사" (#f87171, 13px bold)
- 설명: "무너져가는 회사의 CEO로 부임하여 조직을 살려라!"
- 난이도: ★★★ (badge)

시나리오 2 — AI 혁신 시대 🤖:
- 배경: `linear-gradient(180deg, rgba(96,165,250,0.12), rgba(96,165,250,0.04))`
- 테두리: `2px solid rgba(96,165,250,0.2)`
- 아이콘: 🤖 (32px)
- 제목: "AI 혁신 시대" (#60a5fa, 13px bold)
- 설명: "안정된 회사에 AI 혁신을 도입하여 초일류 기업으로!"
- 난이도: ★★☆ (badge, 신규 추가 요소)

선택 인터랙션: 클릭 시 active 클래스 토글 (기존 `selectScenario()` 로직 유지)

**플레이 방법 요약 스트립 (하단)**
- 한 줄 수평 배치: `🎮 플레이` 레이블 + `① 조직 세우고 → ② 사람 키우고 → ③ 위기 넘기세요`
- 배경: `rgba(96,165,250,0.05)`, 테두리: `rgba(96,165,250,0.1)`
- 기존 3-step 상세 플로우를 한 줄 요약으로 압축
- 스트립 스타일: `height:40px; padding:8px 14px; display:flex; align-items:center; gap:12px; border-radius:8px`
- 레이블: `font-size:10px; font-weight:800; color:#60a5fa`
- 스텝 칩: `background:rgba(255,255,255,0.05); padding:5px 10px; border-radius:5px; font-size:9px; color:#94a3b8`
- 화살표: `color:#334155; font-size:12px`

### Navigation

기존 dot navigation + 이전/다음 버튼 유지. 마지막 슬라이드에서 "🎬 경영 시작!" 버튼.

### Hero Title

기존 유지: "SKMS Company Builder" + "SK경영체계를 체험하는 경영 시뮬레이션"

### Save/Continue

기존 이어하기 로직 그대로 유지 (saveInfo, pendingContBtn, navContBtn).

## Implementation Approach

**캔버스 vs CSS**: 페이지 1의 캐릭터는 **기존 Canvas 방식 유지** (drawIsoChar 함수 재활용). 캔버스 크기를 키우고 레이아웃만 변경. SKMS 패널과 After 영역은 DOM 요소로 구성.

**변경 범위**: `showOnboarding()` 함수 전체 교체 (~690줄). 기존 함수의 구조(slides 배열, goToSlide, startNewGame 등)를 유지하되 슬라이드 내용만 변경.

**유지할 것**:
- `drawIsoChar()` 함수 (캐릭터 렌더링)
- `animatePreview()` 루프
- `selectScenario()` 로직
- save/continue 로직 전체
- navigation (dots, prev/next)

**변경할 것**:
- Slide 1 내용: Before/After + 시나리오 → Before/SKMS/After 갈림길
- Slide 2 내용: 3-step 플로우 → 시나리오 카드 + 플레이 요약 스트립
- 캔버스: 단일 1060x260 → 멀티 캔버스 (Before 280x340, 성공 140x130, 실패 140x130)
- leftChars/rightChars 데이터 → Before/성공/실패 3세트로 분리
- SKMS 화살표: 이모지 → DOM 패널 요소

## Testing

- 기존 기능 보존: 시나리오 선택, 이어하기, 새 게임 시작
- 슬라이드 네비게이션 (dots, 이전/다음)
- 캐릭터 애니메이션 정상 동작
- 모바일 반응형 (카드 크기 조정)
- 세이브 데이터 있을 때 이어하기 버튼 표시

## Out of Scope

- 캐릭터 드로잉 로직 변경 (drawIsoChar 재활용)
- 게임플레이 메커닉 변경
- 시나리오 추가/변경
- 튜토리얼 (showTutorial) 수정
