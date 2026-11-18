# Hardware and environment

| Field | Value |
|---|---|
| CPU | Intel Xeon Silver 4114, 20 threads (the harness and the instance embedder, fastembed on CPU) |
| RAM | 62 GB |
| GPU | none used by the harness; the model is served remotely through the relay |
| Python | 3.13 (backend container) |
| Lockfile | `web/backend/uv.lock` |
| Container | one-off `backend` containers (`docker compose run --rm --no-deps`), run as the host user; `tools/` and `web/backend/` mounted read-only from a `git archive` of commit `181ca3c4`; `docs/research` and a private directory outside the repository mounted writable |
| Database | `mycelium_sandbox_fsusc` on the stack's Postgres, a `pg_dump`/`pg_restore` copy of the live database taken 2026-11-18 ~17:20 UTC (2.1 GB) |
| Model | relay endpoint `default-model` (Gemma 4 31B per the maintainer; self-report at 17:27 UTC: "trained by Google"), shared with live use; at most 4 requests in flight |
| Nightly | `mylo-daily.service` inactive during the run (last run ended 14:22 UTC) |
| Total wall clock | prepare 17:27–17:36 UTC; product-arm search 17:36–17:37; slot diagnostic ~17:38; manual-arm search 17:39–17:40; export 17:41 |

## Where the time went

Reading papers into facets: 9 minutes for 618 works (448 had an abstract and were
sent to the model; a work without one is not sent). Each search took under 15 s with the rerank.
