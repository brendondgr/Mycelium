# EXP-2026-08-014 — Results

**Two halves, and only one of them is here.**

The half this experiment can answer alone — *do these ten retrieval processes
actually return different things on Mycelium's own corpus?* — is answered below.
**Yes, dramatically**, and the size of the disagreement is the finding.

The half it exists to enable — *which list is better?* — is a preference and
belongs to the user. The booklet
([`tables/retrieval-comparison.pdf`](tables/retrieval-comparison.pdf), 42 pages,
blinded A–J with the key on the last page) is the instrument. **No verdict is
recorded here and none will be inferred.** When a preference comes back it is
appended as an amendment, as one person's preference, and never as W5.

## 1. The arms disagree far more than the benchmark suggests

Mean pairwise Jaccard@10 across the ten arms, over twelve (category, query)
cells. Computed twice — on document ids, and again collapsing the store's
duplicate rows onto normalised titles — because different arms pick different
copies of the same document and that would otherwise count as disagreement.

| Category | distinct documents across all ten top-10s | unanimous | mean pairwise Jaccard@10 |
|---|---:|---:|---:|
| **Papers** | **34.0** | **0.0** | **0.339** |
| Conferences | 27.7 | 0.7 | 0.392 |
| Fellowships | 26.7 | 3.7 | 0.467 |
| Grants | 16.7 | 5.0 | 0.701 |
| **overall** | **26.2** | **2.3** | **0.475** |

Ten if the arms agreed perfectly; a hundred if they were disjoint. **On papers
the answer is 34, and not one document appears in all ten top-tens.** Two
configurations picked at random share under half their results.

**This is the number that speaks to the doubt about the benchmark**, and it does
so more sharply than the doubt was posed. The concern was that LongEval-Sci may
not measure our task. What this shows is subtler and worse: the record's own
resolution limit on that collection is roughly ±0.04 nDCG@10 at n = 100
(`EXP-2026-08-009` §4), so a great many of these arms are *statistically
indistinguishable there* — while producing top-tens that share a third of their
documents here. A benchmark null and an entirely different feed are perfectly
compatible. Aggregate means over 100–492 queries and a single visible top ten are
not the same measurement, and no amount of care with intervals converts one into
the other.

**Grants are the exception and worth noticing**: 0.70 agreement, five unanimous
documents. On a 2,171-document corpus of short, templated text the arms mostly
converge — so how much the retrieval choice matters is itself a property of the
corpus, not a constant.

## 2. A defect that fell out of reading the lists

Reading the actual output turned up something thirteen experiments of aggregate
metrics did not: **the store holds the same document several times under
different ids**, and the copies land next to each other at the top of a list. One
framework occupied three of ten slots on the first papers page.

| Category | rows | duplicate rows by title | share | untitled |
|---|---:|---:|---:|---:|
| Papers | 35,209 | 207 | 0.6% | 105 |
| Grants | 2,171 | 31 | 1.4% | 0 |
| Conferences | 912 | 6 | 0.7% | 0 |
| Fellowships | 818 | 0 | 0.0% | 0 |

**Across the 120 ranked lists, 14 top-ten slots went to a document whose title
had already appeared higher in the same list.** Under 1% of every corpus, which
is exactly why no mean ever flagged it, and concentrated in the only ranks a
reader looks at. It belongs to no arm; every retrieval process inherits it.

Note also 105 papers with **no title at all**, which are unreadable in a feed
whatever their rank.

## 3. Cost

Median seconds to answer one query, from `figures/fig-timing.svg`:

| Arm | s/query | | Arm | s/query |
|---|---:|---|---|---:|
| `bm25_only` | **0.008** | | `bm25_only`+xenc | 0.944 |
| `dense_only` | 0.060 | | `dense_only`+xenc | 1.074 |
| `fusion_dense_pool` (deployed) | 0.069 | | `fusion_union_pool`+xenc | 1.416 |
| `fusion_union_splade` | 0.083 | | `fusion_dense_pool`+xenc | 1.434 |
| `fusion_union_pool` | 0.091 | | `fusion_union_splade`+xenc | 1.463 |

Two things are worth separating.

**The cross-encoder costs 15–180× the retrieval it reranks** — every arm lands
between 0.94 s and 1.46 s once it is added, because 50 query-document pairs
through a cross-encoder dominates everything else by so much that which arm
produced the candidates barely registers. For a feed run over hundreds of
targets, that is the entire latency budget, spent on a stage this record has
refuted twice (C-013).

**BM25 alone is an order of magnitude cheaper than any other arm** (8 ms against
60–91 ms), and adding SPLADE as a third channel is nearly free at query time
(0.083 s against 0.091 s for two channels — the sparse matmul is faster than the
extra pgvector scan it replaces).

**Its cost is elsewhere, and it is not small**: 23 minutes to encode 35,205
papers once, plus a second index to keep in step with the corpus forever, plus a
second ONNX model resident in the serving process. One-time per document —
incremental for new ingest, roughly 20 s to 4 min per daily gather batch at the
measured 25.5 docs/s — but never zero.

## 4. What is deliberately not in the booklet

These are rankings, not screenshots of the feed. Three gates are off, each
load-bearing in production, each named on the cover: the match thresholds (they
gate on a cosine only the dense channel populates — C-019 — so leaving them on
would empty the lexical arms), the fellowship eligibility engine, and the paper
freshness gate. No LLM was called anywhere.

## 5. Threats to validity

1. **Three queries, one topic area, chosen by the user.** Nothing here
   generalises to another field and it is not meant to.
2. **The pending judgment is one person's preference.** That is the right basis
   for a product decision about this product and the wrong basis for a paper
   claim. It is not W5 and must never be reported as if it were.
3. **Titles carry the judgment.** The booklet shows title, source and ~190
   characters. An arm that ranks a better document under a duller title will lose
   — a bias shared with the real feed rather than introduced here.
4. **Rerank depth 50.** The cross-encoder arms reorder; they cannot rescue what
   the base arm missed.
5. **Whole-corpus scope for papers**, departing from the deployed freshness gate,
   so the four categories are comparable.
6. **The disagreement statistic is sensitive to duplicates**, which is why §1
   reports it both ways. The two agree to 0.002, so duplicates are a visible
   defect but not the source of the disagreement.

## 6. What this changes

- **New claim C-021** — the ten configurations return substantially different
  top-tens on the production corpus (mean pairwise Jaccard@10 0.475; zero
  unanimous documents on papers), so arms that are statistically
  indistinguishable on LongEval are not interchangeable in the product.
- **A corpus defect is now measured**, not suspected: 207 duplicate paper rows
  and 105 untitled ones, costing 14 of 120 top-ten lists a slot. Recorded as
  `Q-028`.
- **The cross-encoder's cost is now measured on production**: 15–180× the
  retrieval it reranks, on a stage refuted twice on effectiveness.
- **`Q-029` opened** — the preference elicitation itself, pending the user's
  scorecard.
