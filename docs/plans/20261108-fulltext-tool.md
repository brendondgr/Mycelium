# Full-text retrieval tool (`tools/fulltext`)

Revised 2026-11-08. Phases 1–2 shipped; Phases 3–5 to go.

## Objective

Build a new tool, `tools/fulltext`, that takes a paper identifier, checks
whether a legal copy can be reached, fetches it, and keeps the original
(PDF / JATS XML / HTML) plus a markdown rendering. It exposes that through its
`service` and `read` doors and a management command.

This pass builds **the tool only**: no HTTP API, no `Mount`, nothing in the web
app or Discord. An API backend comes later, inside this same tool folder and
only live when the tool is enabled; it, the app wiring, and later tools such as
the claim/citation-stance and hypothesis engines in `docs/goals.md` will all
call the doors built here.

## Decided

- **A brand-new tool inside Mycelium.** The engine is copied from
  PubMedExtraction into `tools/fulltext/engine/` and adapted. No sidecar
  service; PubMedExtraction stays as it is for its own corpus work.
- **No tier gate and no usage limits.** Every tier, no per-user caps. The
  engine's own provider protections (throttles, quota detection, switch-offs)
  stay, since they protect the instance's keys rather than limit people.
- **Keys belong to the instance, not to people.** A Mycelium instance is run
  by a lab or department, and its operator sets the publisher keys once for the
  whole site. Users never enter keys. A keyed source with no key is simply off.
- **The free sources are always on**: PubMed Central, Europe PMC, arXiv, and the
  open-access locators (Unpaywall, OpenAlex, Crossref, CORE, Semantic Scholar),
  which work without a key; a key only raises their rate limit.
- **Keyed sources are optional**: Elsevier, Springer Nature, Wiley.
- **PDF → markdown uses `pypdf`** (already a backend dependency, BSD), not
  PubMedExtraction's `pymupdf4llm` (AGPL-3.0, incompatible with Mycelium's
  Apache-2.0). The original PDF is always kept and is what a person downloads.
- **IP entitlement is accepted.** Elsevier and Wiley authorise by the IP of the
  server making the request, so they work when the instance runs on a
  subscribing network (Elsevier also needs the library to enable the full-text
  Article Retrieval API for the key, or an institutional token). The operator is
  told plainly which of the two it is (Phase 2).
- **Everything fetched is readable by every signed-in user of the instance.**
  The instance belongs to the institution whose subscription the keys carry, so
  there is one shared store, not per-person copies. Licensed fetches are still
  audited.
- **No API in this pass.** The route-prefix question is deferred to the later
  API work.

## Still open

Nothing blocks Phase 1.

## What already exists

**`/home/bdgr/Tools/PubMedExtraction`** has the whole engine, proven on 18,482
articles (36.3% full text from campus):

| Piece | File | Port? |
|---|---|---|
| Identifier parsing (PMID, PMCID, DOI, arXiv old/new, PubMed/PMC/doi.org/publisher/ScienceDirect URLs, objects with an expected `title`) | `server/identifiers.py` | yes, as-is |
| Resolver: ids verified against PubMed → arXiv API → Crossref → DataCite → doi.org; PMID/DOI/title disagreement stops with `identifier_mismatch` | `server/resolver.py` (+ helpers in `pipeline/pubmed_extract.py`) | yes |
| Routing: DOI prefix → publisher → only the owning publisher's API is spent; plain-words `explain()` with `retryable` and `next_steps` | `server/routing.py` | yes, as-is |
| Fetcher: 11 sources, per-source throttles, quota-hidden-in-a-500 detection, 25-strike entitlement switch-off, negative-answer memory, body deadline and size cap | `pipeline/fulltext.py` (`Fetcher`, `SOURCES`) | yes, with the changes in Phase 1 |
| Converters: JATS → md, Elsevier XML → md, HTML → md (5k-char floor) | `pipeline/fulltext.py` | yes |
| PDF → md | `pipeline/fulltext.py` (`pdf_to_markdown`) | rewritten on `pypdf` |
| Job folders, FastAPI service, help pages | `server/{app,jobs,help,service}.py` | no — Mycelium's API, Celery and models replace them |
| Network-free tests | `tests/test_{identifiers,routing,service,arxiv,fetch_deadline}.py` | yes |

