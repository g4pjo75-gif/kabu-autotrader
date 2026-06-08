# Hugging Face Spaces (Docker SDK) — Antigravity NiceGUI dashboard
# SIMULATION_MODE (yfinance real market data) で動作する可視化ダッシュボード
FROM python:3.12-slim

# build deps (cffi / lxml / curl_cffi 等の念のため)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# HF Spaces 推奨: 非root user
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    WEB_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1

WORKDIR $HOME/app

# 依存を先に入れてレイヤキャッシュ
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# アプリ本体
COPY --chown=user . .

# NiceGUI は config.WEB_PORT=8080 で起動。HF Space は README app_port:8080 で公開
EXPOSE 8080

CMD ["python", "main.py"]
