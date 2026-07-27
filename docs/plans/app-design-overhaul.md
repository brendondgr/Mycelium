# App Design Overhaul — bringing the public site's language into the workspace

**Status:** in progress · **Correlation ID:** `20260727-app-design-overhaul`

## Objective

Carry the design work just landed on the public site (`web/landing/`) into the
authenticated workspace (`web/app/`), replace the placeholder mascot art with
the real Mylo portrait, adopt the circular percent-match indicator as the single
way fit is shown, and declutter the Research Papers filter rail. Then reflect
the finalized card structure back onto the public site so the marketing preview
and the real product agree.

Terminology note: "back end" in the request means the **authenticated Next.js
app** (`web/app/`), not the Django API. No Django/DRF changes are planned; the
API payloads already carry everything the UI needs (`match_percent`,
`embedding_match`, `origin`, `cluster`, `bridge_clusters`, `per_interest`).

## Assumptions

- `web/art/Mylo/MyloHeadshot.png` is the canonical Mylo portrait and is the
  intended replacement for the hand-drawn `MyloMark` SVG.
- The app's existing card anatomy (badge row → title → meta → body → reason →
  link) is sound and stays. Only the percent indicator moves.
- Sections whose backing pipeline does not exist yet (Reports, cross-lab
  browsing) stay honest "coming soon" states — see Exclusions.

## Open questions (assumed, not blocking)

- **Ring placement.** The request says the circular indicator "on the left side"
  is good but its "structure and placement" should follow the app's existing
  layout. Assumption: a **left gutter column** on each feed card holding the
  ring, with the card's existing content stack unchanged to its right. This is
  the front page's left-hand emphasis without importing the front page's card
  anatomy.
- **Losing interest-chip focus scoring.** Removing the sub-parameter chip tier
  from Research Papers necessarily removes the chip-driven re-scoring
  (`focusPercent`, `focusMode`, `displayPercent`) that only those chips could
  trigger. Assumption: that is intended — cards then always show their real
  match percent, which is also what makes the new ring trustworthy.

---

## Phase 1 — Real Mylo art everywhere

**Problem.** `web/app/src/components/brand/mylo-mark.tsx` is a hand-drawn inline
SVG mushroom (circles and paths, fixed hex palette). It renders on the login
page, the signup page, and at four points in onboarding. `app/public/mylo-headshot.webp`
is a 3.8 kB derivative of unknown provenance, hand-copied rather than generated.

**Steps.**
1. Rename `web/scripts/sync-landing-assets.mjs` → `sync-art-assets.mjs` and give
   it a second target so it emits app derivatives from the same `web/art/`
   masters. Update the `predev`/`prebuild` hooks in `web/landing/package.json`
   and add them to `web/app/package.json`.
2. Emit `mylo-portrait-{64,128,256,512}.webp` into `web/app/public/images/`.
3. Rewrite `MyloMark` to render the real portrait, keeping its
   `className`-sizes-the-wrapper API so call sites keep working. Drop the
   `aria-hidden` blanket and let callers pass a label where it carries meaning.
4. Audit all 9 call sites for the aspect change (old mark was 100×112, the
   portrait is square).
5. Point the existing `/mylo-headshot.webp` references (`opportunity-bits.tsx`
   ×2, `suggestion-card.tsx`, `lab-onboarding.tsx`) at the generated asset.

**Validation.** `web/app` typechecks and builds; login, signup, and the
onboarding flow render the portrait at every size; no request 404s in the
browser network log; generated files are git-ignored like the landing ones.

---

## Phase 2 — `MatchRing`, the single percent-match element

**Problem.** Fit is currently a pill (`MatchBadge` in `opportunity-bits.tsx`):
a dot, a bold number, and the word "match". Fellowships show the percent as a
tiny uppercase suffix on the eligibility badge instead. Search results show no
percent at all. Three different treatments for one idea.

**Steps.**
1. New primitive `components/portal/primitives/match-ring.tsx` — a
   conic-gradient donut with the percent inside, `size` variants (`sm` for
   dense panels, `md` for feed cards), the tier color (strong ≥ 85 / fair 60–84
   / low < 60) on the arc, and the tier word plus "match" beneath. Number and
   word are always present, so fit never rests on color.
