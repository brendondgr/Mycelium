# Hardware and environment

| Field | Value |
|---|---|
| CPU | 32 cores, x86-64 |
| RAM | 121 GB |
| GPU | none — CPU only, on the host |
| Python | 3.13 |
| Lockfile | `eval/uv.lock` |
| Container | none — run on the host |
| Total wall clock | see `manifest.yaml: compute.wall_clock_hours` |

## Where the time went

Two invocations. A three-cell plumbing smoke (see `ISSUES.md`), then the full
45-cell grid in a single process, so the 869,902-document corpus and its cached
embedding matrix were loaded once and reused across every config.

Embedding cost was **zero** — the `data/eval-cache/embeddings/` matrix from
`EXP-2026-08-001` was hit on the first arm, so no document was re-embedded. Only
the 100 queries were encoded, once per grouping mode per process. The collection
was already extracted in `~/.ir_datasets` from `EXP-2026-08-003`, so nothing was
re-downloaded.

The one arm family that costs materially more CPU than the others is `mmr`: its
selection is greedy over the whole admitted pool for each of 250 slots, so it is
O(pool × limit) per profile rather than O(pool log pool). At this pool size that
is a few extra seconds per cell, not a design constraint.

## Anything about the hardware that affects the claim

Nothing. Every arm is deterministic, CPU-only, and exact — `NumpyIndex` computes
the ranking pgvector's sequential scan would. The comparison is paired within a
process over identical inputs; a different machine reproduces it exactly.

Determinism needed one fix to be true of this experiment specifically.
`combine_clusters` iterates a `set` of document ids, so its ordering among exactly
equal scores depends on Python's per-process string hashing. Every spread function
therefore re-sorts on `(-score, id)` before doing anything else, and
`apps/content/tests/test_fusion_spread.py::test_every_mechanism_is_order_stable_across_calls`
pins it. This matters more here than in earlier experiments because a spread
policy's *order* is its output, so an unstable input order would be an unstable
result.

The only remaining stochastic element anywhere is the seeded bootstrap in
`build_metrics.py`.
