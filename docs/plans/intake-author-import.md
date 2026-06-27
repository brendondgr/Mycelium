# Plan — Intake & Author-Import Buildout

**Source brief:** `~/Documents/Plans/Mycelium/2.Mycelium_Intake_Author_Import_Buildout_Plan.md`
**Branch:** `feat/intake-author-import` (merged to `main` on completion)

## Objective

Stand up the interest-profile intake for users, labs, and departments, with a
three-source author importer (Google Scholar, OpenAlex, Semantic Scholar) and an
auto-provisioning path that creates a login *and* a populated profile from a
single author ID. The importer produces a **profile draft** (aggregated
interests), never `ContentItem` rows — ingesting papers as content is the future
`scraper` app's job and is out of scope here.

## Locked decisions (from the brief's "open decisions" + this repo's patterns)

1. **Contract validator = DRF serializer.** DRF is already a dependency; Pydantic
   is not. One reusable `validate_interests()` gate is shared by API + admin.
2. **Importer home = `apps/accounts/intake/`** (profile-adjacent, decoupled from
   content ingest).
3. **External IDs = typed fields on `Profile`** (`orcid`, `openalex_id`,
   `scholar_id`), not a separate identity model.
4. **Scholar runs on-demand only** (onboarding / opt-in import), never scheduled.
5. **Resolution v1 = exact ID (ORCID / OpenAlex / Semantic / Scholar).** Name +
   institution search is a deferred fast-follow.
6. **HTTP via stdlib `urllib.request`** with an **injectable `fetch` transport**
   (mirrors `apps/grants` retrievers + the LLM client's injectable transport) so
   OpenAlex/Semantic adapters are testable offline. **`scholarly` is a lazy
   import / optional extra** so the core install stays lean and CI stays offline.
7. **OpenAlex/Semantic API keys** read from settings (`OPENALEX_API_KEY`,
   `SEMANTIC_SCHOLAR_API_KEY`) — wiring the env vars the user already staged in
   `.env.example`.
8. **Embedding hook persists canonical text now; the vector dimension stays
   unlocked** (scoring phase owns it). A pluggable embedder seam defaults to a
   no-op that leaves `embedding = NULL`.

## Scope for this session

Phases **A–F** in full, plus Phase **G backend** (REST endpoints, object-level
permissions, serializers — all unit-tested). The Next.js intake UI (chat panel /
import box / confirmation card) is **deferred** to a follow-up.

## Ordered phases (each ends green + committed)

- [x] **A. `interests` contract** — `apps/accounts/interests.py` DRF
  `InterestsContract` + `validate_interests()` gate; data migration stamps
  existing rows to `{version: 1, ...}` and coerces the seeder's string `seeking`
  → list; update seeder to emit `version` + list `seeking`. *Test:
  `test_interests_contract.py` (10).*
- [x] **B. Profile external IDs + provisioning + login export** — indexed
  `orcid`/`openalex_id`/`scholar_id` on `Profile` (migration only);
  `apps/accounts/provisioning.py::provision_from_author(identifier, source)` with
  an injectable importer; `seed_demo` gains the 3 ID columns + a `--from-authors
  FILE` mode. *Tests: `test_profile_external_ids.py` (4), `test_provision_from_author.py` (5).*
- [x] **C. Author importer** — `apps/accounts/intake/`: `drafts.py`
  (`AuthorProfileDraft`), `resolve.py`, `retrievers/{scholar,openalex,semantic}.py`,
  `normalizers/{scholar,openalex,semantic}.py`, `aggregate.py`. Scholar uses the
  verified `select_publications` (10 cited + 10 recent, deduped, ≤20). *Tests:
  `test_scholar_selection.py` (7), `test_adapter_parity.py` (6).*
- [x] **D. Lab & Dept interest surfaces** — `LabProfile` / `DeptProfile`
  one-to-one models auto-created via `post_save`; a derived-aggregate service
  (source gathering now, vector blend deferred). *Test: `test_lab_dept_profile.py` (7).*
- [x] **E. Mylo intake agent** — `apps/accounts/intake/agent.py`: bounded
  schema-filling loop (≤4 turns), structured output validated against the
  contract, deterministic form fallback (no hard model dependency). *Test:
  `test_import_to_profile.py` (6).*
- [x] **F. Embedding hook** — `apps/accounts/embedding.py`: canonical-text blob +
  pluggable embedder seam; `pre_save` wiring for Profile/LabProfile/DeptProfile
  persists `embedding_text`, leaves vector NULL. *Test: `test_embedding_hook.py` (8).*
- [x] **G. API + object-level permissions (backend)** — serializers + DRF views +
  urls for: profile read/update (own), lab/dept profile read/update (lead/admin /
  owner/admin), import-from-author, intake session, confirm-and-save. Precondition
  guards. *Tests: `test_profile_api.py` (8), `test_intake_api.py` (6), `test_intake_ordering.py` (4).*

## Outcome

All phases A–G (backend) complete, each committed on `feat/intake-author-import`.
Full suite **218 passed** on both SQLite and a fresh pgvector Postgres
(`test_mycelium`), confirming the new `VectorField` migration orders after
`core.0001_enable_pgvector`. `ruff` clean, no migration drift. The Next.js intake
UI remains deferred per the agreed scope.

## Public interfaces / artifacts that change

- New: `apps/accounts/interests.py`, `provisioning.py`, `embedding.py`,
  `intake/**`, `aggregates.py`, several accounts migrations (0005–00xx).
- Modified: `apps/accounts/models.py` (Profile fields, LabProfile, DeptProfile),
  `signals.py`, `serializers.py`, `views.py`, `urls.py`, `admin.py`,
  `management/commands/seed_demo.py`; `config/settings.py` (API-key + embedder
  settings); `.env.example`; `pyproject.toml` (optional `scrapers` extra);
  `docs/changelog.md`; `docs/goals.md` (Week 5/6 progress).

## Validation & acceptance

- Per phase: `uv run --directory web/backend python -m pytest -q` green on SQLite
  (every adapter test uses canned fixtures — **no test hits the network**),
  `ruff check` clean. Commit each phase (human-authored message, no AI trailer).
- Final: full suite + `makemigrations --check` on a **fresh Postgres
  `test_mycelium`** to prove the VectorField migrations order after
  `core.0001_enable_pgvector`. Then merge `feat/intake-author-import` → `main`.

## Test matrix (build order — each gates the next)

| # | File | Phase | Asserts |
|---|---|---|---|
| 1 | `test_interests_contract.py` | A | valid v1 accepted; unknown key / missing `areas` rejected; legacy rows wrapped to `version:1` |
| 2 | `test_profile_external_ids.py` | B | external IDs stored; blank default; indexed |
| 3 | `test_scholar_selection.py` | C | cited+recent union, deduped, ≤20, missing-year excluded |
| 4 | `test_adapter_parity.py` | C | all 3 normalizers return identical `AuthorProfileDraft` keys |
| 5 | `test_import_to_profile.py` | C+E | draft → confirm → `Profile.interests` validates |
| 6 | `test_embedding_hook.py` | F | save builds canonical text + fires (re)embed trigger |
| 7 | `test_provision_from_author.py` | B+C | provisioning creates login + populated profile + external IDs |
| 8 | `test_intake_ordering.py` | G | scoring refuses null-embedding target; import refuses unvalidated contract |

## Exclusions

- No `ContentItem` ingestion (scraper app's job).
- No vector dimension lock / real embedding model.
- No Next.js UI this session.
- No scheduled scholar scraping; on-demand only.
