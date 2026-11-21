#!/usr/bin/env bash
# EXP-2026-11-026: stall watchdog for the run's containers (added after
# Amendment 3, where one model request stayed open for two hours with no reply).
#
# Every INTERVAL seconds it reads each experiment container's network counters
# (`docker stats`). A container whose counters have not changed for STALL_MIN
# minutes is waiting on nothing that moves. Before acting, the watchdog sends
# the model one tiny request:
#   * the server answers within 60 s -> the container is stuck, not the server:
#     it is stopped (its driver step then returns and the run moves on) and a
#     "STALL … stopped" line goes to status.txt, to be rerun by hand;
#   * the server does not answer -> nothing is stopped ("STALL … server not
#     answering; left running"), since every container would look the same.
# It never touches the live stack's containers (names starting `mycelium-`).
# Runs until the driver writes "driver finished" and no experiment container is
# left, or until $RUN/watchdog.stop exists.
#
#   setsid nohup bash $RUN/watchdog.sh > $RUN/watchdog.out 2>&1 < /dev/null &
set -u
REPO=/home/bdg20b/Projects/Mycelium
RUN=${RUN:-/home/bdg20b/Projects/Mycelium-runs/inkling-20261121}
STATUS=$RUN/status.txt
LOG=$RUN/watchdog.log
INTERVAL=${INTERVAL:-120}
STALL_MIN=${STALL_MIN:-20}
PATTERN=${PATTERN:-'^(i-|ink-|r6i-)'}
export COMPOSE_FILE=$REPO/compose.yaml COMPOSE_PROJECT_NAME=mycelium
cd "$REPO" || exit 1
echo $$ > "$RUN/watchdog.pid"
declare -A NET SINCE WARNED

log() { echo "$(date -u +%FT%TZ) $*" >> "$LOG"; }
status() { echo "$(date -u +%FT%TZ) $*" >> "$STATUS"; log "STATUS $*"; }

server_answers() {  # 0 if the model answers a tiny request within 60 s
  docker compose exec -T backend sh -c 'curl -s -m 60 -o /dev/null -w "%{http_code}" \
    http://llm-tunnel:9090/v1/chat/completions -H "Content-Type: application/json" \
    -d "{\"model\":\"default-model\",\"max_tokens\":40,\"thinking_token_budget\":16,\"messages\":[{\"role\":\"user\",\"content\":\"Reply with: ok\"}]}"' \
    2>/dev/null | grep -q '^200$'
}

log "watchdog start pid $$ interval ${INTERVAL}s stall ${STALL_MIN} min pattern $PATTERN"
while :; do
  [ -e "$RUN/watchdog.stop" ] && { log "stop file found; exiting"; exit 0; }
  now=$(date -u +%s)
  seen=0
  while IFS='|' read -r name net; do
    [ -z "$name" ] && continue
    echo "$name" | grep -Eq "$PATTERN" || continue
    seen=1
    if [ "${NET[$name]:-}" != "$net" ]; then
      NET[$name]=$net; SINCE[$name]=$now; WARNED[$name]=; continue
    fi
    quiet=$(( (now - ${SINCE[$name]}) / 60 ))
    [ "$quiet" -lt "$STALL_MIN" ] && continue
    if server_answers; then
      status "STALL $name: no network activity for $quiet min while the model answers; stopped (rerun this piece)"
      docker stop -t 10 "$name" >/dev/null 2>&1
      unset "NET[$name]" "SINCE[$name]" "WARNED[$name]"
    elif [ -z "${WARNED[$name]:-}" ]; then
      status "STALL $name: no network activity for $quiet min, but the model is not answering either; left running"
      WARNED[$name]=1
    fi
  done < <(docker stats --no-stream --format '{{.Name}}|{{.NetIO}}' 2>/dev/null)
  if [ "$seen" = 0 ] && grep -q "driver finished" "$STATUS" 2>/dev/null; then
    log "driver finished and no experiment container left; exiting"; exit 0
  fi
  sleep "$INTERVAL"
done
