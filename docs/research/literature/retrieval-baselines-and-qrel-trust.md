# What beats BM25, and how much to trust our LongEval-Sci result

Compiled 2026-08-06. Bears on C-010 (refuted), C-008, EXP-2026-08-002, and the §5 retrieval paper.

**Two conclusions, and they point in opposite directions:**

1. **Our result is normal and independently reproduced.** Tuned full-text BM25 swept the top three
   places in the official CLEF 2025 LongEval-Sci evaluation. The organizers' own 2026 dense
   baseline (Qwen3-Embedding-4B) loses to their own BM25 baseline on all three snapshots. This is
   not an implementation bug.
2. **We have not actually established that BM25 is better — only that we did not beat it.** The
   qrels are click-derived pseudo-labels from CORE's own production ranker, ~10 positives per
   query over ~870k documents, with no human assessment and no published judged@10. Two of our
   three snapshots have ~100 queries, below the detection floor for the effect sizes involved.
   And our fusion configuration is, independently, the documented worst case.

---

## Part 1 — What actually beats BM25

### 1.1 The baseline is genuinely strong, and BEIR's version was not weak

**Thakur et al., BEIR, NeurIPS 2021 D&B** (arXiv:2104.08663) — *"BM25 is a robust baseline and
re-ranking and late-interaction based models on average achieve the best zero-shot performances,
however, at high computational costs."* ColBERT beat BM25 on only **9 of 18** datasets.

The "BEIR's BM25 was misconfigured" claim is largely **false**, and the definitive check exists:
**Kamalloo, Thakur, Lassance, Ma, Yang & Lin, *Resources for Brewing BEIR*, SIGIR 2024**
(arXiv:2306.07471). Re-implemented in Anserini/Lucene, BM25 lands at **0.429** avg nDCG@10 over 18
datasets vs the original ~0.423.

| BM25 variant | Avg nDCG@10 (BEIR-18) |
|---|---|
| multifield (title/body separate) | **0.429** |
| flat (concatenated) | 0.424 |
| flat + BERT wordpiece tokenization | 0.404 |

The confound is **field structure and tokenization** (≤2.5 points), not k1/b — which they never
tune. BEIR used untuned Lucene defaults, so if anything BM25 there is *under*-tuned. Their verdict:
*"none of the models are viable as a replacement [for BM25] yet."*

⚠️ **Beware incompatible averages.** At least five "BEIR average" conventions circulate (18/15/13/9/8
datasets; BM25 = 0.423, 0.429, 43.7, 38.5, 43.42). Never compare across them. Reranking **depth**
(20/50/100/1000) also swings results 5–10 points and is usually unstated.

### 1.2 What wins, ranked by evidence quality

**Learned sparse retrieval — the most robust win in the literature.**

| Model | BEIR-13 | BEIR-18 |
|---|---|---|
| BM25 | 43.7 | 0.429 |
| uniCOIL (no expansion) | — | 0.428 |
| docT5query | — | 0.433 |
| ColBERTv2 | 49.7 | — |
| SPLADE++ CoCondenser-SelfDistil | 50.7 | 0.474 |
| **SPLADE-v3** | **51.7** | — |
| SPLADE++ + BM25 (sum fusion) | 52.1 | — |
| Contriever+SPLADE hybrid (min-max) | — | 0.493 |

Lassance et al., *SPLADE-v3* (arXiv:2403.06789) — meta-analysis over 44 query sets: significantly
better than BM25 on most; **only 3 query sets show a significant decrease.** Formal et al., SIGIR
2022 (arXiv:2205.04733). Thakur et al., SPRINT, SIGIR 2023: *"without external document expansion,
only SPLADEv2 and BT-SPLADE-L can significantly outperform the BM25 baseline on BEIR."*

On the four scientific BEIR sets, SPLADE-v3 vs BM25: TREC-COVID 74.8/65.6, NFCorpus 35.7/32.5,
SciFact 71.0/66.5, **SCIDOCS 15.8/15.8 (dead heat)**. Real but modest.

**Cross-encoder rerankers — reliable on average, near-useless on science.** BEIR BM25→BM25+CE
(MiniLM-L-6, top-100): **+0.053** on the 18-set mean. But the distribution matters enormously:
NQ +0.204, HotpotQA +0.104 versus **SciFact +0.023, NFCorpus +0.025, SCIDOCS +0.008**, and losses
on **Touché (−0.096)** and ArguAna (−0.004). Size dominates: monoT5 60M/220M/3B = 0.423/0.475/0.523
BEIR-18 — **a small cross-encoder does not automatically beat BM25.** Rosa et al.
(arXiv:2212.06121) also show BM25+monoT5 = GTR+monoT5 = 0.496: **a dense first stage buys nothing
once you rerank.**

