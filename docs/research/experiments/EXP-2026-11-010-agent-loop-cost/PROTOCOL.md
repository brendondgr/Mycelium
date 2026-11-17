# EXP-2026-11-010 — Protocol

Written 2026-11-09, before any run.

## Question

How long does one Mylo agent turn take, and how many tokens does it use, when
it makes 1, 5 or 15 model calls against the instance's real endpoint on this
host?

## Hypothesis

A 5-step turn completes in under 60 s and under 30k tokens; a 15-step turn
stays under the default 32k-token context window without compaction.

## Setup

The agent's own system rules (`tools/agent/prompt.py` `BASE_RULES`) and the
schemas of its core functions, sent through `apps.core.llm.LLMClient.complete_stream`
exactly as a turn does, with no output cap (D-6). Function results are
scripted: every `corpus_search` call is answered with the same ~1 500-character
list, so only the model and the growing context are measured.

## Data

No dataset. One instruction per run: call `corpus_search` exactly N times with
different queries, then answer.

## Metrics

Per step: wall-clock latency, time to first delta, prompt and completion
tokens (from the endpoint's usage). Per turn (primary): total latency and total
tokens, mean over three repetitions, for N = 1, 5, 15. The model may stop
early; the steps it actually took are reported, never assumed.

## Baselines

None: this is a feasibility gate, not a comparison.

## Procedure

1. Make sure `LLM_BASE_URL` / `LLM_MODEL` reach the instance model.
2. Run the entrypoint in `manifest.yaml`.
3. Decision rule (from the plan): if a 5-step turn exceeds 60 s, lower
   `tools.agent.max_steps` or choose a faster `tools.agent.model` before the
   agent is offered to people; if 15 steps overflow the window, lower
   `result_cap_tokens`.

## Amendment 1 — 2026-11-12, before attempt 2

Written before attempt 2; nothing was measured in attempt 1.

**Runtime location.** The instance model is now reached through the
`llm-tunnel` container (`http://llm-tunnel:9090/v1`, model `default-model`,
upstream Qwen 3.8 27B on vLLM, one A100 80GB), which has no port on the host.
Every run therefore executes in a one-off container of the backend image with
the repository mounted (`docker compose run --rm --no-deps -T backend uv run
--no-sync --project web/backend python …`), not with the host `uv run` of the
original entrypoint. Same code, same settings module, same model route.

**A2 — a real-question arm.** Scripted results understate a real turn (an
informal look on 2026-11-12 saw one compound demo question still running after
five minutes; that is the reason for this arm, not a measurement).

- Twelve fixed questions (`code/questions_a2.yaml`, committed before the run),
  asked in the public demo world as its PI, in the lab scope, `surface="web"`:
  four single-lookup, four few-lookup, four compound. No question names a real
  person.
- Path: `tools.agent.service.create_thread` and then `tools.agent.loop.run_turn`
  called synchronously — the function the Celery task calls — with an
  instrumented port that timestamps every model call and its first streamed
  delta. Threads are tagged `demo_visitor="EXP-2026-11-010"` so the demo's own
  24-hour cleanup removes them; demo threads never feed the learning pass.
- Per turn: wall clock to the final answer, time to the first activity line
  (first delta or first function call), model calls, function calls, prompt and
  completion tokens, whether it ended on `max_steps` or the thrash stop,
  whether the verifier's repair ran. A hard cap of 15 minutes per turn; a turn
  that hits it is recorded as a timeout, not dropped.
- Three repetitions, strictly one turn at a time, with nothing else of this
  session's using the model while A2 runs. The relay does not expose vLLM's
  load metrics, so idleness is asserted by the operator (no other job was
  scheduled) and the relay's health is logged before and after.
- Reported per group: median, worst case, and mean.
- Decision rule unchanged. No default is changed by this experiment.

## Amendment 2 — 2026-11-13 00:46, before arm A3

**A3 — several people at once.** A1 and A2 measure one turn at a time. A3
asks how a turn's time changes when several are in flight together, as when
a few lab members use Mylo at the same moment. The same twelve A2 questions,
all twelve of a repetition submitted together with 4 (run `a3c4`) and then 8
(run `a3c8`) turns in flight, three repetitions each, after every other job of
this session has finished and with no nightly running. Same per-turn
measures as A2, plus the wall clock of each repetition (how long twelve
questions take end to end). Reported per group and level beside A2's idle
run (1 in flight). The operator states the model server takes up to 128
concurrent requests; 8 turns put at most 8 model calls in flight. No
hypothesis beyond "slower per turn, faster per batch"; descriptive.

Addendum to Amendment 2 (2026-11-13 02:40, after runs `a3c4` and `a3c8`,
before the runs it describes): `a3c4`/`a3c8` ran their turns as threads in one
Python process, while the web chat runs each turn in a Celery prefork worker,
a separate process. To separate the model server's behaviour from the
harness's, A3 is repeated with **separate processes**: 4 (run `a3p4`) and then
8 (run `a3p8`) one-off backend containers started together, each asking all
twelve questions once, one at a time, starting at a different point in the
list (`--rotate k`), so 4 or 8 turns are in flight throughout. Same measures.
`a3c4`/`a3c8` are kept and reported as the thread-based variant.

## Amendment 3 — 2026-11-13 03:31, before arm A4

**A4 — the `max_steps` lever.** The results name `tools.agent.max_steps` (25)
as the lever for slow compound turns. A4 measures what a cap of 10 does to
time and tokens: the twelve A2 questions, three repetitions, one at a time on
an idle server, with `AGENT_MAX_STEPS=10` set in the harness process only
(`run_a2.py --max-steps 10 --tag a4s10`). Reported beside the idle A2 runs:
per-group time and tokens, and how many turns ended on the cap. Answer
quality is not judged here (no raters); the share of turns that hit the cap
and had to answer with what they had is the proxy, stated as such. No
default is changed.

## Amendment 5 — 2026-11-15, before arm A5 (round two, Phase 6)

**A5 — speed after the loop fixes** (plan
`docs/plans/20261115-mylo-evaluation-round-two.md`, Phase 6; correlation
`20261115-mylo-evaluation-round-two`). On the current commit (which includes
`60ae301`, the loop fixes), repeat:

- **A2 idle** — the twelve A2 questions, three repetitions, one at a time
  (`run_a2.py --reps 3 --tag a5idle`);
- **A3 with 8 processes** — eight one-off containers started together, each
  asking all twelve once with `--rotate k` (k = 0…7) (`--reps 1 --tag a5p8_k`).

Questions unchanged (`code/questions_a2.json`). No new bar: C-030's bar (a
turn of up to five tool calls under 60 s and under 30k tokens) is re-read on
these rows, reported beside the round-one rows (`a2idle`, `a2idle2`, `a3p8`,
`a3p8b`). Closes or keeps O8 ("compound questions slow under load") in
`docs/plans/20261113-mylo-evaluation-follow-ups.md`.

