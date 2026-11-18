#!/usr/bin/env bash
# EXP-2026-11-022: one (label, seed, arm) of the replay, from a frozen copy of a
# commit (`git archive <commit> tools web/backend | tar -x -C $SNAP`), mounted
# read-only over the checkout's tools/ and web/backend/, as
# EXP-2026-11-021/code/drive_row.sh does. Run from the repository root.
#   SNAP=<dir> LABEL=f1115 SEED=101 ARM=prompt_only [REPS=1] [CONC=3] [EXTRA=--dry-run] \
#     bash docs/research/experiments/EXP-2026-11-022-gemma-empty-replies-replay/code/drive.sh
set -u
E=docs/research/experiments/EXP-2026-11-022-gemma-empty-replies-replay
docker compose run --rm --no-deps -T --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -e LLM_MODEL=default-model -e AGENT_PARALLEL_CALLS=0 \
  -v "$SNAP/tools:/app/tools:ro" -v "$SNAP/web/backend:/app/web/backend:ro" \
  -v "$PWD/web/backend/media:/app/web/backend/media" \
  -v "$PWD/docs/research:/app/docs/research" \
  backend uv run --no-sync --project web/backend python $E/code/replay.py \
  --label "$LABEL" --seed "$SEED" --arm "$ARM" --reps "${REPS:-1}" --conc "${CONC:-3}" ${EXTRA:-} 2>&1 \
  | grep -v -i -e onnx -e '^  ' | tail -40
