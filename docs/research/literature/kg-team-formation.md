# Knowledge Graphs for Scholarly Matching and Interdisciplinary Team Formation
**Survey date: August 2026.** Use case anchor: grant call → required-expertise extraction → candidate team from disparate backgrounds → joint project ideas.

Evidence tags: **[PR]** peer-reviewed · **[PRE]** preprint · **[TOOL]** software/data/product documentation · **[INF]** my inference, not stated in a source.

---

## 0. Headline conclusions

1. **The data substrate is ready; the funding-linkage layer is the bottleneck.** OpenAlex (2026) and OpenAIRE Graph v11.x are the only open KGs that model funder → award → PI → institution → publication → topic end-to-end. Both have the schema; neither has dense coverage. The **award→publication edge tops out around 10–43% recall** depending on funder.
2. **The end-to-end pipeline barely exists as a literature.** Roughly **four papers worldwide** take a funding call as input and emit a team. ULTRA (Srivastava et al.) is the only deployed, human-evaluated one.
3. **Neural team formation (OpeNTF) and grant teaming are disjoint literatures that do not cite each other.** OpeNTF ships DBLP / IMDB / USPTO / GitHub and **no grant dataset**. Adding one is a clean, unclaimed contribution.
4. **The motivating hypothesis is not supported as stated.** The best direct evidence (Bromham 2016, ARC; Boudreau 2016, randomized) says interdisciplinarity and novelty are *penalized* in review. The defensible reframing: composition predicts award (Wanzenböck 2020, H2020), the relationship is **inverted-U**, and the penalty is a **panel-design artifact** (Seeber 2025).
5. **Award outcome is a very noisy target.** Pier et al. 2018 report **ICC ≈ 0** among NIH reviewers. This caps achievable predictive performance for any award-likelihood model.
6. **LLM idea generation produces ideas judged more novel but that execute worse.** Si/Yang/Hashimoto's own 2025 follow-up closed the gap they found in 2024.

---

## 1. Academic knowledge graphs

### 1.1 Comparison table

| Resource | Grants first-class? | funder→award→PI→pub | License | Scale (2026) | Access |
|---|---|---|---|---|---|
| **OpenAlex** | **Yes** — `awards` entity | **Yes in schema**, coverage ramping | CC0 snapshot; **API now metered** | ~480M works | S3 snapshot + REST |
| **OpenAIRE Graph v11.1.1** | **Yes** — `project` + `person` | **Yes, materialized in dumps** | CC-BY 4.0 | 218M pubs, **3.91M projects** | Zenodo dumps (378 GB), REST |
| Crossref GLS | Yes (grant DOIs) | Partial | CC0 metadata | ~200k grants | REST |
| PID Graph / DataCite | Funder only, **no award node** | Weak | Open | 108M DOIs | GraphQL (**deprecating Jul 2027**) |
| S2AG / S2ORC | **No** | **No** | ODC-BY | 205M pubs, 2.5B citations | REST + bulk |
| ORKG | No | No | CC0 / MIT | ~10k papers | REST, SPARQL |
| SciGraph | Was partial | **Retired 2023** | — | — | dead |
| AI-KG → CS-KG 2.0 | No | No | CC-BY | 25M entities / 67M rels | portal + dump |
| CSO | N/A (taxonomy) | N/A | CC-BY | 14,164 topics | download + classifier |
| Wikidata / WikiCite | Nominal only | Very weak | CC0 | — | **WDQS split May 2025, unstable** |
| Dimensions | **Yes, strongest** | **Yes** | **Proprietary** | 140M+ pubs + grants | API/BigQuery |
| NIH RePORTER | Yes, authoritative | **Yes** (publications table) | Public domain | — | REST + bulk |
| NSF Award Search | Yes | Weak on pub leg | Public domain | 525,927 awards | bulk JSON/XML |
| UKRI GtR | Yes | Yes (Researchfish) | Open | — | REST |
| CORDIS | Yes | Org-level, not PI-level | CC-BY | 8,442 HE + 35,386 H2020 projects | data.europa.eu dumps |

### 1.2 Details that matter

**OpenAlex** [TOOL]. Successor to MAG (retired 31 Dec 2021). Priem, Piwowar & Orr, *OpenAlex: A fully-open index of scholarly works, authors, venues, institutions, and concepts*, arXiv:2205.01833, 2022 — https://arxiv.org/abs/2205.01833 [PRE]. The `awards` endpoint (https://developers.openalex.org/api-reference/awards) exposes `funder.ror`, `funder_award_id`, `amount`, `lead_investigator.orcid`, `lead_investigator.affiliation.*`, `funded_outputs` — **the whole chain on one object**. Per the OpenAlex blog *Funding metadata in OpenAlex* (26 Jan 2026, https://blog.openalex.org/funding-metadata-in-openalex/): Wellcome-funded $3.6M/3yr project, **~11.5M grants ingested**, but **"grant ID matching (linkages between individual grant IDs and papers)" is listed as not yet done**. Two operational changes to plan around: **API keys mandatory since ~Feb 2026, credit-metered, $1/day free**; free snapshot tier now **quarterly**. → **Build on the CC0 snapshot, not the API** [INF].

`concepts` deprecated in favour of **OpenAlex Topics** (4-level Domain/Field/Subfield/Topic, ~4,500 topics).

**OpenAIRE Graph** [TOOL]. v11.1.1 dump, 8 Jun 2026, DOI 10.5281/zenodo.20428976. Counts: 218,421,450 publications · **3,909,902 projects** · 494,099 organizations · **14,803,875 persons (ORCID-derived)**. Relation counts are the useful part: `project_produces` **10,038,714**, `project_hasParticipant` **5,550,746**, `person_projectParticipation` **831,589**, `person_coAuthorship` **372,872,930** (with co-authored-product counts). v11 added `person` as a NEW first-class entity. **This is the single richest open substrate for the use case** — it is the only source that ships both explicit project↔person edges and weighted co-authorship edges [INF]. Atzori et al., *Challenges in building scholarly knowledge graphs for research assessment in open science*, QSS 5(4):991, 2024 — https://direct.mit.edu/qss/article/5/4/991/123928 [PR].

**Crossref Grant Linking System** [TOOL]. https://www.crossref.org/services/grant-linking-system/ — grant DOIs with award title, abstract, amount, and **investigator names + roles + optional ORCID/ROR**. Reality check: **>200,000 grants registered**, ~250k grant→output relationships through Jul 2025, and an earlier Crossref analysis found only **~10% of registered grants** participating in any output link. Separately, **<25% of Crossref journal articles carry funder metadata at all** (Jones & Habermann, arXiv:2501.06843 [PRE]).

**ORCID** [TOOL] does hold funding records — dedicated Funding section with type, amount, dates, funder (ROR/Fundref/Ringgold), grant number; some funder-asserted (UKRI, Wellcome, SmartSimple/Altum platforms). But it is opt-in, sparse, and **carries PI→award only, never award→publication**.

**PID Graph / FREYA** [PR/TOOL]. Fenner et al., *Connected Research: The Potential of the PID Graph*, Patterns 1(3):100180, 2020 — https://www.sciencedirect.com/science/article/pii/S2666389920302440. Funder linkage is funder→work via Funder ID/ROR; **there is no award node**. DataCite GraphQL API deprecating **July 2027**.

**S2AG / S2ORC** [PR]. Kinney et al., arXiv:2301.10140; Lo et al., ACL 2020. 205M pubs, 121M authors, 2.5B citations, SPECTER/SPECTER2 embeddings, full text. **Zero funding layer.** Use as the semantic/capability enrichment join, not the backbone.

**ORKG** [PR]. Jaradeh et al., K-CAP 2019; https://orkg.org. ~10k papers, ~5k research problems, CC0 data. **No funder/award/grant entity.** Useful only as a fine-grained method/problem vocabulary.

