#!/usr/bin/env bash
# EXP-2026-11-027: the access test (EXP-2026-11-016 round two, through
# EXP-2026-11-022's replay) at three temperatures, product code frozen at
# 44100c04 (`git archive 44100c04 tools web/backend`, mounted read-only).
#
# One temperature at a time. Per temperature, six processes (seeds 101 202 303
# x arms gate prompt_only), 8 threads each = 48 in flight and 48 Postgres
# connections (54 with their main threads). Before each temperature the driver
#   * checks the relay lists the endpoint healthy and the model's self-report
#     matches $WHO (stops if it names another model);
#   * waits until Postgres connections in use + 54 stay under 95.
# Every harness writes into the staged copy of the research record
# ($RUN/stage/docs/research); `collect.sh` copies the new files back.
#
#   MODE=smoke bash $RUN/driver.sh                  # dry run, then one cell, T=0, label <prefix>smoke
#   setsid nohup bash $RUN/driver.sh > $RUN/driver.out 2>&1 < /dev/null &
# Variables: LLM (relay endpoint), NAME (operator-stated model), WHO (regex the
# self-report must match, lower case), PREFIX (label prefix; empty for the
# first model), TEMPS (order of the measured run).
# Progress: $RUN/status.txt (one line per step) and $RUN/driver.log.
set -u
REPO=/home/bdg20b/Projects/Mycelium
RUN=${RUN:-/home/bdg20b/Projects/Mycelium-runs/temperature-20261124}
STAGE=$RUN/stage
LOG=$RUN/driver.log
STATUS=$RUN/status.txt
MODE=${MODE:-run}
LLM=${LLM:-default-model}
NAME=${NAME:-Gemma 4 31B}
WHO=${WHO:-google|gemma}
PREFIX=${PREFIX:-}
TEMPS=${TEMPS:-0 0.7 0.2}
TIMEOUT=${TIMEOUT:-14400}
export COMPOSE_FILE=$REPO/compose.yaml COMPOSE_PROJECT_NAME=mycelium
cd "$STAGE" || exit 1
mkdir -p "$RUN/logs"
[ "$MODE" = run ] && echo $$ > "$RUN/driver.pid"
X=docs/research/experiments
E21=$X/EXP-2026-11-021-agent-model-check
E22=$X/EXP-2026-11-022-gemma-empty-replies-replay
E27=$X/EXP-2026-11-027-agent-gate-temperature
SNAP=$RUN/snap-44100c04
PY=(uv run --no-sync --project web/backend python)

log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG"; }
status() { echo "$(date -u +%FT%TZ) $*" >> "$STATUS"; log "STATUS $*"; }

label_of() {  # 0 -> t0, 0.2 -> t02, 0.7 -> t07
  echo "${PREFIX}t$(echo "$1" | tr -d .)"
}

# crun <container name> <timeout s> <output file> <temperature> <args…>
crun() {
  local name=$1 tmo=$2 out=$3 temp=$4; shift 4
  log "start $name (T=$temp, timeout ${tmo}s) -> $out"
  timeout --signal=TERM "$tmo" docker compose run --rm --no-deps -T --name "$name" \
    --user "$(id -u):$(id -g)" -e HOME=/tmp -e LLM_MODEL="$LLM" -e LLM_TEMPERATURE="$temp" \
    -e AGENT_PARALLEL_CALLS=0 -e EVAL_MODEL_NAME="$NAME" \
    -v "$SNAP/tools:/app/tools:ro" -v "$SNAP/web/backend:/app/web/backend:ro" \
    -v "$REPO/web/backend/media:/app/web/backend/media" \
    -v "$STAGE/docs/research:/app/docs/research" -v "$RUN/logs:/runlogs" \
    backend "${PY[@]}" "$@" < /dev/null 2>&1 | grep -v -i -e onnx -e '^  ' > "$out"
  local rc=${PIPESTATUS[0]}
  docker stop "$name" >/dev/null 2>&1 || true
  log "end $name rc=$rc ($(wc -l < "$out") lines)"
  return "$rc"
}

relay_health() {
  docker compose exec -T backend sh -c 'curl -s -m 30 http://llm-tunnel:9090/v1/models' 2>/dev/null \
    | LLM="$LLM" python3 -c '
import json, os, sys
try:
    d = json.load(sys.stdin)["data"]
    print(next((m["relay"]["health"] for m in d if m["id"] == os.environ["LLM"]), "absent"))
except Exception:
    print("unreadable")'
}

