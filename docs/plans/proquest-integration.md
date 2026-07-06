# ProQuest Integration — Grants & Conferences

**Branch:** `claude/proquest-integration` (worked in-place on the main checkout —
the Docker stack bind-mounts `/home/bdgr/Agents/Mycelium`, and Preview is pinned
to the main checkout, so a separate worktree cannot run the real stack; fast-forward
merged to `main` on completion; **not pushed**).
**Status:** Complete. Backend + frontend built and verified (404 backend tests green
on pgvector; app type-check, scoped lint, and full production build pass).

## 1. Objective

Bring the standalone **ProQuest / Pivot-RP** tool (`/home/bdgr/Tools/ProQuest`)
into Mycelium so the product surfaces **grants** and **conferences** the same way
it already surfaces papers: a daily, per-user matching run that ranks each person's
best-fit opportunities, tags brand-new high-fit items, lets users **save**
deadlines, and warns them when a deadline is under a week away.

Two areas from the tool: **Grants** (funding, from Pivot `/funding/results`) and
**Conferences** (calls for papers, from Pivot `/papers_invited`). The tool's own
recommender is **not** ported — Mycelium's `content` pipeline already implements
the identical algorithm (BM25 + BGE-ANN + RRF + multi-interest CombMNZ). We reuse
it and add only what Mycelium lacks: the Pivot **scrapers/importer**, the
grant/conference **deadline logic**, opportunity **LLM scoring**, the **save +
deadlines** system, and the **frontend** pages.

**Scope:** personal workspaces only. **Labs are out of scope** this pass.

## 2. Locked decisions (user-confirmed)

