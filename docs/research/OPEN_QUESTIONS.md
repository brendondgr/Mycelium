# Open Questions

Every follow-up from every `RESULTS.md`, plus known weaknesses. This becomes the
future-work section and pre-empts reviewer objections.

Work items keep the `W` numbering from [`../research-audit.md`](../research-audit.md)
§6.5 so the audit's critical-path analysis stays readable. `Q` items are
follow-ups raised by experiments in this record.

## Backlog — from the audit

| ID | Question / work item | Claims | Weeks | Blocked on | State |
|----|----------------------|--------|------:|------------|-------|
| W0 | Strike the knowledge-graph, Cytoscape, multi-agent, and ReAct overstatements from `README.md`, `docs/architecture.md`, and `briefing_agents.py` | narrative | 0.2 | — | **done** — see the `CORRECTED` changelog entry `20260804-briefing-framing` |
| W1 | Pin `LLM_MODEL`, set `LLM_TEMPERATURE=0`, record model identity and token usage on every `RelevanceScore` | C-004 | 0.2 | — | partly done — per-component LLM calls, failures, and token spend are now recorded; temperature still defaults to 0.2 |
| W2 | Run the retrieval stack on LongEval-Sci vs published baselines | C-001 | 1 | — | **done** — `EXP-2026-08-001` |
| W3 | Write 3 claims formally; instrument the personal feed to emit `RelevanceEvent`s and build a consumer | all | 2.5 | — | claims written (`CLAIMS.md`); instrumentation not started — no personal endpoint calls `record_event` |
| W4 | Related-work section engaging the 15 closest works | positioning | 1.5 | — | seeded in `RELATED_WORK.md`; prose not written |
| W5 | Hand-label 250–300 (item, researcher) pairs, graded TREC-CDS style (eligible=2, relevant-but-ineligible=1, irrelevant=0) | C-002, C-005 | 2.5 | W3; ≥3 annotators outside the lab, κ reporting | not started — **the critical-path bottleneck** |
| W6 | Ablation suite: vector-only / BM25-only / RRF / ±cluster-scoping / β sweep / ±LLM rerank | C-001, C-002, C-003 | 2 | W2, W5 | mostly done — retrieval arms in `EXP-2026-08-001`; cluster-scoping and the β sweep in `EXP-2026-08-003`, which **refuted C-003**. Only the LLM rerank arm is outstanding, and it needs internal judgments |
| W7 | Award-linkage ground truth from NIH RePORTER + NSF + CORDIS; profile each PI strictly *before* the award date | C-005 | 4 | — (parallel) | not started. ⚠️ Temporal leakage is the killer; won ≠ applied, so positives carry selection bias |
| W8 | Member-fit evaluation on the RAP gold-standard protocol: self-reported expertise, misranking rate, TF-IDF baseline, workload balance | C-006 | 4 | W3; recruit ≥15 members across ≥3 labs | not started — recruitment is the bottleneck, not the code |
| W9 | IRB submission for a user study | — | 4–8 elapsed | — | not started; **elapsed time is the constraint, so start now** |
| W10 | Rebuild the opportunity corpus from open sources (CORDIS, RePORTER, NSF, public listings) to make it releasable | data legitimacy | 3 | — | not started. Loses Pivot conference CFPs, which have no open equivalent |
| W11 | Structured-output enforcement + retries + order-robustness test for the LLM scorer | C-004 | 1 | — | not started |
| W12 | Post-cutoff contamination holdout + pre/post match-% distribution comparison | C-004 | 1 | W1 | not started |

## Follow-ups raised by experiments

