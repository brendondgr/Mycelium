# Plan — Literature-Scan Ingestion Pipeline (placeholder)

**Branch:** `feat/literature-scan-pipeline` (worktree; merged to `main` on completion)
**Status:** Complete — `apps/scraper` built (ported sources + window + embedding +
ingest orchestrator + Celery task + management command), validated (27 new tests,
266 backend tests green, ruff clean, `manage.py check` + `makemigrations --check`
clean, live OpenAlex smoke: 1017 raw → 939 unique over the 2026-04-29 → 2026-07-29
window), and committed. No migration (reuses `content.ContentItem`). Embeddings run
via the opt-in `embeddings` extra and degrade to NULL when absent.
**Reference tooling:** `~/Tools/ResearchScraper` (async OpenAlex/PubMed/Semantic Scholar
scrapers + cross-source dedup + the fastembed reranker). The user pointed at this
directory as "all you basically need" for *how to search* and *how to embed*.

## 1. Objective

Stand up a **background-triggerable** literature-scan pipeline in the planned
`apps/scraper` app. Given a list of search queries, it:

1. Searches **OpenAlex + PubMed + Semantic Scholar** concurrently over a window of
   **today − 2 months → today + 1 month** (e.g. on 2026-06-29 → 2026-04-29 → 2026-07-29).
2. Normalizes results into one shape and **de-duplicates across sources**.
3. **De-duplicates against already-stored `ContentItem` rows** so existing papers are
   not re-embedded or re-inserted.
4. **Embeds** the remaining new papers (fastembed `BAAI/bge-small-en-v1.5`, 384-dim).
5. **Upserts** them as `ContentItem(type=paper)` rows with the embedding populated —
   the RAG store for later relevance scoring / digests.

This is a **placeholder for eventual use**: it is wired to no schedule and to no
per-user profile. Queries are passed in at trigger time. It is "plug and play" —
a management command and a Celery task expose it, ready to be scheduled and to be
fed aggregated per-user interests later, once onboarding solidifies.

## 2. Decisions (from the user + grounded in code)

- **Home:** new `web/backend/apps/scraper/` — the documented planned ingestion app
  (`docs/architecture.md` §"Backend app boundaries"; `intake-author-import.md`
  defers paper→ContentItem ingest to "the future `scraper` app").
- **No new model, no migration.** Reuse `content.ContentItem` (dimension-less
  `embedding` VectorField; `(source, external_id)` partial-unique upsert key).
- **Embeddings:** fastembed `BAAI/bge-small-en-v1.5` (384-dim), added as an optional
  `embeddings` uv extra, wired through a **pluggable embedder** (lazy import). The
  dimension-less column means no schema-locking migration; the deferred-dimension
  design decision is preserved. Pipeline **degrades gracefully** (stores rows with
  `embedding=NULL` and logs a reason) when the extra is not installed, rather than
  crashing a worker.
- **Query source:** passed in at trigger time only (no built-in profile aggregation
  this pass).
- **Sources:** OpenAlex, PubMed, Semantic Scholar — ported from the reference tool
  (which is proven and includes PubMed, which the existing `accounts/intake`
  retrievers lack).
- **No Celery Beat schedule** — this is a trigger placeholder, not an active job.

## 3. Grounded facts (verified against code)

- `content.ContentItem`: `type` (paper/grant/fellowship), `source` CharField,
  `external_id` CharField, `source_url`, `embedding` `VectorField(null=True)`,
  `metadata` JSONField. Partial-unique `(source, external_id)` when `external_id != ""`.
  Index on `(source, external_id)`. (`apps/content/models.py:13-74`)
- Celery app `mongo`… `config/celery.py` → `Celery("mycelium")`,
  `autodiscover_tasks()` finds each app's `tasks.py`. Worker already runs
  (`compose.yaml` worker service).
- Settings read `.env` at repo root via django-environ; existing
  `OPENALEX_API_KEY = env("OPEN_ALEX_API_KEY")` and `SEMANTIC_SCHOLAR_API_KEY`.
  `.env` already has all three keys incl. `PUBMED_API_KEY`. `PUBMED_API_KEY` /
  `OPENALEX_MAILTO` are **not yet** read in settings → add them.
- Embedder hook pattern exists for profiles (`accounts/embedding.py`:
  `get/set_embedder`, no-op default). The scraper gets its **own** embedder factory
  (article text = title + abstract), independent of the profile embedder.
- Backend deps via `uv` in `web/backend/pyproject.toml`; optional extras already
  used (`scrapers = ["scholarly"]`). Tests: pytest-django, offline.

## 4. Components to build (all under `web/backend/apps/scraper/`)

