# Academic Venue & Conference Recommendation — Survey

Compiled 2026-08-06. Raw survey; synthesis and Mycelium-specific implications in
[`SYNTHESIS.md`](SYNTHESIS.md).

Tags: **[PR]** peer-reviewed · **[PP]** preprint only · **[TOOL]** commercial/production
service · **[INF]** inference from the evidence gathered.

---

## 1. Field shape

Small, fragmented, method-driven. The only dedicated systematic review covers 32 papers through
2018 and volume has not exploded since. Two nearly non-communicating communities:

- **CS/recsys track** — DBLP/AMiner, offline metrics, conference-oriented, content + co-author
  + graph methods.
- **Biomedical/LIS/publisher track** — journal finders, PubMed/DOAJ, deployed as web tools,
  evaluated (if at all) by top-k accuracy against the actual journal of publication.

Thin or absent: deadline modelling, acceptance-probability modelling, LLM-native venue
recommendation, venue-specific popularity-bias analysis, and any critical treatment of "actual
venue" as ground truth.

---

## 2. Surveys

**Dehdarirad, Ghazimirsaeid & Jalalimanesh (2020). *Scholarly publication venue recommender
systems: A systematic literature review*, Data Technologies and Applications 54(2):169–191**
[PR], DOI 10.1108/DTA-08-2019-0135. The only dedicated venue-rec SLR. Kitchenham protocol,
coverage to 2018-08-11, **N=32**. Most-used data: textual (title/abstract/keywords) and
co-authorship. CB/CF/hybrid used almost equally. **DBLP the main dataset.** Cosine similarity,
SNA, TF-IDF the most frequent algorithms. **24 of 32 papers applied only offline evaluation.**
Precision/accuracy/recall dominant. Stated future directions in the corpus were shallow — "use
more datasets", "new algorithms" — itself a diagnostic that the field's own open problems are
not research-quality problem statements.

**Kreutz & Schenkel (2022). *Scientific paper recommendation systems: a literature review of
recent publications*, IJDL 23(4):335–369** [PR] (arXiv:2201.00682). Paper-rec focused; the
evaluation-methodology critique is the useful part (§7).

***Scholarly recommendation systems: a literature survey*, KAIS (2023)** [PR]. Broadest
taxonomy: literature, **venue**, dataset, grant, and collaborator recommendation from 225
publications. Technical taxonomy: CBF, CF, hybrid, graph-based, statistical/mathematical, IR,
optimization. **Taxonomic finding relevant here: CBF and hybrids dominate journal
recommendation; CF is disproportionately prevalent in *conference* recommendation; IR and
optimization dominate reviewer recommendation.**

**Ajmal & Muzammil (2019). *PVRS: Publication Venue Recommendation System — A Systematic
Literature Review*, ICCED 2019** [PR], DOI 10.1109/icced46541.2019.9161106. Second, smaller SLR.

**Pinedo, Larrañaga & Arruarte (2025/2026). *Recent Advances and Trends in Research Paper
Recommender Systems*, arXiv:2508.08828** [PP]. Covers Nov 2021–Dec 2024. Paper-rec, not
venue-rec. **No venue-recommendation-specific survey covering 2019–2026 exists.**

***Biases in Scholarly Recommender Systems: Impact, Prevalence, and Mitigation*, Scientometrics
(2023)** [PR], arXiv:2301.07483. Separates human-origin from system-induced bias; proposes a
mitigation/fair-evaluation framework. Closest principled bias treatment, though scholarly-rec-
wide rather than venue-specific.

---

## 3. Method families

### Content-based (dominant)
- Medvet, Bartoli & Piccinin (2014). *Publication Venue Recommendation Based on Paper Abstract*,
  **ICTAI 2014**, 1004–1010 [PR]. Canonical abstract-only baseline (topic-based).
- Wang, Liang, Xu, Feng & Guan (2018). *A content-based recommender system for computer science
  publications*, **Knowledge-Based Systems** 157:1–9 [PR].
- Feng et al. (2019). **Pubmender**, *The Deep Learning–Based Recommender System 'Pubmender' for
  Choosing a Biomedical Publication Venue*, **JMIR** 21(5):e12957 [PR]. word2vec init + deep CNN
  over abstract + softmax over PubMed journals. Reported top-10 accuracy improvements of
  87.0%/22.9%/196.0% over Microsoft Academic Search / ACM / CiteSeer. *Caveat: relative
  improvements over weak baselines, not absolute accuracy.*
