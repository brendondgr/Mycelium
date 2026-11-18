#!/usr/bin/env bash
# 2026-11-18: four results measured on Gemma 4 31B, repeated on Qwen 3.8 27B
# (relay endpoint default-model-2, operator-stated), in priority order:
#   1. EXP-2026-11-019 Amendment 10 — round two's counted run (gate vs baseline), tag mainq
#   2. EXP-2026-11-017 Amendment 3  — memory lifecycle probes, logs lifecycle_qwen_*
#   3. EXP-2026-11-019 Amendment 11 — r6's run after the two S1 fixes, tag r6q
#   4. EXP-2026-11-018 Amendment 10 — the full answers run after the feed fix, tag r7
# Code under test: a frozen `git archive a99e1a01` of tools/ and web/backend/,
# mounted read-only. At most 64 model requests in flight on default-model-2.
# Runs detached from the session (setsid nohup) from a copy in the run folder:
#   setsid nohup bash $RUN/driver.sh > $RUN/driver.out 2>&1 < /dev/null &
# Progress: $RUN/status.txt (one line per step) and $RUN/driver.log.
set -u
REPO=/home/bdg20b/Projects/Mycelium
RUN=/home/bdg20b/Projects/Mycelium-runs/qwen-20261118
SNAP=$RUN/snap
LOG=$RUN/driver.log
STATUS=$RUN/status.txt
LLM=default-model-2
NAME="Qwen 3.8 27B"
ITEMS=${ITEMS:-1 2 3 4}
cd "$REPO" || exit 1
echo $$ > "$RUN/driver.pid"
E17=docs/research/experiments/EXP-2026-11-017-agent-memory-lifecycle
E18=docs/research/experiments/EXP-2026-11-018-agent-answers-gold
E19=docs/research/experiments/EXP-2026-11-019-agent-collab-scenarios
C=docs/research/experiments/EXP-2026-11-021-agent-model-check/code/check.py
R=(docker compose run --rm --no-deps -T --user "$(id -u):$(id -g)" -e HOME=/tmp
   -e LLM_MODEL="$LLM" -e AGENT_PARALLEL_CALLS=0 -e EVAL_MODEL_NAME="$NAME"
   -e AMBIENT_EXTRACT_CONCURRENCY=1
   -v "$SNAP/tools:/app/tools:ro" -v "$SNAP/web/backend:/app/web/backend:ro"
   -v "$REPO/web/backend/media:/app/web/backend/media"
   -v "$REPO/docs/research:/app/docs/research" -v "$RUN/logs:/runlogs")
PY=(uv run --no-sync --project web/backend python)

log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG"; }
status() { echo "$(date -u +%FT%TZ) $*" >> "$STATUS"; log "STATUS $*"; }

# crun <container name> <timeout s> <output file> <docker compose run args after the common ones…>
crun() {
  local name=$1 tmo=$2 out=$3; shift 3
  log "start $name (timeout ${tmo}s) -> $out"
  timeout --signal=TERM "$tmo" "${R[@]}" --name "$name" "$@" < /dev/null 2>&1 \
    | grep -v -i -e onnx -e '^  ' > "$out"
  local rc=${PIPESTATUS[0]}
  docker stop "$name" >/dev/null 2>&1 || true
  log "end $name rc=$rc ($(wc -l < "$out") lines)"
  return "$rc"
}

record_model() {  # <jsonl path relative to the repo or /runlogs/…> <label>
  "${R[@]}" backend "${PY[@]}" "$C" --record-model "$1" --label "$2" < /dev/null 2>&1 \
    | grep -v -i -e onnx -e '^  ' | tail -1 | cut -c1-400 >> "$LOG"
}

relay_health() {
  docker compose exec -T backend sh -c 'curl -s -m 30 http://llm-tunnel:9090/v1/models' 2>/dev/null \
    | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)["data"]
    print(next((m["relay"]["health"] for m in d if m["id"] == "default-model-2"), "absent"))
except Exception:
    print("unreadable")'
}

