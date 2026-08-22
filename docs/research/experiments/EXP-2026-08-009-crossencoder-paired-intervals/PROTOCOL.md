# EXP-2026-08-009 — Protocol

**Written before any arm on `sci-2025-01` was run.** Unlike `EXP-2026-08-008`,
every prediction below is a genuine pre-registration: at the time of writing, no
cross-encoder had ever been run on this snapshot and the only cross-encoder
numbers in existence are the 2026 ones.

## Question

Does the cross-encoder's advantage over BM25 — measured at +0.0087 nDCG@10 on
`sci-2026-train` with 100 queries and no interval — survive a **paired bootstrap
confidence interval** on `sci-2025-01`, which carries 492 queries?

This is `Q-016`, and it exists because C-013 currently rests on a margin small
enough that this record has twice before failed to distinguish such an effect from
none at all (`Q-011`, `Q-013`).

## Hypothesis

**Primary `[PRE]`.** A cross-encoder reranking the strongest available first stage
beats that first stage on nDCG@10, with a 95% paired bootstrap interval excluding
zero, on `sci-2025-01`.

**Secondary `[PRE]`, and this one I expect to fail.** The specific 2026 result —
cross-encoder *over the fusion ranking* beating `bm25_only` — will **not**
replicate here. The reason is recorded in advance and is visible in the existing
leaderboard: on `sci-2025-01` the dense channel is far weaker than on 2026
(`dense_only` 0.0931 against `bm25_only` 0.2486, where on 2026 the gap is 0.2401
against 0.3212), so `fusion_union_pool` starts at 0.1819 — 0.067 *below* BM25
rather than 0.016 below it. A reranker confined to that pool has a much worse
candidate set to work with, and reranking cannot promote what retrieval never
surfaced.

That prediction is why this experiment adds an arm `EXP-2026-08-008` did not have:
**the cross-encoder over the BM25 ranking**. If the secondary hypothesis holds and
the primary one also holds, the finding is that the cross-encoder is worth having
but must be stacked on whichever first stage is actually strongest — which is a
different and more useful conclusion than "add a cross-encoder to the fusion".

**No prior** on whether the fusion-based reranker beats its own fusion base here
(it should, but by how much is open), or on interval width.

## Setup

Identical harness, identical production code, one frozen document set per
snapshot. Arms differ from their baseline by exactly one stage. Cross-encoder is
`Xenova/ms-marco-MiniLM-L-6-v2` at depth 50 and 100, ONNX on CPU, no GPU.

The `sci-2025-01` subset is frozen to a committed id list exactly as the 2026 one
was. **Its dense matrix must be encoded from scratch** — unlike 2026, there is no
cached full-corpus matrix to row-slice from, so the arms that need vectors pay a
one-time encode of the pooled subset. The arms whose base is `bm25_only` need no
vectors at all and are run first.

## Data

**LongEval-Sci (CLEF)**, snapshot `longeval-sci/2025-01`, `test` split,
1,213,728 documents and **492 queries** — the reason for choosing it.
Corpus scope `pooled` at depth 1000 (261,294 documents on the recorded rows), a
**re-ranking** evaluation.

Judgments are the released CLEF-2025 `test` qrels. Note this differs from
`EXP-2026-08-008`, which used click-derived `dctr` — so a difference between the
two experiments confounds snapshot with judgment provenance and must not be read
as temporal drift.

`sci-2026-train` is re-analysed from its existing run files for the same paired
intervals, so both query-set sizes are reported side by side.

## Metrics

- **nDCG@10 — primary**, matching `EXP-2026-08-008` so the two are comparable.
- **Paired bootstrap 95% CI on the per-query difference** — the actual output of
  this experiment. 10,000 resamples over query ids with replacement, computing the
  mean per-query delta each time. This is the thing `Q-016` asks for and the thing
  every prior contrast in this record has lacked.
- **Win/loss/tie counts** and a two-sided sign test, reported alongside, because a
  mean delta carried by three queries and a mean delta earned across two hundred
  are different findings with the same number.
- nDCG@100, AP, R@100 secondary.

## Baselines

- `bm25_only` (pooled) — the bar, and on this snapshot the strongest single stage.
- `fusion_union_pool` (pooled) — the ladder's base, for continuity with EXP-008.

## Procedure

```bash
# 1. Freeze the 2025-01 subset. Id list only: there is no cached full-corpus
#    matrix for this snapshot to slice from.
IR_DATASETS_HOME=data/eval-cache/ir_datasets \
  uv run --project eval python eval/freeze_subset.py \
    --collection sci-2025-01 --depth 1000 --skip-matrix

# 2. The arms needing no embeddings — the decisive contrast, runnable immediately.
IR_DATASETS_HOME=data/eval-cache/ir_datasets \
  uv run --project eval python eval/run.py --collection sci-2025-01 \
    --config eval/configs/bm25_only_pooled.toml \
             eval/configs/xenc_rerank_bm25base_d50.toml \
             eval/configs/xenc_rerank_bm25base_d100.toml

# 3. The fusion arms, which pay the one-time subset encode.
IR_DATASETS_HOME=data/eval-cache/ir_datasets \
  uv run --project eval python eval/run.py --collection sci-2025-01 \
    --config eval/configs/fusion_union_pool.toml \
             eval/configs/xenc_rerank_d50.toml eval/configs/xenc_rerank_d100.toml

# 4. Paired bootstrap intervals, on both snapshots.
IR_DATASETS_HOME=data/eval-cache/ir_datasets \
  uv run --project eval python \
    docs/research/experiments/EXP-2026-08-009-*/code/paired.py
```

## What would falsify this

- **The primary hypothesis is falsified** if the 95% paired interval for
  `xenc_rerank`-over-the-best-base minus that base **includes zero**, or if the
  point estimate is negative. In that case C-013 must be downgraded from
  `supported` to `partial` or `unsupported`, and the recommendation to adopt a
  cross-encoder is withdrawn pending better evidence.
- **C-013 as currently worded is falsified** if the cross-encoder over the *fusion*
  base fails to beat `bm25_only` here with an interval excluding zero. That is the
  claim as written, and the secondary hypothesis above predicts exactly this
  failure — so if it fails, the claim gets **rescoped**, not quietly reinterpreted:
  the honest statement becomes "a cross-encoder improves whatever first stage it is
  given" rather than "a cross-encoder beats BM25".
- A **negative** interval anywhere is a result, not a bug, and gets recorded as one.

**Decision rule, fixed now.** Adoption requires the primary interval to exclude
zero on `sci-2025-01`, *and* the win/loss record to favour the reranker on more
queries than it harms. A mean gain with a losing per-query record is not adoption
evidence — it is one or two large wins, and `EXP-2026-08-008` §2 already showed
that pattern for the LLM arm.

**What this still cannot settle.** LongEval is `query → documents`; Mycelium is
`declared-interest profile → feed`. `docs/evaluation.md`'s claims boundary applies
unchanged, and `Q-001` — does any of this hold on the production corpus — remains
open regardless of how this comes out.
