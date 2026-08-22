# EXP-2026-08-015 — Results

**No verdict, by design.** Four arms, one query, four categories, forty ranked
positions, typeset as
[`tables/four-arm-comparison.pdf`](tables/four-arm-comparison.pdf) — 7 pages,
blinded **W–Z** with the key on the last page. The judgment is the reader's and
will be appended as an amendment.

What the run establishes on its own is below: how much these four disagree, and
what each costs.

## 1. Why this exists

`EXP-2026-08-014` failed as an instrument before it succeeded as a question. The
reader's verdict on the booklet: *"you gave me a lot of details so it's very
difficult to navigate… I'm not able to tell that at all"* about which arm ranked
what. Forty-two pages, ten arms, three queries, and each row carrying a title, a
snippet, a source and a carrier set.

The scope here is what the reader asked for, and the format is rebuilt around one
job — **read a title, see where each arm put it**:

| | `EXP-2026-08-014` | here |
|---|---|---|
| arms | 10 | **4** |
| queries | 3 | **1** — `Agentic AI in healthcare` |
| row content | title + snippet + source + carriers | **title, in full, and nothing else** |
| shape | document list, then a separate ordering table | **rows are titles, columns are arms, cells are rank** |
| length | 42 pages | **7** |

The four arms are the ones the reader named: three they rated very good
(`fusion_union_pool`, production as deployed, production + cross-encoder) and
**the one they never rated** — `fusion_union_splade`, the three-channel stack
this eval programme has spent four experiments recommending.

## 2. These four disagree less than the full ten did, but still substantially

| Category | distinct documents across the four top-10s | mean pairwise Jaccard@10 |
|---|---:|---:|
| **Papers** | **21** | **0.31** |
| Grants | 17 | 0.49 |
| Fellowships | 16 | 0.53 |
| Conferences | 16 | 0.59 |

Ten would mean the four arms agree completely; forty that they share nothing. On
papers it is 21 at a mean overlap of 0.31 — **two of these four arms typically
share three of their ten papers.** All four passed a human read (or, for the
three-channel arm, were never read), so this is disagreement *within the
acceptable set*, which is the sharpest form of the question: not "which arm is
wrong" but "which of four defensible answers should a reader get".

Papers are again the category where the choice matters most and conferences the
least, matching `EXP-2026-08-014` §1 on a different query.

## 3. Cost

Median seconds to answer this query, end to end:

| Arm | s/query | note |
|---|---:|---|
| `fusion_union_pool` | **0.094** | |
| `fusion_dense_pool` (production as deployed) | 0.103 | |
| `fusion_union_splade` | 0.186 | **plus** a one-time 23-minute encode over 35,205 papers, a second index to maintain, and a second model resident in the serving process |
| `fusion_dense_pool` **+ cross-encoder** | **1.866** | **18× the arm it reranks** |

The cross-encoder number is the whole chain — base retrieval plus the rerank pass
— because that is what answering a query with it costs. On a feed run over
hundreds of targets it is the entire latency budget, spent on a stage refuted
twice on effectiveness (C-013) and which one human read found helped only the arm
it was rescuing (`EXP-2026-08-014` amendment).

The three-channel arm is twice the cost of the two-channel one at query time and
still under 200 ms; its real price is the index, not the query.

## 4. Threats to validity

1. **One query, one topic area, one reader.** Narrower than `EXP-2026-08-014` on
   purpose; nothing here generalises.
2. **A second round on survivors.** The four arms were selected *by* the previous
   preference, so the population is "arms that already passed one read". A
   judgment here ranks four acceptable options; it says nothing about the six
   dropped.
3. **Titles now carry the entire judgment.** Snippets were removed at the
   reader's request. That makes the booklet readable and makes a good document
   under a dull title easier to miss — a bias shared with the real feed.
4. **Not W5.** Whatever comes back is one person's preference: no interval, no
   aggregation, never a relevance judgment.
5. **Same three gates off** — match thresholds, fellowship eligibility, paper
   freshness (ISSUES §7).

## 5. What this changes

Nothing yet. It is an instrument. `Q-029` stays open until the scorecard comes
back, and the reading that matters most is **whether the three-channel arm — the
one this programme has been recommending on LongEval evidence — is any good on a
real query**, since `EXP-2026-08-014` left it the only arm with no human read at
all.

