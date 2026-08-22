# EXP-2026-08-015 — Protocol

**Pre-registered**, and like `EXP-2026-08-014` it **computes no verdict**. It
produces four ranked lists per category and hands them to the reader. The
protocol fixes procedure and presentation only.

## Why this exists

`EXP-2026-08-014` elicited a preference over ten arms, three queries and four
categories — 120 lists in a 42-page booklet. Two things came back:

1. A usable judgment on eight of the ten arms.
2. **The booklet was too long to navigate.** The reader's words: "you gave me a
   lot of details so it's very difficult to navigate… I'm not able to tell that
   at all" about which arm ranked what. The presentation was part of the
   instrument and it obstructed the measurement.

So this is the same experiment with the scope cut to what the reader asked to
see and the format rebuilt around one job: **read a title, see where each arm
put it.**

## What changes from `EXP-2026-08-014`

| | `EXP-2026-08-014` | here |
|---|---|---|
| Arms | 10 | **4** |
| Queries | 3 | **1** |
| Rows per table | title + snippet + source + carrier set | **title only** |
| Table shape | document-centric list, then a separate ordering table | **one matrix: rows are titles, columns are arms, cells are rank** |
| Length | 42 pages | ~8 |

## Arms

The four the reader named, by their `EXP-2026-08-014` letters:

| was | arm | why it is here |
|:--:|---|---|
| A | `fusion_union_pool` — RRF over dense ∪ corpus-wide BM25 | rated very good |
| C | `fusion_dense_pool` — **production as deployed** | rated very good; the incumbent |
| G | `fusion_dense_pool` **+ cross-encoder** | rated very good; the one reranked arm that did not degrade its base |
| H | `fusion_union_splade` — RRF over BM25 ∪ dense ∪ SPLADE | **never rated** — the eval programme's own recommended stack, and the only arm with no read |

Deliberately excluded: `bm25_only` and `dense_only`, both already judged
decisively (F rejected, D singled out), and the three reranked arms the reader
rejected.

## Blinding — with new letters

Arms are **W, X, Y, Z**, not A–J. Reusing the old letters would leak the previous
verdicts into this read; using A–D would invite the reader to assume A is still
A. The permutation is fixed as `BLIND_ORDER` in `code/run.py` and printed on the
last page only.

## Query

**One**: `Agentic AI in healthcare` — chosen by the reader. Note this string was
**not** run in `EXP-2026-08-014` (that used "AI agents in healthcare"), so these
are fresh lists, not a re-presentation of judged ones.

## Corpora

All four deployed content types, scored independently: papers (35,205), grants
(2,171), conferences (912), fellowships (818). Top **10** per arm, no deeper.

## Presentation, which is the point of this experiment

One page per category. **Rows are document titles, in full, with nothing else —
no snippet, no source, no description. Columns are the four arms. Each cell is
that arm's rank, 1 to 10, or blank if the arm did not surface it.**

Rows are ordered by the best rank any arm gave the document, so the consensus top
sits at the top of the page and disagreement is visible as gaps.

## What is switched off

Unchanged from `EXP-2026-08-014` §"What is deliberately switched off", and for
the same reasons: match thresholds (they gate on a cosine only the dense channel
populates — C-019), the fellowship eligibility engine, the paper freshness gate.
No LLM is called for ranking or scoring anywhere; the cross-encoder in arm G is
an ONNX cross-encoder, not a language model.

## Measurements

Reported without interpretation: the four matrices; pairwise agreement
(Jaccard@10) between the arms; and per-query wall clock. Nothing else, and no
statement by me about which list is better.

## Threats to validity

1. **One query, one topic area, one reader.** Narrower than
   `EXP-2026-08-014` by design; nothing here generalises.
2. **A preference from one person is not W5** — no interval, no aggregation,
   never cited as a relevance judgment.
3. **Titles alone now carry the entire judgment.** The snippet is gone at the
   reader's request, which makes the booklet readable and makes a good document
   under a dull title easier to miss. That trade is deliberate and is shared with
   the real feed, which is also mostly title.
4. **These four arms were pre-selected by a prior preference**, so this is a
   second round on survivors, not an independent sample.

## Procedure

```bash
docker compose up -d postgres
uv run --project eval python .../code/run.py
uv run --project eval python .../code/build_pdf.py
```
