# Content Studio V2 고도화 계획 (2026-03-12)

본 계획은 SKMS 컨텐츠 스튜디오의 생성 속도, 안정성, 그리고 출력물(PPTX/디자인)의 품질을 전문가 수준으로 끌어올리기 위한 상세 로드맵입니다.

## 1. 목표 (Objectives)
- **인프라 혁신**: 비동기 작업의 영속성 보장 및 생성 속도 2배 향상.
- **디자인 혁신**: AI가 생성한 티가 나지 않는 "Expert-Look" PPTX 및 시각 자료 제공.
- **사용자 경험 혁신**: 대시보드 내에서 생성 전 과정을 모니터링하고 제어할 수 있는 통합 UI 제공.

## 2. 상세 작업 내역 (Tasks)

### Task 1: 인프라 안정성 및 성능 최적화
- [ ] **Job Store 영속화 (Persistence)**:
    - 인메모리 `_job_store`를 SQLite 기반의 `DatabaseJobStore`로 전환.
    - 서버 재시작 시 `pending` 또는 `running` 상태의 작업 복구 로직 추가.
- [ ] **에셋 생성 병렬화 (Parallelism)**:
    - `AssetGenerator.generate_assets`에 `asyncio.gather` 적용.
    - 이미지, 차트, 오디오 생성을 동시 실행하여 전체 소요 시간 단축.

### Task 2: 전문가 수준의 디자인 품질 (Design Intelligence)
- [ ] **Design Reasoning 프롬프트 도입**:
    - `ContentPlanner`가 텍스트 구성 시 시각적 레이아웃 의도(Layout Intent)를 함께 생성하도록 프롬프트 수정.
    - 예: "이 슬라이드는 비교 구조이므로 좌우 대칭 레이아웃과 대조적인 색상 사용 권장".
- [ ] **고급 레이아웃 엔진 (`FileAssembler` 개선)**:
    - `python-pptx`를 활용한 5종 이상의 전문 레이아웃 템플릿(핵심수치형, 비교형, 프로세스형 등) 구현.
    - 텍스트 양에 따른 폰트 크기 자동 조정(Auto-fitting) 및 자간/행간 최적화.
- [ ] **브랜드 아이덴티티 강화**:
    - SK 프리미엄 폰트(Pretendard 등) 적용 및 세련된 컬러 팔레트 시스템 구축.

### Task 3: 대시보드 UI 통합 및 UX 개선
- [ ] **Content Studio 탭 구현**:
    - 주제 입력, 유형 선택, 옵션 설정을 위한 UI 폼 추가.
- [ ] **실시간 상태 모니터링**:
    - 비동기 작업 진행률(Progress Bar) 및 단계별 상태(Planning -> Generating -> Assembling) 표시.
- [ ] **결과물 미리보기 및 다운로드**:
    - 생성된 PPTX/HTML 미리보기 기능 및 원클릭 다운로드 링크 제공.

## 3. 일정 (Schedule)
1. **Day 1 (현재)**: 인프라 고도화 (Job Store & 병렬 처리) 완료.
2. **Day 2**: 디자인 엔진 고도화 및 PPTX 템플릿 시스템 강화.
3. **Day 3**: UI 통합 및 최종 E2E 검증.

## 4. 성공 지표 (Success Metrics)
- 평균 생성 시간: 기존 대비 40% 감소.
- 디자인 만족도: 전문가 리뷰 기준 "현업 즉시 사용 가능" 수준 확보.
- 시스템 안정성: 서버 재시작 시 작업 손실률 0%.
