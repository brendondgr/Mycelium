# Hardware and environment

| Field | Value |
|---|---|
| CPU | Intel Xeon Silver 4114 @ 2.20 GHz, 20 logical CPUs (host `sc-zeus`) — harness, database, query embeddings (ONNX, CPU) and the agent loop |
| RAM | 62 GB |
| GPU | none used locally; the model is served remotely behind the instance's `llm-tunnel` SSH relay as `default-model` |
| Python | 3.13 in the backend image |
| Lockfile | `web/backend/uv.lock` |
| Container | one-off backend containers (`docker compose run --rm --no-deps -T`), research folder mounted writable, run as the host user, `AGENT_PARALLEL_CALLS=0` |
| Total wall clock | per row, in `data/metrics.csv` (`started`, `ended`) |

## Which model, per row

Each part logs the model at its start and end (`logs/*_<tag>.jsonl`, `marker`
rows): the relay listing, the self-report, and the operator's statement.

| Tag | Operator states | Self-report | Server |
|---|---|---|---|
| `minicpm47-20261116` | MiniCPM 4.7, 35B total / 3B active (the maintainer, 2026-11-16, as a stand-in while the intended models could not be served) | "I am a model from the MiniCPM series, developed by ModelBest Inc. and the OpenBMB open-source community." (16:29 UTC, in `reasoning`, `content` null) | `vllm-0.31.1rc1.dev344+g5b0b8f251` (`system_fingerprint`); quantisation unknown |
| `qwen38-20261116` | Qwen 3.8 27B (the maintainer, 2026-11-16, after the server was fixed) | "I am Qwen, a large language model independently developed by Alibaba Group's Tongyi Lab." (20:33 UTC; its reasoning says it is instructed to give no version) | server version and quantisation unknown; the operator ran 8 other streams on it throughout |

## Anything about the hardware that affects the claim

Leak and blank counts are unaffected by load. Seconds on 2026-11-16 are
dominated by the relay's connection stalls (ISSUES.md), not by the model.