**Late interaction.** ColBERTv2 (arXiv:2112.01488) BEIR-13 ≈ 49.7; SciFact 69.3, TREC-COVID 73.8,
NFCorpus 33.8, SCIDOCS 15.4. PLAID (arXiv:2205.09707) brings latency from 4568 ms → 352 ms on CPU.

**LLM rerankers.** RankGPT-4 53.68 BEIR-8 (vs BM25 43.42). RankLLaMA BEIR-13 43.7 → 56.6 — but
**NFCorpus goes 32.2 → 30.3 (7B) → 28.4 (13B)**, monotonically worse with scale. 2025–26 reasoning
rerankers (Rank1, CoLM 2025) win big on BRIGHT (14.8 → 29.4) but score **BEIR-9 40.9–41.7 vs
monoT5-3B's 44.7** — worse than a 2022 cross-encoder.

### 1.3 Is bge-small our problem? Partly, but not mainly

| Model | Params | Dim | MTEB v1 Retrieval |
|---|---|---|---|
| bge-small-en-v1.5 | 33.4M | 384 | **51.68** |
| bge-base-en-v1.5 | 109M | 768 | 53.25 |
| bge-large-en-v1.5 | 335M | 1024 | 54.29 |

**10× the parameters buys 2.6 points.** Two sharpening facts:

1. **bge-small is still the best model in its size class in 2026.** granite-embedding-small-r2 (47M,
   2025) = 50.9 BEIR-15, *below* it; arctic-embed-s = 51.98. The 384d tier has been flat for three
   years. Swapping small models gains nothing.
2. **Size is not the controlling variable.** e5-large-v2 (335M) = 50.6 BEIR-15, *below* bge-small.
   Qwen3-Embedding-0.6B (61.83) beats gte-Qwen2-7B (58.09). Portes et al. (arXiv:2508.17400):
   retrieval quality tracks **pretraining FLOPs, not parameters**.

**What would move us:** a size-class jump to a *modern* 300M–600M model — EmbeddingGemma-308M
(MTEB-v2 Retrieval 55.7) or **Qwen3-Embedding-0.6B (61.83)**, roughly +10 points over bge-small.
Not bge-base or bge-large.

Two structural limits worth knowing. **Dimensionality:** Weller et al. (Google DeepMind),
*On the Theoretical Limitations of Embedding-Based Retrieval*, arXiv:2508.21038, ICLR 2026 — top-k
capacity is bounded by the sign rank of the qrel matrix; free-embedding critical corpus size ≈500k
docs at d=512. Their LIMIT benchmark, Recall@100: **BM25 93.6, Gemini Embed (3072d) 10.0, Qwen3
Embed (4096d) 4.8.** BEIR average and LIMIT recall are *anti-correlated*. (Fairness note: on their
synonym variant BM25 drops >89% — *"lexical models are not a panacea."*) **Truncation:**
EmbeddingGemma MRL 768d 55.7 → 512d 54.0 → 256d 51.4 → 128d 46.0. At 384d we are near the knee.

### 1.4 Scientific text — and a category error to avoid

BM25 is unusually competitive here for the 2021 generation (BEIR nDCG@10 — TREC-COVID 0.656,
NFCorpus 0.325, SCIDOCS 0.158, SciFact 0.665, BioASQ 0.465, beating DPR/ANCE/TAS-B on all).
Brewing BEIR's mechanism: rare specialised terms are poorly represented in embedding space, while
sparse models retain lexical matching.

**But be honest about scope:** BMRetriever (EMNLP 2024, arXiv:2404.18443) shows E5-large-v2 (0.491),
BGE-Large (0.511), BMRetriever-2B (0.543) all clearly beating BM25 (0.451) on biomedical retrieval.
Scientific text was a failure mode for the *2021* dense generation, not for well-trained 2024+
embedders. bge-small-en-v1.5 is a 2023 model at the bottom of the size range.

**Domain-adapted scientific retrievers mostly do NOT beat BM25** — the most surprising verified
finding here. MedCPT (Jin et al., *Bioinformatics* 2023), trained on **255M PubMed click pairs**:

