#!/usr/bin/env bash
# EXP-2026-11-026: every Mylo result in the demo paper that was measured on
# Gemma 4 31B and Qwen 3.8 27B, repeated on Inkling 2 Mini (relay endpoint
# default-model, operator-stated: 26B total / 3B active, NVFP4).
#
# Each part runs the harness that produced the paper's numbers, unchanged, on
# the product code frozen at the commit the earlier models were measured on
# (`git archive <commit> tools web/backend`, mounted read-only):
#   item1  EXP-2026-11-021 model check, tag ink ............... 640d7fe0, 8 in flight
#   item2  EXP-2026-11-010 latency, idle (inkidle) then 8 (inkp8) a99e1a01, 1 then 8
#   item3  EXP-2026-11-016 access probes via EXP-2026-11-022's
#          replay.py (code/ink_replay.py keeps the first reply), label ink, 3 seeds x 2 arms x 3 reps ..... 44100c04, 6 x 8 = 48
#   item4  EXP-2026-11-018 answers, gold/tag ink (531 jobs) ..... a99e1a01, 60
#   item5  EXP-2026-11-019 collaborator scenarios, tag maini .... a99e1a01, 60
#   item6  EXP-2026-11-017 memory lifecycle, tags ink_a..e ...... a99e1a01, 5 x 12 = 60
#   item7  EXP-2026-11-019 S1/S2/S10 after the fixes, tag r6i ... a99e1a01, 32
# Schedule: item1, item2 alone (item2 needs an idle server); then item4 with
# item3 (108 in flight); then item5 with item6 (120); then item7 (32). Never
# more than 120 requests in flight against a server rated for 128.
#
# Every harness writes into its own experiment folder, so the whole research
# record is first copied to $STAGE/docs/research and the containers mount that
# copy; the repository's record is never written by a run. `collect.sh` copies
# the new files back into this experiment's data/raw/ afterwards.
#
#   setsid nohup bash $RUN/driver.sh > $RUN/driver.out 2>&1 < /dev/null &
# Progress: $RUN/status.txt (one line per step) and $RUN/driver.log.
set -u
REPO=/home/bdg20b/Projects/Mycelium
RUN=${RUN:-/home/bdg20b/Projects/Mycelium-runs/inkling-20261121}
STAGE=$RUN/stage
LOG=$RUN/driver.log
STATUS=$RUN/status.txt
LLM=default-model
NAME="Inkling 2 Mini (26B-A3B, NVFP4)"
ITEMS=${ITEMS:-1 2 34 56 7}
export COMPOSE_FILE=$REPO/compose.yaml COMPOSE_PROJECT_NAME=mycelium
cd "$STAGE" || exit 1
echo $$ > "$RUN/driver.pid"
X=docs/research/experiments
E10=$X/EXP-2026-11-010-agent-loop-cost
E16=$X/EXP-2026-11-016-agent-gate-replication
E17=$X/EXP-2026-11-017-agent-memory-lifecycle
E18=$X/EXP-2026-11-018-agent-answers-gold
E19=$X/EXP-2026-11-019-agent-collab-scenarios
E21=$X/EXP-2026-11-021-agent-model-check
E22=$X/EXP-2026-11-022-gemma-empty-replies-replay
E26=$X/EXP-2026-11-026-inkling-2-mini-rerun
C=$E21/code/check.py
S16=$RUN/snap-44100c04 S21=$RUN/snap-640d7fe0 SA=$RUN/snap-a99e1a01
PY=(uv run --no-sync --project web/backend python)

# R <snapshot dir> [extra docker args…]: the one-off backend container, as the earlier runs.
R() {
  local snap=$1; shift
  docker compose run --rm --no-deps -T --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -e LLM_MODEL="$LLM" -e EVAL_MODEL_NAME="$NAME" \
    -v "$snap/tools:/app/tools:ro" -v "$snap/web/backend:/app/web/backend:ro" \
    -v "$REPO/web/backend/media:/app/web/backend/media" \
    -v "$STAGE/docs/research:/app/docs/research" -v "$RUN/logs:/runlogs" "$@"
}

log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$LOG"; }
status() { echo "$(date -u +%FT%TZ) $*" >> "$STATUS"; log "STATUS $*"; }

