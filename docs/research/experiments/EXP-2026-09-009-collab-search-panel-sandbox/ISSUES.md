# EXP-2026-09-009 — Issues

1. **Dirty tree at scaffold.** `make new-experiment` ran while EXP-2026-09-008's
   rebuilt world and CN-04's docs were uncommitted; the manifest's commit is
   corrected to the run's commit when results are recorded.
2. **Resized before the run to fit an hour (amended 2026-09-18, pre-run).**
   The owner asked that no experiment run longer than an hour while the model
   server is under heavy load. As registered (120 seekers, every search
   reranked by the model, own words for every fourth) the run would take about
   three hours. Changed before any panel run: 60 seekers; the model reranks
   the first 10 seekers' searches and the rest run with the rerank off (the
   API must answer identically in shape either way, and the rerank's quality
   is EXP-2026-09-008's question); own words for every sixth seeker; 20 calls
   read by the model; a 45-minute wall-clock budget covering the whole run,
   which stops the seeker loop early and reports `stopped_at_deadline`. The
   hypotheses and their bars are unchanged.
3. **Run 1 found own-words search dead; fixed and rerun (recorded).** Run 1
   (`data/exp009-run1.json`): zero violations over 120 searches and every
   refusal path, but all 10 own-words searches ended with no matchable slot —
   the funding-call reader's 20-word floor refused every short statement of
   need before the model was asked. Fixed in `c6e6809` (a
   two-word floor for the manual path) and run 2 made on the same database
   copy with the first run's search logs, feedback and appearances cleared.
   Checked by hand on the real model: "We need someone who can do kriging for
   our data" now reads as a method slot; "survival analysis of patient
   cohorts" reads as a problem rather than a method (the reader's prompt was
   written for calls) — Q-047.
4. **Run 1's raw output was overwritten (recorded).** Copying run 1's JSON
   aside failed on a permission error that went unnoticed, and run 2 wrote to
   the same path. Run 1's numbers survive only as printed during the session:
   0 invariant failures; 60 seekers, 120 searches (60 call, 60 project), 449
   people shown (291 method bridge, 77 in field, 39 problem bridge, 42
   resource), 364 without a reason (the rerank was off for 50 of 60 seekers),
   19 empty results, 34 saves checked, 60 foreign projects refused, 10
   unverified seekers refused, and 10 own-words searches with no matchable
   slot (item 3). Run 2's output is `data/exp009.json`.
