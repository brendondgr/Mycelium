# Landing Feed Preview — Fidelity to the Real Feeds

**Status:** approved direction, ready to implement.
**Correlation ID:** `20260912-landing-feed-preview-fidelity`

## Objective

Make the front page's "Four feeds, one profile, every match explained" section an
honest preview of the four workspace feeds — Research Papers, Grants,
Fellowships, Conferences — matching the structure, field set, chrome and Mylo
prose a visitor will actually meet after signing up.

The section is
`web/landing/src/components/landing/LiveFeed.astro` +
`web/landing/src/components/landing/FeedCard.astro`, fed by `feedTabs` in
`web/landing/src/data/landing.ts`. It is mounted once, by
`web/landing/src/pages/index.astro`.

## Why this needs doing

The preview is not a stale approximation of the app — it shows a **different
card**. Four classes of defect:

### 1. It renders a judgement the app deleted

`FeedCard.astro` draws a left gutter carrying a position number (`1`, `2`) and a
Read / Skim / File verdict chip. `match-card.tsx` says, in its own doc comment,
that both are gone:

> There used to be a judgement gutter down the left — first a percent ring, then
> a rail carrying a position and a verdict chip. Both are gone. […] What is left
> is a card whose content starts where the card does.

The backend still computes `verdict`, `position` and `position_of`, and
`SuggestionSerializer` still sends all three — the **app** chose not to draw
them, because a feed that interleaves themes rendered per-theme positions as a
column of apparently unsorted numbers. So the marketing page promises a visual
element that does not exist on the page it is previewing. That is the single
worst failure mode for a section whose whole job is "this is what you get."

### 2. One card shape stands in for four that differ substantially

`FeedCard.astro` is one template with `kind` branches. The real feeds diverge
much further than those branches allow:

| | Papers | Grants | Fellowships | Conferences |
|---|---|---|---|---|
| Identity line | source · venue, then year · authors (2 lines) | `Sponsor; Original Posted <date>` (1 line) | `<Award class>; Original Posted <date>` (1 line) | `<Location>; <Event dates>` (1 line) |
| Amount | — | yes, bank icon, under identity | yes, bank icon, under identity | — |
| Right column | Save + Ignore inline | `CardActionBar` + `DeadlineMenu` | same | same |
| Extra rows | caveat, bridge note, cross-topics pill | — | eligibility tier, bullets, facet chips | rank badges, quality flags, open-window chips |
| Footer | inline `Read paper` link | `SourceRow` + `View opportunity` | `SourceRow` + `View fellowship` | `SourceRow` + `View conference` |

The preview currently gives conferences a `Where` / `When` definition list (the
app uses one semicolon-joined identity line), gives fellowships an award-class
*chip* (the app puts award class in the identity line), invents subject chips on
conference cards (subjects exist only in the filter rail), and puts amount in the
right-hand column (the app puts it under the title).

### 3. The deadline is drawn as text, not as the control it is

The preview prints a red `Due Sep 1` line. The app renders `DeadlineMenu`: a tiny
uppercase `Deadline` / `Deadlines` label over a full-width rounded button with a
calendar icon, the **next** date, and a chevron — which opens a popover listing
every round with a per-round `Alert` button. Deadlines being addressable, plural
and remindable is a real product capability; flattening it to red text hides it.

### 4. It shows none of the new Mylo output

Mylo's per-theme write-up (`apps/content/cluster_fit.py`) now produces a verdict,
three labelled beats (`matters` / `use` / `take`), a **mandatory caveat**, and a
bridge note. The app's cards render the reason sentence, the caveat under a
bolded `Worth knowing:` lead-in, and the bridge note. The preview shows the
reason only — so it drops the one element that most distinguishes Mylo from a
recommender: he tells you why *not* to read something.

It also overstates how often the green Mylo box appears. In the app that block is
conditional on `origin === "llm"`; most readers are on the deterministic path and
get a plain paragraph plus the deterministic caveat, verbatim:

> Mylo has not read this one for you — the placement is a topical match, not a
> judgement of the work itself.

### 5. The canonical style doc is now wrong, and would make this change look wrong

`docs/styles.md` § "How a recommendation states itself" says position and verdict
appear on "every surface — feed card, report entry, PDF, Discord". That is no
longer true: the app's feed card carries neither. The doc must be corrected in
the same change, or the next reader will treat the corrected preview as the
regression. `docs/skills/ui-frontend.md` likewise still names `MatchRing` as a
shared feed primitive; it no longer exists.

## Assumptions

- **The app is the source of truth.** Confirmed with the user: the preview is
  corrected to the app as it renders today. Restoring a judgement display inside
  the workspace is explicitly out of scope.
- **"Terminal" = the end-state rendering.** Confirmed: the preview should show
  the structure as the four feed pages will actually render it.
