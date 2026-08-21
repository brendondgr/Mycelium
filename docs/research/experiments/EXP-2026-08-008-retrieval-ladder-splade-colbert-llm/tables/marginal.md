### What each stage adds, one change at a time

| Stack | nDCG@10 | nDCG@100 | R@100 | Δ nDCG@10 | Δ nDCG@100 | Δ R@100 |
|---|---:|---:|---:|---:|---:|---:|
| production — BM25 restricted to the dense pool | 0.2937 | 0.3829 | 0.5988 | — | — | — |
| + union pool, so the lexical channel can *add* a document | 0.3056 | 0.4129 | 0.6511 | +0.0119 | +0.0300 | +0.0523 |
| + SPLADE as a third RRF channel | 0.3184 | 0.4356 | 0.7141 | +0.0128 | +0.0226 | +0.0630 |
| + cross-encoder rerank (depth 100) | 0.3305 | 0.4492 | 0.7141 | +0.0121 | +0.0137 | +0.0000 |

### Does reranking deeper pay?

| Cross-encoder arm | nDCG@10 | wall clock |
|---|---:|---:|
| xenc_rerank d50 | 0.3299 | 282 s |
| xenc_rerank d100 | 0.3304 | 377 s |
| xenc_rerank p500 d250 | 0.3307 | 913 s |
| xenc_rerank p500 d1000 | 0.3306 | 1052 s |

### Stages that cost and do not pay

| Arm | nDCG@10 | vs `fusion_union_pool` | one-time encode |
|---|---:|---:|---|
| colbert_rerank d50 | 0.2951 | -0.0105 | 3,640 s + 22.4M token vectors |
| colbert_rerank d100 | 0.2903 | -0.0153 | (same store) |
| cascade colbert250 -> xenc50 | 0.3248 | +0.0192 | (same store) |
| llm_rerank (listwise) | 0.3177 | +0.0121 | none — 1 model call per query |
| llm_rubric (pointwise) | 0.3095 | +0.0040 | none — 20 model calls per query |

One-time corpus encoding over the 84,489-document subset, CPU, no GPU: dense **0 s** (row-sliced from the cached full-corpus matrix), SPLADE **3,451 s** (24.5 docs/s), ColBERT **3,640 s** (23.2 docs/s), cross-encoder **0 s** — it never encodes a corpus, which is why it is the cheapest stage on the ladder as well as the only one that beats BM25.