- de Campos, Fernández-Luna & Huete (2022). *Publication Venue Recommendation Using Profiles
  Based on Clustering*, **IEEE Access** 10:106886 [PR] (arXiv:2401.10611). Per-venue topical
  profiles via clustering, IR-style matching.
- de Campos, Fernández-Luna & Huete (2026). *Combining content information with collaborative
  filtering for publication venue recommendation*, **KAIS**, online 2026-04-15 [PR],
  DOI 10.1007/s10115-026-02749-7. **The most recent peer-reviewed venue-rec paper located.**
- Badieah et al. (2024). *Leveraging Transformer-Based Topic Modeling using BERTopic for
  Publication Venue Recommendation*, **EECSI 2024** [PR]. BERTopic swap-in for LDA.
- *Recommendation method for academic journal submission based on doc2vec and XGBoost*,
  **Scientometrics** (2022) [PR].

### Style / writing-signal (near-singleton)
- Yang & Davison (2012). *Venue Recommendation: Submitting Your Paper with Style*, **ICMLA 2012**,
  681–686 [PR]. CF over neighbouring papers using **both topic and writing-style features**;
  evaluated on ACM and CiteSeer. Still the main citation for style-as-signal, with essentially
  **no follow-up**.

### Co-author / social / collaborative
- Klamma, Pham & Cao (2009). *You Never Walk Alone: Recommending Academic Events Based on Social
  Network Analysis*, **Complex 2009**, 657–670 [PR]. Origin of event/conference recommendation
  via SNA.
- Luong, Huynh, Gauch, Do & Hoang (2012). *Publication Venue Recommendation Using Author
  Network's Publication History*, **ACIIDS 2012**, LNCS 7198:426–435 [PR].
- *Exploiting Social Networks for Publication Venue Recommendations*, **KDIR 2012** [PR].
- Yu et al. (2018). **PAVE**: *Personalized Academic Venue recommendation Exploiting
  co-publication networks*, **JNCA** 104:38–47 [PR]. Heavily cited reference point.
- Alhoori & Furuta (2017). *Recommendation of scholarly venues based on dynamic user interests*,
  **Journal of Informetrics** 11(2):553–563 [PR] (arXiv:1612.05817). Distinctive: derives an
  **implicit venue rating from researchers' reading/bookmarking behaviour**, explicitly to serve
  new researchers with no publication history and emerging venues with no impact factor. One of
  the few papers treating "no impact factor yet" as a design constraint.

### Graph / random-walk / heterogeneous-network embedding
- Chen, Xia, Jiang, Liu & Zhang (2015). **AVER**: *Random Walk Based Academic Venue
  Recommendation*, **WWW '15 Companion**, 579–584 [PR].
- Pradhan & Pal (2020). **CNAVER**: *A Content and Network-based Academic VEnue Recommender
  system*, **Knowledge-Based Systems** 189:105092 [PR].
- Pradhan, Gupta & Pal (2020). **HASVRec**: *A modularized Hierarchical Attention-based Scholarly
  Venue Recommender system*, **KBS** 204:106181 [PR]. Bi-LSTM + hierarchical attention over
  title/abstract/keywords/FoS/author, on **DBLP-Citation-Network V11**. Reports accuracy, F1,
  nDCG, MRR, **average venue quality, and stability** — notable for going beyond accuracy.
- Pradhan et al. (2020). *A hybrid personalized scholarly venue recommender system integrating
  social network analysis and contextual similarity*, **FGCS** [PR].
- Iana & Paulheim (2021). **GraphConfRec**: *A Graph Neural Network-Based Conference Recommender
  System*, **JCDL 2021** [PR] (arXiv:2106.12340). SciGraph + GNN over title/abstract **plus
  co-authorship and citation edges**. **recall@10 up to 0.580, MAP up to 0.336** with a
  GAT-based model, plus a 25-subject user study — one of very few venue-rec papers with any user
  study.
