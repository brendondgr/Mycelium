# Grant & Fellowship Recommendation — Survey

Compiled 2026-08-06. Raw survey; synthesis and Mycelium-specific implications in
[`SYNTHESIS.md`](SYNTHESIS.md).

**Headline:** genuinely thin literature. ~6 peer-reviewed methods papers on
researcher→funding-call matching, 2018–2026, with **zero shared benchmarks, zero public
splits, zero standard metrics**. Every paper builds its own ground truth from a different
agency; most use "was funded by X" as the positive label. The commercial systems that
dominate actual use have **published no method at all**. Eligibility-as-first-class-ranking-
constraint is, in the funding domain, **unstudied**.

---

## 1. Methods papers

| Work | Year / Venue | Data | Method | Result |
|---|---|---|---|---|
| *A Recommendation System of Grants to Acquire External Funds*, arXiv:1807.03493 | 2018, preprint | KAKEN keywords | Association-rule mining; ranks *researchers* per grant | — |
| Zeng & Acuna, **GotFunding**, *Proc. ASIS&T* 57(1):e323 (arXiv:2405.12840) | 2020 | NIH grant–publication records | Random-Forest learning-to-rank, 4 features incl. title/abstract similarity and publication–grant year gap | nDCG@1 = 0.945; AUC ≈ 0.9 vs LSA and Lucene BM25 |
| Zhu, Patra, Wu & Yaseen, *A novel NIH research grant recommender using BERT*, **PLOS ONE** 18(1):e0278636 | 2023 | NIH announcements + researcher publications; grant citations in papers as ground truth | BERT binary classifier over (publication, announcement) pairs; **DPMM clustering of a researcher's publications** + recency weighting for aggregation | Beats BM25, TF-IDF, doc2vec, Naïve Bayes on Recall@k, P@k, MRR, ROC-AUC; plus researcher-rated P@k |
| Han, Richie, Shi & Tsui, *Automated Matchmaking of Researcher Biosketches and Funder RFPs Using DNNs*, **IEEE Access** 12:98096, DOI 10.1109/ACCESS.2024.3427631 | 2024 | 12,991 NIH biosketches (one institution) + 2,234 NIH RFPs, 2014–2019 | Four DNN variants; best = BERT cross-encoder + post-BERT BiLSTM + back-translation ("BC2BT") | F1 = 71.15% |
| Arroyo-Machado et al., *Matching Researchers to Funding Calls: A Reproducible Institution-Level Framework*, arXiv:2604.06321 | 2026-04 | 3,013 Univ. of Granada researchers × 291 Horizon Europe topics | **Multiple bibliometric-slice profiles per researcher** (first-author set, recent-window set…), each embedded separately, cosine-matched to calls; within-researcher normalisation + percentile ranking | Four complementary indicators; **no relevance ground truth, no accuracy metric** |

Two notes on the Granada paper: it explicitly states *"Grant recommendation systems remain one
of the least explored areas within academic recommender systems, and existing proposals are
typically tied to specific funding agencies or disciplinary domains"* — independent
confirmation of the thinness; and it is the only work abandoning the single aggregated
researcher profile, which is a real modelling contribution, undermined by having no evaluation.

### System / grey literature

**Research Highlighter-MatchMaker** (Huang & Li, Office of Strategic Initiatives, University at
Albany SUNY, 2024; par.nsf.gov/servlets/purl/10566919). Deployed institutional system.
11,357 Scopus abstracts for 711 researchers + 3,628 internal proposal abstracts + 1,901 SPIN
opportunities via API. Method deliberately simple: BERTopic-style topic modelling plus
**exact-string keyword match** against SPIN's hierarchical taxonomy, scored as
`(authorship-position weight) × (match count) × (matched docs / total docs)` with first-author
publications weighted 100 vs 50/25. Pilot: 684 weekly emails to 656 researchers covering
1,107 opportunities, Jul 2023–Feb 2024. Feedback reported qualitatively and is **bimodal**
("Dead on!" vs "had nothing to do with my research"), no P@k. The most honest published
account of what a deployed university system actually looks like — and it is a slide deck.

