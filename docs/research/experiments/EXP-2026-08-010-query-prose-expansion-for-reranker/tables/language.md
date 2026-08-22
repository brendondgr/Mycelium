### Is the cross-encoder's damage about documents it cannot read?

Per-query Δ nDCG@10 for `xenc over bm25 d50` − `bm25_only`, split by the share of that query's reranked candidate set whose title is not predominantly Latin-script.

| non-Latin share of the top-50 | queries | mean Δ nDCG@10 | 95% CI |
|---|---:|---:|---|
| 0% non-Latin | 277 | -0.0493 | [-0.0714, -0.0279] |
| 1-10% | 139 | -0.0389 | [-0.0702, -0.0085] |
| 10-25% | 27 | -0.0363 | [-0.0769, +0.0012] |
| >25% | 43 | -0.0361 | [-0.0833, +0.0112] |

**The language hypothesis is refuted.** Harm is *largest* where the candidate set is entirely Latin-script and *smallest* where non-Latin documents are most common — the opposite of the prediction. Whatever is wrong with the reranker on this collection, it is not that it cannot read the documents.
