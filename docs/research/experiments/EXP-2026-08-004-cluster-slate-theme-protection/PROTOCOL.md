# EXP-2026-08-004 — Protocol

Written before the runs. Answers **Q-010**, raised by `EXP-2026-08-003`.

## Question

`EXP-2026-08-003` refuted C-003 by showing that cluster-scoped **global**
ranking — combine within clusters, max across them — leaves the worst-served
theme worse off, not better. But it measured only the path an *individual's* feed
uses (`cluster_top_n = 0`). The **lab** feed additionally emits a per-theme
slate: each cluster's own best *n* candidates by that cluster's score, folded
back into the surfaced set (`fusion.top_per_cluster`).

Does that slate deliver the theme protection global max-pooling did not?

## Hypothesis

The slate raises `cluster_coverage` and `min_cluster_recall` over the surfaced
set relative to both flat and cluster-scoped-global ranking, because it
guarantees every theme a fixed allocation regardless of that theme's absolute
score. It does so **by surfacing more items**, so the comparison is only
meaningful with the surfaced-set size reported alongside.

This is the mechanism `top_per_cluster`'s own docstring describes: a global
ranking "is swept by that theme and the rest of the lab reads as though nothing
was found for it." `EXP-2026-08-003` measured exactly that sweeping. The
hypothesis is that the slate is the remedy the codebase already believed it to be.

## Setup

**System under test:** unchanged production code in
`web/backend/apps/content`. All three arms call `pipeline.fuse_interests_pool` or
`pipeline.fuse_clusters_pool` over an identical pool built by the same
`_build_pool`.

| Arm | Production path it is | Differs by |
|---|---|---|
| `flat_profile` | no clusters in the ranking | `fuse_interests_pool` |
| `clustered_profile` | **an individual's** feed | `cluster_top_n = 0` |
| `slate_profile` | **a lab's** feed | `cluster_top_n = 10` |

`slate_profile` is a keyword-forwarding wrapper over `clustered_profile`: the two
arms differ by exactly one production argument and nothing else, which
`eval/tests/test_profile_arms.py` asserts directly. That test exists because a
silently-dropped `cluster_top_n` would compare the arm against itself and report
a null indistinguishable from a real negative result.

**Held fixed:** encoder, `pool_per_interest = 100`, the 0.15 abstention floor,
RRF `k = 60`, corpus scope `full`, snapshot, seed, and the profile set — the
comparison is paired, profile by profile, and the profiles are the *same 30 per
grouping mode* `EXP-2026-08-003` used (same seed, same construction).

**β is fixed at the deployed 0.15.** `EXP-2026-08-003` measured the paired arm
delta to be invariant in β across {0, 0.15, 0.3}; sweeping it again would triple
the cost for a variable already shown inert. Recorded here rather than decided
later.

## The surfacing condition is the independent variable

A slate is a mechanism for **surviving a cut**. If nothing is ever cut, it is
inert by construction. So the cut is a controlled condition, with two levels:

| Condition | Surfacing | Why |
|---|---|---|
| `prod` | `match_threshold = 0.5`, `surface_limit = 250` | Production for the paper feed: `PAPER_MATCH_THRESHOLD` / `PAPER_MATCH_MAX_SURFACE`. The condition a **product** conclusion needs. |
| `cut30` | no threshold, `surface_limit = 30` | **Stress condition, not production.** A hard 30-item cut forces the truncation guarantees to bind, so the mechanism is observable even if the production threshold turns out not to bind on this collection. |

`prod` and `cut30` rows are never mixed or averaged. If the production threshold
does not bind — i.e. the mean surfaced set is the whole pool — then `prod` cannot
discriminate between the arms and that fact is the finding for the product
question, with `cut30` describing the mechanism instead.

Grouping mode (`coherent` / `random` / `imbalanced`) is carried over unchanged
from `EXP-2026-08-003`, including the `random` negative control.

Full grid: 3 arms × 2 conditions × 3 groupings = 18 cells.

## Data

LongEval-Sci 2026 snapshot 1 train — 869,902 documents, 100 queries, `dctr`
qrels, corpus scope `full`. Synthetic profiles: *K* = 6 interests in *C* = 3
clusters, 30 per grouping mode, seed 20260809, judgments the union of each
profile's constituent queries' qrels keeping the maximum grade. Construction is
`eval/harness/profiles.py`, identical to `EXP-2026-08-003`; its rationale is that
protocol's "Profile construction" section and is not restated here.

**The judgments are click-model-derived pseudo-relevance, not human assessment.**

## Metrics

Same families as `EXP-2026-08-003`, so the two experiments are directly
comparable.

**Coverage (primary).** `min_cluster_recall@10` remains the pre-registered
primary for continuity. But `EXP-2026-08-003` §6 recorded that this metric is
thinly populated — its aggregate there was decided by 4 of 30 profiles — so
**`cluster_coverage@30` is pre-registered as the co-primary here**, on the
reasoning that a slate allocates a *fixed number of slots per theme* and its
effect must therefore appear at a depth comparable to that allocation
(3 clusters × 10 = 30), not at depth 10. Both are reported; neither is chosen
after seeing results. `cluster_gini` and the `@100` variants are reported as
before.

**Relevance (guardrail).** `nDCG@10` and `R@100` over the union qrels, through
`ir_measures`, unchanged.

**Surfaced-set size (mandatory context, not a score).** Mean, median and maximum
surfaced items and mean pool size, per arm. A slate buys coverage by surfacing
more; a coverage gain reported without the set size would be misleading, so the
diagnostic is emitted by every arm and printed in `RESULTS.md`.

## Statistics

Paired bootstrap over profiles, 10,000 resamples, seed 20260809, 95% percentile
interval — identical to `EXP-2026-08-003`. Two arm pairs are reported per cell:
`slate − clustered` (does the slate add anything to the cluster path?) and
`slate − flat` (is the lab feed better than having no clusters at all?).

## What would falsify this

1. **The slate is decoration** if `slate − clustered` on `cluster_coverage@30`
   has a 95% CI spanning zero in the `cut30` condition — where the cut is
   guaranteed to bind. Then the lab feed's theme protection does not work either,
   and C-003 is refuted for both paths rather than one.
2. **The slate is inert in production** if the `prod` condition's mean surfaced
   size equals the mean pool size for every arm. That is not a failure of the
   slate but of the threshold to bind on this collection; report it as a scope
   limit on the product question and lean on `cut30` for the mechanism.
3. **The gain is bought, not earned** if `cluster_coverage@30` rises but the mean
   surfaced set also rises proportionally. A slate that adds 30 items to gain 30
   items of coverage has done nothing an equally larger flat cut would not.
   Report the coverage gain per extra item surfaced.
4. **The harness is wrong** if `slate_profile` and `clustered_profile` produce
   identical rankings in the `cut30` condition — that would mean `cluster_top_n`
   is not reaching production. `eval/tests/test_profile_arms.py` guards this, but
   the identical-ranking share is computed and reported regardless.

## Scope of any conclusion

Everything in `EXP-2026-08-003`'s scope section applies unchanged: synthetic
profiles, union-of-qrels, click-derived judgments, one snapshot, no comparison
across corpus scopes. A positive result here would say the slate mechanism works
under controlled conditions — **not** that the deployed lab feed serves real labs
well, which remains Q-009 and needs real declared profiles.
