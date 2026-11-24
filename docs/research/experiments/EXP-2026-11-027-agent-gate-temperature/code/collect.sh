#!/usr/bin/env bash
# EXP-2026-11-027 (EXP-2026-11-026's collect.sh, paths changed): copy every file the runs created or changed in the staged
# research record into this experiment's data/raw/<source experiment>/, and
# list them. Files the runs did not touch are left out (rsync --compare-dest
# against the repository's record). A file over 5 MB is stored gzipped (the
# record's limit is 10 MB per file). Run from the repository root.
#   bash …/code/collect.sh [EXP-2026-11-021-agent-model-check …]   # default: every folder
# Collect a source folder only once its part has finished (a part in flight
# leaves partial files).
set -eu
RUN=${RUN:-/home/bdg20b/Projects/Mycelium-runs/temperature-20261124}
X=docs/research/experiments
OUT=$X/EXP-2026-11-027-agent-gate-temperature/data/raw
mkdir -p "$OUT"
if [ $# -gt 0 ]; then set -- "${@/#/$RUN/stage/$X/}"; else set -- "$RUN"/stage/$X/EXP-*; fi
for src in "$@"; do
  name=$(basename "$src")
  [ "$name" = EXP-2026-11-027-agent-gate-temperature ] && continue
  rsync -a -m --exclude __pycache__ --compare-dest="$PWD/$X/$name/" "$src/" "$OUT/$name/"
done
find "$OUT" -type d -empty -delete
find "$OUT" -type f -size +5M ! -name '*.gz' -exec gzip -9 {} \;
# the run's own logs (driver, status, per-container output, preflight)
mkdir -p "$OUT/run"
cp "$RUN"/status.txt "$RUN"/driver.log "$OUT/run/"
cp -r "$RUN"/logs "$OUT/run/"
for a in "$RUN"/aborted-*; do [ -d "$a" ] && cp -r "$a" "$OUT/run/"; done
find "$OUT/run" -type f -size +5M ! -name '*.gz' -exec gzip -9 {} \;
(cd "$OUT" && find . -type f | sort > ../raw_files.txt)
wc -l < "$OUT/../raw_files.txt"
