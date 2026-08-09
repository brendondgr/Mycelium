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

## Status counts

| Status | Count |
|---|---:|
| complete | 4 |
| **total** | **4** |
