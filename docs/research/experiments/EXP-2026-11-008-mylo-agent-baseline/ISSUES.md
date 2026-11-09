# EXP-2026-11-008 — Issues

- 2026-11-09, attempt 1: the preflight call failed with `InternalServerError
  502 — upstream error: ConnectError` from the relay at `localhost:4000`.
  Nothing was graded; `logs/attempt.json` records the error.
- The dry run (`--dry-run --reps 1`, `logs/dry_run.json(l)`) used a stub
  model. Its pass rates (permission probes 1.0, everything else ~0) only show
  the graders work: a model that says nothing leaks nothing.
- The manifest records `code.dirty: true` because the experiment was
  scaffolded while the Mylo agent change was uncommitted; the harness and the
  agent code were committed together.
