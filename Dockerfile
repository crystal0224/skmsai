FROM python:3.10-slim AS base

# 보안: non-root 유저 생성
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --create-home appuser

WORKDIR /app

# 시스템 의존성 설치 (빌드 캐시 활용)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Python 의존성 설치
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY scripts/ scripts/
COPY server/ server/
COPY config/ config/
COPY migrations/ migrations/
COPY prompts/ prompts/
COPY guardrails/ guardrails/

# 데이터 디렉토리 준비
RUN mkdir -p data/processed indexes && \
    chown -R appuser:appuser /app

# non-root 유저로 전환
USER appuser

# 환경변수 기본값
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    ALLOWED_ORIGINS="http://localhost:3000"

EXPOSE 8000

# 헬스체크
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# 프로덕션 서버 실행 (uvicorn, 워커 수 조정 가능)
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
