# Hardware and environment

| Field | Value |
|---|---|
| CPU | 32 cores |
| RAM | 130 GB |
| GPU | **None.** No CUDA device on this host — every number was produced on CPU |
| Python | 3.13 (exact patch not recorded; see `../ISSUES.md`) |
| Lockfile | `eval/uv.lock` |
| Container | None — run on the host, not in Compose |
| Total wall clock | 7.97 h across the 31 committed runs |

## Where the time went

| Run | Wall clock |
|---|---:|
| `dense_only`, full corpus, 2026 snapshot | 25,509 s (~7.1 h) |
| `bm25_only`, full corpus, 2026 snapshot | 360 s |
| Fusion arms, full corpus, 2026 snapshot | 17–19 s each |
| Pooled arms | seconds |

Nearly all of it is one arm: embedding 869,902 documents on CPU at ~33–39 docs/s.
The fusion arms are seconds because they reuse that embedding cache — which is
why the cache lives outside the worktree, and why deleting it costs hours rather
than minutes.

**A GPU run would be faster and identical in ranking.** The embedder is
deterministic; hardware changes throughput, not output.

## Why CPU-only matters for the claim

The organizers' Qwen3-Embedding-4B baseline is an order of magnitude larger than
`bge-small-en-v1.5` and was not run on this host — its numbers are the
organizers' own, re-scored here. So the comparison in `fig-baseline-gap` is not
compute-matched, and it is not meant to be: it asks whether a much larger dense
model would have escaped the BM25 gap. It did not.
