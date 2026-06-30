# Daily Research Suggestions — Per-User Pipeline

**Branch:** `claude/daily-research-suggestions` (worked in-place on the main
checkout because the Docker containers bind-mount `/home/bdgr/Agents/Mycelium`;
fast-forward merged to `main` on completion; **not pushed**).
**Status:** Planned.

## 1. Objective

Stand up the daily, per-user research pipeline the product has been building
toward (goals Week 7 relevance + Week 13 digest): for **every user** in the
database, take their interest profile, **run the literature scan**, **RAG-retrieve**
the most relevant new papers, and **ask the language model** to turn those into
ranked "research article suggestions" with a plain-language reason each matters —
then surface them in the dashboard's **Daily Reports** section.

For this pass we **run it for Brendon only** (`brendondgr`, the one real user) to
prove it works end-to-end before it fans out to many accounts. The orchestrator is
written to iterate all users; a `--user` filter scopes the test.

This is a **template-to-real** step: the Daily Reports section currently shows an
honest "coming soon" empty state. After this, it renders real suggestions for the
signed-in account, and still degrades to a calm empty state when no run has
happened yet.

## 2. Locked decisions (user-confirmed + codebase patterns)

| ID | Decision |
|----|----------|
| D1 | **Full vertical slice.** Backend pipeline **plus** a read endpoint, a typed hook, and a rebuilt Daily Reports section so Brendon's real suggestions render in the app. |
| D2 | **Daily Celery Beat schedule + a `beat` compose service**, plus a manual management command and a Celery task to trigger the run now. |
| D3 | **Deterministic fallback** for the suggestion step: always rank the RAG-retrieved papers and write a templated reason; use the real LLM when reachable, mirroring `apps/accounts/intake/extract.py`. |
| D4 | **Reuse `content.RelevanceScore`** as the per-user store — no new model, no migration. One row per `(content, target_user)` (existing unique constraint → idempotent upsert). `score` = cosine similarity; `signals` carries the digest payload: `rank`, `headline`, `reason`, `source` (`llm`/`fallback`), `run_at`, and the matched query/topic. The "suggested" subset is flagged in `signals`. |
| D5 | **One embedding model for both sides.** Reuse the scraper's fastembed embedder (`BAAI/bge-small-en-v1.5`, 384-d, unit-normalized) for content **and** the profile query vector, so pgvector cosine distance is meaningful. Requires installing the `embeddings` extra in the backend/worker containers. |
| D6 | **Persist `Profile.embedding`** as a side effect of a run (compute the profile vector, save it) so a future scoring phase finds it populated; retrieval itself uses the freshly computed vector. |
| D7 | **Honest degradation everywhere.** No content / no embeddings / no LLM / no run yet each produce a clear state (logged in the command, an empty `daily-report` payload, a calm UI empty state) — never fabricated suggestions. |
| D8 | **Home is the content app.** Retrieval, suggestion generation, the per-user pipeline, the task, the command, and the read API live under `apps/content` (it already owns `ContentItem` + `RelevanceScore`). |

## 3. Grounded facts (from exploration)

