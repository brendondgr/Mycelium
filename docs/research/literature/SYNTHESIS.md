# Literature Landscape: Grants, Fellowships, Conferences, Multi-Lens Ranking, and Knowledge-Graph Teaming

Compiled 2026-08-06. Companion surveys in this directory:
[`grants-fellowships.md`](grants-fellowships.md), [`venues-conferences.md`](venues-conferences.md),
[`kg-team-formation.md`](kg-team-formation.md). Feed confirmed entries into
[`../RELATED_WORK.md`](../RELATED_WORK.md) with `[Bn]` numbering (W4).

---

## 0. The one-paragraph answer

Across all four item types Mycelium ranks, **the literature is thin in inverse proportion
to how much the item type matters to us.** Papers/venues have a 15-year literature and no
shared benchmark; grants have roughly six methods papers and no benchmark at all;
fellowships have essentially nothing. The KG-teaming idea is the thinnest of the four —
about four systems worldwide take a funding call as input and emit a team, and only one
(ULTRA) has been deployed and human-evaluated. That thinness is the opportunity, but it
comes with a specific trap: **the hypothesis that better-matched interdisciplinary teams
win more grants is, as literally stated, contradicted by the best available evidence.**
The defensible version of the claim is narrower and is stated in §5.

Two structural facts should shape everything downstream:

1. **The negative class does not exist in open data.** CORDIS, NSF, and NIH publish only
   funded work. Exactly one public dataset contains unsuccessful applications
   (`arXiv:2603.26426`, UK funding lifecycle). Everything else forces "won" as a proxy for
   "should have applied."
2. **The award target is close to noise at the margin.** Pier et al. (PNAS 2018) report
   ICC ≈ 0 among NIH reviewers scoring the same applications. Li & Agha (Science 2015)
   show scores predict outcomes *globally*, with rich controls. Reconciled: signal exists
   across the range, ~none at the funding margin — and the margin is precisely where a
   recommender operates. **Optimize for justifiable recommendations, not predicted award
   probability.**

---

## 1. Grants and fellowships — where we sit

### The whole methods literature, essentially

| Work | Year | Approach | Ground truth |
|---|---|---|---|
| KAKEN association rules (arXiv:1807.03493) | 2018 | Rule mining over grant keywords | — |
| Zeng & Acuna, **GotFunding**, ASIS&T 57(1):e323 | 2020 | Random-Forest LTR, 4 features | NIH grant↔publication |
| Zhu, Patra, Wu & Yaseen, **PLOS ONE** 18(1):e0278636 | 2023 | BERT cross-encoder + **DPMM clustering of the researcher's publications** + recency weighting | Grant citations in papers |
| Han et al., **IEEE Access** 12:98096 | 2024 | BERT cross-encoder + BiLSTM, back-translation aug. | 12,991 NIH biosketches × 2,234 RFPs |
| Arroyo-Machado et al., arXiv:2604.06321 | 2026 | **Multiple bibliometric-slice profiles per researcher**, each embedded separately | **None — no accuracy metric reported** |
| Huang & Li, UAlbany MatchMaker (NSF-PAR 10566919) | 2024 | BERTopic + exact keyword match on SPIN taxonomy, authorship-position weights | Deployed; qualitative feedback only |

Fellowships: **empty.** No peer-reviewed work on postdoc fellowship, K-award, ERC Starting
Grant, or MSCA matching. Nothing treats citizenship, residency, or years-since-PhD — the
*defining* fellowship constraints — as a modelling problem. This is the single emptiest
niche adjacent to us and it is where `apps/content/fellowships.py` already operates.

### What this means for Path A

Two papers independently converged on our core structural idea. Zhu et al. (2023) cluster a
researcher's publications with a Dirichlet Process mixture before aggregating; Arroyo-Machado
et al. (2026) build several bibliometric slices per researcher and embed each separately.
**Neither uses max-pooling, neither has a breadth bonus, neither attributes a result back to
the lens that surfaced it, and neither has a diversification step.** Arroyo-Machado in
particular has no evaluation at all. So the multi-profile idea is no longer novel — but
*evaluated* multi-lens combination is unclaimed, and the specific operators are ours
(§4).

### Eligibility is genuinely unstudied in this domain

No funding paper extracts, represents, or reasons over eligibility. The relevant machinery
lives elsewhere:

- **Constraint-based recommenders**: Felfernig & Burke, ICEC 2008 (DOI 10.1145/1409540.1409544)
  — a funding call *is* a constraint set; this is the canonical framing our
  `_stage_gate` / `_constraint_gates` should cite.
- **Rank-then-filter is provably suboptimal**: arXiv:2202.07088 makes exactly this argument
  for live recommendation with per-account eligibility.