**Mycelium** already has: `ContentItem` papers carrying `doi` / `pmid` /
`pmcid` in `metadata` (`tools/retrieval/sources/record.py`), the pasted-link
resolver (`tools/retrieval/resolver.py`), the Discord outbox, Celery for in-app
jobs, and these keys in `.env` already read by retrieval: `PUBMED_API_KEY`,
`OPEN_ALEX_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY`, `OPENALEX_MAILTO` /
`SCRAPER_CONTACT_EMAIL`.

## Phases

### Phase 1 — scaffold the tool and port the engine

- `make new-tool NAME=fulltext`; `depends_on = ("retrieval",)`, not core.
- `tools/fulltext/engine/`: `identifiers.py`, `resolver.py`, `routing.py`,
  `sources.py` (the `SOURCES` registry), `fetcher.py`, `convert.py`. No Django
  imports, so the engine is testable alone and usable from the eval harness.
- The engine keeps one instance-wide credential set, so the Fetcher's shape
  stays. Two changes, both because Mycelium runs several Celery workers rather
  than one long-lived server process:
  - **Source switch-offs** (quota exhausted, 25 entitlement refusals) go to a
    shared store (Redis key with the `disable_ttl` expiry) instead of an
    in-memory dict, so a Wiley quota stop in one worker stops all of them.
  - **Negative-answer memory** (`attempts.json`) becomes a table,
    `(article key, source) → outcome, at`, so concurrent workers do not race on
    one JSON file. Per-source throttles move to Redis for the same reason.
- `pdf_to_markdown` rewritten on `pypdf` (`extract_text` per page, then the same
  reference-section cut and minimum-length floor).
- Port the network-free tests into `tools/fulltext/tests/engine/`; add tests for
  the shared switch-off and for the `pypdf` converter on a fixture PDF.

**Validation:** `uv run --directory web/backend pytest -c pyproject.toml ../../tools/fulltext`;
`make tools-check` shows `fulltext LOADED`.

### Phase 2 — configuration and the source check

- Keys are optional secret `Setting`s in `tool.py` (`secret=True`, as retrieval
  does for `PUBMED_API_KEY`), **not** entries in `secrets`, because a missing key
  must switch that one source off, not fail the tool. Reuse the names already in
  `.env` (`PUBMED_API_KEY`, `OPEN_ALEX_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY`) and
  add `ELSEVIER_API_KEY`, `ELSEVIER_INST_TOKEN`, `SPRINGER_API_KEY`,
  `WILEY_TDM_TOKEN`, `CORE_API_KEY`, with `.env.example` comments saying where
  each comes from (lift them from PubMedExtraction's `.env.example`).
- Unpaywall needs a real contact address (it rejects placeholders with HTTP
  422): default it to `SCRAPER_CONTACT_EMAIL`.
- `ops/mycelium config` and `docs/skills/configure.md` learn to set the keys,
  so an operator sets them the way they set everything else.
- `manage.py fulltext_sources --check` makes the cheapest call each keyed
  provider offers and reports, per source, one of: `on`, `off (no key)`,
  `key rejected` (401), `key fine, not entitled from this network` (Elsevier:
  Search API 200 while `/content/article/` is 403; Wiley: 403 on a known Wiley
  DOI), `quota exhausted`. The tool's `health` check runs the cheap,
  no-network half (which keys are set) so `make tools-check` shows it.

**Validation:** settings tests (key present → source on; absent → off with the
reason; placeholder treated as absent); golden files re-recorded for the new
settings.

### Phase 3 — models, storage, jobs

Models (app label `fulltext`; FKs only into the platform and `retrieval`):

- `FulltextDocument` — `content_item` (FK, nullable for pasted ids), resolved
  `doi` / `pmid` / `pmcid` / `arxiv_id`, `title`, `source`, `licensed` (true when
  it came from Elsevier, Springer's subscription endpoint, Wiley or a Crossref
  TDM link), `original_path`, `original_kind`, `markdown_path`, `chars`,
  `sha256`, `fetched_at`.
- `FulltextRequest` — requester, item or raw identifier, `status` (the engine's
  statuses `full_text`, `abstract_only`, `invalid_identifier`, `not_found`,
  `identifier_mismatch`, `needs_identifier`, `error`, plus `queued` /
  `running`), `route` (JSON), `explanation`, `retryable`, `next_steps`,
  `document` FK.
- `SourceVerdict` — the negative-answer memory from Phase 1.

Files go under the gitignored `data/fulltext/`, named by sha256. Not MinIO:
nothing uses it.

- A Celery task (`tasks.py`) runs a `FulltextRequest` in the background, so
  the later API can enqueue and return at once.
- A request first looks for an existing `FulltextDocument` with the same
  resolved ids and returns it without touching a provider.
- Every licensed fetch writes an audit event.
- A global concurrency setting (articles fetched in parallel) keeps the tool
  polite to providers; it is not a per-person limit.
- Events: `fulltext.retrieved(document, content_item)`.

**Validation:** model and task tests with the engine's HTTP layer stubbed (no
network); cache-hit test (second request for the same DOI makes no provider
call); audit event on a licensed fetch.

