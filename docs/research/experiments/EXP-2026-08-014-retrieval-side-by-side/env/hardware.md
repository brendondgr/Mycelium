# Hardware and environment

| Field | Value |
|---|---|
| CPU | 32 cores |
| RAM | 121 GB |
| GPU | none — no CUDA device on this host |
| Python | 3.13 (`eval` project) |
| Lockfile | `eval/uv.lock` |
| Container | `pgvector/pgvector:pg17` for the store; the arms run on the host |
| Total wall clock | ~27 min — 25 min of it the one-time SPLADE encode |

## Where the time went

| Stage | Time |
|---|---|
| SPLADE encode, 39,106 documents across four corpora | **1,527 s** (papers 1,381 s at 25.5 docs/s) |
| All ten arms, three queries, four corpora | 92 s |
| BM25 index build, 35,205 papers | 2.3 s |
| SPLADE matrix load from cache, 35,205 papers | 0.8 s |
| Booklet + figure | seconds |

The encode is 94% of the wall clock and is paid once per document, so it is a
property of adopting SPLADE rather than of running this experiment. The measured
25.5 docs/s is below the 24.3 docs/s figure in `EXP-2026-08-008` only because
that host was otherwise idle; here Postgres was serving alongside it.

## Anything about the hardware that affects the claim

The **latency numbers are CPU numbers and would not survive a GPU**. The
cross-encoder arms cost 0.94–1.46 s per query here because 50 query-document
pairs run through an ONNX cross-encoder on CPU; on a GPU that gap would close
substantially. The ratio to quote is therefore "15–180× the retrieval it reranks
*on this hardware*", and this host has no CUDA device — which is also why the
reranker measured throughout this programme is a 22M-parameter model.

Encodes run one at a time. `EXP-2026-08-008` ISSUES §5 measured two concurrent
ONNX sessions on this host as catastrophically slower than serial, so
`code/run.py` (which loads the cross-encoder) was started only after
`code/encode_splade.py` had exited.