| | TREC-COVID | NFCorpus | BioASQ | SciFact | SCIDOCS | Avg |
|---|---|---|---|---|---|---|
| BM25 | 0.656 | 0.325 | 0.465 | 0.665 | 0.158 | **0.454** |
| MedCPT retriever | 0.697 | 0.340 | 0.332 | 0.724 | 0.123 | **0.443** |
| MedCPT full pipeline | 0.709 | 0.355 | 0.553 | 0.761 | 0.172 | 0.510 |

The retriever alone averages **below plain BM25**. Authors concede *"BM25 is a strong baseline that
is generalizable to biomedical IR tasks."* SPECTER2 is worse still (NFCorpus 0.228 vs 0.325).

**Do not use SPECTER2/SciNCL as a dense arm here.** They are citation-graph triplet models over
(paper, paper) pairs with **no text-query encoder in the training objective**. SPECTER's paper
contains no BM25 comparison and no ad-hoc IR evaluation. Medić & Šnajder (SDP@COLING 2022) is
decisive: as the candidate pool grows, **BM25 beats SPECTER at every pool size and beats SciNCL at
1M and 2M docs.** SciRepEval (EMNLP 2023) concedes *"BM25 outperformed both models across all the
domains except Computer Science and BioMed."*

### 1.5 Full text and the 512-token wall — probably our biggest under-examined lever

BGE-M3 (ACL Findings 2024, arXiv:2402.03216), MLDR long-document, avg nDCG@10 over 13 languages:

| Model | Max len | MLDR |
|---|---|---|
| **BM25** (XLM-R tokenizer) | 8192 | **53.6** |
| mDPR / mContriever / mE5-large | **512** | 23.5 / 31.0 / 34.2 |
| text-embedding-ada-002 | 8191 | 32.5 |
| M3 Dense | 8192 | 52.5 |
| M3 All (3 heads) | 8192 | 65.0 |

**Every 512-token dense retriever loses to BM25 by 19–30 points.** M3's own dense head still loses.
And with a proper Lucene analyzer instead of XLM-R tokenization, **BM25 jumps 53.6 → 64.1**.

`bge-small-en-v1.5` has a 512-token limit. The LongEval-Sci winners used **full text**. On full-text
scientific papers, whatever chunking we do discards cross-chunk evidence while BM25 sees the whole
document. This alone can account for a large part of the gap and is a *field mismatch*, not a
retrieval-quality finding.

### 1.6 Our RRF configuration is the most fixable defect

**k=60 has almost no authority.** Cormack, Clarke & Büttcher, SIGIR 2009, verbatim: *"k = 60 was
fixed during a pilot investigation and not altered during subsequent validation"* and *"k = 60 was
near-optimal, but that the choice was not critical."* The full empirical basis:

| k | 0 | 20 | 40 | **60** | 70 | 80 | 100 | 500 |
|---|---|---|---|---|---|---|---|---|
| MAP | .2072 | .2134 | .2138 | **.2145** | .2146 | **.2147** | .2142 | .2098 |

k=60 was **not the argmax** (k=80 was), was tuned once on one 1990s TREC run, reports **MAP only**,
and — decisively — was tuned for fusing **30 system variants, not 2**. Its stated purpose,
*"mitigates the impact of high rankings by outlier systems,"* presupposes a majority to be an
outlier from. With two arms there is no majority.

**Bruch, Gai & Ingber, *An Analysis of Fusion Functions for Hybrid Retrieval*, ACM TOIS 41(4), 2023**
(arXiv:2210.11934) is the definitive reference. NDCG@1000:

| Dataset | Convex comb. (α=0.8) | RRF(60,60) | RRF(5,5) |
|---|---|---|---|
| MS MARCO | **0.454** | 0.425 | 0.435 |
| SciFact | **0.753** | 0.730 | 0.738 |
| NFCorpus | **0.327** | 0.312 | 0.318 |
| FiQA | **0.496** | 0.464 | 0.470 |

**k=5 beats k=60 on 8 of 9 datasets** — the canonical k is far too *large* for two systems. A tuned
convex combination beats RRF **significantly on 9/9 (p<0.01)** and α converges on *"less than 5% of
the training data."* Their formal account: RRF has an effectively unbounded Lipschitz constant (a
discontinuous jump the instant two scores cross); a bounded convex combination degrades gracefully.