### Absent
- **Horizon Europe call recommendation**: only arXiv:2604.06321. No EU-funded published
  recommender, no CORDIS-based benchmark; the Funding & Tenders Portal offers filtering.
- **Two-sided / reciprocal matching** (funder side, portfolio balance, call capacity):
  nothing found. All published work is one-sided content matching.

---

## 2. Fellowships and scholarships

Substantially thinner and lower quality; student-facing, and the two literatures do not cite
each other.

- *Scholarspot: Scholarship Recommendation System using Machine Learning*, IEEE 2024
  (Xplore doc 10775136). Profile/achievement matching. Minor venue, no public data.
- `idrisso4/Scholarship-Recommendation-System` (GitHub, undated) — KMeans/DBSCAN/agglomerative/
  spectral clustering over student profiles. Not peer-reviewed; listed as representative of the
  level of the field.
- Adjacent and better: *Seminar and Training Programs Recommender System for Faculty Members of
  Higher Education Institution*, arXiv:2012.01167 (2020) — closest published analogue to
  career-stage-aware opportunity recommendation for academics.

**This area is essentially empty.** No peer-reviewed work on postdoctoral fellowship
recommendation, no K-award / ERC Starting Grant / MSCA matching, and nothing treating
citizenship, residency, or years-since-PhD — the defining constraints of fellowships — as a
modelling problem.

---

## 3. Commercial systems

**None have a published method.** Everything below is vendor copy or product documentation;
treat mechanism claims as assertion.

- **Pivot-RP** (Clarivate). Auto-generated, user-claimable researcher profiles; "AI-powered
  Funding Advisor"; semantic search added recently. Filters: sponsor, sponsor type, deadline,
  amount, **career stage**, discipline. ~5M awarded-grant records alongside live opportunities.
  No algorithm disclosure. *Inference: profile-text → opportunity-text embedding or weighted
  keyword retrieval over a curated taxonomy; the curation is the moat.*
- **GrantForward** (originated at UIUC). Uses "research interests, publications, and other
  profile information"; ~30,000 sponsors. Despite academic origins, **no paper** describes its
  ranking.
- **InfoEd SPIN / SMARTS**. ~40,000 opportunities. Explicitly **not** an ML recommender: Boolean
  query builder, hierarchical keyword taxonomy, filters on sponsor type and **eligibility**,
  saved-search alerting. Exposes an API and per-opportunity keyword tags — which is what made
  the UAlbany third-party recommender possible. Best-documented data model of the set.
- **Elsevier Funding Institutional**. 45,000+ opportunities from 15,000+ funders, 9M+ awarded
  grants. Search by ASJC classification, Boolean keywords, or by publication-history profile
  (Scopus linkage the obvious inference). No published method.
- **Research Professional** (Clarivate). **No technical documentation found at all.**
- **Dimensions** (Digital Science). Not primarily a recommender — the underlying linked-data
  asset: 7M+ grants linked to 144M+ publications, patents, trials, policy documents. Most
  useful of the commercial set for *building* a recommender.
- **Cayuse Funding Advisor**. Opportunity↔scholar-profile matching, weekly digest. No method.
- **Atom Grants**. The only vendor *claiming* explicit eligibility reasoning: "parses each RFP
  and checks each researcher's profile against every requirement including career stage,
  institution type, **citizenship**, prior funding history, and mechanism limits." Unverified.
- **ScientifyRESEARCH**. Open/curated funding database with eligibility filters. Has the only
  vendor-adjacent peer-reviewed artefact: *ScientifyRESEARCH: An equalizer for research
  funding*, **Information Services & Use** (2023), DOI 10.3233/ISU-230190 — positioning, not
  methods.
- **NIH RePORTER Matchmaker** — free, first-party, de facto baseline. Paste ≤15,000 characters;
  NLP over term/concept frequency returns the 500 most similar **funded projects** with a match
  score. Method described only as "analyzes terms and concepts" — *inference: TF-IDF/BM25-class
  weighting, not neural.* Critically, it recommends past awards, not open opportunities; users
  translate manually.

---

## 4. Eligibility-constrained recommendation

The funding literature does not address this. Transferable work:

