# EXP-2026-11-018 — Issues

- 2026-11-15, **defect found by the run (Q-075), not fixed.** In arm (a) `j08`
  rep 1 the model called `projects_feed` with a project's *name*
  (`project: "Marine heatwave early warning"`) instead of its reference. The
  gate denied it as `not_visible` — "Marine heatwave early warning is not
  something you can open" — although the project is visible to the asker. The
  model then listed the projects and called again correctly (`project: "#1"`),
  but the loop's per-function failure limit (`FAILURE_LIMIT = 2` in
  `tools/agent/loop.py`) had already counted the two denials, so every
  corrected call was refused (`keeps_failing`) for the rest of the turn and
  the answer said the feeds could not be accessed. Two problems: a wrong
  argument reads as a permission denial, and a corrected call is blocked by
  failures of the wrong one. Related to Q-069 (EXP-2026-11-016: a slug passed
  as a project id).
- 2026-11-15, **arm (c) turns that end by asking the person a question.** With
  only the corpus functions, some turns call `ask_user` (after searching for a
  function that is not loaded) and end `waiting` with no final answer. The
  protocol counts a job with no final text as failed and retries it once;
  failures are reported per arm and per reason in RESULTS.md. A question back
  to the person earns no credit, which is the pre-registered rule.
- The instance model behind `default-model` is not the one round one
  recorded (see `env/hardware.md`); identified only by its self-report.
- Audited agent functions (`org_lab_members`, `org_person`, `knowledge_*`)
  write one audit row per call to the live database, attributed to the demo
  PI and targeting the demo thread. That is the product's own behaviour for any
  Mylo turn; the rows were counted by `code/cleanup.py` before the threads were
  deleted and are left in place (an audit log is not edited). Count
  below.
- **Audit rows and cleanup (2026-11-15 07:10 UTC, `logs/cleanup.json`).**
  Before deleting, `code/cleanup.py` counted the audit rows the harnessed turns
  wrote: 60 `agent.org_lab_members`, 9 `agent.org_person`, 14
  `agent.knowledge_people_for_call` (83 in all, across this experiment,
  EXP-2026-11-020 and EXP-2026-11-013 Amendment 5). They are left in place.
  Deleted: 605 demo threads (404 of this experiment — one per arm a/c attempt —
  150 of EXP-2026-11-020, 51 of EXP-2026-11-013) and their 15,740 events.
  Nothing else was written to the live database.
- **Record size.** `data/runs.jsonl` (every attempt with its full function
  results) is 10.9 MB, over the 10 MB folder limit, so it is stored gzipped as
  `data/runs.jsonl.gz` (3.2 MB); `code/grade.py` reads the `.gz` when the
  plain file is absent (a read-path change only; the metrics were checked
  byte-identical before and after).
- `j05` (arm a): in all three repetitions the first attempt's model call
  streamed until the harness's 900 s deadline (first token after 0.2–3 s, no
  end); every retry answered in 21–32 s. The agent has no output cap by
  default (`max_output_tokens` 0), so only the harness deadline ended it
  (Q-078).
