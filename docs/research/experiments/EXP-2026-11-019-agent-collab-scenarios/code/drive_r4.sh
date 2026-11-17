#!/usr/bin/env bash
# EXP-2026-11-019 Amendment 7: S1, S2, S10, repeated and fresh mode side by
# side, three repetitions, on the model behind LLM (default: default-model-2),
# from a frozen copy of the commit under test.
#   SNAP=<dir> EVAL_MODEL_NAME='Gemma 4 31B' bash …/code/drive_r4.sh
set -u
E=docs/research/experiments/EXP-2026-11-019-agent-collab-scenarios
LLM=${LLM:-default-model-2}
TAG=${TAG:-r4}
STOP=$(date -u -d "${STOP_AT:-today 11:40}" +%s)
declare -A DB=( [repeated]=mycelium_sandbox_exp019r4rep [fresh]=mycelium_sandbox_exp019r4fresh )
run() {  # name db args...
  local name=$1 db=$2; shift 2
  local left=$(( STOP - $(date -u +%s) ))
  if [ "$left" -le 60 ]; then echo "hard stop: $name not started"; return 1; fi
  echo "$(date -u +%FT%TZ) start $name"
  timeout --signal=TERM "$left" docker compose run --rm --no-deps -T --name "$name" \
    --user "$(id -u):$(id -g)" -e HOME=/tmp -e SANDBOX_DB="$db" -e LLM_MODEL="$LLM" \
    -e AGENT_PARALLEL_CALLS=0 -e EVAL_MODEL_NAME="${EVAL_MODEL_NAME:-not stated by the operator}" \
    -v "$SNAP/tools:/app/tools:ro" -v "$SNAP/web/backend:/app/web/backend:ro" \
    -v "$PWD/web/backend/media:/app/web/backend/media" \
    -v "$PWD/docs/research:/app/docs/research" backend \
    uv run --no-sync --project web/backend python "$E/code/run019_r4.py" "$@" 2>&1 \
    | grep -v -i -e onnx -e '^  ' > "$E/logs/$name.out"
  local rc=${PIPESTATUS[0]}
  docker stop "$name" >/dev/null 2>&1 || true
  echo "$(date -u +%FT%TZ) end $name rc=$rc ($(wc -l < "$E/logs/$name.out") lines)"
}
if [ -z "${SKIP_SETUP:-}" ]; then
  for mode in repeated fresh; do
    docker compose exec -T postgres psql -U mycelium -d postgres -q \
      -c "CREATE DATABASE \"${DB[$mode]}\" TEMPLATE \"mycelium_sandbox\"" || exit 2
    cp "$E/data/world_r3_$mode.json" "/tmp/world_r3_$mode.keep.json"
    run "$TAG-019-setup-$mode" "${DB[$mode]}" --mode "$mode" --setup
    mv "$E/data/world_r3_$mode.json" "$E/data/world_${TAG}_$mode.json"   # this run's world
    cp "/tmp/world_r3_$mode.keep.json" "$E/data/world_r3_$mode.json"     # round three's, untouched
    tail -4 "$E/logs/$TAG-019-setup-$mode.out"
  done
fi
mode() {
  for rep in ${REPS:-0 1 2}; do
    run "$TAG-019-$1-$rep" "${DB[$1]}" --mode "$1" --rep "$rep" --conc "${CONC:-8}" --tag "$TAG" || return 0
  done
}
mode repeated &
mode fresh &
wait
echo "$(date -u +%FT%TZ) $TAG done"
