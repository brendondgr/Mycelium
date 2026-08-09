# Claims Ledger

Every claim the paper will make, and the evidence that supports it. This is the
highest-value file in the record: it says at a glance which claims can actually
be made and which are currently vapour.

**Status:** `unsupported` | `partial` | `supported` | `refuted` | `cut`

Claims C-001…C-007 are the implicit research claims derived from what the code
does, first written down in [`../research-audit.md`](../research-audit.md) §1.6
as C1–C7. The numbering is preserved deliberately — renumbering would break every
reference in that audit. C-008 onward are new claims added as the work moves.

| ID | Claim | Evidence | Artifact | Status | Notes |
|----|-------|----------|----------|--------|-------|
| C-001 | Fusing a BM25 rescoring of the vector-retrieved pool with the vector ranking via RRF (k=60) orders a paper feed better than vector retrieval alone, for a user described by 2–6 short declared interests. | `EXP-2026-08-001` | `fig-arm-comparison` | **partial** | Measured on an external ad-hoc collection, not on the personalized feed task. Fusion beats dense-only on every snapshot, so the "better than vector alone" half holds. It **loses to BM25 alone** on nDCG@10 everywhere, so the implied "hybrid is the right default" does not. See C-008. |
| C-002 | Rewarding breadth across a user's declared interests — `mean × (1 + 0.15·(n−1))` — produces more useful recommendations than ranking by the single best-matching interest. | — | — | unsupported | Needs multi-interest relevance judgments (W5). One synthetic 2-document unit test confirms only the arithmetic. `EXP-2026-08-003` swept β ∈ {0, 0.15, 0.3} but adds nothing either way: the paired delta it measures is invariant in β. |
| C-004 | An LLM given a researcher's profile and 10 candidates can assign a 0–100 relevance score that orders them better than the fusion score does, **and** the emitted integer is meaningful as a match percentage. | — | — | unsupported | Two experiments, not one: ranking quality, and calibration. The literature says the first is plausible and the second is not. |
| C-005 | Gating fellowships on deterministic eligibility before relevance scoring, then blending 0.65·cosine + 0.35·rule-fit, surfaces fellowships a researcher can actually win better than relevance ranking alone. | — | — | unsupported | Needs graded TREC-CDS-style judgments (eligible=2, ineligible-but-relevant=1, irrelevant=0) on a labeled fellowship sample. |
| C-006 | Cosine between an item embedding and a lab member's profile embedding (floor 0.35, top 3) identifies the member for whom an item is most relevant, and an LLM constrained to remove-only cannot degrade it. | — | — | unsupported | Needs the RAP gold-standard protocol: self-reported expertise from ≥15 members across ≥3 labs. Recruitment is the bottleneck, not the code. |
| C-007 | Admitting every item above an absolute cosine threshold, rather than a fixed top-K, yields a more honest and more useful feed. | — | — | unsupported | ⚠️ No benchmark in this field thresholds on raw cosine, because cosine magnitudes are not calibrated across queries. |
| C-008 | Restricting the lexical channel to the dense-retrieved pool — indexing BM25 over only what vector retrieval already found — costs recall that a union pool recovers, and the cost grows as the dense channel weakens on a corpus. | `EXP-2026-08-002` | `fig-pool-recall-gap` | **supported** | R@100 rises 8.7% on the 2026 snapshot and 75–80% on the two 2025 snapshots at matched pool width. Measured on LongEval-Sci only; the production corpus is untested. |
| C-009 | Mycelium's retrieval effectiveness persists as the corpus grows — it does not decay with corpus age. | `EXP-2026-08-001` | — | **unsupported** | The 2025 pair shows no decay, but confounds elapsed time with topic difficulty (99 vs 492 queries, different topic sets). A clean answer needs the same topics re-judged on a later corpus — the withheld 2026 test snapshots. Blocked on data, not design. |

## Refuted and cut claims

Kept permanently. They document what was tried and prevent re-litigating settled
questions.

