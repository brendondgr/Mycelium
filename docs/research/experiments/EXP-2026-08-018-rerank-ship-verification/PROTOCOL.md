# EXP-2026-08-018 — Protocol

**The gate was fixed before any code was written**, in
`docs/plans/cross-encoder-rerank.md` Phases 0 and 5 — written and committed
(`0c1844f`) before `apps/content/reranking.py` existed. That plan is deleted when
the work ships, per the planner skill's rule that a plan is a working document and
not a record, so its gate is preserved here.

This file was typed after the run. What it records was not chosen after it.

## Question

`docs/skills/global.md` requires a fresh evaluation run for any change to
`pipeline.py`'s ranking path, recorded in an experiment folder. A cross-encoder
rerank stage was added to the tail of `fuse_interests_pool` and
`fuse_clusters_pool`.

**Does turning it off leave the pipeline exactly as it was, and what does turning
it on cost?**

The first question is the one that matters. The stage sits in the *shared* fusion
path, which the eval harness's profile arms also call. If "off" is not identical
to the code before the stage existed, every historical number in this record is in
doubt — which is a far larger problem than whether the stage is any good.

## The gate, as fixed in the plan

> **Flag off ⇒ byte-identical.** Re-run the harness arms and diff against the
> committed run files. Any difference is a bug in the wiring, not a result.

Two levels:

1. **Harness** — re-run `fusion_dense_pool` on `sci-2026-train` and `cmp` the
   gzipped TREC run against the file committed at `ac56cee`.
2. **Production path** — fuse a real two-interest profile against the production
   store twice, flag off and flag on, and compare the surfaced ids, the scores
   and the persist-row signal keys field by field.

## What is deliberately not measured

**Whether the rerank stage is any good.** That is `EXP-2026-08-015` … `-017`, it
is a *preference* from one reader, and nothing here adds to it. This experiment
measures invariance and cost only. `Q-033` remains open.

## Threats to validity

1. **One profile, one store.** The cost figure is two declared interests over
   35,205 papers on a CPU-only host; a GPU and a 22-interest profile are both
   untested.
2. **Cost is CPU-bound and would change on a GPU**, which is the deployment
   target.
3. The harness diff covers one arm on one snapshot. It is the arm that exercises
   `_build_pool`, which is the code path shared with production.
