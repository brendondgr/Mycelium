# Evaluation

How to run the harness, how to read what it produces, and what the numbers do and
do not license you to claim. The harness lives in [`eval/`](../eval/README.md);
re-running is one command:

```bash
uv run --project eval eval/run.py --config eval/configs/fusion_dense_pool.toml --collection sci-2026-train
```

> **The findings live in the research record.** These runs are recorded as
> [`EXP-2026-08-001`](research/experiments/EXP-2026-08-001-longeval-retrieval-baseline/RESULTS.md)
> (does the stack beat BM25?) and
> [`EXP-2026-08-002`](research/experiments/EXP-2026-08-002-dense-pool-vs-union-pool/RESULTS.md)
> (what does the dense-pool restriction cost?). Read those for the hypothesis,
> the interpretation, the threats to validity, and the figures. A new evaluation
> run needs a new experiment folder — see
> [`research/AGENT_INSTRUCTIONS.md`](research/AGENT_INSTRUCTIONS.md).

The leaderboard below is **generated** from `eval/results/*.json` by
`uv run --project eval eval/report.py`. It is the operator's view of every run on
record. Never edit it by hand — a number that has drifted from the run that
produced it is worse than no number.

## Leaderboard

<!-- BEGIN GENERATED LEADERBOARD -->

### `longeval-sci-2026/snapshot-1/train` — qrels `dctr`

