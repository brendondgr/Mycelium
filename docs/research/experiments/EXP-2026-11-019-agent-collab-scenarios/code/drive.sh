#!/usr/bin/env bash
# EXP-2026-11-019: the counted runs after the gate arm's first repetition, with
# PROTOCOL.md's time rule (Amendment 1) and the 11:15 UTC hard stop.
#   bash docs/research/experiments/EXP-2026-11-019-agent-collab-scenarios/code/drive.sh <first_rep_to_run_for_baseline>
# Run from the repository root on the host.
set -u
E=docs/research/experiments/EXP-2026-11-019-agent-collab-scenarios
STOP=$(date -u -d "today 11:15" +%s)
RUNS=103
run() {  # arm rep
  local left=$(( STOP - $(date -u +%s) ))
  if [ "$left" -le 60 ]; then echo "hard stop: $1 rep $2 not started"; return 1; fi
  echo "$(date -u +%FT%TZ) start $1 rep $2 (timeout ${left}s)"
  local name="exp019-$1-rep$2"
  timeout --signal=TERM "$left" docker compose run --rm --no-deps -T --name "$name" \
    --user "$(id -u):$(id -g)" -e HOME=/tmp -e SANDBOX_DB=mycelium_sandbox_exp019 \
    -e AGENT_PARALLEL_CALLS=0 -v "$PWD/docs/research:/app/docs/research" backend \
    uv run --no-sync --project web/backend python "$E/code/run019.py" \
    --arm "$1" --reps 1 --rep-start "$2" --conc 1 --tag main
  local rc=$?
  # A TERM to compose may leave the container running: stop it at the hard stop.
  docker stop "$name" >/dev/null 2>&1 || true
  echo "$(date -u +%FT%TZ) end $1 rep $2 rc=$rc"
  return $rc
}
rep=${1:-0}
# The baseline's first repetition (the gate's ran before this script).
pair_start=${PAIR_START:-$(date -u +%s)}
run baseline "$rep" || exit 0
while [ "$rep" -lt 2 ]; do
  now=$(date -u +%s)
  per_run=$(( (now - pair_start) / (2 * RUNS) ))
  need=$(( per_run * 2 * RUNS ))
  echo "$(date -u +%FT%TZ) pair $rep took $((now - pair_start))s (${per_run}s/run); next pair needs ~${need}s, $((STOP - now))s left"
  if [ $(( now + need )) -gt "$STOP" ]; then echo "time rule: repetition $((rep + 1)) not run"; exit 0; fi
  rep=$((rep + 1))
  pair_start=$(date -u +%s)
  run gate "$rep" || exit 0
  run baseline "$rep" || exit 0
done
echo "$(date -u +%FT%TZ) all repetitions done"