**Foundational**
- Felfernig & Burke, *Constraint-based recommender systems: technologies and research issues*,
  **ICEC 2008**, DOI 10.1145/1409540.1409544. Weighted hard and soft constraints against item
  features; return items satisfying the maximal weighted constraint set. A funding call *is* a
  constraint set.
- Felfernig, Friedrich, Jannach & Zanker, *Developing Constraint-based Recommenders*,
  *Recommender Systems Handbook* — the standard reference chapter.

**Ranking under constraints**
- *Scaling up Ranking under Constraints for Live Recommendations by Replacing Optimization with
  Prediction*, arXiv:2202.07088 (2022). Makes the key point: when not every account is eligible
  for every item, rank-then-filter downstream is sub-optimal; they learn a predictor of the
  constrained-optimization solution to make it serveable.
- **Kan, Yang, Nguyen, Yi, Yi, Yu & Liu (USC), *De-conflating Preference and Qualification:
  Constrained Dual-Perspective Reasoning for Job Recommendation with LLMs*, arXiv:2602.03097,
  Feb 2026.** *The most transferable paper in this section.* Argues that collapsing candidate
  *preference* and employer *qualification* into one interaction signal yields confounded
  supervision under **"recruitment-funnel censoring"** — exactly the funding pathology where
  only awards are observed, not applications or eligibility screening. JobRec: unified semantic
  alignment schema, two-stage cooperative training of decoupled preference/qualification
  experts, **Lagrangian-based policy alignment under explicit eligibility requirements** with
  controllable trade-offs. Preprint.
- *Fairness in Job Recommendation under Quantity Constraints*, **AAAI 2023** — capacity rather
  than eligibility, relevant if call-level applicant capacity is modelled.
- *Fairness of recommender systems in the recruitment domain*, **Frontiers in Big Data** 6:1245198
  (2023) — citizenship/nationality are legally protected in some jurisdictions and legitimate
  hard filters in others.

**Filtered retrieval (systems level)**
Pre-filter (restrict then ANN; collapses as the filtered set grows), post-filter (ANN then
discard; fails when valid items are sparse or far in embedding space), in-filter (predicate
during graph traversal; best at moderate selectivity). Recent: **JAG** (arXiv:2602.10258),
*Filtered ANN Search in Vector Databases* (arXiv:2602.11443), **PipeANN-Filter**
(arXiv:2605.17992), **Compass** (arXiv:2510.27141). Funding eligibility is a *highly selective
conjunctive* predicate — the regime where post-filtering is worst.

**The upstream gap.** None of this helps unless eligibility is machine-readable, and
**extracting structured eligibility from free-text NOFOs is unstudied** — searches returned
nothing. The mature analogue is **clinical trial eligibility criteria parsing**: scoping review
(*Drug Discovery Today* 2024, S1359644624002642), **EliIE** (JAMIA 2017), *Parsing Clinical
Trial Eligibility Criteria for Cohort Query by a Multi-Input Multi-Output Sequence Labeling
Model* (PMC11251129, 2024), *Effective Matching of Patients to Clinical Trials using Entity
Extraction and Neural Re-ranking* (arXiv:2307.00381). Canonical pipeline — sentence chunking →
NER/concept mapping → relation extraction → temporal constraint detection → negation detection
— transfers almost directly. **Clearest open opportunity in the area.**

---

## 5. Datasets