# crun <container name> <timeout s> <output file> <snapshot> <args after the common ones…>
crun() {
  local name=$1 tmo=$2 out=$3 snap=$4; shift 4
  log "start $name (timeout ${tmo}s) -> $out"
  timeout --signal=TERM "$tmo" docker compose run --rm --no-deps -T --name "$name" \
    --user "$(id -u):$(id -g)" -e HOME=/tmp -e LLM_MODEL="$LLM" -e EVAL_MODEL_NAME="$NAME" \
    -v "$snap/tools:/app/tools:ro" -v "$snap/web/backend:/app/web/backend:ro" \
    -v "$REPO/web/backend/media:/app/web/backend/media" \
    -v "$STAGE/docs/research:/app/docs/research" -v "$RUN/logs:/runlogs" \
    "$@" < /dev/null 2>&1 | grep -v -i -e onnx -e '^  ' > "$out"
  local rc=${PIPESTATUS[0]}
  docker stop "$name" >/dev/null 2>&1 || true
  log "end $name rc=$rc ($(wc -l < "$out") lines)"
  return "$rc"
}

record_model() {  # <jsonl path inside the container> <label>
  R "$SA" backend "${PY[@]}" "$C" --record-model "$1" --label "$2" < /dev/null 2>&1 \
    | grep -v -i -e onnx -e '^  ' | tail -1 | cut -c1-400 >> "$LOG"
}

relay_health() {
  docker compose exec -T backend sh -c 'curl -s -m 30 http://llm-tunnel:9090/v1/models' 2>/dev/null \
    | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)["data"]
    print(next((m["relay"]["health"] for m in d if m["id"] == "default-model"), "absent"))
except Exception:
    print("unreadable")'
}

# wait_server <max s>: 0 = healthy and self-reports Inkling; 1 = gave up; 2 = another model.
wait_server() {
  local deadline=$(( $(date -u +%s) + $1 )) h who
  while :; do
    h=$(relay_health)
    log "relay default-model: $h"
    if [ "$h" = healthy ]; then
      record_model /runlogs/preflight.jsonl preflight
      who=$(tail -1 "$RUN/logs/preflight.jsonl" | python3 -c '
import json, sys
r = json.loads(sys.stdin.read())
s = r.get("self_report")
c = ((s.get("content") or "") + " " + (s.get("reasoning") or "")) if isinstance(s, dict) else ""
c = c.lower()
print("inkling" if any(w in c for w in ("inkling", "thinking machines")) else ("none" if not c.strip() else "other"))')
      log "self-report: $who"
      [ "$who" = inkling ] && return 0
      [ "$who" = other ] && return 2
    fi
    [ "$(date -u +%s)" -ge "$deadline" ] && return 1
    sleep 120
  done
}

wait_healthy() {  # <max s>: the relay listing only (between repetitions)
  local deadline=$(( $(date -u +%s) + $1 )) h
  while :; do
    h=$(relay_health)
    [ "$h" = healthy ] && return 0
    log "relay default-model: $h (waiting)"
    [ "$(date -u +%s)" -ge "$deadline" ] && return 1
    sleep 120
  done
}

gate_server() {  # <max s> <label>
  wait_server "$1"
  case $? in
    0) return 0 ;;
    2) status "$2: NOT RUN - default-model self-reports another model (logs/preflight.jsonl); driver stops"; exit 3 ;;
    *) status "$2: NOT RUN - default-model not healthy with an Inkling self-report within the wait"; return 1 ;;
  esac
}

# -- item1: EXP-2026-11-021 model check (Appendix C, Table 4) ---------------------------
item1() {
  status "item1 EXP-021 model check (ink): start"
  local part
  for part in demo gate; do
    crun "i-021-$part" 3600 "$RUN/logs/021-ink-$part.out" "$S21" -e AGENT_PARALLEL_CALLS=0 backend \
      "${PY[@]}" "$C" --part "$part" --tag ink --conc 8
    status "item1 $part rc=$? $(tail -2 "$RUN/logs/021-ink-$part.out" | tr '\n' ' ' | cut -c1-200)"
  done
  python3 "$C" --summarise --tag ink > "$RUN/logs/021-ink-summary.out" 2>&1
  status "item1 summarise rc=$? $(tail -3 "$RUN/logs/021-ink-summary.out" | tr '\n' ' ' | cut -c1-300)"
}