| Arm | Corpus | Docs | Queries | nDCG@10 | nDCG@100 | AP | R@100 | RR | P@10 | Run |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `bm25_only` | full | 869,902 | 100 | 0.3282 | 0.4340 | 0.2796 | 0.6854 | 0.4843 | 0.2110 | `de31887` |
| `dense_only` | full | 869,902 | 100 | 0.2234 | 0.3162 | 0.1754 | 0.5456 | 0.3846 | 0.1590 | `5b66bc2` |
| `fusion_dense_pool` (pool 100) | full | 869,902 | 100 | 0.2852 | 0.3549 | 0.2190 | 0.5419 | 0.4505 | 0.1980 | `5b66bc2` |
| `fusion_full` (pool 100) | full | 869,902 | 100 | 0.2849 | 0.3563 | 0.2233 | 0.5419 | 0.4545 | 0.1960 | `5b66bc2` |
| `fusion_union_pool` (pool 100) | full | 869,902 | 100 | 0.2993 | 0.4031 | 0.2519 | 0.6299 | 0.4734 | 0.1960 | `5b66bc2` |
| `bm25_only` | pooled | 84,489 | 100 | 0.3212 | 0.4314 | 0.2760 | 0.6903 | 0.4788 | 0.2100 | `11d364e` ⚠️dirty |
| `bm25_only` | pooled | 84,489 | 100 | 0.3212 | 0.4314 | 0.2760 | 0.6903 | 0.4788 | 0.2100 | `917ec38` ⚠️dirty |
| `bm25_only` | pooled | 84,489 | 100 | 0.3212 | 0.4314 | 0.2760 | 0.6903 | 0.4788 | 0.2100 | `de31887` |
| `cascade_colbert_xenc` (pool 100) | pooled | 84,489 | 100 | 0.3248 | 0.4300 | 0.2682 | 0.6511 | 0.4980 | 0.2090 | `917ec38` ⚠️dirty |
| `colbert_rerank` (pool 500) | pooled | 84,489 | 100 | 0.2919 | 0.4275 | 0.2584 | 0.7121 | 0.4940 | 0.1940 | `917ec38` ⚠️dirty |
| `colbert_rerank` (pool 100) | pooled | 84,489 | 100 | 0.2903 | 0.4082 | 0.2483 | 0.6511 | 0.4876 | 0.1900 | `917ec38` ⚠️dirty |
| `colbert_rerank` (pool 500) | pooled | 84,489 | 100 | 0.2919 | 0.4275 | 0.2584 | 0.7121 | 0.4940 | 0.1940 | `917ec38` ⚠️dirty |
| `colbert_rerank` (pool 100) | pooled | 84,489 | 100 | 0.2951 | 0.4121 | 0.2517 | 0.6511 | 0.4847 | 0.1920 | `917ec38` ⚠️dirty |
| `dense_only` | pooled | 84,489 | 100 | 0.2401 | 0.3498 | 0.1965 | 0.6120 | 0.4067 | 0.1700 | `917ec38` ⚠️dirty |
| `dense_only` | pooled | 84,489 | 100 | 0.2401 | 0.3498 | 0.1965 | 0.6120 | 0.4067 | 0.1700 | `ac56cee` |
| `dense_only` | pooled | 84,489 | 100 | 0.2401 | 0.3498 | 0.1965 | 0.6120 | 0.4067 | 0.1700 | `de31887` |
| `fusion_bm25_dense_splade` (pool 100) | pooled | 84,489 | 100 | 0.3184 | 0.4356 | 0.2676 | 0.7141 | 0.4875 | 0.2140 | `917ec38` ⚠️dirty |
| `fusion_bm25_dense_splade` (pool 100) | pooled | 84,489 | 100 | 0.3184 | 0.4356 | 0.2676 | 0.7141 | 0.4875 | 0.2140 | `ac56cee` |
| `fusion_dense_pool` (pool 100) | pooled | 84,489 | 100 | 0.2937 | 0.3829 | 0.2360 | 0.5988 | 0.4589 | 0.2010 | `917ec38` ⚠️dirty |
| `fusion_dense_pool` (pool 100) | pooled | 84,489 | 100 | 0.2937 | 0.3829 | 0.2360 | 0.5988 | 0.4589 | 0.2010 | `ac56cee` |
| `fusion_dense_pool` (pool 100) | pooled | 84,489 | 100 | 0.2937 | 0.3829 | 0.2360 | 0.5988 | 0.4589 | 0.2010 | `de31887` |
| `fusion_dense_pool` (pool 1000) | pooled | 84,489 | 100 | 0.2915 | 0.4191 | 0.2577 | 0.7021 | 0.4607 | 0.1910 | `de31887` |
| `fusion_full` (pool 100) | pooled | 84,489 | 100 | 0.2963 | 0.3859 | 0.2415 | 0.5988 | 0.4684 | 0.2020 | `917ec38` ⚠️dirty |
| `fusion_full` (pool 100) | pooled | 84,489 | 100 | 0.2963 | 0.3859 | 0.2415 | 0.5988 | 0.4684 | 0.2020 | `de31887` |
| `fusion_full` (pool 1000) | pooled | 84,489 | 100 | 0.2968 | 0.4221 | 0.2614 | 0.6996 | 0.4753 | 0.1930 | `de31887` |
| `fusion_union_pool` (pool 500) | pooled | 84,489 | 100 | 0.3015 | 0.4313 | 0.2684 | 0.7098 | 0.4696 | 0.2000 | `917ec38` ⚠️dirty |
| `fusion_union_pool` (pool 1000) | pooled | 84,489 | 100 | 0.3001 | 0.4292 | 0.2665 | 0.7065 | 0.4645 | 0.2000 | `de31887` |
| `fusion_union_pool` (pool 100) | pooled | 84,489 | 100 | 0.3056 | 0.4129 | 0.2562 | 0.6511 | 0.4686 | 0.2020 | `11d364e` ⚠️dirty |
| `fusion_union_pool` (pool 100) | pooled | 84,489 | 100 | 0.3056 | 0.4129 | 0.2562 | 0.6511 | 0.4686 | 0.2020 | `16749f1` ⚠️dirty |
| `fusion_union_pool` (pool 100) | pooled | 84,489 | 100 | 0.3056 | 0.4129 | 0.2562 | 0.6511 | 0.4686 | 0.2020 | `917ec38` ⚠️dirty |
| `fusion_union_pool` (pool 100) | pooled | 84,489 | 100 | 0.3056 | 0.4129 | 0.2562 | 0.6511 | 0.4686 | 0.2020 | `de31887` |
| `llm_rerank` (pool 100) | pooled | 84,489 | 100 | 0.3177 | 0.4328 | 0.2676 | 0.6511 | 0.5306 | 0.1930 | `16749f1` ⚠️dirty |
| `llm_rerank` (pool 100) | pooled | 84,489 | 100 | 0.3133 | 0.4304 | 0.2640 | 0.6511 | 0.5320 | 0.1900 | `917ec38` ⚠️dirty |
| `llm_rerank_reversed` (pool 100) | pooled | 84,489 | 100 | 0.2561 | 0.3768 | 0.2119 | 0.6511 | 0.3909 | 0.1950 | `16749f1` ⚠️dirty |
| `llm_rerank_reversed` (pool 100) | pooled | 84,489 | 100 | 0.2563 | 0.3734 | 0.2066 | 0.6511 | 0.3837 | 0.1970 | `917ec38` ⚠️dirty |
| `llm_rubric` (pool 100) | pooled | 84,489 | 100 | 0.3095 | 0.4175 | 0.2607 | 0.6511 | 0.4786 | 0.2040 | `16749f1` ⚠️dirty |
| `llm_rubric` (pool 100) | pooled | 84,489 | 100 | 0.3099 | 0.4175 | 0.2606 | 0.6511 | 0.4794 | 0.2030 | `917ec38` ⚠️dirty |
| `splade_only` | pooled | 84,489 | 100 | 0.2617 | 0.3683 | 0.2177 | 0.6173 | 0.4058 | 0.1760 | `917ec38` ⚠️dirty |
| `xenc_rerank` (pool 500) | pooled | 84,489 | 100 | 0.3307 | 0.4504 | 0.2780 | 0.7199 | 0.4936 | 0.2150 | `917ec38` ⚠️dirty |
| `xenc_rerank` (pool 500) | pooled | 84,489 | 100 | 0.3267 | 0.4468 | 0.2782 | 0.7098 | 0.4898 | 0.2110 | `917ec38` ⚠️dirty |
| `xenc_rerank` (pool 100) | pooled | 84,489 | 100 | 0.3299 | 0.4330 | 0.2711 | 0.6511 | 0.5051 | 0.2110 | `11d364e` ⚠️dirty |
| `xenc_rerank` (pool 100) | pooled | 84,489 | 100 | 0.3299 | 0.4330 | 0.2711 | 0.6511 | 0.5051 | 0.2110 | `2e05dc8` ⚠️dirty |
| `xenc_rerank` (pool 100) | pooled | 84,489 | 100 | 0.3299 | 0.4330 | 0.2711 | 0.6511 | 0.5051 | 0.2110 | `917ec38` ⚠️dirty |
| `xenc_rerank` (pool 100) | pooled | 84,489 | 100 | 0.3299 | 0.4424 | 0.2792 | 0.6903 | 0.4913 | 0.2110 | `11d364e` ⚠️dirty |
| `xenc_rerank` (pool 100) | pooled | 84,489 | 100 | 0.3213 | 0.4398 | 0.2778 | 0.6903 | 0.4943 | 0.2040 | `11d364e` ⚠️dirty |
| `xenc_rerank` (pool 100) | pooled | 84,489 | 100 | 0.3305 | 0.4492 | 0.2780 | 0.7141 | 0.4948 | 0.2140 | `917ec38` ⚠️dirty |
| `xenc_rerank` (pool 100) | pooled | 84,489 | 100 | 0.3304 | 0.4320 | 0.2702 | 0.6511 | 0.4989 | 0.2130 | `11d364e` ⚠️dirty |
| `xenc_rerank` (pool 100) | pooled | 84,489 | 100 | 0.3304 | 0.4320 | 0.2702 | 0.6511 | 0.4989 | 0.2130 | `917ec38` ⚠️dirty |
| `xenc_rerank` (pool 500) | pooled | 84,489 | 100 | 0.3306 | 0.4503 | 0.2779 | 0.7199 | 0.4936 | 0.2150 | `917ec38` ⚠️dirty |
| `xenc_rerank` (pool 100) | pooled | 84,489 | 100 | 0.3304 | 0.4320 | 0.2702 | 0.6511 | 0.4989 | 0.2130 | `917ec38` ⚠️dirty |

### `longeval-sci-2026/snapshot-1/train` — qrels `dctr-union-profiles`

