#!/usr/bin/env bash
# EXP-2026-11-010 Amendment 9: arm A7 (idle, then 8 processes) on the instance
# model, from a frozen copy of the commit under test.
#   SNAP=<dir> EVAL_MODEL_NAME='…' bash docs/research/experiments/EXP-2026-11-010-agent-loop-cost/code/drive_a7.sh
set -u
E=docs/research/experiments/EXP-2026-11-010-agent-loop-cost
C=docs/research/experiments/EXP-2026-11-021-agent-model-check/code/check.py
R=(docker compose run --rm --no-deps -T --user "$(id -u):$(id -g)" -e HOME=/tmp
   -e LLM_MODEL="${LLM:-default-model}"
   -e EVAL_MODEL_NAME="${EVAL_MODEL_NAME:-not stated by the operator}"
   -v "$SNAP/tools:/app/tools:ro" -v "$SNAP/web/backend:/app/web/backend:ro"
   -v "$PWD/web/backend/media:/app/web/backend/media"
   -v "$PWD/docs/research:/app/docs/research")
STOP_HM=${STOP_HM:-11:40}   # the container clock is UTC; run_a2 --stop-at reads it
"${R[@]}" backend uv run --no-sync --project web/backend python $C --record-model $E/logs/model_a7.jsonl --label start 2>&1 | tail -1 | cut -c1-200
# What fits before the hard stop (Amendment 9, added 07:05 UTC): the idle arm
# first, with as many repetitions as the time left allows; the 8-process arm
# only if at least 80 minutes are left after it.
mins_left() { echo $(( ( $(date -u -d "today $STOP_HM" +%s) - $(date -u +%s) ) / 60 )); }
left=$(mins_left)
if   [ "$left" -ge 70 ]; then reps=3
elif [ "$left" -ge 50 ]; then reps=2
elif [ "$left" -ge 25 ]; then reps=1
else reps=0; fi
reps=${IDLE_REPS:-$reps}
echo "$(date -u +%FT%TZ) a7idle: $left minutes left, $reps repetition(s)"
if [ "$reps" -gt 0 ]; then
  "${R[@]}" backend uv run --no-sync --project web/backend python $E/code/run_a6.py --reps "$reps" --tag a7idle --stop-at "$STOP_HM" 2>&1 | grep -v -i -e onnx -e '^  ' | tail -40
fi
left=$(mins_left)
if [ "$left" -ge 80 ]; then
  echo "$(date -u +%FT%TZ) a7p8: $left minutes left"
  for k in 0 1 2 3 4 5 6 7; do
    "${R[@]}" --name "a7p8-$k" backend uv run --no-sync --project web/backend python $E/code/run_a6.py --reps 1 --rotate $k --tag a7p8 --stop-at "$STOP_HM" > "$E/logs/a7p8-$k.out" 2>&1 &
  done
  wait
  python3 $E/code/stamp_process_arm.py a7p8 8
else
  echo "$(date -u +%FT%TZ) a7p8 not run: $left minutes left (needs 80)"
fi
"${R[@]}" backend uv run --no-sync --project web/backend python $C --record-model $E/logs/model_a7.jsonl --label end 2>&1 | tail -1 | cut -c1-200
echo "$(date -u +%FT%TZ) a7 done"
