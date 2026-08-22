# EXP-2026-08-017 — Results

**No verdict, by design.** Two arms, two queries, four categories, sixteen lists,
typeset as [`tables/splade-vs-dense.pdf`](tables/splade-vs-dense.pdf) — 11 pages,
blinded **K** and **V**, key on the last page. The judgment is the reader's and
will be appended as an amendment.

## 1. The confound this removes

`EXP-2026-08-015` and `EXP-2026-08-016` both gave first place to
`fusion_dense_pool+xenc` — six firsts out of six named winners across two research
areas — and the three-channel arm won nothing in either. But in both booklets the
three-channel arm was **bare**, so every comparison changed two things at once:
how the pool was built, and whether anything reranked it.

Here both arms get the identical cross-encoder over their own top 50.
**The only remaining difference is which documents are in the pool.**

## 2. What the run shows on its own: the reranker largely erases the pool difference

| Query | Category | distinct documents across the two top-10s | overlap (Jaccard@10) |
|---|---|---:|---:|
| Agentic AI in healthcare | Papers | 13 | 0.54 |
| Agentic AI in healthcare | **Grants** | **10** | **1.00** |
| Agentic AI in healthcare | Conferences | 11 | 0.82 |
| Agentic AI in healthcare | Fellowships | 12 | 0.67 |
| knowledge graphs | Papers | 14 | 0.43 |
| knowledge graphs | Grants | 13 | 0.54 |
| knowledge graphs | Conferences | 13 | 0.54 |
| knowledge graphs | **Fellowships** | **16** | **0.25** |

Ten distinct documents would mean the two arms are identical; twenty that they
share nothing.

**On healthcare grants they are byte-identical — overlap 1.00.** On healthcare
papers, ranks **1 through 7 are the same document in the same order**, and the
two lists only part company at rank 8. Set against the four-arm booklets, where
pairwise overlap ran 0.27–0.63, giving both pools the same reranker pulls them
together sharply.

That is a result in its own right and it is visible without any judgment: **at
top-10, once a cross-encoder is present, the pool it draws from matters much less
than it does without one.** Which is consistent with the mechanism proposed in
`EXP-2026-08-015` §1 — a reranker imposes its own ordering on whatever it is
handed — and it sharpens what the reader is being asked. If the two lists look
alike, the question stops being "which pool is better" and becomes "is the wider
pool worth an index it does not visibly change".

**The exception is knowledge-graph fellowships at 0.25**, the least agreement of
any cell here. Fellowships were also the least-agreeing cell in
`EXP-2026-08-016` (0.27 across four arms) and the one category the reader could
not judge in either previous read.

## 3. Cost

| Arm | median s/query | one-time index cost |
|---|---:|---|
| `fusion_dense_pool+xenc` | 1.432 | none |
| `fusion_union_splade+xenc` | 1.822 | **~23 min over the papers corpus**, plus a second index kept in step with the corpus and a second model resident in serving |

Both pay the same cross-encoder pass, so the per-query gap is small and mostly
the extra sparse matmul and pgvector scan. **The column that decides this is the
third one**, and it only earns its keep if the reader can tell the lists apart.

## 4. What each possible answer would mean

Fixed in `PROTOCOL.md` before the run:

- **Dense pool still preferred** ⇒ the pool restriction C-008 calls a defect is
  doing something useful for this task, and C-023 becomes a claim about the pool
  and not only about the reranker.
- **Three-channel preferred once reranked** ⇒ the previous six firsts were about
  the *missing reranker*, not the pool, and C-008/C-014's production implications
  return — with a reranker attached.
- **Indistinguishable** ⇒ the pool does not matter at top-10 once a reranker is
  present, and the cheaper arm wins by default. §2 suggests this is the likely
  outcome on at least half the cells.

## 5. Threats to validity

1. **One reader, one query per area, titles only.** Not W5 — no interval, no
   aggregation, never a relevance judgment.
2. **Two arms cannot rank a field.** This resolves one comparison and nothing
   else.
3. **A tie is informative here but not neutral**: it favours the cheaper arm, and
   that inference depends on the cost table in §3 rather than on the reader.
4. **Rerank depth 50.** Both arms can reorder; neither can rescue what its pool
   missed. A pool advantage that lives below rank 50 is invisible to this design.
5. **Fellowships are expected to be uninformative** and are carried so the
   exception stays visible rather than being quietly dropped.

## 6. What this changes

Nothing yet — it is an instrument. It closes the confound in `Q-032`'s answer:
whatever the reader says, the pool and the reranker are no longer varying
together.
