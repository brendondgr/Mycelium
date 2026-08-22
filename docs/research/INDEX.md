<!-- GENERATED FILE — do not edit by hand.
     Regenerate with: make research-index -->

# Experiment Index

Every experiment in the record, newest ID last. Status is the manifest's own
`status` field; a `failed` or `superseded` row stays here permanently, because a
deleted dead end is a dead end you walk into twice.

| ID | Date | Title | Status | Primary metric | Claims | Link |
|---|---|---|---|---|---|---|
| `EXP-2026-08-001` | 2026-08-05 | Does the deployed retrieval and fusion stack beat BM25 on an external scholarly collection? | complete | nDCG@10 0.2937 (n=1) | C-001 (refutes C-010) | [folder](experiments/EXP-2026-08-001-longeval-retrieval-baseline/RESULTS.md) |
| `EXP-2026-08-002` | 2026-08-05 | What does confining the lexical channel to the dense-retrieved pool cost in recall? | complete | recall_gain_pct@100 8.7400 (n=1) | C-008 | [folder](experiments/EXP-2026-08-002-dense-pool-vs-union-pool/RESULTS.md) |
| `EXP-2026-08-003` | 2026-08-09 | Does cluster-scoped ranking protect a starved theme? | complete | delta_min_cluster_recall@10_imbalanced -0.0032 ± 0.0086 (n=30) | — (refutes C-003) | [folder](experiments/EXP-2026-08-003-cluster-scoping-synthetic-profiles/RESULTS.md) |
| `EXP-2026-08-004` | 2026-08-09 | Does the per-theme slate protect a starved theme? | complete | delta_cluster_coverage@1000_imbalanced_cut30 0.0667 ± 0.1356 (n=30) | — (refutes C-003) | [folder](experiments/EXP-2026-08-004-cluster-slate-theme-protection/RESULTS.md) |
| `EXP-2026-08-005` | 2026-08-09 | Theme-spread mechanisms for cluster-scoped ranking | complete | delta_min_cluster_recall@10_imbalanced_mmr 0.0043 ± 0.0087 (n=30) | — (refutes C-011) | [folder](experiments/EXP-2026-08-005-cluster-theme-spread-mechanisms/RESULTS.md) |
| `EXP-2026-08-006` | 2026-08-16 | LLM structured-extraction throughput by reasoning level and concurrency | complete | — | — | [folder](experiments/EXP-2026-08-006-extraction-throughput/RESULTS.md) |
| `EXP-2026-08-007` | 2026-08-16 | Source-length-aware grounding floor and its effect on extraction refusal | complete | — | — | [folder](experiments/EXP-2026-08-007-extraction-grounding-floor/RESULTS.md) |
| `EXP-2026-08-008` | 2026-08-21 | Does a learned-sparse channel, a late-interaction reranker, a cross-encoder, or an LLM reranker beat BM25 on LongEval-Sci? | complete | — | C-008, C-013, C-014, C-015 (refutes C-012, C-016) | [folder](experiments/EXP-2026-08-008-retrieval-ladder-splade-colbert-llm/RESULTS.md) |
| `EXP-2026-08-009` | 2026-08-22 | Does the cross-encoder's advantage over BM25 survive a paired confidence interval at 492 queries? | complete | — | — (refutes C-013) | [folder](experiments/EXP-2026-08-009-crossencoder-paired-intervals/RESULTS.md) |
| `EXP-2026-08-010` | 2026-08-22 | Does an LLM prose expansion of the query rescue the cross-encoder on short queries? | complete | — | — (refutes C-017) | [folder](experiments/EXP-2026-08-010-query-prose-expansion-for-reranker/RESULTS.md) |

## Status counts

| Status | Count |
|---|---:|
| complete | 10 |
| **total** | **10** |