| ID | Decision |
|----|----------|
| D1 | **Decouple ingestion from matching.** The daily 1am job does per-user **matching** over the Pivot items already stored as `ContentItem`s — mirroring `scan()` (ingest) vs `run_daily_suggestions()` (match). A separate importer ingests the tool's scraped output; a Playwright refresh runs **best-effort** only when a valid saved session exists (non-fatal when not). |
| D2 | **Reuse the `content` pipeline, don't port hnswlib/langgraph.** `ContentItem` (add `CONFERENCE` type) + `RelevanceScore` (polymorphic, type-agnostic) back everything. Retrieval/lexical/fusion/ranking are reused as-is; grant/conference-specific LLM prompts run through `core/llm.py` (no langgraph). |
| D3 | **Manual runner** (user-requested): a management command **and** a root wrapper (`manual_opportunities.py`, twin of `manual_search.py`) that runs ingest → prune → match on demand. |
| D4 | **Prune expired items** (user-requested): grants past their application deadline and conferences past their event date are deleted from `ContentItem`, freeing the embedding/retrieval pool. Runs in both the manual runner and the daily job (`--no-prune` to skip). Re-embedding on refresh is acceptable. |
| D5 | **"New" survives refresh + prune.** `metadata.first_seen` is written once on first ingest and **never overwritten** on re-upsert (like the tool's SQLite `first_seen`). New/pin is computed from it, so a nightly re-scrape does not reset a user's "New" items. |
| D6 | **Saved deadlines survive pruning.** `SavedOpportunity.content` is `on_delete=SET_NULL` and carries a **display + deadline snapshot** taken at save time, so a user's Deadlines view persists even after the global item is pruned. |
| D7 | **Overview layout — left stack / right stack.** LEFT: Weekly Report from Milo, then a 1×4 button grid (Projects · Labs · Profile · Watching), then Next Actions. RIGHT: Research Papers (top 3 daily papers with percent match), Deadlines expanding below. |
| D8 | **Backend first, then frontend** (per the task and `goals.md` build-sequence: collect → score → surface). |
| D9 | **Vendor the scrapers, not the recommender.** The Pivot Playwright scrapers + normalize + deadline parsing are vendored under `apps/scraper/pivot/`. The tool's `recommend/` package is intentionally **not** vendored. |

## 3. Assumptions / open questions

- **A1 — Fellowships stay a stub.** The requirement calls fellowships "a work in
  progress (approach TBD)". Pivot has no fellowship source. The Opportunities page
  reserves a Fellowships column with an honest "coming soon" state; `Type.FELLOWSHIP`
  already exists for later.
- **A2 — "New" percentile threshold** defaults to the **80th percentile** of the
  user's ranked match scores (env `OPP_NEW_PERCENTILE`, default 80). An item is
  tagged New + pinned for one week when it is both recently first-seen (≤7 days)
  and at/above that percentile for the user.
- **A3 — Playwright in the container.** The daily job's scrape phase is best-effort
  and guarded on a valid `storage_state.json` + `PIVOT_STORAGE_STATE` env; if
  Playwright/Chromium or the session is absent it logs and falls back to matching
  the existing corpus. Chromium install (`playwright install chromium`) is a manual,
  documented step — not required for matching, tests, or the import path.
- **A4 — Embedding model.** Reuse the shared fastembed `BAAI/bge-small-en-v1.5`
  (384-d) already used by `apps.scraper.embedding` / `apps.content.embeddings`, so
  Pivot item vectors and the profile query vector share a space. The `embeddings`
  extra must be installed in the backend/worker containers (already the case for
  papers).
- **A5 — Notifications.** A lightweight computed endpoint feeds the existing
  `notification-bell.tsx`; no heavy notifications subsystem is introduced.

## 4. Grounded facts (from exploration)

**Mycelium (reused):**
- `content.ContentItem`: `type` (paper/grant/fellowship — **add conference**),
  `source`, `external_id`, `source_url`, `embedding` (pgvector), `metadata` JSON,
  `created_at`. Dedup key `(source, external_id)` partial-unique → upsert.
- `content.RelevanceScore`: FK `content`, exactly-one polymorphic target, `score`
  float, `signals` JSON, unique `(content, target_user)`, order `-score`.
- Pipeline pieces are type-agnostic: `retrieval.retrieve_for_vector(..., content_type=None)`,
  `lexical.build_bm25_index/rank_bm25_over`, `fusion.fuse_interest/combine_interests/with_floor_guarantee`,
  `ranking.rerank_by_focus`, `interests_query.search_interests`, `embeddings.embed_text(s)`,
  `suggest.generate_suggestions` (LLM `match_percent`/headline/reason + deterministic fallback),
  `pipeline.run_daily_batch` (ingest-once → recommend-per-user).
- `content.tasks.run_daily_suggestions` (Celery `apps.content.run_daily_suggestions`),
  command `run_daily_suggestions`, view `DailyReportView` → `GET /api/daily-report/`,
  `SuggestionSerializer`.
- `accounts.Profile.interests` contract already has `areas`, `keywords`, `statement`,
  `skills`, `funding_needs`, `eligibility`, `seeking`; `Profile.embedding`/`embedding_text`;
  `accounts.WatchPreference` (`topics`, `categories`, `cadence` daily/weekly).
- Beat: `config/settings.py::CELERY_BEAT_SCHEDULE` has one entry
  (`daily-research-suggestions`, `crontab(hour=CELERY_DAILY_SUGGESTIONS_HOUR default 6)`).
  `config/urls.py` includes `apps.content.urls` under `/api/`.
- Frontend: `lib/portal/{client,hooks,types,routes}.ts`; `portal-sidebar.tsx`
  (Research group: Daily Reports, Research Papers, Opportunities, Deadlines);
  sections in `components/portal/sections/`; `notification-bell.tsx` exists;
  `SuggestionCard`, `Card`, `EmptyState`, `Pill`, `SectionHeader` primitives.

**ProQuest tool (source of truth for schemas):**
- Grant record: `id, title, sponsor, amount, website, deadline, deadline_date,
  matched_topics, ai_summary, abstract, url, scraped_at` (+ `first_seen/last_seen`).
- Conference record: `id, name, location, country, event_dates, deadlines, scope,
  website, keywords, organizers, eligibility, matched_subjects, url, timeline (JSON),
  scraped_at` (+ `first_seen/last_seen`).
- `normalize.normalize_date` (word/ISO → `YYYY-MM-DD`), `conferences/deadlines.py::conference_status`,
  `recommend/schedule.py::opportunity_status/is_visible/matches_submission`.
- LLM specialists (agents.py): grants → scope-alignment + eligibility → report;
  conferences → topic/track → report; each 0–10 + rationale; report → `final_score` + summary.
- Deps already in backend `pyproject.toml`: `fastembed`(extra), `rank-bm25`,
  `openai`, `numpy`, `pgvector`. New: `playwright` (optional extra), `beautifulsoup4`.

## 5. Data model & schema changes

1. `content.ContentItem.Type` += `CONFERENCE = "conference"`. Migration `000X_conference_type`.
2. New model `content.SavedOpportunity`:
   - `id` UUID pk; `user` FK(User, CASCADE, related_name="saved_opportunities");
     `content` FK(ContentItem, **SET_NULL**, null=True, related_name="saves");
     `area` (grant/conference/fellowship); `title`, `url`, `sponsor_or_location`;
     `deadline_date` DateField null; `deadline_kind` (application/abstract/manuscript/event/other);
     `snapshot` JSON (display fields at save time); `note` TextField blank;
     `created_at`, `updated_at`.
   - Constraint: unique `(user, content)` while content non-null; plus a guard so
     a save always keeps its snapshot. Object-level: users read/write only their own.
   - Migration `000Y_saved_opportunity`.
3. Pivot item `metadata` conventions (documented in `apps/scraper/pivot/records.py`):
   grants/conferences store all tool fields verbatim under `metadata`, plus
   `first_seen` (immutable), `last_seen`, and a normalized `deadline_date`/`event_date`.

## 6. Module layout

```
web/backend/apps/scraper/pivot/            # vendored "collect" side (Playwright + parsing)
  __init__.py
  common.py         # URLs, session path, browser cfg, label/value parse helpers
  normalize.py      # normalize_date + de-dup (from tool)
  deadlines.py      # conference_status (typed submission deadlines)
  status.py         # opportunity_status / is_visible / matches_submission
  login.py          # interactive one-time SSO login → storage_state.json
  grants.py         # grants search + detail + enrich (condensed from tool)
  conferences.py    # conferences subject-walk + detail + enrich (condensed)
  records.py        # raw grant/conference dict -> normalized ContentItem upsert dict
  importer.py       # read tool JSON / SQLite -> normalized records
  ingest.py         # upsert records into content.ContentItem (+embed) + PRUNE expired
  scrape.py         # best-effort Playwright refresh guard (session present? else skip)
  management/commands/ingest_pivot.py

web/backend/apps/content/                  # "match / score / persist / serve" side
  opportunities.py      # per-user grants+conferences matching (reuses retrieval/fusion/ranking/suggest)
  opportunity_llm.py    # grant/conference specialist scoring via core/llm.py (scope/eligibility/topic)
  pinning.py            # New + percentile-pin logic (uses first_seen)
  tasks.py              # + run_daily_opportunities shared_task
  serializers.py        # + Grant/Conference/Saved/Deadline/Notification serializers
  views.py              # + Opportunities/Conferences/Save/Deadlines/Notifications views
  urls.py               # + routes
  management/commands/run_daily_opportunities.py

manual_opportunities.py                    # root wrapper (twin of manual_search.py)
```

Direction of dependency stays legal: `content` already imports `scraper`
(`run_daily_batch` calls `scraper.ingest.scan`); the Pivot deadline/status helpers
live in `scraper.pivot` and are imported by `content`.

## 7. API contract additions (all `IsAuthenticated`, personal scope)

| Route | Method | Returns |
|---|---|---|
| `/api/opportunities/grants/` | GET | latest-run ranked grants: `generated_at`, `items[]` (all grant fields + `match_percent`, `rank`, `reason`, `is_new`, `pinned_until`, `saved`, `deadline_date`, `status`) — pinned-first then by match |
| `/api/opportunities/conferences/` | GET | same shape for conferences (card fields: name, location, country, event_dates, deadlines, scope, keywords, website) |
| `/api/opportunities/save/` | POST | body `{content_id, note?}` → create `SavedOpportunity` (snapshot) → 201 |
| `/api/opportunities/save/<content_id>/` | DELETE | remove the user's save → 204 |
| `/api/deadlines/` | GET | user's saved opportunities: `items[]` with `days_remaining`, `within_week`, sorted by deadline |
| `/api/notifications/` | GET | `{count, items[]}` of "less than a week left" alerts for the bell |

`docs/api-contract.md` and `docs/repo-map.md` updated in the same change.

## 8. Ordered phases (each ends with validation + a commit)

**Phase 0 — Setup & baseline.** Branch (done). Add `playwright` (optional extra
`pivot`) + `beautifulsoup4` to backend `pyproject.toml`. Capture a baseline:
`uv run --project web/backend python manage.py makemigrations --check`,
`ruff check`, `pytest`. *Validate:* baseline green (or known-state) recorded.
*Commit:* "Add Pivot scraper deps + plan".

**Phase 1 — Data model.** Add `CONFERENCE` type; add `SavedOpportunity`; make
migrations. *Validate:* `makemigrations --check` clean after; `migrate` on SQLite
succeeds; a model test round-trips `SavedOpportunity` (SET_NULL keeps the row +
snapshot when the content is deleted). *Commit.*

**Phase 2 — Pivot ingest + prune (vendored scrapers).** Vendor
`scraper/pivot/{common,normalize,deadlines,status,records}`; write
`importer.py` (JSON + SQLite readers) and `ingest.py` (upsert + embed +
`first_seen` immutability + prune-expired). Vendor `grants.py`/`conferences.py`/`login.py`/`scrape.py`
behind lazy Playwright import. `ingest_pivot` command (`--source json|db|scrape`,
`--path`, `--area`, `--no-prune`, `--no-embed`, `--dry-run`). *Validate:* unit test
imports the real sample `data/grants_recommendations.json` source file /
`utils/ProQuest/.../output/*.json` fixtures into a test DB, asserts field mapping,
`first_seen` immutability across a second import, and that an item with a past
deadline is pruned while a future one and any newly-seen one are kept. `ruff`.
*Commit.*

**Phase 3 — Matching pipeline + New/pin + LLM.** `opportunities.py` builds the
per-user query (Profile.interests + WatchPreference.topics), retrieves grants /
conferences ContentItems (`content_type` filter), fuses/ranks (reusing
`fusion`/`ranking`), calls `suggest.generate_suggestions` for percent/headline/reason
with the grant/conference system prompts in `opportunity_llm.py`, applies
`pinning.py`, and persists `RelevanceScore` (`signals`: area, rank, match_percent,
headline, reason, is_new, pinned_until, deadline_date, status, run_at, suggested).
`run_daily_opportunities` task + command (ingest→prune→match, `--user`, `--no-llm`,
`--no-ingest`, `--no-prune`, `--dry-run`, `--async`). Beat entry `daily-opportunities`
at `crontab(hour=CELERY_DAILY_OPPORTUNITIES_HOUR default 1)`. Root
`manual_opportunities.py`. *Validate:* pipeline test with fixture user + fixture
grants/conferences (no network, `--no-llm`) asserts ranking order, that a new
high-fit item is pinned with `is_new`, that pins expire after a week, and that
persistence is idempotent (re-run overwrites, one row per (content,user)). `ruff`,
`pytest`. *Commit.*

**Phase 4 — API + serializers.** Add the six endpoints + serializers, wire
`content/urls.py`. Update `docs/api-contract.md` + `docs/repo-map.md`. *Validate:*
APIClient tests: auth required; grants/conferences return pinned-first with the
saved flag; save→deadlines round-trip; save then prune the content → deadline
still shows from snapshot; notifications lists only <7-day items. `ruff`, `pytest`.
*Commit.*

**Phase 5 — Frontend.** `types.ts`/`client.ts`/`hooks.ts` additions; `routes.ts` +
sidebar Conferences nav; rebuild `opportunities-section` (Grants rows + Fellowships
stub, percent at top, New tag, Save, links), new `conferences-section` (card grid)
+ route page, real `deadlines-section` (days-remaining, within-week highlight),
Overview redesign (D7), wire `notification-bell` to `/api/notifications/`. Honor
loading/empty/error/stale states + reduced-motion + WCAG (no color-only signals;
"New" and percent carry text/icon). *Validate:* from `web/`: `npm run -w app typecheck`,
eslint, `next build` (Preview is pinned to the main checkout per memory, so verify
via tsc/eslint/build + DOM reasoning, not screenshots). *Commit.*

**Phase 6 — Integrate & finish.** Update `docs/changelog.md` (schema per global.md).
Full backend `pytest` + `ruff`; frontend build. If any worktree were used, merge
`main` in and resolve. Fast-forward `main` (**not pushed**). *Commit* any docs.

## 9. Validation & acceptance criteria

- **Backend:** `uv run --project web/backend python manage.py makemigrations --check`
  clean; `uv run --project web/backend ruff check`; `uv run --project web/backend pytest`
  green (new tests for model/import/prune/match/pin/api). Manual: `python manage.py
  ingest_pivot --source json --path <tool output>` then `python manage.py
  run_daily_opportunities --user brendondgr --no-llm` populates `RelevanceScore`
  for grants + conferences; `manual_opportunities.py` runs end-to-end against the
  Docker stack.
- **Frontend:** typecheck + eslint + `next build` pass. Opportunities shows Grants
  (rows, percent top, New pins, Save) + Fellowships stub; Conferences shows ranked
  cards; Deadlines shows saved items with days-remaining and a <1-week highlight;
  Overview matches D7; the bell shows a count when a saved deadline is <7 days.
- **Data integrity:** expired grants/conferences are pruned from `ContentItem`;
  `first_seen` is stable across re-imports; a saved item survives pruning via snapshot.

## 10. Explicit exclusions

- **Labs / department** grant/conference matching (personal only this pass).
- **Fellowships** discovery pipeline (stub column only).
- Porting the tool's `recommend/` package, hnswlib, langgraph, or the slider HTML.
- Automating SSO/MFA — login stays a manual, human-paced step.
- Proposal-readiness checklists beyond a placeholder on the Deadlines page.
- Pushing to any remote.
