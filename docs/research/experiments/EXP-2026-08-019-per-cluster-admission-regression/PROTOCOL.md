# Protocol — per-cluster admission: harness regression check

## The obligation

`docs/skills/global.md` requires a fresh evaluation run for any change to the
ranking path — `retrieval.py`, `lexical.py`, `fusion.py`, `ranking.py`, or
`pipeline.py`'s pool construction. The per-cluster redesign changed
`pipeline.fuse_clusters_pool`'s **admission** step: a single absolute cosine
threshold across the whole profile became a two-part gate (the absolute floor
**or** a candidate reaching `CLUSTER_ADMIT_FRAC` of its own theme's best score,
with `CLUSTER_ADMIT_HARD_FLOOR` beneath both). Two harness arms call that
function with a real `match_threshold`, so they are in scope.

This is a **regression check**, not a quality measurement. It asks one question
and does not attempt the other.

## Question

Does widening admission per theme change what the harness's cluster arms
retrieve, and if so by how much?

## Hypothesis (written before the run)

The relative floor admits strictly more candidates, so the surfaced set can only
grow or stay the same. But both arms already surface at the
`surface_limit = 250` backstop, so anything the wider gate admits should be
truncated before scoring and the metrics should be **unchanged**. If they move,
the gate is reaching further up the ranking than intended and the hard floor is
too low.

## Arms

| Arm | Config | What it is |
| --- | --- | --- |
| `clustered_profile` | `eval/configs/slateexp_clustered_profile_prod_coherent.toml` | Cluster-scoped aggregation under production surfacing |
| `slate_profile` | `eval/configs/slateexp_slate_profile_prod_coherent.toml` | The same, plus the per-theme slate fold-in |

Both at `grouping=coherent`, `beta=0.15`, `pool_per_interest=100`,
`surface_limit=250`, `match_threshold=0.5`, `n_profiles=30`, `seed=20260809`.

## Procedure

1. Record the pre-change baseline by locating the newest committed result file
   for each arm at the **same `config_hash`** (the harness hashes the parameter
   block, so a differing hash is a different experiment, not a comparison).
2. Re-run both arms on the post-change tree, one process, one corpus load.
3. Compare the metric block *and* the diagnostics block. Diagnostics are the
   stronger evidence here: `surfacing` reports how many candidates were surfaced
   per profile, and `clusters_cleared_per_candidate` reports the admitted set's
   shape. Metrics can coincide; those cannot.

## Decision rule

- Diagnostics identical **and** metrics identical → the gate is inert on this
  harness. Report it as such and do not claim it helps or harms.
- Diagnostics differ → the gate is live here; report the metric delta with a
  paired interval (`eval/harness/stats.py`), never as a bare difference.
- Metrics differ while diagnostics are identical → suspect the tie-ordering trap
  recorded against `ir_measures`, not a ranking change. Confirm against a second
  baseline commit before attributing it to anything.

## What this cannot answer

Whether per-cluster admission improves the product. The harness has no notion of
a reader with several research themes competing for one feed, which is the entire
situation the gate exists for, and its synthetic profiles are built by clustering
query embeddings rather than by a person declaring themes. A favourable number
here would not be evidence for the change and an unfavourable one would not be
evidence against it. That question is open.
