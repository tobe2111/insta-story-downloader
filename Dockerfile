# 퀀트 트레이딩 시스템 — 로컬/VPS 배포용 이미지
# 빌드:  docker build -t quant .
# 웹UI:  docker run --rm -p 8000:8000 quant
# 실거래: docker run --rm -e EXCHANGE_API_KEY=... -e EXCHANGE_SECRET=... quant \
#            python examples/run_live.py --paper --market crypto --symbol BTC/USDT
FROM python:3.12-slim

# 런타임 최적화
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 의존성 먼저 설치(레이어 캐시)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 복사
COPY quant/ ./quant/
COPY examples/ ./examples/
COPY config/ ./config/
COPY README.md pyproject.toml ./

# 웹 UI는 컨테이너 외부에서 접속할 수 있게 0.0.0.0 바인딩
EXPOSE 8000
CMD ["python", "-m", "quant", "web", "--host", "0.0.0.0", "--port", "8000"]