---

## AMENDMENTS

### 2026-08-22 — the preference came back, and it is category-dependent

One reader, one query (`Agentic AI in healthcare`), read blind. **Not W5**: no
interval, no aggregation, never a relevance judgment.

| | W = production **+ cross-encoder** | X = three channels **+SPLADE** | Y = union pool | Z = **production as deployed** |
|---|:--:|:--:|:--:|:--:|
| **Papers** | **1st** | ≈3rd | ≈3rd | ≈3rd |
| **Grants** | **1st** | ≈2nd | ≈2nd | ≈2nd |
| **Conferences** | **1st** | **4th** | ≈2nd | ≈2nd |
| **Fellowships** | **4th** | 3rd | 2nd | **1st** |

**Every attribution the reader made is correct against `data/lists.json`.** Spot-
checked: the Salesforce-CRM paper they objected to at rank 1 is X's and Y's rank
1 (W has it 4th, Z 3rd); "Agentic AI in Agriculture" is Y=7, Z=6; the predictive-
biomarker grant is X=5, Y=9, Z=6 and **absent from W**; "Mathematical Reasoning
and AI" and the Agentic-Web workshop are X's alone (7th and 9th); and all four
fellowships they rejected — Physicians of Tomorrow, Autism Science Foundation,
Molecular Imaging, Tropical Medicine & Hygiene — are **W's**, three of them
exclusively.

### 1. The cross-encoder won three categories — and the record says it should not have

`EXP-2026-08-009` refuted C-013 on aggregate ranking and `EXP-2026-08-010` refuted
the rescue for it. Here, reranking **production's dense-restricted pool** took
first place on papers, grants and conferences.

Set against `EXP-2026-08-014`'s four paired comparisons, a mechanism appears:

| base pool | + cross-encoder | outcome |
|---|---|---|
| `dense_only` (broad, semantic) | I | **hurt** |
| `fusion_union_pool` (broad, lexical ∪ dense) | J | **hurt** |
| `bm25_only` (broad, lexical) | B | helped |
| `fusion_dense_pool` (**narrow, dense-filtered**) | G / **W** | neutral, then **best** |

**The cross-encoder appears to help when it reranks a narrow, already
semantically-filtered pool and to hurt when it reranks a broad one.** That is not
what "the cross-encoder is refuted" predicts, and it is consistent with both
reads. It remains a hypothesis from five paired comparisons and one judge.

### 2. Fellowships invert it, and the failure is diagnostic

W is *worst* on fellowships, and the reader named exactly why: Tropical Medicine
& Hygiene, Molecular Imaging, Physicians of Tomorrow, Autism Science Foundation.
Every one is a **medical** fellowship with no connection to AI agents.

That is a term-matching failure of precisely the kind an MS MARCO-trained
cross-encoder makes: on a corpus where the query's domain word ("healthcare")
appears as boilerplate in nearly every document, surface matching promotes domain
membership over topical fit, and the dense channel — which W had already used to
build the pool — was the thing keeping it honest. The reranker undid it.

So the right retrieval configuration may **differ by content type**, which no
experiment in this record has considered and which the deployed code cannot
express: `opportunities.py` and the paper pipeline share `fuse_interests_pool`.
Opened as `Q-031`.

### 3. The two arms this programme recommends won nothing

`fusion_union_pool` (C-008's implication) and `fusion_union_splade` (C-014's) took
**no first place in any category**, and the three-channel arm came last on
conferences. Two human reads in a row have now declined to endorse the ladder's
production recommendation — `EXP-2026-08-014` rated the union pool "very good"
but rated its reranked form bad, and here neither wins anything.

This does not refute C-008 or C-014, which are recall claims about LongEval and
were measured properly. It does mean **no human read has yet endorsed the change
they imply**, which matters more for a shipping decision than either claim does.

### 4. What the reader could not separate

"X, Y, Z are equal to one another" (papers), "each one is pretty close" (grants),
"Y and Z are tied… very very similar" (conferences). Three of four categories
ended with a clear winner and a tie for the rest — so the judgment resolves *one*
arm per category and not an ordering.

**Follow-up:** `EXP-2026-08-016` repeats this on a different research area
(`knowledge graphs`) with the same four arms and a **third** blinding, to test
whether W's advantage is a property of the arms or of the healthcare corpus.
