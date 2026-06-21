# --- Stage 1: build the frontend -------------------------------------
FROM node:20-alpine AS frontend-build

WORKDIR /frontend
COPY frontend/package.json frontend/package.json
RUN cd frontend && npm install

COPY frontend frontend
RUN cd frontend && npm run build
# vite.config.js outputs to ../backend/app/static, so the build lands at
# /backend/app/static inside this stage.

# --- Stage 2: backend runtime -------------------------------------------
FROM python:3.11-slim AS backend

WORKDIR /app

# System deps for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app

# Pull in the built frontend static assets from stage 1
COPY --from=frontend-build /backend/app/static ./app/static

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