(Live disagreement: Chen et al., ECIR 2022, arXiv:2201.10582 found RRF beating interpolation. The
reconciling variable is **metric** — see below.)

**Hybrid genuinely hurts, and the condition is quantified.** Wang et al., *Balancing the Blend*,
arXiv:2508.01405 (PVLDB 2025) — the **"weakest link" phenomenon**:

> *"A low-accuracy path can pollute the candidate pool with irrelevant documents, causing the hybrid
> system to underperform its best constituent path... this degradation, **originating in the
> candidate generation phase, is difficult to mitigate at the re-ranking stage**... Moreover,
> **simply increasing the candidate list size fails to resolve the issue**."*

**Break-even ≈ 1.4× arm-strength ratio**, converged on by two independent papers. Abdallah et al.,
SIGIR 2026 (arXiv:2604.03676): *"Linear Fusion with BM25 is a reliable, zero-cost upgrade for any
dense retriever scoring below ~20 nDCG@10 on BRIGHT, but should be avoided for top-tier models."*
Wang et al.'s ratios: 1.02× → +18.5%; 1.30× → +0.012; **1.44× → ~0 to −0.018; 1.55× → −0.040;
2.45× → −0.215.**

**The metric split is the other half.** Li et al., SIGIR 2022, *To Interpolate or not to
Interpolate* — on the *same runs*, λ=0.5 BM25 interpolation costs **1.4–3.6 nDCG@10 points while
gaining 2.2–4.9 Recall@1000 points.** Nearly every "hybrid always helps" claim in the wild is a
**recall** claim. We measure nDCG@10 — the exact quantity fusion damages.

> **Our stack sits at the textbook worst case on all four axes simultaneously:** rank-based fusion
> (most damage-prone family), k=60 (over-flattening for 2 arms), unequal arm strength (plausibly
> past 1.4×), evaluated on nDCG@10 (the metric that exposes it). This is the industry default, and
> the industry default is wrong for this regime.

---

## Part 2 — How much to trust the LongEval-Sci result

### 2.1 How the qrels are actually built

**LongEval-Web (Qwant)** — Galuščáková et al., SIGIR 2023 (arXiv:2303.03229). No human assessors.
Simplified DBN with session length 1, *"which comes down to the original Cascade Model."* The
estimator is a raw conditional CTR, graded 0/1/2 via inverting the ERR gain function. **~14
assessments per query.** The organizers publish the hole rate themselves: *"in average there are
only **2 or 3 assessed documents in the top 10** retrieved documents and only around 7 assessed
documents in the top 100."* Human pooled assessments were promised for summer 2023; no evidence
they were ever delivered.

**LongEval-Sci (CORE)** — CLEF 2025 overview (arXiv:2509.17469). The entire qrel methodology is
three sentences: *"the relevance judgments were created using a click model, based on click signals
from user logs (e.g., **PDF downloads**)"*, with *"additional negative, **randomly selected**
scientific articles."*

Verified: **click-derived, no human assessors, no pooling of participant runs, no citation labels,
no LLM judgments in 2025.** (The words "assessor" and "pool depth" do not occur in the overview.)
2025 train: ~2M documents, **393 queries, 4,262 assessments → 10.8 judgments/query.**

**2026 snapshots** (`ir-datasets-longeval` README): *"`raw` qrels mark all clicked documents as
relevant"* and *"`dctr` qrels use the Document Click Through Rate as pseudo relevance label."*
snapshot-1 train = 869,902 documents, 100 queries, **8,772 DCTR rows / 1,183 raw rows** (Wu & Yang,
arXiv:2607.04088) → ~87.7 DCTR and ~11.8 raw rows per query. DCTR rows include grade-0, so the
*positive* count is close to the raw count: **~10 relevant documents per query over 870k, every one
surfaced by CORE's production ranker.**

> ⚠️ **Action item.** We report `2026/snapshot-1/train` with no `/raw` or `/dctr` suffix. The README
> lists all three as distinct tags and which the bare tag resolves to is undocumented. Wu & Yang
> found FT BM25 = 0.3302 (DCTR) vs 0.3637 (raw) — **a 10% relative swing from qrel choice alone.**
> Re-run under both and report both.

### 2.2 This is logging-policy bias, not classic pooling bias — and that is worse in one way

The classic story does not apply literally: qrels were **not** pooled from participant runs, so
there is no TREC-style "systems in the pool" advantage.

