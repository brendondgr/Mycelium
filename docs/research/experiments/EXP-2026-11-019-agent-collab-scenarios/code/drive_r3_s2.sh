#!/usr/bin/env bash
# Round three on the second server (EXP-2026-11-019 Amendment 6, EXP-2026-11-016
# Amendment 4): every container runs with LLM_MODEL=default-model-2, so the
# instance route answers from the second server. Repeated and fresh modes run
# side by side (each repetition's 30 turns at once: 60 in flight), then the
# three gate seeds side by side (7 per repetition each: 21 in flight).
# Hard stop 11:15 UTC.
#   EVAL_MODEL_NAME='…' bash docs/research/experiments/EXP-2026-11-019-agent-collab-scenarios/code/drive_r3_s2.sh
set -u
E19=docs/research/experiments/EXP-2026-11-019-agent-collab-scenarios
E16=docs/research/experiments/EXP-2026-11-016-agent-gate-replication
LLM=${LLM_MODEL_S2:-default-model-2}
STOP=$(date -u -d "${STOP_AT:-tomorrow 11:15}" +%s)
[ "$(date -u +%H)" -lt 11 ] && [ -z "${STOP_AT:-}" ] && STOP=$(date -u -d "today 11:15" +%s)
MODEL_NAME=${EVAL_MODEL_NAME:-not stated by the operator}
go() {  # name db script args...
  local name=$1 db=$2; shift 2
  local left=$(( STOP - $(date -u +%s) ))
  if [ "$left" -le 60 ]; then echo "hard stop: $name not started"; return 1; fi
  echo "$(date -u +%FT%TZ) start $name (timeout ${left}s)"
  timeout --signal=TERM "$left" docker compose run --rm --no-deps -T --name "$name" \
    --user "$(id -u):$(id -g)" -e HOME=/tmp ${db:+-e SANDBOX_DB=$db} -e LLM_MODEL="$LLM" \
    -e AGENT_PARALLEL_CALLS=0 -e EVAL_MODEL_NAME="$MODEL_NAME" \
    -v "$PWD/docs/research:/app/docs/research" backend \
    uv run --no-sync --project web/backend python "$@" 2>&1 | grep -v -i -e onnx -e '^  ' > "/tmp/$name.out"
  local rc=${PIPESTATUS[0]}
  docker stop "$name" >/dev/null 2>&1 || true
  echo "$(date -u +%FT%TZ) end $name rc=$rc ($(wc -l < /tmp/$name.out) lines)"
}
mode() {  # mode db
  for rep in 0 1 2; do
    go "r3s2-019-$1-$rep" "$2" "$E19/code/run019_r3.py" --mode "$1" --rep "$rep" --conc 32 --tag r3 || return 0
  done
}
mode repeated mycelium_sandbox_exp019r3rep &
mode fresh mycelium_sandbox_exp019r3fresh &
wait
for seed in 101 202 303; do
  go "r3s2-016-gate-$seed" "" "$E16/code/run_gate_r3.py" --seed "$seed" --reps 3 --conc 8 --tag r3 &
done
wait
echo "$(date -u +%FT%TZ) phase 1 done"
