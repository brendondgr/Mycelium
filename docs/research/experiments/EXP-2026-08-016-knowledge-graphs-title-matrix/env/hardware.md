# Hardware and environment

| Field | Value |
|---|---|
| CPU | 32 cores |
| RAM | 121 GB |
| GPU | none — no CUDA device on this host |
| Python | 3.13 (`eval` project) |
| Lockfile | `eval/uv.lock` |
| Container | `pgvector/pgvector:pg17` for the store; the arms run on the host |
| Total wall clock | ~15 s |

## Where the time went

Nowhere. Four arms, one query, four corpora. The SPLADE matrices were encoded
once by `EXP-2026-08-014` and are content-addressed, so they load from cache in
under a second.

## Anything about the hardware that affects the claim

The **cross-encoder latency is a CPU number**: 0.911 s/query against 0.055–0.084 s
for the single-stage arms, from 50 query-document pairs through an ONNX
cross-encoder with no GPU on this host. Quote it as "~16× on this hardware", not
as a property of cross-encoders. It is uniformly cheaper than the healthcare
query for the ordinary reason that a two-word query does less work than a
four-word one.
