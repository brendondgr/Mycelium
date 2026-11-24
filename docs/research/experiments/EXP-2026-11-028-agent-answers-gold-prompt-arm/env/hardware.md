# Hardware and environment

| Field | Value |
|---|---|
| CPU | Intel Xeon Silver 4114 @ 2.20 GHz, 20 logical CPUs (host `sc-zeus`): harness, database, query embeddings (ONNX, CPU) and the agent loop |
| RAM | 62 GB |
| GPU | none used locally; the model is served remotely behind the instance's `llm-tunnel` relay as `default-model`. Its GPU was not stated for this run (unknown; see `ISSUES.md`) |
| Model | operator-stated Gemma 4 31B (2026-11-24); quantisation not stated for this run (unknown). Self-report "I am a large language model, trained by Google."; server `vllm-0.21.0-5c6ca01c` (2026-11-24 16:46 UTC). The driver records the relay listing and self-report at the start and end (`logs/model_s28.jsonl`) |
| Python | 3.13 in the backend image |
| Lockfile | `web/backend/uv.lock` |
| Container | one-off backend containers (`docker compose run --rm --no-deps -T`), run as the host user; `tools/` and `web/backend/` mounted read-only from a `git archive` snapshot of `a99e1a01`; `docs/research` mounted from a staged copy |
| Total wall clock | in `data/raw/run/status.txt` |

## Anything about the hardware that affects the claim

The earlier record gives Gemma 4 31B as W4A16 on one A100 80GB. That was not
restated for this run, so it is not asserted here.
