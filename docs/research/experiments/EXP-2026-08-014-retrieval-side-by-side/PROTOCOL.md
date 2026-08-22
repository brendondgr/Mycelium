# EXP-2026-08-014 — Protocol

**Pre-registered**, with an unusual property stated up front: **this experiment
computes no verdict.** It produces ranked lists and hands them to a human. The
protocol therefore fixes the *procedure* and the *presentation*, and deliberately
fixes no hypothesis about which arm wins.

## Question

Two, and the second is the reason for the first.

1. **What do these retrieval processes actually return**, on Mycelium's own
   corpus, for queries Mycelium's own users would write? Thirteen experiments
   have reported aggregate metrics on an external collection; nobody has looked
   at the documents.
2. **Do the differences the ladder measures matter for this task at all?**
   The standing worry — raised by the user and shared by the record — is that
   LongEval-Sci evaluates *keyword query → topically-relevant web-scraped
   document*, judged by assessors with no stake in the outcome, and that this may
   simply be a different problem from *declared research interest → things a
   researcher wants in their inbox*. If it is, then a ranking difference that is
   significant on LongEval may be invisible or irrelevant here.

Question 2 has a component this experiment *can* answer without any judgment:
**if the arms return nearly the same documents, the entire ladder is moot for
this corpus** regardless of which is theoretically better. That is measured
(§Agreement). Which list is *better* is not measured — it is asked.

## Why there is no verdict in this file

There are no relevance judgments for this corpus (`EXP-2026-08-013` §6; W5 not
started). Two responses were available. One is to invent a proxy — LLM-as-judge,
or my own reading of the titles — and both are worse than useless here: the LLM
scorer is the component C-004 is about and `EXP-2026-08-008` showed a scorer of
that shape is non-monotonic in relevance, and my own opinion of a grant listing
is not evidence about what a researcher wants.

The other response is to ask the person whose feed it is. That is this
experiment. **The judgment is the user's, it is a preference, and a preference is
the correct instrument here** — there is no ground truth about which conference
belongs in someone's top ten.

## Blinding

Arms are presented as **A–J in a fixed shuffled order**, with the key on the
final page of the PDF only. The permutation is fixed by a recorded constant, not
by arm name, so it is not guessable from the ordering.

This is not ceremony. The whole point of asking a human is to get a judgment that
is not anchored on which list is "ours", which is "the paper's recommendation",
or which one the previous thirteen experiments have been arguing about. An
unblinded comparison of `fusion_dense_pool` against `bm25_only` by the person who
built `fusion_dense_pool` is not worth running.

## Queries

Three, in the shape a declared interest actually takes (`EXP-2026-08-013`
measured real ones at a median of 3 words, 95% ≤ 4):

1. `AI agents in healthcare`
2. `AI agents in medicine`
3. `agentic AI for clinical decision support`

The first two are deliberately near-synonymous. If two arms disagree more with
each other on one of these than the same arm disagrees across the two queries,
that is a fact about the arms' stability worth seeing.

## Corpora

All four deployed content types, each scored independently:

| Type | documents |
|---|---:|
| `paper` | 35,205 |
| `grant` | 2,171 |
| `conference` | 912 |
| `fellowship` | 818 |

**Whole corpus, not one gather day.** The deployed paper feed is scoped to
`latest_gather_date`; that is switched off here so the paper arm is comparable to
the three opportunity arms and so the comparison is about retrieval rather than
about the freshness gate.

## Arms

Five base rankings, each also run with a cross-encoder rerank — ten lists per
(query, content type), twelve such cells, 120 ranked lists.

| Base arm | What it is |
|---|---|
| `bm25_only` | corpus-wide BM25 (`rank_bm25`, the production implementation) |
| `dense_only` | pgvector cosine over `ContentItem.embedding` |
| `fusion_dense_pool` | **production as deployed** — `_build_pool` verbatim, BM25 indexed only over the dense pool |
| `fusion_union_pool` | dense top-100 ∪ corpus-wide BM25 top-100, then the same `fuse_interest` |
| `fusion_union_splade` | the above plus SPLADE as a third RRF channel — the ladder's recommended stack |

**Cross-encoder variant:** `Xenova/ms-marco-MiniLM-L-6-v2` re-scores each base
arm's top 50 and the top 10 of *that* is reported. Included because the user
asked for it directly, and because the record's position on it is a refutation
(C-013) that has never been looked at rather than measured — this is the first
time anyone sees what it actually does to a list.

Every arm calls the production functions (`embeddings.embed_text`,
`build_bm25_index`, `rank_bm25_over`, `fuse_interest`, `PgVectorIndex`).

## What is deliberately switched off

- **No match threshold and no surface cap.** `PAPER_MATCH_THRESHOLD`,
  `GRANT_MATCH_THRESHOLD` etc. gate on a cosine the lexical channels never
  populate (C-019), which would silently empty the non-dense arms. The comparison
  is of *rankings*, so it is run on rankings.
- **No fellowship eligibility engine.** `fellowships.py` gates on a deterministic
  rule ladder before relevance. Leaving it in would make the fellowship tables a
  comparison of eligibility rules rather than of retrieval.
- **No LLM anywhere.** No reranking, no scoring, no summarising.

Each of these is a real part of the product and each is named here so the tables
are not mistaken for a screenshot of the feed.

## Measurements

**Reported without interpretation:**

- The 120 top-10 lists, as tables, blinded.
- **Agreement between arms** — Jaccard@10 and Kendall's τ on the overlap, per
  (query, type) and pooled. This is the half of question 2 that needs no
  judgment.
- **Wall clock per arm**, split into query-time cost and one-time index cost.
  Amortised index construction (the BM25 index, the SPLADE encode) is reported
  separately from per-query latency, because conflating them is how a method that
  costs half an hour once looks the same as one that costs half a second every
  time.

**Not reported:** any statement by me about which list is better.

## Deliverable

A PDF: method, agreement summary, twelve blinded comparison tables, a timing
chart, and the arm key on the final page.

## Threats to validity

1. **n = 3 queries, one topic area.** Chosen by the user for their own domain.
   Nothing here generalises to a different field, and it is not meant to.
2. **A preference from one person is one person's preference.** It is evidence
   about what this user wants, which is the right target for a product decision
   and the wrong target for a paper claim. It must never be written up as W5.
3. **Titles are what a reader will judge on.** The tables show title, source and
   a short snippet; nobody reads 35,205 abstracts. A ranking that puts a good
   paper under a bad title will lose unfairly, and that is also true of the real
   product.
4. **The cross-encoder arms rerank the top 50 only**, so they can reorder but
   never rescue a document the base arm missed.
5. **Whole-corpus scope for papers** departs from the deployed freshness gate
   (§Corpora), by design.

## Procedure

```bash
docker compose up -d postgres
uv run --project eval python .../code/encode_splade.py   # one-time, ~30 min
uv run --project eval python .../code/run.py
uv run --project eval --with matplotlib python .../code/build_pdf.py
```