```
apps/scraper/
  __init__.py
  apps.py                      # ScraperConfig
  window.py                    # ScanWindow.around_today(months_back=2, months_forward=1)
  sources/
    __init__.py
    base.py                    # BaseScraper, RateLimiter, ProgressCB  (ported)
    record.py                  # Record + id/title normalization + abstract rebuild (ported)
    dedup.py                   # Deduplicator (cross-source)            (ported)
    openalex.py                # OpenAlexScraper                        (ported, de-hyphenated)
    pubmed.py                  # PubMedScraper                          (ported)
    semanticscholar.py         # SemanticScholarScraper                (ported)
    registry.py                # name -> scraper class; settings-driven Config
  embedding.py                 # fastembed factory + article canonical text (pluggable)
  ingest.py                    # scan() orchestrator: search -> dedup -> db-dedup -> embed -> upsert
  tasks.py                     # @shared_task scan_literature(...)
  management/commands/scan_literature.py
  tests/
    __init__.py
    test_window.py
    test_dedup_against_db.py
    test_ingest_pipeline.py    # fake scrapers + fake embedder, fully offline
    test_command.py
```

### ContentItem mapping (per scraped paper)
- `type = "paper"`
- `source = record.primary_source` (e.g. "OpenAlex"; provenance)
- `external_id = record.canonical_id` — DOI-preferred stable key
  (`doi:…` / `pmid:…` / `pmcid:…` / `<source>:<id>`).
- `source_url = record.url`
- `metadata = {title, abstract, authors, year, publication_date, venue, doi, pmid,
  pmcid, arxiv, pdf_url, sources:[…], primary_source, query, scanned_window}`
- `embedding =` fastembed vector of `"{title}\n\n{abstract}"` (or NULL when deferred).

### DB-dedup rule
Collect `canonical_id` for every cross-source-deduped record; query
`ContentItem.objects.filter(external_id__in=ids)` once; **skip** records whose
`canonical_id` already exists (any source). This prevents re-embedding. Same-source
re-runs are additionally protected by the `(source, external_id)` unique constraint
(upsert via `update_or_create`). Known limit (documented): a paper with **no** DOI/
PMID discovered via two *different* sources in two *different* runs yields two rows —
acceptable for a placeholder.

### Trigger surfaces
- `scan_literature(queries, *, months_back=2, months_forward=1, sources=None,
  embed=True)` Celery `@shared_task` → calls `ingest.scan(...)`, returns a JSON-able
  summary (`raw, unique, already_present, new, embedded, upserted, by_source`).
- `manage.py scan_literature --query Q [--query Q …] [--months-back 2]
  [--months-forward 1] [--source openalex …] [--no-embed] [--async]`.
  `--async` dispatches the Celery task instead of running inline.

## 5. Config & dependency changes

- `config/settings.py`: add `apps.scraper` to `INSTALLED_APPS`; add
  `PUBMED_API_KEY`, `OPENALEX_MAILTO`/`SCRAPER_CONTACT_EMAIL`,
  `SCRAPER_EMBEDDING_MODEL` (default `BAAI/bge-small-en-v1.5`).
- `.env.example`: document `PUBMED_API_KEY`, `OPENALEX_MAILTO`.
- `pyproject.toml`: add `aiohttp` to core deps; add
  `embeddings = ["fastembed>=0.8.0,<1.0.0", "numpy>=2.0.0"]` extra. Container sync
  stays lean (extra opt-in: `uv sync --extra embeddings`), documented in the app.

## 6. Validation & acceptance

- **Offline test suite** (`uv run --directory web/backend python -m pytest apps/scraper`):
  - window math (2 months back / 1 forward, month rollover, leap day clamp);
  - cross-source + DB dedup (fake records, fake existing rows);
  - full `scan()` with **injected fake scrapers + fake embedder** → asserts upserted
    `ContentItem` rows, populated embeddings, `already_present` skip, idempotent re-run;
  - command parses args and calls `scan` / dispatches the task.
- **Full backend suite green** (no regressions) + **ruff** clean.
- **Optional live smoke** (network + keys; not a merge gate): a 1-query, `--no-embed`,
  small run against the real APIs to confirm the ported scrapers still parse.
- **Acceptance:** a single trigger with a query list produces deduped, embedded
  `ContentItem(type=paper)` rows; a second identical trigger inserts/embeds nothing new.

## 7. Explicit exclusions (eventual goal, not this pass)

- Relevance scoring / weighted per-person distribution, `RelevanceScore` rows.
- LLM relevance reports; top-5 per person; daily digest delivery.
- Per-user/profile query aggregation; WatchPreference wiring; scheduling (Beat).
- Grants / fellowships sources; arXiv / NIH Reporter / grants.gov.

## 8. Sequencing

1. Scaffold app + port `sources/` (base, record, dedup, 3 scrapers, registry).
2. `window.py` + tests.
3. `embedding.py` (fastembed factory, pluggable) + article text.
4. `ingest.scan()` orchestrator (search → dedup → db-dedup → embed → upsert).
5. `tasks.py` + management command.
6. Settings / `.env.example` / `pyproject.toml` wiring.
7. Tests (offline) → run suite + ruff → optional live smoke.
8. Docs: architecture note + changelog. Commit. Merge to `main`, resolve, re-validate.
</content>
</invoke>
