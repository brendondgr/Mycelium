# EXP-2026-08-016 — Results

**No verdict, by design.** The same four arms as `EXP-2026-08-015`, on a second
research area, typeset as
[`tables/knowledge-graphs-comparison.pdf`](tables/knowledge-graphs-comparison.pdf)
— 7 pages, blinded **M, N, P, R**, key on the last page. The judgment is the
reader's and will be appended as an amendment.

## 1. Why

`EXP-2026-08-015` gave a clean per-category winner on `Agentic AI in healthcare`
— one arm first on papers, grants and conferences, and **last** on fellowships.
That could be a property of the arms or of that corner of the corpus, and one
query cannot tell the difference.

`knowledge graphs` is a different declared cluster of the same reader and a
different region of the same store. Same arms, same pool width, same rerank
depth, same gates off, same layout, **third blinding**.

**Either answer is actionable, which is rare here.** Same winner ⇒ there is a
configuration to ship. Different winner ⇒ no single configuration is right for
the whole product, and the fix is routing rather than a parameter (`Q-031`,
`Q-032`).

## 2. Agreement, and one number that stands out

| Category | distinct documents across the four top-10s | mean pairwise Jaccard@10 | healthcare, for comparison |
|---|---:|---:|---:|
| Papers | 21 | **0.29** | 0.31 |
| Grants | 15 | 0.63 | 0.49 |
| Conferences | 14 | 0.63 | 0.59 |
| **Fellowships** | **25** | **0.27** | **0.53** |

Papers behave the same way in both areas — around 21 distinct documents at ~0.30
overlap, the category where the choice of arm matters most.

**Fellowships flip completely.** On healthcare the four arms largely agreed
(0.53); on knowledge graphs they agree less than on any other cell measured in
either experiment (0.27, 25 distinct documents out of a possible 40). The
fellowship corpus is 818 documents of programme descriptions, and a query with no
medical vocabulary appears to give the four channels almost nothing to converge
on. Worth watching in the read: this is the cell where the arms have the least in
common anywhere.

Grants and conferences are *more* convergent here than on healthcare (0.63
against 0.49 and 0.59).

## 3. Cost

| Arm | s/query | healthcare |
|---|---:|---:|
| `fusion_union_pool` | 0.055 | 0.094 |
| `fusion_dense_pool` (production as deployed) | 0.056 | 0.103 |
| `fusion_union_splade` | 0.084 | 0.186 |
| `fusion_dense_pool` **+ cross-encoder** | **0.911** | 1.866 |

Uniformly cheaper than the healthcare query — a two-word query does less BM25 and
cross-encoder work than a four-word one — and the shape is unchanged: **the
reranked arm costs roughly 16× the arm it reranks.**

## 4. Threats to validity

1. **Not pre-registered** — `PROTOCOL.md` was written after the run
   (`ISSUES.md` §1).
2. **One query, one reader.** The second of two; the pair is what makes either
   informative, and neither generalises alone.
3. **A second round on survivors** — these four arms were selected by
   `EXP-2026-08-014`'s preference.
4. **Titles carry the whole judgment**; no snippets, at the reader's request.
5. **Not W5.** One person's preference: no interval, no aggregation, never a
   relevance judgment.

## 5. What this changes

Nothing yet — it is an instrument. `Q-032` closes when the read comes back, and
with it the question of whether this programme has one configuration to recommend
or needs per-type routing.