| Dataset | Contents | License | Award→PI | Award→pubs | Benchmark? |
|---|---|---|---|---|---|
| **NIH RePORTER / ExPORTER** | Project abstracts, amounts, PI names, institution, activity code, FY, patents; weekly updates; bulk per-FY files | US federal public data, no auth | **Yes** | **Yes** (PubMed) — but NIH warns publications **cannot be attributed to a project year**, a direct temporal-split hazard | **No public benchmark.** GotFunding and Zhu et al. both built private ground truths; neither released splits |
| **NSF Award Search** | 500k+ awards from 1959 (abstracts from 1976); title, abstract, awardee, PI name/email, program officer, funds, directorate, CFDA, dates. **XML→JSON Jan 2025.** UI export capped 3,000 rows | Public domain | **Yes** (+emails) | Indirectly via NSF-PAR; join is not first-class | **No** |
| **Grants.gov XML Extract** | Daily full-database export, schema bundled. **Opportunity side, not award side.** Multi-valued Funding Instrument Type, Category, CFDA, and **Eligible Applicants** | Public, free | n/a | n/a | **No** — but the only large public source with a **structured eligibility field**. Coarse (org-type codes); citizenship and career stage live only in free-text NOFOs |
| **CORDIS** | Projects + participating organisations, legal basis, topics, URLs; IPRs; deliverables; **project publications**; report summaries; **PIs for ERC projects** | **CC-BY 4.0** — best-licensed of the set | **Partial** — org-level for most, named PIs only for ERC | **Yes**, dedicated sub-set | **No.** Cleaned dumps on Zenodo (13882123, 13765372); R package `KTH-Library/cordis` |
| **UKRI Gateway to Research** | ~170,000 projects from 2006; projects, funding, persons, organisations, ResearchFish outcomes | **Open Government Licence** | **Yes** | **Yes** | **Nearly** — see below |
| **Dimensions** | 7M+ grants ↔ 144M+ publications, patents, trials, datasets, policy docs. Broadest funder coverage | **Commercial** (free tier for publications; grants need licence) | Yes | Yes — core product | **No** |
| **OpenAIRE Graph** | Products linked to funders, projects, communities, organisations; ~480M relations; 10M+ OA full texts mined | **CC-BY**, free APIs | Variable | **Yes** | **No** |

### The one dataset that closes the loop
**Demystifying Funding: Reconstructing a Unified Dataset of the UK Funding Lifecycle**,
arXiv:2603.26426 (Mar 2026). Reconstructs GtR to link **funding opportunities → submitted
proposals → panel decisions → funded projects → outcomes**, integrating the GtR project
database, UKRI opportunity records, and competitive funding decision records across research
councils. **They release the database and code.**

As far as this survey found, **this is the only public dataset containing unsuccessful
applications alongside successful ones** — the only way to evaluate on *applied* rather than
*won*. Completeness and license not independently verified; do that before committing.

---

## 6. Evaluation practice and pitfalls

### Temporal leakage
- Ji, Sun, Zhang & Li, *A Critical Study on Data Leakage in Recommender System Offline
  Evaluation*, **ACM TOIS** 41(3), 2023 (arXiv:2010.11060). Of recent top-venue recsys papers:
  **53.7% random split, 28% leave-one-out, only 12.3% split-by-timepoint.** All evaluated models
  recommend items that did not yet exist at the test timepoint, and — the part that matters —
  **relative model rankings become unpredictable** as leaked future data varies. Leakage does
  not merely inflate numbers; it changes which method appears best.
- *Don't Get Ahead of Yourself: A Critical Study on Data Leakage in Offline Evaluation of
  Sequential Recommenders*, **RecSys 2025**, DOI 10.1145/3705328.3759329. Quantifies it:
  **sampled nDCG@10 drops 21.7–73.4%** moving from temporal leave-one-out to split-by-timepoint.

**Why this bites unusually hard for grants.** Funding calls are recurring and near-duplicated
year over year — the same NIH PA/PAR reissued, the same Horizon topic reopened. A random or
leave-one-out split places the FY2024 reissue in train and the FY2025 reissue in test, and any
text model matches them trivially. **Every published grant recommender is vulnerable and none
reports split-by-timepoint.** Additionally, NIH's own documentation states publications cannot
be attributed to a specific project year, so even a well-intentioned temporal split on RePORTER
has an irreducible leakage channel through the publication side. No grant recommender paper
acknowledges this.

### "Won ≠ applied"
Every published grant recommender uses *awards* as positive labels, conflating four events: the
researcher **knew about** the call, was **eligible**, **applied**, and **won**. Training on
awards teaches the model to predict *winning* — a different and more conservative objective than
recommending calls a researcher should consider.

- The censoring problem is formalised (in the job domain) as "recruitment-funnel censoring" in
  arXiv:2602.03097 — the sharpest available articulation of why preference and qualification
  must be modelled separately.
- **Unfunded applications are systematically unobservable.** Buck & Marcum, *Let Unfunded Grant
  Applications See the Light of Day*, **Issues in Science and Technology** — because unfunded
  proposals are never disclosed, there is no way to assess whether agencies support a range of
  ideas or a narrow one.
