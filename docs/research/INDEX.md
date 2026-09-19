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
| `EXP-2026-08-011` | 2026-08-22 | Do the ladder's two surviving recall claims survive a paired confidence interval? | complete | — | C-008, C-014, C-018 | [folder](experiments/EXP-2026-08-011-recall-paired-intervals/RESULTS.md) |
| `EXP-2026-08-012` | 2026-08-22 | Do the ladder's surviving recall claims replicate on sci-2025-01? | complete | — | C-008, C-014, C-018 | [folder](experiments/EXP-2026-08-012-recall-replication-2025/RESULTS.md) |
| `EXP-2026-08-013` | 2026-08-22 | Q-001: does the union pool's advantage survive on the production corpus? | complete | — | C-019, C-020 | [folder](experiments/EXP-2026-08-013-production-pool-contrast/RESULTS.md) |
| `EXP-2026-08-014` | 2026-08-22 | Side-by-side top-10 lists across retrieval arms, for human preference | complete | — | C-021 | [folder](experiments/EXP-2026-08-014-retrieval-side-by-side/RESULTS.md) |
| `EXP-2026-08-015` | 2026-08-22 | Four arms, one query: title-by-arm rank matrix for human preference | complete | — | C-021 | [folder](experiments/EXP-2026-08-015-four-arm-title-matrix/RESULTS.md) |
| `EXP-2026-08-016` | 2026-08-22 | Same four arms, a second research area: knowledge graphs | complete | — | C-021 | [folder](experiments/EXP-2026-08-016-knowledge-graphs-title-matrix/RESULTS.md) |
| `EXP-2026-08-017` | 2026-08-22 | Three channels + cross-encoder against the dense pool + cross-encoder | complete | — | C-021 | [folder](experiments/EXP-2026-08-017-splade-vs-dense-reranked/RESULTS.md) |
| `EXP-2026-08-018` | 2026-08-22 | Shipping the cross-encoder rerank: flag-off invariance and on/off cost | complete | — | C-023 | [folder](experiments/EXP-2026-08-018-rerank-ship-verification/RESULTS.md) |
| `EXP-2026-08-019` | 2026-08-23 | Per-cluster admission: harness regression check | complete | — | — | [folder](experiments/EXP-2026-08-019-per-cluster-admission-regression/RESULTS.md) |
| `EXP-2026-08-020` | 2026-08-23 | Theme-scoped interest context: production slate separation | complete | — | — | [folder](experiments/EXP-2026-08-020-theme-scoped-interest-context/RESULTS.md) |
| `EXP-2026-09-001` | 2026-09-11 | Alert precision, and the thresholds it sets | planned | — | C-024 | [folder](experiments/EXP-2026-09-001-alert-precision-calibration/RESULTS.md) |
| `EXP-2026-09-002` | 2026-09-11 | Does the citation verifier agree with a person? | planned | — | C-025 | [folder](experiments/EXP-2026-09-002-weekly-citation-verifier/RESULTS.md) |
| `EXP-2026-09-003` | 2026-09-17 | Does a calibrated decision model agree with the fused order and the LLM verdicts on one reader's grant and conference slates? | complete | — | C-026 | [folder](experiments/EXP-2026-09-003-typesafe-personal-opportunities/RESULTS.md) |
| `EXP-2026-09-004` | 2026-09-17 | Does a calibrated pointwise probability rerank a scholarly feed better than BM25 alone? | complete | — | — (refutes C-027) | [folder](experiments/EXP-2026-09-004-typesafe-pointwise-rerank-longeval/RESULTS.md) |
| `EXP-2026-09-005` | 2026-09-18 | Do people's papers become the right demonstrated concepts? A synthetic-world test of plan CN-02 | complete | — | — | [folder](experiments/EXP-2026-09-005-knowledge-demonstrated-sandbox/RESULTS.md) |
| `EXP-2026-09-006` | 2026-09-18 | Do funding calls become the right requirement slots, and is team coverage marked correctly? A synthetic-world test of plan CN-03 | complete | — | — | [folder](experiments/EXP-2026-09-006-collab-slots-teamfit-sandbox/RESULTS.md) |
| `EXP-2026-09-007` | 2026-09-18 | Is anyone ever findable who should not be? A synthetic-world test of plan CN-04 | complete | — | — | [folder](experiments/EXP-2026-09-007-collab-consent-sandbox/RESULTS.md) |
| `EXP-2026-09-008` | 2026-09-19 | Does the matcher find the right people in the right lane, and nobody it should not? A 600-person synthetic test of plan CN-05 | complete | — | — | [folder](experiments/EXP-2026-09-008-collab-matcher-sandbox/RESULTS.md) |
| `EXP-2026-09-009` | 2026-09-19 | Does the collaborator search panel work end to end for hundreds of fake seekers, and does every response stay a coarse pointer? A sandbox test of plan CN-06 | complete | — | — | [folder](experiments/EXP-2026-09-009-collab-search-panel-sandbox/RESULTS.md) |
| `EXP-2026-09-010` | 2026-09-19 | Do introduction paths, 'outside my network' and team formation name only who they may, and find what they should? A synthetic-graph test of plan CN-07 | complete | — | — | [folder](experiments/EXP-2026-09-010-collab-graph-features-sandbox/RESULTS.md) |
| `EXP-2026-09-011` | 2026-09-18 | Postgres recursive queries or Neo4j for the co-authorship graph? Latency at 1,000, 5,000 and 20,000 people | complete | — | — | [folder](experiments/EXP-2026-09-011-coauthorship-store-benchmark/RESULTS.md) |
| `EXP-2026-09-012` | 2026-09-18 | Is the collaboration network useful and harmless in real use? Slot quality, coverage accuracy, concept linking, lane quality, concentration and harm on live data (plan CN-08) | planned | — | — | [folder](experiments/EXP-2026-09-012-collab-live-evaluation/RESULTS.md) |
| `EXP-2026-09-013` | 2026-09-19 | Does ambient Plan 04 find what people said, decide the right outcome, and keep every privacy promise? Four weeks of model-written lab conversation with planted truth | complete | — | — | [folder](experiments/EXP-2026-09-013-ambient-reasoning-sandbox/RESULTS.md) |

## Status counts

| Status | Count |
|---|---:|
| complete | 30 |
| planned | 3 |
| **total** | **33** |
