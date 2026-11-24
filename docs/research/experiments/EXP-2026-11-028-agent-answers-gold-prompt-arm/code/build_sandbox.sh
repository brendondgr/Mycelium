#!/usr/bin/env bash
# EXP-2026-11-028: build the sandbox database by allow-list.
#
# A fresh database, migrated by the frozen product code (a99e1a01), then filled
# with rows copied from the live database: the public corpus whole, and of
# everything that belongs to a person or an organisation only the rows of the
# fictional demo world (accounts at @showcase.mycelium.invalid, the demo lab
# and department, the demo lab's two projects). A table that is not named
# below stays as `migrate` left it: no chat thread, observation, integration
# row, audit event or non-demo account is ever copied. Primary keys are kept,
# because the frozen questions name corpus items by id.
#
# The live database is only read (COPY … TO STDOUT). Run from the repository
# root, once; it refuses to run if the sandbox database already exists.
#
#   bash docs/research/experiments/EXP-2026-11-028-agent-answers-gold-prompt-arm/code/build_sandbox.sh
set -euo pipefail
REPO=/home/bdg20b/Projects/Mycelium
RUN=${RUN:-/home/bdg20b/Projects/Mycelium-runs/answers-20261124}
SNAP=$RUN/snap-a99e1a01
LIVE=mycelium
SB=${SANDBOX_DB:-mycelium_sandbox_exp028}
[[ $SB =~ ^mycelium_sandbox_[a-z0-9]+$ ]] || { echo "refusing: $SB is not a sandbox name"; exit 2; }
export COMPOSE_FILE=$REPO/compose.yaml COMPOSE_PROJECT_NAME=mycelium
PSQL=(docker compose exec -T postgres psql -U mycelium -v ON_ERROR_STOP=1)
live() { "${PSQL[@]}" -d "$LIVE" -Atc "$1"; }
sb() { "${PSQL[@]}" -d "$SB" -Atc "$1"; }
say() { echo "$(date -u +%FT%TZ) $*"; }

if [ "$("${PSQL[@]}" -d postgres -Atc "select count(*) from pg_database where datname='$SB'")" != 0 ]; then
  echo "refusing: database $SB already exists"; exit 2
fi
say "create $SB"
"${PSQL[@]}" -d postgres -q -c "CREATE DATABASE \"$SB\""

say "migrate with the frozen code (a99e1a01)"
docker compose run --rm --no-deps -T --user "$(id -u):$(id -g)" -e HOME=/tmp -e SANDBOX_DB="$SB" \
  -v "$SNAP/tools:/app/tools:ro" -v "$SNAP/web/backend:/app/web/backend:ro" \
  -v "$REPO/web/backend/media:/app/web/backend/media" backend \
  uv run --no-sync --project web/backend python -c '
import sys
sys.path[:0] = ["/app/web/backend", "/app"]
from sandbox.collab import bootstrap
bootstrap.setup()
from django.core.management import call_command
call_command("migrate", verbosity=0)
from django.db import connection
print("migrated", connection.settings_dict["NAME"])' < /dev/null 2>&1 | grep -v -i -e onnx -e '^  ' | tail -3

# The demo world, identified in the live database.
DU="(select id from auth_user where email ilike '%@showcase.mycelium.invalid')"
L="(select lab_id from demo_demoworld where key='default')"
D="(select department_id from demo_demoworld where key='default')"
P="(select id from research_project where scope_lab_id = $L)"
EDGES="(user_id in $DU or lab_id = $L or project_id in $P)"
CONCEPTS="(select concept_id from knowledge_edge where $EDGES)"

