# Hardware and environment

| Field | Value |
|---|---|
| CPU | Intel Xeon Silver 4114, 20 threads (the harness and the instance embedder, fastembed on CPU) |
| RAM | 62 GB |
| GPU | none used by the harness; the model is served remotely through the relay |
| Python | 3.13 (backend container) |
| Lockfile | `web/backend/uv.lock` |
| Container | one-off `backend` containers (`docker compose run --rm --no-deps`), run as the host user; `tools/` and `web/backend/` mounted read-only from a `git archive` of `b45c1211` (arm `before`) or `2cc179d9` (prepare and arm `after`); `docs/research` and a private directory outside the repository mounted writable |
| Database | `mycelium_sandbox_fsusc24` on the stack's Postgres, a `pg_dump`/`pg_restore` copy of the live database taken 2026-11-19 18:44–18:47 UTC |
| Model | relay endpoint `default-model`, `healthy` in the relay listing; self-report "I am a large language model, trained by Google" at 18:48 and 19:06 UTC; shared with live use; at most 4 requests in flight |
| Nightly | `mylo-daily.service` inactive during the run (timer next at 2026-11-20 12:04 UTC) |
| Total wall clock | copy 18:44–18:47 UTC; prepare 18:48–19:04; arm `before` 19:04:26–19:05:05; arm `after` 19:05:15–19:06:12 |

## Where the time went

Prepare (imports and reading papers into facets): 15 minutes, against 9 in
EXP-2026-11-023. Each search took under 20 s with the rerank.

## Anything about the hardware that affects the claim

None: the counts do not depend on speed. `make test-fast` ran on the same
machine during the prepare step (its own test databases, no model calls).
