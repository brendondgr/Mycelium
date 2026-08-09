# EXP-2026-08-003 — Issues, anomalies, and gotchas

## A hand-rolled metric, declared

`eval/harness/scoring.py` carries a standing rule: never hand-roll a metric,
because `ir_measures` is the implementation the LongEval overview papers score
with and a number produced through it is directly comparable to a published one.

This experiment breaks that rule for three metrics — `min_cluster_recall`,
`cluster_coverage`, `cluster_gini` — in `eval/harness/cluster_metrics.py`.

**Why it is unavoidable.** A *cluster* is a property of the profile doing the
searching, not of the collection. No qrels file says which of a user's research
themes a document belongs to; the attribution has to be derived from which of the
profile's constituent queries judged the document relevant, which only the harness
knows. C-003 is a coverage claim, and nDCG@10 over a union of judgments is blind
to which theme the relevant documents came from.

**What the exception costs, and was paid.** `eval/tests/test_cluster_metrics.py`
pins every metric to hand-computed expected values on small fixtures, with the
arithmetic written out in a comment above each assertion. The relevance family
(`nDCG@10`, `R@100`) still goes through `ir_measures` untouched, so the guardrail
numbers remain externally comparable even though the coverage numbers are not.

**What a reader should not do with them.** These three numbers are comparable
*within* this experiment — between arms, across grouping modes and β. They are not
comparable to any published number, because no published number uses them.

## The abstention floor — instrumented regardless of outcome

The design plan named this the most likely bug: `fuse_interest` drops a candidate
below the 0.15 floor *before* aggregation, so an interest that weakly matches
contributes nothing rather than a low score. Under clustering that culling happens
per interest while aggregation happens per cluster, so it is easy to end up with
clusters that are empty for most candidates — which would make the two arms agree
trivially and the comparison measure nothing.

Both arms therefore record how many interests (flat) or clusters (clustered) each
surfaced candidate cleared. Generated from `data/metrics.json`, never typed:

<!-- BEGIN GENERATED DIAGNOSTICS -->

| Arm | Grouping | β | Cleared 1 | Cleared 2 | Cleared 3 | Share clearing ≥ 2 |
|---|---|---:|---:|---:|---:|---:|
| `clustered_profile` | `coherent` | 0.0 | 14963 | 1552 | 51 | 9.7% |
| `clustered_profile` | `coherent` | 0.15 | 14963 | 1552 | 51 | 9.7% |
| `clustered_profile` | `coherent` | 0.3 | 14963 | 1552 | 51 | 9.7% |
| `clustered_profile` | `imbalanced` | 0.0 | 14708 | 781 | 19 | 5.2% |
| `clustered_profile` | `imbalanced` | 0.15 | 14708 | 781 | 19 | 5.2% |
| `clustered_profile` | `imbalanced` | 0.3 | 14708 | 781 | 19 | 5.2% |
| `clustered_profile` | `random` | 0.0 | 13447 | 2948 | 171 | 18.8% |
| `clustered_profile` | `random` | 0.15 | 13447 | 2948 | 171 | 18.8% |
| `clustered_profile` | `random` | 0.3 | 13447 | 2948 | 171 | 18.8% |
| `flat_profile` | `coherent` | 0.0 | 12660 | 3433 | 418 | 23.6% |
| `flat_profile` | `coherent` | 0.15 | 12660 | 3433 | 418 | 23.6% |
| `flat_profile` | `coherent` | 0.3 | 12660 | 3433 | 418 | 23.6% |
| `flat_profile` | `imbalanced` | 0.0 | 12782 | 2518 | 193 | 17.6% |
| `flat_profile` | `imbalanced` | 0.15 | 12782 | 2518 | 193 | 17.6% |
| `flat_profile` | `imbalanced` | 0.3 | 12782 | 2518 | 193 | 17.6% |
| `flat_profile` | `random` | 0.0 | 12660 | 3433 | 418 | 23.6% |
| `flat_profile` | `random` | 0.15 | 12660 | 3433 | 418 | 23.6% |
| `flat_profile` | `random` | 0.3 | 12660 | 3433 | 418 | 23.6% |

<!-- END GENERATED DIAGNOSTICS -->

## Truncation guarantees do not bind at this depth

The flat path reserves each interest's best paper (`with_floor_guarantee`); the
cluster path reserves each cluster's best (`cap_clusters`). §8 of the design plan
flagged the difference as something to state rather than remove.

Both arms run at `surface_limit = 5000`, above the maximum possible pool size
(`k_interests × pool_per_interest` = 600), so **neither guarantee can bind**. The
measured difference between arms is attributable to `combine_interests` vs
`combine_clusters` alone. A run at a surfacing depth below 600 would be a
different experiment and is not what these numbers describe.

## The tree was dirty when the runs executed

`manifest.yaml` records `code.dirty: true`. The uncommitted changes were the
harness code this experiment adds — `profiles.py`, `cluster_metrics.py`, the two
profile arms, the `scoring.py` per-topic path, and the 18 configs — which were
committed in the same change as this folder, per the process rule. The recorded
`code.commit` is the commit *before* that change; the runs were produced by the
working tree that became it. No production ranking code was modified.

## The corpus was re-downloaded

`~/.ir_datasets` was empty at the start of the session, so `ir_datasets_longeval`
re-fetched the whole 2026 family (~11 GB) before the first run. Registration is
eager — constructing one subset downloads the family — so this is expected cost,
not an error. The embedding matrix cache in `data/eval-cache/embeddings/` survived
and was hit on the first arm (`869902 docs`), so no corpus was re-embedded.