| ID | Claim | Evidence | Status | Why |
|----|-------|----------|--------|-----|
| C-003 | For a lab or broad-interest user, ranking within research clusters and max-pooling across them prevents one vocabulary-dominant theme from monopolizing the feed, relative to global ranking. | `EXP-2026-08-003`, `EXP-2026-08-004` | **refuted** | Measured on synthetic multi-cluster profiles over LongEval-Sci. In the `imbalanced` condition the claim names — one theme's vocabulary far closer to the corpus than the others' — cluster-scoping *lowers* the worst-served theme's recall (Δ`min_cluster_recall@10` = −0.0032, 95% CI `[−0.0066, −0.0007]`) and lowers `cluster_coverage@10` by 0.044. Under `coherent` grouping the effect is +0.0010 with an interval whose lower bound is zero. `cluster_gini@10` rises (worsens) in all nine cells: max-over-clusters concentrates the feed rather than spreading it. The `random` negative control shows the *largest* clustered gains, so what gain exists belongs to the max operator, not to cluster semantics — see `EXP-2026-08-003` RESULTS §4 and Q-007. **Both** cluster paths were tested. `EXP-2026-08-003` covered the global max-pooled ranking (an individual's feed); `EXP-2026-08-004` added the lab feed's per-theme slate (`top_per_cluster`), which does not restore the claim: it is inert at production surfacing (identical surfaced sets for 100% of profiles) and, where the cut binds, its coverage gain halves to a zero-spanning interval once the cluster path is given the same number of slots. Scoped to synthetic profiles and click-derived qrels; it refutes the mechanism, not the product decision (Q-009, Q-011). |
| C-011 | A theme-aware *selection* rule over the cluster-scoped ranking — allocating slots per theme rather than filling them by a global score — raises the worst-served theme's representation in the visible feed, at a relevance cost inside a stated budget. | `EXP-2026-08-005` | **refuted** | The remedy C-003's refutation implies. Six mechanisms measured individually and combined, on the same synthetic profiles, at deployed surfacing. Against the *cluster* baseline the claim looks true: on `imbalanced` profiles four mechanisms raise `min_cluster_recall@10` with intervals excluding zero (rank-merge +0.0047 `[+0.0010, +0.0089]`, MMR +0.0043 `[+0.0014, +0.0078]`), MMR and rank-merge raise `cluster_coverage@10` by +0.0778, and — unlike `EXP-2026-08-003` — the `random` control is null for every mechanism, so the gain **is** theme-attributable. Against the *flat* baseline it collapses: no mechanism's advantage over no-clusters-at-all has an interval excluding zero (best +0.0015 `[−0.0011, +0.0043]`), round-robin is significantly worse than flat on nDCG@10 (−0.0196), and under the realistic `coherent` grouping nothing helps and most point estimates are negative. There is also no synergy — every combination collapses onto one of its parts on ≥27/30 profiles, because the score fix and the selection fix act on disjoint inputs. So the mechanisms repair damage clustering the ranking caused rather than creating value over not clustering it. Scoped to synthetic profiles, click-derived qrels, one parameter setting per mechanism, and n = 30 (see Q-013). No production default was changed; every policy ships off. |
| C-010 | The deployed hybrid fusion ranker outperforms a strong lexical baseline on scholarly retrieval. | `EXP-2026-08-001` | **refuted** | BM25 alone beats every fusion arm on nDCG@10 on all three snapshots. The organizers' own 4B-parameter dense baseline also loses to BM25. This is a property of short keyword queries over titles + abstracts, so it is evidence about the task shape — not only a reason to swap embedders. Any paper draft must state it. |

## Rules

- Write a claim here **before** it is supported, marked `unsupported`. The
  unsupported rows are the experiment backlog.
- A claim moves to `supported` only when an experiment ID sits in its Evidence
  column and that experiment's `supports_claims` names it back. The validator
  checks the second direction.
- A claim is never deleted. Cut claims move to the table above with the reason.
- Claims are scoped to what was measured. "On LongEval-Sci" is part of the claim,
  not a footnote — see the claims boundary in
  [`../evaluation.md`](../evaluation.md).
