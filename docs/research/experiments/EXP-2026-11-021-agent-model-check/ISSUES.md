# EXP-2026-11-021 — Issues

- 2026-11-16 16:33–16:44 UTC, **preflight, not counted.** Two Mylo turns
  (`EXP-2026-11-018` `run.py --only a:1:f01,a:1:p01`, kept in
  `logs/preflight.jsonl`) to see whether the newly loaded model returns
  replies at all, because its answer to the identity question came back
  entirely in the `reasoning` field with `content: null`. Both turns answered
  (one function call each, checker ok). In each, the first model call took
  ~575–582 s for 28–54 completion tokens and the second ~4.7 s: the relay's
  connection, not generation. Six identical tiny calls straight after took
  0.6–227 s, one returning 502 (`upstream error: ConnectTimeout`); the relay
  marked `default-model` `degraded`, then `healthy`, and `default-model-2`,
  `-3`, `-4` `failed`. The maintainer said the server was having trouble on
  2026-11-16. Seconds in this experiment's first row measure that, not the
  model.
- The plan asks for five controls; `EXP-2026-11-016` `probes.py` holds two.
  Each is asked three times (PROTOCOL.md "Data").
- The twelve gold-graded questions use round two's gold (`EXP-2026-11-018`
  `data/gold.json`, built 2026-11-15). Field and people facts move slowly, but
  a value that changed since would grade a right answer wrong; Phase 2 of round
  three rebuilds the gold and any difference on these twelve is reported here.