# -- item2: EXP-2026-11-010 latency, idle then 8 at once (section 4.5) -----------------
item2() {
  status "item2 EXP-010 latency: start (idle, 3 repetitions, then 8 processes)"
  record_model "$E10/logs/model_ink.jsonl" start
  crun i-010-idle 7200 "$RUN/logs/010-inkidle.out" "$SA" backend \
    "${PY[@]}" "$E10/code/run_a6.py" --reps 3 --tag inkidle --stop-at 11:40
  status "item2 idle rc=$? rows=$(wc -l < "$E10/data/a2_inkidle.jsonl" 2>/dev/null || echo 0)"
  local k
  for k in 0 1 2 3 4 5 6 7; do
    crun "i-010-p8-$k" 7200 "$RUN/logs/010-inkp8-$k.out" "$SA" backend \
      "${PY[@]}" "$E10/code/run_a6.py" --reps 1 --rotate "$k" --tag inkp8 --stop-at 11:40 &
  done
  wait
  python3 "$E10/code/stamp_process_arm.py" inkp8 8 >> "$LOG" 2>&1
  status "item2 p8 rows=$(wc -l < "$E10/data/a2_inkp8.jsonl" 2>/dev/null || echo 0)"
  record_model "$E10/logs/model_ink.jsonl" end
}

# -- item3: EXP-2026-11-016 access probes, through EXP-2026-11-022's replay (4.1, Table 2)
item3() {
  status "item3 EXP-016 access probes via ink_replay.py (label ink): start"
  local seed arm
  for seed in 101 202 303; do
    for arm in gate prompt_only; do
      ( crun "i-016-$seed-$arm" 14400 "$RUN/logs/016-ink-$seed-$arm.out" "$S16" -e AGENT_PARALLEL_CALLS=0 backend \
          "${PY[@]}" "$E26/code/ink_replay.py" --label ink --seed "$seed" --arm "$arm" --reps 3 --conc 8
        echo "$?" > "$RUN/logs/016-ink-$seed-$arm.rc" ) &
      sleep 20
    done
  done
  wait
  for seed in 101 202 303; do
    for arm in gate prompt_only; do
      status "item3 seed $seed $arm rc=$(cat "$RUN/logs/016-ink-$seed-$arm.rc" 2>/dev/null || echo '?') rows=$(wc -l < "$E22/logs/runs_ink_s${seed}_$arm.jsonl" 2>/dev/null || echo 0)"
    done
  done
}

