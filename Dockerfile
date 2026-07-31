FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl nginx \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist
COPY nginx.conf /etc/nginx/nginx.conf
COPY start.sh ./start.sh

RUN chmod +x ./start.sh

EXPOSE 7860

HEALTHCHECK --interval=20s --timeout=5s --start-period=30s --retries=5 \
    CMD curl --fail http://localhost:7860/health || exit 1

ENTRYPOINT ["/app/start.sh"]
