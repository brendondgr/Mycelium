# EXP-2026-11-024 — Issues

- **`code.dirty` at scaffold time.** `make new-experiment` recorded the tree as
  dirty only because this experiment's own folder was untracked; the fix had
  been committed (`2cc179d9`) and nothing else was uncommitted. The code under
  test is in any case the `git archive` of each arm's commit, so the manifest
  records `dirty: false`.
- **EXP-2026-11-023's copy was gone.** `mycelium_sandbox_fsusc` had been
  dropped, so the department's papers were imported and read again into a new
  copy (`mycelium_sandbox_fsusc24`). The candidate pool therefore differs from
  023's somewhat (OpenAlex as of today, the model's facet reading at
  temperature 0.2, live changes since 2026-11-18). This is why the fix is
  measured as `before` against `after` on this copy, with 023's numbers beside
  them, not differenced against them.
- **First driver attempt failed before doing anything.** The frozen trees made
  by `git archive` have no `web/backend/media/` mount point (it is untracked),
  so the container could not start. An empty directory was created in each
  frozen tree and the command rerun; nothing had run against the copy.
- **Two identity records before the run** (`logs/identity_*.json`, 18:48:12Z and
  18:48:36Z): the first came from a driver invocation whose output my shell
  pipeline failed to parse, so it was run again. Both are kept; they agree.
- **The model's name is a self-report.** "I am a large language model, trained
  by Google", the same self-report EXP-2026-11-023 recorded; the maintainer did
  not state the model for this run. Not to be read as the same model as 023's
  without that confirmation.
