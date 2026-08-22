# EXP-2026-08-017 — Protocol

**Pre-registered.** Written before either arm was scored. Like its two
predecessors it **computes no verdict** — it produces two ranked lists per cell
and hands them to the reader.

## Question

`EXP-2026-08-015` and `EXP-2026-08-016` gave the same winner in both research
areas: **production's dense-restricted pool plus a cross-encoder rerank**, six
firsts out of six named winners. The three-channel arm (BM25 ∪ dense ∪ SPLADE)
was in both booklets and won nothing.

But **it was never reranked**. Every comparison so far has been
`dense pool + cross-encoder` against a *bare* three-channel pool, which confounds
two differences at once: the pool construction and the presence of a reranker.
`EXP-2026-08-014` did include a reranked three-channel arm (its arm E) and the
reader rated it "very good", but it was never placed head to head against the
winner.

**So: does the dense-restricted pool still win once the three-channel pool gets
the same reranker?** This is the one comparison that isolates the pool.

## Arms — exactly two

| Arm | Pool | Rerank |
|---|---|---|
| `fusion_dense_pool+xenc` | production as deployed — dense top-100 per interest, BM25 indexed only over that pool | cross-encoder over its top 50 |
| `fusion_union_splade+xenc` | BM25 ∪ dense ∪ SPLADE, RRF-fused over a true union pool | cross-encoder over its top 50 |

Everything downstream is identical: same `pool_per_interest = 100`, same rerank
depth 50, same top-10 cut, same cross-encoder
(`Xenova/ms-marco-MiniLM-L-6-v2`), same corpora, same gates off. **The only
difference between the two arms is which documents are in the pool**, which is
what makes this a clean test and is why no third arm is included.

## Queries — both areas, in one booklet

1. `Agentic AI in healthcare`
2. `knowledge graphs`

Both, because the previous two experiments each covered one area and the finding
that mattered was that the winner did not change between them. A pool difference
that only shows up in one area would be a different result from one that shows up
in both, and a single booklet is the only way the reader sees both under one
blinding.

## Corpora

All four types, scored independently: papers (35,205), grants (2,171),
conferences (912), fellowships (818). Top 10 per arm.

**Fellowships are included but are expected to be uninformative.** The reader
could not judge them in either previous read ("I have no idea what fellowships
are… very generalized"), and the winning arm came *last* on them in healthcare.
They are carried so the exception stays visible rather than being quietly
dropped, and a shrug is a legitimate outcome.

## Blinding — a fourth set of letters

**K and V.** No overlap with `A–J`, `W–Z` or `M/N/P/R`. The same letter means the
same arm across both queries and all four categories, so a coherent overall
verdict is possible; the mapping is `BLIND_ORDER` in `code/run.py` and is printed
on the last page only.

## What is switched off

Unchanged and for the same reasons: match thresholds (they gate on a cosine only
the dense channel populates — C-019), the fellowship eligibility engine, the paper
freshness gate. No LLM is called; the cross-encoder is an ONNX cross-encoder.

## Measurements

The sixteen lists as eight matrices; Jaccard@10 between the two arms per cell;
per-query wall clock. **No verdict** — this corpus has no relevance judgments, an
LLM judge is the component `EXP-2026-08-008` measured as non-monotonic in
relevance, and my own reading is not evidence about what this researcher wants.

## What the answer would mean

- **Dense pool still wins** ⇒ the pool restriction C-008 calls a defect is doing
  something useful for this task, and the reranker is not merely compensating for
  a narrow pool. That would make C-023 a claim about the *pool*, not just about
  the reranker.
- **Three-channel wins once reranked** ⇒ the previous six firsts were about the
  **missing reranker**, not the pool, and C-008/C-014's production implications
  are back in play — with a reranker attached.
- **Indistinguishable** ⇒ the pool does not matter at top-10 for this task once a
  reranker is present, which would make the cheaper arm the right one.

All three are useful, which is the point of running it.

## Threats to validity

1. **One reader, one query per area, titles only.** Not W5: no interval, no
   aggregation, never a relevance judgment.
2. **Two arms cannot rank a field.** This resolves one comparison and deliberately
   nothing else.
3. **The three-channel arm carries a cost the other does not** — a SPLADE index
   over every document, ~23 minutes for the papers corpus and a second model
   resident in the serving process. If the reader cannot separate the two lists,
   that cost is the tiebreak, and it is reported alongside.
4. **Rerank depth 50**: both arms can reorder, neither can rescue what its pool
   missed.

## Procedure

```bash
docker compose up -d postgres
uv run --project eval python .../code/run.py
uv run --project eval python .../code/build_pdf.py
```