**SciGraph** — **retired 2023.** Do not build on it. Its grant modeling was real and is now gone.

**AI-KG → CS-KG 2.0** [PR]. Dessì et al., ISWC 2020 (820K entities, 14M triples, 333K AI papers); CS-KG 2.0, *Scientific Data* 12:964, 2025 — https://www.nature.com/articles/s41597-025-05200-8 (25M entities, 67M relations, 15M papers, CC-BY). Content graphs — task/method/metric — **no people, institutions, or funders**. Complement, never backbone.

**CSO** [PR]. Salatino et al., ISWC 2018 — 14,164 topics, 162,121 relations, CC-BY, v3.4.1; CSO Classifier arXiv:2104.00948. **SciNoBo FoS** (Kotitsas et al., *Frontiers in Research Metrics and Analytics* 8:1149834, 2023) is the better choice for grant-call classification: 6-level taxonomy, **explicitly multi-label and designed for multidisciplinarity**.

**Wikidata / WikiCite** [TOOL]. Scholia (Nielsen, Mietchen, Willighagen, ESWC 2017). Grant coverage anecdotal. **The 2025 event was not removal but a graph split**: scholarly articles exceeded 50% of Wikidata triples; WDQS split into main + scholarly subgraphs on **9 May 2025**, legacy Blazegraph endpoint slated to disappear during 2026. See https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service/WDQS_graph_split and CEUR Vol-4064/PD-paper3. **Infrastructurally unstable; do not depend on it.**

### 1.3 Derived datasets worth knowing (2025–2026)

- **FIND — From Funding to Findings**, Smith, Lu & Fan, arXiv:2510.10336, 2025 [PRE]. Crossref ∪ NSF-PAR over **525,927 NSF awards**: **224,524 (42.7%) matched to ≥1 publication**; enriched with OpenAlex; **12.4M scored (proposal, finding) pairs**. Closest thing to an open, text-aware NSF award↔output graph.
- **NIH-MPINet**, Shi et al., arXiv:2604.22802, 2026 [PRE]. **30,127 PIs, 86,743 R01-equivalent grants, 2006–2023**, 888 orgs, 40 ICs, edge features (grant year, title, abstract). Funded grants only — **no negative class**.
- *Linking Global Science Funding to Research Publications*, arXiv:2603.24147, 2026 [PRE] — disambiguates **1.9M funder acknowledgement strings**.

### 1.4 Where the chain breaks — three systematic weak points [INF]

1. **award→publication is sparse everywhere.** Treat funding evidence as sparse positive signal, never as a filter; filtering on "has a grant record" silently excludes most competent researchers.
2. **award→PI is name-based, not ORCID-based** in NSF, CORDIS, and most national funders. Entity resolution (name + institution + topic + time window) is a required, non-trivial pipeline stage.
3. **Only the lead investigator is modeled.** OpenAlex exposes `lead_investigator` — singular. Co-Is, who are precisely the "disparate backgrounds" collaborators you want, are largely invisible in award metadata. Co-authorship is the better capacity proxy.

---

## 2. KG-based recommender methods

### 2.1 The established taxonomy

Three families, all pre-2021, all still the baselines everyone reports against:

- **Embedding-regularization**: TransE (Bordes 2013), ComplEx (Trouillon, ICML 2016), **RotatE** (Sun et al., ICLR 2019, arXiv:1902.10197) as KG-side regularizers on item embeddings. CKE, KTUP.
- **Propagation / GNN**: **RippleNet** (Wang et al., CIKM 2018) — preference propagation, seeds = interacted items, iterative expansion along KG edges. **KGCN** (Wang et al., WWW 2019) — user-specific relation weighting, then GCN aggregation. **KGAT** (Wang et al., KDD 2019, arXiv:1905.07854) — attentive embedding propagation over a collaborative KG; original paper claims recall@20 gains of 8.95%/4.93%/7.18% on Amazon-book/Last-FM/Yelp2018. **KGIN** (WWW 2021) — intent-aware, path-aware aggregation. KGAT and KGIN are the two usually named as SOTA in the classical line.
- **Path reasoning / explainable**: **PGPR** — Xian et al., *Reinforcement Knowledge Graph Reasoning for Explainable Recommendation*, SIGIR 2019, arXiv:1906.05237, code https://github.com/orcax/PGPR. Policy-guided path reasoning with soft rewards, user-conditional action pruning, multi-hop scoring; the recommendation **is** a path, so the explanation is free. Successors: ReMR (2022), TPRec (2022), CogER (2023), ERRKG (2024), PGRC (2025, *Data Technologies and Applications*), M4Re (2025).

### 2.2 The reproducibility problem — read this before trusting any of the above

**[PR/PRE]** *A Worrying Reproducibility Study of Intent-Aware Recommendation Models*, arXiv:2501.10143, 2025 — re-examines KGIN and peers. Findings: **most methods fail to outperform simple baselines**, notably on Amazon-Book; data preprocessing claims did not match the actual data (low-interaction users/items not discarded as stated); embedding size held fixed across models despite being a decisive hyperparameter; no code shared for baselines or tuning. Related: *Reproducibility and Artifact Consistency of the SIGIR 2022 Recommender Systems Papers Based on Message Passing*, arXiv:2503.07823. Also **KGUF** (arXiv:2403.20095) shows a deliberately simple knowledge-aware graph recommender is competitive.

**Practical implication [INF]:** do not adopt KGAT/KGIN on the strength of their reported numbers. For a team-formation setting the honest baseline set is: co-authorship-weighted personalized PageRank, TF-IDF/BM25 over abstracts, and SPECTER2 nearest-neighbour. A KG-GNN must beat those with tuned hyperparameters before it earns its complexity.

Reinforcing this from the adjacent expert-finding literature: *Traditional statistical representations outperform generative AI in identifying expert peer reviewers*, arXiv:2605.18752, 2026 [PRE] — **TF-IDF beat SPECTER2** for reviewer identification, because in specialized domains precise technical vocabulary is more discriminative than broad semantic clustering.

### 2.3 KG embeddings themselves

Standard evaluation is MRR / Hits@{1,3,10} on FB15k-237 and WN18RR. Overview: *Knowledge Graph Embedding: An Overview*, arXiv:2309.12501 [PRE]. **2025–26 direction is KG foundation models** — e.g. SEMMA, *A Semantic Aware Knowledge Graph Foundation Model*, arXiv:2505.20422 [PRE] — pretrained, transferable across graphs, replacing per-graph shallow embeddings. **Confidence caveat: my searching here was shallower than for other sections; I did not find a definitive 2025–26 KGE benchmark survey and would not claim a single SOTA method.**

### 2.4 Heterogeneous GNNs

Metapath-based line: MEIRec (KDD 2019, metapath-guided HGNN for intent recommendation), MAGNN, HMSG (*Knowledge-Based Systems* 2023), and paper-recommendation-specific metapath aggregation (IEEE 2024, doc 10674400). 2026 direction: **cross-domain graph foundation models** — CrossHGL, arXiv:2603.27685 [PRE]; *One Router to Route Them All: Homogeneous Expert Routing for Heterogeneous Graph Transformers*, arXiv:2511.07603 [PRE].

### 2.5 2025–2026 LLM + KG / GraphRAG hybrids — where the field actually is

- **KG-RAG for recommendation**: *Knowledge Graph Retrieval-Augmented Generation for LLM-based Recommendation*, arXiv:2501.02226 [PRE]. *Comprehending Knowledge Graphs with LLMs for Recommender Systems*, arXiv:2410.12229 [PRE]. *Enhancing LLM-based Recommendation with Preference Hint Discovery from Knowledge Graph*, arXiv:2601.18096 [PRE].
- **X-KGRank**, arXiv:2608.01732, 2026 [PRE] — six-stage KG-RAG for **explainable** LLM recommendation: heterogeneous KG in Neo4j → LightGCN embeddings → structural feature mining → candidate-specific path retrieval → LLM re-ranking. **This is the closest published architecture to what a grant-team recommender should look like** [INF]: the retrieved KG paths *are* the justification, and each path is an auditable, removable set of edges.
- Surveys: *Large Language Model Enhanced Recommender Systems: A Survey*, arXiv:2412.13432 [PRE]; *LLM-empowered knowledge graph construction: A survey*, arXiv:2510.20345 [PRE]; living list https://github.com/zjukg/KG-LLM-Papers.

