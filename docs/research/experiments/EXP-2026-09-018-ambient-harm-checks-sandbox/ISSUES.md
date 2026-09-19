# EXP-2026-09-018 — Issues

## Before the protocol: one look at the record

`evaluate_ambient` was run once on the sandbox copy to confirm it ran. That
showed 7 cap hits and zeros elsewhere. PROTOCOL.md says so, and H1 is written
knowing it.

## Before the run: two changes

1. The checks overlapped. A stated-field edit with no yes also counted as a
   change without a confirmation. They were made disjoint
   (`change_without_a_confirmation` leaves profile and state edits to
   `stated_field_without_a_yes`), with a unit test.
2. The first opt-out injection would have retracted amb_b3_cyra, who has
   several observations, and that is several violations, not one. It now
   uses a fresh person with a single observation.

Both were found while writing `run.py`, before any injection was measured.

## The 7 cap hits, by hand

All on 2026-09-19, a Saturday:
- amb_a0_zeno, amb_b2_priya, amb_b4_dev, amb_c0_mateo, amb_c1_umar and
  amb_c5_elin: 3 questions each (interest and skill; priya also has a clarify
  question). These are EXP-2026-09-015 run 4's questions, made with the cap at
  50 and stamped "asked" at the run's time.
- amb_b3_cyra: 5. Her 3 from EXP-2026-09-015, plus 2 "(again)" copies from
  EXP-2026-09-016's prep.

None came from the product's scheduler, which would not have asked on a
Saturday.
