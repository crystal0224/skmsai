# S03: CI/CD 파이프라인 명세

> SKMS Time-Aware RAG Pipeline CI/CD 구성

## 1. 파이프라인 개요

```
Push/PR → Lint → Test → Build → Deploy (staging) → Smoke Test → Deploy (prod)
```

## 2. GitHub Actions 워크플로우

### PR 검증 (ci.yml)

```yaml
# .github/workflows/ci.yml
name: CI
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run tests
        run: python -m pytest tests/ -v --tb=short

      - name: Check test count
        run: |
          COUNT=$(python -m pytest tests/ --collect-only -q 2>/dev/null | tail -1 | grep -oP '\d+')
          echo "Test count: $COUNT"
          if [ "$COUNT" -lt 1185 ]; then
            echo "ERROR: Test count dropped below 1185"
            exit 1
          fi
```

### Docker 빌드 + 배포 (deploy.yml)

```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    branches: [main]
    paths-ignore:
      - "docs/**"
      - "*.md"

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -t skms-api:${{ github.sha }} .

      - name: Run smoke test
        run: |
          docker run -d --name test-api \
            -e OPENAI_API_KEY=test \
            -p 8000:8000 \
            skms-api:${{ github.sha }}
          sleep 5
          curl -f http://localhost:8000/api/health || exit 1
          docker stop test-api

      - name: Push to registry
        run: |
          docker tag skms-api:${{ github.sha }} $REGISTRY/skms-api:latest
          docker push $REGISTRY/skms-api:latest
```

## 3. 환경별 구성

| 환경 | 트리거 | 자동 배포 | 데이터 |
|------|--------|-----------|--------|
| 개발 (local) | 수동 | N/A | 로컬 SQLite + Chroma |
| 스테이징 | PR merge → main | Yes | 스테이징 DB |
| 프로덕션 | main 태그 | 수동 승인 | 프로덕션 DB + Pinecone |

## 4. 필수 검증 단계

### PR Merge 전
1. **테스트 통과**: 전체 1,185+ 테스트 PASS
2. **테스트 수 미감소**: 이전 버전 대비 테스트 수 감소 시 실패
3. **Docker 빌드 성공**: Dockerfile 빌드 검증

### 배포 전
1. **헬스체크 통과**: `/api/health` 200 응답
2. **스모크 테스트**: 검색/생성 기본 API 동작 확인
3. **환경변수 검증**: `validate_environment()` 필수 변수 확인

## 5. 의존성 관리

### requirements.txt 주요 패키지

| 패키지 | 용도 | 버전 정책 |
|--------|------|-----------|
| fastapi | API 서버 | 마이너 버전 고정 |
| uvicorn | ASGI 서버 | 마이너 버전 고정 |
| openai | 임베딩 API | 메이저 버전 고정 |
| anthropic | LLM API | 메이저 버전 고정 |
| chromadb | 벡터 DB (dev) | 마이너 버전 고정 |
| rank-bm25 | 키워드 검색 | 고정 |
| pydantic | 데이터 검증 | v2 고정 |

### 보안 스캔
- `pip audit` — 알려진 취약점 검사 (CI에서 주 1회)
- Dependabot — GitHub 자동 PR

## 6. 롤백 전략

| 시나리오 | 방법 | 소요 시간 |
|----------|------|-----------|
| API 오류 | 이전 Docker 이미지로 롤백 | < 5분 |
| 데이터 오류 | SQLite 백업 복원 | < 10분 |
| 인덱스 오류 | 이전 BM25/Chroma 인덱스 복원 | < 10분 |
| 전체 장애 | docker-compose down/up (이전 버전) | < 15분 |