| ID | Question | Raised by | Why it matters |
|----|----------|-----------|----------------|
| Q-001 | Does the union pool's recall advantage survive on the production corpus, where documents are longer and queries are declared interests rather than keywords? | `EXP-2026-08-002` | C-008 is currently a claim about LongEval only. The fix it implies — indexing BM25 over more than the dense pool — is a production change that should not be made on external evidence alone. |
| Q-002 | Would a stronger or domain-adapted embedder close the BM25 gap, or is the gap a property of short keyword queries over titles + abstracts? | `EXP-2026-08-001` | The organizers' 4B-parameter dense baseline also loses to BM25, which points at task shape rather than model size. Testing this cheaply distinguishes "swap the embedder" from "the dense channel is the wrong tool for this query type". |
| Q-003 | Is effectiveness genuinely persistent, or did the 2025 pair only look flat because the topic sets differ? | `EXP-2026-08-001` | The persistence question is the reason LongEval was chosen (D-001) and it is currently unanswered. Needs the same topics re-judged on a later corpus. |
| Q-004 | What does the fusion stack cost, in wall-clock and in dollars, relative to BM25 alone at equal effectiveness? | `EXP-2026-08-001` | A method that loses on the metric *and* costs more has no defence. Wall-clock is already recorded per run; the comparison has not been written up. |
| Q-005 | Does the RRF `k=60` constant matter on this collection, or is any value in a wide band equivalent? | `EXP-2026-08-001` | `k=60` is inherited from the original RRF paper and has never been checked here. A reviewer will ask. Cheap: it is a config sweep on existing runs. |
| Q-006 | At what pool width does deepening the dense pool stop substituting for widening it to a union pool? | `EXP-2026-08-002` | The recall gap is +8.7% at width 100 and +0.6% at width 1000 on the 2026 snapshot. Only two points are measured, so "depth substitutes for width" is a description, not a curve. This decides whether the production fix is a config value or a rewrite of the pool builder — cheap to answer, since pooled runs take seconds. |
| Q-007 | If the retrieval gain from cluster-scoping belongs to the **max operator** rather than to cluster semantics, where on the granularity dial — 1 cluster (flat mean) … *N* clusters (TPMS, max over items) — does retrieval peak, and does the optimum rise with how multi-strand the profile is? | `EXP-2026-08-003` | The `random` control produced the *largest* clustered gains, so the operator is doing the work and the declared themes are not. That reframes the whole area: the interesting variable is granularity, not whether clusters are human-declared. It is also the only framing under which a reviewer-expertise study (CMU Gold, LR-Bench) is still worth its cost. |
| Q-008 | Is `min_cluster_recall@k` the right primary coverage metric? Its aggregate at *k* = 10 was decided by 4 of 30 profiles. | `EXP-2026-08-003` | The metric is zero for most profiles because roughly half of all clusters get nothing in a top-10 at all, so the mean delta is carried by a handful of cases and is invariant in β for mechanical rather than substantive reasons. A depth-normalised or rank-weighted per-cluster measure might have usable power at feed depth. Any future coverage experiment inherits this problem. |
| Q-009 | Does the refutation of C-003 survive on profiles whose clusters are **declared** by a real researcher rather than synthesised from query embeddings? | `EXP-2026-08-003` | The mechanism is refuted under controlled conditions, but the product decision — whether to keep `fuse_clusters_pool` on the lab feed — needs evidence on real lab profiles. Synthetic profiles cannot settle it, and removing a shipped feature on external evidence alone would repeat the mistake C-008/Q-001 already flags. |
| Q-010 | ~~Does the per-theme **slate** deliver the theme protection that global max-pooling was shown not to?~~ **Answered by `EXP-2026-08-004`: no, not demonstrably.** | `EXP-2026-08-003` | The slate is inert at production surfacing (the 250-item backstop leaves every theme's top ten already inside the cut, so the surfaced sets are identical for 100% of profiles), and where the cut binds its coverage gain under `imbalanced` halves to a zero-spanning interval once the cluster path gets the same number of slots. Superseded by Q-011 and Q-012. |
| Q-011 | Does the slate's `imbalanced` advantage resolve with more profiles? | `EXP-2026-08-004` | Every point estimate favours the slate under `imbalanced` and the `random` control is null, but three of the size-matched intervals sit just across zero at n = 30. This is the cheapest open question in the record — `candidate_pool` is already 300, so raising `n_profiles` and re-running one condition costs minutes. Until it runs, "no effect" and "an effect too small to resolve" are not distinguished. |
| Q-012 | On the **production** corpus, does `PAPER_MATCH_THRESHOLD = 0.5` admit more candidates than `PAPER_MATCH_MAX_SURFACE = 250`, as it did for every synthetic profile tested? | `EXP-2026-08-004` | If so, the deployed cut is the backstop rather than the threshold — which makes `top_per_cluster` dead code for the lab paper feed and means the match threshold is not doing the filtering it is assumed to do. Cheap to check against real pools; it is a measurement, not a change. Any settings change still gates on Q-009. |

## Known weaknesses to state before a reviewer does

- **Task mismatch.** Every number in this record comes from ad-hoc *query →
  documents* retrieval. The product does *declared-interest profile → feed*. The
  granularity mismatch between a three-word interest and a 200-word abstract is
  one of the core difficulties of the real problem and is untested.
- **Judgment quality.** All LongEval-Sci numbers rest on click-model-derived
  pseudo-relevance, not human assessment.
- **No seeds in the matching path.** Nothing in the production matching pipeline
  sets a seed. The retrieval arms are deterministic, so this does not affect the
  recorded numbers, but any experiment touching the LLM layer must fix it first.
- **Nondeterministic scoring layer.** `LLM_TEMPERATURE` defaults to 0.2, so the
  scoring layer varies run to run even once the model is pinned. Pinning is
  necessary but not sufficient (W1).
- **Opportunity corpus is not redistributable.** Pivot-RP is Clarivate
  proprietary behind institutional SSO; the Illinois Fellowship Finder is one
  university's site. The paper corpus (OpenAlex, CC0) is fine. W10 is the route
  out.
- **Nothing above the retrieval layer is measured.** Cluster max-pooling, the
  LLM percent-match, fellowship eligibility, and member routing (C-003 to C-006)
  have no evidence at all.
