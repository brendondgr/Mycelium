*Paired bootstrap, 10,000 resamples over query ids, fixed seed. `R@100` is recall **within each snapshot's pooled subset** — a re-ranking evaluation, not a claim about a full corpus.*

### R@100 — the primary comparison

| Claim | Contrast | 2026 (100q, `dctr`) | 2025-01 (492q, `test`) | replicates |
|---|---|---|---|:--:|
| C-008 | fusion_union_pool − fusion_dense_pool | +0.0523 [+0.0235, +0.0858]<br>28W/10L, p=0.0051 | +0.2459 [+0.2196, +0.2717]<br>302W/21L, p=6.2e-65 | **yes** |
| C-014 | fusion_bm25_dense_splade − fusion_union_pool | +0.0630 [+0.0396, +0.0923]<br>39W/3L, p=5.6e-09 | *not run* | — |
| C-018 | fusion_union_pool − bm25_only | -0.0392 [-0.0711, -0.0100]<br>14W/32L, p=0.011 | -0.0219 [-0.0338, -0.0104]<br>48W/94L, p=0.00014 | **yes** |
| — | fusion_bm25_dense_splade − bm25_only | +0.0238 [+0.0031, +0.0465]<br>24W/15L, p=0.2 | *not run* | — |

### nDCG@100

| Claim | Contrast | 2026 | 2025-01 |
|---|---|---|---|
| C-008 | fusion_union_pool − fusion_dense_pool | +0.0300 | +0.0990 |
| C-014 | fusion_bm25_dense_splade − fusion_union_pool | +0.0226 | *not run* |
| C-018 | fusion_union_pool − bm25_only | -0.0185 (spans 0) | -0.0498 |
| — | fusion_bm25_dense_splade − bm25_only | +0.0042 (spans 0) | *not run* |

### nDCG@10

| Claim | Contrast | 2026 | 2025-01 |
|---|---|---|---|
| C-008 | fusion_union_pool − fusion_dense_pool | +0.0119 (spans 0) | +0.0369 |
| C-014 | fusion_bm25_dense_splade − fusion_union_pool | +0.0128 (spans 0) | *not run* |
| C-018 | fusion_union_pool − bm25_only | -0.0156 (spans 0) | -0.0666 |
| — | fusion_bm25_dense_splade − bm25_only | -0.0028 (spans 0) | *not run* |

### Absolute R@100 per arm

| Arm | 2026 | 2025-01 |
|---|---:|---:|
| dense_only | 0.6120 | 0.3348 |
| fusion_dense_pool | 0.5988 | 0.3294 |
| fusion_union_pool | 0.6511 | 0.5753 |
| fusion_bm25_dense_splade | 0.7141 | — |
| bm25_only | 0.6903 | 0.5972 |

*`sci-2025-01` — no run file for: fusion_bm25_dense_splade*
