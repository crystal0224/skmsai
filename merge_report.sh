#!/bin/bash
set -e

OUTPUT="SKMS_Final_Report.html"
MAIN="SKMS_NotebookLM_Report.html"

echo "=== Step 1: Head + Header (lines 1-201) ==="
head -n 201 "$MAIN" > "$OUTPUT"

echo "=== Step 2: Updated TOC ==="
cat >> "$OUTPUT" << 'TOCEOF'
<!-- ========== TOC ========== -->
<div class="toc">
  <h3 style="margin-top:0;">목차</h3>
  <ul>
    <li><a href="#sec0">0. 데이터 특성 진단 및 전처리 전략</a></li>
    <li><a href="#secA">A. 계획 통합본 검토 보고서</a>
      <ul>
        <li><a href="#a1">A-1. 목표 / 비목표</a></li>
        <li><a href="#a2">A-2. 데이터 특성 진단</a></li>
        <li><a href="#a3">A-3. 설계안 요약 (Components + Dataflow)</a></li>
        <li><a href="#a4">A-4. 핵심 리스크 10개 + 완화책</a></li>
        <li><a href="#a5">A-5. 의사결정 포인트 10개</a></li>
        <li><a href="#a6">A-6. 구현 난이도/효과 매트릭스</a></li>
        <li><a href="#a7">A-7. MVP &rarr; V1 &rarr; V2 단계화</a></li>
        <li><a href="#a8">A-8. 보안 요구사항</a></li>
      </ul>
    </li>
    <li><a href="#secB">B. 실행 계획 + 팀 구성안</a>
      <ul>
        <li><a href="#b1">B-1. WBS + 마일스톤</a></li>
        <li><a href="#b2">B-2. 역할 정의 (RACI)</a></li>
        <li><a href="#b3">B-3. 인원/역량 요구</a></li>
        <li><a href="#b4">B-4. 리스크/의존성/우선순위</a></li>
        <li><a href="#b5">B-5. 경영진 보고용 1페이지 요약</a></li>
      </ul>
    </li>
    <li><a href="#secC">C. PR 기반 실행 계획 (39개 PR)</a>
      <ul>
        <li><a href="#pr-plan-phase01">C-1. Phase 0 + Phase 1 MVP (PR-001 ~ PR-016)</a></li>
        <li><a href="#pr-plan-phase2">C-2. Phase 2 V1 (PR-017 ~ PR-030)</a></li>
        <li><a href="#pr-plan-phase3">C-3. Phase 3 V2 (PR-031 ~ PR-039)</a></li>
      </ul>
    </li>
    <li><a href="#appendix">부록: 프로젝트 폴더 구조 / 데이터 스키마</a></li>
  </ul>
</div>

TOCEOF

echo "=== Step 3: Sections 0 + A (lines 231-2293) ==="
sed -n '231,2293p' "$MAIN" >> "$OUTPUT"

echo "=== Step 4: A-8 Security placeholder ==="
cat >> "$OUTPUT" << 'A8EOF'

<!-- ================================================================ -->
<h2 id="a8">A-8. 보안 요구사항</h2>
<!-- ================================================================ -->
<!-- PLACEHOLDER_A8_SECURITY -->

A8EOF

echo "=== Step 5: Section B (lines 2294-4027) ==="
sed -n '2294,4027p' "$MAIN" >> "$OUTPUT"

echo "=== Step 6: Section C header + PR styles ==="
cat >> "$OUTPUT" << 'CEOF'

<hr>

<!-- ================================================================ -->
<h1 id="secC">C. PR 기반 실행 계획</h1>
<!-- ================================================================ -->

<style>
  .pr-entry {
    background: var(--surface, #1a1d27);
    border: 1px solid var(--border, #2d3242);
    border-radius: 10px;
    padding: 1.5rem;
    margin: 1.5rem 0;
  }
  .pr-entry h4 {
    font-size: 1.1rem;
    color: var(--accent, #6c8cff);
    margin: 0 0 0.8rem;
  }
  .pr-meta {
    font-size: 0.85rem;
    color: var(--text-dim, #8b8fa3);
    margin-bottom: 1rem;
  }
  .pr-divider {
    border: none;
    border-top: 2px dashed var(--border, #2d3242);
    margin: 2rem 0;
  }
</style>

<p>본 섹션은 A산출물(계획 통합본 검토 보고서)과 B산출물(실행 계획 + 팀 구성안)을 기반으로 작성된 <strong>39개 PR 단위 실행 계획</strong>이다. 각 PR은 독립적으로 리뷰·머지 가능하며, 의존 관계가 명시되어 있다.</p>
<p style="font-size:0.85rem; color:var(--text-dim);">
  Phase 0 (PR-001~008): 프로젝트 기반 구조 | Phase 1 MVP (PR-009~016): 핵심 기능 |
  Phase 2 V1 (PR-017~030): 고도화 | Phase 3 V2 (PR-031~039): 프로덕션 전환
</p>

<h2 id="pr-plan-phase01">C-1. Phase 0 + Phase 1 MVP (PR-001 ~ PR-016)</h2>

CEOF

echo "=== Step 7: PR Phase 0+1 (skip first 5 lines: comments + h1) ==="
tail -n +6 pr_phase01.html >> "$OUTPUT"

echo "=== Step 8: Phase 2 header + content ==="
cat >> "$OUTPUT" << 'P2EOF'

<h2 id="pr-plan-phase2">C-2. Phase 2 V1 (PR-017 ~ PR-030)</h2>

P2EOF
tail -n +5 pr_phase2.html >> "$OUTPUT"

echo "=== Step 9: Phase 3 header + content ==="
cat >> "$OUTPUT" << 'P3EOF'

<h2 id="pr-plan-phase3">C-3. Phase 3 V2 (PR-031 ~ PR-039)</h2>

P3EOF
# Phase 3 original: skip style block + heading (lines 1-52), keep gate conditions (line 49+)
# Actually include gate conditions paragraph (lines 49-52) and all PR entries
sed -n '49,$ p' pr_phase3.html >> "$OUTPUT"

# Phase 3 new fragments
echo "" >> "$OUTPUT"
cat pr_phase3_034_035.html >> "$OUTPUT"
echo "" >> "$OUTPUT"
cat pr_phase3_036_037.html >> "$OUTPUT"
echo "" >> "$OUTPUT"
cat pr_phase3_038_039.html >> "$OUTPUT"

echo "=== Step 10: Appendix + closing (lines 4028-end) ==="
sed -n '4028,$ p' "$MAIN" >> "$OUTPUT"

echo "=== Merge complete! ==="
wc -l "$OUTPUT"
