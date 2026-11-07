# Plan: bring the Labs design into the real workspace

Working document. Delete it once the last step ships, and record the result in
`docs/changelog.md`, `docs/styles.md` and `docs/repo-map.md`.

## Objective

Rebuild the authenticated workspace (`/app/*`) in the look and structure the user
chose in `/labs`: the Night Forest look, one page that scrolls through the cards,
the opened item pinned on the right, the workspace switcher back in the header,
fuller cards, search and filters on every feed, grouping by theme, a fuller
overview, settings that are easy to find, and loading placeholders.

The **source of truth for every visual decision is `/labs`**:

- `web/app/src/app/labs/labs.css` holds the styles;
- `web/app/src/components/labs/` holds the structure;
- the defaults in `schema.ts` are the user's chosen settings.

Port what is there. Don't redesign it again.

## Decisions taken from the Labs export

| Area | Chosen | Real app today |
| --- | --- | --- |
| Theme | Night Forest by default; Daylight kept as the alternative | light/dark toggle, light by default |
| Background | contour lines at 35 % strength | per-section growth (`section-ground.tsx`) |
| Density | comfortable, with compact and open as a user setting | one fixed density |
| Navigation | left rail, collapsed by default, remembered | sidebar, always open |
| Workspace switcher | header dropdown | left workspace rail (`workspace-rail.tsx`) |
| Surfaces / corners / headings / width | cards, soft corners, serif headings, wide | mixed |
| Feeds | list on the left, item opens in a sticky reader pane on the right; drawer below ~980 px | cards expand in place or open a modal |
| Feed toolbar | search, sort, filter menus in a bar, active-filter chips, grouped by theme | filter rail on grants/conferences/fellowships only, no per-feed search on all |
| Cards | Mylo's reason with his portrait inline, caveat, who it suits and why, key facts, themes. No percent, position or verdict on the card | percent and verdict shown |
| Overview | split layout: report table + today by theme / closing soon, for each person, Mylo is asking, project pulse, what Mylo found (table) | report card, found card, panels |
| Search | centred entry, no decoration (the vine goes), results grouped by kind | vine frame |
| Loading | placeholders shaped like the page, cross-fade in | spinners |
| Motion | full; off under reduced motion | mixed |

The data the new cards need already comes from the API, so no backend changes
are planned:

- `beats` and `caveat` on papers and opportunities (`lib/portal/types.ts`);
- `recommended_for` with each member's `reason` (`RecommendedMember`);
- deadlines, checks and announcements from the usability strip.

## Assumptions and open questions

1. **Hiding percent and verdict on cards changes the style guide.** It is the
   Labs rule. Step 1 writes it into `docs/styles.md` so it is a recorded
   decision, not just code. The reader pane may still show the verdict in words;
   confirm that during step 5.
2. **Settings stay on their existing routes:** `/app/account`,
   `/app/mylo-and-you`, the lab settings page and `/app/members`. They become
   findable through:
   - the account menu, which lists every settings page;
   - one shared settings navigation (the Labs "sectioned" layout) shown across
     those pages.

   No route is merged or renamed.
3. **Department scope has no research feeds** (`lib/portal/nav.ts`). It gets the
   new chrome and the overview panels it already has, nothing more.
4. **Personal, lab and project parity.** Each feed keeps one component, and the
   lab-only parts appear when the data is present. "Who it suits" and "for each
   person" are examples, since a personal feed has no `recommended_for`.
5. **Feeds load more cards as you scroll** (`use-infinite-reveal.ts`,
   `scroll-parent.ts`). With grouping by theme, the groups are rebuilt from the
   cards loaded so far, so a theme heading can gain cards as you scroll. Grouping
   happens after loading and never re-sorts the whole feed.
6. `/labs` stays as the playground until step 12, which decides whether to
   delete it.

## How every step is validated before its commit

Run both from `web/app/`:

```bash
npm run lint
```

```bash
npx tsc --noEmit
```

Then check it in the browser at `http://localhost:11050/app/...`. That is the
Compose `next dev` server: it hot-reloads, and host `next build` is blocked by
the root-owned `.next`. Check:

- desktop at 1600×1000, a tablet width and a phone width (375×812);
- Night Forest and Daylight;
- no console errors;
- keyboard focus visible and in a sensible order;
- `prefers-reduced-motion` stops every animation;
- a personal scope **and** a lab scope, plus a department scope when chrome
  changed.

Read layout with DOM reads rather than relying on screenshots alone.

Each step then:

1. Adds a `docs/changelog.md` row under correlation ID `20261107-workspace-night-forest`.
2. Updates `docs/repo-map.md` if a file moved or appeared.
3. Commits only its own files (`git commit -m … -- <paths>`), because other
   sessions share this checkout.

