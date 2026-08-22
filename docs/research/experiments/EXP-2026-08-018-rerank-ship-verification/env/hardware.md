# Hardware and environment

| Field | Value |
|---|---|
| CPU | 32 cores |
| RAM | 121 GB |
| GPU | none — no CUDA device on this host |
| Python | 3.13 |
| Lockfile | `web/backend/uv.lock` (`--extra embeddings`) |
| Container | `pgvector/pgvector:pg17` for the store; the pipeline runs on the host |
| Total wall clock | seconds |

## Where the time went

Nowhere worth reporting. The only measurable cost is the rerank pass itself:
**+2.59 s for 100 query-document pairs, about 38 pairs/s.**

## Anything about the hardware that affects the claim

**Yes, and it is the main caveat on the cost number.** This host has no CUDA
device, so the reranker runs on the CPU — and a cross-encoder is exactly the stage
a GPU helps most, since it is a forward pass per query-document pair rather than a
vector lookup. The deployment target has CUDA GPUs and
`apps/content/reranking.py` selects them automatically, so +2.59 s per target here
is an upper bound measured on the wrong hardware.

The invariance result is hardware-independent: it is a comparison of outputs, not
of timings.

Confirm the device on a real server with:

```
uv run --project web/backend python web/backend/manage.py rerank_device --load
```