# gate_server <label>: 0 = healthy and the self-report matches $WHO. Exits the
# driver when the self-report names another model; returns 1 after an hour of
# an unhealthy or silent server.
gate_server() {
  local deadline=$(( $(date -u +%s) + 3600 )) h who
  while :; do
    h=$(relay_health)
    log "relay $LLM: $h"
    if [ "$h" = healthy ]; then
      crun "t-preflight-$$" 900 "$RUN/logs/preflight-$1.out" 0.2 "$E21/code/check.py" \
        --record-model /runlogs/preflight.jsonl --label "$1" >/dev/null
      who=$(tail -1 "$RUN/logs/preflight.jsonl" | WHO="$WHO" python3 -c '
import json, os, re, sys
r = json.loads(sys.stdin.read())
s = r.get("self_report")
c = ((s.get("content") or "") + " " + (s.get("reasoning") or "")) if isinstance(s, dict) else ""
c = c.lower()
print("match" if re.search(os.environ["WHO"], c) else ("none" if not c.strip() else "other"))')
      log "self-report: $who"
      [ "$who" = match ] && return 0
      if [ "$who" = other ]; then
        status "$1: NOT RUN - $LLM self-reports another model (logs/preflight.jsonl); driver stops"
        exit 3
      fi
    fi
    [ "$(date -u +%s)" -ge "$deadline" ] && { status "$1: NOT RUN - $LLM not healthy with a matching self-report within 1 h"; return 1; }
    sleep 120
  done
}

db_in_use() {
  docker compose exec -T postgres psql -U mycelium -d postgres -Atc "select count(*) from pg_stat_activity" 2>/dev/null || echo 999
}
wait_db_room() {  # <threads> <label>: wait (up to 2 h) for room under 95 connections
  local need=$1 deadline=$(( $(date -u +%s) + 7200 )) used
  while :; do
    used=$(db_in_use)
    [ $(( used + need )) -le 95 ] && { log "$2: postgres $used in use + $need <= 95"; return 0; }
    log "$2: postgres $used in use + $need > 95 (waiting)"
    [ "$(date -u +%s)" -ge "$deadline" ] && { status "$2: postgres never had room; NOT RUN"; return 1; }
    sleep 60
  done
}

one_temperature() {  # <temperature>
  local temp=$1 label seed arm
  label=$(label_of "$temp")
  gate_server "$label" || return 1
  wait_db_room 54 "$label" || return 1
  status "$label (T=$temp, $NAME on $LLM): start, 6 processes x 8"
  for seed in 101 202 303; do
    for arm in gate prompt_only; do
      ( crun "t-$label-$seed-$arm" "$TIMEOUT" "$RUN/logs/$label-$seed-$arm.out" "$temp" \
          "$E27/code/temp_replay.py" --label "$label" --expect "$temp" --seed "$seed" --arm "$arm" --reps 3 --conc 8
        echo "$?" > "$RUN/logs/$label-$seed-$arm.rc" ) &
      sleep 20
    done
  done
  wait
  for seed in 101 202 303; do
    for arm in gate prompt_only; do
      status "$label seed $seed $arm rc=$(cat "$RUN/logs/$label-$seed-$arm.rc" 2>/dev/null || echo '?') rows=$(wc -l < "$E22/logs/runs_${label}_s${seed}_$arm.jsonl" 2>/dev/null || echo 0) of 54"
    done
  done
}

if [ "$MODE" = smoke ]; then
  label=${PREFIX}smoke
  gate_server "$label" || exit 1
  wait_db_room 10 "$label" || exit 1
  status "$label: dry run (no model), seed 101 gate, T=0"
  crun "t-$label-dry" 1800 "$RUN/logs/$label-dry.out" 0 "$E27/code/temp_replay.py" \
    --label "$label" --expect 0 --seed 101 --arm gate --reps 1 --conc 8 --dry-run
  status "$label dry rc=$? rows=$(wc -l < "$E22/logs/runs_${label}_s101_gate_dry.jsonl" 2>/dev/null || echo 0) of 18"
  status "$label: one cell, seed 101 prompt_only, 1 repetition, T=0"
  crun "t-$label-101-prompt_only" 7200 "$RUN/logs/$label-101-prompt_only.out" 0 "$E27/code/temp_replay.py" \
    --label "$label" --expect 0 --seed 101 --arm prompt_only --reps 1 --conc 8
  status "$label cell rc=$? rows=$(wc -l < "$E22/logs/runs_${label}_s101_prompt_only.jsonl" 2>/dev/null || echo 0) of 18"
  exit 0
fi

status "driver start pid $$: $NAME on $LLM, temperatures $TEMPS, labels prefix '$PREFIX', snapshot 44100c04, stage $STAGE"
for t in $TEMPS; do
  one_temperature "$t"
  status "$(label_of "$t") returned"
done
status "driver finished"
