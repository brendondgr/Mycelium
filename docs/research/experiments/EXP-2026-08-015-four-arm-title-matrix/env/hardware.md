# Hardware and environment

| Field | Value |
|---|---|
| CPU | 32 cores |
| RAM | 121 GB |
| GPU | none — no CUDA device on this host |
| Python | 3.13 (`eval` project) |
| Lockfile | `eval/uv.lock` |
| Container | `pgvector/pgvector:pg17` for the store; the arms run on the host |
| Total wall clock | ~20 s |

## Where the time went

Nowhere worth reporting: four arms, one query, four corpora, twenty seconds. The
expensive part — encoding SPLADE over 39,106 documents — was paid once by
`EXP-2026-08-014` and is content-addressed, so this run loaded the matrices from
cache in under a second.

## Anything about the hardware that affects the claim

The **cross-encoder latency is a CPU number**. 1.866 s/query for the reranked arm
against 0.094–0.186 s for the single-stage arms reflects 50 query-document pairs
through an ONNX cross-encoder with no GPU on this host. On a GPU that ratio would
narrow substantially, so quote it as "18× on this hardware" rather than as a
property of cross-encoders.
