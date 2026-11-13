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

## Amendment 3 — 2026-11-13 03:38, before arm A4

**A4 — the `max_steps` lever.** The results name `tools.agent.max_steps` (25)
as the lever for slow compound turns. A4 measures what a cap of 10 does to
time and tokens: the twelve A2 questions, three repetitions, one at a time on
an idle server, with `AGENT_MAX_STEPS=10` set in the harness process only
(`run_a2.py --max-steps 10 --tag a4s10`). Reported beside the idle A2 runs:
per-group time and tokens, and how many turns ended on the cap. Answer
quality is not judged here (no raters); the share of turns that hit the cap
and had to answer with what they had is the proxy, stated as such. No
default is changed.
