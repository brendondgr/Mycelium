# PROTOCOL — EXP-2026-08-007

Written **before** the run. Follows directly from EXP-2026-08-006's `ISSUES.md`.

## Question

EXP-2026-08-006 measured a **34.4 % refusal rate** for the fast extraction arm
and a **6.2 %** rate for the thinking arm, and `ungrounded_prose` was the
dominant failure in *every* arm. Was that a real quality difference between
reasoning levels, or an artefact of a mis-set validator?

## The defect under test

`overlap_ratio(claim, source)` is `|claim_words ∩ source_words| / |claim_words|`,
gated at `PROSE_FLOOR = 0.45`. Measured on the live stores:

| domain | distinct content words in the source (min / median / max) |
|---|---|
| conference | 6 / **9** / 14 |
| grant | 12 / **484** / 1142 |

Conference records are stubs because `cfp_text` is `""` on all 2,234 rows — the
prompt is title + acronym + series name + CCF area codes. A 2–3 sentence summary
carries roughly 35 content words, so the **ceiling** on overlap against a 9-word
source is 9/35 ≈ 0.26, and reaching even that would require reusing every single
source word.

**The 0.45 floor is therefore unsatisfiable for a conference by construction.**
It came from the collector, where it guarded summaries of *fully fetched web
pages* — the same number against a completely different denominator.

## Hypothesis

1. Conference refusals in EXP-2026-08-006 were near-total and drove the headline
   number; grant refusals were much lower.
2. Replacing the flat floor with a source-length-aware test collapses the
   refusal rate, and collapses it **most** for the fast arm — because that arm
   was being punished hardest by a test it could not pass.
3. Consequently the speed/coverage trade-off that appeared to force a choice
   between a 1-hour and a 12-hour backfill will substantially narrow or vanish.

Recorded so it can be wrong: if refusal stays high for `thinking-none` after the
fix, then the 34 % was real, the trade-off stands, and the arm choice is a
genuine product decision rather than a bug.

## The change (exactly one variable)

`grounding_failures(prose, source)` replaces the flat check with two regimes:

- **Rich source** (`≥ MIN_SOURCE_WORDS_FOR_OVERLAP = 80` content words): the
  0.45 overlap floor, unchanged. Grants keep the strict test.
- **Stub source** (`< 80`): overlap is not tested, because it cannot be
  satisfied honestly. Instead the prose must **invent no specifics** — every
  year, ordinal, bare integer and money token in the summary must appear in the
  source. A model summarising nine words cannot be asked to reuse them, but it
  can be held to inventing nothing.

Topic grounding gets the same two regimes for the same reason: against nine
source words, demanding every topic reuse one of them means the only acceptable
topics are the ones already there, which makes extraction pointless.

Everything else — prompts, schema, `MAX_ATTEMPTS = 3`, the sample, the seed,
temperature 0.0 — is byte-identical to EXP-2026-08-006.

## Design

Four cells at **16 workers** (EXP-2026-08-006 found no plateau at 12;
0.905 → 1.125 rec/s), `n = 32`, same seed, same records:

| # | Arm | Why |
|---|---|---|
| 1 | `thinking-none` | the fast arm, the one the fix should help most |
| 2 | `thinking-medium` | the high-coverage arm; the comparison that matters |
| 3 | `effort-low` | best first-attempt validity previously (0.531) |
| 4 | `thinking-none` (repeat) | **drift check** against cell 1 |

`effort-medium` is dropped: EXP-2026-08-006 showed it strictly dominated —
slower than `thinking-medium` (44.4 s vs 31.2 s) *and* refusing far more
(28.1 % vs 6.2 %).

Cell order interleaves cheap and expensive arms rather than grouping them, and
cell 4 repeats cell 1 at the end. If the endpoint drifts during the run, cells 1
and 4 diverge and say so. That is the control EXP-2026-08-006 lacked, which is
why its 4- and 8-worker cells were unusable.

No concurrency sweep. That question was answered as well as a shared endpoint
allows; repeating it would only re-measure the proxy's mood.

## Metrics

Primary: **`refusal_rate`, split by domain** — the number EXP-2026-08-006 could
not produce (its `ISSUES.md` §2).

Secondary: `verified_records_per_second`, `median_latency_s`,
`first_attempt_valid_rate`, `mean_attempts_per_verified_record`,
`failure_reasons` per domain, `projected_backfill_hours`.

## What would refute the hypothesis

- Conference refusal stays above ~20 % after the fix → the floor was not the
  main cause.
- `thinking-none` refusal stays materially above `thinking-medium` → the
  speed/coverage trade-off is real and a human must choose.
- Cells 1 and 4 diverge by more than a few points → the endpoint drifted and
  **nothing in this run is comparable across cells**; report that and re-run.
- `unsupported_claim` becomes the new dominant failure → the replacement test is
  too strict in its own way, and the fix traded one artefact for another.

## Threats to validity

- Same shared endpoint, same lack of isolation. Cell 4 is the detector, not a
  cure.
- `n = 32`, single run, no seed replication. Sizes a decision; establishes no law.
- The 80-word threshold is a judgement, not a measured optimum. It sits far above
  the conference maximum (14) and far below the grant median (484), so no record
  in this corpus is near the boundary — but that is a property of *this* corpus,
  and a future source with 60-word descriptions would land in the gap untested.
- Loosening a validator to raise a pass rate is exactly how a check gets
  quietly gutted. The `unsupported_claim` counter is the guard: if the stub
  regime were vacuous, invented specifics would sail through and never be
  counted. A run where it fires **zero** times on every arm is suspicious, not
  reassuring, and should be treated as evidence the replacement test is inert.

## Exclusions

Retrieval quality is not measured. Whether extracted text embeds better than raw
text is a separate experiment.
