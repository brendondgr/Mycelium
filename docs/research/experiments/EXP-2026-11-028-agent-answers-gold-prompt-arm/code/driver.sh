#!/usr/bin/env bash
# EXP-2026-11-028: answer accuracy, rules in code against rules in the prompt,
# on the sandbox database only (PROTOCOL.md). Product code frozen at a99e1a01.
#
#   MODE=check bash $RUN/driver.sh   # sandbox check (committed), gold on the sandbox (tag $TAG)
#   MODE=smoke bash $RUN/driver.sh   # three jobs per arm, tag smoke; kept, not counted
#   setsid nohup bash $RUN/driver.sh > $RUN/driver.out 2>&1 < /dev/null &   # the measured run, then grading
# Variables: LLM, NAME, WHO (regex the self-report must match), TAG, CONC.
# Every harness writes into the staged copy of the research record.
set -u
REPO=/home/bdg20b/Projects/Mycelium
RUN=${RUN:-/home/bdg20b/Projects/Mycelium-runs/answers-20261124}
STAGE=$RUN/stage
LOG=$RUN/driver.log
STATUS=$RUN/status.txt
MODE=${MODE:-run}
LLM=${LLM:-default-model}
NAME=${NAME:-Gemma 4 31B}
WHO=${WHO:-google|gemma}
TAG=${TAG:-s28}
CONC=${CONC:-30}
SB=${SANDBOX_DB:-mycelium_sandbox_exp028}
export COMPOSE_FILE=$REPO/compose.yaml COMPOSE_PROJECT_NAME=mycelium
cd "$STAGE" || exit 1
mkdir -p "$RUN/logs"
X=docs/research/experiments
E18=$X/EXP-2026-11-018-agent-answers-gold
E21=$X/EXP-2026-11-021-agent-model-check
E28=$X/EXP-2026-11-028-agent-answers-gold-prompt-arm
SNAP=$RUN/snap-a99e1a01
PY=(uv run --no-sync --project web/backend python)

log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG"; }
status() { echo "$(date -u +%FT%TZ) $*" >> "$STATUS"; log "STATUS $*"; }

# crun <container name> <timeout s> <output file> <args…>: always on the sandbox
crun() {
  local name=$1 tmo=$2 out=$3; shift 3
  log "start $name (timeout ${tmo}s) -> $out"
  timeout --signal=TERM "$tmo" docker compose run --rm --no-deps -T --name "$name" \
    --user "$(id -u):$(id -g)" -e HOME=/tmp -e LLM_MODEL="$LLM" -e AGENT_PARALLEL_CALLS=0 \
    -e EVAL_MODEL_NAME="$NAME" -e SANDBOX_DB="$SB" -e R4_GOLD="$TAG" \
    -v "$SNAP/tools:/app/tools:ro" -v "$SNAP/web/backend:/app/web/backend:ro" \
    -v "$REPO/web/backend/media:/app/web/backend/media" \
    -v "$STAGE/docs/research:/app/docs/research" -v "$RUN/logs:/runlogs" \
    backend "${PY[@]}" "$@" < /dev/null 2>&1 | grep -v -i -e onnx -e '^  ' > "$out"
  local rc=${PIPESTATUS[0]}
  docker stop "$name" >/dev/null 2>&1 || true
  log "end $name rc=$rc ($(wc -l < "$out") lines)"
  return "$rc"
}

record_model() {  # <label>: relay listing and self-report; 0 only if the self-report matches $WHO
  crun "a-model-$$" 900 "$RUN/logs/model-$1.out" "$E21/code/check.py" \
    --record-model "$E28/logs/model_$TAG.jsonl" --label "$1" >/dev/null
  tail -1 "$E28/logs/model_$TAG.jsonl" | WHO="$WHO" python3 -c '
import json, os, re, sys
r = json.loads(sys.stdin.read())
s = r.get("self_report")
c = ((s.get("content") or "") + " " + (s.get("reasoning") or "")).lower() if isinstance(s, dict) else ""
sys.exit(0 if re.search(os.environ["WHO"], c) else 1)'
}