| Arm | Corpus | Docs | Queries | nDCG@10 | nDCG@100 | AP | R@100 | RR | P@10 | Run |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1810 | 0.2409 | 0.0972 | 0.2750 | 0.4384 | 0.2600 | `6ffbd37` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1544 | 0.1374 | 0.0414 | 0.1224 | 0.3854 | 0.2133 | `e356280` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1892 | 0.2426 | 0.0982 | 0.2738 | 0.4558 | 0.2633 | `6ffbd37` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1892 | 0.2426 | 0.0937 | 0.2738 | 0.4558 | 0.2633 | `e356280` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.2078 | 0.2492 | 0.0991 | 0.2738 | 0.6106 | 0.2633 | `f0dc7e5` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1896 | 0.1985 | 0.0735 | 0.2158 | 0.5202 | 0.2500 | `e356280` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1901 | 0.1969 | 0.0720 | 0.2158 | 0.4835 | 0.2500 | `f0dc7e5` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1673 | 0.1907 | 0.0729 | 0.2170 | 0.4744 | 0.2367 | `6ffbd37` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1351 | 0.2162 | 0.0822 | 0.2612 | 0.3509 | 0.1967 | `6ffbd37` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.2227 | 0.2034 | 0.0804 | 0.2116 | 0.5425 | 0.2833 | `6ffbd37` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1896 | 0.1985 | 0.0774 | 0.2158 | 0.5202 | 0.2500 | `6ffbd37` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1544 | 0.1374 | 0.0414 | 0.1224 | 0.3854 | 0.2133 | `e356280` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1896 | 0.1272 | 0.0381 | 0.1062 | 0.5202 | 0.2500 | `e356280` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1544 | 0.1435 | 0.0433 | 0.1316 | 0.3854 | 0.2133 | `e356280` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1544 | 0.2177 | 0.0800 | 0.2521 | 0.3854 | 0.2133 | `e356280` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1752 | 0.2257 | 0.0841 | 0.2521 | 0.5132 | 0.2133 | `f0dc7e5` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1892 | 0.1682 | 0.0568 | 0.1519 | 0.4558 | 0.2633 | `e356280` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1896 | 0.1187 | 0.0359 | 0.0950 | 0.5202 | 0.2500 | `e356280` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1544 | 0.2177 | 0.0841 | 0.2521 | 0.3854 | 0.2133 | `6ffbd37` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1892 | 0.1620 | 0.0536 | 0.1413 | 0.4558 | 0.2633 | `e356280` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1896 | 0.1187 | 0.0359 | 0.0950 | 0.5202 | 0.2500 | `e356280` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1633 | 0.2209 | 0.0854 | 0.2480 | 0.4236 | 0.2200 | `6ffbd37` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1942 | 0.2450 | 0.0988 | 0.2724 | 0.4781 | 0.2633 | `6ffbd37` ⚠️dirty |
| `clustered_profile` (pool 100) | full | 869,902 | 30 | 0.1892 | 0.1620 | 0.0536 | 0.1413 | 0.4558 | 0.2633 | `e356280` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1643 | 0.2093 | 0.0818 | 0.2343 | 0.4045 | 0.2167 | `6ffbd37` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.2262 | 0.1988 | 0.0783 | 0.2085 | 0.5308 | 0.2967 | `6ffbd37` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1997 | 0.1219 | 0.0371 | 0.0985 | 0.5196 | 0.2667 | `e356280` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1684 | 0.2098 | 0.0808 | 0.2303 | 0.4301 | 0.2200 | `6ffbd37` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1643 | 0.1396 | 0.0427 | 0.1230 | 0.4045 | 0.2167 | `e356280` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1643 | 0.2093 | 0.0818 | 0.2343 | 0.4045 | 0.2167 | `6ffbd37` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1442 | 0.2138 | 0.0813 | 0.2530 | 0.3681 | 0.1967 | `6ffbd37` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1643 | 0.2093 | 0.0773 | 0.2343 | 0.4045 | 0.2167 | `e356280` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1787 | 0.2141 | 0.0799 | 0.2343 | 0.5073 | 0.2167 | `f0dc7e5` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1684 | 0.2098 | 0.0808 | 0.2303 | 0.4301 | 0.2200 | `6ffbd37` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1997 | 0.1949 | 0.0767 | 0.2105 | 0.5196 | 0.2667 | `6ffbd37` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1643 | 0.1396 | 0.0427 | 0.1230 | 0.4045 | 0.2167 | `e356280` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1643 | 0.1396 | 0.0427 | 0.1230 | 0.4045 | 0.2167 | `e356280` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1643 | 0.1396 | 0.0427 | 0.1230 | 0.4045 | 0.2167 | `e356280` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1643 | 0.1463 | 0.0446 | 0.1331 | 0.4045 | 0.2167 | `e356280` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1442 | 0.2138 | 0.0813 | 0.2530 | 0.3681 | 0.1967 | `6ffbd37` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1741 | 0.1864 | 0.0722 | 0.2090 | 0.4723 | 0.2500 | `6ffbd37` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1997 | 0.1310 | 0.0393 | 0.1096 | 0.5196 | 0.2667 | `e356280` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1643 | 0.2093 | 0.0773 | 0.2343 | 0.4045 | 0.2167 | `e356280` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1787 | 0.2141 | 0.0799 | 0.2343 | 0.5073 | 0.2167 | `f0dc7e5` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1643 | 0.1463 | 0.0446 | 0.1331 | 0.4045 | 0.2167 | `e356280` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1997 | 0.1219 | 0.0371 | 0.0985 | 0.5196 | 0.2667 | `e356280` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.1997 | 0.1949 | 0.0724 | 0.2105 | 0.5196 | 0.2667 | `e356280` ⚠️dirty |
| `flat_profile` (pool 100) | full | 869,902 | 30 | 0.2030 | 0.1942 | 0.0709 | 0.2105 | 0.5024 | 0.2667 | `f0dc7e5` ⚠️dirty |
| `slate_profile` (pool 100) | full | 869,902 | 30 | 0.1896 | 0.1287 | 0.0382 | 0.1077 | 0.5202 | 0.2500 | `e356280` ⚠️dirty |
| `slate_profile` (pool 100) | full | 869,902 | 30 | 0.1544 | 0.2177 | 0.0800 | 0.2521 | 0.3854 | 0.2133 | `e356280` ⚠️dirty |
| `slate_profile` (pool 100) | full | 869,902 | 30 | 0.1896 | 0.1985 | 0.0735 | 0.2158 | 0.5202 | 0.2500 | `e356280` ⚠️dirty |
| `slate_profile` (pool 100) | full | 869,902 | 30 | 0.1892 | 0.1699 | 0.0553 | 0.1518 | 0.4558 | 0.2633 | `e356280` ⚠️dirty |
| `slate_profile` (pool 100) | full | 869,902 | 30 | 0.1544 | 0.1418 | 0.0425 | 0.1289 | 0.3854 | 0.2133 | `e356280` ⚠️dirty |
| `slate_profile` (pool 100) | full | 869,902 | 30 | 0.1892 | 0.1699 | 0.0553 | 0.1518 | 0.4558 | 0.2633 | `e356280` ⚠️dirty |
| `slate_profile` (pool 100) | full | 869,902 | 30 | 0.1544 | 0.1418 | 0.0425 | 0.1289 | 0.3854 | 0.2133 | `e356280` ⚠️dirty |
| `slate_profile` (pool 100) | full | 869,902 | 30 | 0.1896 | 0.1287 | 0.0382 | 0.1077 | 0.5202 | 0.2500 | `e356280` ⚠️dirty |
| `slate_profile` (pool 100) | full | 869,902 | 30 | 0.1892 | 0.2426 | 0.0937 | 0.2738 | 0.4558 | 0.2633 | `e356280` ⚠️dirty |
| `spread_all` (pool 100) | full | 869,902 | 30 | 0.1834 | 0.1921 | 0.0704 | 0.2116 | 0.4013 | 0.2433 | `f0dc7e5` ⚠️dirty |
| `spread_all` (pool 100) | full | 869,902 | 30 | 0.1536 | 0.2097 | 0.0780 | 0.2387 | 0.4086 | 0.2100 | `f0dc7e5` ⚠️dirty |
| `spread_all` (pool 100) | full | 869,902 | 30 | 0.1885 | 0.2361 | 0.0905 | 0.2619 | 0.4881 | 0.2500 | `f0dc7e5` ⚠️dirty |
| `spread_cap` (pool 100) | full | 869,902 | 30 | 0.2045 | 0.2469 | 0.0964 | 0.2709 | 0.6039 | 0.2633 | `f0dc7e5` ⚠️dirty |
| `spread_cap` (pool 100) | full | 869,902 | 30 | 0.1675 | 0.2178 | 0.0801 | 0.2470 | 0.5068 | 0.2100 | `f0dc7e5` ⚠️dirty |
| `spread_cap` (pool 100) | full | 869,902 | 30 | 0.1987 | 0.2000 | 0.0737 | 0.2189 | 0.4946 | 0.2600 | `f0dc7e5` ⚠️dirty |
| `spread_floor` (pool 100) | full | 869,902 | 30 | 0.2078 | 0.2492 | 0.0991 | 0.2738 | 0.6106 | 0.2633 | `f0dc7e5` ⚠️dirty |
| `spread_floor` (pool 100) | full | 869,902 | 30 | 0.1901 | 0.1969 | 0.0720 | 0.2158 | 0.4835 | 0.2500 | `f0dc7e5` ⚠️dirty |
| `spread_floor` (pool 100) | full | 869,902 | 30 | 0.1752 | 0.2257 | 0.0841 | 0.2521 | 0.5132 | 0.2133 | `f0dc7e5` ⚠️dirty |
| `spread_floor_interleave` (pool 100) | full | 869,902 | 30 | 0.1885 | 0.2361 | 0.0905 | 0.2619 | 0.4881 | 0.2500 | `f0dc7e5` ⚠️dirty |
| `spread_floor_interleave` (pool 100) | full | 869,902 | 30 | 0.1536 | 0.2097 | 0.0780 | 0.2387 | 0.4086 | 0.2100 | `f0dc7e5` ⚠️dirty |
| `spread_floor_interleave` (pool 100) | full | 869,902 | 30 | 0.1834 | 0.1921 | 0.0704 | 0.2116 | 0.4013 | 0.2433 | `f0dc7e5` ⚠️dirty |
| `spread_identity` (pool 100) | full | 869,902 | 30 | 0.1901 | 0.1969 | 0.0720 | 0.2158 | 0.4835 | 0.2500 | `f0dc7e5` ⚠️dirty |
| `spread_identity` (pool 100) | full | 869,902 | 30 | 0.1752 | 0.2257 | 0.0841 | 0.2521 | 0.5132 | 0.2133 | `f0dc7e5` ⚠️dirty |
| `spread_identity` (pool 100) | full | 869,902 | 30 | 0.2078 | 0.2492 | 0.0991 | 0.2738 | 0.6106 | 0.2633 | `f0dc7e5` ⚠️dirty |
| `spread_interleave` (pool 100) | full | 869,902 | 30 | 0.1834 | 0.1921 | 0.0704 | 0.2116 | 0.4013 | 0.2433 | `f0dc7e5` ⚠️dirty |
| `spread_interleave` (pool 100) | full | 869,902 | 30 | 0.1885 | 0.2361 | 0.0905 | 0.2619 | 0.4881 | 0.2500 | `f0dc7e5` ⚠️dirty |
| `spread_interleave` (pool 100) | full | 869,902 | 30 | 0.1536 | 0.2097 | 0.0780 | 0.2387 | 0.4086 | 0.2100 | `f0dc7e5` ⚠️dirty |
| `spread_mmr` (pool 100) | full | 869,902 | 30 | 0.1706 | 0.2191 | 0.0819 | 0.2443 | 0.5017 | 0.2133 | `f0dc7e5` ⚠️dirty |
| `spread_mmr` (pool 100) | full | 869,902 | 30 | 0.2056 | 0.2456 | 0.0964 | 0.2679 | 0.6020 | 0.2633 | `f0dc7e5` ⚠️dirty |
| `spread_mmr` (pool 100) | full | 869,902 | 30 | 0.1956 | 0.1946 | 0.0712 | 0.2146 | 0.4833 | 0.2600 | `f0dc7e5` ⚠️dirty |
| `spread_quota` (pool 100) | full | 869,902 | 30 | 0.1834 | 0.1921 | 0.0697 | 0.2116 | 0.4013 | 0.2433 | `f0dc7e5` ⚠️dirty |
| `spread_quota` (pool 100) | full | 869,902 | 30 | 0.1885 | 0.2361 | 0.0906 | 0.2619 | 0.4881 | 0.2500 | `f0dc7e5` ⚠️dirty |
| `spread_quota` (pool 100) | full | 869,902 | 30 | 0.1536 | 0.2097 | 0.0778 | 0.2387 | 0.4086 | 0.2100 | `f0dc7e5` ⚠️dirty |
| `spread_rankmerge` (pool 100) | full | 869,902 | 30 | 0.1713 | 0.2180 | 0.0810 | 0.2395 | 0.5272 | 0.2133 | `f0dc7e5` ⚠️dirty |
| `spread_rankmerge` (pool 100) | full | 869,902 | 30 | 0.1941 | 0.1936 | 0.0710 | 0.2120 | 0.4815 | 0.2500 | `f0dc7e5` ⚠️dirty |
| `spread_rankmerge` (pool 100) | full | 869,902 | 30 | 0.2066 | 0.2429 | 0.0940 | 0.2615 | 0.6037 | 0.2600 | `f0dc7e5` ⚠️dirty |
| `spread_rankmerge_cap` (pool 100) | full | 869,902 | 30 | 0.1941 | 0.1936 | 0.0710 | 0.2120 | 0.4815 | 0.2500 | `f0dc7e5` ⚠️dirty |
| `spread_rankmerge_cap` (pool 100) | full | 869,902 | 30 | 0.2066 | 0.2429 | 0.0940 | 0.2615 | 0.6037 | 0.2600 | `f0dc7e5` ⚠️dirty |
| `spread_rankmerge_cap` (pool 100) | full | 869,902 | 30 | 0.1713 | 0.2180 | 0.0810 | 0.2395 | 0.5272 | 0.2133 | `f0dc7e5` ⚠️dirty |
| `spread_rankmerge_interleave` (pool 100) | full | 869,902 | 30 | 0.1536 | 0.2097 | 0.0780 | 0.2387 | 0.4086 | 0.2100 | `f0dc7e5` ⚠️dirty |
| `spread_rankmerge_interleave` (pool 100) | full | 869,902 | 30 | 0.1834 | 0.1921 | 0.0704 | 0.2116 | 0.4013 | 0.2433 | `f0dc7e5` ⚠️dirty |
| `spread_rankmerge_interleave` (pool 100) | full | 869,902 | 30 | 0.1885 | 0.2361 | 0.0905 | 0.2619 | 0.4881 | 0.2500 | `f0dc7e5` ⚠️dirty |
| `spread_rankmerge_mmr` (pool 100) | full | 869,902 | 30 | 0.2065 | 0.2430 | 0.0941 | 0.2615 | 0.6037 | 0.2600 | `f0dc7e5` ⚠️dirty |
| `spread_rankmerge_mmr` (pool 100) | full | 869,902 | 30 | 0.1941 | 0.1936 | 0.0710 | 0.2120 | 0.4815 | 0.2500 | `f0dc7e5` ⚠️dirty |
| `spread_rankmerge_mmr` (pool 100) | full | 869,902 | 30 | 0.1713 | 0.2180 | 0.0810 | 0.2395 | 0.5272 | 0.2133 | `f0dc7e5` ⚠️dirty |
| `spread_rankmerge_quota` (pool 100) | full | 869,902 | 30 | 0.1536 | 0.2097 | 0.0778 | 0.2387 | 0.4086 | 0.2100 | `f0dc7e5` ⚠️dirty |
| `spread_rankmerge_quota` (pool 100) | full | 869,902 | 30 | 0.1834 | 0.1921 | 0.0697 | 0.2116 | 0.4013 | 0.2433 | `f0dc7e5` ⚠️dirty |
| `spread_rankmerge_quota` (pool 100) | full | 869,902 | 30 | 0.1885 | 0.2361 | 0.0906 | 0.2619 | 0.4881 | 0.2500 | `f0dc7e5` ⚠️dirty |