- **metapath2vec** (Dong, Chawla & Swami, **KDD 2017**) [PR]. *Important nuance:* it does venue
  node **classification** on AMiner CS, not venue recommendation. Venue-rec papers borrow the
  meta-path random-walk machinery. Treat "metapath2vec for venue rec" as a method transfer.
- **ogbn-mag** (Open Graph Benchmark, Hu et al. 2020) [PR], arXiv:2005.00687. **Venue prediction
  as a 349-class classification problem** over MAG. The closest thing to a standardized,
  leaderboard-backed venue-prediction benchmark — framed as node classification, not top-k
  recommendation, and **not used by the venue-rec literature.** [INF] Bridging ogbn-mag to
  venue rec is an obvious, unexploited move.

### LLM-based — **thin, flag**
Essentially one dedicated peer-reviewed item:
- Chen, Liu, Pan, Yu & Chen (2026). **TEEVRec**: *Tuple Embedding Enhancement by Heterogeneous
  Information Network Mining and LLM-Driven Knowledge Augmentation for Venue Recommendation*,
  **ICIC 2026**, CCIS/Springer, 464–476 [PR], DOI 10.1007/978-981-92-3563-6_38. Positions against
  CNAVER/HASVRec/PAVE/PUB-VEN. *Caveat: verified via Crossref metadata only; full text not
  retrieved; zero citations as of indexing.*

Adjacent: *The Unique Taste of LLMs for Papers: Potential Issues in Using LLMs for Digital
Library Document Recommendation Tasks*, arXiv:2409.19868 [PP] — documents systematic LLM
preference idiosyncrasies in scholarly document recommendation; directly transferable warning.
LLM-recsys surveys (arXiv:2305.19860, arXiv:2412.13432) [PP] contain **no venue-rec coverage.**

[INF] **There is no LLM-native venue recommender with a serious evaluation as of Aug 2026. No
"GPT-4 vs. journal finder" benchmark study. This is the single largest open gap in the field.**

---

## 4. Commercial / production tools [TOOL]

| Tool | Basis |
|---|---|
| Elsevier Journal Finder | **BM25** over ~1M similar articles, scores averaged per journal |
| JANE (Journal/Author Name Estimator) | **Lucene MoreLikeThis**, top-50 similar PubMed articles, scores summed per journal and normalized |
| Springer Nature Journal Suggester | undisclosed text similarity, publisher-locked catalogue |
| IEEE Publication Recommender | undisclosed |
| Wiley Journal Finder, Charlesworth ASJF, Edanz JS, Researcher JF | undisclosed |
| **B!SON** | title + abstract + **references**; similarity to published articles. **Open source, open data (DOAJ + OpenCitations Meta), open API, publisher-independent, cross-domain, OA-only.** TIB Hannover + SLUB Dresden |

**The evaluation paper:** Entrup, Ewerth & Hoppe (2023). *A Comparison of Automated Journal
Recommender Systems*, **TPDL 2023**, LNCS 14241 [PR], DOI 10.1007/978-3-031-43849-3_20. Compares
input values, functionality, privacy; quantitative analysis of result overlap and accuracy.
Headline: **due to providers' lack of transparency about the technologies used, the results
cannot be easily interpreted** — motivating a call for openness about algorithms and datasets.
The strongest citable statement that the commercial layer is unevaluable.

Companions: *Comparing different search methods for the open access journal recommendation tool
B!SON*, **IJDL** (2023) [PR]; *B!SON: A Tool for Open Access Journal Recommendation* (2022) [PR].
Weaker: *Enhancing research publication choices: A comparative study of journal recommender
systems and their effectiveness*, **IJAAS** (2024) [PR, weak venue].

---

## 5. Datasets and benchmarks

**Used as venue-rec benchmarks:**
- **DBLP** — named by the SLR as *the* main dataset. Used bare or via AMiner enrichment.
- **AMiner DBLP-Citation-Network** — the workhorse. **V11** in HASVRec; **V12** (4,894,081
  papers / 45,564,149 citations) and **ACM-V10** (2,579,904 / 17,254,368) in the surrounding
  citation-rec literature. Preprocessing is non-trivial and non-standardized — see *AMiner
  Citation-Data Preprocessing for Recommender Systems on Scientific Publications* (2022) [PR].
