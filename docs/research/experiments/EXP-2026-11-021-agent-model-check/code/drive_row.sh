#!/usr/bin/env bash
# EXP-2026-11-021 Amendment 4: one row of the model check from a frozen copy of
# a commit (tools/ and web/backend/ of `git archive <commit>` mounted read-only
# over the checkout's), so the row reads the code of that commit whatever is
# being edited in the checkout.
#   TAG=<tag> SNAP=<dir with tools/ and web/backend/> LLM=<relay model> \
#   EVAL_MODEL_NAME='<as the operator states it>' CONC=8 bash …/code/drive_row.sh
set -u
E=docs/research/experiments/EXP-2026-11-021-agent-model-check
R=(docker compose run --rm --no-deps -T --user "$(id -u):$(id -g)" -e HOME=/tmp
   -e LLM_MODEL="${LLM:-default-model}" -e AGENT_PARALLEL_CALLS=0
   -e EVAL_MODEL_NAME="${EVAL_MODEL_NAME:-not stated by the operator}"
   -v "$SNAP/tools:/app/tools:ro" -v "$SNAP/web/backend:/app/web/backend:ro"
   -v "$PWD/web/backend/media:/app/web/backend/media"
   -v "$PWD/docs/research:/app/docs/research")
for part in demo gate; do
  echo "$(date -u +%FT%TZ) $TAG $part"
  "${R[@]}" backend uv run --no-sync --project web/backend python $E/code/check.py --part $part --tag "$TAG" --conc "${CONC:-8}" 2>&1 \
    | grep -v -i -e onnx -e '^  ' | tail -15
done
python3 $E/code/check.py --summarise --tag "$TAG" | tail -5
echo "$(date -u +%FT%TZ) $TAG done"