### `longeval-sci/2024-11` — qrels `test`

| Arm | Corpus | Docs | Queries | nDCG@10 | nDCG@100 | AP | R@100 | RR | P@10 | Run |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `bm25_only` | full | 2,014,265 | 99 | 0.1841 | 0.3319 | 0.1949 | 0.6332 | 0.3239 | 0.1596 | `de31887` |
| `bm25_only` | pooled | 69,141 | 99 | 0.1869 | 0.3337 | 0.1985 | 0.6322 | 0.3277 | 0.1636 | `de31887` |
| `dense_only` | pooled | 69,141 | 99 | 0.0804 | 0.1675 | 0.0772 | 0.3518 | 0.2424 | 0.0717 | `de31887` |
| `fusion_dense_pool` (pool 100) | pooled | 69,141 | 99 | 0.1062 | 0.1842 | 0.0881 | 0.3449 | 0.2552 | 0.1020 | `de31887` |
| `fusion_dense_pool` (pool 1000) | pooled | 69,141 | 99 | 0.1298 | 0.2748 | 0.1273 | 0.5709 | 0.3017 | 0.1172 | `de31887` |
| `fusion_full` (pool 100) | pooled | 69,141 | 99 | 0.1098 | 0.1867 | 0.0903 | 0.3449 | 0.2617 | 0.1030 | `de31887` |
| `fusion_full` (pool 1000) | pooled | 69,141 | 99 | 0.1384 | 0.2828 | 0.1341 | 0.5680 | 0.3177 | 0.1192 | `de31887` |
| `fusion_union_pool` (pool 1000) | pooled | 69,141 | 99 | 0.1410 | 0.3032 | 0.1413 | 0.6403 | 0.3169 | 0.1253 | `de31887` |
| `fusion_union_pool` (pool 100) | pooled | 69,141 | 99 | 0.1350 | 0.2927 | 0.1315 | 0.6196 | 0.3121 | 0.1253 | `de31887` |

