# Related Work

Running bibliography with one line on how each work differs from ours, plus a
scoop watch. Update this whenever a relevant paper surfaces — not the week before
submission.

The full annotated bibliography (~50 entries, grouped by area) lives in
[`../research-audit.md`](../research-audit.md) §9 and keeps its `[Bn]` numbering.
This file carries the works that bear directly on a claim, and it is the one that
gets maintained.

## Closest prior work

| Ref | Work | How it differs from us | Bears on |
|---|---|---|---|
| **[B1]** | Flicke et al., *Scholar Inbox: Personalized Paper Recommendations for Scientists*, ACL 2025 Demos | They **learn** from 800k public user ratings and evaluate with a user study; we do neither. We add funding/CFPs, lab-level targets, and member routing. | C-001, C-003 |
| **[B26]** | *ResearchArena: Benchmarking LLMs as Research Agents* | Benchmarks the discovery→selection→organization pipeline. Their headline finding points against us: LLM approaches **underperform keyword retrieval**. | C-004 |
| **[B14]** | Zeng & Acuna, *GotFunding*, ASIS&T 2020 | Learning-to-rank over NIH grant–publication records (nDCG@1 = 0.945); we hand-pick a 6-feature linear blend. Existence proof that award data yields ground truth. | C-005 |
| **[B39]** | *Matching Researchers to Funding Calls: A Reproducible Institution-Level Framework*, 2026 | Closest published architecture. No eligibility layer; institution-scale not lab-scale; no LLM — and they evaluate. Their multiple-profiles-per-researcher is our multi-interest vectors. | C-005 |
| **[B15]** | *A Gold Standard Dataset for the Reviewer Assignment Problem*, 2023 | Measures the member-fit task under another name. Reports **36–43% misranking in hard cases**; our cosine floor of 0.35 sits in that regime. | C-006 |
| **[B17]** | *Traditional statistical representations outperform generative AI in identifying expert peer reviewers*, 2026 | TF-IDF 79.5% vs GPT-4o mini 51.5% at top-25 expert recall, diagnosing "semantic smoothing" in embeddings. Any member-fit evaluation needs a TF-IDF baseline. | C-006 |
| **[B7]** | Jin et al., *TrialGPT*, Nat. Commun. 2024 | Per-criterion eligibility prediction with provenance; we use a hardcoded facet table. Sets the bar for what an eligibility layer should look like. | C-005 |
| **[B8]** | *SatIR: Constraint-Satisfaction-Based IR for Clinical Trials Matching*, 2026 | Compiles free-text eligibility into SMT constraints, with a principled safety condition, +22–38 recall points over TrialGPT. States properly the correctness condition our rule engine gestures at. | C-005 |
| **[B4]** | Cen et al., *ComiRec*, KDD 2020 | Multi-interest retrieval with a **tuned** controllable aggregation parameter. Our β=0.15 occupies that slot and is a self-declared placeholder. | C-002 |
| **[B41]** | Mysore et al., *LACE*, SIGIR 2023 | Human-readable, user-editable concept profiles — the direct intellectual ancestor of our interest clusters — but evaluated, with a controllability guarantee. | C-003, C-007 |
| **[B2]** | Cormack, Clarke & Buettcher, *Reciprocal Rank Fusion*, SIGIR 2009 | The fusion method itself. ⚠️ The same paper showed RRF beating CombMNZ; we stack a softened CombMNZ *on top of* RRF. | C-001, Q-005 |
| **[B9]** | Cemri et al., *Why Do Multi-Agent LLM Systems Fail?*, NeurIPS 2025 D&B | 14 failure modes from 150 annotated traces; gains "often minimal". | — |
| **[B10]** | Tran & Kiela, *Single-Agent LLMs Outperform Multi-Agent Systems Under Equal Thinking Token Budgets*, 2026 | Controlled ablation at matched budgets: single-agent matches or beats multi-agent. | — |
| **[B42]** | *PaperWeaver*, CHI 2024 | LLM contextual explanations of relevance, measured with N=15: better understanding, more confident triage. The template for measuring our prose rationales. | C-004 |
| **[B43]** | Adaptive candidate-set expansion | Up to +28% recall by expanding the candidate set rather than filtering it. The literature's answer to bounded-recall architectures like ours. | C-008 |
| **[B21]** | TREC-CDS graded eligibility protocol | eligible=2 / relevant-but-ineligible=1 / irrelevant=0. The judgment scheme W5 should adopt. | C-005 |

## Baselines we are measured against

| System | Where | Why it is the right baseline |
|---|---|---|
| BM25 (PyTerrier, LongEval'26 organizers) | `EXP-2026-08-001` | The organizers' own published run, re-scored by our harness with the same `ir_measures` call — not a number quoted from a paper. It currently **beats every arm we have**. |
| Qwen3-Embedding-4B (LongEval'26 organizers) | `EXP-2026-08-001` | A 4B-parameter dense retriever. It also loses to BM25 on this collection, which is what makes the result evidence about task shape rather than about our 384-dimension model. |

## Scoop watch

Papers that partially overlap the contribution. Checked when a relevant paper
surfaces; last swept 2026-08-04 as part of the research audit.

| Threat | Work | Status |
|---|---|---|
| **Scoops the paper-feed framing** | Scholar Inbox [B1] | Live. Any paper claiming "personalized daily research feed" must cite it and state a delta. They also shipped an 800k-rating dataset we do not have. |
| **Scoops literature discovery, pointing against us** | ResearchArena [B26] | Live. Their finding that LLM selection underperforms keyword retrieval is consistent with `EXP-2026-08-001`, where BM25 beat every fusion arm. |
| **Pre-refutes any multi-agent framing** | [B9], [B10] | Live, and already acted on — the multi-agent language was struck from this repository's docs (W0). |
| **Undercuts member routing** | [B15], [B17] | Live. Both say the measurement will be unflattering. That is a reason to run it, not to skip it. |
| **Not scooped** | Eligibility-constrained fellowship recommendation with *graded* ineligibility (G2); lab-level recommendation with member routing (G3) | A good-faith search found no paper on either. These are the two defensible contributions. Re-sweep before any submission. |

## How to sweep

Search terms that were used and should be reused: `grant recommendation system`,
`funding opportunity matching`, `fellowship recommender`, `call for proposals
recommendation`, `team recommendation scholarly`, `group recommendation research
papers`, `paper routing lab member`, plus the reviewer-assignment, expert-finding,
and clinical-trial-matching literatures.