**SOTA assessment [INF]:** the classical KG-recsys line (KGAT/KGIN/PGPR) is **methodologically mature but empirically contested**. The live frontier is **KG-RAG with LLM re-ranking**, whose selling point is explanation quality rather than accuracy. For a use case where a research office must *justify* a proposed team to a PI, explanation quality is the right thing to optimize, and the accuracy story is weak enough that you should not pretend otherwise.

---

## 3. Team formation in expert networks

### 3.1 The Lappas line

**Lappas, Liu & Terzi, *Finding a Team of Experts in Social Networks*, KDD 2009**, 467–476 — https://dl.acm.org/doi/10.1145/1557019.1557074 [PR]. Experts with skill sets, a compatibility graph, a task = required skill set. Find `X ⊆ V` covering `T` while minimizing communication cost: **diameter** or **MST** of the induced subgraph. Both NP-hard. `RarestFirst` approximation for diameter; enhanced-graph + Steiner reduction for MST. Evaluated on DBLP. Every later paper perturbs one term of this.

Follow-ups, each changing one term:
- **Anagnostopoulos et al., WWW 2012** — online arrival + **workload balancing**, competitive analysis. https://dl.acm.org/doi/10.1145/2187836.2187950
- **Kargar & An, CIKM 2011** — sum-of-edge-weights cost, leader variant, **top-k** teams
- **Kargar, Zihayat & An, SDM 2013** — adds **personnel cost**, Pareto/skyline
- **Majumder, Datta & Naidu, KDD 2012** — expert **capacity** constraints
- **Rangapuram, Bühler & Hein, WWW 2013** — **densest subgraph** reformulation (FORTE); always-feasible with quality guarantee; argues density beats diameter/MST as a cohesion proxy. https://dl.acm.org/doi/10.1145/2488388.2488482
- **Bhowmik et al., SDM 2014** — unifies coverage, compatibility, cost, and **skill redundancy** into unconstrained non-monotone **submodular** maximization (0.41-approx). Dissolves the "coverage as hard constraint" assumption. https://epubs.siam.org/doi/10.1137/1.9781611973440.102
- **Okimoto et al. (2015)** — ***k*-robust** teams (feasible after removing any *k* members). Adopted as a metric by ULTRA.

Recent (2023–2026): fairness-constrained assembly (arXiv:2306.07023 [PRE]; Springer 2023 [PR]); *Forming Coordinated Teams that Balance Task Coverage and Expert Workload*, **DMKD 2025** (arXiv:2503.05898) [PR]; *Team Formation amidst Conflicts*, arXiv:2403.00859 [PRE]; hierarchical ILP, arXiv:2506.02756 [PRE].

**Surveys.** Juárez, Santos & Brizuela, *A Comprehensive Review and a Taxonomy Proposal of Team Formation Problems*, **ACM CSUR 54(7), 2021** — https://dl.acm.org/doi/abs/10.1145/3465399 [PR]; note their observation that *assembling a covering group does not guarantee it operates as a team*. Saeedi, Hosseini, Wong & Fani, *A Survey of Subgraph Optimization for Expert Team Formation*, **ACM CSUR 2025**, DOI 10.1145/3737455 [PR] — current best entry point, written as the graph-side companion to the neural line.

### 3.2 The neural line and OpeNTF — specifics as requested

**[TOOL]** https://github.com/fani-lab/OpeNTF · CC BY-NC-SA 4.0 · latest release **v0.2.0.0 "Graph Neural Team Formation", 18 Nov 2025** · successor branding OpeNTF2 · ~29 stars (small community).

**Datasets shipped — exactly four domains** (verified from `readme.md` and `src/__config__.yaml`):

| Class | Source | Team | Skills | Location |
|---|---|---|---|---|
| `cmn.publication.Publication` | **DBLP** (AMiner v12) | paper | keywords / FoS | venue |
| `cmn.movie.Movie` | **IMDB** | movie | genres | — |
| `cmn.repository.Repository` | **GitHub** | repo | languages/topics | — |
| `cmn.patent.Patent` | **USPTO/PatentsView** | patent | subgroup codes | inventor location |

> **No grant or funding dataset. No PubMed either.** The domain enum is closed at these four. A `cmn.grant.Grant` domain (award = team, PI+co-PIs = members, program element / MeSH = skills, directorate/IC = location) is a clean, unclaimed extension that fits the existing OO dataset hierarchy.

**Representation.** Sparse boolean occurrence matrices in `teamsvecs.pkl`: `['skill']` (input), `['member']` (labels), `['loc']`; plus `indexes.pkl`. Core formulation: **multi-label classification** — skill vector in, distribution over all experts out, each expert a label.

**Models** (`src/mdl/`): `rnd`, `fnn`, **`bnn`** (variational Bayesian via `bayesian-torch` — the flagship), `nmt` (OpenNMT-py seq2seq, SIGIR 2025), `gnn` (PyG, team recommendation as **expert↔team link prediction**). Skill embeddings: `d2v`, node2vec, metapath2vec, GCN, GraphSAGE, GAT, GATv2, GIN. Temporal wrappers `tNtf`/`tNmt`; baselines `rrn`, `caser`.

**Training strategies.** **Streaming/temporal** training (teams sorted by interval, incremental training, test on last `step_ahead` intervals) — counters the i.i.d. bag-of-teams assumption. **Negative sampling** under a closed-world assumption (no real rejected teams exist): `uniform`, `unigram`, `unigram_b` (Laplace-smoothed per-minibatch). **Curriculum learning** (adaptive loss-based, WSDM 2025).