A step that fails any check is not committed.

## Steps

### 1. Tokens, ground and density

- Port the Labs tokens into the shared token sheet,
  `web/packages/config/src/theme.css`, as semantic tokens:
  - surface, card, glass, text, link;
  - gold, kept for deadlines and opportunities only;
  - warning, clay, theme tones.
- Night Forest becomes the default. Daylight keeps working through the existing
  `data-theme` switch (`lib/portal/theme.ts`, `components/layout/theme-script.tsx`).
- Add density variables (font size, padding, gap, header height) keyed off
  `data-density` on the workspace root, with "comfortable" as the default.
- Replace `PortalGround` (`motion/section-ground.tsx`) with the contour ground,
  ported from `components/labs/preview/ground.tsx`. It is static under reduced
  motion.
- Write the Labs rules into `docs/styles.md`:
  - Night Forest is the workspace look;
  - no percent, position or verdict on feed cards;
  - gold is reserved for deadlines;
  - Mylo is painted art only.
- **Done when:** every existing `/app` page reads correctly in both themes on the
  new tokens, with no hard-coded colours left in the files touched.
- **Commit:** "Workspace: Night Forest tokens, contour ground, density".

### 2. Header and navigation

- Add a header workspace dropdown, ported from `ScopeMenu` in `preview-app.tsx`.
  It replaces `workspace-rail.tsx` and `workspace-caption.tsx` on desktop.
  `workspace-sheet.tsx` stays as the mobile menu, and the ⌘K
  `workspace-palette.tsx` stays everywhere.
- Make `portal-sidebar.tsx` a collapsible rail: icon-only when collapsed,
  collapsed by default, with the state remembered in `localStorage`.
- Group the account menu (`user-menu.tsx`): Account, Notifications, Mylo & you,
  Lab settings, Members, the theme switch, then Sign out.
- Keep the `?ws=` URL behaviour (`lib/portal/routes.ts`) and `ScopeGuard`
  exactly as they are.
- **Done when:** switching personal, lab and department scope from the dropdown
  updates `?ws=`; the rail collapses, expands and keyboard-navigates; and phone
  width shows one header row.
- **Commit:** "Workspace: header scope dropdown, collapsible rail, account menu".
- **Pause for user feedback here.** The chrome is the most visible change.

### 3. Page loading and transitions

- Add `components/portal/skeleton.tsx`, ported from
  `components/labs/preview/skeleton.tsx`, with overview, feed (with the
  reader-pane placeholder), search, settings and a generic page.
- Replace the spinners on each section's first load with the matching
  placeholder.
- `SectionStage` cross-fades the placeholder into the content: opacity only, so
  nothing shifts.
- Keep `main` as the one scroll area. This is the "page scrolls through the
  cards" model the user asked for.
- **Done when:** a slow network (DevTools throttling) shows a placeholder shaped
  like each page, and the layout doesn't jump when content arrives.
- **Commit:** "Workspace: page-shaped loading placeholders".

### 4. Shared feed parts, before any feed switches

Build these in `components/portal/primitives/`. Nothing mounts them yet.

- **`feed-card.tsx`:**
  - signal and New pill, title, key facts;
  - Mylo's reason from `beats[0]`, with his portrait inline;
  - the caveat;
  - "Best for" from `recommended_for`;
  - theme badges (reuse `ClusterRow`);
  - the existing `CardActionBar`.
- **`item-detail.tsx`:**
  - Mylo's take, with all `beats` and the caveat;
  - best suited to, with each member's reason;
  - "Can we use this?" (reuse `usability-strip`);
  - Team fit and key dates (reuse `deadline-list`);
  - abstract, connects to, themes;
  - source and where it was announced (reuse `source-footer`).
- **`feed-toolbar.tsx`:** search, sort, filter menus in a bar, active-filter
  chips with Clear all, and a filter sheet on phones. Built from
  `components/labs/preview/pages/feed.tsx`. The existing filter logic in
  `grant-filters.tsx` and its siblings becomes the menus' contents rather than
  being rewritten.
- **`reader-layout.tsx`:**
  - list on the left, sticky pane on the right at ≥980 px, scrolling on its own;
  - a drawer below that width;
  - selection kept in the URL (`?item=`) so a link opens the same item;
  - built from the "sticky reader pane" block in `labs.css`.
- **Done when:** lint and types pass. Each part renders correctly with real data
  in a temporary mount, which is removed before the commit.
- **Commit:** "Workspace: shared feed card, item detail, toolbar, reader layout".

### 5. Papers feed

- Move `research-papers-section.tsx` onto the step-4 parts: reader layout,
  toolbar (search, sort, theme / best for / show only / found / venue) and
  grouping by theme.