**Worse:** the judged set is the output of a **single ranker** — CORE's deployed search — at shallow
depth, rather than the union of dozens of diverse systems at depth 100. Zobel (SIGIR 1998) found
pools reusable *precisely because* they aggregate heterogeneous systems. A single-system pool has
none of that insurance. CORE is widely reported to run Elasticsearch/Lucene, i.e. BM25 by default —
**not verified from a primary source; treat as inference.** If true, our BM25 run and the
judgment-producing policy share a scoring function.

**Better:** injected negatives are *random*, not "top-ranked-by-lexical", so there is no systematic
*negative* bias against dense — only a systematic absence of positives outside CORE's reach.

**Net:** a dense/hybrid arm that surfaces a genuinely relevant paper CORE never displayed gets zero
credit and is scored as retrieving a non-relevant document. A lexical system is partly measuring
*"how well do I reproduce CORE's SERP"* — which is what BM25 is best at.

Canonical statement of the mechanism, Buckley, Dimmick, Soboroff & Voorhees, *Bias and the limits of
pooling for large collections*, Inf. Retr. 10(6), 2007: pools too shallow relative to collection
size *"favor relevant documents containing topic title words"*, and runs *"that do not have title
word emphasis ... will mostly retrieve unjudged documents."* That maps almost exactly onto us.

**Honest counterweight — cite it.** Voorhees, Soboroff & Lin, *Can Old TREC Collections Reliably
Evaluate Modern Neural Retrieval Models?*, arXiv:2201.11086 — re-pooled TREC-8 with transformer
runs; neural runs did retrieve unseen documents *"but the vast majority of those documents were not
relevant"*, and system rankings held at **Kendall τ > 0.99**. Caveat: TREC-8 pools were depth-100
unions of ~70 diverse systems, nothing like a 10-judgment single-ranker click pool.

**Supporting the concern:** Arabzadeh, Vtyurina, Yan & Clarke, *Shallow pooling for sparse labels*,
IRJ 25, 2022 — on MS MARCO (~1 known relevant/query), re-judging found assessors **consistently
preferred unjudged passages over the labelled "relevant" one.** Same regime as ours. Also Cai et al.,
CIKM 2022 (arXiv:2209.05072) on pooling bias creating false negatives in training; Fröbe et al.,
SIGIR 2023 (arXiv:2407.07790) where neural weakness on Touché was substantially a judgment-hole
artifact.

**Click-specific:** Deffayet, Thonet, Renders & de Rijke, *Evaluating the Robustness of Click Models
to Policy Distributional Shift*, ACM TOIS 41(4), 2023 — click models trained on logs from one
logging policy degrade sharply when evaluating rankers that differ from it. A dense retriever
differs from a BM25-ish production ranker; that *is* a policy distributional shift. Note the 2026
`dctr` qrels model **no position bias at all** — plain DCTR is the weakest model in Chuklin et al.'s
taxonomy — and `raw` does not debias whatsoever.

### 2.3 Official results — strong corroboration

**LongEval-Sci 2025 (CLEF overview Table 4), nDCG@10:**

| Run | 2024-11 | 2025-01 |
|---|---|---|
| BM25 k1=1.0 b=0.7, stop+stem, **fullText** | 0.102 | **0.292** |
| BM25 k1=0.2 b=0.8, stop+stem, fullText | 0.102 | 0.291 |
| BM25 k1=0.95 b=0.75, stop+stem, fullText | 0.103 | 0.290 |
| rm3-on-qrel-boost | 0.150 | 0.252 |
| ows-bm25 | **0.161** | 0.216 |
| BM25 + **ColBERTv2** reranker (same team as top runs) | 0.060 | **0.175** |
| **SBERT-MPNet** (dense) | 0.024 | 0.062 |
| **SciBERT** | 0.028 | 0.059 |
| **monoT5** reranker | 0.027 | **0.031** |

The same team's ColBERTv2 reranker scored **0.175 vs their own plain BM25's 0.292 — a 40% loss from
adding a reranker.** monoT5 was the *worst* run OpenWebSearch submitted (0.031 vs their 0.216 BM25).
TF-IDF (0.126) beat SBERT-MPNet (0.062) by 2×.

The one team claiming dense+cross-encoder beat lexical (EAIiIB/AGH Cracow) scored **0.041**
officially — their working notes reveal they filtered the 2M-doc corpus down to the ~4,262 qrel
documents first. **That same paper independently reports our exact finding: *"BM25 did not enhance
retrieval when fused with dense pipelines."***

