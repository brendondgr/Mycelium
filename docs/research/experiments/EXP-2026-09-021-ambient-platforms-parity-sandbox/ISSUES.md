# EXP-2026-09-021 — Issues

## Run 1 — registered (7a62e91)

All five hypotheses held. The corpus has no one without an account, and
everyone in it is opted in and on a paid plan, so only the too-short drop was
exercised. That is too weak a test of H2.

## Run 2 — post hoc (4c97fb7)

Added `--gates` after seeing run 1. It is deterministic:
- every third person is opted out (on every platform, through the mirrored
  consent);
- every fifth is on a free plan;
- every seventh channel line is spoken by a guest with no account.

The result was the same parity. The Django test client's CSRF debug lines in
the log are the dev settings' request logging, not failures (every response
was 200, which the harness asserts).
