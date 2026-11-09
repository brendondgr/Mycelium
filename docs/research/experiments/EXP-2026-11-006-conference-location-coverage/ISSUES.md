# EXP-2026-11-006 — Issues

- **Dirty tree at scaffold time.** `code.dirty: true` because Phase 1 itself
  (`tools/retrieval/geography.py` and its callers) and the not-yet-committed
  Phase 2 draft (`/mylo populate`) were uncommitted on branch
  `discord-forum-upgrades`. `run.py` uses only `geography.py`, which is committed
  with this folder.
- **Run twice.** The first run surfaced a cosmetic fault in the sample ("Athens,Greece"
  kept its missing space); comma spacing was normalised and the run repeated. The
  numbers were identical; only the display text in `data/sample.json` changed. The
  recorded data is from the second run, against the committed code.
- **Live data, not a snapshot.** The corpus is re-collected nightly; a re-run on a
  later day will count a different 912.
- **Renumbered from EXP-2026-11-005 before merging.** Another session recorded
  `EXP-2026-11-005-fulltext-coverage-own-ids` on main while this one sat on its
  branch. This folder and its references were renamed to EXP-2026-11-006 when
  the branch was merged; nothing in the run or its numbers changed. The
  changelog entry for Phase 1 still names EXP-2026-11-005 and is corrected by a
  later entry rather than edited.