**LongEval-Sci 2026 official baselines** (Wu & Yang, arXiv:2607.04088 Table 5):

| Model | S1 | S2 | S3 |
|---|---|---|---|
| `baseline-bm25` (title+abstract) | 0.270 | 0.236 | 0.140 |
| `baseline-qwen3-4b` (**dense**) | 0.228 | 0.189 | 0.125 |
| custom full-text BM25 | 0.275 | 0.239 | 0.153 |
| FT BM25 + temporal | **0.285** | **0.267** | **0.180** |

**The organizers' own dense baseline loses to their own BM25 baseline on all three snapshots.**

And their snapshot-1 diagnostics (DCTR, 100 queries) reproduce our pattern *including the recall
split*: FT BM25 nDCG@10 **0.3302** / R@1000 0.9245; **RRF(FT-BM25, Dense) 0.3175 / R@1000 0.9667**;
Qwen3 dense alone 0.2820 / 0.8613. **The hybrid loses at rank 10 and wins on recall** — the classic
hole signature. Our C-008 union-pool recall gains (+8.7%, +75–80%) fit this exactly.

Organizers' own conclusion: *"While established retrieval methods such as BM25 and Lucene remain
main building blocks, we notice a shift toward integrating advanced methods like chunk-based
indexing, neural reranking, and query expansion powered by large language models."*

### 2.4 Statistical power — two of our three snapshots cannot support a conclusion

Query counts: `2026/snapshot-1/train` **100**, `2024-11` **99**, `2025-01` **492**.

Detectable difference for a paired test at α=0.05, 80% power, δ ≈ 2.80·σ_d/√n (σ_d for nDCG@10 on
sparse-qrel collections typically 0.15–0.25):

| n | σ_d = 0.15 | σ_d = 0.20 | σ_d = 0.25 |
|---|---|---|---|
| 99–100 | 0.042 | 0.056 | 0.070 |
| 492 | 0.019 | 0.025 | 0.032 |

**At n≈100 we cannot reliably detect anything under ~0.04–0.06 nDCG@10.** Wu & Yang's FT BM25 vs
hybrid gap of **0.013** is far below that floor, and they concede *"We do not yet report paired
significance tests."* Compute σ_d from our own per-query scores rather than this table.

Also: the lab reports snapshot-to-snapshot system-ranking correlation on Sci at only **Kendall
τ = 0.500** (vs 0.89–0.93 on Web). Single-snapshot deltas on this collection are noisy by the
organizers' own measurement. Guidance: Sakai, *Topic set size design*, IRJ 19(3), 2016; Sakai,
*Laboratory Experiments in IR*, Springer 2018; Voorhees & Buckley, SIGIR 2002; Urbano, Lima &
Hanjalic, SIGIR 2019 (recommends paired bootstrap/permutation over the t-test).

### 2.5 Task and topic quality — the organizers concede a problem

The 2025 overview publishes **almost nothing** about LongEval-Sci query characteristics: no length
distribution, no query-type taxonomy, no language statement. Queries are real CORE user queries from
server logs, bot-filtered — short keyword academic-search queries, not TREC-style topics.

**The organizers themselves flag this as a reliability defect.** LongEval 2026 Task 2
(LongEval-TopEx) exists precisely because *"When queries are extracted from query logs, none of
those formalization exists **which can reduce the reliability of a derived offline evaluation
collection** (because the subjectivity of relevance judgments is increased)."* Cite this.

Wu & Yang also found *"important relevance evidence often appears outside the abstract"* — full-text
BM25 consistently beat title+abstract BM25. If our dense arm embeds title+abstract only, we are
**field-mismatched** against a full-text lexical baseline.

### 2.6 What could not be determined

1. Which specific click model produced the **2025** Sci qrels (only "a click model" is stated).
2. **judged@10, unjudged rate, or grade distribution for any LongEval-Sci snapshot** — not published
   by organizers or in any working note. This is the biggest measurable gap.
3. Whether the bare `snapshot-1/train` tag resolves to `raw` or `dctr`.
4. Whether LongEval-Web's promised human pooled assessments were ever produced.
5. Whether the 2026 LLM-judged pooled qrels have been released.
6. CORE's production ranking stack (the Elasticsearch/BM25 assumption is inference).

---