**Run condition.** Only when every other round-two run has stopped (A2 idle
needs an idle server; A3 p8 alone uses the night's cap of 8 requests), and no
new turn after 11:15 UTC (the nightly starts 12:00 UTC); otherwise A5 is
recorded as blocked.

**A confound stated before the run.** The relay model `default-model` that
the instance uses self-reported on 2026-11-15 as Google-trained (Gemma-style
reasoning); round one recorded it as Qwen 3.8 27B. The relay was reconfigured
in between. A5 therefore compares the loop fixes **and a different model**
against round one; the two cannot be separated here, and RESULTS.md says so
next to every comparison.

## Amendment 6 — 2026-11-16, before arm A6 (round three, Phase 3)

**A6 — speed on the model serving now** (plan
`docs/plans/20261115-mylo-evaluation-round-three.md`, Phase 3; correlation
`20261115-mylo-evaluation-round-three`). Repeats A5 exactly, through
`code/run_a6.py` (`run_a2.py` plus a recorder of each model call's finish
reason and token counts):

- **A2 idle** — the twelve A2 questions, three repetitions, one at a time
  (`run_a6.py --reps 3 --tag a6idle`);
- **A3 with 8 processes** — eight one-off containers started together, each
  asking all twelve once with `--rotate k` (k = 0…7) (`--reps 1 --tag a6p8`),
  then `code/stamp_process_arm.py a6p8 8`.

Questions unchanged. Reported as one table row per model beside the earlier
rows, never compared with them as the same model. Also reported: turns that
hit the reply cap (`tools.agent.max_output_tokens`, 4096: `finish_reason`
`length` or completion tokens at the cap) or the thinking budget
(`thinking_budget`, 512: reasoning tokens at the budget, where the server
reports them). No new bar; C-030 and O8 are re-read on these rows.

**Run condition.** Only after every other round-three run has stopped. The
plan's general limit is 4 turns in flight; A3 is defined as 8 processes, so
A6's process arm alone uses 8, within the maintainer's overnight cap of 8 in
all (2026-11-15). No new turn after 11:15 UTC. Model recorded at the start and
the end with the operator's statement.

**A confound stated before the run.** On 2026-11-16 the relay was unstable
(EXP-2026-11-021 ISSUES.md: 0.6–227 s for one tiny call, 502s). Seconds
measured while it is unstable measure the relay's connection, not the model;
the relay's health is logged before and after each run (`logs/a2_<tag>_health.json`)
and failed turns are counted, not dropped.

## Amendment 7 — 2026-11-16 20:40 UTC, before the rerun on Qwen 3.8 27B (round three)

- **The model.** The operator stated **Qwen 3.8 27B** on the relay's `default-model`. Preflight (`EXP-2026-11-021-agent-model-check/logs/preflight_qwen38.jsonl`, 20:33 UTC): endpoint healthy; self-reports Qwen, Alibaba / Tongyi Lab, and is instructed not to give a version, so the version rests on the operator's statement. Recorded at the start and end of every part, as registered.
- **The earlier counted run failed.** Amendment 6's first run (MiniCPM 4.7 35B-A3B, 2026-11-16 17:06–18:36 UTC) met a server outage and is recorded as a failed run (RESULTS.md AMENDMENTS); its files are in `outage-20261116/`. This run uses the registered file names.
- **Other load on the server.** The operator is running 8 concurrent sequences of their own against the same server for the whole run, so the server carries about 16 streams. Seconds measured here are under that load and are not compared with earlier rounds' idle seconds. Outcome classes and grades are read as registered; a server failure or timeout may be more likely, and is counted, not rerun beyond the registered single retry.
- **A6's arms keep their registered concurrency** (idle: one turn at a time; process arm: 8 containers). Because of the operator's load, A6 idle is not idle: it is one Mylo turn beside 8 other streams, and the process arm is 8 beside 8. C-030 and O8 are read as *under load*; A6 rows are not pooled with A2/A5 idle rows.
- Nothing else changes: questions, gold, graders, classes and hypotheses are as registered.

## Amendment 8 — 2026-11-16 20:50 UTC, before any run on the second server (round three)

- **The server.** The operator moved the run to a second server, the relay's `default-model-2`, which serves **Qwen 3.8 27B** (the operator: both endpoints serve Qwen 3.8 27B) and carries nothing else. Every one-off container runs with `LLM_MODEL=default-model-2`, so the instance's own model route answers from that server; the harness code is unchanged apart from the limit below, and every log records the model name `default-model-2`. Preflight 20:41–20:42 UTC: endpoint healthy, self-reports Qwen (Alibaba / Tongyi Lab) without a version, server `vllm-0.31.1rc1.dev344+g5b0b8f251-98b23dce`; 64 requests sent at once all returned 200 in 4.3–6.2 s.
- **Up to 64 in flight.** The operator said the second server takes 64 concurrent requests. The harness limit is raised to 64. No Mylo function calls the decision server (only the nightly opportunities pipeline does), so only `default-model-2` carries this load; the host's Postgres (100 connections) and CPU are shared with the live instance as before.
- **The run on `default-model` was stopped** at 20:41 UTC, three minutes into Phase 1, when the operator moved the work; it is not counted (ISSUES.md).
- **A6 on the second server, alone.** `code/drive_a6_s2.sh` runs last, after every other phase has stopped, so A6 idle is idle on the model server again (Amendment 7's load caveat no longer applies; the host is shared with the live instance as in every arm).
- **A new arm, A6x64.** Eight containers, each asking the twelve questions with `--conc 8` and a different `--rotate`: at most 64 turns in flight. Rows are stamped `conc: 64` by `stamp_process_arm.py` so the analysis measures the batch from timestamps; the real in-flight count is read from those timestamps and reported. No claim is attached; it describes how the second server behaves at the concurrency the operator named.
- Nothing else changes: questions, gold, graders, classes and hypotheses are as registered.

## Amendment 9 — 2026-11-17 05:30 UTC, before arm A7 (after the overnight fixes)

**A7 — the same questions after three fixes** (plan
`docs/plans/20261116-mylo-overnight-fixes.md`, Phase 4.3; commits `f81d2837`,
`035c9066`, `3ea9c144`, `62c9fa17`). Feed lists now filter and page, which may
cost more calls per turn; A7 says whether it does. Repeats A6 through
`code/run_a6.py`, unchanged:

- **A7 idle** — the twelve A2 questions, three repetitions, one at a time
  (`--reps 3 --tag a7idle`);
- **A7 with 8 processes** — eight one-off containers started together, each
  asking all twelve once with `--rotate k` (`--reps 1 --tag a7p8`), then
  `code/stamp_process_arm.py a7p8 8`.

`code/drive_a7.sh`; the containers mount a frozen copy of `62c9fa17`
(`tools/`, `web/backend/`). Model: the operator states **Qwen 3.8 27B** on
`default-model`, shared with the operator's own work, so "idle" is one Mylo
turn beside the operator's streams, as in Amendment 7; rows are read beside
A6's rows on the same model (`a6idle`, `a6p8` ran on the second server with
nothing else on it, so seconds are not compared — model calls and tokens per
turn are). A7 runs after `EXP-2026-11-018`'s run has stopped, so at most 8
Mylo turns are in flight. No new turn after 11:40 UTC. No new bar; C-030 and
O8 are re-read. Reported by `code/a7_table.py` (A6's table with A7's rows
beside it; written after the run, reading only the recorded files).
