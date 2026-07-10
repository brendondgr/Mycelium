# Unified Search — Implementation Plan

## Objective

Add user-facing search over the app's content corpus (papers, grants,
fellowships, conferences) from the portal header search box and a dedicated
`/app/search` page. Search is the existing digest retrieval pipeline run
**query-first** instead of **profile-first**: reuse the pgvector ANN, the RRF
fusion idea, and the shared BGE embedder — do not build a parallel stack.

Source: `docs/plans/` (this session) + the query-first search brief. Grounded in
the current code in `web/backend/apps/content/` and the Next.js portal in
`web/app/`.

## Key finding (reshapes the source brief)

`content.ContentItem` is **already** the unified single-table surface the brief's
S2 asks for: one table, a `type` discriminator (paper/grant/fellowship/
conference), a JSONB `metadata` blob, a shared 384-dim `embedding`
(`BAAI/bge-small-en-v1.5`), and `source`/`external_id`/`created_at`. So there is
**no materialized `search_document` view to build** — lexical search is Postgres
full-text search over `ContentItem`, filtered by `type`. Retrieval
(`retrieval.retrieve_for_vector`), the shared embedder (`embeddings.embed_text`),
and RRF (`fusion.fuse_interest`) already exist for the digest.

## Locked decisions

- **S1 corpus:** search reads the shared `ContentItem` corpus directly (no
  per-user read model). Same rows the digest scores.
- **S2 surface:** the existing `ContentItem` table *is* the unified surface.
- **S3 lexical engine:** native Postgres FTS (`SearchVector`/`SearchQuery`/
  `SearchRank`, weighted title=A / body=B / aux=C) first. A BM25 extension
  (ParadeDB) is out of scope; revisit only if an eval shows it moves the needle.
- **S4 embedding:** the **same** `embeddings.embed_text` (BGE-small, 384-dim) used
  for corpus ingest — query and corpus vectors share space. Non-negotiable.
- **S5 abstention:** **off** on the search path. Search always returns top-k; a
  `confidence: "low"` flag is attached (display cue only) when the top cosine is
  below `SEARCH_LOW_CONFIDENCE_COSINE` (default 0.35). The digest path keeps its
  abstention — this is a **separate module** (`content/search.py`), the digest's
  `fusion.fuse_interest`/`pipeline` are untouched.
- **Scope of "search":** content items only (papers/grants/fellowships/
  conferences). People/projects search is a later addition (the header
  placeholder copy is updated to match).
- **Date filter:** on `created_at` (ingest time — the one reliable common
  timestamp across all four types), documented as such.
- **Pagination:** the relevance pool is bounded (default 500 candidates from the
  union of channels); pages slice within that bounded, ordered pool by an opaque
  offset cursor, so page N latency ≈ page 1. The bound is surfaced in the
  response (`pool_truncated`), never silent.
- **p95 latency target:** < 400 ms warm (small in-process corpus + one query
  embed, cached on repeat). Soft target, not a gate.

## Auth / permissions / data ownership

- `GET /api/search/` requires authentication (`IsAuthenticated`, the DRF
  default). It reads the **global** corpus (`ContentItem`), which is not
  user-scoped — the same global rows the grants/conferences feeds already expose
  post-match. No object-level lab data is read, so no per-lab authorization is
  involved. No writes, so no audit-log surface.

## Phased build (dependency-ordered; each phase is independently committable)

### Phase 1 — Lexical FTS + endpoint + facets + pagination
- Add `django.contrib.postgres` to `INSTALLED_APPS`.
- Migration `content/0004_search_vector`: `AddField` a real, nullable
  `search_vector = SearchVectorField(null=True)` (created on **all** backends so
  ORM inserts still work on SQLite), then a **Postgres-only** `RunPython` that
  creates: a GIN index on `search_vector`; a trigger function that recomputes the
  weighted tsvector from `metadata` on INSERT/UPDATE (title/name=A;
  abstract/ai_summary/search_text/description=B; authors/sponsor/venue/keywords/
  matched_subjects=C); the trigger; and a one-time backfill of existing rows.
  Reverse drops trigger/function/index. Guarded by
  `schema_editor.connection.vendor == "postgresql"` so SQLite/tests are a no-op.
- `content/search.py`: `run_search(query, *, types, sources, date_from, date_to,
  sort, limit, offset)`. Phase 1 = lexical channel only + filters + facets +
  offset pagination.