- Make sure loading more cards (`use-infinite-reveal.ts`) still fires inside the
  page scroll, with the sticky pane present.
- **Done when:**
  - the page scrolls through every card;
  - the pane stays pinned and scrolls on its own;
  - loading more cards still works;
  - the same component works in personal, lab and project scope;
  - narrow widths open a drawer.
- **Commit:** "Workspace: papers on the reader layout".
- **Pause for user feedback here** before repeating the pattern three times.

### 6–8. Grants, fellowships, conferences

These are separate steps with separate commits, in this order:

- **6:** `opportunities-section.tsx`
- **7:** `fellowships-section.tsx`
- **8:** `conferences-section.tsx`

Each moves onto the same reader layout and toolbar, with its own filters:

| Feed | Filters |
| --- | --- |
| Grants | deadline, sponsor, can we apply |
| Fellowships | eligibility, stage, citizenship |
| Conferences | submissions, event date, region, ranking |

The deadline shows as both a countdown and a date. Each step removes the filter
rail it replaced and keeps `hidden-by-filters.tsx` and `held-back.tsx` working.

- **Done when:** the same checks as step 5 pass, plus existing deadline alerts,
  save and ignore with undo, and "Find collaborators" all still work.
- **Commits:**
  - "Workspace: grants on the reader layout"
  - "Workspace: fellowships on the reader layout"
  - "Workspace: conferences on the reader layout"

### 9. Overview

- Rebuild the overview (`overview-panels.tsx`, `lab-overview-section.tsx`,
  `mylo-report-card.tsx`, `mylo-found-card.tsx`) in the split layout, using
  `components/labs/preview/pages/overview.tsx` as the reference.
- **Main column:**
  - Mylo's note;
  - the report table (area, new, lead item, PDF);
  - today by theme, across every kind of item.
- **Side column:**
  - closing soon (≤30 days, every kind);
  - for each person (lab only);
  - Mylo is asking (from the ambient questions in `lib/portal/ambient/`);
  - project pulse;
  - what Mylo found (table).
- A lab keeps the Announced panel and the lab changes card.
- **Done when:**
  - personal, lab and department each show only the panels they have data for;
  - empty panels say so rather than disappearing silently;
  - an item opens in the drawer.
- **Commit:** "Workspace: overview in the split layout".

### 10. Search

- Restyle `search-section.tsx` and `global-search.tsx`: a centred entry, no frame
  decoration, results grouped by kind using the step-4 feed card, and
  suggestions under the box.
- Remove the vine from search. `leaf-vine.tsx` is deleted only if nothing else
  uses it.
- **Done when:** search returns grouped results, keyboard use works from the
  header box to the results, and phone width is usable.
- **Commit:** "Workspace: search restyled and grouped by kind".

### 11. Settings

- Add a shared settings navigation (the Labs "sectioned" layout) across
  `account-section.tsx`, `mylo-and-you-section.tsx`, `lab-settings-section.tsx`
  and `members-section.tsx`. It has two groups: You and Lab.
- Add an Appearance section for theme, density and motion, saved per user in
  `localStorage`. Saving to the server would be a separate decision.
- **Done when:**
  - every settings page can be reached from the account menu and from the
    settings navigation;
  - the role gates on lab settings are unchanged;
  - density and motion apply across the whole workspace.
- **Commit:** "Workspace: settings navigation and appearance".

### 12. Phone pass, accessibility, cleanup

- Do a full phone and tablet pass on every page.
- Do a WCAG 2.2 AA pass following `docs/skills/ada-compliance.md`: contrast in
  both themes, focus order and visibility, labelled controls, reduced motion.
- Delete the code nothing uses any more: `workspace-rail.tsx`,
  `workspace-caption.tsx`, the old filter rails, the old ground, and unused
  keyframes in `globals.css`.
- Update `docs/repo-map.md`; its workspace-switching, feed-filter-rail and
  motion rows will be wrong by then.
- Decide with the user whether `/labs` stays as a playground or is deleted.
- Delete this plan and add the closing changelog entry.
- **Commit:** "Workspace: phone and accessibility pass, remove the old chrome".

## What changes outside the frontend

- **Docs:** `docs/styles.md` (step 1), `docs/repo-map.md` (steps 2, 4, 12), and
  `docs/changelog.md` (every step).
- **No API, model, route or permission changes.** If a step finds a field
  missing, it stops and the gap goes to the user. It is not added on the fly.

## Not included

- No backend or ranking changes, and nothing in the nightly run.
- No server-side storage of appearance preferences.
- Nothing changes on the public site (`web/landing`).
- No new routes. Settings pages keep their URLs.
- The Grants "board" layout from Labs is not ported, because the user chose the
  reader layout for every feed.