- **De-conflating preference from qualification**: Kan et al., arXiv:2602.03097 (Feb 2026,
  USC). Names our exact pathology — "recruitment-funnel censoring" — and proposes decoupled
  preference/qualification experts with Lagrangian constraint optimization. **The single
  most transferable paper to our fellowship layer.**
- **Filtered ANN**: funding eligibility is a *highly selective conjunctive* predicate
  (citizenship ∧ stage ∧ institution type ∧ deadline), the regime where post-filtering is
  worst. See arXiv:2602.10258 (JAG), arXiv:2602.11443, arXiv:2510.27141 (Compass).
- **Upstream gap**: extracting structured eligibility from free-text NOFOs is unstudied.
  The mature analogue is **clinical trial eligibility parsing** (EliIE, JAMIA 2017;
  PMC11251129; arXiv:2307.00381) — chunk → NER/concept map → relation extraction →
  temporal constraints → negation. That pipeline transfers almost directly to
  `apps/scraper/eligibility/constraints.py`, which currently does it ad hoc.

### Datasets that fix W10

| Source | License | Award→PI | Award→pub | Note |
|---|---|---|---|---|
| Grants.gov XML Extract | Public | n/a | n/a | **Only large public source with a structured eligibility field** (`Eligible Applicants`) — but org-type only, no citizenship/stage |
| NIH RePORTER/ExPORTER | Public domain | Yes | Yes | ⚠️ NIH states publications **cannot be attributed to a project year** — irreducible leakage channel |
| NSF Award Search | Public domain | Yes (+emails) | Weak (via NSF-PAR) | XML→JSON Jan 2025 |
| CORDIS | **CC-BY 4.0** | ERC projects only | Yes | Best-licensed; org-level not PI-level |
| UKRI Gateway to Research | OGL | Yes | Yes (Researchfish) | |
| **arXiv:2603.26426** (UK funding lifecycle) | released | Yes | Yes | **The only public dataset with unsuccessful applications.** Opportunity → proposal → panel decision → project → outcome |
| **FIND** (arXiv:2510.10336) | released | Yes | 42.7% of 525,927 NSF awards | 12.4M scored (proposal, finding) pairs |
| **NIH-MPINet** (arXiv:2604.22802) | released | 30,127 PIs, 86,743 R01s | — | Multi-PI network, funded only |

**Recommendation for W10:** Grants.gov XML Extract + CORDIS gives a CC-BY/public
redistributable opportunity corpus with a real eligibility field. arXiv:2603.26426 is the
only path to an *applied* rather than *won* label, and it should be checked for completeness
and license before being made load-bearing.

---

## 2. Conferences and venues — a mature field with soft foundations

The only dedicated systematic review (Dehdarirad et al., *DTA* 54(2), 2020) covers 32 papers
through Aug 2018 and reports 24/32 offline-only evaluation, DBLP as the dominant dataset.
**No venue-recommendation survey exists covering 2019–2026.**

Method families and their exemplars: content-based (Medvet ICTAI 2014; Pubmender JMIR 2019;
de Campos IEEE Access 2022 — *venue profiles via clustering*), co-author/social (PAVE, JNCA
2018; Alhoori & Furuta JOI 2017), graph (CNAVER/HASVRec, KBS 2020; GraphConfRec, JCDL 2021,
recall@10 0.580), LLM (**exactly one**: TEEVRec, ICIC 2026).

Six findings that bear on us:

1. **A hard ceiling on content-only venue matching.** arXiv:2506.08199 (2025): across ~60k CS
   documents and nine venues, some venues are *indistinguishable* from their SPECTER
   embedding distributions alone, and several venue pairs are **converging over time**.
   Content-only conference recommendation has a tightening ceiling — this is a direct
   argument for the signals we already have (eligibility, deadlines, member fit) and against
   pushing the embedding harder.
2. **Deadline modelling is essentially nonexistent.** The only mechanism in the literature is
   Iana et al. (SEMANTiCS 2019) linking SciGraph history to WikiCFP so that *upcoming*
   conferences can be recommended. No paper treats a deadline as a constraint or an
   optimization variable, and none models the resubmission cascade. Our
   `apps/content/opportunities.py` already carries deadlines; nobody has published on it.
