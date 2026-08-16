# RESULTS — EXP-2026-08-007

Run 2026-08-16. `n = 32` (16 grants, 16 conferences), 16 workers, four cells,
same seed and same records as EXP-2026-08-006. One variable changed: the
grounding test is now scaled to the amount of source available.

Raw numbers: `data/metrics.json`, `data/metrics.csv`.

## Headline

**The 34.4 % refusal rate EXP-2026-08-006 attributed to the fast reasoning arm
was a validator artefact. It falls to 3.1 %.** The speed-versus-coverage
trade-off that appeared to force a choice between a 1-hour and a 12-hour
backfill has collapsed.

| Arm | rec/s | median | refusal — all | grants | conferences | projected backfill |
|---|---|---|---|---|---|---|
| `thinking-none` | **1.798** | 3.45 s | **3.1 %** | 0.0 % | 6.2 % | **0.68 h** |
| `thinking-medium` | 0.359 | 26.06 s | 0.0 % | 0.0 % | 0.0 % | 3.42 h |
| `effort-low` | 0.836 | 12.39 s | 0.0 % | 0.0 % | 0.0 % | 1.47 h |
| `thinking-none` (repeat) | 1.733 | 3.16 s | 3.1 % | 0.0 % | 6.2 % | 0.71 h |

**The backfill is ~41 minutes**, thinking off, 16 workers.

## The drift control held

Cells 1 and 4 are the same arm, run first and last: **1.798 vs 1.733 rec/s,
refusal 0.031 in both, identical per-domain breakdown.** The endpoint did not
drift, so cross-cell comparison in this run is legitimate — which is exactly
what could not be said of EXP-2026-08-006's 4- and 8-worker cells.

## Hypotheses, judged

1. **Conference refusals drove the headline number — CONFIRMED.** After the fix,
   grant refusal is **0.0 % in every arm** and all remaining refusals are
   conferences. In EXP-2026-08-006, `ungrounded_prose` fired 37 times for
   `thinking-none`; here it fires **zero** times — and grants kept the identical
   0.45 floor throughout, so those 37 were essentially all conferences hitting an
   unsatisfiable test.
2. **The fix helps the fast arm most — CONFIRMED.** `thinking-none` refusal fell
   34.4 % → 3.1 % (an 11× reduction). `thinking-medium` fell 6.2 % → 0.0 %.
3. **The trade-off narrows or vanishes — CONFIRMED.** 34.4 % vs 6.2 % became
   3.1 % vs 0.0 %. Thinking now buys about **one record in 32** of extra
   coverage, for **5× the wall-clock**.

## Is the loosened check inert? No — verified directly

Zero `unsupported_claim` failures across all four cells is the signal the
protocol named as suspicious, so the validator was exercised directly rather
than inferred from the run:

| Case | Source words | Verdict |
|---|---|---|
| stub + faithful prose, no numbers | 10 | pass |
| stub + **invented year** (`1998`) | 10 | **refused** `unsupported_claim` |
| stub + **invented attendance** (`4500`) | 10 | **refused** `unsupported_claim` |
| stub + a number that *is* in the source (`2026`) | 10 | pass |
| rich + grounded prose | 107 | pass |
| rich + **ungrounded prose** (overlap 0.00) | 107 | **refused** `ungrounded_prose` |
| rich + **half-grounded** (overlap 0.22) | 107 | **refused** `ungrounded_prose` |

Both regimes fire. The strict 0.45 floor is untouched and still catches
ungrounded prose on any source above 80 content words — which is every grant.
Zero `unsupported_claim` therefore means the model genuinely did not invent
numeric specifics on conference stubs, not that the test is vacuous.

## What now fails instead

`out_of_bounds` is the dominant remaining failure and it is **entirely
conferences** (8, 1, 4, 7 across the cells). That is the summary-length bound
(40–900 chars) or the topic-count bound (2–6). Given a 9-word source, a model
asked for "2–3 sentences" sometimes returns less. This is a **correct** refusal
— the bound is doing its job — but it is worth knowing that the remaining 6.2 %
conference refusal is about *shape*, not *truthfulness*.

Every one of those was recovered by a repair attempt in the arms that reached
0 % refusal, which is the loop working as designed.

## Answering the question that started this

The plan carried **5–6 hours**, extrapolated from the collector's published
table for a different server. The measured answer, on this endpoint, with the
validator corrected:

**~41 minutes at 16 workers with reasoning off, refusing 3.1 % of records.**

Roughly an order of magnitude out, and the error was compounded by a validator
that made the fast arm look far worse than it is.

## AMENDMENTS

None.

## What this does not show

- **Nothing about retrieval quality.** Whether extracted text embeds better than
  raw text is a separate experiment, still unrun. Everything here is cost and
  refusal.
- **The 80-word threshold is a judgement, not an optimum.** No record in this
  corpus sits near it (conference max 14, grant median 484), so it is untested
  in the 15–80 band. A future source with 60-word descriptions lands there
  unmeasured.
- **`n = 32`, single run, no seed replication.** The drift control shows the
  endpoint was stable *during this run*; it is not a variance estimate.
- **`out_of_bounds` bounds were not tuned.** They were carried over unexamined
  and are now the dominant failure. A follow-up should check whether 40 chars is
  the right floor for a venue described in nine words.
