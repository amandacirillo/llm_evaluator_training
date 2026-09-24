# ── Stage 1: Build React UI ────────────────────────────────────────────────
FROM node:18-slim AS ui-builder
WORKDIR /app/demo/ui
COPY demo/ui/package*.json ./
RUN npm ci
COPY demo/ui/ ./
RUN npm run build

# ── Stage 2: Python runtime ────────────────────────────────────────────────
FROM python:3.12-slim
WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App source
COPY src/ ./src/
COPY demo/server/ ./demo/server/
COPY config/ ./config/

# Pre-built React SPA (served by Flask in production)
COPY --from=ui-builder /app/demo/ui/dist ./demo/ui/dist

# Make src importable as a package root
ENV PYTHONPATH=/app

EXPOSE 5001

# 4 workers × 2 threads — enough for parallel LLM calls; long SSE streams
# use --timeout 300 to survive slow judge responses.
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5001", \
     "--workers", "4", \
     "--threads", "2", \
     "--timeout", "300", \
     "--worker-class", "gthread", \
     "demo.server.wsgi:app"]
