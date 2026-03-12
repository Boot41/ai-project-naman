# --- Stage 1: Build frontend ---
FROM node:20-slim AS frontend-build
WORKDIR /build
COPY client/package.json client/package-lock.json ./
RUN npm ci
COPY client/ .
RUN npm run build

# --- Stage 2: Python app ---
FROM python:3.12-slim AS runtime
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY server/pyproject.toml server/uv.lock ./
RUN uv pip install --system --no-cache -r pyproject.toml

COPY server/ .
COPY --from=frontend-build /build/dist /app/static

EXPOSE 8020

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8020"]
