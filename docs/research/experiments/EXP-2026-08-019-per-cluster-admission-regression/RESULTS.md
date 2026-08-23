# Results — per-cluster admission: harness regression check

**Status:** complete. **Verdict:** the new admission gate is **inert on this
harness**. Both arms' diagnostics are byte-identical across the change, and the
one metric difference is attributable to a different commit, not to this one.

## What was measured

`eval/run.py` over `longeval-sci-2026/snapshot-1/train`, both cluster arms, at
`match_threshold = 0.5` and `surface_limit = 250`. Full numbers in
`data/metrics.csv`; the machine-readable block with run-file names is
`data/metrics.json`.

### Diagnostics — the load-bearing comparison

Identical for both arms, before and after:

| Diagnostic | Before | After |
| --- | --- | --- |
| `surfacing.mean_surfaced` | 250.0 | 250.0 |
| `surfacing.median_surfaced` | 250.0 | 250.0 |
| `surfacing.max_surfaced` | 250.0 | 250.0 |
| `surfacing.mean_pool` | 574.47 | 574.47 |
| `clusters_cleared_per_candidate` | {1: 6692, 2: 790, 3: 18} | {1: 6692, 2: 790, 3: 18} |

This is the answer. Every profile in the harness already surfaces at the 250
backstop, so whatever the relative floor additionally admits is truncated before
a single metric is computed. The gate cannot move a number here because it never
reaches the scored window.

### Metrics

`clustered_profile`, against the newest same-hash baseline (`f0dc7e5`): **every
metric identical to six decimal places**, including nDCG@10 0.1752, nDCG@100
0.2257, AP 0.0841, R@100 0.2521, and all nine cluster-balance metrics.

`slate_profile` has no `f0dc7e5` baseline on record; its newest same-hash
baseline is the older `e356280`, against which nDCG@10 reads +0.0208 and nDCG@100
+0.0080. **This is not attributable to the admission change.** `clustered_profile`
at that same older commit shows the *same* +0.0208 / +0.0080 shift, and at the
newer `f0dc7e5` it shows zero — so the shift lives between `e356280` and
`f0dc7e5`, and this change is on the far side of it. Given identical diagnostics,
the most likely cause is the tie-ordering behaviour recorded in the traps note:
`ir_measures` reorders equally-scored documents, so byte-identical run files can
score differently. It is recorded here rather than silently dropped.

## Interpretation

The change is **safe** with respect to the recorded harness numbers and is
**unmeasured** with respect to its actual purpose.

Safe: no arm's retrieved set moved. Nothing already on record is invalidated, and
the leaderboard needs no correction.

Unmeasured: this harness cannot test the gate. The gate exists because a reader
with several declared research themes gets a feed swept by whichever theme's
vocabulary sits closest to the corpus, and the harness has no such reader — its
profiles are clusters of query embeddings, its surfacing saturates a backstop
that a real feed rarely reaches, and its relevance judgements are per-query, not
per-theme. A favourable number here would not have been evidence for the change.

## Threats to validity

1. **Saturation is the whole result.** The finding is "the gate does not reach
   the scored window", which is a fact about this configuration, not about the
   gate. Lowering `surface_limit` below the admitted count would make it live —
   and that experiment has not been run.
2. **One collection, one grouping, one seed.** `coherent` grouping only, 30
   synthetic profiles, `seed = 20260809`. No paired interval was computed because
   there is no difference to bound.
3. **The `slate_profile` baseline is two commits stale.** The attribution above
   is an inference from `clustered_profile`'s two baselines, not a direct
   observation. Re-running `slate_profile` at `f0dc7e5` would settle it; it was
   not done because it does not change this experiment's conclusion.
4. **Tie ordering is unresolved.** See the traps note. It affects any comparison
   in this record where two commits produce identical run files.

## What would change the verdict

A configuration where admitted candidates fall inside the scored window — a lower
`surface_limit`, or a corpus where the pool does not saturate. Until then, the
per-cluster gate should be described as *deployed and unmeasured*, and no claim
in `CLAIMS.md` should be moved on the strength of this run.