3. **Acceptance probability is modelled — but never inside a recommender.** A paper-acceptance
   prediction literature exists (WWW '21 Companion, DOI 10.1145/3442442.3451370). No one has
   composed P(accept | paper, venue) × value(venue) into an expected-value ranking.
4. **Popularity/long-tail bias in venue recommenders is literally unmeasured.** Zero papers.
   Given that venue volume is extremely skewed (megajournals vs. specialist venues), an
   accuracy-optimal model can win by memorizing venue priors. Pradhan et al.'s "average venue
   quality" and "stability" are the only gestures beyond accuracy.
5. **"Observed venue ≠ relevance" is an unwritten critique.** The published venue is a *choice
   under constraints* — prestige-seeking, deadline pressure, prior rejections invisible in the
   data. The parallel critique is well developed in citation recommendation (Kreutz &
   Schenkel, IJDL 2022) and has never been stated for venues.
6. **Commercial venue tools are unevaluable.** Entrup et al., TPDL 2023 — the definitive
   statement. Elsevier Journal Finder is BM25; JANE is Lucene MoreLikeThis; everything else is
   undisclosed. **B!SON** (TIB Hannover, DOAJ + OpenCitations, open source/data/API) is the
   only fully open counterexample and the right baseline to cite.

Datasets: DBLP/AMiner is the workhorse. **S2ORC/S2AG and OpenAlex are used by nobody as a
venue-rec benchmark** despite being the obvious modern choices — and OpenAlex is our corpus.
`ogbn-mag` frames venue prediction as 349-class node classification with a leaderboard; the
venue-rec literature does not use it. No canonical WikiCFP corpus exists — every group
re-crawls.

---

## 3. Knowledge graphs and teaming — the thinnest, most claimable ground

### The four systems that exist

1. **ULTRA** (Srivastava et al., arXiv:2201.05646; ACM 2023; *AI Magazine* 2024) — the only
   deployed, human-evaluated system for exactly this. NSF RFP scrape (1,797 RFPs) + faculty
   pages, **SPECTER** matching, greedy team assembly under three hand-elicited constraints.
   Methods ladder random → string → ACM CCS taxonomy → **relational boosted contextual
   bandits**; goodness = weighted mean of redundancy(−), set size(−), coverage(+),
   **k-robustness(+)** [Okimoto 2015]. USC 0.0879 → 0.5295; replicated at IIT-Roorkee
   0.0896 → 0.5835. IRB study, 212 responses, 90.09% relevant / 97.64% useful.
   **What is not evaluated: the teams.** The authors flag the reason — the success signal
   arrives months-to-years later.
2. **Rosati, Laurenzi & Quadrini** (Springer CCIS 2787, 2026) — Agentic Graph RAG over a
   CORDIS + OpenAlex KG for Horizon Europe consortium formation. Master's-derived; evaluated
   on **RAG quality, not consortium outcome**; recommends collaborators, not a constrained
   consortium.
3. **Król et al.**, ACIIDS 2022 — deep entity embeddings of CORDIS organisations. Evaluated
   with coverage/Gini/entropy; **no outcome link**; does not condition on call topic.
4. **Jadhav, Masrouri & Qin, ResearchConnect**, *Advanced Intelligent Systems* 2026 — profiles
   → thematic clustering into teams → LLM proposes interdisciplinary topics. Evaluated against
   **250 NSF-funded project summaries**, testing whether recovered groupings match actual
   funded teams. That recovery protocol *is* OpeNTF's recall@k on DBLP, and nobody has
   connected the two.

### Data substrate

Only **OpenAlex** (CC0 snapshot; `awards` entity exposes `funder.ror`, `funder_award_id`,
`amount`, `lead_investigator.orcid`, `funded_outputs`; ~11.5M grants ingested under a Wellcome
project) and **OpenAIRE Graph v11.1.1** (CC-BY; DOI 10.5281/zenodo.20428976 —
3,909,902 projects, 14,803,875 ORCID-derived persons, `project_produces` 10.0M,
`project_hasParticipant` 5.55M, **`person_coAuthorship` 372.9M**) model funder → award → PI →
publication end to end. OpenAIRE v11 is the richest open substrate for this use case and is
the only one shipping both project↔person and weighted co-authorship edges.

Three systematic weak points to plan around:

- **award→publication is sparse everywhere** (10–43% recall). Treat funding history as sparse
  positive signal, never as a filter — filtering on "has a grant record" silently excludes
  most competent researchers, and disproportionately juniors.
- **award→PI is name-based**, not ORCID-based, in NSF/CORDIS/most national funders. Entity
  resolution is a required non-trivial stage.
- **Only the lead investigator is modelled.** Co-Is — precisely the disparate-background
  collaborators we want — are largely invisible in award metadata. **Co-authorship is the
  better capacity proxy.**

Operational: OpenAlex API is metered since ~Feb 2026 ($1/day free) and the free snapshot tier
is quarterly — **build on the snapshot, not the API**. Do not build on SciGraph (retired
2023), DataCite GraphQL (deprecating Jul 2027), or the Wikidata scholarly subgraph (split
May 2025, unstable).

### Method reality check

The classical KG-recsys line (KGAT, KGIN, RippleNet, PGPR) is **methodologically mature and
empirically contested**: arXiv:2501.10143 (2025) re-examines intent-aware models and finds
most fail to beat simple baselines, with preprocessing claims not matching the actual data.
KGUF (arXiv:2403.20095) shows a deliberately simple knowledge-aware recommender is
competitive. Reinforcing this from expert-finding: arXiv:2605.18752 (2026) reports **TF-IDF
beat SPECTER2** for reviewer identification, because precise technical vocabulary is more
discriminative than broad semantic clustering in specialised domains.

**This is the same shape as our own §5 result** (BM25 beats every fusion arm). It converts an
awkward negative into a *convergent* finding with independent corroboration in two adjacent
tasks. That is worth saying explicitly in the paper.

The live frontier is **KG-RAG with LLM re-ranking**, whose selling point is explanation
quality rather than accuracy — e.g. **X-KGRank** (arXiv:2608.01732, 2026): heterogeneous KG in
Neo4j → LightGCN embeddings → structural feature mining → candidate-specific path retrieval →
LLM re-rank. The retrieved paths *are* the justification, each an auditable removable edge
set. Given the ICC≈0 noise floor on award outcome, explanation quality is the right objective.

### The right formalism is not recsys — it is reviewer assignment

**Kobren, Saha & McCallum, *Paper Matching with Local Fairness Constraints*, KDD 2019
(arXiv:1905.11924)** — FairIR/FairFlow. Two named failure modes: the assigned *group* lacks
collective expertise, and workloads skew. This is "does this set of people cover the required
expertise subject to load and conflict constraints" solved as constrained flow. **Start here,
not from KGAT.** Also: Charlin & Zemel's Toronto Paper Matching System (ICML 2013 workshop)
on suitability elicitation cost — you cannot ask 3,000 researchers to rate 291 calls, which is
the same bottleneck as our W5.

Warning from the same field: **MERIT** (arXiv:2605.27865, 2026) finds general-purpose LLMs
"remain unreliable for assessing reviewer suitability, tending to produce broad judgments of
**topical relevance** rather than evaluating **expertise** along individual dimensions." That
is a direct, pre-registered threat to our C-004 LLM percent-match claim and to any LLM-based
expertise scoring in a teaming layer.

### Team formation

Two disjoint literatures. **Subgraph optimization**: Lappas, Liu & Terzi (KDD 2009) — cover
required skills while minimizing communication cost (diameter or MST), both NP-hard; then
workload balancing (WWW 2012), top-k (CIKM 2011), personnel cost (SDM 2013), densest-subgraph
(FORTE, WWW 2013), submodular unification with **skill redundancy** (SDM 2014, 0.41-approx),
k-robustness (Okimoto 2015). Surveys: ACM CSUR 54(7) 2021; **Saeedi et al., ACM CSUR 2025
(DOI 10.1145/3737455)** is the current best entry point.

**Neural team formation / OpeNTF** (github.com/fani-lab/OpeNTF, CC BY-NC-SA, v0.2.0.0 Nov
2025). Formulation: sparse skill vector in → distribution over experts out, multi-label
classification. Models: `fnn`, **`bnn`** (variational Bayesian, TOIS 42(1) 2023), `nmt`
(seq2seq, SIGIR 2025), `gnn` (expert↔team link prediction). **Streaming/temporal training**
sorted by interval with test on the last `step_ahead` intervals — this is the temporal-split
discipline our own eval needs. Metrics via `pytrec_eval`: P@k, recall@k, ndcg_cut@k, map_cut@k,
success@k, **skill_coverage@k**, plus fairness (ndkl@k, skew@k); per-instance results retained
for **paired significance tests**. Datasets shipped: **DBLP, IMDB, USPTO, GitHub — and no
grant or funding domain.**

Most relevant single paper: **Zhang, Rad, Zihayat & Bagheri, *Say the Task, Build the Team:
Prompt-Based Team Formation*, ASONAM 2025** — fine-tunes T5-Large to map a **free-text project
description → expert team**, on the argument that keyword matching cannot capture project
semantics. That is exactly the input modality a grant call has, evaluated on papers.

**Unexploited synthesis:** structural-hole spanning (Burt 1992/2004; Lou & Tang WWW 2013) has
**never been used as a term in a team-formation objective**. For an explicitly cross-disciplinary
team — "cover the skills *and* include a broker linking the sub-communities" — this is the
most obvious missing piece.

### Idea generation

**SciMuse** (Gu & Krenn, arXiv:2405.17044, MPI) is the closest published system to the second
half of the idea: evolving KG over 58M+ papers, concepts via RAKE, GPT-4 generation
personalized to a researcher's concept neighbourhood, **evaluated by 100+ Max Planck group
leaders ranking 4,000+ ideas**; less common concepts and semantic similarity predict interest,
>65% precision. Also **ResearchAgent** (NAACL 2025) — ideation over an academic graph refined
by human-preference-aligned ReviewingAgents; **DeepMind Co-Scientist** (*Nature* 2026) with
wet-lab-validated hypotheses.

Two cautions that must be cited together:
- Si, Yang & Hashimoto (ICLR 2025) found LLM ideas judged **more novel** by 79 expert
  reviewers — but their own sequel, **The Ideation-Execution Gap** (arXiv:2506.20803), had 43
  experts spend 100+ hours executing assigned ideas and found **LLM-idea scores dropped
  significantly more on every metric, closing the gap.** Citing the first without the second
  is now a reviewer trap.
- **LLM-as-judge fails for novelty**: arXiv:2606.12071, arXiv:2608.01666 ("Style Wins,
  Substance Loses"), arXiv:2607.28631. And arXiv:2607.25881 found both AI reviewers scored
  AI-written proposals ~1 point higher on 5 — clear self-preference bias.

---

## 4. What is actually unique in our stack

Stated precisely, against the above. Implementation references from
`web/backend/apps/content/`.

| Element | Ours | Nearest prior work | Verdict |
|---|---|---|---|
| Multiple profiles per researcher | Declared, named, user-editable clusters (`accounts/interests.py`, `intake/clusters.py`, `cluster-organizer.tsx`), `MAX_CLUSTERS=6` | Zhu 2023 (DPMM, **learned**); Arroyo-Machado 2026 (bibliometric slices, **derived**) | **Not novel, but ours are declared and editable** — no one has compared declared vs. learned lenses |
| Cluster max-pooling | `final_score = max` over per-cluster combined scores; `combine_clusters` in `fusion.py` | None found. Prior work concatenates, averages, or ranks per slice without recombining | **Novel operator, zero evidence (C-003)** |
| Breadth bonus | `mean(scores)·(1+β(n_matched−1))`, `DEFAULT_BETA=0.15`, breadth confined *within* a cluster | Softened CombMNZ. Untuned; documented as a placeholder | **Novel constraint (within-cluster), untuned (W6)** |
| Lens attribution | `cluster_id` = argmax cluster, surfaced as a UI badge; `bridge_cluster_ids` when ≥2 clear | None. Multi-profile papers do not attribute results back to a profile | **Genuinely unclaimed and cheap to evaluate** |
| Cross-lens bridging | `bridge_cluster_ids` — items clearing multiple lenses | Conceptually adjacent to structural holes / Uzzi atypicality; unimplemented anywhere in recsys | **The most interesting thing in the codebase** |
| Diversification | `cap_clusters` reserves each cluster's best item; `top_per_cluster` builds per-cluster slates | Standard MMR-style diversification exists; per-*declared-lens* quotas do not | Modest novelty |
| Eligibility gating | Deterministic `_stage_gate`/`_constraint_gates` before relevance; blend `0.65·embed + 0.35·rule`; tiers 1.0/0.55/0.35 | Felfernig constraint-based recsys; nothing in the funding domain | **Unclaimed in this domain (C-005)** |
| Item→member routing | `member_fit.py`, cosine floor ~0.35, top 3, LLM **remove-only** | RAP gold standard reports 36–43% misranking in hard cases | Adjacent work exists; ours is remove-only, which is defensible |

**The sharpest available framing of our contribution**, given that §5's headline is a negative
retrieval result: *lens attribution and cross-lens bridging are the only things in this system
that a single-profile baseline cannot produce at all.* Everything else is a scoring variant.
An evaluation that measures whether users find bridge items more valuable than single-lens
items is small, needs no award data, and tests the one thing nobody else has built.

---

## 5. The KG teaming hypothesis — what the evidence actually says

> **Correction (2026-08-06).** An earlier draft of this section claimed the teaming hypothesis
> was "contradicted by evidence," citing Bromham 2016 and Boudreau 2016. **That was wrong** and
> conflated two distinct constructs. Neither paper measures team disciplinary composition. The
> corrected reading is below; the interrogation is in
> [`interdisciplinarity-evidence.md`](interdisciplinarity-evidence.md).

**The construct that matters.** There are two different things called "interdisciplinary
research" and they behave differently:

- **Individual/proposal interdisciplinarity** — one project or one person spanning fields.
- **Team-level complementarity** — two or more *specialists*, each in their own lane, whose
  fields jointly cover what the call requires.

The hypothesis being tested here is the second. Almost all of the funding-penalty literature
measures the first.

### What the two commonly-cited papers do *not* say

- **Bromham, Dinnage & Hua, *Nature* 534:684, 2016.** IDD is computed **entirely from Field of
  Research codes the applicant ticks on the form**, plus their assigned percentage weights. No
  investigator publication histories, affiliations, or citation data enter it. The authors state
  the distinction themselves: *"IDD reflects the interdisciplinarity of the project, **not the
  inclusion of practitioners from different disciplines**, because a single researcher can devise
  a project that spans different disciplinary traditions."* Their measure is phylogenetic species
  evenness over the FoR hierarchy (balance + disparity), not Rao–Stirling. Effect: slope −0.40 on
  the logit, P = 1.1×10⁻¹¹, n = 18,476, ≈20.5% → 14.7% success across the IDD range.
  **Critically, they did control for team size and it went the other way:** *"proposals with more
  chief investigators have slightly higher success rates (slope = 0.03, P = 0.003), across all
  research fields"*, and team size is nearly orthogonal to IDD (Spearman ρ = 0.09). The authors
  are agnostic on cause and explicitly float lower average proposal quality as an alternative to
  reviewer bias. No formal replication failure or Matters Arising found.
- **Boudreau et al., *Management Science* 62(10), 2016.** Entirely about **evaluator–proposal**
  intellectual distance. Team composition is not a variable. And the distance finding runs
  backwards from how it is usually invoked: evaluators scored proposals **closer** to their own
  expertise *lower*. Only the novelty penalty is a headwind, and novelty ≠ team composition.

### The paper that is actually on point — and cuts both ways

**Banal-Estañol, Macho-Stadler & Pérez-Castrillo, *Evaluation in research funding agencies: Are
structurally diverse teams biased against?*, Research Policy 48(7):1823–1840, 2019.** 17,835
EPSRC applications 1996–2007, 3,786 academics, 40 UK engineering departments. Award rate 34%,
mean team size 2.5. Field diversity measured **from each member's own prior 5-year publication
record**, and they construct almost exactly this system's target variable — `num additional
fields`, the count of fields the team publishes in that the PI does not — with the illustrating
example: *"a two-member team in which the PI has only published in field A whereas the other team
member has only published in field B... should have no individual-level diversity because it is
composed of two specialists, whereas it exhibits team-level diversity."*

Three findings, in order of importance here:

1. **Funding penalty (the real, narrow threat).** `num additional fields`, Blau index over team
   fields, and research-type variation are all **negative and significant** on award probability.
   Team size also reduces award probability.
2. **Impact benefit (the value proposition).** `num additional fields` has a **significant
   positive effect** on ex-post success (top-25% normalized citations). *Individual*-level
   interdisciplinarity (within-person Blau/Shannon) is penalized ex-ante and is **not**
   significant ex-post. This is the two-specialists-vs-one-generalist distinction, tested, and it
   favours the team framing.
3. **The penalty is offsettable.** *"the prestige of the PI has a strong positive effect in
   mitigating the negative impact of diversity... the sum of the coefficient of the interaction
   term and the main effect is often close to zero, indicating that the negative effect of
   diversity is not only mitigated but offset if the team is led by a prestigious PI."* They also
   find **no** effect of demographic diversity on either award or ex-post success.

Caveats: UK engineering only, 1996–2007, PI-prestige proxied by full professorship, small ex-post
sample (963 publications from 1,493 grants), and the authors note they cannot separate project
novelty from team diversity — so part of the funding penalty may be a novelty penalty.

### Supporting evidence for the team framing

- **Lin, Frey & Wu, *Expertise diversity of teams predicts originality and long-term impact in
  science and technology*, arXiv:2210.04422.** Measures **expertise distance between team members
  from their prior career histories** — the exact variable — across 23M papers and 4M patents.
  Expertise-diverse teams produce work with greater originality; no advantage at 2 or 5 years,
  **substantially higher impact at 10 years**. Effect strongest when other diversity dimensions
  are absent (same institution/country). Abstract verified only.
- **Uzzi et al., *Science* 342:468, 2013.** 17.9M articles. Highest-impact work is **high
  conventionality plus a tail of high atypicality** (~2× likelihood of top-5% citation), and
  **teams are 37.7% more likely than solo authors to insert novel combinations**.
- **Xiang, Romero & Teplitskiy, *PNAS* 122(16), 2025.** 128,950 manuscripts (not teams).
  **Knowledge-base** interdisciplinarity (from references) → 1 SD ≈ +0.9pp acceptance; **topic**
  interdisciplinarity (from title/abstract) → 1 SD ≈ −1.2pp. High-topic-ID submissions do **not**
  fare worse if knowledge-base ID is also high. Analogically supportive — breadth of inputs helps,
  framing is what gets punished — but do not represent it as team-level evidence.
- **Seeber et al., *Research Evaluation* 2025** — COST, deliberately panel-free: 1,928 proposals,
  5,330 evaluations, 3,050 reviewers. Effect of interdisciplinarity **negligible and
  non-significant**, suggesting the penalty is a property of disciplinary-panel architecture.
- **Sun, Livan, Ma & Latora, *Communications Physics* 4:263, 2021** — 44,419 UK research-council
  grants; interdisciplinary researchers underperform early and **eventually outperform on funding
  volume and value**. Career-level unit, so survivorship risk.

### What Wanzenböck 2020 does and does not contain

Verified by full-text check: **there is no disciplinary-diversity variable in the paper at all** —
no Blau/Shannon/HHI over partner fields, no cognitive distance. Multidisciplinarity appears only
rhetorically. What consortium composition *did* predict (7,208 H2020 proposals, McFadden R² ≈
0.09): **consortium size positive and highly significant**; coordinator FP7 experience strongly
positive; top-50 universities positive; share of universities **negative** while firms and
research organisations are positive; CEE partners strongly negative; prior acquaintance
significantly **negative** on expert score. Net: neutral-to-favourable — sector heterogeneity and
larger consortia are rewarded, and the paper simply has nothing to say about disciplinary mix.

### One shape constraint that does survive

**Do not maximize distance.** Nooteboom et al. (*Research Policy* 36(7), 2007) confirm an
inverted-U between cognitive distance and innovative performance in firm alliances, with the
optimum shifting outward for exploratory work (firm-level data; transfer to academic teams is an
inference). Yegros-Yegros et al. (PLoS ONE 2015) find the same shape for citations. Uzzi's
conventional-core-plus-atypical-tail is the same message. **There is an interior optimum.**

### Equity, unchanged

Ginther et al. (*Science* 2011) — Black NIH applicants 10pp less likely funded after full
controls; Hoppe et al. (*Science Advances* 2019) — topic choice alone accounts for >20% of the
gap. Combined with Wanzenböck's incumbency findings, **any teaming model trained on realised
funded teams encodes incumbency directly, and none of the four systems in §3 mentions this.**
Note that Banal-Estañol found **no** demographic-diversity effect either way, so this is a
training-data problem, not a composition finding.

### Defensible statement of the hypothesis

> Assembling complementary specialists — two researchers in different fields whose combined
> coverage matches a call — is supported as a route to **higher-impact research**
> (Banal-Estañol 2019 on citations; Lin et al. on 10-year impact; Uzzi 2013 on atypical
> combinations). It is *not* supported as a route to higher **award probability**: the one study
> that measures team-level field complementarity directly finds it **reduces** funding odds
> (Banal-Estañol 2019), while noting the effect is **fully offset under a prestigious PI**, and
> characterising it as evaluator bias rather than quality deficit. Distance should target an
> interior optimum, not a maximum (Nooteboom 2007). Given ICC ≈ 0 among NIH reviewers
> (Pier 2018), award probability is in any case a near-noise target; **optimize for
> justifiable, well-covered teams and report incumbency concentration**, not for predicted
> award.

Two design implications follow directly, both actionable:

1. **Anchor teams under a senior/prestigious PI where possible.** Banal-Estañol's interaction
   term says this is not cosmetic — it is the difference between a penalty and no penalty.
2. **Help with framing, not just assembly.** Xiang 2025 locates the penalty in how the *topic* is
   framed rather than in the underlying knowledge breadth. A system that assembles a broad team
   and then helps frame the proposal within a recognisable disciplinary home may capture the
   upside without the evaluation cost. (Inference across constructs, not a verified finding —
   but a cheap, testable one.)

---

## 6. Gaps worth claiming, ranked by (claimability × fit to our stack × cost)

**Tier 1 — cheap, needs nobody, uses data we have**

1. **A grant/funding domain for OpeNTF.** OpeNTF's dataset enum is closed at DBLP/IMDB/USPTO/
   GitHub. A `cmn.grant.Grant` domain (award = team, PI+co-PIs = members, program element/MeSH
   = skills, IC/directorate = location) fits the existing OO hierarchy exactly. NIH-MPINet
   (30,127 PIs, 86,743 R01s) and FIND (525,927 NSF awards, 42.7% publication-linked) are
   already released. **This is a resource paper with a maintained benchmark library as the
   distribution channel, and the two literatures do not currently cite each other.**
2. **The venue-side critique paper we can write from §5 data.** "The observed venue is a choice
   under constraints, not a relevance label" is unwritten for venues, well developed for
   citations. Combine with the fact that popularity/long-tail bias in venue recommenders is
   **literally unmeasured** — we can run coverage/Gini/long-tail metrics on our existing runs
   in days.
3. **Declared vs. learned lenses.** Zhu (DPMM) and Arroyo-Machado (bibliometric slices) both
   derive profiles; ours are declared. A three-arm comparison (single profile / learned
   clusters / declared clusters) on the same corpus needs no annotators for retrieval-style
   proxies and directly tests C-003.
4. **Lens attribution and bridging as an evaluated construct.** No prior work attributes a
   recommendation back to a profile or flags cross-profile items. Smallest possible user study.

**Tier 2 — needs modest new data, high novelty**

5. **EU consortium link prediction.** "Given topic T and partial consortium C, predict the next
   partner", temporal held-out. CORDIS is CC-BY and complete (35,386 H2020 + 8,442 HE
   projects, `organization` join with role/country/activity type). **Firm negative finding
   from the survey: nobody has done this.** The Commission holds the richest
   call→consortium→output graph in the world and exposes it through a search box.
6. **Structural-hole spanning as a team-formation objective term.** Two disconnected
   literatures; the synthesis is obvious and unclaimed, and it is the formal version of our
   `bridge_cluster_ids` idea.
7. **Structured requirement extraction from call text.** Every system reduces "required
   expertise" to a bag of embeddings. Horizon Europe topic texts explicitly state required
   disciplines, TRL, mandatory partner types, country-diversity minima, mandatory roles — all
   machine-extractable. Pair with the clinical-trial criteria pipeline for eligibility. This
   serves *both* Path A and the teaming route.
8. **Fellowship eligibility as a first-class ranking constraint**, with the Kan et al.
   preference/qualification decoupling and in-filtered ANN. Nothing exists in this domain at
   all.

**Tier 3 — high value, gated on data we do not control**

9. Expected-value venue ranking: P(accept) × value(venue). Both components exist; never composed.
10. Anything that needs the negative class (applied-but-rejected). Gated on arXiv:2603.26426
    for the UK, or on privileged access elsewhere.

---

## 7. Concrete recommendations

**On paper strategy.** The survey strengthens the split recommended earlier, and sharpens the
short paper. Our §5 headline (BM25 beats every fusion arm) now has two independent
corroborations in adjacent scholarly-matching tasks — TF-IDF > SPECTER2 for reviewer
identification (arXiv:2605.18752) and the intent-aware KG-recsys reproducibility failure
(arXiv:2501.10143). Reframe §5 from "our stack loses" to **"lexical baselines are
underestimated across scholarly matching tasks; here is a third measurement, with artifacts."**
That is a reproducibility-track paper with a thesis rather than an apology.

**On the KG route.** Build it, but as an **explanation and coverage** system, not an
award-prediction system:
- Backbone: OpenAlex CC0 snapshot ⋈ OpenAIRE Graph v11.1.1 CC-BY dump, joined on DOI/ROR/ORCID.
- Repair thin award→publication edges with NIH RePORTER, FIND, UKRI GtR, CORDIS.
- Assembly: constrained flow in the FairIR/FairFlow tradition with ULTRA's goodness metric
  (coverage, redundancy, set size, k-robustness) — the only objective validated with real users.
- Explanation: KG path retrieval, X-KGRank style. Each path is an auditable, removable edge set.
- Baseline discipline: co-authorship-weighted personalized PageRank, BM25, and SPECTER2-NN
  must be beaten with tuned hyperparameters before a KG-GNN earns its complexity. Given our own
  §5 result, assume they will be hard to beat.
- Report incumbency/prestige concentration as a first-class metric. Nobody does; it is the
  ethical and the novel move simultaneously.

**On evaluation hygiene.** Three items from the survey that apply to work already in flight:
- **Temporal splitting.** Ji et al. (*TOIS* 41(3), 2023) find 53.7% of recent recsys papers use
  random splits, and — the part that matters — **relative model rankings become unpredictable**
  under leakage. RecSys 2025 (DOI 10.1145/3705328.3759329) quantifies 21.7–73.4% nDCG@10 drops.
  Funding calls are near-duplicated year to year (reissued NIH PAs, reopened Horizon topics), so
  a random split is close to guaranteed leakage. **De-duplicate reissued calls across the split
  boundary explicitly.** OpeNTF's streaming trainer is a working reference implementation.
- **Per-query scores and paired significance tests** — OpeNTF retains per-instance results for
  exactly this. Our `eval/harness/scoring.py` currently calls `calc_aggregate` only.
- **Beyond-accuracy metrics.** Absent from neural TF evaluation entirely, absent from venue
  recommendation entirely, standard in RecSys since Kaminskas & Bridge (*TiiS* 7(1), 2016).
  Cheap for us, and unclaimed in both adjacent fields.

**Immediate next step.** Before committing to the KG route, decide which of the two claimable
resource contributions to anchor on — the **OpeNTF grant domain** (§6.1) or **CORDIS consortium
link prediction** (§6.5). Both are open-data, need no annotators, and have explicit negative
findings in the survey confirming nobody has done them. Both would give the KG work a
publishable spine independent of whether the teaming system itself performs.
