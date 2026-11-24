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
- 2026-11-24 17:15 UTC, after the smoke check, before the measured run: in
  the six smoke rows `gate_would_not_allow` was 4 to 6 per job in both arms,
  more than the functions called, because the gate is also asked about every
  function when the catalog is built (`permissions.py`, the per-function
  listing, `args=None`). The counter now counts real calls only
  (`args is not None`). The smoke rows keep the old count. The smoke check
  otherwise passed: the policy text ended the prompt arm's system prompt in
  3 of 3 jobs and was absent in the code arm's 3; it listed the two demo
  projects only; the turn's own `denied` count was 1 in one code-arm job
  (`f01`) and 0 in every prompt-arm job.
- 2026-11-24, Qwen run: 2 first attempts failed in each arm and succeeded on
  the one retry (176 rows per arm for 174 jobs).
- 2026-11-24: the sandbox copies for the second and third model
  (`mycelium_sandbox_exp028q`, `…exp028i`) keep the 119 audit rows and the
  one usage-counter row the first run wrote, all for demo accounts; only
  the chat threads were emptied.