### `longeval-sci/2025-01` — qrels `test`

| Arm | Corpus | Docs | Queries | nDCG@10 | nDCG@100 | AP | R@100 | RR | P@10 | Run |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `bm25_only` | full | 1,213,728 | 492 | 0.2362 | 0.3426 | 0.2181 | 0.5989 | 0.4054 | 0.1846 | `de31887` |
| `bm25_only` | pooled | 261,294 | 492 | 0.2486 | 0.3498 | 0.2280 | 0.5972 | 0.4199 | 0.1941 | `11d364e` ⚠️dirty |
| `bm25_only` | pooled | 261,294 | 492 | 0.2486 | 0.3498 | 0.2280 | 0.5972 | 0.4199 | 0.1941 | `de31887` |
| `dense_only` | pooled | 261,294 | 492 | 0.0931 | 0.1660 | 0.0786 | 0.3348 | 0.1996 | 0.0736 | `62d7a1d` |
| `dense_only` | pooled | 261,294 | 492 | 0.0931 | 0.1660 | 0.0786 | 0.3348 | 0.1996 | 0.0736 | `de31887` |
| `fusion_bm25_dense_splade` (pool 100) | pooled | 261,294 | 492 | 0.1966 | 0.3187 | 0.1763 | 0.6083 | 0.3729 | 0.1537 | `ef5569e` |
| `fusion_dense_pool` (pool 100) | pooled | 261,294 | 492 | 0.1451 | 0.2010 | 0.1156 | 0.3294 | 0.2903 | 0.1118 | `62d7a1d` |
| `fusion_dense_pool` (pool 100) | pooled | 261,294 | 492 | 0.1451 | 0.2010 | 0.1156 | 0.3294 | 0.2903 | 0.1118 | `de31887` |
| `fusion_dense_pool` (pool 1000) | pooled | 261,294 | 492 | 0.1656 | 0.2628 | 0.1463 | 0.4869 | 0.3221 | 0.1272 | `de31887` |
| `fusion_full` (pool 100) | pooled | 261,294 | 492 | 0.1506 | 0.2046 | 0.1187 | 0.3294 | 0.3002 | 0.1157 | `de31887` |
| `fusion_full` (pool 1000) | pooled | 261,294 | 492 | 0.1710 | 0.2678 | 0.1501 | 0.4915 | 0.3286 | 0.1315 | `de31887` |
| `fusion_union_pool` (pool 1000) | pooled | 261,294 | 492 | 0.1840 | 0.3074 | 0.1695 | 0.5946 | 0.3424 | 0.1459 | `de31887` |
| `fusion_union_pool` (pool 100) | pooled | 261,294 | 492 | 0.1819 | 0.3000 | 0.1635 | 0.5753 | 0.3442 | 0.1435 | `62d7a1d` |
| `fusion_union_pool` (pool 100) | pooled | 261,294 | 492 | 0.1819 | 0.3000 | 0.1635 | 0.5753 | 0.3442 | 0.1435 | `de31887` |
| `xenc_rerank` (pool 100) | pooled | 261,294 | 492 | 0.1611 | 0.2963 | 0.1530 | 0.5972 | 0.3017 | 0.1289 | `500c261` ⚠️dirty |
| `xenc_rerank` (pool 100) | pooled | 261,294 | 492 | 0.1944 | 0.3138 | 0.1769 | 0.5972 | 0.3663 | 0.1537 | `11d364e` ⚠️dirty |
| `xenc_rerank` (pool 100) | pooled | 261,294 | 492 | 0.2047 | 0.3224 | 0.1868 | 0.5972 | 0.3762 | 0.1626 | `11d364e` ⚠️dirty |
| `xenc_rerank` (pool 100) | pooled | 261,294 | 492 | 0.1564 | 0.2931 | 0.1495 | 0.5972 | 0.3007 | 0.1254 | `500c261` ⚠️dirty |
| `xenc_rerank` (pool 100) | pooled | 261,294 | 492 | 0.1696 | 0.3003 | 0.1591 | 0.5972 | 0.3103 | 0.1352 | `500c261` ⚠️dirty |
| `xenc_rerank` (pool 100) | pooled | 261,294 | 492 | 0.1547 | 0.2902 | 0.1454 | 0.5972 | 0.2802 | 0.1254 | `500c261` ⚠️dirty |

