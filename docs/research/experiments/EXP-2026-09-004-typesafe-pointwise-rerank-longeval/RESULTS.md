# EXP-2026-09-004 — Results

**Collection:** LongEval-Sci, `longeval-sci-2026/snapshot-1/train`, pooled scope
(84,489 documents from the frozen id list), **100 queries**. **Qrels:** `dctr` —
click-model-derived pseudo-relevance, **not human assessment**. **Model:**
TypeSafe `jev-1.13.0`, pinned. **Runs:** 1 per arm; a paired bootstrap over
query ids gives the intervals. Every number below is read from
`data/paired.json`, `data/discrimination.json`, `data/determinism.json` and the
harness result files named in §8; the tables are generated, not typed.

## 1. The headline

`typesafe_noul` over BM25's top 20 scores **+0.0185 nDCG@10 above BM25 alone**
(0.3397 vs 0.3212), 43 queries better, 36 worse, 21 tied — and the 95 % paired
interval is **[−0.0207, +0.0603]**, which spans zero. The primary hypothesis is
**falsified on its pre-registered criterion**, and C-027 is marked refuted. It is
nonetheless the first reranker in this record whose delta against BM25 is
**positive in every query-length bucket**, including the one- and two-word
queries where the cross-encoder was significantly harmful.

## 2. Results table

<!-- BEGIN GENERATED TABLE -->
See [`tables/paired.md`](tables/paired.md) for the contrasts with intervals
and the query-length split, and [`tables/discrimination.md`](tables/discrimination.md)
for the C-016 measurements and the agreement between the two arms.
<!-- END GENERATED TABLE -->

**Absolute, this host, one corpus build** (`n = 100`):

| Arm | nDCG@10 | nDCG@100 | AP | RR | P@10 | R@100 |
|---|---:|---:|---:|---:|---:|---:|
| `bm25_only` (pooled) | 0.3212 | 0.4314 | 0.2760 | 0.4788 | 0.2100 | 0.6903 |
| `typesafe_noul` over bm25, w20 | **0.3397** | **0.4476** | **0.2836** | **0.5498** | **0.2190** | 0.6903 |
| `typesafe_score` over bm25, w20 | 0.3160 | 0.4320 | 0.2693 | 0.5025 | 0.2100 | 0.6903 |

R@100 is identical by construction: the arms reorder a 20-document window and
touch nothing below it.

**Paired contrasts, nDCG@10** (10,000 resamples, seed 20260821):

| Contrast | mean Δ | 95 % CI | excludes 0 | W/L/T | sign p |
|---|---:|---|:--:|---|---:|
| noul over bm25 − bm25_only | +0.0185 | [−0.0207, +0.0603] | no | 43/36/21 | 0.50 |
| score over bm25 − bm25_only | −0.0052 | [−0.0460, +0.0384] | no | 38/39/23 | 1.00 |
| noul over bm25 − score over bm25 | +0.0237 | [+0.0074, +0.0413] | **yes** | 39/20/41 | 0.018 |

**By query length, noul − bm25_only:** 1 word (5 queries) +0.0567; 2 words (27)
+0.0029; 3–4 words (33) +0.0393; 5+ words (35) +0.0054.

**Discrimination** (the C-016 measurements):

| Measure | `typesafe_noul` | `typesafe_score` | LLM rubric, `EXP-2026-08-008` |
|---|---:|---:|---:|
| distinct values per 20-window, mean | 12.61 | 17.38 | 1.99 |
| adjacent pairs the model ordered (vs base tiebreak) | 0.611 | 0.862 | — |
| mean value, grade 0 / 1 / 2 | 0.662 / 0.866 / 0.830 | 2.046 / 2.577 / 2.435 | (2 below 1) |
| monotonic in grade | **no** (1 > 2) | **no** (1 > 2) | **no** (1 > 2) |
| pairs answered / failed | 2000 / 0 | 2000 / 0 | — |

Grade counts in the windows: 1,686 grade 0, 138 grade 1, 176 grade 2.

**Agreement between the two arms:** mean top-10 Jaccard **0.805** over 100
queries (bar 0.8: met, barely).

**Determinism** (`data/determinism.json`, 20 pairs × 3 calls, before any arm
ran): max |Δ noul| **0.040**, mean 0.014, 0 pairs above 0.05. Between the bar
(0.01) and the falsifier (0.05), as in `EXP-2026-09-003`.

**Cost and time:**

| | Calls | Input tokens | Output tokens | Cost at list price | Wall |
|---|---:|---:|---:|---:|---:|
| determinism check | 60 | 29,085 | not recorded | $0.0012 | — |
| `typesafe_noul` arm | 2,000 | 1,001,263 | 44,000 | $0.0421 | 104 s incl. base ranking |
| `typesafe_score` arm | 2,000 | 1,065,263 | 38,000 | $0.0447 | 40 s, base cached |
| **total** | **4,060** | **2,095,611** | ≥ 82,000 | **$0.088** | |

Price $0.042 per million input tokens, output free, read 2026-09-17. About 500
input tokens per pair; concurrency 12.

## 3. Figures

None. The record's convention for a single-snapshot contrast is the interval
table, and a figure of three bars with overlapping intervals would say less than
the table does.

## 4. Interpretation

**Primary: falsified, and worth reading past the verdict.** The interval spans
zero, so the record cannot claim a gain, and it does not. What it can record is
the *shape*: +0.0185 with 43/36 wins, positive in all four query-length buckets.
Every previous reranker on this collection lost most on short queries — the
cross-encoder's harm was concentrated on one- and two-word queries and vanished
at five-plus words (`EXP-2026-08-009`). This one's largest deltas are on one-word
(+0.057, five queries) and three-to-four-word (+0.039, 33 queries) queries. That
is the opposite shape, and it is consistent with the mechanism Q-021/Q-023
proposed: a model not trained on MS MARCO web queries reads a scientific keyword
query differently. Consistent with, not evidence for; n = 100 cannot separate
+0.0185 from zero, and this record has been burned by exactly that twice.

