# Onboarding — Animated Research Radar & Source Import

**Branch:** `claude/loving-diffie-7d7888` (merged to `main` on completion; no push)
**Status:** In progress

## 1. Objective

Rework the post-signup `/app/onboarding` flow ("research radar") so it both *feels*
like Mycelium and *works* harder. Two threads:

1. **Mycelium-branch motion.** Step transitions grow a branch to the right: the
   current step slides left, a new branch segment draws in, and the next step
   arrives from the right. The upcoming step stays partially visible off to the
   side while the user fills in the current one.
2. **Source-driven research extraction.** Replace the manual "tell us about your
   research" steps with an importer that builds a research profile from **one** of
   OpenAlex / Semantic Scholar / Google Scholar (top ~10 most-cited + ~10 most-recent
   works) **and/or** an uploaded résumé/CV (PDF or text). The result is a natural-
   language statement + areas/keywords/methods the user can refine, then a
   "what should Milo keep an eye on" step seeded from those interests plus manual
   additions.

The backend three-source importer, interests contract, bounded Mylo intake agent,
and `import/session/confirm` endpoints **already exist and are tested** — the
frontend never calls them. This work wires them in, adds résumé parsing + natural-
language synthesis + a durable watch model, and rebuilds the onboarding UI.

## 2. Locked decisions (from user + codebase patterns)

| ID | Decision |
|----|----------|
| D1 | **Watch persistence = new `WatchPreference` model** (topics, categories, cadence) with own-only REST endpoints, migration, serializer, admin, tests. Home: `apps/accounts` (profile-adjacent; may move to a future `reports` app). |
| D2 | **Résumé = parse-and-discard.** Extract text server-side, derive interests, drop the file. No object storage, no profile file field. |
| D3 | **LLM-optional with deterministic fallback.** Résumé extraction and the natural-language statement use `apps/core/llm.py` when configured, else a deterministic heuristic — so dev/CI run fully offline. Mirrors the existing intake-agent `extractor` seam. |
| D4 | **At most one of the three sites** per import; résumé is independent/additive. Enforced by a single `source` field server-side and single-select UI client-side. At least one source (site or résumé) required to synthesize. |
| D5 | **Import-first, manual-refine.** The synthesized draft pre-fills an editable review step; users can still add/remove areas/keywords/methods by hand. A "skip / enter manually" path remains for users with no profile. |
| D6 | **PDF text via `pypdf`** (pure-Python, lightweight) added as a core backend dependency. `scholarly` stays the optional `scrapers` extra. |
| D7 | The unpersisted "goals" and standalone "alerts & cadence" scaffold steps are **replaced** by Import → Review → Watch. Cadence now lives on `WatchPreference`. |
| D8 | Commits are **human-authored, no AI attribution / co-author trailers** (per `docs/skills/global.md`, which overrides the harness default). Per-phase commits, no push until the final merge. |

## 3. Grounded facts (verified by exploration)

- Importer: `apps/accounts/intake/importer.py::import_author(identifier, source)` → `AuthorProfileDraft`; sources `openalex|semantic|scholar` (+ `orcid`→openalex). Scholar selects 10 cited + 10 recent (≤20, deduped); optional `scholarly`.
- `AuthorProfileDraft.to_interests(statement="")` → contract dict; `aggregate()` dedupes/caps.
- Contract: `apps/accounts/interests.py::validate_interests()`; `areas` required, plus statement/methods/keywords/skills/funding_needs/eligibility/seeking/exclusions/sources; **unknown keys rejected**.
- Endpoints (DRF, `apps/accounts/urls.py` + `views.py`): `POST /api/auth/intake/{import,session,confirm}/`; `MyProfileView` at `/api/auth/profile/me/` (RetrieveUpdate, own).
- `Profile` (accounts/models.py): `academic_title`, `institution`, `orcid`, `openalex_id`, `scholar_id`, `interests` (JSON), `embedding` (VectorField, nullable), `embedding_text`, `is_verified`. Embedding hook persists canonical text on save.
- LLM: `apps/core/llm.py::LLMClient.complete(messages, ...)`; OpenAI-compatible/vLLM; lazy `openai` import; settings `LLM_*`. Not currently used by intake.
- Frontend: `web/app/src/components/onboarding/onboarding-flow.tsx` (state machine: verify → 5 intake steps → building → `/app`) only calls `saveOnboarding` (`PATCH /profile/me/`). `framer-motion` v12 installed, unused. Tokens in `web/packages/config/src/theme.css`; fonts Geist/Fraunces/Inter. No file upload anywhere.
- Validation commands (host venv per `backend-local-validation` memory):
  - `export UV_PROJECT_ENVIRONMENT=/home/bdgr/.cache/mycelium-backend-venv`
  - tests: `DATABASE_URL="sqlite:////<abs>/test.db" uv run --directory web/backend python -m pytest -q`
  - lint: `uv run --project web/backend ruff check web/backend`
  - migration check: `uv run --project web/backend python web/backend/manage.py makemigrations --check`
  - fresh-pg check: throwaway `pgvector/pgvector:pg17` on `:5433`.
  - frontend: `npm run lint`; `npm --workspace @mycelium/app run build`.

