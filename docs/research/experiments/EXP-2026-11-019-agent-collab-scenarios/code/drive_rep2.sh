#!/usr/bin/env bash
# EXP-2026-11-019: the third repetition (rep 2), after the coordinator freed
# model capacity at 08:40 UTC (up to 3 requests in flight). Replaces the tail
# of drive.sh, which was stopped while baseline rep 1 was running (that run
# was left to finish). Same time rule (Amendment 1), judged on pair 1's
# measured rate at one request in flight; same 11:15 UTC hard stop.
#   PAIR1_START=<epoch> bash .../code/drive_rep2.sh
set -u
E=docs/research/experiments/EXP-2026-11-019-agent-collab-scenarios
STOP=$(date -u -d "today 11:15" +%s)
RUNS=103
CONC=${CONC:-3}
until [ "$(wc -l < "$E/logs/runs_baseline_main.jsonl")" -ge $((2 * RUNS)) ] \
  && ! docker ps --format '{{.Names}}' | grep -qx exp019-baseline-rep1; do sleep 10; done
now=$(date -u +%s)
need=$(( (now - PAIR1_START) ))
echo "$(date -u +%FT%TZ) pair 1 took ${need}s at conc 1; $((STOP - now))s left"
if [ $(( now + need )) -gt "$STOP" ]; then echo "time rule: repetition 2 not run"; exit 0; fi
for arm in gate baseline; do
  left=$(( STOP - $(date -u +%s) ))
  if [ "$left" -le 60 ]; then echo "hard stop: $arm rep 2 not started"; exit 0; fi
  name="exp019-$arm-rep2"
  echo "$(date -u +%FT%TZ) start $arm rep 2 conc $CONC (timeout ${left}s)"
  timeout --signal=TERM "$left" docker compose run --rm --no-deps -T --name "$name" \
    --user "$(id -u):$(id -g)" -e HOME=/tmp -e SANDBOX_DB=mycelium_sandbox_exp019 \
    -e AGENT_PARALLEL_CALLS=0 -v "$PWD/docs/research:/app/docs/research" backend \
    uv run --no-sync --project web/backend python "$E/code/run019.py" \
    --arm "$arm" --reps 1 --rep-start 2 --conc "$CONC" --tag main
  rc=$?
  docker stop "$name" >/dev/null 2>&1 || true
  echo "$(date -u +%FT%TZ) end $arm rep 2 rc=$rc"
done
echo "$(date -u +%FT%TZ) all repetitions done"
