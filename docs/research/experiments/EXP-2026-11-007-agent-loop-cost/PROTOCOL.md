# EXP-2026-11-007 — Protocol

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