**The framing is not free.** The yes/no arm is significantly better than the
rubric-Score arm on the same pairs (+0.0237, interval excluding zero, sign
p = 0.018) — despite the two agreeing on 80 % of every top ten. The Score arm
separates *more* finely (17.4 distinct values against 12.6) and orders more of
the window itself (86 % against 61 %), yet ranks worse. Finer is not better:
the rubric's four described levels give the model more ways to be wrong about
degree while the yes/no question asks only about kind. Any future use of this
model for ranking should use the yes/no framing and treat the Score as a
different instrument.

**Secondary: half met, and the failing half is shared with the LLM.** Distinct
values are far above the bar (17.4 and 12.6 against 5; the LLM rubric's 1.99).
Monotonicity fails in both arms, in the same direction the LLM rubric failed:
grade-1 documents score *above* grade-2 ones, while both sit well clear of
grade 0. Three independent pointwise judges inverting the same two grades is a
statement about the `dctr` grades more than about any judge (Q-041). Under the
protocol's rule the secondary hypothesis is nonetheless falsified, because it
said "either fails".

**Tertiary: met.** Jaccard 0.805 against a bar of 0.8. Two framings of one
question agree on most of the top ten; the ranking difference above lives in
the ordering within that set.

**C-016 in the light of this.** C-016 said the LLM's pointwise verdict could not
discriminate well enough to order a feed, on the evidence of 1.99 distinct
values and a grade inversion. The first half of that mechanism does not recur
here: a probability-weighted output is continuous by construction. The second
half does recur, and Q-041 now asks whether it was ever the judge's fault.
C-016 stands as written — it is a claim about the LLM — and is not amended.

**What this means for the product.** Nothing ships. The cross-encoder stage
stays off, and no TypeSafe stage exists in the pipeline. What the two TypeSafe
experiments together establish is narrower and useful: a pointwise decision
model is cheap (about nine cents for 4,000 judgements), fast (2,000 pairs in
40 s), stable to ±0.04, continuous where the LLM rubric was not, and *not
harmful* on short queries where every other reranker was. Whether it is
*helpful* is Q-040.

## 5. Threats to validity

- **n = 100 and click-derived qrels.** The interval is ±0.04 wide, four times
  the point estimate. `dctr` grades are a click model's output; the grade
  inversion may be theirs.
- **Pooled scope.** A re-ranking evaluation over 84,489 documents; nothing here
  is a recall claim, and R@100 is unchanged by design.
- **One host, one build.** The BM25 baseline reproduces the committed 0.3212
  exactly, which is the check that the corpus build matches. Still, no number
  here is paired against a run from another machine.
- **Repeat spread.** ±0.04 on a probability that decides ordering within a
  window; verdict flips near ties are possible between runs. Single-run numbers
  are reported with that stated.
- **Question wording.** One yes/no question and one four-level rubric, written
  once. The significant gap between them says wording matters; a third wording
  might land elsewhere.
- **Window 20.** Chosen to match `llm_rubric`. The cross-encoder arms used depth
  50 and 100; a deeper window is untested.
- **Determinism check output tokens** were not summed; the cost line uses input
  tokens only, which is what is billed.

## 6. What surprised us

That finer separation ranked *worse*: the Score arm has more distinct values,
orders more of its window, and loses to the yes/no arm significantly. And the
grade inversion: the same two grades swapped by three judges built nothing
alike. Neither was predicted.

## 7. Follow-ups

Copied into `../../OPEN_QUESTIONS.md`.

- **Q-040** — run `typesafe_noul` over BM25 on `sci-2025-01` (492 queries,
  human-assessed qrels). The protocol's replication rule kept it out of this
  experiment; the positive-everywhere shape is the reason to ask anyway. About
  $0.50 and one corpus download.
- **Q-041** — is the `dctr` grade-1 / grade-2 distinction meaningful? Three
  judges invert it identically. Answerable on `sci-2025-01`'s human qrels.
- Not opened as a question, but noted: the yes/no framing over the
  `fusion_union_pool` base (`eval/configs/typesafe_noul_fusion.toml`) would give
  the like-for-like contrast with `llm_rubric`; it needs the pooled dense matrix
  encoded on this host.

## 8. Reproduction

```bash
export IR_DATASETS_HOME=$PWD/data/eval-cache/ir_datasets MYCELIUM_EVAL_CACHE=$PWD/data/eval-cache/embeddings
uv run --project eval eval/run.py --config eval/configs/bm25_only_pooled.toml --collection sci-2026-train
uv run --project eval python docs/research/experiments/EXP-2026-09-004-typesafe-pointwise-rerank-longeval/code/determinism.py
uv run --project eval eval/run.py --config eval/configs/typesafe_noul_bm25.toml eval/configs/typesafe_score_bm25.toml --collection sci-2026-train
uv run --project eval python docs/research/experiments/EXP-2026-09-004-typesafe-pointwise-rerank-longeval/code/paired.py
uv run --project eval python docs/research/experiments/EXP-2026-09-004-typesafe-pointwise-rerank-longeval/code/discrimination.py
```

Result files: `eval/results/longeval-sci-2026_snapshot-1_train__{bm25_only,typesafe_noul,typesafe_score}__pooled__dctr__*__acc44a3.json`.
Raw answers: `data/typesafe_{noul,score}_answers.json` (copies of the arms'
dumps). The last two commands regenerate every table from committed files
without a network call.

## AMENDMENTS

None.
