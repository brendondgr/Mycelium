*10,000 paired bootstrap resamples over query ids, seed 20260821. Ties are exact per-query equality; the sign test excludes them. Qrels are click-derived on sci-2026-train, not human assessment.*

## `longeval-sci-2026/snapshot-1/train` — qrels `dctr`, 100 queries

*Not run: typesafe_noul over fusion, fusion_union_pool*

| Contrast | mean Δ nDCG@10 | 95% CI | excludes 0 | win/loss/tie | sign p |
|---|---:|---|:--:|---|---:|
| typesafe_noul over bm25 − bm25_only | +0.0185 | [-0.0207, +0.0603] | no | 43/36/21 | 0.5 |
| typesafe_score over bm25 − bm25_only | -0.0052 | [-0.0460, +0.0384] | no | 38/39/23 | 1 |
| typesafe_noul over bm25 − typesafe_score over bm25 | +0.0237 | [+0.0074, +0.0413] | **yes** | 39/20/41 | 0.0183 |

Per-query Δ for `typesafe_noul over bm25` − `bm25_only`, split by query length:

| query length | queries | mean Δ nDCG@10 |
|---|---:|---:|
| 1 word | 5 | +0.0567 |
| 2 words | 27 | +0.0029 |
| 3-4 words | 33 | +0.0393 |
| 5+ words | 35 | +0.0054 |

