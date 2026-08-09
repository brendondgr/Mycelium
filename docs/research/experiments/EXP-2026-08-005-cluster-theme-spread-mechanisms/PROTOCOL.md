# EXP-2026-08-005 — Protocol

## Question

For a cluster-scoped feed, does any of six candidate mechanisms spread the
ranking across a profile's themes — individually, or in combination — without
costing relevance, and is the gain attributable to theme semantics rather than to
the operator itself?

## Background: what is already measured

`EXP-2026-08-003` found that cluster-scoped max-pooling *concentrates* the feed:
`cluster_gini@10` was worse than the flat arm in all nine cells it ran, and
`min_cluster_recall@10` on the `imbalanced` grouping was −0.0032, CI
[−0.0066, −0.0007]. It refuted C-003 for the global max-pooled path.

`EXP-2026-08-004` found that the per-theme slate cannot fix it. `fuse_clusters_pool`
appends slate members to the surfaced set and then re-sorts the union by
`final_score`; a slate member is by definition a candidate the global cut
rejected, so after the re-sort it always lands below the cut. Every `@10` and
`@30` delta in that experiment was exactly 0.0, which is arithmetic, not evidence.

No diversification machinery exists anywhere in the ranking stack today:
`apps/content/ranking.py` has only `rerank_by_focus` (a relevance boost) and
`apps/content/digest_selection.py` has none.

This experiment measures the mechanisms that would.

## Hypothesis

Stated before the run.

1. **Selection mechanisms will move the primary metric and score mechanisms will
   not, on their own.** M1/M3/M4/M5 change the order of the surfaced 250, which a
   top-10 metric reads directly. M2 changes the ranking key, which should also
   reorder — but only if cross-cluster score incomparability is real in this
   corpus, which is untested.
2. **M6 (per-theme admission floor) is inert alone at `prod`.** The 250-item
   backstop already binds — `EXP-2026-08-004` measured every arm surfacing exactly
   250 of a ~575 pool — and anything M6 newly admits has a low `final_score`, so
   `cap_clusters` discards it. This is the same arithmetic that made the slate
   inert. It is run anyway, and predicted to matter only combined with a
   selection policy.
3. **Spread will cost relevance**, and the interesting question is how much. An
   equal-slot round robin must promote a weak theme's mediocre candidate over a
   strong theme's good one; that is the mechanism, not a defect.
4. **No prior hypothesis on which mechanism wins**, or on whether any combination
   beats the best individual.

## Setup

The Mycelium ranking stack through the `eval/` harness, at the commit recorded in
`manifest.yaml`. Held fixed across every cell: the collection, the corpus scope
(`full`), the embedding model, the synthetic-profile builder and its seed, `beta`
(0.15 — `EXP-2026-08-003` measured the paired arm delta to be invariant in it),
`pool_per_interest` (100), and the `prod` surfacing condition
(`match_threshold = 0.5`, `surface_limit = 250`).

Every arm is a call into `apps.content.pipeline.fuse_clusters_pool` differing from
the baseline by **exactly one production argument** — the `spread` keyword. The
mechanisms themselves are production code in `apps/content/fusion.py`, defaulting
to off; the harness contains no ranking logic of its own.

`prod` is the informative condition here, in contrast to `EXP-2026-08-004` where
it was inert. That experiment's mechanism only added to a *set*, and every added
item sorted below the cut. Five of these six change the *order* of the surfaced
250, and a top-10 metric observes an ordering change directly.

## Data

LongEval-Sci 2026, snapshot 1, `train` split, `full` corpus scope (869,902
documents), 100 queries.

**The judgments are `dctr` click-model-derived pseudo-relevance, not human
assessment.** That is true of every number in this experiment and is repeated
next to the results.

Profiles are **synthetic**: 30 per grouping, each 6 LongEval queries as search
interests partitioned into 3 clusters, built by `eval/harness/profiles.py` with
seed 20260809 from a 300-query candidate pool. A profile's qrels are the union of
its constituent queries' qrels; each cluster's relevant set is the union of its
own queries'. This is not a released judgment set and these numbers are
comparable to nothing published.

Three groupings, and the contrast between them is the experiment's internal
control:

- `coherent` — clusters agglomerated by embedding cosine, the realistic case.
- `imbalanced` — clusters chosen for the largest across-cluster variance in score
  mass. The failure mode these mechanisms exist for, and the **target condition**.
- `random` — the same interest sets, seeded reshuffle. The **negative control**:
  a mechanism whose gain here matches its gain on `imbalanced` is exploiting the
  operator, not theme semantics.

## Metrics

**Primary — `min_cluster_recall@10`.** Of the profile's clusters that have any
relevant document, the *smallest* per-cluster recall inside the top 10. It is the
worst-served theme's outcome, which is the quantity a spread mechanism claims to
improve; a mean over themes would let a dominant theme's gain hide a starved
theme's loss, which is the failure itself.

**Relevance guardrail — `nDCG@10`,** via `ir_measures`. Spread is only worth
anything if the items are still relevant, so every mechanism reports it and it is
part of the decision rule below, not an afterthought.

