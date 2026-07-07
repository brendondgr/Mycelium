# Fellowships Integration Plan

**Objective.** Wire the ProQuest tool's Fellowships area (`/home/bdgr/Tools/ProQuest/utils/Fellowships/`,
Illinois Fellowship Finder source) into Mycelium the way Grants are wired: vendored
scraper → `ContentItem` ingest → per-user matching → API feed → portal page with a
filter sidebar. Unlike grants/conferences (semantic fuse + LLM), fellowships match by a
**deterministic eligibility rule engine** driven by a new `eligibility` block on the
user profile, captured in onboarding and editable from the profile page. The root
`pivot.py` runner scrapes grants, conferences, and fellowships **in parallel**.

## Assumptions / decisions

- Fellowship rows are `content.ContentItem` rows with the existing
  `type="fellowship"`, `source="illinois-fellowship-finder"`, `external_id=<site id>`.
  Upsert/prune key is `(source, external_id)` — ingest is generalized from the
  hard-coded `source="pivot"`.
- The eligibility block lives inside `Profile.interests["eligibility"]` (the
  interests contract already reserves an optional dict there):
  `citizenship` ("us" | "international"), `stage` ("masters" | "doctoral_early" |
  "doctoral_dissertation" | "postdoc" | ""), `fields` (subset of the five broad
  buckets: Social Sciences, Sciences/Engineering/Math, Professional Programs,
  Fine Arts, Humanities), `eligible_restrictions` (subset of ["Women", "Equity"]),
  plus the pre-existing `career_stage`. University comes from `Profile.institution`;
  Illinois affiliation is derived, not stored.
- Matching is deterministic: tier qualified/conditional/not_eligible + fit score +
  deadline status, vendored from the tool's `recommend.py`. `not_eligible` and
  closed/suspended fellowships are not persisted. `match_percent = round(fit × 100)`.
  New/pin markers reuse `content.pinning`.
- Fellowship metadata mirrors the tool's structured record: `title`, `blurb`,
  `description`, `award_class`, `deadline` (typed dict), `deadline_date` (ISO day;
  `YYYY-MM` coerced to first of month), `amount_*` (kind/currency/min/max/raw/note),
  `facets`, `flags`, `eligibility` (list), `external_url` (website), `contact_email`,
  `note`, plus the shared `prune_after`/`next_kind`/`status`/`status_summary`/
  `first_seen`/`last_seen`/`search_text`. `prune_after` is set only for
  hard (`type=="true"`) deadlines; rolling/anticipated/continuous entries persist.
- Fellowships need no Pivot SSO — scrape is public and best-effort like the others.
- Grants scraped from the fellowship site (`award_class=="grant"`) are excluded at
  ingest (the Pivot funding feed owns grants).

## Phases

1. **Worktree setup** — branch from local main, hardlink node_modules.
2. **Backend scraper + ingest** — `apps/scraper/pivot/fellowships/` vendored package
   (facet/deadline/amount parsers, Illinois adapter, best-effort scrape entry);
   `records.py`/`ingest.py`/`importer.py`/`scrape.py` learn the third area; root
   `pivot.py` adds fellowships everywhere and scrapes the three areas in parallel
   (one thread per area, each owning its own asyncio loop).
   *Validate:* parser/record unit tests against tool fixtures; `ingest_pivot` from the
   tool's real `fellowships.json` (53 records).
3. **Backend eligibility + matching + API** — interests-contract eligibility shape;
   `apps/content/fellowships.py` rule engine; `opportunities.py` fellowships branch
   (skips fuse/LLM, scores whole corpus deterministically); serializer/view/URL for
   `GET /api/content/opportunities/fellowships/`; save gate widened to fellowships;
   daily task covers the area.
   *Validate:* rule-engine tests mirroring the tool's tests; API tests; save/deadline
   round-trip test.
4. **Frontend fellowships page** — `FellowshipOpportunity` type + client/hook;
   `fellowship-filters.tsx` rail (tier, deadline, field, stage, award type,
   citizenship, saved/new toggles, sort) with pure `filterAndSortFellowships`;
   real `fellowships-section.tsx` (cards: tier badge, deadline, amount, facet chips,
   eligibility notes, save button; loading/empty/error states; top-25 cap + Show all).
5. **Frontend onboarding + profile** — "Fellowship eligibility" step in the
   onboarding flow (citizenship, stage, fields, restriction groups; optional,
   sensible defaults), saved inside `interests.eligibility`, prefetched in edit mode;
   eligibility card on the profile page; completeness includes eligibility.
6. **Integration validation** — backend pytest (host venv, throwaway pgvector if
   needed), `tsc`, `eslint`, `next build`.
7. **End-to-end** — seed the 53 scraped records, run matching for the real test user
   (whose eligibility mirrors the adjusted `profile.json` in the tool), verify the
   feed API + saved deadlines, run root `pivot.py` paths.
8. **Docs + merge** — repo-map, changelog, this plan; commits (no push); merge the
   worktree branch back into local main.

## Interfaces that change

- New API route: `GET /api/content/opportunities/fellowships/` (auth required,
  same envelope as grants). `POST /api/content/opportunities/save/` accepts
  fellowship content ids; deadlines/notifications already area-aware.
- `PATCH /api/accounts/profile/me/` now round-trips `interests.eligibility`.
- Root runner: `pivot.py scrape --area fellowships`, `pivot.py import`,
  `pivot.py all` include fellowships; scrapes run in parallel.
- Frontend: `/app/fellowships` becomes a real page; onboarding gains a step.

## Exclusions

- No LLM scoring for fellowships (deterministic engine only).
- No new fellowship sources beyond Illinois Fellowship Finder (adapter seam kept).
- Lab-level fellowship matching is out of scope (user-level only, like grants).
