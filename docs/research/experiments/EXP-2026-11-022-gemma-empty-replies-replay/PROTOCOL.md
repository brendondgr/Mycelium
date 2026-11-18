# EXP-2026-11-022 — Protocol

Written 2026-11-18 (about 17:15 UTC) before any model call of this experiment.
Correlation `20261118-gemma-empty-replies-replay`. Open questions Q-070, Q-088.

## Question

On 2026-11-15 Gemma 4 31B (relay `default-model`) ended 47 of 324 Mylo turns of
EXP-2026-11-016's instance-model rows with no reply (14.5%; 21 of 108 in the
first repetition); on 2026-11-17 the same model, as the operator stated it,
ended 0 of 180 turns blank, twice (EXP-2026-11-019 Amendments 7, 8). Is the
difference in **our code** (what Mycelium sent and how it read the reply) or in
**the model server**? Answered by one number: blank turns when the 2026-11-15
code is replayed, unchanged, against today's server.

## What the record already says (read before the run)

- The 11-15 runs used product code `14a24374` (identical to `44100c04` in
  `tools/` and `web/backend/`; `git diff 14a24374 44100c04 -- tools web/backend`
  is empty), harness `EXP-2026-11-016/code/run_gate.py` (unchanged since).
- Their databases are kept (`mycelium_agent_eval_r2_<seed>_<arm>_instance`).
  Read 2026-11-18: every blank turn has the same shape. The empty step is
  never the first: it follows a function result (`load_functions`,
  `find_functions`, `me_interests`, `projects_get`, `projects_list`,
  `corpus_search`, `org_labs`, …); the step's stored usage is **13 completion
  tokens (9 in 8 cases)**, the stored text is empty, with no call and
  `repairs: ["empty_retry"]` (the stored usage is the retry's). No finish
  reason and no raw reply were stored. Other 11-15 steps of the same model
  carry Gemma's channel markup in their text (`<|channel>thought\n<channel|>…`),
  so that markup was **not** stripped on 11-15: `llmcall` at `44100c04` tests
  `response.content.strip()` before any parsing, so an empty content means the
  server sent no visible text.
- The 11-17 empty calls were a different shape: the **first** step of a turn,
  `finish_reason: tool_calls`, 35–51 completion tokens, no parsed call.
- What changed in the request between the two days (code): `a8e21c0e`
  (2026-11-15 10:58 EST, after the 11-15 runs) makes every agent call send
  `max_tokens: 4096` and `thinking_token_budget: 512`; on 11-15 the agent sent
  no `max_tokens`. The client (`apps/core/llm.py`) is otherwise unchanged
  between `14a24374` and `127428f3`. Prompt, function index, recall and the
  loop's retries also changed (`git log 14a24374..55cfdb1c -- tools/agent`).
  At `44100c04` a function loaded with `load_functions` is not offered until
  the next turn (the loop's thread row is stale; fixed in `90882479`, 11-17,
  after the 11-17 morning runs), so the model may call a function that the
  request does not offer.
- What changed (server): unknown. The 11-15 record has no server version; the
  11-17 preflights read `vllm-0.21.0-5c6ca01c`. `.env` and `mycelium.toml`
  were modified on 11-15 *after* the runs (14:29 and 09:55 EST); today's
  `.env` has `LLM_REASONING=none` (`enable_thinking: false`), temperature 0.2.
  The 11-15 values are not recorded.

## Hypothesis

Leading hypothesis (H-code): the blanks are produced by our 11-15 request, most
likely the model calling a function the request did not offer (a just-loaded or
a not-loaded function) and the server dropping that call, so they will
**reproduce** when the 11-15 code is replayed against today's server. The
alternative (H-server): the server changed between 11-15 and 11-17 (build, chat
template, call parser, checkpoint or launch flags); then the 11-15 code against
today's server gives about as few blanks as 11-17 did. Today's server is the
11-17 evening one (`default-model`, Gemma 4 31B, as the operator states it) if
the preflight says so; if it does not self-report as Google-trained, nothing is
run.

## Setup

- **Phase 1, `f1115`:** `tools/` and `web/backend/` of `44100c04` frozen
  (`git archive`), mounted read-only over the checkout in one-off backend
  containers. Harness `code/replay.py`: EXP-2026-11-016's harness (its world,
  probes, `flow_narrow` and round one's `run_v2`, imported unchanged) with
  its own databases (`mycelium_agent_eval_x022_<label>_<seed>_<arm>`), its own
  logs, a port wrapper that logs every raw model reply, and a read-back of each
  thread (so a turn that ends on a clarifying question is not blank).
- **Model:** relay `default-model`, `LLM_MODEL=default-model`, instance
  settings as they are today (`LLM_REASONING=none`, style `thinking`,
  temperature 0.2), `AGENT_PARALLEL_CALLS=0` as on 11-15.
- **Diagnostic, not a result:** when a model call returns no text and no call,
  the wrapper sends one extra request beside it: the same messages and
  functions, `tool_choice: none`, `skip_special_tokens: false`, not streamed.
  It is a fresh sample (temperature 0.2), never seen by the loop; its raw text
  shows what the model writes for that request when the server's call parser
  is not applied.
- **Load:** per seed, the two arms side by side, 3 turns in flight each: at
  most 6 model requests in flight (cap 8). Total model load is capped at 90
  minutes. `mylo-daily.service` is idle (last run ended 14:22 UTC; next 12:00
  UTC 2026-11-19).

## Data

EXP-2026-11-016's seeded worlds and probes: seeds 101, 202, 303; both arms
(gate, prompt-only); 16 access probes + 2 controls; **one repetition**: 108
turns per phase. Reference from 11-15, the same 108 (seed × arm × task, rep 0):
21 blank (19.4%); all three repetitions: 47 of 324 (14.5%). Fictional data;
no human judgments are involved; "blank" is mechanical.

## Metrics

- **Primary — blank turns / turns:** a turn is blank when it was not refused,
  raised no error, and the person would see nothing: no final text and no
  clarifying question (EXP-2026-11-016 Amendment 1's "reply the reader
  sees"). Reported by phase and arm, with a Wilson 95% interval.
- **Secondary — turns with an empty model call / turns, and empty calls /
  calls:** a call whose content is blank, with no call and not cancelled
  (later code repairs these turns, so this is the measure that compares
  across commits). Split by position (first step vs after a function
  result), finish reason and completion tokens.
- **Descriptive:** the diagnostic requests' raw text; whether a call in it
  names a function that the request did not offer.

## Baselines

The 11-15 rows of EXP-2026-11-016 (same seeds, arms, tasks, first repetition):
21 of 108 blank. The 11-17 Gemma runs (EXP-2026-11-019 r4/r5/r6): 0 of 180
blank, 3–4 empty calls in about 950.

## Procedure

```bash
S=<scratchpad>; git archive 44100c04 tools web/backend | tar -x -C $S/snap-44100c04
mkdir -p $S/snap-44100c04/web/backend/media
for seed in 101 202 303; do
  for arm in gate prompt_only; do
    SNAP=$S/snap-44100c04 LABEL=f1115 SEED=$seed ARM=$arm \
      bash docs/research/experiments/EXP-2026-11-022-gemma-empty-replies-replay/code/drive.sh &
  done; wait
done
python3 docs/research/experiments/EXP-2026-11-022-gemma-empty-replies-replay/code/analyse.py
```

Each container writes the model record (relay listing, self-report, server
fingerprint) at its start and end to `env/model_record.jsonl`. Dry runs
(`--dry-run`, stub model, label `dry`/`dry1117`) were made before this protocol
to check that the frozen code loads; they are kept and not counted.

**Phase 2 (only if Phase 1 reproduces), `f1117`:** the same 108 turns from a
frozen copy of `55cfdb1c` (the code of EXP-2026-11-019 r4, the first 11-17
Gemma run; dry-run checked on both arms). Its loop repairs empty replies, so
the comparison is the secondary metric (turns with an empty model call). If
time allows after that, one bisection step at the most likely commit named by
Phase 1's diagnostic text.

## Decision rules (written before the run)

- **Reproduces (H-code):** ≥ 5 blank turns of 108 in Phase 1. Then the cause is
  in what our 11-15 code sent or read; Phase 2 runs to place it between
  `44100c04` and `55cfdb1c`.
- **Does not reproduce (H-server):** ≤ 1 blank turn of 108. At the 11-15
  first-repetition rate (19.4%) P(≤ 1) < 10⁻⁸; at the all-repetition rate
  (14.5%) about 2·10⁻⁶. Then our code is not the cause and the server changed
  between 11-15 and 11-17; only the operator can say how. Phase 2 is not run.
- **2–4:** neither; one more repetition of Phase 1 (108 turns) before
  deciding on the pooled 216 with the same thresholds doubled (≥ 10 / ≤ 3).
- If the self-report at the start or end of any container is not
  Google-trained, or the relay lists `default-model` unhealthy, that
  container's rows are recorded and not counted.

## What would falsify this

H-code is falsified by ≤ 1 blank in 108 (rule above). H-server is falsified by
≥ 5. Neither result says *which* server setting or *which* code change; the
diagnostic text and Phase 2 narrow it, and anything server-side has to be
confirmed by the operator.

## Amendment, 2026-11-18 17:35 UTC — before Phase 3 (after Phases 1 and 2)

Phase 1 reproduced (19 of 108 blank) and Phase 2 ran as registered. What they
showed that bears on the next step: every empty call, at both commits, follows
a function result, has `finish_reason: tool_calls` and 13 (twice 9) completion
tokens, and its diagnostic re-request shows an argument-less call in Gemma's
markup (`<|tool_call>call:projects_list{}<tool_call|>`, `files_list`,
`me_profile`). The same short calls are parsed correctly 103 times in Phase 1,
including calls to functions the request did not offer — so neither the
missing arguments nor an unoffered name is enough. A cause that is not
deterministic in the text is consistent with the server's **streamed** call
parsing (the agent streams every call).

**Phase 3, `f1115ns` (the one bisection step the protocol allowed, at the
transport rather than at a commit):** Phase 1 exactly (frozen `44100c04`, both
arms, seeds 101/202/303, one repetition, 108 turns, 6 in flight), with one
change made in the harness process only: the agent's calls go out unstreamed
(`LLMClient.complete_stream` replaced by `complete`, `--no-stream`). The
frozen product code is not edited.

- **Streaming is the trigger:** ≤ 1 turn with an empty call of 108 (Phase 1:
  20; Phase 2: 14). Then the server's streamed function-call parsing drops
  these calls, and the 11-15 code had no repair for it.
- **Streaming is not the trigger:** ≥ 5 turns with an empty call. Then the
  dropping happens in the server's call parser whether streamed or not.
- 2–4: not decided; reported as is.

Model load so far about 17 minutes; Phase 3 is about 8 more.
