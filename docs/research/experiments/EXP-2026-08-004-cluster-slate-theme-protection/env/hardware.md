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

Three sequential invocations, each loading the 869,902-document corpus once and
reusing it across its configs: the 18-cell `prod`/`cut30` grid, a nine-cell
re-run of `cut30` with whole-set cut-offs added (see `ISSUES.md`), and the
six-cell size-matched `cut34` condition.

Embedding cost was **zero** — the `data/eval-cache/embeddings/` matrix from
`EXP-2026-08-001` was hit on the first arm of each invocation, so no document was
re-embedded. Only the 100 queries were encoded, once per grouping mode per
process. The collection was already extracted in `~/.ir_datasets` from
`EXP-2026-08-003`, so nothing was re-downloaded.

## Anything about the hardware that affects the claim

Nothing. Every arm is deterministic, CPU-only, and exact — `NumpyIndex` computes
the ranking pgvector's sequential scan would. The comparison is paired within a
process over identical inputs; a different machine reproduces it exactly. The
only stochastic element anywhere is the seeded bootstrap in `build_metrics.py`.