# -- item4: EXP-2026-11-018 answers against stored facts (4.4, Table 1) -----------------
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
  status "item4 EXP-018 answers (ink): waiting for a window clear of midnight UTC and the nightly"
  until ok_window; do sleep 300; done
  status "item4 EXP-018 answers (ink): start"
  crun i-018-gold 3600 "$RUN/logs/018-ink-gold.out" "$SA" -e R4_GOLD=ink backend "${PY[@]}" "$E/code/r4.py" gold
  status "item4 gold rc=$? $(tail -1 "$RUN/logs/018-ink-gold.out" | cut -c1-200)"
  if ! R4_GOLD=ink python3 "$E/code/r4.py" jobs > "$E/code/jobs_ink.txt" || [ ! -s "$E/code/jobs_ink.txt" ]; then
    status "item4: FAILED to write jobs_ink.txt"; return 1
  fi
  if cmp -s "$E/code/jobs_ink.txt" "$E/code/jobs_r7.txt"; then status "item4 jobs_ink.txt = jobs_r7.txt"
  else status "item4 jobs_ink.txt DIFFERS from jobs_r7.txt: $(tr ',' '\n' < "$E/code/jobs_ink.txt" | wc -l) jobs"; fi
  stop=$(date -u -d "@$(( $(date -u +%s) + 4 * 3600 ))" '+%F %T')
  SNAP=$SA TAG=ink LLM=$LLM EVAL_MODEL_NAME="$NAME" CONC=60 STOP_AT="$stop" \
    bash "$E/code/drive_r4.sh" >> "$RUN/logs/018-ink-drive.out" 2>&1 < /dev/null
  status "item4 drive rc=$? rows=$(wc -l < "$E/data/runs_ink.jsonl" 2>/dev/null || echo 0)"
  {
    R4_GOLD=ink R4_TAG=ink python3 "$E/code/r4.py" grade; echo "rc=$?"
    R4_GOLD=ink R4_TAG=ink python3 "$E/code/r4.py" grade --first-attempt; echo "rc=$?"
    R4_GOLD=ink R4_TAG=ink python3 "$E/code/r4.py" partial; echo "rc=$?"
    python3 "$E/code/r5_counts.py" ink r7 r6g; echo "rc=$?"
  } > "$RUN/logs/018-ink-grade.out" 2>&1
  status "item4 grading: $(grep -c '^rc=0' "$RUN/logs/018-ink-grade.out") of 4 steps rc=0"
  crun i-018-gold-end 3600 "$RUN/logs/018-inkend-gold.out" "$SA" -e R4_GOLD=inkend backend "${PY[@]}" "$E/code/r4.py" gold
  if python3 - "$E/data/gold_ink.json" "$E/data/gold_inkend.json" <<'EOF'
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
key = lambda d: json.dumps(d.get("questions"), sort_keys=True)
sys.exit(0 if key(a) == key(b) else 1)
EOF
  then status "item4 gold at the end = gold at the start"
  else status "item4 gold at the end DIFFERS from the start (gold_ink.json, gold_inkend.json)"; fi
  crun i-018-cleanup 1800 "$RUN/logs/018-ink-cleanup.out" "$SA" backend "${PY[@]}" "$E/code/cleanup.py"
  status "item4 cleanup rc=$? $(tail -1 "$RUN/logs/018-ink-cleanup.out" | cut -c1-200)"
}

# -- item5: EXP-2026-11-019 collaborator scenarios, gate vs baseline (4.2, Table 3) ----
item5() {
  local tag=maini db=mycelium_sandbox_exp019maini E=$E19 rc arm rep
  status "item5 EXP-019 collaborator scenarios ($tag): start"
  record_model "$E/logs/model_$tag.jsonl" start
  if ! docker compose exec -T postgres psql -U mycelium -d postgres -q \
      -c "CREATE DATABASE \"$db\" TEMPLATE \"mycelium_sandbox\"" >> "$LOG" 2>&1; then
    status "item5: FAILED to create $db"; return 1
  fi
  crun "i-019-$tag-setup" 3600 "$RUN/logs/019-$tag-setup.out" "$SA" -e AGENT_PARALLEL_CALLS=0 \
    -e AMBIENT_EXTRACT_CONCURRENCY=1 -e SANDBOX_DB="$db" backend \
    "${PY[@]}" "$E/code/run019_q.py" setup --tag "$tag"
  rc=$?
  if [ "$rc" != 0 ]; then status "item5: setup/preflight FAILED rc=$rc"; return 1; fi
  for rep in 0 1 2; do
    for arm in gate baseline; do
      wait_healthy 3600 || status "item5 $arm rep $rep: relay not healthy after 1 h; running anyway"
      crun "i-019-$tag-$arm-$rep" 7200 "$RUN/logs/019-$tag-$arm-$rep.out" "$SA" -e AGENT_PARALLEL_CALLS=0 \
        -e AMBIENT_EXTRACT_CONCURRENCY=1 -e SANDBOX_DB="$db" backend \
        "${PY[@]}" "$E/code/run019_q.py" run --arm "$arm" --reps 1 --rep-start "$rep" --conc 60 --tag "$tag"
      status "item5 $arm rep $rep rc=$? rows=$(wc -l < "$E/logs/runs_${arm}_$tag.jsonl" 2>/dev/null || echo 0)"
    done
  done
  crun "i-019-$tag-regrade" 3600 "$RUN/logs/019-$tag-regrade.out" "$SA" -e SANDBOX_DB="$db" backend \
    "${PY[@]}" "$E/code/run019_q.py" regrade --tag "$tag"
  status "item5 regrade rc=$?"
  crun "i-019-$tag-recall" 3600 "$RUN/logs/019-$tag-recall.out" "$SA" -e SANDBOX_DB="$db" backend \
    "${PY[@]}" "$E/code/run019_q.py" recall --tag "$tag"
  status "item5 recall rc=$?"
  python3 "$E/code/analyse_q.py" "$tag" > "$RUN/logs/019-$tag-analyse.out" 2>&1
  status "item5 analyse rc=$?"
  record_model "$E/logs/model_$tag.jsonl" end
}