## 4. Public interfaces that change

- **New** `POST /api/auth/intake/synthesize/` (multipart): optional `source`+`identifier`, optional `resume` file → `{ draft, interests }` (site + résumé merged, natural-language `statement` filled). Enforces D4.
- **New** `GET/PUT /api/auth/watch/me/` → `WatchPreference` (own only).
- Enhanced: imports now return a populated `interests.statement`.
- New backend modules: `intake/statement.py`, `intake/resume.py`, `intake/merge.py`; `WatchPreference` model + migration; serializer/view/admin/url wiring.
- New frontend: `mycelium-branch.tsx`, `onboarding-stage.tsx`, rewritten `onboarding-flow.tsx`, new `auth-client`/`auth-types` functions/types.
- Docs: `api-contract.md`, `changelog.md`, `goals.md`, this plan.

## 5. Phased plan (each phase: implement → validate → commit; no push)

- **Phase 0 — Baseline.** Set up host venv; run backend suite + app lint/build to confirm green start. No commit.
- **Phase 1 — Statement synthesis** (`intake/statement.py`). LLM-optional `draft_statement(draft, *, complete=None)` + deterministic template fallback; wire into import path. Tests. Validate (pytest+ruff). Commit.
- **Phase 2 — Résumé parsing** (`intake/resume.py` + `pypdf`). Text extraction (pdf/text) with size/type guards; `draft_from_resume(text, *, complete=None)` LLM-optional + heuristic fallback. Fixture-based offline tests. Validate. Commit.
- **Phase 3 — Merge + synthesize endpoint.** `intake/merge.py::merge_drafts`; `SynthesizeView` (`/intake/synthesize/`), urls, serializer. Tests (site-only, résumé-only, both, none→400, bad source→400, oversize/bad-type→400). api-contract. Validate (pytest+ruff+makemigrations --check). Commit.
- **Phase 4 — WatchPreference + API.** Model + migration (orders after latest accounts migration), serializer, `MyWatchView` (own, get_or_create), urls, admin. Tests. api-contract. Validate incl. fresh-pg migrate. Commit.
- **Phase 5 — Frontend API client + types.** `synthesizeProfile`, `confirmInterests`, `getWatch`/`saveWatch`; `auth-types` additions. Validate (lint+build). Commit (or fold into Phase 7).
- **Phase 6 — Branch-motion primitives.** `mycelium-branch.tsx` (framer-motion `pathLength` grow) + `onboarding-stage.tsx` (slide: prev exits left, active centered, next peeks right; reduced-motion aware). Validate (lint+build). Commit. *(Independent files — may run in parallel with backend.)*
- **Phase 7 — Onboarding flow rebuild.** Rewrite `onboarding-flow.tsx`: verify(skippable) → About you → Import (source cards + identifier + résumé dropzone, single-site) → Review (editable statement/areas/keywords/methods) → Watch (seeded topics + categories + cadence) → Building. Wire synthesize/confirm/watch. Loading/empty/error/permission/reduced-motion/keyboard/mobile states. Validate (lint+build; Preview walkthrough if feasible). Commit.
- **Phase 8 — Docs + full validation.** changelog (schema), goals (Week 6 note), api-contract finalize, this plan status. Full backend suite + app lint + build. Commit.
- **Phase 9 — Merge to main.** Merge `claude/loving-diffie-7d7888` → `main`, resolve conflicts, re-validate. No push.

## 6. Validation & acceptance

- Per phase: targeted tests green, `ruff` clean, `makemigrations --check` clean; frontend phases lint + build (typecheck) clean. Commit per phase (human-authored, no AI trailer).
- Final: full backend suite green on SQLite **and** a fresh pgvector Postgres; app lint + build clean; branch merged to `main` still green.
- Acceptance:
  - User can pick exactly one site and/or upload a résumé, get a natural-language draft, edit it, and save contract-valid `interests` (no unknown keys).
  - `synthesize/` enforces ≤1 site and ≥1 source; rejects oversize/bad-type files and bad sources with 4xx.
  - `watch/me/` persists topics/categories/cadence for the caller only.
  - Onboarding animates step transitions with a growing branch and a side-visible next step; honors `prefers-reduced-motion`; keyboard- and mobile-usable.

## 7. Exclusions

Real SMTP/token email verification; OAuth; storing résumé files; `ContentItem`
ingestion (scraper app's job); a real embedding model / vector dimension lock;
scheduled scholar scraping; name+institution author resolution (exact IDs only);
multi-site import in one pass.

## 8. Orchestration

Per the session request: Opus (this agent) plans, validates each gate, and
commits; Haiku sub-agents did repository search; Sonnet sub-agents implement
self-contained phases. Backend phases run sequentially (shared `views.py`/`urls.py`).
The branch-motion primitives (Phase 6, isolated new files) may run in parallel
with backend work. Phase 7 integrates after Phases 5+6 and the backend endpoints.
