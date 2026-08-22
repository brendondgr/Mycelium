*10,000 paired bootstrap resamples over query ids, seed 20260821. Ties are exact per-query equality; the sign test excludes them.*

## `longeval-sci-2026/snapshot-1/train` — qrels `dctr`, 100 queries

| Contrast | mean Δ nDCG@10 | 95% CI | excludes 0 | win/loss/tie | sign p |
|---|---:|---|:--:|---|---:|
| xenc over bm25 d50 − bm25_only | +0.0001 | [-0.0418, +0.0427] | no | 41/37/22 | 0.734 |
| xenc over bm25 d100 − bm25_only | +0.0087 | [-0.0342, +0.0525] | no | 43/36/21 | 0.5 |
| xenc over fusion d50 − bm25_only | +0.0088 | [-0.0349, +0.0537] | no | 41/39/20 | 0.911 |
| xenc over fusion d50 − fusion_union_pool | +0.0243 | [-0.0104, +0.0609] | no | 44/33/23 | 0.254 |
| xenc over fusion d100 − fusion_union_pool | +0.0249 | [-0.0097, +0.0614] | no | 45/33/22 | 0.213 |
| fusion_union_pool − bm25_only | -0.0156 | [-0.0526, +0.0190] | no | 38/42/20 | 0.738 |

Per-query Δ for `xenc over bm25 d100` − `bm25_only`, split by query length:

| query length | queries | mean Δ nDCG@10 |
|---|---:|---:|
| 1 word | 5 | +0.0315 |
| 2 words | 27 | -0.0203 |
| 3-4 words | 33 | +0.0164 |
| 5+ words | 35 | +0.0206 |

## `longeval-sci/2025-01` — qrels `test`, 492 queries

*Not yet run: fusion_union_pool, xenc over fusion d50, xenc over fusion d100*

| Contrast | mean Δ nDCG@10 | 95% CI | excludes 0 | win/loss/tie | sign p |
|---|---:|---|:--:|---|---:|
| xenc over bm25 d50 − bm25_only | -0.0439 | [-0.0597, -0.0283] | **yes** | 139/218/135 | 3.41e-05 |
| xenc over bm25 d100 − bm25_only | -0.0541 | [-0.0704, -0.0380] | **yes** | 130/228/134 | 2.5e-07 |

Per-query Δ for `xenc over bm25 d100` − `bm25_only`, split by query length:

| query length | queries | mean Δ nDCG@10 |
|---|---:|---:|
| 1 word | 231 | -0.0530 |
| 2 words | 181 | -0.0510 |
| 3-4 words | 48 | -0.1081 |
| 5+ words | 32 | +0.0009 |

