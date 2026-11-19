# Hardware and environment

| Field | Value |
|---|---|
| CPU | Intel Xeon Silver 4114, 20 threads (the harness and the instance embedder, fastembed on CPU) |
| RAM | 62 GB |
| GPU | none used by the harness; the model is served remotely through the relay |
| Python | 3.13 (backend container) |
| Lockfile | `web/backend/uv.lock` |
| Container | one-off `backend` containers (`docker compose run --rm --no-deps`), run as the host user; `tools/` and `web/backend/` mounted read-only from a `git archive` of `2cc179d9` (arm `prev`) or `77166b9e` (arm `multi`); `docs/research` and a private directory outside the repository mounted writable |
| Database | `mycelium_sandbox_fsusc24`, EXP-2026-11-024's copy as prepared there |
| Model | relay endpoint `default-model`; self-report "I am a large language model, trained by Google" at 19:13 and 19:15 UTC; shared with live use; at most 4 requests in flight |
| Nightly | `mylo-daily.service` inactive during the run |
| Total wall clock | identity 19:13:11; arm `prev` 19:13:18–19:13:58 UTC; arm `multi` 19:14:09–19:15:00; identity 19:15:05 |

## Where the time went

Each search took under 20 s with the rerank; nothing was imported.

## Anything about the hardware that affects the claim

None: the counts do not depend on speed.
