#!/usr/bin/env bash
# EXP-2026-08-012 phases 2 and 3, chained so they need no supervision.
#
# Written because the network was expected to drop mid-run. Nothing here touches
# the network: the corpus is already downloaded under data/eval-cache/ir_datasets,
# the models are cached under data/eval-cache/fastembed, and HF_HUB_OFFLINE stops
# fastembed phoning home to check for updates. No LLM is called.
#
# Waits for the phase-1 process, then encodes SPLADE over the 2025-01 subset,
# scores the three-channel arm, and computes the replication intervals.
set -u
cd "$(dirname "$0")/../../../../.."  # the repository root

export IR_DATASETS_HOME=data/eval-cache/ir_datasets
export FASTEMBED_CACHE_PATH="$PWD/data/eval-cache/fastembed"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1

LOG=data/eval-cache/logs
say() { echo "[chain $(date '+%H:%M:%S')] $*" | tee -a "$LOG/exp012_chain.log"; }

PHASE1_PID="${1:-}"
if [ -n "$PHASE1_PID" ]; then
  say "waiting for phase 1 (pid $PHASE1_PID) …"
  while kill -0 "$PHASE1_PID" 2>/dev/null; do sleep 60; done
fi
say "phase 1 finished"

# One model at a time: two concurrent ONNX sessions oversubscribe this host
# badly (EXP-2026-08-008 ISSUES section 5).
say "phase 2a — SPLADE encode over the 2025-01 pooled subset (~3 h)"
uv run --project eval python eval/encode_ladder.py --model splade --collection sci-2025-01 \
  >> "$LOG/exp012_phase2_encode.log" 2>&1
say "SPLADE encode exited $?"

say "phase 2b — three-channel arm"
uv run --project eval python eval/run.py --collection sci-2025-01 \
  --config eval/configs/fusion_bm25_dense_splade.toml \
  >> "$LOG/exp012_phase2_arm.log" 2>&1
say "three-channel arm exited $?"

say "phase 3 — replication intervals"
uv run --project eval python \
  docs/research/experiments/EXP-2026-08-012-recall-replication-2025/code/replicate.py \
  >> "$LOG/exp012_phase3.log" 2>&1
say "replicate.py exited $?"
say "ALL PHASES COMPLETE"
