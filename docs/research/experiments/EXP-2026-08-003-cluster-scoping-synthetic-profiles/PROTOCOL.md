# EXP-2026-08-003 — Protocol

Written before the runs. Nothing below was edited after the numbers landed;
corrections, if any, are appended to `RESULTS.md` under `AMENDMENTS`.

## Question

For a profile whose declared interests span several research themes, does
combining within clusters and max-pooling across them leave the **worst-served
theme** better served in the top 10 than flat combination over all interests
does — and at what cost to overall relevance?

## Hypothesis

Clustered aggregation raises `min_cluster_recall@10` relative to flat
aggregation, most under the `imbalanced` grouping (where one theme's vocabulary
sits far closer to the corpus than the others'), not at all under `random`
grouping, and the gap widens with β.

The reasoning: flat combination scores a candidate by `mean × (1 + β(n−1))` over
every interest it matched, so a paper that touches several interests shallowly
outranks a paper that is excellent for exactly one theme. As β rises, that
preference strengthens. Clustered combination confines the breadth bonus inside a
cluster and takes the max across clusters, so a theme's best paper competes on
its own strength. If C-003 is real, that difference shows up as the worst-served
cluster's recall.

## Setup

**System under test:** the deployed ranking stack in `web/backend/apps/content`,
called directly. `eval/harness/arms.py::flat_profile` wraps
`pipeline.fuse_interests_pool`; `clustered_profile` wraps
`pipeline.fuse_clusters_pool`. Both delegate to the same `_build_pool`, so the
two arms see an **identical candidate pool and an identical
`per_interest_scores` map**, and the only difference between them is the
aggregation step (`combine_interests` vs `combine_clusters`). Neither arm
contains aggregation logic of its own.

**Held fixed across every arm:** encoder (`BAAI/bge-small-en-v1.5`),
`pool_per_interest = 100`, the 0.15 per-interest abstention floor, RRF `k = 60`,
corpus scope (`full`), snapshot, seed, and the profile set — the comparison is
paired, profile by profile.

**Varied:** aggregation (2) × grouping mode (3) × β (3) = 18 cells.

**Truncation guarantees.** The flat path reserves each interest's best paper
(`with_floor_guarantee`); the cluster path reserves each cluster's best
(`cap_clusters`). Both are run at `surface_limit = 5000`, which is above the
maximum possible pool size (`k_interests × pool_per_interest` = 600), so
**neither guarantee can bind** and neither can contribute to the measured
difference. This is stated because §8 of the design plan flagged the two
guarantees as a possible confound: at this depth they are not one, and the
measured effect is attributable to mean-vs-max alone. A run at a surfacing depth
below 600 would be a different experiment.

## Data

LongEval-Sci 2026, snapshot 1, **train** split — 869,902 documents, 100 queries,
`dctr` qrels. Corpus scope `full` (no pooling), so recall numbers are corpus-wide.

**The judgments are not human assessments.** LongEval `dctr` qrels are
click-model-derived pseudo-relevance. That qualification attaches to every number
this experiment produces and is repeated in `RESULTS.md`.

### Profile construction

A **synthetic profile** is *K* = 6 of the collection's queries treated as six
declared interests, partitioned into *C* = 3 clusters of two. 30 profiles per
grouping mode, drawn from a candidate pool of 300, seed `20260809`.

Its relevance judgments are the **union** of its six constituent queries' qrels,
deduplicated, keeping the **maximum** grade where a document is judged for more
than one constituent query. Each cluster additionally carries its own relevant
set — the documents judged relevant (grade > 0) by that cluster's two queries —
which is what the coverage metrics attribute against.

### The grouping mode is the independent variable

| Mode | Construction | Role |
|---|---|---|
| `coherent` | Queries are embedded with the production encoder and agglomerated greedily into pairs by cosine similarity: take the most similar unused pair, repeat. A profile is three such pairs. | The condition C-003 assumes. |
| `random` | **The same 30 profiles** as `coherent` — identical interest sets, so the flat arm's ranking is bit-identical between the two modes — repartitioned into three pairs by a seeded shuffle. | Negative control. |
| `imbalanced` | The 30 candidate profiles with the largest **variance of score mass across their clusters**. | The condition C-003 actually claims to fix. |

**Score mass is fixed here, before the runs:** a query's mass is the mean cosine
of its top 100 dense hits over the full corpus; a cluster's mass is the mean of
its two queries' masses; a profile's imbalance is the population variance across
its three cluster masses. This rule is not tuned after seeing results.

Fused scores are deliberately *not* used for mass — `fuse_interest` min-max
normalizes within each interest, so every query's best candidate is 1.0 by
construction and the magnitudes are not comparable across queries. Judged-document
count is also deliberately not used: it is the denominator of the primary metric,
so selecting on it would bias the metric being reported.

Cluster **declaration order** is shuffled per profile from the seed, because
`combine_clusters` breaks argmax ties by earliest-declared cluster and, with
synthetic profiles, declaration order is otherwise an arbitrary hidden variable.

Greedy agglomeration rather than k-means: k-means gives clusters of uneven size,
which would vary cluster size alongside cluster coherence. Equal-size groups keep
coherence the only thing the mode changes.

## Metrics

Two families, reported together, always.

### Coverage — primary; this is what C-003 claims

For a top-*k* list, each relevant document is attributed to **every** cluster
whose own qrels judge it relevant. Clusters with no relevant documents at all are
excluded — they have no recall to be starved of.

| Metric | Definition | Direction |
|---|---|---|
| **`min_cluster_recall@10`** | **Primary.** Over the profile's clusters, the recall of the worst-served one. | higher better |
| `cluster_coverage@10` | Share of clusters contributing ≥ 1 relevant document to the top *k*. | higher better |
| `cluster_gini@10` | Gini coefficient of the per-cluster share of relevant documents in the top *k*. | **lower** better |

`min_cluster_recall@10` is primary because "no theme is starved" is literally the
claim, so the minimum is literally the metric. All three are also reported at
*k* = 100.

These three are **hand-written** (`eval/harness/cluster_metrics.py`), breaking the
harness's standing "never hand-roll a metric" rule. The justification, and the
hand-computed unit-test fixtures that are the price of the exception, are in that
module's docstring, `eval/tests/test_cluster_metrics.py`, and `ISSUES.md`. No IR
toolkit implements per-cluster coverage because a cluster is a property of the
profile, not of the collection.

### Relevance — guardrail

`nDCG@10` and `R@100` over the profile's union qrels, through `ir_measures`,
unchanged. If clustering evens out coverage while dropping nDCG@10, that is a
**tradeoff**, not a win, and C-003 must be rewritten as a tradeoff claim. The
intended output of this experiment is a two-axis picture — coverage gain against
relevance cost — not a single number.

## Baselines

`flat_profile` at the same grouping mode, same β, same profiles. That is the
right baseline because it is what the system did before clusters existed and it
is the "global ranking" C-003 names. There is no external baseline: no published
system scores a multi-cluster profile against LongEval, because the profiles do
not exist outside this harness.

## Statistics

**Paired bootstrap over profiles**, 10,000 resamples, seed `20260809`, resampling
profiles with replacement and recomputing the mean paired delta. Reported as the
delta with a 95% percentile confidence interval, for every arm pair.

`EXP-2026-08-002` recorded `statistical_test: null`, which was defensible there —
deterministic arms, one number per snapshot. It is not defensible here: this is a
per-profile comparison with n = 30 and effect sizes that may be small.

## Procedure

```bash
uv run --project eval eval/run.py --collection sci-2026-train \
  --config eval/configs/flat_profile_coherent_b015.toml \
           eval/configs/clustered_profile_coherent_b015.toml \
           eval/configs/flat_profile_random_b015.toml \
           eval/configs/clustered_profile_random_b015.toml
```

Gate on that first (stage 1 of the design plan's §7 sequencing), then the full
grid — all 18 configs in one process, so the corpus and its embedding matrix load
once:

```bash
uv run --project eval eval/run.py --collection sci-2026-train \
  --config eval/configs/flat_profile_*.toml eval/configs/clustered_profile_*.toml
```

Then derive the paired comparison and rebuild the record:

```bash
uv run --project scripts/research \
  docs/research/experiments/EXP-2026-08-003-cluster-scoping-synthetic-profiles/data/build_metrics.py
make figures research-index validate-research
```

## What would falsify this

Pre-registered, in the design plan's §3.6 and repeated here so they cannot be
renegotiated once the numbers are in.

1. **C-003 is decoration** if the clustered-vs-flat delta in
   `min_cluster_recall@10` under `imbalanced` has a 95% CI spanning zero. Mark
   C-003 `refuted`, keep the experiment, record it. Negative results are
   first-class here.
2. **The harness is wrong**, not the finding, if clustered beats flat under
   `random` grouping by a comparable margin. Fix before interpreting anything
   else.
3. **C-003 becomes a tradeoff claim** if coverage improves but nDCG@10 falls by
   more than the CI width. Rewrite the claim; do not report the coverage gain
   alone.
4. **The construction is degenerate** if flat and clustered produce identical
   rankings for more than 90% of profiles — most likely the abstention floor
   culling cross-cluster matches before aggregation ever sees them. Investigate
   the floor before proceeding.

The abstention-floor instrumentation runs regardless of outcome: both arms record
the distribution of how many interests (flat) or clusters (clustered) each
surfaced candidate cleared, and that distribution goes into `ISSUES.md` whether
or not falsifier 4 fires.

## Scope of any conclusion

- The profiles are **synthetic**. A real researcher's interests may not resemble
  greedy embedding pairs over LongEval topics. This tests the aggregation math
  under known conditions; it does not test whether real users have cluster-shaped
  interests.
- Union-of-qrels is an approximation. A document relevant to the *combination* of
  two interests but to neither alone is invisible to it.
- Judgments are click-derived, not human.
- `full` and `pooled` corpus scopes are not comparable on recall. Every run here
  is `full`; the coverage metrics inherit the rule.