db_in_use() {
  docker compose exec -T postgres psql -U mycelium -d postgres -Atc "select count(*) from pg_stat_activity" 2>/dev/null || echo 999
}
wait_db_room() {  # <threads>: wait (up to 3 h) for room under 95 connections
  local need=$1 deadline=$(( $(date -u +%s) + 10800 )) used
  while :; do
    used=$(db_in_use)
    [ $(( used + need )) -le 95 ] && { log "postgres $used in use + $need <= 95"; return 0; }
    log "postgres $used in use + $need > 95 (waiting)"
    [ "$(date -u +%s)" -ge "$deadline" ] && { status "postgres never had room; NOT RUN"; return 1; }
    sleep 60
  done
}

two_arms() {  # <tag> <timeout s> [extra args…]: the two arms side by side
  local tag=$1 tmo=$2 arm; shift 2
  for arm in code prompt; do
    ( crun "a-$tag-$arm" "$tmo" "$RUN/logs/$tag-$arm.out" "$E28/code/run_arms.py" run \
        --arm "$arm" --tag "$tag" --conc "$CONC" "$@"
      echo "$?" > "$RUN/logs/$tag-$arm.rc" ) &
    sleep 5
  done
  wait
  for arm in code prompt; do
    status "$tag $arm rc=$(cat "$RUN/logs/$tag-$arm.rc" 2>/dev/null || echo '?') rows=$(wc -l < "$E18/data/runs_${tag}_$arm.jsonl" 2>/dev/null || echo 0)"
  done
}

mkdir -p "$E28/logs"
case $MODE in
check)
  crun a-check 900 "$RUN/logs/check.out" "$E28/code/check_sandbox.py"
  rc=$?
  sed -n '/^{/,$p' "$RUN/logs/check.out" > "$E28/logs/check_sandbox.json"
  status "sandbox check rc=$rc"
  [ "$rc" = 0 ] || exit 1
  crun a-gold 3600 "$RUN/logs/gold.out" "$E28/code/run_arms.py" gold
  status "gold ($TAG) rc=$? $(tail -1 "$RUN/logs/gold.out" | cut -c1-300)"
  ;;
smoke)
  record_model smoke || { status "smoke: NOT RUN - the self-report does not match '$WHO'"; exit 3; }
  wait_db_room 10 || exit 1
  only=$(python3 - "$E18/data/gold_$TAG.json" <<'PY'
import json, sys
qs = json.load(open(sys.argv[1]))["questions"]
ids = [q["id"] for q in qs] if isinstance(qs, list) else list(qs)
pick = [next(i for i in ids if i.startswith(k)) for k in ("p", "j", "f")]
print(",".join(f"1:{i}" for i in pick))
PY
)
  status "smoke: jobs $only per arm"
  CONC=3 two_arms smoke 3600 --only "$only"
  ;;
run)
  echo $$ > "$RUN/driver.pid"
  status "driver start pid $$: $NAME on $LLM, tag $TAG, $CONC threads per arm, sandbox $SB, snapshot a99e1a01"
  record_model start || { status "NOT RUN - the self-report does not match '$WHO'"; exit 3; }
  wait_db_room $(( 2 * CONC + 2 )) || exit 1
  two_arms "$TAG" 14400
  record_model end || status "the self-report at the end does not match '$WHO'"
  cat "$E18/data/runs_${TAG}_code.jsonl" "$E18/data/runs_${TAG}_prompt.jsonl" > "$E18/data/runs_$TAG.jsonl"
  {
    R4_GOLD=$TAG R4_TAG=$TAG python3 "$E18/code/r4.py" grade; echo "rc=$?"
    R4_GOLD=$TAG R4_TAG=$TAG python3 "$E18/code/r4.py" grade --first-attempt; echo "rc=$?"
    R4_GOLD=$TAG R4_TAG=$TAG python3 "$E18/code/r4.py" partial; echo "rc=$?"
  } > "$RUN/logs/$TAG-grade.out" 2>&1
  status "grading: $(grep -c '^rc=0' "$RUN/logs/$TAG-grade.out") of 3 steps rc=0"
  crun a-check-end 900 "$RUN/logs/check-end.out" "$E28/code/check_sandbox.py"
  status "sandbox check at the end rc=$?"
  sed -n '/^{/,$p' "$RUN/logs/check-end.out" > "$E28/logs/check_sandbox_end.json"
  status "driver finished"
  ;;
esac