- **CiteSeer/CiteSeerX + ACM DL** — Yang & Davison 2012; Pubmender baselines.
- **PubMed** — Pubmender; JANE's backing corpus.
- **Springer Nature SciGraph** — GraphConfRec. *(Note: SciGraph retired 2023.)*
- **DOAJ + OpenCitations Meta** — B!SON, the only fully-open-data venue recommender.
- **MAG → ogbn-mag** — venue prediction as 349-class classification.

**Notably absent — flag:**
- **S2ORC / S2AG** — **no venue-recommendation paper found using it as a benchmark**, despite
  being the natural modern choice (full text, clean venue normalization, permissive license).
  SPECTER/SPECTER2 (Cohan et al., ACL 2020) are used for *paper* tasks and venue *analysis*, not
  venue rec.
- **OpenAlex** — 209M works, ~124k venues, drop-in MAG replacement (Priem, Piwowar & Orr,
  arXiv:2205.01833). Used bibliometrically; **no venue-rec benchmark built on it.**

**Splits and temporal evaluation — flag, weak evidence.** Temporal splitting **is** established
in the neighbouring **citation** recommendation literature ("a temporal split ensures that
recommendations for test papers only include citations to earlier works, which is more realistic
than conventional random splits" — *Benchmark for Evaluation and Analysis of Citation
Recommendation Models*, arXiv:2412.07713 [PP]). For **venue** recommendation, no evidence that
temporal splitting is standard: the SLR reports 24/32 offline-only with precision/accuracy/recall
and no mention of temporal protocol, and there is **no shared benchmark split**. [INF] Random
splitting is likely the default, leaking future venue-topic drift into training — an unaddressed
methodological weakness and a defensible contribution area.

**WikiCFP and CFP datasets.** WikiCFP (wikicfp.com) is a wiki of CFPs with name, acronym, dates,
location, and **submission deadline**. Iana, Jung, Naeser, Birukou, Hertling & Paulheim (2019),
*Building a Conference Recommender System Based on SciGraph and WikiCFP*, **SEMANTiCS 2019**,
117–123 [PR] — **recall@10 up to 0.665, MAP up to 0.540** on author/abstract/keyword input.
Crucially, **linking SciGraph history to WikiCFP is what lets it recommend *upcoming*
conferences** rather than only historical venues — the key architectural idea for a
deadline-aware system. Crawl scales reported: 65,714 CFPs (Jul 2018), 4,902 CFPs (Jan 2020).
**No canonical, versioned, publicly redistributed WikiCFP dataset exists — every group
re-crawls. Building one would be a real contribution.**

Also noted: a conference recommender over a **1.5B-triple knowledge graph** integrating MAG,
Dimensions, DBpedia, GRID, CSO, INDUSO (~25M articles) [PR] — details thin; verify before citing.

---

## 6. Time, deadlines, acceptance rate, prestige — thinnest area

