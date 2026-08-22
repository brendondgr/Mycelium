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
| W10 | Rebuild the opportunity corpus from open sources (CORDIS, RePORTER, NSF, public listings) to make it releasable | data legitimacy | 3 | — | **done for grants and conferences** — the corpus is now collected entirely from public sources. The audit's cost estimate ("loses Pivot conference CFPs, which have no open equivalent") **did not hold**; see the amendment below |
| W11 | Structured-output enforcement + retries + order-robustness test for the LLM scorer | C-004 | 1 | — | not started **for the scorer**, which is the component C-004 is about. A working reference implementation of the first two thirds now exists for a *different* component — the opportunity description extractor (`apps/scraper/collect/extract.py`): fixed JSON schema, deterministic validators, bounded repair loop, refusal as a first-class outcome. Order-robustness is not addressed there, since the extractor sees one record at a time |
| W12 | Post-cutoff contamination holdout + pre/post match-% distribution comparison | C-004 | 1 | W1 | not started |

### Amendment to W10 — 2026-08-16

**What was believed.** `research-audit.md` §6.5 costed W10 at three weeks and
scored its risk "Medium", on one specific ground: rebuilding from open sources
would *lose the Pivot conference CFPs, which have no open equivalent*. The open
sources the audit named — CORDIS, NIH RePORTER, NSF, public university listings —
are all **funding** sources. The audit found no open substitute for the
call-for-papers half and treated that loss as the price of releasability. Risk
row #4 in the same document says the same thing about the corpus overall.

**What was found.** The premise was wrong. Six conference sources were
implemented, all public and all requiring no login or licence:
`ccf_deadlines`, `openreview`, `openresearch`, `miccai`, `ams_mathcal`, and
`society_pages` (`web/backend/apps/scraper/collect/conferences/adapters/`).
They resolve into a series/instance model that carries strictly **more** than
the commercial source did: a trust tier on every series, CCF / CORE / THCPL
rankings where a series has them, per-source links and licence strings, and
**every** deadline round rather than one. Grants come from five live public
adapters (`grants_gov`, `sbir`, `nih_guide`, `nsf`, `eu_portal`; a sixth,
`sam_gov`, needs a free self-service API key and ships disabled). Nothing in the
grant or conference path now requires institutional SSO or a commercial licence.
Fellowships were never a Pivot dependency and are unchanged.

**Evidence.** The adapters above, and the collector store snapshot the extraction
experiments were sampled from — recorded as `mycelium-grants collector stores
(opportunities.db + conferences.db), snapshot 2026-08-16, collector HEAD
6fddf55` in the `data:` block of both
[`EXP-2026-08-006`](experiments/EXP-2026-08-006-extraction-throughput/manifest.yaml)
and
[`EXP-2026-08-007`](experiments/EXP-2026-08-007-extraction-grounding-floor/manifest.yaml).
Of the 1,425 conference series in that snapshot, 334 carry a rank from any of
the three systems and 334 sit in trust tier A, the rest in tier B.

**What the amendment does not settle.** Three things, and they should not be read
as closed:

1. **No coverage comparison was run.** Nobody measured what fraction of the
   commercial corpus's venues the six adapters reproduce, and the old corpus has
   since been deleted, so the comparison is no longer available to run. "There is
   an open equivalent" is demonstrated; "the open equivalent is as complete" is
   not, and cannot now be tested here.
2. **Coverage is skewed by construction.** Four of the six conference sources are
   computer-science-centric; non-CS venues arrive through the society-pages trio
   and land in trust tier B. `openresearch` is geographically skewed and is
   treated as a deadline-and-location spine only, never authoritative on
   descriptive text.
3. **Releasability is not the same as redistributability.** Each row now carries
   a licence string, and they differ per source. A released corpus has to honour
   them row by row; it is not one blanket licence.