- `SearchResultSerializer` (reads a `ContentItem`, not a `RelevanceScore`):
  unified `content_id/type/title/summary/source/url/created_at` + per-type extras.
- `SearchView` → `GET /api/search/` (+ no-slash twin), `IsAuthenticated`.

### Phase 2 — Semantic + RRF fusion
- Query embedding via `embeddings.embed_text(normalized_query)`.
- pgvector cosine ANN over the same filtered candidate set (reuse
  `CosineDistance` + `retrieval._similarity`).
- A **general** `rrf_fuse(*channels, k=60)` (rank-only, normalization-before-fuse)
  local to `search.py` — the digest fusion stays untouched.
- No abstention: always return top-k; attach `confidence` flag.

### Phase 3 — Fuzzy + sort modes + cache
- `pg_trgm` extension + expression GIN index on the title; add
  `TrigramWordSimilarity` as a third RRF channel (typo tolerance).
- Sort modes: relevance (RRF), date (recency), deadline (grants/fellowships/
  conferences, nulls last).
- Redis cache (Django `CACHES`, `REDIS_URL` db 2) for the query embedding keyed
  by normalized query (skip the model call on repeats); best-effort, degrades if
  Redis is down.

### Phase 4 — Regression tests (eval harness deferred)
- Unit + API tests (see Validation). The leave-one-out citation eval harness and
  a BM25 extension are **explicitly deferred** — they are research tasks that do
  not ship user-facing search.

### Frontend
- `lib/portal/{types,client,hooks,routes}.ts`: `SearchResponse`/`SearchResultItem`
  types, `fetchSearch(params)`, `useSearch(params)`, `search` SectionKey + route.
- Route `app/app/(workspace)/search/page.tsx` → `SearchSection`.
- `components/portal/sections/search-section.tsx`: debounced (~250 ms) input
  synced to the URL (`q`, `type`, `source`, `sort`); faceted sidebar with live
  counts; per-type result cards; "load more" (cursor); empty/low-confidence
  states; loading skeletons; mobile-friendly.
- `global-search.tsx`: submit/Enter → `router.push('/app/search?q=…')`.
- Add a "Search" entry to the sidebar + mobile nav.

## Public interfaces / files that change

- **New API:** `GET /api/search/` (documented in `docs/api-contract.md`).
- **Schema:** `ContentItem.search_vector` (+ trigger, GIN, pg_trgm index).
- **Settings:** `INSTALLED_APPS += django.contrib.postgres`; `CACHES`;
  `SEARCH_*` tunables.
- **Backend:** `content/search.py`, `SearchResultSerializer`, `SearchView`,
  `content/urls.py`, `content/tests/test_search.py`.
- **Frontend:** the files listed above.
- **Docs:** `repo-map.md`, `api-contract.md`, `changelog.md`, this plan; a memory.

## Validation & acceptance

Backend (host venv + Postgres, per `backend-local-validation` memory):
- `manage.py makemigrations --check` clean after the migration; `migrate` applies
  on Postgres; `manage.py check` clean; `ruff check` clean.
- `pytest apps/content/tests/test_search.py` green (Postgres-gated DB cases; pure
  RRF cases always run). Assertions:
  - exact title query ranks that title #1; author/sponsor lexical hit returns it.
  - `type=grant` returns zero papers/fellowships; facet counts match filters.
  - concept query with no keyword overlap surfaces the item (semantic).
  - single-typo title recovers the item (fuzzy, pg_trgm).
  - fused ranking ≥ best single signal for a doubly-matched item.
  - RRF normalizes before fusing (pure unit test); search never abstains;
    the digest still abstains (its module unchanged).
  - deep page latency ≈ page 1 (bounded pool + offset within it).
  - `GET /api/search/` shape + `401/403` when anonymous.
- Full `apps/content` suite stays green (no digest regression).

Frontend (`web/`): `typecheck`, `lint`, `build` clean. Live browser verification
of the search page + header box against the running compose gateway
(`localhost:11050`) after merge to `main`.

## Explicit exclusions

- ParadeDB / true-BM25 extension; the leave-one-out eval harness.
- People/project search (content items only).
- Writing to the corpus, saving searches, or per-lab authorization (global read).
- Neo4j / graph-aware search.
