| Snapshot | Scope | Arm | Pool | Docs | Q | nDCG@10 | nDCG@100 | AP | R@100 | RR | P@10 | Run |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `longeval-sci-2026/snapshot-1/train` | full | `bm25_only` | — | 869,902 | 100 | 0.3282 | 0.4340 | 0.2796 | 0.6854 | 0.4843 | 0.2110 | `de31887` |
| `longeval-sci-2026/snapshot-1/train` | full | `dense_only` | — | 869,902 | 100 | 0.2234 | 0.3162 | 0.1754 | 0.5456 | 0.3846 | 0.1590 | `5b66bc2` |
| `longeval-sci-2026/snapshot-1/train` | full | `fusion_dense_pool` | 100 | 869,902 | 100 | 0.2852 | 0.3549 | 0.2190 | 0.5419 | 0.4505 | 0.1980 | `5b66bc2` |
| `longeval-sci-2026/snapshot-1/train` | full | `fusion_full` | 100 | 869,902 | 100 | 0.2849 | 0.3563 | 0.2233 | 0.5419 | 0.4545 | 0.1960 | `5b66bc2` |
| `longeval-sci-2026/snapshot-1/train` | full | `fusion_union_pool` | 100 | 869,902 | 100 | 0.2993 | 0.4031 | 0.2519 | 0.6299 | 0.4734 | 0.1960 | `5b66bc2` |
| `longeval-sci-2026/snapshot-1/train` | full | `BM25 (PyTerrier, organizers)` | — | — | 100 | 0.2922 | 0.4123 | 0.2573 | 0.6836 | 0.4717 | 0.1950 | _published_ |
| `longeval-sci-2026/snapshot-1/train` | full | `Qwen3-Embedding-4B (organizers)` | — | — | 100 | 0.2820 | 0.3919 | 0.2378 | 0.6390 | 0.4389 | 0.1880 | _published_ |
| `longeval-sci-2026/snapshot-1/train` | pooled | `bm25_only` | — | 84,489 | 100 | 0.3212 | 0.4314 | 0.2760 | 0.6903 | 0.4788 | 0.2100 | `de31887` |
| `longeval-sci-2026/snapshot-1/train` | pooled | `dense_only` | — | 84,489 | 100 | 0.2401 | 0.3498 | 0.1965 | 0.6120 | 0.4067 | 0.1700 | `de31887` |
| `longeval-sci-2026/snapshot-1/train` | pooled | `fusion_dense_pool` | 100 | 84,489 | 100 | 0.2937 | 0.3829 | 0.2360 | 0.5988 | 0.4589 | 0.2010 | `de31887` |
| `longeval-sci-2026/snapshot-1/train` | pooled | `fusion_dense_pool` | 1000 | 84,489 | 100 | 0.2915 | 0.4191 | 0.2577 | 0.7021 | 0.4607 | 0.1910 | `de31887` |
| `longeval-sci-2026/snapshot-1/train` | pooled | `fusion_full` | 100 | 84,489 | 100 | 0.2963 | 0.3859 | 0.2415 | 0.5988 | 0.4684 | 0.2020 | `de31887` |
| `longeval-sci-2026/snapshot-1/train` | pooled | `fusion_full` | 1000 | 84,489 | 100 | 0.2968 | 0.4221 | 0.2614 | 0.6996 | 0.4753 | 0.1930 | `de31887` |
| `longeval-sci-2026/snapshot-1/train` | pooled | `fusion_union_pool` | 100 | 84,489 | 100 | 0.3056 | 0.4129 | 0.2562 | 0.6511 | 0.4686 | 0.2020 | `de31887` |
| `longeval-sci-2026/snapshot-1/train` | pooled | `fusion_union_pool` | 1000 | 84,489 | 100 | 0.3001 | 0.4292 | 0.2665 | 0.7065 | 0.4645 | 0.2000 | `de31887` |
| `longeval-sci/2024-11` | full | `bm25_only` | — | 2,014,265 | 99 | 0.1841 | 0.3319 | 0.1949 | 0.6332 | 0.3239 | 0.1596 | `de31887` |
| `longeval-sci/2024-11` | pooled | `bm25_only` | — | 69,141 | 99 | 0.1869 | 0.3337 | 0.1985 | 0.6322 | 0.3277 | 0.1636 | `de31887` |
| `longeval-sci/2024-11` | pooled | `dense_only` | — | 69,141 | 99 | 0.0804 | 0.1675 | 0.0772 | 0.3518 | 0.2424 | 0.0717 | `de31887` |
| `longeval-sci/2024-11` | pooled | `fusion_dense_pool` | 100 | 69,141 | 99 | 0.1062 | 0.1842 | 0.0881 | 0.3449 | 0.2552 | 0.1020 | `de31887` |
| `longeval-sci/2024-11` | pooled | `fusion_dense_pool` | 1000 | 69,141 | 99 | 0.1298 | 0.2748 | 0.1273 | 0.5709 | 0.3017 | 0.1172 | `de31887` |
| `longeval-sci/2024-11` | pooled | `fusion_full` | 100 | 69,141 | 99 | 0.1098 | 0.1867 | 0.0903 | 0.3449 | 0.2617 | 0.1030 | `de31887` |
| `longeval-sci/2024-11` | pooled | `fusion_full` | 1000 | 69,141 | 99 | 0.1384 | 0.2828 | 0.1341 | 0.5680 | 0.3177 | 0.1192 | `de31887` |
| `longeval-sci/2024-11` | pooled | `fusion_union_pool` | 100 | 69,141 | 99 | 0.1350 | 0.2927 | 0.1315 | 0.6196 | 0.3121 | 0.1253 | `de31887` |
| `longeval-sci/2024-11` | pooled | `fusion_union_pool` | 1000 | 69,141 | 99 | 0.1410 | 0.3032 | 0.1413 | 0.6403 | 0.3169 | 0.1253 | `de31887` |
| `longeval-sci/2025-01` | full | `bm25_only` | — | 1,213,728 | 492 | 0.2362 | 0.3426 | 0.2181 | 0.5989 | 0.4054 | 0.1846 | `de31887` |
| `longeval-sci/2025-01` | pooled | `bm25_only` | — | 261,294 | 492 | 0.2486 | 0.3498 | 0.2280 | 0.5972 | 0.4199 | 0.1941 | `de31887` |
| `longeval-sci/2025-01` | pooled | `dense_only` | — | 261,294 | 492 | 0.0931 | 0.1660 | 0.0786 | 0.3348 | 0.1996 | 0.0736 | `de31887` |
| `longeval-sci/2025-01` | pooled | `fusion_dense_pool` | 100 | 261,294 | 492 | 0.1451 | 0.2010 | 0.1156 | 0.3294 | 0.2903 | 0.1118 | `de31887` |
| `longeval-sci/2025-01` | pooled | `fusion_dense_pool` | 1000 | 261,294 | 492 | 0.1656 | 0.2628 | 0.1463 | 0.4869 | 0.3221 | 0.1272 | `de31887` |
| `longeval-sci/2025-01` | pooled | `fusion_full` | 100 | 261,294 | 492 | 0.1506 | 0.2046 | 0.1187 | 0.3294 | 0.3002 | 0.1157 | `de31887` |
| `longeval-sci/2025-01` | pooled | `fusion_full` | 1000 | 261,294 | 492 | 0.1710 | 0.2678 | 0.1501 | 0.4915 | 0.3286 | 0.1315 | `de31887` |
| `longeval-sci/2025-01` | pooled | `fusion_union_pool` | 100 | 261,294 | 492 | 0.1819 | 0.3000 | 0.1635 | 0.5753 | 0.3442 | 0.1435 | `de31887` |
| `longeval-sci/2025-01` | pooled | `fusion_union_pool` | 1000 | 261,294 | 492 | 0.1840 | 0.3074 | 0.1695 | 0.5946 | 0.3424 | 0.1459 | `de31887` |