# wait_server <max seconds>: 0 = healthy and self-reports Qwen; 1 = gave up; 2 = another model.
wait_server() {
  local deadline=$(( $(date -u +%s) + $1 )) h who
  while :; do
    h=$(relay_health)
    log "relay default-model-2: $h"
    if [ "$h" = healthy ]; then
      record_model /runlogs/preflight.jsonl preflight
      who=$(tail -1 "$RUN/logs/preflight.jsonl" | python3 -c '
import json, sys
r = json.loads(sys.stdin.read())
s = r.get("self_report")
c = ((s.get("content") or "") + " " + (s.get("reasoning") or "")) if isinstance(s, dict) else ""
c = c.lower()
print("qwen" if any(w in c for w in ("qwen", "alibaba", "tongyi")) else ("none" if not c.strip() else "other"))')
      log "self-report: $who"
      [ "$who" = qwen ] && return 0
      [ "$who" = other ] && return 2
    fi
    [ "$(date -u +%s)" -ge "$deadline" ] && return 1
    sleep 120
  done
}

# wait_healthy <max seconds>: the relay listing only (between repetitions).
wait_healthy() {
  local deadline=$(( $(date -u +%s) + $1 )) h
  while :; do
    h=$(relay_health)
    [ "$h" = healthy ] && return 0
    log "relay default-model-2: $h (waiting)"
    [ "$(date -u +%s)" -ge "$deadline" ] && return 1
    sleep 120
  done
}

gate_server() {  # <max seconds> <label>
  wait_server "$1"
  local rc=$?
  case $rc in
    0) return 0 ;;
    2) status "$2: NOT RUN - default-model-2 self-reports another model (see logs/preflight.jsonl); driver stops"; exit 3 ;;
    *) status "$2: NOT RUN - default-model-2 not healthy with a Qwen self-report within the wait"; return 1 ;;
  esac
}

# -- 1. EXP-2026-11-019 Amendment 10: round two's counted run, tag mainq -----------------
item1() {
  local tag=mainq db=mycelium_sandbox_exp019mainq E=$E19 rc arm rep
  status "item1 EXP-019 A10 ($tag): start"
  record_model "$E/logs/model_$tag.jsonl" start
  if ! docker compose exec -T postgres psql -U mycelium -d postgres -q \
      -c "CREATE DATABASE \"$db\" TEMPLATE \"mycelium_sandbox\"" >> "$LOG" 2>&1; then
    status "item1: FAILED to create $db"; return 1
  fi
  crun "q-019-$tag-setup" 3600 "$RUN/logs/019-$tag-setup.out" -e SANDBOX_DB="$db" backend \
    "${PY[@]}" "$E/code/run019_q.py" setup --tag "$tag"
  rc=$?
  tail -4 "$RUN/logs/019-$tag-setup.out" >> "$LOG"
  if [ "$rc" != 0 ]; then status "item1: setup/preflight FAILED rc=$rc"; return 1; fi
  for arm in gate baseline; do  # the registered dry runs (no model), as round two's procedure
    crun "q-019-$tag-dry-$arm" 3600 "$RUN/logs/019-$tag-dry-$arm.out" -e SANDBOX_DB="$db" backend \
      "${PY[@]}" "$E/code/run019_q.py" run --arm "$arm" --dry-run --reps 1 --conc 8 --tag dry2q
    status "item1 dry $arm rc=$?"
  done
  for rep in 0 1 2; do
    for arm in gate baseline; do
      wait_healthy 3600 || status "item1 $arm rep $rep: relay not healthy after 1 h; running anyway"
      crun "q-019-$tag-$arm-$rep" 7200 "$RUN/logs/019-$tag-$arm-$rep.out" -e SANDBOX_DB="$db" backend \
        "${PY[@]}" "$E/code/run019_q.py" run --arm "$arm" --reps 1 --rep-start "$rep" --conc 60 --tag "$tag"
      rc=$?
      status "item1 $arm rep $rep rc=$rc rows=$(wc -l < "$E/logs/runs_${arm}_$tag.jsonl" 2>/dev/null || echo 0)"
    done
  done
  crun "q-019-$tag-regrade" 3600 "$RUN/logs/019-$tag-regrade.out" -e SANDBOX_DB="$db" backend \
    "${PY[@]}" "$E/code/run019_q.py" regrade --tag "$tag"
  status "item1 regrade rc=$?"
  crun "q-019-$tag-recall" 3600 "$RUN/logs/019-$tag-recall.out" -e SANDBOX_DB="$db" backend \
    "${PY[@]}" "$E/code/run019_q.py" recall --tag "$tag"
  status "item1 recall rc=$?"
  python3 "$E/code/analyse_q.py" "$tag" > "$RUN/logs/019-$tag-analyse.out" 2>&1
  status "item1 analyse rc=$? (data/metrics_$tag.json, tables/summary_$tag.md)"
  record_model "$E/logs/model_$tag.jsonl" end
  status "item1 EXP-019 A10 ($tag): done"
}

