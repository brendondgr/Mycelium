# EXP-2026-08-016 — Issues

## 1. `PROTOCOL.md` was written after the run

Stated plainly because the record's rule is to write it first. What happened: the
run is a repetition of `EXP-2026-08-015`'s procedure with one constant changed,
it takes twenty seconds, and it was launched in the same breath as the folder was
scaffolded.

**Why it changes nothing here.** This experiment has no hypothesis and produces
no verdict — the pre-registration a protocol protects is protection against
choosing an analysis after seeing the result, and there is no analysis to choose.
The two things that *were* chosen are the query (the reader's, given before
anything ran) and the blinding permutation (a constant in `code/run.py`, and with
no verdict to favour there is nothing it could be chosen to favour).

**What it would have changed.** If this experiment tested a claim, writing the
protocol afterwards would void it, and it should be read that way in any future
case. It is recorded as a process failure rather than excused.

## 2. The retrieval code is imported, not copied

`code/run.py` re-points `EXP-2026-08-015`'s runner — its query, its blinding, its
output directory — and calls it. `code/build_pdf.py` imports that experiment's
table, page and style code and redefines only the cover, key page and footer.

This is the whole point of the experiment. The comparison being made is *between
two areas scored by the same pipeline*; a second copy of the arm code would be a
second chance for the pipelines to differ and the comparison would be worthless.
The typesetting is shared for the same reason at one remove: two booklets with
different layouts invite a reader to see a layout difference as a result.

`EXP-2026-08-015` is a completed folder and was not modified — only read.

## 3. A third set of letters

**M, N, P, R.** No overlap with `A–J` (`EXP-2026-08-014`) or `W–Z`
(`EXP-2026-08-015`), so neither previous read's verdicts can carry into this one
and no letter can be assumed to have kept its meaning. `O` is skipped because it
reads as a zero in a rank column.

The healthcare identities were **withheld from the reader** while this read was
outstanding. They are recorded in `EXP-2026-08-015/RESULTS.md`, so that file
unblinds the previous booklet and should not be opened until both reads are done.

## 4. No verdict, same reason as the previous two

No relevance judgments exist for this corpus; an LLM judge is the component
`EXP-2026-08-008` measured as non-monotonic in relevance; and my own reading of a
knowledge-graph paper is not evidence about what this researcher wants. The
judgment is the reader's, and when it arrives it is one person's preference over
one query — not W5, no interval, never aggregated.

## 5. Same three gates off

Match thresholds (they gate on a cosine only the dense channel populates —
C-019), the fellowship eligibility engine, and the paper freshness gate.
Unchanged from `EXP-2026-08-015` ISSUES §7 and stated on the booklet's cover.

## 6. Working tree dirty

`code.dirty: true`. Uncommitted while running: this experiment's folder and the
`EXP-2026-08-015` amendment. Nothing under `web/backend/apps/` was modified.
