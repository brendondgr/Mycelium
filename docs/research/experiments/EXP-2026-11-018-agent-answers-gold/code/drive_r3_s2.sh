#!/usr/bin/env bash
# EXP-2026-11-018 Amendment 5 (round three, Phase 2, second server): the answers, 64 in
# flight, the model recorded at the start and the end, hard stop 11:15 UTC.
#   EVAL_MODEL_NAME='…' bash docs/research/experiments/EXP-2026-11-018-agent-answers-gold/code/drive_r3.sh
set -u
E=docs/research/experiments/EXP-2026-11-018-agent-answers-gold
C=docs/research/experiments/EXP-2026-11-021-agent-model-check/code/check.py
STOP=$(date -u -d "${STOP_AT:-tomorrow 11:15}" +%s)
[ "$(date -u +%H)" -lt 11 ] && [ -z "${STOP_AT:-}" ] && STOP=$(date -u -d "today 11:15" +%s)
R=(docker compose run --rm --no-deps -T --user "$(id -u):$(id -g)" -e HOME=/tmp
   -e LLM_MODEL="${LLM_MODEL_S2:-default-model-2}" -e AGENT_PARALLEL_CALLS=0 -e EVAL_MODEL_NAME="${EVAL_MODEL_NAME:-not stated by the operator}"
   -v "$PWD/docs/research:/app/docs/research")
"${R[@]}" backend uv run --no-sync --project web/backend python $C --record-model $E/logs/model_r3.jsonl --label start 2>&1 | tail -1
left=$(( STOP - $(date -u +%s) ))
echo "$(date -u +%FT%TZ) start phase 2 (timeout ${left}s)"
timeout --signal=TERM "$left" "${R[@]}" --name r3s2-018-run backend uv run --no-sync --project web/backend \
  python $E/code/run.py --conc 64 --out data/runs_r3.jsonl --only "$(cat $E/code/jobs_r3.txt)" 2>&1 \
  | grep -v -i -e onnx -e '^  ' -e arm_c_catalog
docker stop r3s2-018-run >/dev/null 2>&1 || true
"${R[@]}" backend uv run --no-sync --project web/backend python $C --record-model $E/logs/model_r3.jsonl --label end 2>&1 | tail -1
echo "$(date -u +%FT%TZ) phase 2 done"
