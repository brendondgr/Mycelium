# EXP-2026-11-005 — Issues

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
