# EXP-2026-11-028 — Issues

- 2026-11-24: the model's quantisation and GPU were not stated by the
  operator for this run; `env/hardware.md` records them as unknown.
- 2026-11-24: the sandbox is built by a route the plan did not name
  (allow-list copy of the demo world's rows and the public corpus into a
  fresh database); the reasons are in `PROTOCOL.md`, Setup.
- 2026-11-24 17:13 UTC, before any model turn: the first sandbox check passed
  (every count zero) but its saved copy lost its inner lines, because the
  driver drops indented lines from container output. `check_sandbox.py` now
  prints one line and the driver keeps that line; the check was run again and
  `logs/check_sandbox.json` is the second run's output. No count changed.
- 2026-11-24: the gold builder kept 58 of the 60 frozen questions on the
  sandbox (`l02`: 12 gold items, `l06`: 10; both over its limit of 8). 174
  jobs per arm.