- **The preview keeps showing the page, not just the card.** The app puts a
  `FeedSearchBar` above every feed and a left filter rail beside Grants,
  Fellowships and Conferences. Both are included, inert. If they prove too heavy
  on the marketing page, the rail is the first thing to drop — it is one
  self-contained block.
- Sample content stays fictional, and the controls stay inert. Real feeds are
  lab-scoped and permission-gated.
- The landing site imports `@mycelium/config/theme.css`, so every token the app's
  cards use (`--cluster-1…8`, `--shadow`, `--success`, `--warning`,
  `--destructive`, `--accent`) is already in scope. No new tokens.
- The landing site still ships **zero framework JS**. Every interactive shape
  here — popovers, dropdowns, the filter rail — is rendered in its resting state
  as inert markup. No `client:*` directive.

## Open question (does not block)

`HiddenByFilters` renders only when the rail has hidden something. With no
filters applied in a static preview it would render nothing, so it is excluded.
If we later show the rail in an *engaged* state, it comes back.

---

## Phase 1 — Correct the canonical docs

**What:** fix the two docs that currently describe the deleted judgement rail as
live app UI.

**How:**
- `docs/styles.md` § "How a recommendation states itself": keep the rule that a
  recommendation is never a percentage. Split the surfaces explicitly — position
  and verdict are carried by the **report entry, the PDF, the Discord digest and
  the briefing**; the **app's feed cards carry no judgement element at all**, and
  say why (interleaved themes made a per-theme position read as an unsorted
  column). Keep the "gold is not for verdicts" rule as written.
- `docs/skills/ui-frontend.md`: drop `MatchRing` from the shared-primitives list;
  replace with the primitives that exist (`MatchCard`, `ClusterRow`,
  `DeadlineMenu`, `SourceRow`, `FeedSearchBar`, `FeedSentinel`).

**Why:** the rest of this plan makes the landing page disagree with `styles.md`.
A claim that is no longer true of the code is worse than no claim — and here it
would actively mislead the next person into reverting Phase 3.

**Validation:** re-read both sections against `match-card.tsx` and
`report-entry.tsx`; confirm no remaining sentence asserts a verdict chip in the
app.

---

## Phase 2 — Re-shape the preview data

**What:** rewrite `FeedItem` and `feedTabs` in
`web/landing/src/data/landing.ts` so the fields are the app's fields.

**How:** replace the current type with four per-kind item types sharing a common
core, so the compiler stops a conference from carrying an amount:

- **Core:** `title`, `identity` (the one semicolon-joined line), `description`,
  `reason`, `caveat`, `bridgeNote?`, `origin: "llm" | "fallback"`, `cluster`,
  `clusterToken`, `bridge?`, `isNew?`, `isUpdated?`, `sourceCredit`.
- **Papers add:** `provenance` + `byline` (the two meta lines) and
  `crossTopics?: true`. No deadline, no amount, no source row.
- **Grants add:** `amount`, `deadlines: { label, date, passed?, anticipated? }[]`,
  `deadlineFootnote?`.
- **Fellowships add:** `amount`, `deadlines`, `band: "matched" | "open"`,
  `eligibility?: "Qualified" | "Possible fit" | "Eligibility not listed"`,
  `eligibilityBullets?`, `facets?`.
- **Conferences add:** `deadlines`, `rankings?: { system, rank }[]`,
  `qualityFlags?: string[]`, `openWindows?: string[]`.

Delete `fit`, `rank`, `awardClass`, `where`, `when`, `subjects`, `due`, `byMylo`
(replaced by `origin`), and the `eligibility: "Not eligible"` value — the rule
engine's third tier is `"Eligibility not listed"`; a genuinely ineligible award is
gated out and never reaches a card.

Then rewrite the eight sample items in the current Mylo voice, taking the prose
contract from `cluster_fit.py` and the tone from
`management/commands/render_sample_report.py`. Concretely: one grounded reason
sentence naming the specific interest, and a caveat that is a real reason not to
bother. At least two items must sit on `origin: "fallback"` carrying the verbatim
deterministic caveat, so the preview does not imply every reader gets model prose.

**Why:** every downstream defect in `FeedCard.astro` is really a data-shape
defect. Fixing the template against the old shape would just move the lie.