### Published baselines (external, for comparison)

Scored by this harness with the same `ir_measures` call used above, from the LongEval'26 organizers' own published runs — not numbers quoted from a paper.

| System | Snapshot | qrels | nDCG@10 | nDCG@100 | AP | R@100 | RR | P@10 |
|---|---|---|---:|---:|---:|---:|---:|---:|
| BM25 (PyTerrier, organizers) | `longeval-sci-2026/snapshot-1/train` | dctr | 0.2922 | 0.4123 | 0.2573 | 0.6836 | 0.4717 | 0.1950 |
| Qwen3-Embedding-4B (organizers) | `longeval-sci-2026/snapshot-1/train` | dctr | 0.2820 | 0.3919 | 0.2378 | 0.6390 | 0.4389 | 0.1880 |

> **Do not compare across corpus scopes.** A `pooled` row is a re-ranking result over the judged set plus a lexical pool; a `full` row ranks the entire snapshot. Reordering metrics (nDCG@10) are broadly comparable, recall metrics are not.

<!-- END GENERATED LEADERBOARD -->

## How to read these numbers

**The collection.** LongEval-Sci (CLEF). Documents are paper titles + abstracts;
queries are short keyword topics. `sci-2026-train` is the 2026 training snapshot
(869,902 documents, 100 queries); `sci-2025-11` and `sci-2025-01` are the released
2025 test snapshots and form the temporal-persistence pair.

**The qrels.** Recorded on every row, and it matters: LongEval-Sci ships
click-model–derived pseudo-relevance judgments (`dctr`), not TREC-grade human
assessment. Report the qrel provenance next to every number, and size your
confidence to it.

**Corpus scope.** `full` ranks the entire snapshot. `pooled` ranks the union of
the judged documents with a deep corpus-wide BM25 pool — a standard, defensible
reduction, but a **re-ranking** evaluation. Recall numbers from a pooled run do
not transfer to the full corpus, and the two scopes must never be compared.

**Dirty runs.** A ⚠️ means the working tree had uncommitted changes, so the
number is not reproducible from the recorded SHA. Treat it as indicative only.

## Temporal persistence, and what is currently blocked

Persistence — whether effectiveness decays as a corpus grows — is the reason for
choosing LongEval over a static collection, and it is the question most specific
to Mycelium: the production corpus grows daily and nobody has ever checked
whether relevance degrades as it does.

**What the 2025 pair shows.** Across `2024-11` → `2025-01`, full-corpus BM25 goes
from nDCG@10 0.1841 to 0.2362 and R@100 0.6332 to 0.5989: effectiveness did not
decay. Read that cautiously — the two snapshots use *different topic sets* (99 vs
492 queries) over differently sized corpora, so the comparison confounds elapsed
time with topic difficulty. It is evidence against catastrophic decay, not a
controlled measurement of persistence. A clean persistence result needs the same
topics re-judged on a later corpus, which is exactly what the withheld 2026 test
snapshots provide.

The 2025 pair (`sci-2025-11` → `sci-2025-01`) answers it today. The three 2026
*test* snapshots cannot: CLEF 2026 is an active shared task and the organizers
withhold those qrels until it closes. This is a **temporary data-availability
block, not a design limitation** — `eval/collections.toml` already declares the
snapshots, and enabling them is a config edit (flip `scoreable`, name the qrels
variants), never a code change. Run files for them can already be produced for a
TIRA submission; only scoring is unavailable.

## What this does and does not license you to claim

Keep this section next to the numbers. The temptation to overclaim from a first
number is exactly how the "multi-agent" overstatement happened in the first
place (see the `CORRECTED` entry `20260804-briefing-framing`).

**You may claim:**

- Whether this repository's BM25 implementation is correct, by comparison with a
  published BM25 baseline on the same snapshot and qrels.
- Whether RRF fusion over a dense-retrieved pool beats BM25 alone, and by how
  much, on an external collection.
- What the dense-pool restriction costs relative to a true union pool — the
  `fusion_dense_pool` vs `fusion_union_pool` gap. This is the audit's sharpest
  structural criticism turned into a measured number: today BM25 indexes only
  what dense retrieval already found, so the lexical channel can never *add* a
  document, only reorder one. Measured at matched pool width, the union pool
  raises R@100 by **8.7%** on the 2026 snapshot and by **75-80%** on the two 2025
  snapshots. The cost scales with how weak the dense channel is on that corpus,
  which makes it a risk that grows silently as a corpus drifts away from what the
  embedding model handles well.
- That on this collection **BM25 alone outranks every fusion arm** on nDCG@10,
  and that the organizers' 4B-parameter dense baseline also loses to BM25. That
  is a property of short keyword queries over titles+abstracts, not solely of the
  384-dimension model in use — so it is evidence about the task shape, not just a
  reason to swap embedders.
