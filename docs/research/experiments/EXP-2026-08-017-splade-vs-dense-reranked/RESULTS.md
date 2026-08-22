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

---

## AMENDMENTS

### 2026-08-22 — the pre-registered question is answered: **the dense pool still wins**

Read blind. **One reader, one query per area, titles only. Not W5** — no interval,
no aggregation, never a relevance judgment.

**Unblinding.** `K` = `fusion_union_splade+xenc` (three channels).
`V` = `fusion_dense_pool+xenc` (production's dense-restricted pool).

| Query | Category | Verdict |
|---|---|---|
| healthcare | Papers | **V** — "goes into more detailed topics that are more related to what the user is looking at" |
| healthcare | Grants | **tie, forced** — the two top-tens are byte-identical |
| healthcare | Conferences | **V** — "it skips the molecular sciences, which isn't exactly what healthcare is" |
| healthcare | Fellowships | **V**, qualified — see §3 |
| knowledge graphs | Papers | **V** — "it does talk about large language models, knowledge graphs, generative AI" |
| knowledge graphs | Grants | **V** |
| knowledge graphs | Conferences | **tie** — "they both miss out on something" |
| knowledge graphs | Fellowships | **tie**, with V leaning — "V might be a little bit more grounded in what we're trying to do" |

**V: five wins, three ties, zero losses.** One of the ties is not a judgment at
all — the healthcare grant lists are identical, so there was nothing to choose.
Of the seven cells where a choice existed, **the three-channel pool did not win
one**.

Attributions verified against `data/lists.json`: the Agentic Systems for
Molecular Sciences workshop is K=9 and absent from V; the three knowledge-graph
conferences V "misses out on" are K's alone — Natural Language Processing (K=5),
Applied Mathematics and Graph Theory (K=9), and ECML / Principles and Practice of
Knowledge Discovery in Databases (K=10); and the healthcare grant top-tens are
identical id for id.

### 1. The pre-registered reading, applied as written

`PROTOCOL.md` fixed three outcomes before the run. The one that occurred:

> **Dense pool still preferred** ⇒ the pool restriction C-008 calls a defect is
> doing something useful for this task, and the reranker is not merely
> compensating for a narrow pool. That would make C-023 a claim about the
> **pool**, not just about the reranker.

The confound is now removed: both arms had the identical cross-encoder, the same
depth, the same cut. **The pool was the only difference and the narrower pool won
or tied everywhere.**

C-023 is updated accordingly — it is a claim about the dense-restricted pool *and*
the reranker, not the reranker alone.

### 2. What this settles about SPLADE, and what it does not

`fusion_union_splade` has now been in **three** blinded reads and won **nothing**:
bare in `EXP-2026-08-015` (last on healthcare conferences), bare in
`EXP-2026-08-016` (second on knowledge-graph papers, its best showing anywhere),
and here with every advantage equalised.

**C-014 stands.** It is a correctly-measured recall claim about LongEval-Sci,
replicated across two snapshots and two judgment regimes, and a preference cannot
overturn it. What has changed is its production implication: **there is now no
human evidence for building a SPLADE index, and three reads of evidence against
spending the effort.** That is a decision, and its price tag is concrete — ~23
minutes of one-time encoding over the papers corpus, a second index to keep in
step with the corpus forever, and a second model resident in the serving process,
for lists this reader either preferred less or could not distinguish.

The same now holds for the union pool (C-008's implication), which won nothing in
`EXP-2026-08-015` or `EXP-2026-08-016` either.

### 3. Fellowships, and one thing the reader said that does not parse cleanly

Healthcare fellowships were recorded as a **V** win, but the reasoning as spoken
contains a tension worth preserving rather than smoothing: *"V doesn't have one of
the fellowships I think would be very important, but at the same time K has two of
them that I think would be very important. So I'm gonna have to give it to V again
on this one for the top ten at the very least."*

Read literally, the two clauses favour K and the conclusion favours V. The most
likely reading is that V's top ten is better **overall** despite K carrying one or
two stronger individual items — which is a coherent judgment about a list rather
than about its best members — and that is how it is recorded. **If the reader
meant K, healthcare fellowships flips and V's record becomes 4–3–1.** Flagged
rather than resolved.

Note also that this does **not** contradict `EXP-2026-08-015`, where the same
reranked arm came *last* on healthcare fellowships. There its opponents were
un-reranked; here its only opponent is another reranked arm. Both readings hold
together: **the reranker hurts fellowships, and between two reranked arms the
dense pool is still the better one.** `Q-031` is untouched.

### 4. How thin the wins are

Stated so this is not quoted stronger than it is. The two arms' lists are close —
healthcare papers agree exactly through rank 7, healthcare grants are identical,
and median overlap across the eight cells is ~0.54. The reader's reasons are
correspondingly narrow: one workshop present or absent, one or two items further
down. **This is a consistent preference over a small difference, not a large
one** — which is itself the finding, because the small difference costs an entire
extra index.

### 5. What this changes

- **The pre-registered question is answered** and `C-023` is updated from a claim
  about the reranker to a claim about the pool **and** the reranker.
- **`Q-034` opened**: the SPLADE and union-pool production changes have no human
  endorsement across three reads and a measurable cost. Recommend not building
  them, and record that as a decision rather than an absence.
- **`Q-033` is unchanged and is now the only thing left**: the preferred
  configuration has still never been measured against anything but taste.