**Metrics** (from `src/__config__.yaml`, via `pytrec_eval`):
- `trec`: **P@k, recall@k, ndcg_cut@k, map_cut@k, success@k**; default `topk = 2,5,10`, first-stage `topK = 1000`
- `other`: **skill_coverage@k**, **aucroc** (README itself flags aucroc as questionable when #classes = #experts)
- `fair`: **ndkl@k**, **skew@k**, optional FairRankTune `exp`/`expu`
- Per-instance results retained for **paired significance tests**. Efficiency reported as preprocessing speedup curves, not as a first-class metric.
- **Absent: any novelty, serendipity, or intra-team diversity metric.**

**Key papers.** Rad, Fani et al., *Learning to Form Skill-based Teams of Experts*, CIKM 2020 · *Retrieving Skill-based Teams from Collaboration Networks*, SIGIR 2021 · **PyTFL**, CIKM 2021 (DOI 10.1145/3459637.3481992) · EDBT 2022 · *Learning Heterogeneous Subgraph Representations for Team Discovery*, IRJ 26(1):8, 2023 · **Dashti, Saxena, Patel & Fani, *OpeNTF: A Benchmark Library for Neural Team Formation*, CIKM 2022 demo** (10.1145/3511808.3557526) · **Dashti, Samet & Fani, *Effective Neural Team Formation via Negative Samples*, CIKM 2022** (10.1145/3511808.3557590) · **Rad et al., *A Variational Neural Architecture for Skill-based Team Formation*, ACM TOIS 42(1), 2023** (10.1145/3589762) — the `bnn` flagship · **Loghmani & Fani, *Bootless Application of Greedy Re-ranking Algorithms in Fair Neural Team Formation*, BIAS@ECIR 2023** (10.1007/978-3-031-37249-0_9) — **negative result**: off-the-shelf greedy fair re-rankers (det_greedy, det_cons, det_relaxed, fa\*ir) either fail to achieve fairness or destroy utility · *A Streaming Approach to Neural Team Formation Training*, ECIR 2024 · *vivaFemme*, BIAS@SIGIR 2024 (in-process loss regularization, the answer to "bootless") · WSDM 2025 curricula · **Thang, Hosseini & Fani, *Translative Neural Team Recommendation: From Multilabel Classification to Sequence Prediction*, SIGIR 2025** · *Neural Shifts in Collaborative Team Recommendation*, CIKM 2025 · **OpeNTF2: Fairness-aware Graph Neural Team Formation, SIGIR 2026** · **Saeedi & Fani, *Beyond Searching a Village: Learning to Recommend Diverse and Successful Collaborative Teams*, RecSys 2026** — first move toward joint diversity + predicted success. Full list with PDFs and referee reports: https://hosseinfani.github.io/lab/publication.html.

**Neural TF outside the Fani lab:**
- **Dara, Rad, Zarrinkalam & Bagheri, *Retrieval-Augmented Neural Team Formation*, ECIR 2025**, 362–371 — https://link.springer.com/chapter/10.1007/978-3-031-88714-7_35 [PR]
- **Zhang, Rad, Zihayat & Bagheri, *Say the Task, Build the Team: Prompt-Based Team Formation*, ASONAM 2025 (LNCS 16322)**, 227–242, DOI 10.1007/978-3-032-13513-1_19, code https://github.com/littlebeanbean7/Prompt-Based-Team-Formation [PR] — **the most directly relevant LLM work**: fine-tunes **T5-Large** to map a free-text **project description → expert team**, on the argument that keyword matching cannot capture natural-language project semantics. Ships a DBLP-V14 dataset with LLM-generated expertise labels. **This is exactly the input modality a grant call has — but it is evaluated on papers, not grants.**
- Kaw, Kobti & Selvarajah, GAT transfer learning, IJCNN 2023 · Sapienza, Goyal & Ferrara, *Frontiers in Big Data* 2:14, 2019 · **Golzadeh, Golab & Szlichta, *ExES: Explaining Expert Search and Team Formation Systems*, arXiv:2405.12881** [PRE] — matters if a human PI must accept the team.
- **Thin area:** RL-based team formation is nearly empty (arXiv:2304.04022 GP+RL hybrid; ULTRA's bandit). Appears to be a real gap, not a search failure.

---

## 4. Collaborator recommendation, cross-disciplinary matching, structural holes

- **Link prediction for interdisciplinary collaboration via co-authorship network**, *Social Network Analysis and Mining* 8, 2018 (arXiv:1803.06249) [PR] — university-wide co-authorship network, predicts **cross-department** links specifically. Closest published match to the interdisciplinary motivation.
- *Link prediction in co-authorship networks based on hybrid content similarity metric*, *Applied Intelligence* 2017 [PR]; *Dual network embedding for research interests in co-authorship link prediction*, PeerJ CS 2021 [PR]; supervised link prediction with author node features, arXiv:2505.21673, 2025 [PRE].
- **Zhu & Yaseen, *A recommender for research collaborators using graph neural networks*, Frontiers in AI 5, 2022** [PR] — same group as the NIH grant recommender below.

**Structural holes — the mechanism you actually want:**
- **Burt (1992, 2004)** — *Structural Holes*; *Structural Holes and Good Ideas*, AJS 110(2). Brokers across holes get earlier access to more diverse information and produce more novel ideas. This is the theoretical warrant for wanting disparate backgrounds at all.
- **Lou & Tang, *Mining Structural Hole Spanners Through Information Diffusion in Social Networks*, WWW 2013** — HIS and MaxD algorithms; NP-hard. https://keg.cs.tsinghua.edu.cn/jietang/publications/WWW13-Lou&Tang-Structural-Hole-Information-Diffusion.pdf
- Diversified top-k SH spanners, *Information Sciences* 2022; SDHE (hyperbolic space, 2022); dynamic maintenance arXiv:2502.11396, 2025.

> **Gap [INF]:** structural-hole detection and skill-coverage team formation are **two disconnected literatures**. I found **no work using SH-spanner scores as a term in a team formation objective** ("cover the skills *and* include a broker linking the sub-communities"). For an explicitly cross-disciplinary grant team, this is the most obvious unexploited synthesis.

**Serendipity / beyond-accuracy:** Kaminskas & Bridge, *Diversity, Serendipity, Novelty, and Coverage*, **ACM TiiS 7(1), 2016** — https://dl.acm.org/doi/10.1145/2926720 [PR]; Ge, Delgado-Battenfeld & Jannach, RecSys 2010; *Beyond-accuracy … in GNN recommenders*, Frontiers in Big Data 6, 2023. **These metrics are standard in RecSys and entirely absent from neural TF evaluation.**

**Deployed systems:** VIVO (ontology + app, RDF/SPARQL, the de facto scholarship representation standard); Harvard Catalyst **Profiles RNS** (built on VIVO 1.4 ontology); **RNS-Searcher** (https://github.com/pittdbmivis/rns-searcher, explicitly for finding collaborators); Elsevier **Pure Experts Portal** / SciVal; **Dimensions Analytics** (grants↔publications↔patents↔trials in one graph — the best commercial substrate); Academic Analytics. **[INF] All of these are search/browse over profiles. None solves a coverage-plus-cohesion objective; none uses neural team formation.** That is the gap between the literature and what universities actually run.

---

## 5. Science-of-science evidence — does the hypothesis hold?

### 5.1 Against

1. **Bromham, Dinnage & Hua, *Interdisciplinary research has consistently lower funding success*, Nature 534:684–687, 2016** — https://www.nature.com/articles/nature18315 [PR]. **All 18,476 proposals** to the Australian Research Council Discovery Programme over 5 years (2010–2014). Interdisciplinarity from applicant-declared Field-of-Research codes via a Rao–Stirling-family diversity measure. **Degree of interdisciplinarity correlates negatively with funding probability, within every primary field**, robust to controls for number of collaborators, field, and institution type. ⚠️ **Exact effect size could not be verified from open sources — read Fig. 2 before quoting a magnitude.** Note the measure is *declared category codes*, i.e. a claim about disciplinary position, not measured knowledge integration.
2. **Boudreau, Guinan, Lakhani & Riedl, *Looking Across and Looking Beyond the Knowledge Frontier*, Management Science 62(10):2765–2783, 2016** — https://pubsonline.informs.org/doi/10.1287/mnsc.2015.2285 [PR]. **Randomized** evaluator assignment, 2,130 evaluator–proposal pairs. Two adverse findings: evaluators score proposals **closer to their own expertise lower**, and score **highly novel proposals lower**. **Highest internal validity in this entire section, and doubly awkward: a system that maximizes reviewer–proposal expertise proximity would, per this result, lower scores.**
3. **Leahey, Beckman & Stanko, *Prominent but Less Productive*, ASQ 62(1):105–139, 2017** [PR]. ~900 scientists, ~32,000 articles including unpublished. IDR → **fewer papers published**, higher citations conditional on publishing. Mechanism that could *explain* Bromham without invoking reviewer bias: IDR degrades the track-record signal reviewers use.
4. **Hofstra et al., *The Diversity–Innovation Paradox in Science*, PNAS 117(17):9284–9291, 2020** [PR]. 1.2M+ US PhDs 1977–2015. Underrepresented groups produce novelty at **higher** rates; their novelty is **taken up at lower rates** and converts less often into careers. Diversity→novelty, but novelty→discounted.
5. **Xiang, Romero & Teplitskiy, *Evaluating interdisciplinary research: Disparate outcomes for topic and knowledge base*, PNAS 122(16):e2409752122, 2025** — https://www.pnas.org/doi/10.1073/pnas.2409752122 [PR]. 128,950 manuscripts. **Knowledge-base interdisciplinarity (from references) → higher acceptance. Topic interdisciplinarity (from title/abstract) → lower acceptance.** Interaction: topic-interdisciplinary work does *not* suffer if knowledge-base interdisciplinarity is also high. **The single most useful reframing paper** — but manuscripts, not grants.

### 5.2 For (a narrower claim)

1. **Wanzenböck, Lata & Ince, *Proposal success in Horizon 2020: A study of the influence of consortium characteristics*, QSS 1(3):1136–1158, 2020** — https://direct.mit.edu/qss/article/1/3/1136/96101/ [PR]. Uses **actual proposal-level H2020 data including rejected proposals** (obtained from the Commission). Three significant success-factor families: **network visibility/centrality; prior experience and prior acquaintance among partners; research capability/reputation**. Consortia with high shares of universities score **significantly lower**; private-company- and RTO-heavy consortia score higher; Western European share helps. **This is the empirical warrant that composition predicts award — but the mechanism is incumbency and reputation, not disciplinary complementarity. A recommender trained on this signal optimizes for entrenchment.**
2. **Sun, Livan, Ma & Latora, *Interdisciplinary researchers attain better long-term funding performance*, Communications Physics 4:263, 2021** [PR]. 44,419 UK Research Council grants. IDR researchers show lower short-run impact but **eventually outperform on funding volume and value**, occupying central brokerage positions. Unit is the career, not the proposal → survivorship risk.
3. **Seeber et al., *Partial and particularistic: grant peer review panels evaluating interdisciplinarity*, Research Evaluation, 2025** [PR]. COST — a deliberately **panel-free, non-disciplinary** framework. 1,928 proposals, 5,330 evaluations, 3,050 reviewers. Effect of interdisciplinarity on evaluation was **negligible and non-significant**, no turf wars. **Implies the Bromham penalty is a property of disciplinary-panel architecture, not of IDR itself.**
4. **Yang, Tian, Woodruff, Jones & Uzzi, *Gender-diverse teams produce more novel and higher-impact scientific ideas*, PNAS 119(36), 2022** [PR]. 6.6M medical papers. Mixed-gender teams are **underrepresented vs. a random-mixing null** yet produce more novel, higher-impact work; advantage increases with balance. Strongest single diversity→impact result; still observational, and the underrepresentation finding itself implies non-random selection.
5. **Uzzi, Mukherjee, Stringer & Jones, *Atypical combinations and scientific impact*, Science 342:468–472, 2013** [PR]. 17.9M articles. **Highest-impact papers = high conventionality plus a tail of high atypicality**, ~2× likelihood of top-5% citation. Teams **37.7%** more likely than solo authors to insert novel combinations. **Against naive diversity-maximization: the optimum is a conventional core with an unusual intrusion.**

### 5.3 The shape of the relationship, and the noise floor

- **Inverted-U, repeatedly.** Yegros-Yegros, Rafols & D'Este, PLoS ONE 10(8):e0135095, 2015 [PR] — all three IDR dimensions (variety, balance, disparity) show inverted-U with citations; **proximal** interdisciplinarity helps, **distal** hurts. Nooteboom et al., *Research Policy* 2007 — inverted-U between cognitive distance and innovation. *Scientific Reports* 12, 2022 — societal impact declines past a diversity peak. **Maximizing diversity is empirically wrong; there is an interior optimum.**
- **Near-null baseline.** Larivière & Gingras, JASIST 61(1):126–131, 2010 [PR] — for all disciplines combined, **no clear correlation** between interdisciplinarity and citation rate; positive in biology, negative in biomedical. And *Scientometrics* 127(5), 2022: the **sign flips with the citation window chosen**. Much of this literature is methodologically fragile.
- **The target variable is extremely noisy.** **Pier et al., *Low agreement among reviewers evaluating the same NIH grant applications*, PNAS 115(12):2952–2957, 2018** [PR] — **ICC = 0** for overall ratings (95% CI 0–0.14), ICC = 0.017 for weaknesses. **Fang, Bowen & Casadevall, eLife 5:e13323, 2016** [PR] — percentile score poorly discriminates productivity **within the funded range**; a lottery among meritorious applications would perform comparably. Counterweight: **Li & Agha, *Big names or big ideas*, Science 348:434–438, 2015** [PR] — across 130,000+ NIH R01s 1980–2008, better scores **do** predict better outcomes with rich controls. **Reconciliation: signal exists globally, ~none at the margin — and the margin is exactly where a matching product operates.** Restriction-of-range critique of ICC≈0: https://shinyitemanalysis.org/docs/Metascience-2021-IRR.pdf.
- **Equity.** Ginther et al., Science 333:1015–1019, 2011 [PR] — Black applicants 13pp less likely funded raw, **10pp after full controls**. Hoppe et al., Science Advances 5(10):eaaw7238, 2019 [PR] — **topic choice alone accounts for >20% of the gap**; topic + discuss-decision + score = 42%, leaving 58% unexplained. Composition features that predict funding are prestige/incumbency features; encoding them encodes the inequity.
- **Contested background result.** Wu, Wang & Evans, *Large teams develop and small teams disrupt*, Nature 566:378–382, 2019 [PR] — small teams (≤3) disrupt, large teams develop. **But the CD/disruption index is biased by citation inflation**: Petersen, Arroyave & Pammolli, QSS 5(4):936, 2024 and *Journal of Informetrics* 2024/25 (arXiv:2406.15311) explicitly report **discrepancies in the CD–team-size relationship**. Same caveat applies to Lin, Frey & Wu, *Remote collaboration fuses fewer breakthrough ideas*, Nature 623:987–991, 2023 [PR] — relevant because a KG matcher will assemble geographically dispersed teams, and this literature predicts a breakthrough penalty.
- **AlShebli, Rahwan & Woon, Nature Communications 9:5163, 2018** (ethnic diversity strongest impact predictor) — **NOT retracted.** The retraction was a *different* paper: AlShebli, Makovi & Rahwan, Nat. Comms. 11:5855, 2020 on informal mentorship, **retracted 21 Dec 2020** (co-authorship is an invalid mentorship proxy). Same group, same methodology genre — reputational caution warranted; the 2018 paper is purely correlational.

### 5.4 Background and gaps

Guimerà, Uzzi, Spiro & Amaral, *Team assembly mechanisms determine collaboration network structure and team performance*, Science 308:697–702, 2005 [PR] — three parameters: team size, fraction of newcomers, **incumbent tendency to repeat prior collaborations**. **A matching engine competes against strong incumbency dynamics.** Recent: *Team careers in science*, npj Complexity 2026 [PR] — teams as stable cores + transient peripheries; **team quality bounded by the *minimum* quality among members** (weakest-link), awkward for diversity-maximizing matching. *A review of the science of team science*, Journal of Informetrics 2026 [PR] — names **causal inference as still open**.

**Explicit gaps:** no proposal-level replication of Bromham at NIH/NSF/ERC/NWO; no located critique or replication of Hofstra 2020; no quantitative composition→outcome evaluation of NSF Convergence Accelerator or NIH Common Fund; **no peer-reviewed multi-PI vs single-PI NIH success-rate comparison** (claims to that effect appear only in vendor blogs — do not cite).

---

## 6. LLM research idea generation

### 6.1 Literature-based discovery lineage

Swanson's ABC model: A–B known in one literature, B–C in another, A–C proposed (fish oil / Raynaud's, validated by later trial). Modern: *A context-based ABC model for literature-based discovery*, PLoS ONE 2019 [PR]; AGATHA (deep-learning hypothesis ranking); **SciMON — Wang et al., *SciMON: Scientific Inspiration Machines Optimized for Novelty*, arXiv:2305.14259** [PRE], literature retrieval + iterative novelty enhancement. Survey: **LLM4SR: A Survey on Large Language Models for Scientific Research**, arXiv:2501.04306 [PRE].

### 6.2 The KG + LLM idea generation system most relevant to you

**Gu & Krenn, *Interesting Scientific Idea Generation using Knowledge Graphs and LLMs: Evaluations with 100 Research Group Leaders* (SciMuse), arXiv:2405.17044, Max Planck Institute for the Science of Light** — https://arxiv.org/abs/2405.17044, code https://github.com/artificial-scientist-lab/SciMuse [PRE, with subsequent journal version]. **This is the closest published system to the second half of your use case.** Evolving KG from **58M+ papers**, concepts extracted via RAKE from ~2.44M titles/abstracts, GPT-4 interface, ideas personalized to a researcher's concept neighbourhood. **Evaluated by 100+ Max Planck group leaders across natural sciences, technology, social sciences and humanities, ranking 4,000+ personalized ideas by interest.** Findings: **less common concepts and semantic similarity predict interest; predictive models exceed 65% precision.** Explicitly framed as surfacing interdisciplinary ideas *and collaborations*.

### 6.3 The human evaluation that everyone cites — and its sequel

- **Si, Yang & Hashimoto, *Can LLMs Generate Novel Research Ideas? A Large-Scale Human Study with 100+ NLP Researchers*, arXiv:2409.04109, ICLR 2025** [PR]. **49 expert researchers** wrote ideas on 7 NLP topics; **79 independent expert reviewers** (PhDs/postdocs) blind-scored human vs. LLM ideas on novelty, excitement, feasibility, expected effectiveness. **LLM ideas judged significantly more novel (p<0.05), slightly weaker on feasibility.**
- **Si, Hashimoto & Yang, *The Ideation-Execution Gap: Execution Outcomes of LLM-Generated versus Human Research Ideas*, arXiv:2506.20803, 2025** [PRE]. **43 experts each spent 100+ hours executing a randomly assigned idea** and wrote a 4-page paper. **LLM-idea scores dropped significantly more than expert-idea scores on all metrics after execution, closing the gap observed at ideation.** *If you cite the 2024 result you must cite this one.*

### 6.4 Systems and evaluation infrastructure

- **Sakana AI Scientist-v2** — https://github.com/SakanaAI/AI-Scientist-v2. Agentic tree search; produced a paper that **passed peer review at an ICLR 2025 workshop** with no human edits — **then was withdrawn by Sakana before publication.**
- **Google DeepMind Co-Scientist** — Gemini-based multi-agent system that generates, debates, and evolves hypotheses; **published in Nature (2026), *Accelerating scientific discovery with Co-Scientist*, https://www.nature.com/articles/s41586-026-10644-y** [PR]; blog https://deepmind.google/blog/co-scientist-a-multi-agent-ai-partner-to-accelerate-research/. Experimentally validated hypotheses in liver fibrosis and AMR. **The strongest existence proof that agentic hypothesis generation produces wet-lab-validated results.**
- **Nova**, arXiv:2410.14255 [PRE] — iterative planning and search for novelty/diversity; **3.4× increase in unique novel ideas over baseline**; explicitly aimed at interdisciplinary connection-making.
- **ResearchAgent**, NAACL 2025 (https://aclanthology.org/2025.naacl-long.342/) [PR] — idea generation over an **academic graph** plus a concept knowledge store, refined by multiple human-preference-aligned **ReviewingAgents**.
- Others: **Chain of Ideas** (Findings of EMNLP 2025), **Deep Ideation** (arXiv:2511.02238, over a scientific concept network), HypER (arXiv:2506.12937), HypoChainer (arXiv:2507.17209, LLM+KG hypothesis-driven discovery), SciPIP, Scideator, IdeaSynth.
- Surveys: *Large Language Models for Scientific Idea Generation: A Creativity-Centered Survey*, arXiv:2511.07448 [PRE]; *Towards Scientific Intelligence: A Survey of LLM-based Scientific Agents*, arXiv:2503.24047 [PRE].

### 6.5 How novelty/feasibility are evaluated — and why to distrust it

- **AI Idea Bench 2025**, arXiv:2504.14191 [PRE] — 3,495 top-tier AI papers; three dimensions: Quality (idea-to-idea matching), Novelty (distance to existing literature weighted by citation impact), Feasibility (methodological grounding via reference citation influence). **Typical pattern: novelty >0.6, feasibility <0.5** — plausible-sounding is easy, executable is hard.
- **LLM-as-judge is unreliable here.** *On the Limits of LLM-as-Judge for Scientific Novelty Assessment*, arXiv:2606.12071 [PRE]; ***Style Wins, Substance Loses: A Diagnosis of LLM-as-Judge in Idea Generation***, arXiv:2608.01666 [PRE]; *Can AI Evaluate AI Scientists?*, arXiv:2607.28631 [PRE]. Concretely: *AI's Capability in Assisting Scientific Research … II: Project Planning and Proposal Evaluation*, arXiv:2607.25881 [PRE] — 8 projects, 32 one-page proposals, blind review by 4 humans + 2 frontier LLMs. **Humans rated human- and AI-written proposals similarly; both AI reviewers scored AI-written proposals ~1 point higher on a 5-point scale.** Clear self-preference bias.
- Also: *Do Large Language Models Reduce Research Novelty?*, arXiv:2603.22510 and *Epistemic Diversity and Knowledge Collapse in Large Language Models*, arXiv:2510.04226 [both PRE] — homogenization risk, directly relevant if the system generates joint project ideas at scale.

---

## 7. Grant call → expertise → team assembly — the applied core

**This is the thinnest part of the survey, and the thinness has a specific shape.**

### 7.1 The four systems that exist

1. **ULTRA** (University Lead Team builder from RFPs and Analysis), Srivastava et al., AI4Society / Univ. of South Carolina — arXiv:2201.05646 [PRE]; ACM DOI 10.1145/3632410.3632503, 2023 [PR]; deployed at http://casy.cse.sc.edu/ultra/teaming/; metrics tool https://github.com/ai4society/Ultra-Metric; journal companion **Valluru et al., AI Magazine 2024, https://onlinelibrary.wiley.com/doi/10.1002/aaai.12203** [PR]. **The only deployed, human-evaluated system for exactly this use case.** They name the problem *TeamingForFunding*.
   - Pipeline: scrape NSF call pages (1,797 RFPs; 100% synopsis, 90.4% deadline, 96.2% budget extraction) + faculty pages + Google Scholar. Matching via **SPECTER** embeddings, beating fuzzy string matching. Team formation by **greedy heuristic** under three hand-elicited constraints (size ≤5 unless budget allows; ≥$50K/participant; each member has ≥1 non-overlapping skill).
   - Methods M0 random → M1 string → M2 **ACM CCS taxonomical** → M3 **relational boosted contextual bandits**. **Goodness score** = weighted mean of **redundancy (−), set size (−), coverage (+), k-robustness (+)** [Okimoto et al.].
   - Results, USC (434 RFPs × 200 researchers): M0 0.0879 → M1 0.3673 → M2 0.4097 → **M3 0.5295 at volume 6**. Replicated at **IIT-Roorkee** with Indian DST calls: M0 0.0896 → **M3 0.5835 at volume 1**. Consistent: more informed methods → **fewer but better** teams.
   - Deployed 1 May 2023; IRB-approved 28-day study, **212 responses: 90.09% rated output relevant, 97.64% useful.** Separate retrospective RFP-recommendation accuracy: **54.5%**.
   - **What is not evaluated: the teams.** No ground truth on team quality. The authors state the limitation themselves, and flag the structural obstacle: **the success signal (did the proposal win?) arrives months-to-years later and is effectively unavailable as training feedback.**
2. **Rosati, Laurenzi & Quadrini, *A Hybrid AI Approach for Recommending Collaborators in Research Projects*, Society 5.0 (Springer CCIS 2787), 2026, pp. 252–264**, DOI 10.1007/978-3-032-15463-7_21 [PR]. Explicitly framed on **Horizon Europe consortium formation**. **Agentic Graph RAG** over a KG built from CORDIS + OpenAlex/Semantic Scholar, LLM reasoning for explainable recommendations, evaluated with Claude Sonnet 3.5 and GPT-4o via Design Science + RAGAs. Code https://github.com/Piermuz7/MasterThesisProject.git. **Caveats:** master's-thesis-derived, ~13 pages; recommends *collaborators*, not a constrained consortium (no eligibility rules, no country diversity, no WP/role decomposition); evaluation is RAG quality, not consortium outcome. Same group previously did KG+ML reviewer assignment (AAAI-MAKE 2023) — a useful lineage.
3. **Król, Zborowska, Ropa & Kincel, *CORDIS Partner Matching Algorithm for Recommender Systems*, ACIIDS 2022 (LNAI 13757), pp. 701–715**, DOI 10.1007/978-3-031-21743-2_56 [PR]. Deep learning on historical completed EU projects: entity embeddings of organisations, and a keyword embedding space. Reported via coverage/accuracy/Gini/entropy — **recsys diversity metrics, no outcome link.** Org-to-org matchmaking from co-participation history; does not condition on call topic.
4. **Jadhav, Masrouri & Qin, *ResearchConnect: An AI-Powered Platform for Interdisciplinary Research Team Formation and Ideation Development*, Advanced Intelligent Systems, 2026**, https://doi.org/10.1002/aisy.202501399 [PR]. Syracuse. PDFs/text/URLs → researcher keyword profiles → thematic clustering into teams → **LLMs propose interdisciplinary topics from the team's collective expertise**. **Evaluated against 250 NSF-funded project summaries, testing whether recovered groupings match the actual funded teams.** [INF] This recovery protocol is precisely the recall@k evaluation OpeNTF runs on DBLP — nobody has connected the two.

**Adjacent, individual-level:** **Arroyo-Machado et al., *Matching Researchers to Funding Calls: A Reproducible Institution-Level Framework*, arXiv:2604.06321, 2026** [PRE] — **3,013 University of Granada researchers × 291 Horizon Europe topics**; multiple bibliometric publication sets per researcher (by authorship position, time window), **SPECTER2** embeddings, within-researcher normalisation + percentile ranking. No team step. **Zhu, Patra, Wu & Yaseen, *A novel NIH research grant recommender using BERT*, PLoS ONE 18(1):e0278636, 2023** [PR] — frames grant-announcement recommendation as classification rather than similarity ranking.

**Commercial funding-opportunity recommenders** (all individual↔opportunity, none team-level, none with published methodology): **Pivot-RP** (Clarivate; >25,000 opportunities from >4,000 sponsors; markets an "AI-powered Funding Advisor"), **InfoEd SPIN** (~40,000 opportunities, 1,000+ institutions), **GrantForward**, **Research Professional**, **Scry/AMAforge**. ULTRA's authors noted in 2022 that none identify *teaming* opportunities; four years on, that still holds [INF].

### 7.2 CORDIS as the dataset

Per-framework-programme dumps (CSV/XML/JSON) at data.europa.eu; schema confirmed via the KTH Library `cordis` R package (https://kth-library.github.io/cordis/):

| Table | H2020 | Horizon Europe | FP7 |
|---|---|---|---|
| `project` | 35,386 | 8,442 | 25,785 |
| `organization` | 177,834 | 52,918 | 140,008 |
| `topics` | 35,386 | 8,442 | 26,153 |
| `euroSciVoc` | 120,020 | 26,158 | 68,017 |
| `projectPublications` | 355,710 | — | 305,549 |
| `projectDeliverables` | 148,106 | 1,180 | — |
| `pi` | 8,043 (ERC only) | — | — |

`project` carries `masterCall`, `subCall`, `topics`, `legalBasis`, `fundingScheme`, `objective` (free text), `ecMaxContribution`, `grantDoi`. `organization` joins on `projectID` with role (coordinator/participant), country, activity type (HES/REC/PRC/PUB/OTH), PIC. **So call topic → funded consortium → per-partner contribution → outputs is fully reconstructable from open CC-BY files.** Reference tables: `ref_h2020topics` (3,910), `ref_horizontopics` (2,211), `ref_h2020topicKeywords` (2,562). CORDIS itself now runs semi-automatic ML project classification with a published explainability notice (https://cordis.europa.eu/about/explainability).

> **⚠️ The binding constraint: rejected proposals are not public.** CORDIS contains only funded projects. This is why there is no supervised literature on "will this consortium win" — the negative class does not exist in open data. Wanzenböck et al. (QSS 2020) is the sole exception and required direct Commission access. The **Horizon Dashboard** publishes proposal-level statistics only in aggregate, with no bulk download.

### 7.3 EU partner-search tools — what they actually are

**Funding & Tenders Portal Partner Search** (https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/how-to-participate/partner-search) — search registered organisations by topic/country/type, plus a bulletin board of partner offers and requests, plus person profiles. **Mechanism: keyword + facet filtering over self-declared profiles. No semantic matching, no ranking model, no team-level reasoning.** Also: **Ideal-ist** (ICT NCP network, quality-checked partner search, https://www.ideal-ist.eu/partner-search-home), **Horizon Europe NCP Portal** (cluster-specific services + guides), **Enterprise Europe Network** partnering database + brokerage events, **EURAXESS**, **CORDIS Datalab collaboration network visualisation**, national NCPs (UKRO, NCP Brussels, ISED Canada), commercial (EMDESK, Eurice).

**Blunt assessment: every official EU facility for consortium assembly is a keyword-faceted directory or a bulletin board.** The Commission holds the richest call→consortium→output graph in the world and exposes it through a search box.

### 7.4 EU consortium network analysis (mature but descriptive)

Heller-Schuh et al., *Analysis of Networks in European Framework Programmes (1984–2006)*, JRC/IPTS 2011 (the EUPRO dataset); Barber et al., UNU-MERIT WP 2007-032; Scherngell & Barber, *Annals of Regional Science* 2011 (spatial interaction models); *European R&D networks: a snapshot from FP7*, Economics of Innovation and New Technology 27(5–6), 2018. Recent: arXiv:2410.19556 (2024, CORDIS leadership/community mapping); arXiv:2604.11339 (2026, longitudinal — geographic distance has largely ceased to determine collaboration, country size/economic capacity dominates); *Co-funding networks as a new tool in research evaluation*, Scientometrics 2026.

> **Firm negative finding: no paper does link prediction on EU consortium formation** — no "given topic T and partial consortium C, predict the next partner" model with temporal held-out evaluation. The data is open and complete. **Unclaimed.**

### 7.5 The mature analogue: reviewer assignment (RAP)

This is what a solved version of the problem looks like — shared formalism, gold-standard dataset, deployed systems, contested fairness criteria.

- **Charlin & Zemel, *The Toronto Paper Matching System*, ICML 2013 workshop** — https://www.cs.toronto.edu/~lcharlin/papers/tpms.pdf; **Charlin, Zemel & Boutilier, *A Framework for Optimizing Paper Matching*, UAI 2011** — suitability learned from a small elicited set. The elicitation-cost insight transfers directly: you cannot ask 3,000 researchers to rate 291 calls.
- **Kobren, Saha & McCallum, *Paper Matching with Local Fairness Constraints*, KDD 2019, 1247–1257, arXiv:1905.11924** — **FairIR** and **FairFlow**. Two named failure modes: the assigned *group* lacks collective expertise; workloads are skewed. **This is the single most transferable result to consortium assembly** — "does this set of people cover required expertise subject to load and conflict constraints" solved as constrained flow/IR. **Start here, not from recsys** [INF].
- Infrastructure: gold-standard RAP dataset arXiv:2303.16750; scoping review arXiv:2305.07887; large-conference matching arXiv:2202.12273; randomization arXiv:2310.05995; group fairness arXiv:2410.03474; OpenReview affinity in production; SPECTER/SPECTER2/SciBERT as the shared expertise encoder.
- **2024–26 LLM front**: *Leveraging knowledge graphs and LLMs for content-based reviewer assignment*, **Journal of Intelligent Information Systems, 2025**, DOI 10.1007/s10844-025-01004-9 [PR] — same KG+LLM recipe as Rosati et al. **MERIT**, arXiv:2605.27865, 2026 [PRE], with a warning that transfers directly: general-purpose LLMs "remain unreliable for assessing reviewer suitability, tending to produce broad judgments of **topical relevance** rather than evaluating **expertise** along individual dimensions." Also OmniReview (arXiv:2602.08896), structured profiling (arXiv:2604.05866). **NeurIPS 2026 AI-Assisted Reviewing Experiment** — randomized, three arms — is the template for how to evaluate LLM assistance in a funding pipeline.
- **Funder-side panel formation is closed.** NIH CSR uses referral-staff judgment "supported by knowledge-based technologies"; NSF is program-officer-driven. **Neither publishes an algorithmic system nor releases assignment data.**

### 7.6 LLM/agentic grant systems, 2025–26

The wave is entirely about **writing** and **reviewing**, not assembly. *Assessing ChatGPT's potential as an autonomous grant writing tool*, Innovative Surgical Trends (Springer, Dec 2025), DOI 10.1007/s44414-025-00007-x [PR] — blinded SAGES reviewers: polished and grammatical, **lacking depth of scientific reasoning and feasibility analysis**. *Evaluating LLM-Based Grant Proposal Review via Structured Perturbations*, arXiv:2603.08281 [PRE]. GrantCheck (compliance language, PMC12699247). Commercial: Grantable, FundRobin, Granted AI — **no published methodology, no held-out evaluation, no funding-outcome data. Treat all vendor performance claims as marketing.**

**Firm negative finding: no evaluated agentic system goes call → expertise → assembled team.** The only agentic assembly work is the single Rosati et al. CCIS paper.

---

## 8. Gaps, thin areas, and what is unclaimed

**Genuinely thin or absent:**
1. **Neural team formation has never been applied to grant teams.** OpeNTF ships no funding domain; the grant-teaming papers use string/taxonomy matching, bandits, GAs, and LLM prompting, and never train a neural model on award data. The two communities do not cite each other — **Rosati et al. do not cite ULTRA; ULTRA does not cite the CORDIS work.**
2. **No benchmark and no ground truth for team quality.** RAP has a gold standard and conference-scale deployment. Consortium assembly has: 7-user Likert (ULTRA), diversity metrics with no outcome link (Król), RAG-quality (Rosati), indicator complementarity (Granada). **Nobody has evaluated a recommended consortium against a realised funding outcome.**
3. **The negative class is closed.** Rejected proposals are not public in CORDIS, NSF, or NIH. This is a data-access problem, not a modelling one, and it is the single largest obstacle to the entire supervised framing.
4. **Required-expertise extraction is under-specified everywhere.** Every system reduces "required expertise" to a bag of embeddings of call free text. **Nobody extracts structured requirements** — required disciplines, infrastructure, TRL, mandatory partner types (SME/RTO/public body), country-diversity minima, mandatory roles (dissemination, ethics, data management). Horizon Europe topic texts state these explicitly and they are machine-extractable. MERIT's "topical relevance ≠ dimension-wise expertise" is the RAP field's diagnosis of the same failure.
5. **The constraint layer is trivial where it exists.** ULTRA has three hand-written heuristics. Actual EU eligibility rules (≥3 independent legal entities from ≥3 Member/Associated States for RIA/IA, WP structure, Widening targets) appear in **no** system. FairIR/FairFlow is the right machinery and has never been applied here.
6. **EU consortium link prediction is unclaimed** with a ready-made open CC-BY dataset.
7. **Structural-hole spanning is never used as a team-formation objective term** — the most obvious unexploited synthesis for an explicitly cross-disciplinary team.
8. **Beyond-accuracy metrics (novelty, serendipity, intra-team diversity) are absent from neural TF evaluation**, despite being standard in RecSys since 2010–2016.
9. **RL for team formation is nearly empty.**
10. **Equity is a live, unhandled risk.** Wanzenböck shows experience, centrality, reputation, and Western European location predict success; Ginther and Hoppe show NIH award depends on race and topic choice. **Any recommender trained on realised teams encodes incumbency directly, and no system in §7 mentions this.**
11. **Zero longitudinal or randomized evaluation of team recommendation.** The review side has moved to RCTs (NeurIPS 2026); the teaming side has nothing comparable.

**Where my own confidence is weakest:** §2.3 (KG embedding SOTA — I did not find a definitive 2025–26 fair-evaluation survey and would not name a single best method); the exact Bromham 2016 effect magnitude and Lin 2023 magnitudes (paywalled, unverified); the Gajewar & Das Sarma SDM 2012 citation and the Kong/Xia collaborator-recommendation surveys (from memory, not verified live); the exact CORDIS license string (data.europa.eu pages are JS-only and did not render).

---

## 9. Architecture implied by all of the above [INF — my judgement]

- **Backbone:** OpenAlex CC0 snapshot ⋈ OpenAIRE Graph v11.1.1 CC-BY dump. Complementary funder coverage (OpenAlex skews Crossref/DataCite award DOIs and US/global-north registries; OpenAIRE skews EU/national funder databases). Join on **DOI / ROR / ORCID** — ROR is the reliable key, ORCID the high-value sparse one.
- **Funder ground truth to repair thin edges:** NIH RePORTER (publications table is the gold standard), FIND (saves you the NSF work), UKRI GtR, CORDIS.
- **Specialty layer:** OpenAlex Topics baseline; **SciNoBo FoS** for defensible multi-label classification of the *call text*; CSO/CS-KG for method-level matching in computational specialties.
- **Semantic matching:** SPECTER2 over call text and candidate abstracts — but **benchmark against TF-IDF**, which beat SPECTER2 for reviewer identification (arXiv:2605.18752).
- **Assembly:** constrained flow/matching in the FairIR/FairFlow tradition, with ULTRA's goodness metric (coverage, redundancy, set size, k-robustness) as the objective — better-motivated than recall@k, and the only metric set validated with real users.
- **Explanation:** KG path retrieval in the X-KGRank style; each path is an auditable, removable set of edges. Given the noise floor on award prediction (ICC≈0), **optimize for justifiable recommendations, not for predicted award probability.**
- **Ideation:** SciMuse-style KG-neighbourhood-conditioned LLM generation, evaluated by human interest ratings — and cite the Ideation-Execution Gap when reporting novelty.
- **Diversity target:** interior optimum, not maximum. Uzzi's shape — conventional core plus atypical tail — is the empirical target.
- **Do not build on:** SciGraph (dead), DataCite GraphQL (deprecating Jul 2027), Wikidata scholarly subgraph (unstable), or the metered OpenAlex API for bulk fan-out.

Sources: all URLs are inline above; the highest-value five to read first are [Wanzenböck et al., QSS 2020](https://direct.mit.edu/qss/article/1/3/1136/96101/), [ULTRA arXiv:2201.05646](https://arxiv.org/abs/2201.05646), [Kobren et al., KDD 2019](https://arxiv.org/abs/1905.11924), [SciMuse arXiv:2405.17044](https://arxiv.org/abs/2405.17044), and [The Ideation-Execution Gap arXiv:2506.20803](https://arxiv.org/abs/2506.20803).agentId: af4160018b38a01c6 (use SendMessage with to: 'af4160018b38a01c6', summary: '<5-10 word recap>' to continue this agent)
<usage>subagent_tokens: 134448
tool_uses: 20
duration_ms: 895571</usage>