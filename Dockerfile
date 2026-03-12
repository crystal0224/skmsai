FROM python:3.10-slim

WORKDIR /app

# 시스템 의존성 (한글 폰트, 폰트 설정 도구, FFmpeg 추가)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    fonts-nanum \
    fontconfig \
    ffmpeg && \
    fc-cache -f -v && \
    rm -rf /var/lib/apt/lists/*

# Python 의존성 (경량 deploy 버전)
COPY requirements-deploy.txt ./
RUN pip install --no-cache-dir -r requirements-deploy.txt

# 애플리케이션 코드
COPY scripts/ scripts/
COPY server/ server/
COPY src/ src/
COPY config/ config/
COPY prompts/ prompts/

# 데이터 + 인덱스 (검색 작동에 필수)
COPY data/ data/
COPY indexes/ indexes/

# output 디렉토리
RUN mkdir -p output

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Render free tier: 워커 1개로 메모리 절약
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
