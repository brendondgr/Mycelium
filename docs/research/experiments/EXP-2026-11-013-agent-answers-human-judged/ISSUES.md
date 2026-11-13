# EXP-2026-11-013 — Issues

- 2026-11-12: arm (a) ran 23:31–23:40 while the nightly run
  (`mylo-daily.service`, started by hand at 22:58) was using the same model
  server and the decision server, and alongside EXP-2026-11-011's gate arm (4
  turns at a time). Seconds per answer in arm (a) are therefore under load;
  correctness is unaffected.
- 2026-11-12, harness bug (fixed before any rating): the timing wrapper read
  `reply.calls`, but the raw port reply names them `tool_calls`, so the
  per-call `function_calls` field in `calls[]` is 0 in arm (a)'s `main` run.
  Turn-level function counts come from the event log and are correct. The only
  number it affects is the repair's cost (tokens and seconds after the first
  draft), which `analyse.py` reports as unknown for that run rather than
  guessing.
- 2026-11-12, harness bug (fixed before any rating): arm (b) and the
  paraphrase step read `reply.text`; the raw port reply's text is `content`.
  The first arm (b) launch failed on every question and was stopped after two
  rows (kept at the session scratch path, not used); arm (b) was rerun from
  scratch. The injection's first launch crashed at the paraphrase step before
  writing anything.
- Only 1 of 50 arm (a) turns triggered the verifier's repair (and that one was
  then stripped), so the removed-item sheet is tiny and verifier precision
  from people will rest on very few items. The injected-error set is the
  substantive evidence on the verifier.
- Injected class 2 (`unread_cite`) produced 0 copies: in a single-turn thread
  every reference the turn surfaced was also in view, so there is no
  "surfaced but unread" reference to move a citation to. The `unread` check
  can only fire on multi-turn threads or after old results are cleared; this
  set cannot test it.