- That **no reranker tried here beats BM25** — and that this was checked with
  paired confidence intervals rather than point estimates. `EXP-2026-08-008` briefly
  reported a cross-encoder as the first stage to clear that bar (+0.0095 nDCG@10);
  `EXP-2026-08-009` computed the interval and **refuted C-013**. On
  `sci-2026-train` no contrast excludes zero (the headline gain has sign p = 0.91);
  on `sci-2025-01`'s 492 queries the cross-encoder is significantly *worse*
  (−0.0439 and −0.0541, both intervals excluding zero), losing on 218 of 492
  queries, with the harm concentrated on **short keyword queries** and vanishing
  at 5+ words.
- That **query expansion does not rescue the reranker, and makes it worse in
  proportion to how much you expand** (C-017, refuted). Handing the cross-encoder
  ~8/16/20/40 words of LLM prose describing the query, while BM25 keeps the
  original short string, moves Δ vs BM25 from −0.0439 to −0.0939 monotonically —
  and pushes the 5+ word queries, the only ones previously unharmed, from +0.0016
  to −0.0552. Query length was a correlate, not a cause.
- That the failure is **not** the English-only reranker meeting a multilingual
  corpus either: harm is largest where the candidate set is entirely Latin-script
  (−0.0493) and smallest where non-Latin documents dominate (−0.0361).
- That **widening the retrieval pool is the one intervention that pays, and
  re-sorting it is not** — now with paired intervals **on two snapshots under two
  judgment regimes** (`EXP-2026-08-011`, `EXP-2026-08-012`). The union pool beats
  production's dense-restricted pool by +0.0523 R@100 on 2026 and **+0.2459
  `[+0.2196, +0.2717]` (302 queries better, 21 worse)** on `sci-2025-01`; adding
  SPLADE beats that by +0.0630 and +0.0330 respectively. On the human-judged
  snapshot both also move nDCG@10 with intervals excluding zero.
- That the **magnitude of C-008 is corpus-dependent and must never be quoted as a
  single number**: it is 5× larger where the dense channel is weaker, which is
  what the claim says and why the direction — not the size — is the finding.
- **NOT** that any configuration beats BM25. A statement in `EXP-2026-08-011` that
  the three-channel pool did (+0.0238 R@100) **failed to replicate** — on
  `sci-2025-01` that contrast spans zero, and the three-channel pool is
  significantly *worse* than BM25 on ranking there (−0.0519 nDCG@10). The
  pool-construction ordering is robust; the fusion family beating BM25 is not.
- That **two-channel fusion retrieves less than BM25 alone** (C-018, exploratory):
  −0.0392 R@100 `[−0.0711, −0.0100]`. The dense channel displaces documents BM25
  would have found; only the third channel reverses it.
- That **this collection cannot resolve a difference smaller than roughly ±0.04
  nDCG@10 at n = 100.** That is wider than most differences this project has
  discussed, and it is the reason every future contrast here ships with an
  interval (`EXP-2026-08-009` §4).
- That **SPLADE is a poor retriever on this collection and a good recall
  contributor to a fusion over it** (C-014, `supported` with a paired interval:
  +0.0630 R@100 `[+0.0396, +0.0923]`, 39 queries better to 3 worse) — alone it loses to BM25 (0.2617 vs 0.3212),
  but as a third RRF channel it gives the highest recall on the ladder
  (R@100 0.7141 vs 0.6903). Those are two different claims; C-014 is only the
  second (`EXP-2026-08-008`).
- That **late-interaction reranking as implemented here makes the ranking worse**
  — C-012 refuted at every depth and on both pool widths, and it degrades a
  cross-encoder placed after it. The implementation was never checked against a
  published ColBERT number, so the refutation is of this implementation, not of
  late interaction as such (Q-017).
- That **an LLM reranker adds no ranking signal here, and is unstable.**
  Reversing the candidate order with the set held identical costs 0.0570 nDCG@10
  (−18.2%) and lands below the ranking the model was asked to improve; only 72%
  of the top ten survives that reordering; the per-query record against the base
  is 29 better / 31 worse / 40 tied; and re-running at temperature 0 moves the
  arm as much as its whole apparent gain (C-015). The mechanism is *not*
  order-copying — that reading was tested and refuted.
- That **the model's pointwise relevance verdict does not discriminate relevance**
  (C-016, refuted): 1.99 distinct values used across 20 candidates, and grade 2
  scoring *below* grade 1. This is the first direct evidence against C-004's
  calibration half — the deployed percent-match — though it was measured on a 0-3
  scale where production uses 0-100 (Q-020).
- That **on the production corpus itself, the dense-restricted pool leaves a lot
  unreached** (C-020, `EXP-2026-08-013`). This is the one measurement in the
  record taken on Mycelium's own store, against the real declared interests of
  the real targets, through the deployed functions. A median **0.610** of the
  corpus-wide BM25 top-100 is already inside the dense pool across the deployed
  regimes — so ~40% is not — and it falls with corpus scope: 0.81 on a
  303-document gather day, 0.49 over the whole 35,205-paper store, and **0.44 on
  the deployed opportunity feeds**, which are corpus-scoped and are the worst
  regime measured. The pre-registered "inert" threshold (≥ 0.90) was not
  approached anywhere.
- That **the pool fix alone cannot change the deployed feed at all** (C-019,
  `EXP-2026-08-013`) — and this is the one finding here that is about shipped
  behaviour rather than a candidate. `fuse_interests_pool` surfaces a candidate
  only when `best_cosine[id] >= match_threshold`, and `_build_pool` populates
  `best_cosine` solely from the dense channel, so a lexically-retrieved candidate
  is compared at `0.0`. Across 126 (regime, target) pairs and four union arms,
  **union-only documents reaching the surfaced feed: 0**. Complete the gate over
  the whole pool and 7,440 surface. **C-008's fix is two edits; the pool edit on
  its own is a no-op.**
- That **`PAPER_MATCH_THRESHOLD`, not `PAPER_MATCH_MAX_SURFACE` and not the 0.15
  interest floor, is the cut that binds in production** (`EXP-2026-08-013`,
  answering `Q-012` and `Q-018`). The 250 backstop fires in 1 of 102 deployed
  paper pairs; 61% of a target's pool survives one interest's floor, against ≈37%
  on LongEval.
- That **real declared interests are short** — median 3 words, **95% at four or
  fewer** (`EXP-2026-08-013`). That is inside both LongEval query sets' ranges,
  and it is inside the band where the cross-encoder was measured harmful, which
  is why C-013's refutation now rests on production-shaped queries and not only
  on an external collection.
