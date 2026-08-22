# EXP-2026-08-017 — Issues

## 1. Pre-registered, and this time before the run

`PROTOCOL.md` was written before either arm was scored — including the three
possible outcomes and what each would mean, so none of them can be reinterpreted
after the fact. `EXP-2026-08-016` recorded a process failure on exactly this
point; this is the correction.

## 2. The two arms differ in one place only

Both call the same `rerank()` closure over their own top 50, the same
cross-encoder instance, the same depth, the same top-10 cut. The pool builders
come from `EXP-2026-08-013` and the sparse encoder and RRF from `eval/harness` —
imported, never reimplemented.

That is the entire design: a comparison that changes one thing is worth running
and a comparison that changes two is not, which is why the previous two booklets
could not answer this question despite containing both arms.

## 3. `code/build_pdf.py` imports the previous booklet's typesetting

Three booklets have now gone to the same reader. A layout difference between them
would be read as a result, so the table, page and style code is
`EXP-2026-08-015`'s, imported rather than copied.

One inherited string had to be replaced rather than reused: that experiment's
per-page caption is written for four arms ("across the four top-tens… 40 that
they share nothing") and both of its counts are wrong with two. It is overridden
in `build()` and the reason is noted at the call site.

## 4. A fourth set of letters

**K and V** — no overlap with `A–J` (`EXP-2026-08-014`), `W–Z`
(`EXP-2026-08-015`) or `M/N/P/R` (`EXP-2026-08-016`). The same letter means the
same arm across both queries and all four categories, so one coherent verdict is
possible.

By this point the reader knows the identities behind `W–Z` and `M/N/P/R`, and one
of these two arms appeared in both previous booklets. The blinding protects the
*comparison*, not the arms' existence — a reader who reasons carefully about which
is which is not doing anything the design forbids, and the honest limit of the
blinding is that it stops anchoring rather than making inference impossible.

## 5. A tie is not a neutral outcome

If the reader cannot separate the lists, that decides the question **in favour of
the cheaper arm** — and that inference comes from the cost table, not from them.
It is stated on the booklet's cover so the reader knows a shrug is a real answer
and what it will be taken to mean.

## 6. Ranks 1–7 are identical on healthcare papers

Noted because it will be the first thing visible: on that page the two arms agree
exactly down to rank 7 and diverge only at 8, and on healthcare grants the two
top-tens are identical outright. That is a property of the run, not a bug in the
table — and it is the substance of §2 in `RESULTS.md`.

## 7. A pool advantage below rank 50 is invisible here

Both arms rerank only their top 50. A document the three-channel pool surfaces at
rank 200 cannot reach the visible list, so this design tests the pools *as
feeders to a shallow reranker* and not their retrieval depth. That is the
deployed shape, but it is not the whole of what C-008 and C-014 claim.

## 8. Working tree dirty

`code.dirty: true`. Uncommitted while running: this experiment's folder. Nothing
under `web/backend/apps/` was modified.