Secondary, all reported: `cluster_coverage@10` (fraction of relevant-bearing
clusters with at least one document in the top 10), `cluster_gini@10` (**lower is
better**; inequality of per-theme representation), the same three at `@100`, and
`AP` and `R@100` for relevance.

The three coverage metrics come from `eval/harness/cluster_metrics.py` and are
hand-rolled, which breaks the harness's standing rule. The justification is in
that module's docstring: a cluster is a property of the synthetic *profile*, not
of the collection, so no IR toolkit can implement them. They are comparable
within and across `EXP-2026-08-003/004/005` and to nothing published. The
relevance family still goes through `ir_measures`.

**Statistics.** Paired bootstrap over the 30 profiles, 10,000 resamples, seed
20260809, 95% percentile interval, against the `clustered_profile` baseline.
Paired because every arm scores the identical profiles over the identical pool.

## Baselines

- `clustered_profile` — the deployed cluster-scoped ranking. **Every delta is
  against this.**
- `flat_profile` — no clusters at all. `EXP-2026-08-003` found it already beats
  the clustered arm on theme coverage, so it is the bar a spread mechanism has to
  clear to justify clustering the ranking in the first place.
- `spread_identity` — the null policy, and falsifier 4 below.

## The mechanisms

| id | arm | what it changes |
|----|-----|-----------------|
| M1 | `spread_interleave` | selection — round-robin, equal slots per theme |
| M2 | `spread_rankmerge` | scores — merge on within-cluster RRF rank, not raw score |
| M3 | `spread_quota` | selection — slots proportional to a theme's score mass |
| M4 | `spread_cap` | selection — no theme holds more than α=0.5 of any prefix |
| M5 | `spread_mmr` | selection — greedy with a theme-saturation penalty λ=0.5 |
| M6 | `spread_floor` | admission — per-theme relative floor beside the global one |

Parameter values (α, λ, `admit_frac`) are the midpoint of their meaningful range
and are **fixed before the runs**. Tuning a knob on the same profiles used to
measure it is how a null result becomes a positive one.

Phase 2 combines the score mechanism (M2) with each selection mechanism, plus
`spread_floor_interleave` (which hypothesis 2 predicts is the only way M6 can
matter) and `spread_all`. All six combinations are **run** regardless of what
phase 1 returns — the marginal cost of a cell is ~15 s once the corpus is loaded,
and running only the combinations that looked promising would be selecting the
grid on the results. The decision rule below governs which are *interpreted as
helping*, not which are executed.

## Decision rule (pre-registered)

A mechanism **helps** iff, on the `imbalanced` grouping, against
`clustered_profile`:

- Δ`min_cluster_recall@10` > 0 with the 95% CI excluding zero, **and**
- Δ`nDCG@10` has a CI lower bound above −0.01.

Anything else is reported as measured and does not enter the combination phase.

## Procedure

```bash
# Phase 1 — individual mechanisms (27 cells: 9 arms x 3 groupings)
uv run --project eval eval/run.py --config \
  eval/configs/spreadexp_{clustered_profile,flat_profile,spread_identity,spread_interleave,spread_quota,spread_cap,spread_mmr,spread_rankmerge,spread_floor}_{coherent,imbalanced,random}.toml

# Phase 2 — combinations (18 cells: 6 arms x 3 groupings)
uv run --project eval eval/run.py --config \
  eval/configs/spreadexp_{spread_rankmerge_interleave,spread_rankmerge_quota,spread_rankmerge_cap,spread_rankmerge_mmr,spread_floor_interleave,spread_all}_{coherent,imbalanced,random}.toml

# Aggregate, bootstrap, and write data/metrics.{csv,json}
python docs/research/experiments/EXP-2026-08-005-cluster-theme-spread-mechanisms/data/build_metrics.py

# Figures, index, validation
make figures && make research-index && make validate-research
```

All 45 cells run in one process so the 869,902-document corpus and its cached
embedding matrix are loaded once.

## What would falsify this

1. **Operator artifact.** A mechanism whose `imbalanced` gain is matched on the
   `random` control is not exploiting theme semantics — `random` has the same
   interests in a meaningless partition. On a tie, no theme-awareness claim is
   made, whatever the size of the gain.
2. **Bought, not earned.** A coverage gain accompanied by a larger surfaced set
   is a different thing from one that comes free. The surfacing diagnostic is
   recorded for every cell and any such gain is discounted.
3. **No synergy.** If no combination beats the best individual mechanism on the
   primary metric, that is the finding: ship at most one.
4. **Plumbing regression.** `spread_identity` must reproduce `clustered_profile`'s
   per-profile metrics exactly. If it does not, the spread code path — not a
   mechanism — is moving the numbers, and every result here is void.
5. **Relevance collapse.** A mechanism that improves the primary metric while
   ΔnDCG@10's CI sits entirely below −0.01 has not solved the problem; it has
   traded the feed's usefulness for an evenness statistic.

## Scope limits, stated in advance

These are synthetic profiles. A positive result licenses "the mechanism works",
never "ship it". Q-009 (real declared clusters) still gates any product decision,
and no production default is changed by this experiment — every policy ships off.
