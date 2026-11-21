# EXP-2026-11-026 — Issues

- 2026-11-21 17:34 UTC: the first driver start failed at its first container
  before any model turn: the frozen snapshots (`git archive`) have no
  `web/backend/media` directory, so the read-only `web/backend` mount had no
  mount point for the writable media volume. Fixed by creating the empty
  directory in each snapshot (as the Qwen run's snapshot had). Logs in
  `data/raw/run/aborted-1/`.
- 2026-11-21 17:39 UTC: the driver was stopped after part 1 and restarted with
  `ITEMS="2 34 56 7"` so part 3 runs through `code/ink_replay.py`
  (PROTOCOL Amendment 1). No part was interrupted mid-run.
- 2026-11-21 18:08–18:12 UTC: Postgres connection limit (100) exhausted by
  parts 3 and 4 running together; 34 part-3 turns failed with "too many
  clients". The live app shares that Postgres and may have seen connection
  errors in those minutes. Part 3 stopped and set aside
  (`data/raw/run/aborted-2-part3/`); PROTOCOL Amendment 2.
- 2026-11-21 19:17–21:24 UTC: one part-3 model request (seed 101, code arm)
  never returned; the harness has no deadline on a streamed request that
  stays open, so the process waited two hours. Stopped and rerun in full
  (PROTOCOL Amendment 3). The same can happen in any part; the per-container
  timeouts in the driver (2–7 h) are the only backstop.
