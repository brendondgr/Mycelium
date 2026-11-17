#!/usr/bin/env bash
# The backend suite and every tool's tests, without the wait of `make test`.
#
#   ops/test-fast.sh             everything, split over several processes
#   ops/test-fast.sh --changed   only the test directories a change touches
#                                (committed since origin/main, or not committed)
#   ops/test-fast.sh PATH...     only these directories or files
#
#   SHARDS=8    how many processes the whole suite is split over
#   REUSE=1     keep each process's test database from the last run
#
# `make test` runs every test in one process. Here the suite is split by
# directory (each Django app, each tool) over SHARDS processes, each with a
# test database of its own (`test_<name>_fast<k>`), so the whole of it takes a
# few minutes. The tests and their settings are the ones `make test` runs;
# only the order and the database differ.
#
# Building a test database takes most of a minute. REUSE=1 skips it, which
# turns a small run into seconds — but a kept database has lost the rows the
# migrations seed once a transactional test has emptied it, and tests that
# read those rows then fail. So it is for iterating on one directory; a
# failure seen with REUSE=1 is checked again without it.
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
BACKEND=$ROOT/web/backend
SHARDS=${SHARDS:-8}
LOGS=${TMPDIR:-/tmp}/mycelium-test-fast
mkdir -p "$LOGS"

BASE=${DATABASE_URL:-$(grep -E '^DATABASE_URL=' "$ROOT/.env" 2>/dev/null | cut -d= -f2-)}
if [ -z "$BASE" ]; then
  echo "No DATABASE_URL (in the environment or .env): run 'make setup' first." >&2
  exit 2
fi
NAME=${BASE##*/}
DB_FLAG=--create-db
[ -n "${REUSE:-}" ] && DB_FLAG=--reuse-db

cd "$BACKEND" || exit 2
count() { # test files under a directory; a file counts by its size, in kilobytes
  if [ -f "$1" ]; then
    echo $(($(wc -c <"$1") / 1024 + 1))
  else
    find "$1" \( -name 'test_*.py' -o -name 'tests.py' -o -name '*_tests.py' \) -not -path '*/.venv/*' 2>/dev/null | wc -l
  fi
}

# Every directory that holds tests, as pytest paths relative to web/backend.
all_units() {
  for d in apps/* ../../tools/*; do
    [ -d "$d" ] && [ "$(count "$d")" -gt 0 ] && echo "$d"
  done
  find . -maxdepth 1 -mindepth 1 -type d ! -name apps ! -name .venv ! -name media ! -name '.*' | sed 's#^\./##' |
    while read -r d; do [ "$(count "$d")" -gt 0 ] && echo "$d"; done
}

# The units a change touches: files committed since origin/main, plus what is
# modified or new in the working tree.
changed_units() {
  {
    git -C "$ROOT" diff --name-only origin/main...HEAD 2>/dev/null
    git -C "$ROOT" status --porcelain | cut -c4-
  } | sort -u | while read -r f; do
    case "$f" in
      web/backend/apps/*/*) echo "apps/$(echo "$f" | cut -d/ -f4)" ;;
      web/backend/*/*) echo "$(echo "$f" | cut -d/ -f3)" ;;
      tools/*/*) echo "../../tools/$(echo "$f" | cut -d/ -f2)" ;;
    esac
  done | sort -u | while read -r d; do
    [ -d "$d" ] && [ "$(count "$d")" -gt 0 ] && echo "$d"
  done
}

run_shard() { # k paths...
  local k=$1
  shift
  DATABASE_URL="${BASE%/*}/${NAME}_fast$k" uv run --no-sync pytest -c pyproject.toml -q \
    -p no:cacheprovider "$DB_FLAG" "$@" >"$LOGS/shard$k.log" 2>&1
  echo "exit=$?" >>"$LOGS/shard$k.log"
}

case "${1:-}" in
  --changed)
    mapfile -t units < <(changed_units)
    if [ "${#units[@]}" -eq 0 ]; then
      echo "Nothing under web/backend or tools changed since origin/main: no tests to run."
      exit 0
    fi
    ;;
  "") mapfile -t units < <(all_units) ;;
  *)
    units=()
    for p in "$@"; do units+=("$(realpath --relative-to="$BACKEND" "$ROOT/$p" 2>/dev/null || echo "$p")"); done
    ;;
esac

# A few directories and many processes: split them into their test files, so
# one large tool's tests still run side by side.
if [ "${#units[@]}" -lt "$SHARDS" ]; then
  mapfile -t units < <(for u in "${units[@]}"; do
    if [ -d "$u" ]; then
      find "$u" \( -name 'test_*.py' -o -name 'tests.py' -o -name '*_tests.py' \) -not -path '*/.venv/*' | sort
    else
      echo "$u"
    fi
  done)
fi

# Largest first into the emptiest of N bins, by number of test files.
n=$SHARDS
[ "${#units[@]}" -lt "$n" ] && n=${#units[@]}
declare -a bins load
for k in $(seq 0 $((n - 1))); do
  bins[k]=""
  load[k]=0
done
while read -r c d; do
  best=0
  for k in $(seq 0 $((n - 1))); do [ "${load[k]}" -lt "${load[best]}" ] && best=$k; done
  bins[best]="${bins[best]} $d"
  load[best]=$((load[best] + c))
done < <(for u in "${units[@]}"; do echo "$(count "$u") $u"; done | sort -rn)

echo "${#units[@]} test directories or files over $n process(es)"
rm -f "$LOGS"/shard*.log
start=$(date +%s)
pids=()
for k in $(seq 0 $((n - 1))); do
  # shellcheck disable=SC2086
  run_shard "$k" ${bins[k]} &
  pids+=($!)
done
wait "${pids[@]}"

status=0
for k in $(seq 0 $((n - 1))); do
  line=$(grep -E '(passed|failed|error|no tests ran).* in [0-9.]+s' "$LOGS/shard$k.log" | tail -1)
  grep -q '^exit=0$' "$LOGS/shard$k.log" || status=1
  what=$(echo ${bins[k]} | cut -c1-70)
  echo "  process $k ($what): ${line:-no summary; see $LOGS/shard$k.log}"
done
grep -h -E '^(FAILED|ERROR) ' "$LOGS"/shard*.log 2>/dev/null | sort -u >"$LOGS/failed.txt"
echo "Finished in $(($(date +%s) - start)) s. Failed or errored: $(wc -l <"$LOGS/failed.txt")."
if [ -s "$LOGS/failed.txt" ]; then
  cut -c1-160 "$LOGS/failed.txt"
  echo "Full output: $LOGS/shard<k>.log."
  [ -n "${REUSE:-}" ] && echo "This run kept its test databases (REUSE=1): check a failure again without it."
fi
exit $status
