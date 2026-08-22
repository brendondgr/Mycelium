# EXP-2026-08-016 — Protocol

**Not pre-registered** — written after the run, and that is recorded rather than
disguised. See `ISSUES.md` §1 for why it changes nothing here and what it would
have changed if this experiment had a hypothesis.

## Question

`EXP-2026-08-015` produced a clean per-category winner on `Agentic AI in
healthcare`: one arm first on papers, grants and conferences, and **last** on
fellowships. Is that a property of **the arms**, or of **that corner of the
corpus**?

The only way to tell is to repeat the identical measurement somewhere else. This
does it on **`knowledge graphs`** — a different declared research cluster of the
same reader, a different region of the same store — with the same four arms and a
third blinding.

**Either answer is actionable, which is rare in this record.** If the same arm
wins again, it is the arm, and there is a configuration to ship. If a different
one wins, then no single configuration is right for the whole product and the fix
is routing — per content type, or per interest — not a parameter.

## What is identical to `EXP-2026-08-015`

Everything except the query and the letters. The four arms, the pool width
(`pool_per_interest = 100`), the rerank depth (50), the top-10 cut, the four
corpora, the three gates switched off, the table format, the page layout.

**The retrieval code is imported, not copied.** `code/run.py` re-points
`EXP-2026-08-015`'s runner at a new query, a new blinding and this folder, then
calls it. A second copy of the arm code would be a second chance for the two
areas to be scored by subtly different pipelines — which would destroy the single
comparison this experiment exists to make.

## Query

**One**: `knowledge graphs` — general, at the reader's request ("the general
knowledge graphs, nothing specific"), not scoped to any application area.

## Blinding — a third set of letters

**M, N, P, R.** Neither `A–J` (`EXP-2026-08-014`) nor `W–Z`
(`EXP-2026-08-015`), so no verdict from either previous read can carry over, and
no reader can assume a letter kept its meaning. `O` is skipped because it reads
as a zero in a rank column. The permutation is `BLIND_ORDER` in `code/run.py` and
is printed on the last page.

**The healthcare identities are deliberately still withheld from the reader** at
this point, so that read cannot anchor this one. They are in
`EXP-2026-08-015/RESULTS.md`, which is why that file should not be opened until
both reads are done.

## Measurements

The four matrices, pairwise Jaccard@10 between arms, per-query wall clock. **No
verdict**, for the same reasons as `EXP-2026-08-014` and `EXP-2026-08-015`: this
corpus has no relevance judgments, an LLM judge is the component
`EXP-2026-08-008` measured as non-monotonic in relevance, and my own reading of a
knowledge-graph paper is not evidence about what this researcher wants.

## Threats to validity

1. **Not pre-registered** (ISSUES §1).
2. **One query, one reader, one topic area** — the second of two, which is what
   makes the pair informative and still does not make either generalise.
3. **A second round on survivors.** These four arms were selected by
   `EXP-2026-08-014`'s preference, so the comparison ranks four already-acceptable
   options.
4. **Titles carry the whole judgment** — no snippets, at the reader's request.
5. **Not W5.** Whatever comes back is one person's preference: no interval, no
   aggregation, never a relevance judgment.

## Procedure

```bash
docker compose up -d postgres
uv run --project eval python .../code/run.py
uv run --project eval python .../code/build_pdf.py
```
