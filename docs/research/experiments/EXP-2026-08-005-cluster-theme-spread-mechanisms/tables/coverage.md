| Arm | Measure | baseline | treatment | Δ | 95% CI |
|---|---|---:|---:|---:|---|
| `flat_profile` | `min_cluster_recall@10` | 0.0049 | 0.0081 | **+0.0032** | [+0.0007, +0.0066] |
| `flat_profile` | `cluster_coverage@10` | 0.5667 | 0.6111 | +0.0444 | [+0.0000, +0.1000] — spans 0 |
| `flat_profile` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3452 | -0.0056 | [-0.0656, +0.0589] — spans 0 |
| `spread_identity` | `min_cluster_recall@10` | 0.0049 | 0.0049 | +0.0000 | [+0.0000, +0.0000] — spans 0 |
| `spread_identity` | `cluster_coverage@10` | 0.5667 | 0.5667 | +0.0000 | [+0.0000, +0.0000] — spans 0 |
| `spread_identity` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3507 | +0.0000 | [+0.0000, +0.0000] — spans 0 |
| `spread_interleave` | `min_cluster_recall@10` | 0.0049 | 0.0085 | **+0.0035** | [+0.0007, +0.0064] |
| `spread_interleave` | `cluster_coverage@10` | 0.5667 | 0.6111 | +0.0444 | [-0.0111, +0.1000] — spans 0 |
| `spread_interleave` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3448 | -0.0059 | [-0.0730, +0.0681] — spans 0 |
| `spread_quota` | `min_cluster_recall@10` | 0.0049 | 0.0085 | **+0.0035** | [+0.0007, +0.0064] |
| `spread_quota` | `cluster_coverage@10` | 0.5667 | 0.6111 | +0.0444 | [-0.0111, +0.1000] — spans 0 |
| `spread_quota` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3448 | -0.0059 | [-0.0730, +0.0681] — spans 0 |
| `spread_cap` | `min_cluster_recall@10` | 0.0049 | 0.0056 | +0.0007 | [+0.0000, +0.0021] — spans 0 |
| `spread_cap` | `cluster_coverage@10` | 0.5667 | 0.5889 | +0.0222 | [+0.0000, +0.0556] — spans 0 |
| `spread_cap` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3648 | +0.0141 | [-0.0256, +0.0678] — spans 0 |
| `spread_mmr` | `min_cluster_recall@10` | 0.0049 | 0.0092 | **+0.0043** | [+0.0014, +0.0078] |
| `spread_mmr` | `cluster_coverage@10` | 0.5667 | 0.6444 | **+0.0778** | [+0.0333, +0.1333] |
| `spread_mmr` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3099 | -0.0408 | [-0.1050, +0.0289] — spans 0 |
| `spread_rankmerge` | `min_cluster_recall@10` | 0.0049 | 0.0096 | **+0.0047** | [+0.0010, +0.0089] |
| `spread_rankmerge` | `cluster_coverage@10` | 0.5667 | 0.6444 | **+0.0778** | [+0.0111, +0.1444] |
| `spread_rankmerge` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3093 | -0.0415 | [-0.1178, +0.0400] — spans 0 |
| `spread_floor` | `min_cluster_recall@10` | 0.0049 | 0.0049 | +0.0000 | [+0.0000, +0.0000] — spans 0 |
| `spread_floor` | `cluster_coverage@10` | 0.5667 | 0.5667 | +0.0000 | [+0.0000, +0.0000] — spans 0 |
| `spread_floor` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3507 | +0.0000 | [+0.0000, +0.0000] — spans 0 |
| `spread_rankmerge_interleave` | `min_cluster_recall@10` | 0.0049 | 0.0085 | **+0.0035** | [+0.0007, +0.0064] |
| `spread_rankmerge_interleave` | `cluster_coverage@10` | 0.5667 | 0.6111 | +0.0444 | [-0.0111, +0.1000] — spans 0 |
| `spread_rankmerge_interleave` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3448 | -0.0059 | [-0.0730, +0.0681] — spans 0 |
| `spread_rankmerge_quota` | `min_cluster_recall@10` | 0.0049 | 0.0085 | **+0.0035** | [+0.0007, +0.0064] |
| `spread_rankmerge_quota` | `cluster_coverage@10` | 0.5667 | 0.6111 | +0.0444 | [-0.0111, +0.1000] — spans 0 |
| `spread_rankmerge_quota` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3448 | -0.0059 | [-0.0730, +0.0681] — spans 0 |
| `spread_rankmerge_cap` | `min_cluster_recall@10` | 0.0049 | 0.0096 | **+0.0047** | [+0.0010, +0.0089] |
| `spread_rankmerge_cap` | `cluster_coverage@10` | 0.5667 | 0.6444 | **+0.0778** | [+0.0111, +0.1444] |
| `spread_rankmerge_cap` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3093 | -0.0415 | [-0.1178, +0.0400] — spans 0 |
| `spread_rankmerge_mmr` | `min_cluster_recall@10` | 0.0049 | 0.0096 | **+0.0047** | [+0.0010, +0.0089] |
| `spread_rankmerge_mmr` | `cluster_coverage@10` | 0.5667 | 0.6444 | **+0.0778** | [+0.0111, +0.1444] |
| `spread_rankmerge_mmr` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3093 | -0.0415 | [-0.1178, +0.0400] — spans 0 |
| `spread_floor_interleave` | `min_cluster_recall@10` | 0.0049 | 0.0085 | **+0.0035** | [+0.0007, +0.0064] |
| `spread_floor_interleave` | `cluster_coverage@10` | 0.5667 | 0.6111 | +0.0444 | [-0.0111, +0.1000] — spans 0 |
| `spread_floor_interleave` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3448 | -0.0059 | [-0.0730, +0.0681] — spans 0 |
| `spread_all` | `min_cluster_recall@10` | 0.0049 | 0.0085 | **+0.0035** | [+0.0007, +0.0064] |
| `spread_all` | `cluster_coverage@10` | 0.5667 | 0.6111 | +0.0444 | [-0.0111, +0.1000] — spans 0 |
| `spread_all` | `cluster_gini@10` (lower is better) | 0.3507 | 0.3448 | -0.0059 | [-0.0730, +0.0681] — spans 0 |
