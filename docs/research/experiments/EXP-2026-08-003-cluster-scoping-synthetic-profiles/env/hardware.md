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

Almost none of it went to the arms. A single profile arm scores 30 profiles ×
6 interests = 180 dense probes over 869,902 documents plus one BM25 index per
profile over its ≤ 600-document pool, which is minutes.

The costs that dominated, in order:

1. **Re-downloading the collection.** `~/.ir_datasets` was empty, and
   `ir_datasets_longeval` registration is eager — constructing one subset
   downloads its whole family. ~11 GB before the first arm ran.
2. **Loading 869,902 documents** into memory from the extracted collection, once
   per process. `eval/run.py` memoizes the corpus across configs in a single
   invocation specifically so the 18-cell grid pays this once rather than
   eighteen times.
3. **Embedding: zero.** The `data/eval-cache/embeddings/` matrix from
   `EXP-2026-08-001` was hit on the first arm (869,902 docs), so no document was
   re-embedded. Only the 100 queries were encoded, once per grouping mode.

## Anything about the hardware that affects the claim

Nothing. Every arm is deterministic, CPU-only, and exact — `NumpyIndex` computes
the same ranking pgvector's sequential scan would, so there is no
approximation-versus-hardware tradeoff hiding in these numbers. The comparison is
paired within a single process over identical inputs; a different machine would
reproduce it exactly.
