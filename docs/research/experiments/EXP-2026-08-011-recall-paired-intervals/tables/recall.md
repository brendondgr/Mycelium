*Snapshot `longeval-sci-2026/snapshot-1/train`, qrels `dctr`, pooled scope. 10,000 paired bootstrap resamples over query ids, seed 20260821. R@100 here is recall **within the pooled subset** — a re-ranking evaluation, not a claim about a full corpus.*

### Reproduction gate

| Arm | R@100 now | R@100 recorded | matches |
|---|---:|---:|:--:|
| dense_only | 0.6120 | 0.6120 | yes |
| fusion_dense_pool | 0.5988 | 0.5988 | yes |
| fusion_union_pool | 0.6511 | 0.6511 | yes |
| fusion_bm25_dense_splade | 0.7141 | 0.7141 | yes |
| bm25_only | 0.6903 | 0.6903 | yes |

### R@100

| Contrast | claim | mean Δ | 95% CI | excludes 0 | win/loss/tie | sign p |
|---|:--:|---:|---|:--:|---|---:|
| fusion_union_pool − fusion_dense_pool | C-008 | +0.0523 | [+0.0235, +0.0858] | **yes** | 28/10/62 | 0.0051 |
| fusion_bm25_dense_splade − fusion_union_pool | C-014 | +0.0630 | [+0.0396, +0.0923] | **yes** | 39/3/58 | 5.63e-09 |
| fusion_bm25_dense_splade − bm25_only | — | +0.0238 | [+0.0031, +0.0465] | **yes** | 24/15/61 | 0.2 |
| fusion_union_pool − bm25_only | — | -0.0392 | [-0.0711, -0.0100] | **yes** | 14/32/54 | 0.0114 |

### nDCG@100

| Contrast | claim | mean Δ | 95% CI | excludes 0 | win/loss/tie | sign p |
|---|:--:|---:|---|:--:|---|---:|
| fusion_union_pool − fusion_dense_pool | C-008 | +0.0300 | [+0.0155, +0.0455] | **yes** | 59/25/16 | 0.000266 |
| fusion_bm25_dense_splade − fusion_union_pool | C-014 | +0.0226 | [+0.0082, +0.0374] | **yes** | 62/28/10 | 0.000438 |
| fusion_bm25_dense_splade − bm25_only | — | +0.0042 | [-0.0273, +0.0339] | no | 50/43/7 | 0.534 |
| fusion_union_pool − bm25_only | — | -0.0185 | [-0.0473, +0.0090] | no | 43/49/8 | 0.602 |

### nDCG@10

| Contrast | claim | mean Δ | 95% CI | excludes 0 | win/loss/tie | sign p |
|---|:--:|---:|---|:--:|---|---:|
| fusion_union_pool − fusion_dense_pool | C-008 | +0.0119 | [-0.0036, +0.0282] | no | 35/27/38 | 0.374 |
| fusion_bm25_dense_splade − fusion_union_pool | C-014 | +0.0128 | [-0.0096, +0.0345] | no | 46/24/30 | 0.0115 |
| fusion_bm25_dense_splade − bm25_only | — | -0.0028 | [-0.0458, +0.0389] | no | 43/39/18 | 0.741 |
| fusion_union_pool − bm25_only | — | -0.0156 | [-0.0526, +0.0190] | no | 38/42/20 | 0.738 |