### Phase 4 — doors, command, and a coverage measurement

The doors are the tool's whole interface in this pass:

- `service.check(ids)` — resolve + route, **fetch nothing**: "open access via
  arXiv", "via Wiley (instance key)", "Elsevier: not available on this
  instance", "no legal copy known". An Unpaywall lookup makes "open" real, not
  guessed.
- `service.request(ids, *, requester=None, background=False) -> FulltextRequest`
  — fetch now, or enqueue the Celery task.
- `service.retry(request)` — re-run transient failures (quota, 5xx).
- `service.sources()` — which sources are live on this instance and, for the off
  ones, why.
- `read.full_text(item) -> str | None`, `read.document(item)` (paths to the
  original and the markdown) and `read.availability(item)`.
- `manage.py fulltext_get <id> [<id> …] [--check-only]` — the same path from the
  shell, printing status, source, explanation and file paths. This is how the
  tool is exercised before anything else uses it.
- Experiment (mandatory record): `make new-experiment SLUG=fulltext-coverage`
  — sample N papers from the live corpus, run `check` and the fetch, and report
  coverage by source and by year from this host, once with free sources only and
  once with the keyed ones. Metrics go in `manifest.yaml` / `RESULTS.md`.
  `make validate-research`.
- Optional later stage, not in this plan: prefetch open-access full text for
  each target's Top-25 papers nightly, for the stance and hypothesis engines.

**Validation:** door tests; one live `fulltext_get` per free source (a PMC id,
an arXiv id, an open-access DOI) recorded in the experiment.

### Phase 5 — docs

`tools/fulltext/README.md` (doors, settings, sources, the IP-entitlement
explanation), `tools/README.md` installed-tools table, `docs/repo-map.md`,
`docs/configuration.md`, `.env.example`,
`docs/changelog.md`; delete this plan.

## `[tools.fulltext]` settings (proposed)

`sources` (order), `contact_email` (defaults to `SCRAPER_CONTACT_EMAIL`),
`min_chars`, `max_bytes`, `concurrency`, `disable_ttl_hours`. Keys as optional
secret settings (Phase 2).

## Explicitly out of scope

- An HTTP API. Built later inside this tool (its `urls.py` / `views.py` and a
  `Mount`), live only when the tool is enabled, calling the doors above.
- Wiring into the app: paper cards, saves, the reader pane, an operator status
  panel, Discord delivery, `/mylo paper`. A follow-up once the tool works.
- Tier gates and per-user limits.
- Per-user or per-lab keys. One instance, one key set.
- Any non-legal source (shadow libraries, scraping behind paywalls).
- Bulk corpus download — this is per request, plus the optional later
  open-access prefetch.
- Proxying a library login (EZproxy / OpenAthens / Shibboleth) to reach
  IP-gated content off campus. A separate design if ever wanted.
- Chat-with-your-PDF (`docs/goals.md` rules it out).