## Part 3 — What to do before publishing

**Diagnostics, in priority order.** All cheap, all currently missing.

1. **`judged@10` per arm** (`ir_measures` `Judged@10`). If the dense/hybrid arms have materially
   lower judged@10 than BM25, the comparison is confounded. **This is the decisive test.**
2. **Condensed-list nDCG@10** (Sakai, SIGIR 2007, *Alternatives to bpref*): strip unjudged documents
   from every run, recompute. If BM25's lead collapses, the lead was hole-driven.
3. **bpref** and **infAP/infNDCG** as secondary robustness checks (Buckley & Voorhees, SIGIR 2004;
   Yilmaz & Aslam, CIKM 2006).
4. **Run both `raw` and `dctr` qrels** and report both — a 10% relative swing is documented.
5. **Per-query scores + paired bootstrap tests** with Holm correction (already flagged as W-work).
6. **Sample 30–50 top-10 unjudged documents** from the hybrid arm and judge them, disclosed as
   manual or LLM-assisted (MacAvaney & Soldaini, SIGIR 2023; Abbasiantaeb et al. 2024).
7. **Report Recall@1000 alongside nDCG@10.** We likely find fusion helps recall while hurting
   precision — the documented signature, and it reframes C-008 as a coherent story rather than an
   isolated positive.

**Fixes, in order of return on effort.**

1. **Tune BM25 properly.** The winning LongEval runs were BM25 with tuned k1/b, stopwords, stemming,
   **full text**. `rank_bm25.BM25Okapi` with defaults and an ad-hoc tokenizer is a different, weaker
   system than Lucene BM25 with an English analyzer. Tokenization alone is worth 2.5 nDCG points on
   BEIR and **10.5 points on long documents**. Zero cost, highest ROI — and note this cuts *against*
   us: a reviewer will say we compared against a weak version of our own baseline too.
2. **Fix the fusion.** Sweep k (expect k≈5 ≫ k=60 for 2 arms); use per-system k to discount the weak
   arm; better, switch to a min-max-normalized convex combination and fit α on <5% of a train split.
   Measure both arms separately first — **if BM25/dense > ~1.4×, expect fusion to be net-negative
   and skip it.**
3. **Address the 512-token / full-text mismatch** before drawing conclusions about dense retrieval.
4. **If a model change is warranted, jump size class** (Qwen3-Embedding-0.6B, EmbeddingGemma-308M),
   not to bge-base/large. Or move to **SPLADE-v3**, which stays on an inverted index and is the most
   robust published win over BM25.

**Recommended framing for the paper:**

> BM25's advantage over dense and hybrid arms on LongEval-Sci is **real and independently
> reproduced** — the organizers' own Qwen3-Embedding-4B baseline loses to their own BM25 baseline on
> all three 2026 snapshots, and tuned full-text BM25 swept the top three places in the official CLEF
> 2025 Sci evaluation. However, LongEval-Sci qrels are **pseudo-relevance labels derived from
> clicks/downloads on CORE's production search results**, with roughly 10 positives per query over
> an 870k-document corpus, no human assessment, no participant pooling, and no published judged@10.
> The judged set is the output of a single, probably-lexical logging policy, which structurally
> cannot credit a retriever that surfaces relevant documents CORE never displayed. Combined with
> 99–100 queries on two of three snapshots — below the ~0.04–0.06 nDCG@10 detection floor — the
> correct conclusion is: **"BM25 is not beaten here, and we cannot yet tell how much of that is
> retrieval quality versus judgment provenance."**

That is a stronger and more publishable claim than either "our stack loses" or "BM25 wins". It is
also the reproducibility-track thesis: **the field keeps reproducing a lexical win on a collection
whose labels were generated by a lexical system, and nobody has measured the hole rate.**

---

## Sources