**Validation:** `npm --prefix web/landing run build` (Astro type-checks the data
module through the component's `Props`).

---

## Phase 3 — Rebuild the card

**What:** replace `FeedCard.astro` with four per-kind cards over one shared shell.

**How:** `FeedCard.astro` keeps the shell (`Card`: `rounded-2xl`,
`border-border`, `bg-surface`, `var(--shadow)`, `p-5`, the `hover:-translate-y-0.5`
lift with its reduced-motion guard) and delegates the head and body to
`PaperCard.astro`, `GrantCard.astro`, `FellowshipCard.astro`,
`ConferenceCard.astro` in the same directory.

Every card, in order:

1. **No gutter.** Content starts at the card's left edge. Delete `.fit-position`,
   `.fit-chip`, `.fit-chip-mylo` and the grid that reserved the column.
2. Head: `flex flex-wrap items-start justify-between gap-3`; left block
   `min-w-0 flex-1`.
3. Title — `font-serif text-lg font-semibold leading-snug`.
4. Identity line(s), per the table above.
5. Amount line (grants, fellowships only) — bank icon + `text-xs font-semibold
   text-[var(--text-primary)]`.
6. `ClusterRow`: `NewTag` then `UpdatedTag` (grants/conferences only) as leading
   chips, then the cluster badge, then the dashed `Also: …` bridge badge. Papers
   included — the New tag leads the cluster row on papers too, it does **not**
   ride the right-hand stack.
7. Kind-specific rows: fellowship eligibility tier (its own row, under the
   cluster row); conference rank badges + quality-flag pill, then the
   `Mylo flagged this date` note.
8. Right column:
   - Papers — inline `Cross-topics match` pill (only when `crossTopics`), then
     bookmark, then eye-off.
   - Opportunities — the `CardActionBar` column at `w-[8.75rem]`: icon row
     **Ignore → Remind → Save**, left to right, all neutral at rest except Save,
     which keeps its gold tint because it is state; beneath it the `DeadlineMenu`
     in its **closed** state — uppercase `Deadline`/`Deadlines` label, then the
     bordered full-width button with calendar icon, next date, chevron.
9. Description.
10. Reason — the soft primary `MyloReason` box with the portrait when
    `origin === "llm"`, a plain paragraph otherwise.
11. **Caveat** — `Worth knowing:` in semibold, then the sentence, in
    `text-[var(--text-muted)]`. New to the preview.
12. **Bridge note** — plain paragraph. New to the preview.
13. Fellowship eligibility bullets (`<ul>` under 4 items, `<details>` at 4+) and
    facet chips; conference open-window chips.
14. Footer — papers get the inline `Read paper` link with the arrow; the other
    three get `SourceRow`: a `border-t border-[var(--divider)] pt-3` row with the
    licence/source credit on the left and the pill-shaped `ViewLink` on the
    right, labelled `View opportunity` / `View fellowship` / `View conference`.
    The current `View venue` label is not a string the app uses.

Controls stay `span`s, never focusable, `aria-hidden` where they convey nothing —
they are shapes, not functions. The deadline button must not be announced as a
control that opens nothing.

**Why:** this is the phase that actually delivers the ask. Each of the four feeds
gets the row it really has, including the three capabilities the current preview
hides entirely — plural addressable deadlines, the rule-engine eligibility tier,
and venue quality signals.

**Validation:** `npm --prefix web/landing run build`; then a side-by-side read of
each rendered card against its section component.

---

## Phase 4 — Rebuild the section around the cards

**What:** update `LiveFeed.astro` so the surrounding page chrome is the app's.

**How:**
- Replace each tab's `blurb` with the app's real subtitle copy, in the app's
  shape — e.g. Grants: `"12 grants matched your research profile and timeline."`;
  Conferences: `"9 conferences, ranked by fit · gathered this morning."` The
  eyebrow/title pairs (`Your feed` / `Research Papers`, `Opportunities` /
  `Grants`…) are already right and stay.
- Add the inert `FeedSearchBar` above each panel: the search field with its real
  per-feed placeholder, and the cluster chip row beneath it.
- Add the inert filter rail beside Grants, Fellowships and Conferences —
  `flex flex-col gap-6 lg:flex-row lg:gap-8`, rail first, list in
  `min-w-0 flex-1`. Rail is `lg:` only; on mobile it collapses out, exactly as
  the narrow-screen app behaves.
- Papers: no rail, and add the `Cross-topics matches` divider — a centred
  uppercase label between two hairlines — before the final paper.
- Fellowships: add the two band headings, `Matched to your themes` and
  `Open to you`, with their real notes.
- Keep the CSS-only radio tab mechanism and the `:has()` fallback exactly as is.

**Why:** the cards do not appear on a blank page. A reader deciding whether this
product fits their workflow needs to see that the feed is searchable, filterable
and split into bands — those are the things that make it a workspace rather than
a list.

**Validation:** build; then check the tab group still works with arrow keys and
that the rail does not create horizontal overflow at 320px.

---

## Phase 5 — Copy pass on the section's own heading

**What:** keep the heading, fix the paragraph under it.

**How:** the supporting paragraph currently reads "Mycelium **scores** what it
finds against your lab's research clusters". "Scores" implies the number the
product deliberately does not show. Rewrite it to say what actually happens: Mylo
matches each item to a research theme, writes why it fits, and names what would
make it a waste of your time. Keep the sentence disclosing that the content is
fictional and the controls inert.

The heading `Four feeds, one profile, every match explained` stands. With the
caveat and bridge note now rendered, the preview earns the claim for the first
time.

**Why:** `docs/styles.md` bans the percentage because it implied a measurement
nobody made; "scores" smuggles the same implication back in as a verb.

**Validation:** read against `docs/styles.md` § Voice And Copy.

---

## Phase 6 — States, responsiveness, accessibility

**What:** the checks `docs/skills/ui-frontend.md` requires of any UI change.

**How:**
- Dark theme: every colour is a token or a `color-mix` over one — verify no
  hard-coded hex survives except the two the app itself hard-codes (the blue
  `#3f6fa3` alert/remind accent).
- Reduced motion: the card lift and the chevron rotation both carry a
  `prefers-reduced-motion` guard.
- 320px / 768px / 1280px: no horizontal overflow; the `w-[8.75rem]` action
  column wraps under the head rather than crushing the title.
- Contrast: the muted caveat text against `--surface` in both themes must clear
  4.5:1. `--text-muted` at `#7F8775` on `#FFFDF8` is the one to actually measure
  — if it fails, the caveat uses `--text-secondary`.
- Nothing is signalled by hue alone: every chip carries text.
- Inert controls are `aria-hidden` or carry no role; no focus stop leads nowhere.

**Why:** this section is the densest thing on the front page and the most likely
to break on a phone.

**Validation:** `npm --prefix web/landing run build`, then a manual pass at the
three widths in both themes.

---

## Phase 7 — Record and commit

**What:** close the loop per `docs/skills/global.md`.

**How:**
- `docs/repo-map.md`: the landing feed row currently reads "Landing feed preview
  card (mirrors the app's `MatchCard`)" and points at one file. Update it to name
  the four per-kind cards.
- `docs/changelog.md`: one `MODIFIED` entry under `## Entries`, correlation ID
  `20260912-landing-feed-preview-fidelity`, UTC timestamp, outcome-focused.
- Delete this plan file once the work has shipped.
- Commit. Do not push without explicit permission.

**Validation:** `make validate-research` is not applicable (no experiment here —
no metric is produced or reported). Final `npm --prefix web/landing run build`.

---

## Interfaces that change

| Surface | Change |
|---|---|
| `web/landing/src/data/landing.ts` | `FeedItem` replaced by four per-kind types; `feedTabs` content rewritten |
| `web/landing/src/components/landing/FeedCard.astro` | Reduced to a shell + delegation |
| `web/landing/src/components/landing/{Paper,Grant,Fellowship,Conference}Card.astro` | New |
| `web/landing/src/components/landing/LiveFeed.astro` | Search bar, filter rail, band headings, divider, copy |
| `docs/styles.md` | § "How a recommendation states itself" corrected |
| `docs/skills/ui-frontend.md` | Primitive list corrected |
| `docs/repo-map.md`, `docs/changelog.md` | Updated |

No backend, no API, no app route, no entitlement, no new dependency, no new
route registration. Nothing here touches an authenticated surface.

## Acceptance criteria

1. No position number and no verdict chip appears anywhere in the landing
   preview.
2. Each of the four cards renders the field set its app counterpart renders, in
   the same order, and nothing it does not.
3. Every card shows a caveat; at least two show the deterministic caveat verbatim
   with a plain (non-Mylo-box) reason.
4. Deadlines render as the closed `DeadlineMenu` control, not as red text.
5. Fellowship cards carry a rule-engine tier and sit under a band heading.
6. Conference cards carry rank badges and the quality-flag pill.
7. Footer link labels are `Read paper`, `View opportunity`, `View fellowship`,
   `View conference`.
8. `npm --prefix web/landing run build` passes; no framework JS is added.
9. `docs/styles.md` no longer claims the app's feed card shows a verdict.
10. No horizontal overflow at 320px; reduced-motion honoured; dark theme intact.

## Explicitly out of scope

- Restoring the verdict chip or per-theme position **inside the workspace app**.
  The user chose the opposite direction; the backend keeps computing and serving
  `verdict` / `position` / `position_of` regardless.
- Rendering the three-beat write-up (`matters` / `use` / `take`) anywhere. The
  API serializes `beats` and the app discards them; the preview mirrors the app.
- Any change to `apps/content` — no ranking, scoring, prompt or serializer edits,
  so no evaluation-harness run and no research-record entry is required.
- The product, pricing, about and contact pages, and the `FeedCard` usage on
  them. There is none — `LiveFeed` is mounted only by `index.astro`.
- Making the preview's controls actually work.