- **Funded ≠ better.** Danielle Li, *Expertise vs. Bias in Evaluation: Evidence from the NIH*,
  HBS WP 16-053 — funded researchers publish more *because* they were funded, so ex-post
  outcome comparison mistakes the treatment effect for proposal quality. Directly undermines
  "award = strong relevance label."
- Related: unfunded grants generate comparable near-term citations and publications to funded
  ones.

### Matthew effect / feedback loops
*The Matthew effect and early-career setbacks in research funding — a replication study*, RoRI
Working Paper No. 16 (eLife reviewed preprint). Early funding strongly predicts later funding —
but the mechanism is that **previously funded researchers apply more often**, not that reviewers
score them higher; committees did not give higher scores to previously funded applicants.
Initially rejected applicants who reapply achieve *higher* citation impact.

The implication is sharp and unaddressed in any funding-recsys paper: **if the Matthew effect
runs through application behaviour, a recommender that shapes application behaviour intervenes
directly on the causal channel.** Trained on awards and deployed to already-funded researchers,
it amplifies; surfacing eligible calls to unfunded and early-career researchers could attenuate.
Nobody has measured either.

Also: *Bias in Research Grant Evaluation Has Dire Consequences for Small Universities*, **PLOS
ONE** 11(6):e0155876 (2016); *Measuring bias, burden and conservatism in research funding
processes*, **F1000Research** 8:851 (2019).

### Benchmarking hygiene
Sun et al., *Are We Evaluating Rigorously?*, **RecSys 2020**, DOI 10.1145/3383313.3412489 —
85 papers across 8 venues, standardised toolkit released. **ORBIT: Open Recommendation Benchmark
for Reproducible Research with Hidden Tests**, arXiv:2510.26095 (2025) — hidden-test leaderboard,
12 models × 5 datasets. Neither covers grants; both are the template a grant benchmark needs.

---

## 7. Thin areas — explicit list

1. **Any shared benchmark for grant recommendation.** Zero. Five methods papers, five
   incompatible private ground truths.
2. **Eligibility as a modelled object.** No paper extracts, represents, or reasons over it.
3. **Fellowship/scholarship recommendation for researchers.** Effectively nonexistent, despite
   being the setting where hard constraints matter most.
4. **Any temporally-correct evaluation.** None reports split-by-timepoint, despite recurring
   near-duplicate calls making leakage near-certain.
5. **Modelling the application decision separately from the award.** Only arXiv:2603.26426 makes
   it possible; no method paper exploits it.
6. **Two-sided / reciprocal formulation.** Nothing models funder objectives, portfolio balance,
   or call capacity.
7. **Commercial method disclosure.** Nothing from Pivot-RP, GrantForward, Funding Institutional,
   or Research Professional.
8. **Cold start for early-career researchers.** The population that most needs recommendation has
   the thinnest profile. The Granada authorship-position slices and UAlbany's first-author-100 /
   other-25 weighting both actively *disadvantage* juniors.
9. **Non-English / Global South funding landscapes.** All work is NIH, NSF, Horizon, UKRI, KAKEN.

---

## Sources

