FROM node:24-bookworm-slim AS ocr_dependencies
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ocr_dependencies /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=ocr_dependencies /build/node_modules /app/node_modules
COPY app ./app
RUN useradd --uid 10001 --create-home appuser \
    && mkdir -p /app/work /app/results && chown -R appuser:appuser /app/work /app/results
ENV APP_HOST=0.0.0.0 APP_PORT=8765 APP_DATA_DIR=/app/work APP_RESULTS_DIR=/app/results \
    OCR_NODE_BIN=/usr/local/bin/node PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER appuser
EXPOSE 8765
HEALTHCHECK --interval=20s --timeout=3s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=2)"
CMD ["python", "-m", "app.server"]