[BEIR (NeurIPS 2021)](https://arxiv.org/abs/2104.08663) ·
[Resources for Brewing BEIR (SIGIR 2024)](https://arxiv.org/abs/2306.07471) ·
[LongEval CLEF 2025 overview](https://arxiv.org/abs/2509.17469) ·
[LongEval CLEF 2024 overview](https://ceur-ws.org/Vol-3740/paper-213.pdf) ·
[LongEval-Retrieval (SIGIR 2023)](https://arxiv.org/pdf/2303.03229) ·
[ir-datasets-longeval README](https://github.com/clef-longeval/ir-datasets-longeval) ·
[LongEval 2026 tasks page](https://clef-longeval.github.io/tasks/) ·
[Wu & Yang, Full-Text Temporal Retrieval for LongEval-Sci (CLEF 2026)](https://arxiv.org/abs/2607.04088) ·
[AGH IR at LongEval 2025](https://ceur-ws.org/Vol-4038/paper_276.pdf) ·
[RRF (SIGIR 2009)](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf) ·
[Bruch et al., Fusion Functions for Hybrid Retrieval (TOIS 2023)](https://arxiv.org/abs/2210.11934) ·
[Balancing the Blend (PVLDB 2025)](https://arxiv.org/abs/2508.01405) ·
[To Interpolate or not to Interpolate (SIGIR 2022)](https://cs.uwaterloo.ca/~jimmylin/publications/Li_etal_SIGIR2022.pdf) ·
[Out-of-Domain Semantics to the Rescue (ECIR 2022)](https://marc.najork.org/papers/ecir2022.pdf) ·
[Are LLM-Based Retrievers Worth Their Cost? (SIGIR 2026)](https://arxiv.org/abs/2604.03676) ·
[SPLADE++ (SIGIR 2022)](https://arxiv.org/abs/2205.04733) ·
[SPLADE-v3](https://arxiv.org/abs/2403.06789) ·
[SPRINT (SIGIR 2023)](https://arxiv.org/abs/2307.10488) ·
[ColBERTv2 (NAACL 2022)](https://arxiv.org/abs/2112.01488) ·
[PLAID (CIKM 2022)](https://arxiv.org/abs/2205.09707) ·
[RankGPT (EMNLP 2023)](https://arxiv.org/abs/2304.09542) ·
[RankLLaMA (SIGIR 2024)](https://arxiv.org/abs/2310.08319) ·
[In Defense of Cross-Encoders](https://arxiv.org/abs/2212.06121) ·
[Rank1 (CoLM 2025)](https://arxiv.org/abs/2502.18418) ·
[BGE-M3 (ACL Findings 2024)](https://arxiv.org/abs/2402.03216) ·
[MedCPT (Bioinformatics 2023)](https://arxiv.org/abs/2307.00589) ·
[Medić & Šnajder (SDP@COLING 2022)](https://aclanthology.org/2022.sdp-1.3/) ·
[SciRepEval (EMNLP 2023)](https://arxiv.org/abs/2211.13308) ·
[BMRetriever (EMNLP 2024)](https://arxiv.org/abs/2404.18443) ·
[Theoretical Limitations of Embedding-Based Retrieval (ICLR 2026)](https://arxiv.org/abs/2508.21038) ·
[Retrieval Scales with Pretraining FLOPs](https://arxiv.org/abs/2508.17400) ·
[bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5) ·
[Buckley & Voorhees, Retrieval evaluation with incomplete information (SIGIR 2004)](https://dl.acm.org/doi/10.1145/1008992.1009000) ·
[Buckley et al., Bias and the limits of pooling (IRJ 2007)](https://link.springer.com/article/10.1007/s10791-007-9032-x) ·
[Sakai, Alternatives to Bpref (SIGIR 2007)](https://dl.acm.org/doi/10.1145/1277741.1277756) ·
[Arabzadeh et al., Shallow pooling for sparse labels (IRJ 2022)](https://link.springer.com/article/10.1007/s10791-022-09411-0) ·
[Voorhees, Soboroff & Lin, Can Old TREC Collections Reliably Evaluate Modern Neural Retrieval Models?](https://arxiv.org/abs/2201.11086) ·
[Fröbe et al., Touché 2020 BEIR subset (SIGIR 2023)](https://arxiv.org/pdf/2407.07790) ·
[Cai et al., Hard Negatives or False Negatives (CIKM 2022)](https://arxiv.org/pdf/2209.05072) ·
[Deffayet et al., Robustness of Click Models to Policy Shift (TOIS 2023)](https://dl.acm.org/doi/10.1145/3569086) ·
[MacAvaney & Soldaini, One-Shot Labeling (SIGIR 2023)](https://dl.acm.org/doi/10.1145/3539618.3592032) ·
[Sakai, Topic set size design (IRJ 2016)](https://link.springer.com/article/10.1007/s10791-015-9273-z) ·
[Urbano et al., Statistical Significance Testing in IR (SIGIR 2019)](https://arxiv.org/pdf/1905.11096)
