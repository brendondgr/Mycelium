# Manual Ignore — plan

## Objective

Give a reader a one-click way to dismiss an entry they have reviewed or simply
do not want surfaced again, across all four feed areas — **papers, grants,
fellowships, conferences**. The control sits beside the existing save
("remember") bookmark on every card. The state is **per user**, never global,
and never a signal that changes anyone else's ranking.

## Decisions and assumptions

These are judgement calls the docs do not decide; they are stated here so the
implementation does not re-litigate them.

1. **Ignoring hides, it does not delete.** The `ContentItem` and its
   `RelevanceScore` rows are untouched; the item stays in the corpus and stays
   rankable. Ignore is a per-reader display filter, reversible at any time.
2. **It follows the reader, not the surface.** An item this user ignored is
   hidden from their personal feeds *and* from lab / project feeds they read,
   because "I don't want to see this" is a fact about the reader. It does not
   affect what any other member of that lab sees.
3. **Feeds only, not search.** `/app/search` is explicit intent — if you typed
   the query, suppressing the hit is dishonest. Search results still render, with
   the ignore control showing its current state so search doubles as the way to
   find and undo one.
4. **Saves are the reader's own list, so they are exempt.** The Saves and
   Deadlines pages always show what the reader saved. Ignore and personal save
   are made **mutually exclusive** so the two can never disagree: ignoring an
   item drops its personal save, saving an item clears its ignore. Lab saves are
   untouched (they belong to the lab, not the reader).
5. **The daily report honours it.** An ignored item is excluded from that user's
   briefing and PDF report, otherwise "no longer surfaced" is false by tomorrow
   morning. It is *not* excluded from Top-25 slate computation — the slate is the
   ranking, and re-ranking it per reader-ignore would corrupt the "entered the
   slate" definition of new. It is filtered at render, so the reader's report
   simply carries one fewer item.
6. **No tier gate.** Dismissing something you were shown is a baseline
   interaction, available on every plan including Free. Nothing is read through
   `billing.entitlements`.
7. **No relevance-learning claim.** A `RelevanceEvent` with action `dismiss` is
   logged (that stream already exists and already has the action), but no plan
   here reads it back into ranking. It is a label for later, not a promise.

## Design proposal for the button

**Placement.** Last in the card's action row, immediately to the right of the
save bookmark: `[bell] [bookmark] [ignore]` on dated opportunities,
`[bookmark] [ignore]` on papers. Same `h-8 w-8` round geometry as
`SaveTrigger variant="icon"`, so the row stays on one rhythm.

**Icon.** A new `EyeOffIcon` (eye with a slash) in
`web/app/src/components/portal/icons.tsx`. An `X` reads as "close this card" and
collides with modal-close semantics; a trash can overstates it as destruction.
An eye-with-a-slash says exactly "stop showing me this".

**Tone.** The quietest control in the row, deliberately. Save is accent green,
the reminder bell is blue; ignore rests as a transparent-border button with
`--text-secondary` at ~55% opacity and lifts to full opacity when the card is
hovered or the button focused. On hover/focus it takes a `--destructive`-tinted
border and an 8% `--destructive` fill. It is always mounted and always in the tab
order — hover-only controls are unusable on touch and invisible to screen
readers.

**After the click.** The card does not silently vanish. It collapses in place to
a single-line strip — "Ignored. **Undo**" — which is the row's whole content
until the next fetch drops it. Optimistic; a failed request restores the card and
shows the error inline. Under `prefers-reduced-motion` the swap is instant with
no height animation.

**Accessibility.** `aria-label="Ignore <title>"` / `"Stop ignoring <title>"`,
`aria-pressed` reflecting state on the search surface (where the ignored item
stays visible), and the Undo strip carries `role="status"` so the change is
announced.

## Phases

Each phase ends with the named validation command and a commit.

### Phase 1 — Backend model

- Add `IgnoredItem` to `web/backend/apps/content/models.py`: `user` FK
  (CASCADE), `content` FK to `ContentItem` (CASCADE — a pruned item needs no
  ignore row), `area` mirroring `SavedOpportunity.Area`, `created_at`. Unique
  constraint on `(user, content)`; index on `(user, content)`.
- Migration in `apps/content/migrations/`.
- Register in `apps/content/admin.py` alongside the other content models.

Validation: `uv run --project web/backend python web/backend/manage.py makemigrations --check --dry-run`
and `uv run --project web/backend python web/backend/manage.py migrate`.

### Phase 2 — API

- `IgnoreItemView` in `apps/content/views.py`:
  - `POST` `{content_id}` → create the row, delete any **personal**
    `SavedOpportunity` for it, log `RelevanceEvent.Action.DISMISS`. Idempotent;
    returns `{content_id, ignored: true}`.
  - `DELETE /<content_id>` → remove the row, `204`; `404` when not ignored.
- `IgnoredItemsView` (`GET`) → the reader's ignored entries, newest first, with
  the same feed-parity `card` payload the Saves page uses, so the review surface
  reuses existing serializers.
