#!/usr/bin/env bash
# Start (or stop) a backend and a web server for EXP-2026-09-016's browser check.
#
# The backend reads a sandbox database (SANDBOX_DB, default the panel run's copy) and queues to its own Redis database,
# so nothing it saves reaches the development data or the development worker.
# The web server proxies /api to that backend and builds into its own .next
# (an anonymous volume), so it never disturbs the development web server.
#
#   sandbox_stack.sh up     # backend on :18001, web on :18002
#   sandbox_stack.sh down
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
API=mycelium-sbx-api
WEB=mycelium-sbx-web

if [ "${1:-up}" = down ]; then
  docker rm -f "$API" "$WEB" >/dev/null 2>&1 || true
  exit 0
fi

docker compose run -d --rm --no-deps --name "$API" -p 18001:8000 \
  -e DATABASE_URL=postgres://mycelium:mycelium@postgres:5432/${SANDBOX_DB:-mycelium_sandbox_ambweb} \
  -e REDIS_URL=redis://redis:6379/9 \
  -e CELERY_BROKER_URL=redis://redis:6379/9 \
  -e CELERY_RESULT_BACKEND=redis://redis:6379/10 \
  -e KNOWLEDGE_PROJECT_ON_SAVE=false -e KNOWLEDGE_FACET_ON_IMPORT=false \
  -e AMBIENT_ENABLED=true -e AMBIENT_DELIBERATE_ENABLED=false -e AMBIENT_CACHE_URL=redis://redis:6379/11 \
  -e DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1,$API" \
  -e DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:18002 \
  -e DJANGO_CORS_ALLOWED_ORIGINS=http://localhost:18002 \
  backend sh -c "uv run --project web/backend python web/backend/manage.py runserver 0.0.0.0:8000 --noreload"

docker compose run -d --rm --no-deps --name "$WEB" -p 18002:3000 \
  -v /app/web/app/.next \
  -e API_PROXY_TARGET="http://$API:8000" \
  -e API_INTERNAL_URL="http://$API:8000/api" \
  -e NEXT_PUBLIC_API_BASE_URL=/api \
  web sh -c "npm run dev:app:docker"

until curl -sf -o /dev/null http://localhost:18001/api/auth/csrf/; do sleep 2; done
until curl -sf -o /dev/null http://localhost:18002/login; do sleep 3; done
echo "sandbox stack up: api :18001, web :18002"
