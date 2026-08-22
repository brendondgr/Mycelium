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

---

## AMENDMENTS

### 2026-08-22 — both reads are in, and they agree. `Q-032` closes.

The knowledge-graphs booklet was read blind. **One reader, one query per area, two
areas. Not W5** — no interval, no aggregation, never a relevance judgment.

**Unblinding both experiments.** `EXP-2026-08-015` used `W X Y Z` on
`Agentic AI in healthcare`; this one used `M N P R` on `knowledge graphs`. Neither
letter set overlapped, and the healthcare identities were withheld until this read
was complete.

| Arm | healthcare | knowledge graphs |
|---|:--:|:--:|
| `fusion_dense_pool` **+ cross-encoder** | **W** | **P** |
| `fusion_union_splade` (three channels) | X | R |
| `fusion_union_pool` | Y | M |
| `fusion_dense_pool` (**production as deployed**) | Z | N |

### 1. The same arm won, in both areas, in every category the reader could separate

| | papers | grants | conferences | fellowships |
|---|---|---|---|---|
| **healthcare** | **+xenc** 1st | **+xenc** 1st | **+xenc** 1st | production 1st · **+xenc last** |
| **knowledge graphs** | **+xenc** 1st | **+xenc** 1st | **+xenc** 1st | all tied · +xenc marginally best |

**`fusion_dense_pool` + cross-encoder took six outright firsts out of six cells
where a winner was named**, across two unrelated research areas, under two
independent blindings. No other arm won anything except production-alone on
healthcare fellowships.

`Q-032` asked whether the winner was a property of the arms or of that corner of
the corpus. **It is the arms.**

The reader's attributions verify again: Native American Scholars Initiative is 1st
or 2nd in the three other arms and **5th** in the winner; the Epistemic
Intelligence workshop is 5th/5th/6th elsewhere and **10th** in the winner; and the
winner's conference slots 5–8 are Generative IR, Graph Machine Learning,
Information Modelling and Knowledge Bases, and Document Intelligence.

### 2. This is the inverse of what the ladder recommended

Sixteen experiments produced a recommendation — union pool, add SPLADE, no
reranker. **Every element of it lost.**

| Ladder said | Arm | Reader's result |
|---|---|---|
| widen to a **union pool** (C-008) | `fusion_union_pool` | **no first place in either area**; tied last on knowledge-graph papers |
| add **SPLADE** as a third channel (C-014) | `fusion_union_splade` | **no first place**; last on healthcare conferences; its one strong showing is 2nd on knowledge-graph papers |
| **no reranker** (C-013 refuted twice) | the reranker | **the single differentiator that wins everything** |
| — | the **dense-restricted pool** C-008 calls the worst configuration | **the base of the winning arm in both areas** |

**None of this refutes C-008, C-013 or C-014.** Those are measured claims about
recall and aggregate nDCG on LongEval-Sci, they were measured correctly, and a
preference cannot overturn them. What it does establish is narrower and more
consequential for the product: **no production change this programme has proposed
has ever been endorsed by the only human who has looked at the output, and the
configuration that human keeps choosing is one the programme argued against.**

### 3. The story across all three reads is consistent

| read | what was rejected | what was preferred |
|---|---|---|
| `EXP-2026-08-014` | `bm25_only` — "obscure stuff… zero correlation" | `dense_only` — singled out, "really nice", unique finds |
| `EXP-2026-08-015` | union pool, three-channel | dense pool + rerank |
| `EXP-2026-08-016` | union pool, three-channel | dense pool + rerank |

**Everything that widens the pool with lexical reach loses; everything that keeps
the pool dense-filtered wins.** That is C-022 seen from a second angle, and it is
now three independent blinded reads pointing the same way.

The cross-encoder's role fits the mechanism proposed in `EXP-2026-08-015`
§1: it helps when reranking a **narrow, already semantically-filtered** pool and
hurts when reranking a broad one. Seven paired comparisons now, all consistent.

### 4. Where the wins are thin, and where they are not

Reported so the result is not quoted stronger than it is:

- **Papers is where the discrimination is real.** Both areas produced a clear
  first and a clear tail ("P is extremely specific… more in tune"; "W is
  definitely number one"). Papers is also the category with the lowest arm
  agreement in both areas (0.29 and 0.31).
- **Grants and conferences wins are marginal.** "All fairly similar, hard to tell";
  "all pretty much equal… but systematically P gets the most correct". The winner
  is the same but the margin is small, and grant/conference arm agreement is high
  (0.49–0.63).
- **Fellowships cannot be judged by this reader at all** — "I have no idea what
  fellowships are… very generalized" — and are the one category where the winner
  came *last* in the other area. They should be treated as unresolved, not as a
  tie.

### 5. What this changes

- **`Q-032` closed**: the winner is a property of the arms, not the topic area.
- **New claim C-023** — the configuration this reader prefers is production's
  dense-restricted pool **plus** a cross-encoder rerank, on papers, grants and
  conferences; `unsupported`, on two blinded reads by one person.
- **`Q-031` sharpened**: fellowships are the live exception, in both directions.
- **`Q-033` opened** — the preferred configuration has never been measured on
  anything but a preference, and it is now the specific thing worth labelling.
