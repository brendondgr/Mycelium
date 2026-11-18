#!/usr/bin/env bash
# EXP-2026-11-023 driver. Usage (repo root):
#   PRIVATE_DIR=<dir outside the repo> FROZEN=<git archive of the commit> \
#     docs/research/experiments/EXP-2026-11-023-collab-live-fsu-sc/code/drive.sh check|prepare|search|export [--only F01,..]
set -euo pipefail
: "${PRIVATE_DIR:?set PRIVATE_DIR}" "${FROZEN:?set FROZEN}"
exec docker compose run --rm --no-deps -T --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -e SANDBOX_DB=mycelium_sandbox_fsusc -e LLM_MODEL=default-model \
  -v "$FROZEN/tools:/app/tools:ro" -v "$FROZEN/web/backend:/app/web/backend:ro" \
  -v "$PWD/web/backend/media:/app/web/backend/media" \
  -v "$PWD/docs/research:/app/docs/research" -v "$PRIVATE_DIR:/private" backend \
  uv run --no-sync --project web/backend python \
  docs/research/experiments/EXP-2026-11-023-collab-live-fsu-sc/code/run023.py "$@"
