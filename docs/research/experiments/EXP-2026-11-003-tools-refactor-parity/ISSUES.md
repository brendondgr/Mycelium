# EXP-2026-11-003 — Issues

- `code.dirty: true`: the scaffold was created before the Phase 0 commit; the
  only uncommitted files were this folder and the golden snapshot files. No
  ranking code was modified when the before-runs were produced.
- Run files are compared after decompression. The `.txt.gz` bytes are not
  comparable across runs because gzip records a timestamp.
- Each "after" run is produced from the phase's finished but not yet committed
  tree (the commit records the result), so the SHA in the run-file name is the
  previous phase's commit. The phase's own commit hash is recorded in RESULTS.md.
