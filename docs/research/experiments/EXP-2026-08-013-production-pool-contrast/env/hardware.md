# Hardware and environment

| Field | Value |
|---|---|
| CPU | 32 cores |
| RAM | 121 GB |
| GPU | none — no CUDA device on this host |
| Python | 3.13 (`eval` project) |
| Lockfile | `eval/uv.lock` |
| Container | `pgvector/pgvector:pg17` for the store; the arms run on the host |
| Total wall clock | ~6 minutes for `code/run.py`, plus ~2 minutes for `code/premise.py` and seconds for `code/analyse.py` |

## Where the time went

Nothing dominates, which is the point: this experiment does **no encoding**.
Every document embedding it needs is already stored in `ContentItem.embedding`,
and the only vectors computed at run time are 38 interest queries (cached across
regimes) plus one probe for the alignment gate. That is why a contrast which cost
5.4 hours on LongEval (`EXP-2026-08-012`, two corpus encodes) costs six minutes
here.

The largest single cost is building the corpus-wide BM25 index once per regime —
21 regimes, the biggest being 35,205 documents. `rank_bm25.BM25Okapi` holds the
whole index in process, which is fine at this size and is exactly why arm A3/A4
exists: it is **not** fine as a production design, and Postgres FTS is the
channel that would have to carry it.

## Anything about the hardware that affects the claim

No. Every arm is deterministic and none is compute-bound at this corpus size —
re-running one regime reproduced all 44 of its rows field-for-field (ISSUES §10).
The absence of a GPU shaped the rest of this programme (it is why the cross-encoder
was a 22M-parameter model) but is irrelevant here, because no neural model runs
beyond 38 cached query embeddings.

The one environment fact that *does* matter is the embedder: the query side must
be the same model that produced the stored corpus embeddings, or every dense pool
is wrong. That is checked rather than assumed — gate 0 in `code/run.py`.