**Consequences elsewhere in the record.** The audit's risk row #4 and its W10
critical-path note both rest on the superseded premise; they are historical and
are left as written. This amendment is the correction.

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
| Q-013 | Does any theme-spread mechanism beat the **flat** arm at a larger n, or is flat genuinely the ceiling? | `EXP-2026-08-005` | The decisive question that experiment could not answer. Every mechanism beat the cluster baseline with an interval excluding zero and none beat flat — but the best point estimate over flat is +0.0015 with a CI of `[−0.0011, +0.0043]`, so "no advantage" and "an advantage too small to resolve at n = 30" are not distinguished. Same shape as Q-011, and the same cheap fix: raise `n_profiles` and re-run two arms. Until it runs, the recommendation to ship nothing rests on an absence of evidence rather than evidence of absence. |
| Q-014 | How common is the `imbalanced` condition among **real** declared cluster sets? | `EXP-2026-08-005` | Every mechanism that did anything did it only under `imbalanced` — the grouping built for maximum across-theme score-mass variance. Under `coherent`, the grouping a real profile resembles, not one arm's interval excluded zero and most point estimates were negative. So the prevalence of the pathology decides whether any of this matters, and it is measurable on the production corpus without changing anything. Pairs naturally with Q-009. |
| Q-015 | Should a pre-registered decision threshold be calibrated against the confidence-interval widths the design actually produces, before it is fixed? | `EXP-2026-08-005` | `spread_rankmerge` had the largest primary gain in the grid and a *positive* nDCG@10 point estimate, and failed the guardrail because its interval's lower bound was −0.0104 against a floor of −0.0100. The rule was not renegotiated, correctly — but the floor was chosen with no prior sense of the CI widths at n = 30, so it functioned as an arbitrary coin-flip on the best-performing arm. A pilot-calibrated budget, or a rule stated on the point estimate with the interval reported separately, would not have that property. This is a protocol-design question, not a ranking one, and it applies to every future experiment in this record. |
| Q-016 | ~~Does the cross-encoder's advantage over BM25 survive a paired interval at a larger query set?~~ **Answered by `EXP-2026-08-009`: no — it does not survive, and at 492 queries the cross-encoder is significantly worse.** | `EXP-2026-08-008` | C-013 rests on +0.0095 nDCG@10 at n = 100 with no interval computed. This is the third time this record has been unable to separate a small effect from no effect (see Q-011, Q-013), and it is the cheapest possible fix: `sci-2025-01` carries 492 queries, the arms are already written, and the only new cost is one corpus encode per model. Until it runs, C-013 should be quoted with its margin attached. |
| Q-017 | Is ColBERT's refutation a property of late interaction on this collection, or of this implementation? | `EXP-2026-08-008` | C-012 is refuted on measurement, but the implementation was never checked against a published ColBERT benchmark number, and it differs from the reference setup in two ways that could plausibly degrade MaxSim: `answerai-colbert-small-v1` through fastembed's `query_embed`/`embed` asymmetry, and float16 document vectors. Reproducing a known BEIR number with the same code would settle it in an afternoon and would either harden the refutation or void it. |
| Q-018 | On the production corpus, how many candidates does `fuse_interest` actually emit per target, and is the 0.15 interest floor the binding cut? | `EXP-2026-08-008` | On LongEval the deployed fusion emits only 59-97 candidates per query (median 74) from a 200-document pool, because `DEFAULT_INTEREST_FLOOR = 0.15` discards more than half of it after min-max normalization. That caps rerank depth and caps recall — widening `pool_per_interest` to 500 lifted R@100 from 0.6511 to 0.7098 on identical fusion code. If the same holds on real declared-interest queries, the floor rather than `PAPER_MATCH_THRESHOLD` or `PAPER_MATCH_MAX_SURFACE` is the real constraint on the feed. Pairs directly with Q-012, and is a measurement, not a change. |
| Q-019 | Would a pointwise rubric scorer improve the deployed annotator, which already emits a per-candidate percent? | `EXP-2026-08-008` | The rubric arm matched the listwise arm's quality (0.3099 vs 0.3133) while being order-free by construction and parsing 2,000 of 2,000 pairs against listwise's 95 of 100 queries. It is also structurally much closer to what `apps.content.suggest` already does — score a candidate, do not reorder — than a reranker is. That makes it the one rung on this ladder with a plausible path into the product, and it bears on C-004, which is still unsupported on both of its halves. |

| Q-020 | Does the deployed 0–100 percent-match discriminate relevance where a 0–3 rubric did not? | `EXP-2026-08-008` | The rubric arm collapsed twenty candidates into 1.99 distinct values and ordered grade 2 below grade 1, which is direct evidence against C-004's calibration half — but it used a four-point scale of this experiment's own design, and production emits 0–100. A finer scale may separate where four points cannot, or may simply spread the same non-discrimination over more digits. Until this runs, the deployed match percent is a user-facing number with no evidence that it means anything, and `EXP-2026-08-008` narrows rather than settles that. Cheap: re-run `llm_rubric` with the production prompt and scale, and correlate against the same qrels. |
| Q-021 | Is the cross-encoder result a property of *this* 22M-parameter reranker, or of cross-encoders on short scientific queries generally? | `EXP-2026-08-009` | C-013 is refuted on one model — `Xenova/ms-marco-MiniLM-L-6-v2`, chosen because this host has no GPU. The harm concentrates exactly where a small MS MARCO-trained model would be weakest (one- and two-word queries), which is as consistent with "wrong model" as with "wrong family". `bge-reranker-base` is 1 GB and would take roughly 10x the CPU time per pair, but the arms already exist and only the model name changes. Until it runs, the refutation is scoped to one model and should be quoted that way. |
| Q-022 | Do the recall claims C-008 and C-014 survive paired intervals? | `EXP-2026-08-009` | Every nDCG@10 contrast re-tested from `EXP-2026-08-008` spans zero at n = 100. Those two are the only ladder findings still standing, and neither has an interval. Their effects are much larger (+0.052 and +0.063 R@100 against a ±0.04 nDCG@10 resolution limit) so they are likely to hold, but "likely" is what this record has twice been burned by. The runs already exist — this is a scoring pass over committed run files, not a re-run. |
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
- **Opportunity corpus licensing is now per-row, not blocked.** The commercial,
  SSO-gated source is gone (W10): grants and conferences come from public
  sources and each row carries its own licence string, which a release has to
  honour individually rather than under one blanket. The Illinois Fellowship
  Finder is still one university's public site. The paper corpus (OpenAlex, CC0)
  is fine.
- **Opportunity descriptions are model-written.** Every grant and conference
  description in the corpus is an LLM extraction, verified by deterministic
  checks and refused when it fails them, and the verified text is what gets
  embedded. This is a property of the corpus a released dataset must state, and
  it means the opportunity retrieval basis is not raw source text. Its effect on
  retrieval quality is **unmeasured** — `metadata["search_text_source"]`
  (`extracted` | `raw`) is recorded per row precisely so that the comparison
  stays available.
- **Nothing above the retrieval layer is measured.** Cluster max-pooling, the
  LLM percent-match, fellowship eligibility, and member routing (C-003 to C-006)
  have no evidence at all.
