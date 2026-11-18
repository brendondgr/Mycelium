# Issues

## 1. Deviations from the 2026-11-15 configuration

- **Instance settings are today's.** `.env` was modified on 2026-11-15 at
  19:29 UTC and `mycelium.toml` at 14:55 UTC, both after the 11-15 runs
  (05:42–07:01 UTC); the values the 11-15 containers read are not recorded.
  Today: `LLM_REASONING=none`, style `thinking`, temperature 0.2. The replay
  reproduced the 11-15 rate, so whatever changed there did not hide the effect.
- **Load.** 11-15: 3 turns in flight from this harness, with two other
  phases of round two running beside it (up to 8 in flight in all). Here: 6 in
  flight (two arms side by side), other load on the server unknown.
- **One repetition** of the 16 probes and 2 controls per seed and arm (108
  turns per phase), against three on 11-15; the reference is the 11-15 first
  repetition (21 of 108).
- **The server is today's** (`vllm-0.21.0-5c6ca01c`, the 11-17 fingerprint).
  The 11-15 server's build, template and flags are not recorded anywhere, so
  "the same server as 11-15" cannot be shown; what is shown is that today's
  server reproduces the 11-15 rate with the 11-15 code.

## 2. The harness is a copy, not EXP-2026-11-016's file

`code/replay.py` imports EXP-2026-11-016's world, probes and `flow_narrow` and
round one's `run_v2` unchanged (none changed since `44100c04`), but its own
`main()` differs: its own databases (`mycelium_agent_eval_x022_*`, so round
two's databases with the 11-15 threads are untouched), its own logs, the raw
model-reply logger, the diagnostic request, and the thread read-back. These
only observe; the diagnostic request's reply never reaches the loop.

## 3. The diagnostic request is a fresh sample

It is sent after the empty reply, not instead of it, with `tool_choice: none`
and temperature 0.2, so its text is what the model writes for the same
messages, not a recording of the dropped text. In all 39 (Phase 1) and 28
(Phase 2) cases it was a single argument-less call of 13 tokens or less,
which matches the 13 completion tokens of the dropped reply; that is the
evidence, and it is indirect.

## 4. Dry runs kept, not counted

`logs/*_dry*` (labels `dry`, `dry1117`, `dryns`; stub model, no model call)
checked that each frozen copy loads before any counted run.

## 5. Errors seen in the logs that are not results

`projects_get` raised `ValidationError: "… is not a valid UUID"` in the
prompt-only arm at `44100c04` (Q-069, fixed in `a8e21c0e`); as on 11-15, the
model reads the error and answers. Not counted as blank or as an error turn.

## 6. Manifest `code.dirty`

`make new-experiment` recorded `dirty: true` because this experiment's own new
folder was untracked; product code was clean at `a99e1a01`. Set to false.

## 7. Other work during the run, and what is left behind

Another session worked on EXP-2026-11-019 and EXP-2026-11-023 at the same
time; its model record (17:17 UTC) is on `default-model-2` (Qwen 3.8 27B), not
on the server used here. The 22 databases `mycelium_agent_eval_x022_*`
(`f1115`, `f1117`, `f1115ns` × three seeds × two arms, plus four dry runs) are kept
so the threads can be re-read; nothing else on the instance was touched.