- Routes in `apps/content/urls.py`, **both slash forms** for every path:
  `opportunities/ignore/`, `opportunities/ignore/<uuid:content_id>/`,
  `opportunities/ignored/`.
- Restrict to the four saveable types, matching `SaveOpportunityView`.
- `_save_from_item` clears any ignore row for the same `(user, content)` on a
  personal save (decision 4).

Validation: `uv run --project web/backend pytest apps/content/tests -k ignore`
(new tests: create / idempotent create / delete / 404 / cross-user isolation /
save-clears-ignore / ignore-clears-save).

### Phase 3 — Feed filtering

- One helper, `_ignored_content_ids(user)`, next to `_saved_content_ids` in
  `views.py`.
- Apply it in the shared read paths so personal, lab, and project feeds all
  inherit it from the same place: `_latest_scores` and `_accumulated_scores` take
  an optional `viewer`, and `_OpportunityFeedView`, `DailyReportView`, and
  `_recommendations_payload` pass the signed-in user. Parity is structural, not
  copied.
- `_window_counts` / `counts` are recomputed from the filtered lists so the stat
  cards never claim more than the feed shows.
- Search (`search.py` / `SearchResultSerializer`) gains an `ignored` flag but no
  filtering (decision 3).
- Briefing render (`briefing_sections.py` / `daily_report.py`) drops ignored
  items for that user at render time; slate computation in `top_feed.py` is
  untouched (decision 5).

Validation: `uv run --project web/backend pytest apps/content/tests -k "feed or briefing or recommendations"`.
Any test touching vectors needs the Compose Postgres `DATABASE_URL` (pgvector
tests skip on SQLite).

### Phase 4 — Frontend

- `EyeOffIcon` in `components/portal/icons.tsx`.
- `IgnoreButton` in `components/portal/sections/opportunity-bits.tsx`, next to
  `SaveButton`, styled per the design proposal above.
- `ignoreItem` / `unignoreItem` in `lib/portal/mutations.ts`; `useIgnoreItem` in
  `lib/portal/hooks.ts` invalidating the same key set `useSaveOpportunity`
  already invalidates, plus `ignored`.
- Types in `lib/portal/types.ts`: `ignored: boolean` on the suggestion,
  opportunity, and search-result shapes.
- Mount in all four feeds + the shared paper card:
  `suggestion-card.tsx`, `opportunities-section.tsx`, `conferences-section.tsx`,
  `fellowships-section.tsx`, and `search-result-card.tsx`.
- The collapsed "Ignored — Undo" strip lives with `IgnoreButton` so all five call
  sites behave identically.

Validation: `npm run lint` and `npm run build` from the repo root; then browser
verify via `preview_start` + DOM reads (per `docs/skills/ui-frontend.md`) on
`/app/papers`, `/app/opportunities`, `/app/conferences`, `/app/fellowships`.

### Phase 5 — Review surface

- An "Ignored" view on the Saves page: a new facet in `saves-filters.tsx` and a
  branch in `saves-section.tsx` reading `GET /api/opportunities/ignored/`,
  rendering the same cards with a single "Stop ignoring" action.
- This is the permanent, discoverable way back; the inline Undo covers only the
  moments after the click.

Validation: `npm run lint`, `npm run build`, plus a DOM-read pass on `/app/saves`.

### Phase 6 — Docs

- `docs/api-contract.md`: the three new routes and the `ignored` flag.
- `docs/repo-map.md`: rows for the ignore model/view and the `IgnoreButton`.
- `docs/changelog.md`: one entry, correlation ID `20260817-manual-ignore`.
- Delete this plan file.

## Interfaces that change

| Surface | Change |
|---|---|
| `POST /api/opportunities/ignore/` | new — `{content_id}` |
| `DELETE /api/opportunities/ignore/<content_id>/` | new |
| `GET /api/opportunities/ignored/` | new |
| Feed item payloads (papers, grants, conferences, fellowships, search) | new `ignored: boolean` |
| `POST /api/opportunities/save/` | now also clears an ignore row |

## Acceptance criteria

- The ignore control renders on every card in all four feeds and on search
  results, keyboard-reachable and labelled.
- Ignoring an item removes it from that user's papers / grants / fellowships /
  conferences feeds, from lab and project feeds *they* read, and from their next
  briefing — and from nobody else's.
- Undo (inline, or from the Saves page's Ignored view) restores it everywhere.
- Ignoring a personally-saved item removes the save; saving an ignored item
  clears the ignore. Lab saves are unaffected.
- Counts and stat cards agree with what the feeds actually show.
- Backend tests cover cross-user isolation; no endpoint leaks another user's
  ignore state.

## Explicitly excluded

- Lab-wide or project-wide ignore (a manager hiding an item for everyone).
- Feeding dismissals back into ranking or profile learning.
- Auto-expiry of ignores.
- Bulk ignore / "ignore everything from this sponsor or venue" rules.
- Any change to Top-25 slate computation or to what the collector ingests.