- `apps/scraper/ingest.py::scan(queries, *, window=None, months_back=2, months_forward=1, sources=None, embed=True, search_fn=None, embedder=None) -> ScanSummary` upserts global `content.ContentItem(type="paper")` rows and embeds new ones with fastembed when available. `apps/scraper/tasks.py::scan_literature` wraps it; `scan_literature` management command is the CLI.
- `apps/scraper/embedding.py::get_default_embedder()` returns a batch `Callable[[list[str]], list[list[float]]]` (unit-normalized) or `None` if fastembed/numpy are missing. `build_article_text(record)` = title + abstract.
- `accounts.Profile` (`user.profile`): `interests` JSON contract (`statement`, `areas`, `keywords`, `methods`, `skills`, …), `embedding` (pgvector, currently NULL), `embedding_text`. `accounts/embedding.py::canonical_text(profile)` builds the blob; `set_embedder` installs a global single-text embedder (no-op by default).
- `accounts.WatchPreference` (`user.watch`): `topics`, `categories`, `cadence` (daily/weekly/realtime). Brendon: rich topics, categories incl. `papers`, cadence `weekly`.
- `content.RelevanceScore`: FK `content`, polymorphic target (exactly one of user/project/lab/dept), `score` float, `signals` JSON, unique `(content, target_user)`, default order `-score`.
- `apps/core/llm.py`: `build_llm_client()` → `LLMClient.complete(messages, …) -> LLMResponse(content, reasoning, finish_reason, …)`. `accounts/intake/extract.py` is the canonical LLM→JSON→fallback pattern to mirror. `llm_check` command verifies reachability.
- Celery app `config/celery.py` (`autodiscover_tasks`), Redis broker; **no Beat schedule and no beat service yet**. `compose.yaml` has `worker` but no `beat`.
- Frontend: `web/app/src/components/portal/sections/daily-reports-section.tsx` is an `EmptyState`. Portal data layer: `web/app/src/lib/portal/{client,hooks,types}.ts` (CSRF-free GET fetchers + react-query hooks). No suggestions hook/endpoint yet.
- **Current DB state:** `ContentItem=0`, `RelevanceScore=0`, fastembed **not installed**. So the test is a genuine cold run.

## 4. Public interfaces / files that change

**Backend (new):**
- `apps/content/embeddings.py` — thin shared accessor over the scraper embedder: `embed_text(str) -> list[float] | None`, `embed_texts(list[str])`. One model for both sides.
- `apps/content/retrieval.py` — `retrieve_for_vector(vector, *, type="paper", limit=N, exclude_ids=…) -> list[(ContentItem, distance)]` via `pgvector.django.CosineDistance`.
- `apps/content/suggest.py` — `generate_suggestions(profile, items, *, complete=None, fallback=…) -> list[Suggestion]` (LLM ranks/justifies; deterministic fallback ranks by similarity + templated reason). Mirrors `extract.py`.
- `apps/content/pipeline.py` — `run_for_user(user, *, months_back, sources, query_limit, top_k, suggestions, embed_profile=True) -> RunResult`: build queries → `scan` → embed profile → retrieve → upsert `RelevanceScore` → generate suggestions → write digest payload into `signals`. Returns a structured summary.
- `apps/content/tasks.py` — `@shared_task run_daily_suggestions(usernames=None, **opts)` iterating users (all, or filtered), calling `run_for_user`.
- `apps/content/management/commands/run_daily_suggestions.py` — CLI wrapper with `--user`, `--months-back`, `--source`, `--query-limit`, `--top-k`, `--no-llm`, `--async`, `--dry-run`.
- `apps/content/serializers.py`, `apps/content/views.py`, `apps/content/urls.py` — `GET /api/daily-report/` (+ no-slash variant): the signed-in user's current suggestions (joined `RelevanceScore` + `ContentItem` metadata), newest run first.
- `config/urls.py` — include `apps.content.urls`.
- `config/settings.py` — `CELERY_BEAT_SCHEDULE` (daily crontab → `run_daily_suggestions`); ensure timezone is set.
- `web/backend/pyproject.toml` is unchanged (the `embeddings` extra already exists); **container dep sync** gains `--extra embeddings`.

**Infra:**
- `compose.yaml` — `backend-deps`/`worker`/`backend` install the `embeddings` extra; add a `beat` service (`celery -A config beat`).

**Frontend:**
- `web/app/src/lib/portal/types.ts` — `DailyReport`, `Suggestion` types.
- `web/app/src/lib/portal/client.ts` + `hooks.ts` — `fetchDailyReport()` + `useDailyReport()`.
- `web/app/src/components/portal/sections/daily-reports-section.tsx` — render loading / populated / empty states; new `suggestion-card.tsx` primitive.

**Docs:** `docs/api-contract.md` (new endpoint), `docs/goals.md` (Week 7/13 progress note), `docs/changelog.md`.

