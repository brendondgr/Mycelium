# EXP-2026-11-009 — Protocol

Written before the run, on 2026-11-09.

## Question

Does a stock 4B instruct model served by llama.cpp, asked the production rerank
questions through Mycelium's `[decision] backend = "port"` path (the `openai`
protocol: first-token logprobs), tell an item's own theme from a foreign one
better than d3-lite did in `EXP-2026-11-007` — and at what throughput?

## Hypothesis

Exploratory, with a stated prior: a general 4B model reading the full strand
should beat a 0.85B decision model on the off-theme control, most of all on
grants, where d3-lite matched shared words (AUC 0.538).

## Setup

- **Server:** llama.cpp `llama-server` release `b11912` (ggml-org prebuilt,
  Vulkan, `ubuntu-vulkan-x64`), on the Radeon 8060S, all layers on the GPU,
  `--parallel 8`, `--ctx-size 32768`, bound to `127.0.0.1:5180`.
- **Model:** `Qwen/Qwen3-4B-GGUF`, file `Qwen3-4B-Q4_K_M.gguf`, SHA-256
  `7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`. Thinking
  off (`chat_template_kwargs.enable_thinking = false`, sent by the client).
- **Client:** `apps.core.decisions.PortDecisionClient`, protocol detected from
  `/v1/models`. One chat completion per question, `max_tokens = 1`,
  `temperature = 0`, `top_logprobs = 20`. Questions:
  `tools.recommendation.typesafe_rerank.questions_for` — the production
  wording, unchanged.
- **Held fixed against EXP-2026-11-007:** the same 165 states (built on
  2026-11-09 by that experiment's `extract.py`, kept in a scratch file outside
  the repo because they carry profile text), same metric code.

## Data

The 120 on-theme pairs and 45 off-theme controls of `EXP-2026-11-007`. No human
judgements; the stored verdict is a system output.

## Metrics

Primary, as in EXP-2026-11-007: **ROC AUC of `P(worth = yes)`**, each theme's
top-3 items on their own theme vs the same items on a theme whose slate does not
hold them. Also, per content type; the paired win rate; the `fit` AUC; verdict
agreement with the stored verdict; saturation; determinism (5 pairs × 3).

**Paired comparison with d3-lite:** the difference in worth AUC (Qwen − d3) with
a 95 % bootstrap interval over the 45 control pairs (2,000 resamples, seed 0),
resampling each (home, control) pair as a unit so both models see the same
resample.

**Throughput:** `decision_check --calls 48 --concurrency 1/4/8` on the fixed
synthetic state, as in EXP-2026-11-008, plus the per-call latency of the main
pass on the real states (sequential).

## Baselines

d3-lite on the decide port (`EXP-2026-11-007` quality, `EXP-2026-11-008`
throughput), on identical states.

## Procedure

```bash
export UV_PROJECT_ENVIRONMENT=$HOME/.cache/mycelium-backend-venv
L=$HOME/.local/share/mycelium-decision
$L/llama.cpp-b11912/llama-b11912/llama-server -m $L/models/Qwen3-4B-Q4_K_M.gguf \
  -ngl 99 -c 32768 -np 8 --host 127.0.0.1 --port 5180 &
D=docs/research/experiments/EXP-2026-11-009-qwen3-4b-llamacpp-decisions
uv run --no-sync --project web/backend python $D/code/run.py --states $S/states.json \
  --url http://127.0.0.1:5180
M="uv run --no-sync --project web/backend python web/backend/manage.py decision_check --url http://127.0.0.1:5180"
$M --calls 2                     # warm-up, not recorded
for c in 1 4 8; do $M --calls 48 --concurrency $c --json $D/data/throughput_c$c.json; done
python3 $D/code/analyse.py
```

## What would falsify this

- The prior is refuted if the worth AUC difference's interval includes zero or
  sits below it (no measurable gain over d3-lite), or the grant AUC stays under
  0.65.
- The bar from EXP-2026-11-007 still applies: worth AUC below 0.75 means not
  ready to judge on its own.
- Any failed call, or no answer tokens in the top-20 logprobs, means the
  `openai` path is not reliable with this server.
