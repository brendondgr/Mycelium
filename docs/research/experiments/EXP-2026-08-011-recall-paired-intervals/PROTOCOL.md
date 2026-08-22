# EXP-2026-08-011 — Protocol

**Pre-registered.** Written before any interval in this experiment was computed.

## Question

`Q-022`. After `EXP-2026-08-009` and `EXP-2026-08-010`, the recall claims are the
**only positive findings left standing** in the whole ladder — every nDCG@10
contrast that was re-tested with a paired interval spans zero, and the two
rerankers and the LLM are all refuted. Neither recall claim has ever had an
interval computed.

So: **do C-008 and C-014 survive a paired bootstrap, or does the ladder have no
surviving positive result at all?**

- **C-008** — restricting the lexical channel to the dense-retrieved pool costs
  recall that a union pool recovers. (`fusion_union_pool` − `fusion_dense_pool`)
- **C-014** — adding SPLADE as a third RRF channel raises recall over two-channel
  fusion. (`fusion_bm25_dense_splade` − `fusion_union_pool`)

## Hypothesis

**Both survive.** The point estimates are +0.0523 and +0.0630 R@100, an order of
magnitude larger than the ±0.04 nDCG@10 band this collection could not resolve at
n = 100. Recall is also a less brittle quantity than a top-10 ordering: it counts
set membership rather than position, so it should be less sensitive to which
queries land in a resample.

**Falsifier, stated now.** Either interval includes zero. If C-008 fails, the
single most-cited structural criticism of the deployed ranker is unsupported and
the ladder has produced **no** surviving positive finding. If C-014 fails, SPLADE
has no measured value at all and its 58-minute encode is unjustifiable.

**Secondary, no strong prior.** Whether the recall gain also shows up in the
per-query win/loss record, or whether it is a mean carried by a minority of
queries — the same distinction that unmasked the cross-encoder and the LLM arm.

## Setup

No new ranking logic. Three arms already measured in `EXP-2026-08-008`, re-run
only so their run files carry the config hash the newer harness stamps (the older
files predate it and cannot be resolved unambiguously). Identical frozen 84,489-doc
subset, identical cached embedding matrix, identical production code.

Reproduction is the correctness gate: each arm must return the value already on
the leaderboard, or the comparison is not about what it claims to be.

## Data

**LongEval-Sci**, `longeval-sci-2026/snapshot-1/train`, `dctr` qrels, 100 queries,
pooled scope at depth 1000 (84,489 documents).

Only the 2026 snapshot. The 2025-01 fusion arms would need a ~2 h corpus encode
and were not run in `EXP-2026-08-009` either — so this answers `Q-022` on one
snapshot, and says so.

Judgments are click-model–derived pseudo-relevance, not human assessment.

## Metrics

- **R@100 — primary.** The quantity both claims are about.
- **nDCG@100** secondary: recall that never surfaces in a ranking is not worth
  much, so a recall gain that fails to move the deeper ranking metric is a weaker
  finding than one that does.
- **Paired bootstrap 95% CI**, 10,000 resamples, fixed seed, via
  `harness.stats` — the same implementation `EXP-2026-08-009` and
  `EXP-2026-08-010` used.
- **Win/loss/tie and a two-sided sign test.**

**Scope, restated because it is easy to lose:** `pooled` scope is a re-ranking
evaluation. R@100 here is recall *within the pooled subset*. It supports a claim
about the relative ordering of these pool constructions and **not** a claim about
recall on the production corpus. `Q-001` is untouched.

## Baselines

`fusion_dense_pool` is production behaviour and the control for C-008.
`fusion_union_pool` is the control for C-014. Both are re-scored here rather than
quoted.

## Procedure

```bash
IR_DATASETS_HOME=data/eval-cache/ir_datasets \
  uv run --project eval python eval/run.py --collection sci-2026-train \
    --config eval/configs/fusion_dense_pool.toml \
             eval/configs/fusion_bm25_dense_splade.toml \
             eval/configs/dense_only.toml

IR_DATASETS_HOME=data/eval-cache/ir_datasets \
  uv run --project eval python \
    docs/research/experiments/EXP-2026-08-011-recall-paired-intervals/code/recall.py
```

## What would falsify this

- **C-008 is falsified** if the `fusion_union_pool` − `fusion_dense_pool` interval
  on R@100 includes zero.
- **C-014 is falsified** if the `fusion_bm25_dense_splade` − `fusion_union_pool`
  interval on R@100 includes zero.
- **An arm failing to reproduce its recorded value** invalidates this experiment
  rather than the claim.

**Decision rule, fixed now.** A claim moves to `supported` only if its interval
excludes zero **and** its per-query record favours the treatment. A mean gain with
a losing record is one or two large wins, which is exactly the pattern that
disqualified the LLM arm in `EXP-2026-08-008` and the cross-encoder in
`EXP-2026-08-009`; recall does not get a lower bar than they did.
