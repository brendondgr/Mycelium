# Hardware and environment

| Field | Value |
|---|---|
| CPU | 32 cores |
| RAM | 121 GB |
| GPU | none — no CUDA device on this host |
| Python | 3.13 (`eval` project) |
| Lockfile | `eval/uv.lock` |
| Container | `pgvector/pgvector:pg17` for the store; the arms run on the host |
| Total wall clock | ~70 s |

## Where the time went

Two arms, two queries, four corpora, and both arms pay a 50-pair cross-encoder
pass per cell — which is essentially all of it. The SPLADE matrices were encoded
once by `EXP-2026-08-014` and are content-addressed, so they load from cache in
under a second.

## Anything about the hardware that affects the claim

The per-query numbers are CPU numbers dominated by the cross-encoder, which **both
arms pay equally** — so the 1.432 s against 1.822 s gap is the extra sparse matmul
and pgvector scan, and it is the part a GPU would barely touch. The number that
decides this comparison is not on the clock at all: it is the ~23-minute one-time
SPLADE encode over the papers corpus, plus a second index to keep in step with the
corpus and a second model resident in the serving process.