# copy <table> <where> [replica]: the sandbox's column list, read from live.
# With "replica" the sandbox session skips triggers (the corpus's stored search
# vector is copied as it is, not recomputed); otherwise foreign keys are
# checked when each copy commits, so a row pointing at something that was not
# copied stops the build.
copy() {
  local t=$1 where=$2 mode=${3:-} cols n
  cols=$(sb "select string_agg(quote_ident(column_name), ',' order by ordinal_position) from information_schema.columns where table_schema='public' and table_name='$t'")
  [ -n "$cols" ] || { echo "no such table in the sandbox: $t"; exit 1; }
  [ "$(sb "select count(*) from $t")" = 0 ] || { echo "sandbox table $t is not empty"; exit 1; }
  "${PSQL[@]}" -d "$LIVE" -c "COPY (SELECT $cols FROM $t WHERE $where) TO STDOUT" \
    | "${PSQL[@]}" -d "$SB" -q ${mode:+-c "SET session_replication_role = replica"} -c "COPY $t($cols) FROM STDIN"
  n=$(sb "select count(*) from $t")
  say "copied $t: $n rows"
  echo "$t $n" >> "$RUN/logs/sandbox_copied.txt"
}
: > "$RUN/logs/sandbox_copied.txt"

# -- the demo world (people and organisations) ----------------------------------
copy auth_user                    "id in $DU"
copy accounts_department          "id = $D"
copy accounts_lab                 "id = $L"
copy accounts_profile             "user_id in $DU"
copy accounts_watchpreference     "user_id in $DU"
copy accounts_deptprofile         "department_id = $D"
copy accounts_deptmembership      "department_id = $D and user_id in $DU"
copy accounts_labprofile          "lab_id = $L"
copy accounts_labwatchpreference  "lab_id = $L"
copy accounts_labmembership       "lab_id = $L and user_id in $DU"
copy research_project             "scope_lab_id = $L"
copy research_projectmember       "project_id in $P and user_id in $DU"
copy demo_demoworld               "key = 'default'"

# -- the public corpus, whole ----------------------------------------------------
copy content_contentitem          "true" replica
copy content_contentdeadline      "true"
copy content_itemcomprehension    "true"
copy collab_requirementslots      "true"

# -- the demo world's rankings and what hangs off them --------------------------
copy content_relevancescore       "target_user_id in $DU or target_lab_id = $L or target_department_id = $D or target_project_id in $P"
copy content_projectprofile       "project_id in $P"
copy content_dailybriefing        "user_id in $DU or lab_id = $L or department_id = $D"
copy content_savedopportunity     "user_id in $DU and (target_lab_id is null or target_lab_id = $L)"
copy content_remindersubscription "(target_lab_id = $L or target_user_id in $DU) and (created_by_id is null or created_by_id in $DU)"
copy content_reminderoffset       "subscription_id in (select id from content_remindersubscription where (target_lab_id = $L or target_user_id in $DU) and (created_by_id is null or created_by_id in $DU))"
copy content_projectshare         "project_id in $P and shared_by_id in $DU"
copy content_membersuggestion     "user_id in $DU and project_id in $P"

# -- what Mylo knows about the demo people: their edges and only the concepts
#    those edges point at (global concepts come from shared sources) ------------
copy knowledge_concept            "id in $CONCEPTS and (scope_user_id is null or scope_user_id in $DU) and (scope_lab_id is null or scope_lab_id = $L) and (scope_department_id is null or scope_department_id = $D)"
copy knowledge_conceptalias       "concept_id in $CONCEPTS and (scope_user_id is null or scope_user_id in $DU) and (scope_lab_id is null or scope_lab_id = $L) and (scope_department_id is null or scope_department_id = $D)"
copy knowledge_edge               "$EDGES and author_work_id is null"

say "reset sequences"
"${PSQL[@]}" -d "$SB" -q <<'SQL'
DO $$
DECLARE r record; m bigint;
BEGIN
  FOR r IN
    SELECT c.table_name, c.column_name, pg_get_serial_sequence(quote_ident(c.table_name), c.column_name) AS seq
    FROM information_schema.columns c
    WHERE c.table_schema = 'public' AND pg_get_serial_sequence(quote_ident(c.table_name), c.column_name) IS NOT NULL
  LOOP
    EXECUTE format('SELECT max(%I) FROM %I', r.column_name, r.table_name) INTO m;
    IF m IS NOT NULL THEN PERFORM setval(r.seq, m); END IF;
  END LOOP;
END $$;
ANALYZE;
SQL
say "done: $SB ($(sb "select pg_size_pretty(pg_database_size('$SB'))"))"
