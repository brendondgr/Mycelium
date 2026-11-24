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
| `EXP-2026-09-002` | 2026-11-12 | Does the citation verifier agree with a person? | complete | inject_paraphrase_recall 0.0000 | C-025 | [folder](experiments/EXP-2026-09-002-weekly-citation-verifier/RESULTS.md) |
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
| `EXP-2026-09-014` | 2026-09-19 | Does the evolving profile keep its promises over eight simulated weeks, and do exploration themes stay beside the declared ones? | complete | — | — | [folder](experiments/EXP-2026-09-014-ambient-evolving-profile-sandbox/RESULTS.md) |
| `EXP-2026-09-015` | 2026-09-19 | Does Mylo read replies in people's own words right, never turn a no into a yes, and catch "stop asking"? | complete | — | — | [folder](experiments/EXP-2026-09-015-ambient-dialogue-replies-sandbox/RESULTS.md) |
| `EXP-2026-09-016` | 2026-09-19 | Do the ambient web pages work in a real browser, from the keyboard, and pass WCAG 2.1 AA checks? | complete | — | — | [folder](experiments/EXP-2026-09-016-ambient-web-browser-a11y/RESULTS.md) |
| `EXP-2026-09-017` | 2026-09-19 | Does what changed reach the right reports, and only them? | complete | — | — | [folder](experiments/EXP-2026-09-017-ambient-reports-routing-sandbox/RESULTS.md) |
| `EXP-2026-09-018` | 2026-09-19 | Do the ambient harm checks read zero on a clean record and catch each violation they exist for? | complete | — | — | [folder](experiments/EXP-2026-09-018-ambient-harm-checks-sandbox/RESULTS.md) |
| `EXP-2026-09-019` | 2026-09-19 | How much may a confirmed exploration weigh before it moves the declared slates? | complete | — | — | [folder](experiments/EXP-2026-09-019-ambient-drift-weight-ablation/RESULTS.md) |
| `EXP-2026-09-020` | 2026-09-19 | Ambient pilot: is Mylo making changes people agree with, and do they make the recommendations better? | planned | — | — | [folder](experiments/EXP-2026-09-020-ambient-pilot-go-no-go/RESULTS.md) |
| `EXP-2026-09-021` | 2026-09-19 | Do Slack and Teams change anything past the adapter? | complete | — | — | [folder](experiments/EXP-2026-09-021-ambient-platforms-parity-sandbox/RESULTS.md) |
| `EXP-2026-11-001` | 2026-11-05 | Precision of the department-level call detector | complete | precision_overall_v1 0.8333 | C-028 | [folder](experiments/EXP-2026-11-001-dept-level-precision/RESULTS.md) |
| `EXP-2026-11-002` | 2026-11-05 | Announcement measures baseline and department lab-fit floor | complete | lab_fit_precision_at_floor 0.6667 | C-029 | [folder](experiments/EXP-2026-11-002-announcement-baseline/RESULTS.md) |
| `EXP-2026-11-003` | 2026-11-08 | Tools refactor: ranking parity before and after the code moves | complete | run_files_identical 1.0000 | — | [folder](experiments/EXP-2026-11-003-tools-refactor-parity/RESULTS.md) |
| `EXP-2026-11-004` | 2026-11-08 | Full-text coverage of the paper corpus from free sources | complete | full_text_rate 0.5400 (n=200) | — | [folder](experiments/EXP-2026-11-004-fulltext-coverage/RESULTS.md) |
| `EXP-2026-11-005` | 2026-11-08 | Full-text coverage after the PubMed id repair (Q-057) | complete | full_text_rate 0.6500 (n=200) | — | [folder](experiments/EXP-2026-11-005-fulltext-coverage-own-ids/RESULTS.md) |
| `EXP-2026-11-006` | 2026-11-08 | Conference location and continent coverage | complete | continent_rate 0.9035 (n=912) | — | [folder](experiments/EXP-2026-11-006-conference-location-coverage/RESULTS.md) |
| `EXP-2026-11-007` | 2026-11-09 | Can a 0.85B decision model served on this host answer the TypeSafe rerank questions? | complete | discrimination_auc_worth 0.6899 | — | [folder](experiments/EXP-2026-11-007-d3-lite-local-decision-smoke/RESULTS.md) |
| `EXP-2026-11-008` | 2026-11-09 | How many decisions per second does the local decide port sustain through Mycelium's client? | complete | throughput_c1 7.1320 | — | [folder](experiments/EXP-2026-11-008-decision-port-throughput/RESULTS.md) |
| `EXP-2026-11-009` | 2026-11-09 | Does a stock 4B instruct model on llama.cpp make usable rerank decisions through the port path? | complete | worth_auc 0.4889 | — | [folder](experiments/EXP-2026-11-009-qwen3-4b-llamacpp-decisions/RESULTS.md) |
| `EXP-2026-11-010` | 2026-11-13 | Mylo agent: latency and tokens of a 1-, 5- and 15-step tool loop, and of real questions | complete | a2.a2idle.turns_with_up_to_5_function_calls.wall_s_max 9.5900 | C-030 | [folder](experiments/EXP-2026-11-010-agent-loop-cost/RESULTS.md) |
| `EXP-2026-11-011` | 2026-11-13 | Mylo agent baseline: grounded answers, permission and scope probes, prompt-only comparison, memory lifecycle | complete | pooled_3_3b.diff_prompt_only_minus_gate 0.5104 | C-031, C-032 (refutes C-036) | [folder](experiments/EXP-2026-11-011-mylo-agent-baseline/RESULTS.md) |
| `EXP-2026-11-012` | 2026-11-09 | d3-lite throughput when pairs share a forward pass | complete | d3_over_qwen_best_real 1.3890 | — | [folder](experiments/EXP-2026-11-012-d3-lite-batched-throughput/RESULTS.md) |
| `EXP-2026-11-013` | 2026-11-12 | Mylo answers: human-judged correctness, single-call baseline, and the answer verifier | running | inject.main.paraphrase.recall 0.0000 | C-033, C-034, C-035 | [folder](experiments/EXP-2026-11-013-agent-answers-human-judged/RESULTS.md) |
| `EXP-2026-11-014` | 2026-11-13 | pplx-decider-flash load test on the local decision server | complete | r1.joint.c24.decisions_per_s 5.2540 | — | [folder](experiments/EXP-2026-11-014-decider-flash-load/RESULTS.md) |
| `EXP-2026-11-015` | 2026-11-12 | Deployment usage snapshot | complete | people_active_30d 2.0000 | — | [folder](experiments/EXP-2026-11-015-deployment-usage-snapshot/RESULTS.md) |
| `EXP-2026-11-016` | 2026-11-15 | Permission gate replicated: second model, seeded worlds, second reader | complete | — | C-037, C-038 | [folder](experiments/EXP-2026-11-016-agent-gate-replication/RESULTS.md) |
| `EXP-2026-11-017` | 2026-11-15 | Deletion, opt-out and member isolation with enough runs | complete | — | C-041, C-042 (refutes C-040) | [folder](experiments/EXP-2026-11-017-agent-memory-lifecycle/RESULTS.md) |
| `EXP-2026-11-018` | 2026-11-15 | Mylo answers graded by code against stored facts | complete | arm_a_answerable_full_credit 0.7200 (n=150) | C-043, C-044, C-045, C-046 | [folder](experiments/EXP-2026-11-018-agent-answers-gold/RESULTS.md) |
| `EXP-2026-11-019` | 2026-11-15 | Collaborator search through Mylo, by scenario | complete | claim_b_gate_violation_rate_S3_S10 0.0000 (n=206) | C-050, C-051, C-052 | [folder](experiments/EXP-2026-11-019-agent-collab-scenarios/RESULTS.md) |
| `EXP-2026-11-020` | 2026-11-15 | The answer checker as a loop: repair, removal, unread | complete | forced_drafts_error_in_final 0.0000 (n=90) | C-047, C-048 (refutes C-049) | [folder](experiments/EXP-2026-11-020-agent-verifier-loop/RESULTS.md) |
| `EXP-2026-11-021` | 2026-11-16 | Does Mylo work on the model just loaded? A thirty-turn check, one row per model | complete | — | C-053, C-054 | [folder](experiments/EXP-2026-11-021-agent-model-check/RESULTS.md) |
| `EXP-2026-11-022` | 2026-11-18 | Gemma 4 31B empty replies: the 2026-11-15 code replayed against today's server | complete | f1115.both.blank_turns 19.0000 (n=108) | — | [folder](experiments/EXP-2026-11-022-gemma-empty-replies-replay/RESULTS.md) |
| `EXP-2026-11-023` | 2026-11-19 | Collaborator suggestions for a real department's faculty, for rating by someone who knows them | complete | ratings_would_contact_rate_shown 0.9706 | C-057 | [folder](experiments/EXP-2026-11-023-collab-live-fsu-sc/RESULTS.md) |
| `EXP-2026-11-024` | 2026-11-19 | Typed-question collaborator search after the slot-reader fix, on the EXP-2026-11-023 department | complete | after_seekers_with_any_suggestion 11.0000 | — | [folder](experiments/EXP-2026-11-024-collab-typed-question-rerun/RESULTS.md) |
| `EXP-2026-11-025` | 2026-11-19 | One problem slot per listed topic in typed collaborator questions (Q-102) | complete | multi_seekers_with_any_suggestion 12.0000 | — | [folder](experiments/EXP-2026-11-025-collab-self-query-problem-slots/RESULTS.md) |
| `EXP-2026-11-026` | 2026-11-22 | The paper's Mylo evaluation repeated on Inkling 2 Mini (26B-A3B, NVFP4) | complete | — | C-037, C-038, C-044, C-052, C-053, C-054 | [folder](experiments/EXP-2026-11-026-inkling-2-mini-rerun/RESULTS.md) |
| `EXP-2026-11-027` | 2026-11-24 | Access test at three temperatures, rules in code against rules in the prompt | complete | — | C-058, C-059 | [folder](experiments/EXP-2026-11-027-agent-gate-temperature/RESULTS.md) |
| `EXP-2026-11-028` | 2026-11-24 | Answer accuracy with the rules in code against the rules in the prompt, on a demo-only sandbox | complete | — | C-060 | [folder](experiments/EXP-2026-11-028-agent-answers-gold-prompt-arm/RESULTS.md) |

## Status counts

| Status | Count |
|---|---:|
| complete | 65 |
| planned | 3 |
| running | 1 |
| **total** | **69** |
