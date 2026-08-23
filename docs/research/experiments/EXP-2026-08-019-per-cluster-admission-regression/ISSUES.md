# Issues

- **`code.dirty: true`.** The tree carried the per-cluster redesign's frontend
  and documentation edits while the arms ran. The backend ranking path — the only
  code the arms execute — was committed at `7ff764a` and unmodified during the
  run, which is the commit recorded in the manifest.
- **No `slate_profile` baseline at `f0dc7e5`.** Only `e356280` is on record at
  that config hash, so its before/after delta is confounded with two intervening
  commits. See `RESULTS.md` for why the delta is nonetheless attributed
  elsewhere.
- **`compute.wall_clock_hours` is approximate.** Both arms ran in one process
  against the warm embedding cache at `data/eval-cache/`; the corpus load
  dominates and was not timed separately.