## 5. Implementation phases (each ends green + a commit; no push)

- **Phase 0 — Branch + deps.** Create `claude/daily-research-suggestions`. Add `--extra embeddings` to the container dep sync; rebuild `backend-deps`; confirm `fastembed`+`numpy` import in the backend container. Commit.
- **Phase 1 — Embedding + retrieval seam.** `embeddings.py` + `retrieval.py` with unit tests (fake vectors; cosine ordering). `ruff` + targeted `pytest`. Commit.
- **Phase 2 — Suggestion generator.** `suggest.py` (LLM seam + deterministic fallback) with tests using a recording/fake `complete` and a no-model path (mirror `test_extract_llm_call.py`). Commit.
- **Phase 3 — Per-user pipeline + task + command.** `pipeline.py`, `tasks.py`, `run_daily_suggestions` command. Tests with an injected `search_fn`/fake embedder so no network is needed; assert `RelevanceScore` upsert + `signals` payload + idempotency. Commit.
- **Phase 4 — Read API.** Serializer + `DailyReportView` (auth required, own data only) + urls + `config/urls.py` include + no-slash variant. Tests: unauth 401/403, returns own suggestions, shape. Commit.
- **Phase 5 — Beat schedule + service.** `CELERY_BEAT_SCHEDULE` + `beat` compose service. Validate the schedule imports and the task is registered (`celery inspect registered` or a settings check). Commit.
- **Phase 6 — Frontend Daily Reports.** Types, client, hook, section rebuild + `suggestion-card`. `tsc` + `npx eslint src` + `next build`. Commit.
- **Phase 7 — Live test for Brendon.** Confirm LLM reachability (`llm_check`); run `run_daily_suggestions --user brendondgr` in the backend container against live sources; verify `ContentItem`/`RelevanceScore` populated and suggestions sensible; load `/app` Daily Reports in a browser as Brendon and DOM-verify real suggestions render. Capture results. Commit (docs/changelog + goals note).
- **Phase 8 — Full validation + merge.** Full backend `pytest` + `ruff` on SQLite and a fresh pgvector Postgres; migration-drift check (expect none); frontend `tsc`/eslint/build. Fast-forward merge branch → `main`. Post-merge smoke. **Do not push.**

## 6. Validation & acceptance criteria

- `run_daily_suggestions --user brendondgr` completes and reports counts (queries, scanned/new, embedded, retrieved, suggestions, llm-vs-fallback).
- `content.RelevanceScore` has rows for Brendon with `score` in [0,1] and `signals` carrying `rank`/`headline`/`reason`/`source`/`run_at`.
- `GET /api/daily-report/` returns Brendon's suggestions; unauthenticated is rejected; a second user sees none.
- Daily Reports section renders the suggestions in-browser (DOM-verified) with title, source, reason; empty state when no run.
- Pipeline degrades cleanly: no fastembed → logged, no retrieval, empty (not crash); no LLM → deterministic fallback suggestions still produced.
- All tests pass on SQLite and fresh pgvector; `ruff` clean; no migration drift; frontend `tsc`/eslint/`next build` clean.

## 7. Explicit exclusions (this pass)

- Grants/fellowships (papers only), opportunity/deadline scoring, and the other "coming soon" sections.
- Lab/department/project targets (user target only for now).
- Per-cadence gating logic beyond a daily run + a `cadence` note (weekly/real-time refinement later).
- Notifications/digests over email/Slack/Discord.
- Relevance-tuning UI, audit-log surfacing, and write actions.
- `django-celery-beat` DB scheduler (static `CELERY_BEAT_SCHEDULE` is enough now).

## 8. Orchestration

Per the user's workflow guidance: **Opus** planned this; **Haiku** ran the
repository exploration (scraper, profile, RAG/LLM, scheduling); **Sonnet** will
implement the code phases. Independent code units (retrieval, suggestion
generator, frontend data layer) can be built in parallel where they don't depend
on one another; the live test (Phase 7) is sequential and run by the lead.