**Deadline modelling: essentially nonexistent.** The only mechanism found is the SciGraph→WikiCFP
link (Iana et al. 2019) filtering to *upcoming* conferences. **No paper models a deadline as a
constraint or optimization variable** (e.g. "given my paper is ready on date D, what is the best
reachable venue?"), and none models the sequential resubmission process. [INF] Wide open, and
notably it is the aspect authors actually reason about in practice.

**Fit-vs-prestige / multi-criteria — small but real:**
- Ajmal, Sarfraz, Memon, Bilal & Alam (2024). **PUB-VEN**: *a personalized recommendation system
  for suggesting publication venues*, **MTAP** 83(14):42103–42124 [PR]. CBF+CF hybrid **fused
  with Multi-Criteria Decision Making over impact factor, eigenfactor, and average review time**,
  weighted by the researcher's own stated priorities. The only work making speed and prestige
  first-class, author-weighted objectives.
- HASVRec / CNAVER report **"average venue quality"** — implicit acknowledgment that
  recommending only fitting-but-weak venues is a failure mode.
- Alhoori & Furuta (2017) argues explicitly *against* relying on impact factor.
- Li, Shao, Bian & Huang (2023), **IPM** 60(5):103460; Li, Shao & Bian (2024), **Applied Soft
  Computing** 163:111888 [PR] — multi-dimensional feature fusion for journal recommendation, the
  latter incorporating **scholars' personality traits**. Prestige as a feature, not a tradeoff
  axis.

**Acceptance probability: modelled, but as a separate task.** A live literature exists —
*Predicting Paper Acceptance via Interpretable Decision Sets*, **WWW '21 Companion**,
DOI 10.1145/3442442.3451370 [PR]; *Conference Paper Acceptance Prediction: Using Machine
Learning* (Springer 2021) [PR] — using features like reference count, figures/tables, title
length, ML-term frequency. [INF] **No paper couples an acceptance-probability model to a venue
recommender to produce an expected-value ranking, P(accept | paper, venue) × value(venue). That
composition is unbuilt and is arguably the most obviously valuable missing artifact.**

**A hard empirical constraint on the whole enterprise:** *Extracting Information About Publication
Venues Using Citation-Informed Transformers*, arXiv:2506.08199 (Jun 2025) [PP]. ~60,000 CS
documents, 2015–2023, nine well-known venues, SPECTER embeddings. **Some CS venues are
*indistinguishable* from the distributions of their document embeddings alone, and several venue
pairs are *converging over time*.** Content-only venue recommendation has a hard ceiling, and the
ceiling is tightening. Strong motivation for signals beyond text — deadlines, acceptance rates,
author history, prestige.

---

## 7. Evaluation weaknesses

**7a. Ground truth = actual published venue.** The near-universal offline protocol (24/32
offline-only). It conflates (i) topical fit, (ii) the author's strategic choice under
prestige/deadline/cost constraints, and (iii) the outcome of peer review, including prior
rejections invisible in the data. **No paper in the venue-rec literature states this critique
squarely.** The closest support is by analogy from citation recommendation, where the parallel
critique is well developed: Kreutz & Schenkel (2022) and Beel et al. — "ground-truths are
incomplete and contain only a fraction of relevant items"; if inferred from citations they suffer
**content, author, venue, timeliness, and access bias**; "even if a system recommends equally
valid or better papers, they will not be recognized as 'correct' if they were not cited." Also
Beel et al., *A Comparison of Offline Evaluations, Online Evaluations, and User Studies* [PR];
Castells & Moffat (2022), *Offline recommender system evaluation: Challenges and new directions*,
**AI Magazine** [PR].

[INF] **Writing the venue-specific version — "the observed venue is a *choice under constraints*,
not a relevance label" — is an unclaimed, citable contribution.** Concrete testable consequence:
any recommender trained on observed venues learns author prestige-seeking and self-selection, not
fit, and will systematically under-recommend venues an author *should* have targeted but didn't.

**7b. Popularity bias toward large venues.** The general literature is mature (Abdollahpouri et
al., arXiv:1901.07555, arXiv:2008.08551, arXiv:2103.06364; Klimashevskaia et al., *Information*
2025), and the scholarly-domain bias survey exists (Scientometrics 2023). **But zero papers
measure popularity/long-tail bias in venue recommenders specifically.** The venue-rec papers
report accuracy/F1/nDCG/MRR — no coverage, no Gini, no long-tail metrics. Structurally severe:
venue publication-volume distributions are extremely skewed (megajournals vs. small specialist
venues), so an accuracy-optimal model can win by memorizing venue priors. Pradhan et al.'s
"average venue quality" and "stability" are the only gestures beyond accuracy, and quality ≠
diversity.

**7c. Non-reproducibility of the commercial layer.** Entrup et al. (2023) is definitive. B!SON is
the only fully open counter-example.

**7d. No shared benchmark, split, or leaderboard.** Every paper builds its own DBLP/AMiner slice
with its own venue-count cutoff, minimum-papers-per-venue filter, and split. Cross-paper numbers
are not comparable. [INF]

---

## 8. Ranked gap list

1. **Deadline-/time-aware venue recommendation.** Zero prior art beyond WikiCFP filtering. CFP
   data exists but is uncurated.
2. **Expected-value ranking: acceptance-probability × venue value.** Both components exist
   independently; never composed.
3. **LLM-native venue recommendation with rigorous evaluation.** One 2026 paper uses LLMs as an
   augmentation module; no LLM-vs-classical benchmark exists.
4. **A standard, temporally-split, openly-licensed venue-rec benchmark** — natural build on
   OpenAlex or S2ORC, neither currently used. Plus a versioned WikiCFP corpus.
5. **Popularity/long-tail bias measurement in venue recommenders.** Literally unmeasured.
6. **The "observed venue ≠ relevance" critique, stated for venues.** Unwritten.
7. **A 2019–2026 venue-recommendation survey.** The only dedicated SLR stops at Aug 2018.

---

## Sources

[Scholarly publication venue recommender systems: SLR (DTA 2020)](https://www.emerald.com/insight/content/doi/10.1108/dta-08-2019-0135/full/html) ·
[Scholarly recommendation systems: a literature survey (KAIS 2023)](https://link.springer.com/article/10.1007/s10115-023-01901-x) ·
[Scientific paper recommendation systems (IJDL 2022)](https://arxiv.org/abs/2201.00682) ·
[Recent Advances in Research Paper Recommender Systems (arXiv:2508.08828)](https://arxiv.org/abs/2508.08828) ·
[Biases in Scholarly Recommender Systems (arXiv:2301.07483)](https://arxiv.org/abs/2301.07483) ·
[Venue Recommendation: Submitting Your Paper with Style (ICMLA 2012)](https://www.cse.lehigh.edu/~brian/pubs/2012/ICMLA/venue-recommendation.pdf) ·
[Publication Venue Recommendation Using Author Network's Publication History (ACIIDS 2012)](https://dl.acm.org/doi/10.1007/978-3-642-28493-9_45) ·
[Recommendation of Scholarly Venues Based on Dynamic User Interests (JOI 2017)](https://arxiv.org/abs/1612.05817) ·
[PAVE (JNCA 2018)](https://doi.org/10.1016/j.jnca.2017.12.004) ·
[Pubmender (JMIR 2019)](https://www.jmir.org/2019/5/e12957/) ·
[HASVRec (KBS 2020)](https://www.sciencedirect.com/science/article/abs/pii/S0950705120304135) ·
[Hybrid personalized scholarly venue recommender (FGCS 2020)](https://www.sciencedirect.com/science/article/abs/pii/S0167739X19307101) ·
[PUB-VEN (MTAP 2024)](https://link.springer.com/article/10.1007/s11042-023-16798-5) ·
[Venue recommendation using profiles based on clustering (IEEE Access 2022)](https://arxiv.org/abs/2401.10611) ·
[TEEVRec (ICIC 2026)](https://doi.org/10.1007/978-981-92-3563-6_38) ·
[GraphConfRec (JCDL 2021)](https://arxiv.org/abs/2106.12340) ·
[SciGraph + WikiCFP conference recommender (SEMANTiCS 2019)](https://2019.semantics.cc/building-conference-recommender-system-based-scigraph-and-wikicfp) ·
[WikiCFP](http://www.wikicfp.com/cfp/) ·
[A Comparison of Automated Journal Recommender Systems (TPDL 2023)](https://link.springer.com/chapter/10.1007/978-3-031-43849-3_20) ·
[Comparing search methods for B!SON (IJDL 2023)](https://link.springer.com/article/10.1007/s00799-023-00372-3) ·
[Extracting Information About Publication Venues (arXiv:2506.08199)](https://arxiv.org/abs/2506.08199) ·
[SPECTER (ACL 2020)](https://aclanthology.org/2020.acl-main.207/) ·
[metapath2vec (KDD 2017)](https://ericdongyx.github.io/metapath2vec/m2v.html) ·
[Open Graph Benchmark / ogbn-mag](https://arxiv.org/pdf/2005.00687) ·
[OpenAlex (arXiv:2205.01833)](https://arxiv.org/abs/2205.01833) ·
[Benchmark for Citation Recommendation Models (arXiv:2412.07713)](https://arxiv.org/pdf/2412.07713) ·
[Offline recommender system evaluation (AI Magazine 2022)](https://onlinelibrary.wiley.com/doi/10.1002/aaai.12051) ·
[Offline vs Online Evaluations vs User Studies (Beel et al.)](https://docear.org/papers/A%20Comparison%20of%20Offline%20Evaluations,%20Online%20Evaluations,%20and%20User%20Studies%20...%20(preprint).pdf) ·
[Popularity Bias in Recommender Systems (Information 2025)](https://www.mdpi.com/2078-2489/16/2/151) ·
[The Unique Taste of LLMs for Papers (arXiv:2409.19868)](https://arxiv.org/pdf/2409.19868)