2. Mylo attribution moves onto the ring: when `origin === "llm"`, a small
   headshot marker sits on the ring instead of a plain arc cap.
3. Adopt it in a left gutter on the feed cards, leaving each card's existing
   content order intact: `suggestion-card.tsx`, `opportunities-section.tsx`
   (GrantRow), `conferences-section.tsx` (ConferenceCard),
   `fellowships-section.tsx` (FellowshipRow — ring for research fit, the
   eligibility tier badge stays, since eligibility is a different claim).
4. `overview-panels.tsx` (TopPapersPanel) uses the `sm` ring inline.
5. Retire `MatchBadge` once nothing imports it.

**Validation.** Every card that has a percent renders exactly one ring; the
gutter collapses cleanly at mobile width; contrast of the percent text and the
tier word clears WCAG AA on the card surface; `aria-label` still reads the
percent, the tier word, and Mylo attribution.

---

## Phase 3 — Declutter Research Papers

**Problem.** The filter rail stacks a cluster tier and, directly beneath it, an
interest-chip tier (up to dozens of sub-search parameters). The area reads as
crowded and the second tier restates what the cluster already says.

**Steps.**
1. Remove the interest-chip tier and its "Clear" affordance from the rail; keep
   the search input and the cluster tier.
2. Selecting a cluster now filters to that cluster only — no interest
   auto-selection, no derived focus percent.
3. Delete the now-dead `chipSet`, `interestsForCluster`, `focusPercent`,
   `focusMode`, `selected` state, `toggleChip`, and the `focusMode` /
   `displayPercent` props on `SuggestionCard`.
4. Show the cluster tier whenever there is at least one cluster (today it needs
   two), with an "All" segment so clearing is obvious.

**Validation.** Filtering by cluster narrows the list and the subtitle count;
cards keep their real match percent while filtered; no unused
exports/props remain; typecheck and lint clean.

---

## Phase 4 — Structural consistency pass

**Steps.**
1. `SectionHeader` gains an optional `eyebrow` (the small uppercase label the
   public site uses above every section heading) and keeps its `action` slot.
   Adopt it across the feed sections so every page opens the same way.
2. Unify the four filter rails' shared controls with the public site's
   segmented-control look, and fix the same `peer-checked` general-sibling trap
   if it appears here.
3. Sweep the workspace for text using `--text-muted` as body/meta copy (it
   measures ~3.4:1 on the app surface) and move those to `--text-secondary`,
   matching the fix already made on the public site.

**Validation.** Every section header renders through the primitive; a contrast
sweep over the workspace routes reports no failures; build clean.

---

## Phase 5 — Mirror the finalized card back onto the public site

**Steps.**
1. Update `web/landing/src/components/landing/LiveFeed.astro` so the sample
   cards use the app's finalized anatomy (ring gutter, badge row, title, meta,
   reason).
2. Keep the sample content fictional and labelled as such.

**Validation.** Landing build clean, still zero `<script>` tags, contrast sweep
still passes, the preview visibly matches an app card.

---

## Interfaces that change

- `MyloMark` — same props, now renders a raster portrait.
- `SuggestionCard` — drops `focusMode` and `displayPercent`.
- `MatchBadge` — removed; `MatchRing` replaces it.
- `SectionHeader` — gains optional `eyebrow`.
- `web/scripts/sync-landing-assets.mjs` — renamed to `sync-art-assets.mjs`,
  now emits app assets too; `web/app/package.json` gains predev/prebuild hooks.
- No Django, API-contract, or database changes.

## Acceptance criteria

- No hand-drawn mushroom SVG remains in `web/app`.
- One percent-match element, used everywhere a percent is shown.
- Research Papers shows clusters only above the list.
- `npm run build` (app) and `npm run build` (landing) both clean.
- Contrast sweep passes on the workspace routes and the public pages.
- `docs/repo-map.md` and `docs/changelog.md` updated; work committed.

## Exclusions

- Building the pipelines behind the "coming soon" surfaces (Reports/monthly
  summaries, cross-lab browsing, project editing). Those are Month 3–4 items in
  `docs/goals.md`; dressing them up as working would be dishonest. They keep
  their honest placeholder states.
- Any Django/DRF, Celery, or schema change.
- The knowledge-graph surfaces, which do not exist yet.
