# Hardware and environment

| Field | Value |
|---|---|
| CPU | Intel Xeon Silver 4114 @ 2.20 GHz, 20 logical CPUs (host `sc-zeus`) — harness, database, ONNX query embeddings, the agent loop |
| RAM | 62 GB |
| Model, instance | relay model `default-model` through the instance's `llm-tunnel` SSH relay (what Mylo uses, `LLM_MODEL`). On 2026-11-15 05:40 UTC it answered "I am a large language model, trained by Google", with Gemma-style reasoning. Round one (2026-11-12) recorded the same relay name as Qwen 3.8 27B on an A100 80GB; the relay was reconfigured in between (its `/v1/models` now lists `default-model` → upstream `default-model-2` and the reverse). True identity, size, quantisation and server are not exposed: **unknown**, recorded as "relay default-model, self-reports Google". |
| Model, second | relay model `default-model-2`, given only to the harness container (`EVAL2_LLM_MODEL`). Self-reports "trained by Alibaba Group's Tongyi Lab … Qwen"; returns a different usage schema (`cached_tokens`, `reasoning_tokens`), so a different server. Taken as a different model family on that evidence; identity otherwise unknown. |
| GPU (local) | NVIDIA Quadro RTX 5000 16 GB, serving the decision model (`pplx-decider-flash`, qwen3_5 architecture); it cannot generate text and is not used here |
| Python | 3.13 in the backend image; lockfile `web/backend/uv.lock` |
| Container | one-off backend containers (`docker compose run --rm --no-deps`), research folder mounted writable, run as the host user |
| Model settings | instance defaults for the agent (temperature 0.2, reasoning style as configured); `AGENT_PARALLEL_CALLS=0` |

## What else used the model servers

Three phases of round two ran side by side through the night (this one, and
EXP-2026-11-018/-020 and EXP-2026-11-019 by two sub-agents), under the
maintainer's cap of **8 model requests in flight across all of them**. The
maintainer also said one of the two servers might be busy with other tests.
Turn times rose from ~15 s to 40–70 s once all three phases were running;
latency is therefore not a result of this experiment. The nightly run
(`mylo-daily.timer`, 07:00 EST = 12:00 UTC) did not overlap: every counted run
stopped before 11:15 UTC (see ISSUES.md if that changes).

## Anything about the hardware that affects the claim

None for leak counts: the gate is deterministic code, and every grade is an
exact string match on rows and text. Load can only make turns slower or fail
(failed runs are counted separately).

## Model names (added 2026-11-16)

Confirmed by the maintainer on 2026-11-15: the instance model (`default-model`) in round two was Gemma 4 31B; the second model (`default-model-2`) was Qwen 3.8 27B, which was also round one's instance model. The "self-reports…" text above is left in place. Quantisation and server version of both: **unknown** — the relay does not expose them, and neither model was being served when this was written (see ISSUES.md).