# -- 2. EXP-2026-11-017 Amendment 3: the lifecycle probes, logs lifecycle_qwen_* ---------
item2() {
  local E=$E17 db=mycelium_agent_eval_r2_lifecycle_qwen rc p
  status "item2 EXP-017 A3 (qwen): start"
  record_model "$E/logs/model_qwen.jsonl" start
  crun q-017-setup 3600 "$RUN/logs/017-qwen-setup.out" -e LIFECYCLE_DB="$db" backend \
    "${PY[@]}" "$E/code/lifecycle_q.py" --fresh-db --probes "" --conc 1 --tag qwen_setup
  rc=$?
  if [ "$rc" != 0 ]; then status "item2: setup FAILED rc=$rc"; return 1; fi
  declare -A PROBES=(
    [a]=delete_thread [b]=delete_obs [c]=delete_thread_production,optout
    [d]=message,forget,excluded [e]=isolation )
  declare -A SEED=( [a]=20261118 [b]=20261119 [c]=20261120 [d]=20261121 [e]=20261122 )
  for p in a b c d e; do
    ( crun "q-017-$p" 25200 "$RUN/logs/017-qwen-$p.out" -e LIFECYCLE_DB="$db" backend \
        "${PY[@]}" "$E/code/lifecycle_q.py" --probes "${PROBES[$p]}" --conc 12 \
        --tag "qwen_$p" --seed "${SEED[$p]}"
      echo "$?" > "$RUN/logs/017-qwen-$p.rc" ) &
    sleep 30
  done
  wait
  for p in a b c d e; do
    status "item2 process $p (${PROBES[$p]}) rc=$(cat "$RUN/logs/017-qwen-$p.rc" 2>/dev/null || echo '?') rows=$(wc -l < "$E/logs/lifecycle_qwen_$p.jsonl" 2>/dev/null || echo 0)"
  done
  python3 "$E/code/analyse_q.py" qwen > "$RUN/logs/017-qwen-analyse.out" 2>&1
  status "item2 analyse rc=$? (data/metrics_qwen.json, tables/summary_qwen.md)"
  record_model "$E/logs/model_qwen.jsonl" end
  status "item2 EXP-017 A3 (qwen): done"
}

# -- 3. EXP-2026-11-019 Amendment 11: r6's run on Qwen, tag r6q -------------------------
item3() {
  local E=$E19
  status "item3 EXP-019 A11 (r6q): start"
  record_model "$E/logs/model_r6q.jsonl" start
  SNAP=$SNAP TAG=r6q LLM=$LLM EVAL_MODEL_NAME="$NAME" CONC=32 STOP_AT="2026-11-19 18:00" \
    bash "$RUN/copies/drive_r4_019.sh" >> "$RUN/logs/019-r6q-drive.out" 2>&1 < /dev/null
  status "item3 drive rc=$? ($(cat "$E"/logs/runs_r3_*_instance_r6q.jsonl 2>/dev/null | wc -l) log lines)"
  python3 "$E/code/analyse_r4.py" r6q > "$RUN/logs/019-r6q-analyse.out" 2>&1
  status "item3 analyse rc=$? (data/metrics_r6q.json, tables/r6q_outcomes.md)"
  record_model "$E/logs/model_r6q.jsonl" end
  status "item3 EXP-019 A11 (r6q): done"
}

