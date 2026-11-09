# EXP-2026-11-007 — Issues

- 2026-11-09, attempt 1: `InternalServerError 502 — upstream error: ConnectError:
  All connection attempts failed` from the relay at `localhost:4000` (model
  `skynet`, relay health `failed`). Nothing was measured; `logs/attempt.json`
  records the error. Status set to `failed` for this attempt.
- The manifest records `code.dirty: true` because the experiment was
  scaffolded while the Mylo agent change (branch `mylo-agent`) was
  uncommitted; the harness and the agent code it measures were committed
  together in the same change.
