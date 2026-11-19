#!/usr/bin/env bash
# EXP-2026-11-025 driver (same container as EXP-2026-11-024). Usage (repo root):
#   PRIVATE_DIR=<dir outside the repo> FROZEN=<git archive of the commit, with COMMIT> \
#     docs/research/experiments/EXP-2026-11-025-collab-self-query-problem-slots/code/drive.sh \
#     identity|search --arm prev|multi [--only F01,..]
set -euo pipefail
: "${PRIVATE_DIR:?set PRIVATE_DIR}" "${FROZEN:?set FROZEN}"
exec docker compose run --rm --no-deps -T --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -e SANDBOX_DB=mycelium_sandbox_fsusc24 -e LLM_MODEL="${LLM_MODEL:-default-model}" \
  -e COMMIT_UNDER_TEST="$(cat "$FROZEN/COMMIT")" \
  -v "$FROZEN/tools:/app/tools:ro" -v "$FROZEN/web/backend:/app/web/backend:ro" \
  -v "$PWD/web/backend/media:/app/web/backend/media" \
  -v "$PWD/docs/research:/app/docs/research" -v "$PRIVATE_DIR:/private" backend \
  uv run --no-sync --project web/backend python \
  docs/research/experiments/EXP-2026-11-025-collab-self-query-problem-slots/code/run025.py "$@"
