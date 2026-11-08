# EXP-2026-11-003 — Protocol

## Question

Does moving the ranking stack out of `apps/content` into the `tools/` modules
(plan `docs/plans/modular-tools/`) change any ranking the evaluation harness
produces?

## Hypothesis

No. The refactor moves code between packages and rewrites import paths; it does
not change a single expression in the ranking path. Every TREC run file written
after each phase is expected to be **byte-identical** to the one written before
the refactor, and every metric therefore identical to the last digit.

## Setup

- System under test: the production ranking code the harness calls —
  `lexical.build_bm25_index` / `rank_bm25_over` and `pipeline._build_pool`
  (the deployed dense-restricted pool, BM25 reordering inside it).
- Before: commit `47a8565` (branch `modular-tools`, before any code moves).
- After: the head of each phase that moves ranking code (retrieval, then
  recommendation, then delivery).
- Held fixed: the eval project's lockfile (`eval/uv.lock`), the cached embedding
  matrices (`data/eval-cache/embeddings` in the main checkout), the fastembed
  model cache, and the arm configs below, unedited.

## Data

`sci-2026-train` (LongEval-Sci 2026 training snapshot) through the harness's own
loader, with the harness's standard qrels. The judgments are the collection's
published relevance assessments, as for every other harness run.

## Metrics

Primary: **byte equality of the TREC run files** (sha256 of each run file
before and after). This is the correct test for a pure code move: any
difference at all is a regression to explain, whatever it does to the
aggregate. Secondary: nDCG@10 and R@100 as the harness reports them, recorded
for the reader, not used to decide anything.

## Baselines

The same arms on the pre-refactor commit. There is no other baseline: the
question is equality, not improvement.

## Procedure

```bash
export IR_DATASETS_HOME=/home/bdgr/Agents/Mycelium/data/eval-cache/ir_datasets \
       MYCELIUM_EVAL_CACHE=/home/bdgr/Agents/Mycelium/data/eval-cache/embeddings \
       FASTEMBED_CACHE_PATH=/home/bdgr/Agents/Mycelium/data/eval-cache/fastembed \
       HF_HUB_OFFLINE=1
uv run --project eval eval/run.py \
  --config eval/configs/fusion_dense_pool.toml eval/configs/bm25_only.toml \
  --collection sci-2026-train
sha256sum eval/runs/<the run files this wrote>
```

Repeated at each phase head; the hashes are compared to the pre-refactor ones.

## What would falsify this

Any run file whose hash differs from its pre-refactor counterpart. One differing
file means the refactor changed behaviour (or the harness is nondeterministic,
which would itself have to be shown by re-running the before commit), and the
phase does not ship until the cause is found.
