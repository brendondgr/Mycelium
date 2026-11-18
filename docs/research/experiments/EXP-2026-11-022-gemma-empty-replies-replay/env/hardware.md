# Hardware and environment

| Field | Value |
|---|---|
| CPU | Intel Xeon Silver 4114 @ 2.20 GHz, 20 logical CPUs (host `sc-zeus`) — harness, database, ONNX query embeddings, the agent loop |
| RAM | 62 GB |
| GPU | none used locally; the model is served remotely behind the instance's `llm-tunnel` SSH relay |
| Model | relay `default-model`, operator-stated Gemma 4 31B (the server the maintainer restarted with Gemma on 2026-11-17 evening). Every container's start and end record (`env/model_record.jsonl`): relay lists `default-model` `healthy`; self-report "I am a large language model, trained by Google."; `system_fingerprint` `vllm-0.21.0-5c6ca01c` — the same fingerprint as EXP-2026-11-021's preflights of 2026-11-17 (04:44 UTC on `default-model-2`, 22:04 UTC on `default-model`). The relay exposes no `max_model_len`, quantisation, chat template or parser flags (`null` in the listing). |
| Model settings | today's instance settings, read from `.env` and `mycelium.toml` as they are on 2026-11-18: `LLM_REASONING=none`, `LLM_REASONING_STYLE=thinking` (so `chat_template_kwargs.enable_thinking: false`), `LLM_TEMPERATURE=0.2`; the agent's own cap is whatever the frozen code sends (at `44100c04`: no `max_tokens`; at `55cfdb1c`: `max_tokens` 4096 and `thinking_token_budget` 512). `AGENT_PARALLEL_CALLS=0`. |
| Python | 3.13 in the backend image (`ghcr.io/astral-sh/uv:python3.13-bookworm`); `web/backend/uv.lock` unchanged between `44100c04` and `a99e1a01` |
| Container | one-off backend containers (`docker compose run --rm --no-deps -T`), `tools/` and `web/backend/` of the frozen commit mounted read-only over the checkout's, research folder mounted writable, run as the host user (`code/drive.sh`) |
| Load | per seed the two arms side by side, 3 turns in flight each: at most 6 model requests in flight from this experiment. Other load on the server: not known. `mylo-daily.service` idle throughout. |
| Total wall clock | 2026-11-18: preflight 17:10:45; Phase 1 (`f1115`) 17:10:54–17:18:40; Phase 2 (`f1117`) 17:18:51–17:27:42; Phase 3 (`f1115ns`) 17:30:00–17:38:32 UTC. Model load about 26 minutes, at most 6 requests in flight |

## Anything about the hardware that affects the claim

Whether a call is dropped could depend on how the server streams tokens
(see RESULTS.md); load and streaming chunking on 2026-11-15 are not recorded.
