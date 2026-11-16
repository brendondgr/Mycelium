#!/usr/bin/env bash
# EXP-2026-11-010 Amendment 6 (round three, Phase 3): A6 idle, then 8 processes.
#   EVAL_MODEL_NAME='…' bash docs/research/experiments/EXP-2026-11-010-agent-loop-cost/code/drive_a6.sh
set -u
E=docs/research/experiments/EXP-2026-11-010-agent-loop-cost
C=docs/research/experiments/EXP-2026-11-021-agent-model-check/code/check.py
R=(docker compose run --rm --no-deps -T --user "$(id -u):$(id -g)" -e HOME=/tmp
   -e EVAL_MODEL_NAME="${EVAL_MODEL_NAME:-not stated by the operator}"
   -v "$PWD/docs/research:/app/docs/research")
STOP_HM=${STOP_HM:-11:15}   # the container clock is UTC; run_a2 --stop-at reads it
"${R[@]}" backend uv run --no-sync --project web/backend python $C --record-model $E/logs/model_a6.jsonl --label start 2>&1 | tail -1
echo "$(date -u +%FT%TZ) a6idle"
"${R[@]}" backend uv run --no-sync --project web/backend python $E/code/run_a6.py --reps 3 --tag a6idle --stop-at "$STOP_HM" 2>&1 | grep -v -i -e onnx -e '^  '
echo "$(date -u +%FT%TZ) a6p8"
for k in 0 1 2 3 4 5 6 7; do
  "${R[@]}" --name "a6p8-$k" backend uv run --no-sync --project web/backend python $E/code/run_a6.py --reps 1 --rotate $k --tag a6p8 --stop-at "$STOP_HM" > "$E/logs/a6p8-$k.out" 2>&1 &
done
wait
grep -h -v -i -e onnx -e '^  ' $E/logs/a6p8-*.out | tail -100
python3 $E/code/stamp_process_arm.py a6p8 8
"${R[@]}" backend uv run --no-sync --project web/backend python $C --record-model $E/logs/model_a6.jsonl --label end 2>&1 | tail -1
echo "$(date -u +%FT%TZ) phase 3 done"
