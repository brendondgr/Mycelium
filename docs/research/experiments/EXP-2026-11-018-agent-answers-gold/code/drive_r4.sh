#!/usr/bin/env bash
# EXP-2026-11-018 Amendment 6: the answers after the overnight fixes, 8 in
# flight on the instance model, from a frozen copy of the commit under test.
#   SNAP=<dir with tools/ and web/backend/ of the commit> EVAL_MODEL_NAME='…' \
#   bash docs/research/experiments/EXP-2026-11-018-agent-answers-gold/code/drive_r4.sh
set -u
E=docs/research/experiments/EXP-2026-11-018-agent-answers-gold
C=docs/research/experiments/EXP-2026-11-021-agent-model-check/code/check.py
STOP=$(date -u -d "${STOP_AT:-today 11:40}" +%s)
R=(docker compose run --rm --no-deps -T --user "$(id -u):$(id -g)" -e HOME=/tmp
   -e LLM_MODEL="${LLM:-default-model}" -e AGENT_PARALLEL_CALLS=0
   -e EVAL_MODEL_NAME="${EVAL_MODEL_NAME:-not stated by the operator}"
   -v "$SNAP/tools:/app/tools:ro" -v "$SNAP/web/backend:/app/web/backend:ro"
   -v "$PWD/web/backend/media:/app/web/backend/media"
   -v "$PWD/docs/research:/app/docs/research")
TAG=${TAG:-r4}
"${R[@]}" backend uv run --no-sync --project web/backend python $C --record-model $E/logs/model_$TAG.jsonl --label start 2>&1 | tail -1 | cut -c1-200
left=$(( STOP - $(date -u +%s) ))
echo "$(date -u +%FT%TZ) start (timeout ${left}s)"
timeout --signal=TERM "$left" "${R[@]}" --name "$TAG-018-run" backend uv run --no-sync --project web/backend \
  python $E/code/run.py --conc "${CONC:-8}" --out data/runs_$TAG.jsonl --only "$(cat $E/code/jobs_$TAG.txt)" 2>&1 \
  | grep -v -i -e onnx -e '^  ' -e arm_c_catalog
docker stop "$TAG-018-run" >/dev/null 2>&1 || true
"${R[@]}" backend uv run --no-sync --project web/backend python $C --record-model $E/logs/model_$TAG.jsonl --label end 2>&1 | tail -1 | cut -c1-200
echo "$(date -u +%FT%TZ) done"