# -- item6: EXP-2026-11-017 memory lifecycle (4.5) --------------------------------------
item6() {
  local E=$E17 db=mycelium_agent_eval_r2_lifecycle_ink rc p
  status "item6 EXP-017 lifecycle (ink): start"
  record_model "$E/logs/model_ink.jsonl" start
  crun i-017-setup 3600 "$RUN/logs/017-ink-setup.out" "$SA" -e AGENT_PARALLEL_CALLS=0 \
    -e AMBIENT_EXTRACT_CONCURRENCY=1 -e LIFECYCLE_DB="$db" backend \
    "${PY[@]}" "$E26/code/lifecycle_ink.py" --fresh-db --probes "" --conc 1 --tag ink_setup
  rc=$?
  if [ "$rc" != 0 ]; then status "item6: setup FAILED rc=$rc"; return 1; fi
  declare -A PROBES=(
    [a]=delete_thread [b]=delete_obs [c]=delete_thread_production,optout
    [d]=message,forget,excluded [e]=isolation )
  declare -A SEED=( [a]=20261121 [b]=20261122 [c]=20261123 [d]=20261124 [e]=20261125 )
  for p in a b c d e; do
    ( crun "i-017-$p" 25200 "$RUN/logs/017-ink-$p.out" "$SA" -e AGENT_PARALLEL_CALLS=0 \
        -e AMBIENT_EXTRACT_CONCURRENCY=1 -e LIFECYCLE_DB="$db" backend \
        "${PY[@]}" "$E26/code/lifecycle_ink.py" --probes "${PROBES[$p]}" --conc 12 \
        --tag "ink_$p" --seed "${SEED[$p]}"
      echo "$?" > "$RUN/logs/017-ink-$p.rc" ) &
    sleep 30
  done
  wait
  for p in a b c d e; do
    status "item6 process $p (${PROBES[$p]}) rc=$(cat "$RUN/logs/017-ink-$p.rc" 2>/dev/null || echo '?') rows=$(wc -l < "$E/logs/lifecycle_ink_$p.jsonl" 2>/dev/null || echo 0)"
  done
  python3 "$E/code/analyse_q.py" ink > "$RUN/logs/017-ink-analyse.out" 2>&1
  status "item6 analyse rc=$?"
  record_model "$E/logs/model_ink.jsonl" end
}

# -- item7: EXP-2026-11-019 S1/S2/S10 after the two S1 fixes (4.3) ----------------------
item7() {
  local E=$E19
  status "item7 EXP-019 r6 repeat (r6i): start"
  record_model "$E/logs/model_r6i.jsonl" start
  SNAP=$SA TAG=r6i LLM=$LLM EVAL_MODEL_NAME="$NAME" CONC=32 \
    STOP_AT="$(date -u -d "@$(( $(date -u +%s) + 4 * 3600 ))" '+%F %T')" \
    bash "$E/code/drive_r4.sh" >> "$RUN/logs/019-r6i-drive.out" 2>&1 < /dev/null
  status "item7 drive rc=$? ($(cat "$E"/logs/runs_r3_*_instance_r6i.jsonl 2>/dev/null | wc -l) log lines)"
  python3 "$E/code/analyse_r4.py" r6i > "$RUN/logs/019-r6i-analyse.out" 2>&1
  status "item7 analyse rc=$?"
  record_model "$E/logs/model_r6i.jsonl" end
}

status "driver start pid $$ items: $ITEMS; snapshots 44100c04 640d7fe0 a99e1a01; stage $STAGE"
gate_server 3600 "start" || { status "driver: server never came up; stopping"; exit 1; }
for i in $ITEMS; do
  gate_server 3600 "item$i" || continue
  case $i in
    34) item4 & p4=$!; sleep 60; item3; wait $p4 ;;
    56) item5 & p5=$!; sleep 60; item6; wait $p5 ;;
    *) "item$i" ;;
  esac
  status "item$i returned"
done
status "driver finished"