# -- 4. EXP-2026-11-018 Amendment 10: the full run, tag r7 ------------------------------
ok_window() {  # gold and run on one UTC day, clear of the nightly (12:00 UTC)
  local hm
  hm=$((10#$(date -u +%H%M)))
  systemctl is-active --quiet mylo-daily.service && return 1
  [ "$hm" -ge 2200 ] && return 1
  [ "$hm" -ge 1000 ] && [ "$hm" -lt 1530 ] && return 1
  return 0
}
item4() {
  local E=$E18 stop
  status "item4 EXP-018 A10 (r7): waiting for a window clear of midnight UTC and the nightly"
  until ok_window; do sleep 300; done
  gate_server 3600 "item4" || return 1
  status "item4 EXP-018 A10 (r7): start"
  crun q-018-gold 3600 "$RUN/logs/018-r7-gold.out" -e R4_GOLD=r7 backend "${PY[@]}" "$E/code/r4.py" gold
  status "item4 gold rc=$? $(tail -1 "$RUN/logs/018-r7-gold.out" | cut -c1-200)"
  if ! R4_GOLD=r7 python3 "$E/code/r4.py" jobs > "$E/code/jobs_r7.txt" || [ ! -s "$E/code/jobs_r7.txt" ]; then
    status "item4: FAILED to write jobs_r7.txt"; return 1
  fi
  if cmp -s "$E/code/jobs_r7.txt" "$E/code/jobs_r5g.txt"; then status "item4 jobs_r7.txt = jobs_r5g.txt (531 jobs)"
  else status "item4 jobs_r7.txt DIFFERS from jobs_r5g.txt: $(tr ',' '\n' < "$E/code/jobs_r7.txt" | wc -l) jobs"; fi
  stop=$(date -u -d "@$(( $(date -u +%s) + 4 * 3600 ))" '+%F %T')
  SNAP=$SNAP TAG=r7 LLM=$LLM EVAL_MODEL_NAME="$NAME" CONC=60 STOP_AT="$stop" \
    bash "$RUN/copies/drive_r4_018.sh" >> "$RUN/logs/018-r7-drive.out" 2>&1 < /dev/null
  status "item4 drive rc=$? rows=$(wc -l < "$E/data/runs_r7.jsonl" 2>/dev/null || echo 0)"
  {
    R4_GOLD=r7 R4_TAG=r7 python3 "$E/code/r4.py" grade; echo "rc=$?"
    R4_GOLD=r7 R4_TAG=r7 python3 "$E/code/r4.py" grade --first-attempt; echo "rc=$?"
    R4_GOLD=r7 R4_TAG=r7 python3 "$E/code/r4.py" partial; echo "rc=$?"
    python3 "$E/code/r5_counts.py" r7 r5 r5g r6g; echo "rc=$?"
  } > "$RUN/logs/018-r7-grade.out" 2>&1
  status "item4 grading: $(grep -c '^rc=0' "$RUN/logs/018-r7-grade.out") of 4 steps rc=0 (data/metrics_r7.json, tables/summary_r7.md)"
  crun q-018-gold-end 3600 "$RUN/logs/018-r7end-gold.out" -e R4_GOLD=r7end backend "${PY[@]}" "$E/code/r4.py" gold
  if python3 - "$E/data/gold_r7.json" "$E/data/gold_r7end.json" <<'EOF'
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
key = lambda d: json.dumps(d.get("questions"), sort_keys=True)
sys.exit(0 if key(a) == key(b) else 1)
EOF
  then status "item4 gold at the end = gold at the start (gold_r7end.json)"
  else status "item4 gold at the end DIFFERS from the start (compare gold_r7.json, gold_r7end.json)"; fi
  crun q-018-cleanup 1800 "$RUN/logs/018-r7-cleanup.out" backend "${PY[@]}" "$E/code/cleanup.py"
  status "item4 cleanup rc=$? $(tail -1 "$RUN/logs/018-r7-cleanup.out" | cut -c1-200)"
  status "item4 EXP-018 A10 (r7): done"
}

status "driver start pid $$ items: $ITEMS; frozen code a99e1a01 at $SNAP"
gate_server 10800 "start" || { status "driver: server never came up; stopping"; exit 1; }
for i in $ITEMS; do
  if [ "$i" != 1 ]; then gate_server 7200 "item$i" || continue; fi
  "item$i"
  status "item$i returned rc=$?"
done
status "driver finished"
