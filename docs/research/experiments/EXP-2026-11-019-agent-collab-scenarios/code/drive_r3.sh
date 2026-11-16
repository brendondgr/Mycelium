#!/usr/bin/env bash
# Round three, Phase 1 (EXP-2026-11-019 Amendment 4, EXP-2026-11-016 Amendment 2):
# every counted run, one container at a time (at most 4 Mylo turns in flight),
# with a hard stop at 11:15 UTC so nothing overlaps the 12:00 UTC nightly run.
#   EVAL_MODEL_NAME='…' bash docs/research/experiments/EXP-2026-11-019-agent-collab-scenarios/code/drive_r3.sh
# Run from the repository root on the host.
set -u
E19=docs/research/experiments/EXP-2026-11-019-agent-collab-scenarios
E16=docs/research/experiments/EXP-2026-11-016-agent-gate-replication
STOP=$(date -u -d "${STOP_AT:-tomorrow 11:15}" +%s)
[ "$(date -u +%H)" -lt 11 ] && [ -z "${STOP_AT:-}" ] && STOP=$(date -u -d "today 11:15" +%s)
MODEL_NAME=${EVAL_MODEL_NAME:-not stated by the operator}
go() {  # name db script args...
  local name=$1 db=$2; shift 2
  local left=$(( STOP - $(date -u +%s) ))
  if [ "$left" -le 60 ]; then echo "hard stop: $name not started"; return 1; fi
  echo "$(date -u +%FT%TZ) start $name (timeout ${left}s)"
  timeout --signal=TERM "$left" docker compose run --rm --no-deps -T --name "$name" \
    --user "$(id -u):$(id -g)" -e HOME=/tmp ${db:+-e SANDBOX_DB=$db} \
    -e AGENT_PARALLEL_CALLS=0 -e EVAL_MODEL_NAME="$MODEL_NAME" \
    -v "$PWD/docs/research:/app/docs/research" backend \
    uv run --no-sync --project web/backend python "$@" 2>&1 | grep -v -i -e onnx -e '^  '
  local rc=${PIPESTATUS[0]}
  docker stop "$name" >/dev/null 2>&1 || true
  echo "$(date -u +%FT%TZ) end $name rc=$rc"
}
for rep in 0 1 2; do
  go "r3-019-repeated-$rep" mycelium_sandbox_exp019r3rep "$E19/code/run019_r3.py" --mode repeated --rep "$rep" --conc 4 --tag r3 || exit 0
done
for rep in 0 1 2; do
  go "r3-019-fresh-$rep" mycelium_sandbox_exp019r3fresh "$E19/code/run019_r3.py" --mode fresh --rep "$rep" --conc 4 --tag r3 || exit 0
done
for seed in 101 202 303; do
  go "r3-016-gate-$seed" "" "$E16/code/run_gate_r3.py" --seed "$seed" --reps 3 --conc 4 --tag r3 || exit 0
done
echo "$(date -u +%FT%TZ) phase 1 done"
