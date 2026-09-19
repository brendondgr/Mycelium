# EXP-2026-09-008 — Issues

1. **The first world build never finished (recorded, not deleted).** The
   600-person build started 2026-09-18 19:59 ran 35 minutes at full CPU with
   no output: the world generator drew given × family name pairs until it
   found an unused one, and 600 people exceed the pairs available, so the
   draw never ended. No data was written; the database still held the
   240-person world. Fixed in `sandbox/collab/world.py` (`_unique_name`: a
   middle initial once the pairs run out, drawn only then, so every world
   below the limit — including EXP-2026-09-005 to -007's 240 — is unchanged)
   and rebuilt. The `match` command was also missing from the harness's
   command list and would have been refused; added.
2. **The second build failed at seeding (recorded).** The rebuild wrote the
   whole corpus (2,734 papers; 2,706 with an abstract — 28 calls failed while
   the model server was under heavy load and are retried by the next build),
   then failed flushing the sandbox database, because EXP-2026-09-010's smoke
   run was writing to the same database at that moment. An operator error, not
   a code fault; the build was rerun with nothing else on the database.
3. **A second arm, declared before any matcher run.** EXP-2026-09-010's smoke
   run (240 people) showed short concept phrases for *different* methods
   matching at the registered lane threshold (0.70): across the world's
   method names, 12.75% of distinct-method pairs reach 0.70 and none reach
   0.80. The shipped matcher now matches concepts at
   `COLLAB_CONCEPT_MATCH_COSINE = 0.80`. This experiment therefore runs:
   **arm A** exactly as registered (`--concept-cosine 0.70`), and **arm B**
   with the shipped setting (0.80). H2's bars apply to both; the decision
   follows arm A's result, never replaces it.
4. **The world build's two invariant flags are load, not code.** Two of 2,734
   papers got a 502 from the model relay on the first reading pass (the server
   was under heavy load) and were read on the second, which the harness flags
   as `second_pass_model_calls = 2`. Every other build check held: 2,732 read
   first time, method recall 0.998, Q1 precision and recall 1.0, no wrong
   merges, 17 method splits (Q-043).
5. **Arm C is post hoc — declared after arm A's result, before its own run.**
   Arm A failed H2's hit-rate bar (0.46 against 0.80) with precision 0.98 and
   2.66 of 3 method-bridge places filled per search: the lane's three places
   were shared by all of a project's method slots and ranked across them, so
   a project needing three methods tended to get three people for its easiest
   one. Arm C fills each lane's shortlist and places slot by slot (the best
   person for each slot, then the second best, and so on, never the same
   person twice) — a change prompted by arm A's numbers, so it is reported as
   exploratory, and H2 is judged on arm A, not on arm C. Arm C runs on the
   shipped concept threshold (0.80), so it is compared with arm B.
6. **Arm C's first run was invalid — a harness bug (recorded).** To use the
   model server's headroom the harness was changed to run searches in
   parallel (`610f8cf`); it stored results by project name, and the world's 96
   projects share 24 names, so results were scored against the wrong seeker:
   the run (`data/exp008-armC-invalid.json`) reported 293 and 103 gate
   "violations" and a hit rate of 0.17 that belong to the scoring, not the
   matcher. Fixed in `edb7c55` (keyed by lab and project) and arm C rerun on
   the same database with the invalid run's search logs cleared. Arms A and B
   ran before the parallel change and are unaffected.