- Whether effectiveness persists across the 2025 snapshot pair.
- That **cluster-scoped max-pooling does not do what it was built to do** — on
  synthetic multi-cluster profiles over this collection. `EXP-2026-08-003`
  refuted C-003: in the condition the claim names (one theme's vocabulary far
  closer to the corpus than the others'), cluster-scoping *lowers* the
  worst-served theme's recall, and the per-cluster evenness measure worsens in
  every cell. Scope it precisely — the profiles are synthesised from LongEval
  queries, so this refutes the **mechanism** under controlled conditions and
  says nothing about whether real declared clusters behave the same way (Q-009).
  Scope it precisely in a second way too: `EXP-2026-08-003`'s arms ran
  `cluster_top_n = 0`, the global max-pooled ranking **an individual's feed**
  uses. `EXP-2026-08-004` then tested the lab feed's per-theme slate
  (`fusion.top_per_cluster`), and it does not restore the claim either — see the
  next bullet.
- That the lab feed's **per-theme slate is inert at the deployed surfacing
  settings**, on this collection. `EXP-2026-08-004`: with
  `PAPER_MATCH_MAX_SURFACE = 250` over a ~575-candidate pool, the slate and the
  plain cluster path emit **identical surfaced sets for 100% of synthetic
  profiles** — every theme's top ten is already inside the cut. Where the cut is
  forced to bind, the slate's theme-coverage gain halves and its interval opens
  across zero once the cluster path is given the same number of slots. Read that
  as "not demonstrated at n = 30", not as "disproved" (Q-011), and note it is a
  finding about the **configuration**, which should not drive a settings change
  without Q-009 evidence on real declared profiles.
- That whatever retrieval gain cluster-scoping produces belongs to the **max
  operator, not to cluster semantics**: the `random`-grouping negative control
  showed the largest clustered gains of any mode. That is a statement about the
  aggregation operator, and it is the only positive reading the control permits.
- That **adding a theme-spread mechanism does not rescue the cluster path**, on
  this collection. `EXP-2026-08-005` measured six of them — equal round-robin,
  proportional quota, a per-theme share cap, an MMR-style saturation penalty, a
  rank-based cross-cluster merge, and a per-theme admission floor — alone and
  combined, at deployed surfacing. Four beat the cluster baseline on the
  worst-served theme with intervals excluding zero, and this time the `random`
  control is null for every one, so the gain **is** theme-attributable. But **no
  mechanism beats the flat, no-cluster arm** (best +0.0015, CI `[−0.0011,
  +0.0043]`), round-robin is significantly worse than flat on nDCG@10, and under
  the realistic `coherent` grouping nothing helps at all. C-011 is refuted. Two
  narrower facts worth carrying: combinations add nothing because the score fix
  and the selection fixes act on disjoint inputs, and the per-theme admission
  floor is **exactly** inert at deployed surfacing for the same reason the slate
  is. Every mechanism is measured at one untuned parameter value, and at n = 30
  (Q-013, Q-014).

**You may not claim:**

- That this validates Mycelium's actual task. LongEval evaluates
  **query → documents**. Mycelium does **declared-interest profile → feed**, and
  no measurement anywhere in this record scores that task, because the production
  corpus has no relevance judgments (W5). What *has* changed is the size of the
  gap: `EXP-2026-08-013` measured both halves of the assumed mismatch and found
  them small. A real declared interest is 3 words at the median — inside
  LongEval's own range, not a different query shape — and production papers run
  239 tokens against LongEval's 161–185, with grants (116) and conferences (86)
  *shorter*. So the granularity mismatch between a three-word interest and a
  200-word abstract is **the same mismatch LongEval already contains**. What
  genuinely remains untested is fusing several interests into one ranked list and
  judging the result.
- Anything about the LLM percent-match, fellowship eligibility, or member
  routing (audit claims C4–C6). None are exercised. `EXP-2026-08-008`'s LLM arms
  are the nearest thing, and they measure a **counterfactual**: production does
  not reorder — `tools.recommendation.suggest` annotates a fused ordering — so those arms
  describe a design option, not shipped behaviour. They also ran at temperature 0
  while production defaults to 0.2 (audit item W1, open).
- That the **shipped** cross-encoder rerank stage improves anything. It is in
  `tools/recommendation/reranking.py`, it ships **off** (`RERANK_ENABLED=false`), and the
  only evidence for it is a **preference from one reader** over two queries
  (`EXP-2026-08-015`…`-017`). On this collection the same model is significantly
  *harmful* on short queries and C-013 stands refuted. What `EXP-2026-08-018`
  establishes is narrower and is the only thing it establishes: with the flag off,
  the pipeline is byte-identical to before the stage existed. Whether turning it on
  helps is `Q-033`, and it is unmeasured.
- That any *other* ladder stage should ship. SPLADE, ColBERT, the cross-encoder and the
  LLM rerankers live in `eval/harness/{ladder,llm_rerank}.py` and are **candidate
  code that is not in production**. A number from `harness/arms.py` describes
  Mycelium; a number from those two modules describes something Mycelium could
  become. Nothing in `apps.content` changed.
- That the cluster result transfers to the product. `EXP-2026-08-003` measures
  synthetic profiles built from keyword queries. A researcher's declared clusters
  are neither keyword queries nor greedy embedding pairs, and the union-of-qrels
  construction is blind to a document relevant only to a *combination* of
  interests — which is the case multi-interest scoring exists to reward.
- Anything about **effectiveness** on grants, fellowships, or conferences.
  LongEval is papers only. `EXP-2026-08-013` measures *reachability* on those
  three corpora — and finds them the worst-served regime in the store, 0.42–0.61
  — but reachability is not relevance, and no judgment of any kind exists for
  them.
- Certainty proportional to the qrels. These are click-derived pseudo-relevance
  judgments, not human assessment.

The honest framing: **this measures whether the foundation is sound, not whether
the idea is right.** That is worth the effort, because everything downstream
silently inherits whatever is wrong at this layer.

## The re-run rule

Any change to `tools/retrieval/index.py`, `tools/retrieval/lexical.py`, `tools/recommendation/fusion.py`, `tools/recommendation/ranking.py`, or
`tools/recommendation/pipeline.py`'s pool construction must be accompanied by a fresh evaluation run,
with the before/after numbers in the changelog entry **and an experiment folder
recording them**:

```bash
make new-experiment SLUG=<what-changed>
```

The harness exists so that the run costs one command and the record costs one
more; see `docs/skills/global.md` and
[`research/AGENT_INSTRUCTIONS.md`](research/AGENT_INSTRUCTIONS.md).