[GotFunding (arXiv:2405.12840)](https://arxiv.org/html/2405.12840v1) ·
[KAKEN grants recommendation (arXiv:1807.03493)](https://arxiv.org/abs/1807.03493) ·
[NIH grant recommender using BERT — PLOS ONE](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0278636) ·
[Biosketch/RFP matchmaking — IEEE Access](https://ieeexplore.ieee.org/document/10597426/) ·
[Matching Researchers to Funding Calls (arXiv:2604.06321)](https://arxiv.org/abs/2604.06321) ·
[Demystifying Funding: UK Funding Lifecycle (arXiv:2603.26426)](https://arxiv.org/html/2603.26426) ·
[Research Highlighter-MatchMaker (NSF-PAR 10566919)](https://par.nsf.gov/servlets/purl/10566919) ·
[Scholarspot (IEEE)](https://ieeexplore.ieee.org/document/10775136/) ·
[Seminar and Training Programs Recommender (arXiv:2012.01167)](https://arxiv.org/pdf/2012.01167) ·
[Pivot-RP](https://clarivate.com/academia-government/scientific-and-academic-research/research-funding-analytics/pivot-rp-funding/) ·
[GrantForward](https://www.grantforward.com/index) ·
[InfoEd SPIN](https://www.infoedglobal.com/products/spin-global-suite/) ·
[Elsevier Funding Institutional](https://www.elsevier.com/products/funding-institutional) ·
[Dimensions Data](https://www.dimensions.ai/dimensions-data/) ·
[ScientifyRESEARCH (ISU)](https://journals.sagepub.com/doi/pdf/10.3233/ISU-230190) ·
[Atom Grants](https://atomgrants.com/platform/discovery) ·
[Cayuse Funding Advisor](https://www.cayuse.com/award-management/fund-finder/) ·
[NIH RePORTER Matchmaker](https://reporter.nih.gov/matchmaker) ·
[Constraint-based recommender systems (ICEC 2008)](https://dl.acm.org/doi/pdf/10.1145/1409540.1409544) ·
[Developing Constraint-based Recommenders](https://www.ise.bgu.ac.il/faculty/liorr/recsyshb/chConstraint.pdf) ·
[Ranking under Constraints (arXiv:2202.07088)](https://arxiv.org/pdf/2202.07088) ·
[De-conflating Preference and Qualification (arXiv:2602.03097)](https://arxiv.org/html/2602.03097) ·
[Fairness in Job Recommendation under Quantity Constraints (AAAI 2023)](https://pike.psu.edu/publications/aaai23-fair.pdf) ·
[Fairness of recommender systems in recruitment (Frontiers in Big Data)](https://www.frontiersin.org/journals/big-data/articles/10.3389/fdata.2023.1245198/full) ·
[JAG (arXiv:2602.10258)](https://arxiv.org/pdf/2602.10258) ·
[Filtered ANN in Vector Databases (arXiv:2602.11443)](https://arxiv.org/pdf/2602.11443) ·
[Compass (arXiv:2510.27141)](https://arxiv.org/pdf/2510.27141) ·
[Clinical trial eligibility parsing scoping review](https://www.sciencedirect.com/science/article/abs/pii/S1359644624002642) ·
[Patient–trial matching via entity extraction and neural re-ranking (arXiv:2307.00381)](https://arxiv.org/pdf/2307.00381) ·
[NIH RePORT](https://report.nih.gov/) ·
[NSF Award Search Web API](https://resources.research.gov/common/webapi/awardapisearch-v1.htm) ·
[Grants.gov XML Extract](https://www.grants.gov/xml-extract) ·
[CORDIS H2020 projects](https://data.europa.eu/data/datasets/cordish2020projects?locale=en) ·
[CORDIS Horizon Europe projects](https://data.europa.eu/data/datasets/cordis-eu-research-projects-under-horizon-europe-2021-2027?locale=en) ·
[Gateway to Research data](https://gtr.ukri.org/resources/data.html) ·
[OpenAIRE Graph dumps](https://old.openaire.eu/graph-dumps.html) ·
[Data Leakage in Recsys Offline Evaluation (TOIS)](https://dl.acm.org/doi/10.1145/3569930) ·
[Don't Get Ahead of Yourself (RecSys 2025)](https://dl.acm.org/doi/10.1145/3705328.3759329) ·
[Are We Evaluating Rigorously? (RecSys 2020)](https://dl.acm.org/doi/10.1145/3383313.3412489) ·
[ORBIT (arXiv:2510.26095)](https://arxiv.org/html/2510.26095) ·
[Let Unfunded Grant Applications See the Light of Day](https://issues.org/unfunded-grant-applications-open-science-buck-marcum/) ·
[Expertise vs. Bias in Evaluation: Evidence from the NIH](https://www.hbs.edu/ris/Publication%20Files/16-053_d27212a1-d6ca-400d-bb65-b078f104d8ae.pdf) ·
[Matthew effect replication (RoRI WP 16)](https://rori.figshare.com/articles/preprint/29302004) ·
[Bias in Research Grant Evaluation (PLOS ONE)](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0155876) ·
[Measuring bias, burden and conservatism (F1000Research)](https://f1000research.com/articles/8-851)
