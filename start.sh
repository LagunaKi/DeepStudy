#!/usr/bin/env bash
set -euo pipefail

python -m uvicorn backend.main:app \
  --host "${API_HOST:-0.0.0.0}" \
  --port "${API_PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips="*" &
backend_pid=$!

cleanup() {
  kill "$backend_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 30); do
  if curl --fail --silent "http://localhost:${API_PORT:-8000}/health" >/dev/null; then
    exec nginx -g "daemon off;"
  fi
  sleep 1
done

echo "Backend failed to become healthy" >&2
exit 1
