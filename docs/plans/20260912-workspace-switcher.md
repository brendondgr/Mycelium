# Workspace Switcher — Plan

**Status:** awaiting variant choice (Phase 1 output).
**Correlation ID:** `20260912-workspace-switcher`

## Objective

Replace the two-position Personal/Lab slider in the app header with a workspace
switcher that can carry the org model the backend already has — personal, lab,
**and department** — and that stays usable for a PI in eight labs rather than
degrading into a long flat menu.

The current control is at
`web/app/src/components/portal/lab-switcher.tsx`. Its shape is the problem, not
its styling: it is a *binary* toggle whose right half silently changes meaning
(button → dropdown) depending on how many labs you belong to, so the same pixel
does three different things for three different users. A third scope kind cannot
be expressed in it at all.

## Why this is worth doing now

Four defects, each independently worth fixing, all rooted in the same control:

1. **Departments are invisible.** `MyDepartment`, `/app/department/[id]`,
   `GET /api/auth/departments/`, department profiles, rosters, invites and
   billing all exist. The switcher cannot reach any of it. A department is
   reachable today only from a card inside `labs-section.tsx`.
2. **Scope is not in the URL.** `labScope` lives only in `localStorage` under
   `mycelium_lab_scope` (`portal-context.tsx`). A link you paste to a labmate
   opens in *their* last workspace, not the one you were looking at. Two tabs
   cannot hold two workspaces.
3. **It does not scale.** One lab → a button. Two labs → a dropdown. Eight labs
   → an eight-item flat list with no search, no recents, no grouping.
4. **"Where am I" is weak in the header.** The sidebar states it well
   (`LabIdentity` / `PersonalIdentity` in `portal-sidebar.tsx`), the header
   states it as a pressed pill, and the two duplicate each other while neither
   is authoritative.

## The constraint that shapes everything (read this before designing)

**A department has no research feeds, and giving it some is a backend project,
not a frontend one.**

- `apps/content/targets.py` builds exactly three `MatchTarget` kinds:
  `user`, `lab`, `project`. There is no department builder.
- `apps/content/views.py` never mentions a department. Every feed, save,
  reminder and briefing route scopes with `?lab=<slug>` only
  (`web/app/src/lib/portal/client.ts`).
- A department owns *projects* and pays for *seats* (`tasks.py`), which is why
  it looks feed-adjacent without being a scored surface.

So a department workspace can honestly offer: overview, its labs, its roster,
its profile, invites, settings, billing, and its projects. It cannot offer
Papers / Grants / Fellowships / Conferences without someone first building a
department `MatchTarget` and adding it to the nightly run — and per the global
rules, that means the whole corpus gets ranked for every department every night.
That is a real cost and a separate decision.

**This plan therefore treats department feeds as out of scope** and renders
those nav entries as absent (not empty, not broken) in a department scope. See
*Open questions* — this is the one thing I want confirmed.

## Assumptions

- No product-direction change: the switcher is chrome, not a new feature, so
  `purpose.md` / `goals.md` are unaffected. `styles.md` governs its appearance.
- No new API endpoints. `GET /api/auth/labs/` and `GET /api/auth/departments/`
  already return everything a switcher needs, and both hooks
  (`useMyLabs`, `useMyDepartments`) already exist in `lib/portal/hooks.ts`.
- No backend change at all in Phases 1–7.
- `web/app` has no frontend test runner. Validation is `lint`, `build`, and
  driving the real app — stated per phase rather than pretended otherwise.

---

## Phase 1 — Prototype gallery (the deliverable you choose from)

**What.** One self-contained static HTML file,
`docs/plans/assets/20260912-workspace-switcher/prototypes.html`, that is a
near-exact replica of the real workspace chrome — header, left sidebar, mobile
tab strip, background — rendered with the actual tokens from
`web/packages/config/src/theme.css`, in both light and dark, with realistic
seeded data (a personal space, the FSU Dept. of Scientific Computing, PULSE Lab
plus enough sibling labs to show the scaling case).

Each variant is swapped into that same chrome so you are comparing switchers in
context, not floating widgets on a blank page.

**How.** Plain HTML + CSS + a little vanilla JS. No build step, no framework —
open the file in a browser. Tokens are copied from `theme.css` rather than
re-picked by eye, so what you approve is what ships. A theme toggle and a
"pretend I'm in N labs" control sit at the top so you can stress each variant.

**Why.** You asked to choose before I build. Building six switchers in React
inside the real portal would cost several days and a scope refactor *before* the
decision that determines what the refactor should look like. A static replica
gets the decision made in one pass, and it is deleted once the choice is made.

### The six variants

| # | Name | The idea | Strengths | Costs |
|---|---|---|---|---|
| A | **Command palette** | Header keeps one compact workspace chip; ⌘K/Ctrl+K opens a centred searchable palette grouped Personal / Departments / Labs, with recents on top | Scales to any number; fastest for keyboard users; smallest header footprint | Discoverability for mouse-first users; the chip alone must carry "where am I" |
| B | **Workspace rail** | A narrow always-visible vertical rail at the far left (Slack/Linear style): personal avatar, department crests, lab logos, `+` at the foot | Zero-click switching; strongest presence signal; uses lab logos already uploaded | Costs ~56px of width; needs a real mobile answer; awkward past ~10 workspaces |
| C | **Scope breadcrumb** | Header shows `Department › Lab`, each segment independently clickable with its own menu | Only variant that shows the real hierarchy — `MyLab.department` already carries it | Two menus to learn; personal scope has no parent, so the shape changes |
| D | **Sidebar workspace header** | The switcher moves out of the top bar into the head of the sidebar as a full-width identity block (logo, name, role, chevron) that expands in place into a searchable list | Merges the header pill and the sidebar identity block, which duplicate each other today; conventional and legible | Sidebar is hidden under `lg`, so mobile needs its own switcher |
| E | **Two-stage segmented** | A small segmented control for scope *kind*, then a picker for *which* | Closest to today, cheapest, least retraining | Keeps the flaw that scope kind and scope identity compete for one row |
| F | **Spore map** | On-brand: personal is the centre node, departments and labs are connected nodes on a small mycelium graph you click through | Distinctly Mycelium; makes the org structure felt rather than read | Risks novelty over utility; hard to make accessible and keyboard-navigable |

**Every variant is prototyped with all four of your must-haves wired**, so the
comparison is about form rather than feature: keyboard switching, scope in the
URL, a scaling story at 8+ workspaces, and an explicit active-workspace
treatment across header/sidebar/mobile.

**Validation.** Open the file; confirm light and dark against `styles.md`;
confirm each variant at 1 / 3 / 9 workspaces and at mobile width.

**You choose here.** Everything below is conditional on that choice.

---

## Phase 2 — Scope model refactor (no visual change)

**What.** Replace the `labScope: string` in
`web/app/src/components/portal/portal-context.tsx` with a typed scope:

```ts
type WorkspaceScope =
  | { kind: "personal" }
  | { kind: "lab"; slug: string }
  | { kind: "department"; id: string };
```

`currentLab` stays as a derived convenience so the ~dozen existing
`currentLab`-reading call sites keep compiling. Add `currentDepartment`,
`currentWorkspace` (a normalised `{ kind, key, name, role, logo }`), and a
combined `workspaces` list from `useMyLabs` + `useMyDepartments`.

**How.** Ship this behind the *existing* switcher first — the old control
narrows to `kind: "personal" | "lab"` and behaves identically. A refactor that
lands with its own UI change gives you no way to tell which half broke.

**Why.** Every later phase depends on scope being expressible. Doing it as its
own commit keeps the diff readable and reversible.

**Validation.** `npm --prefix web run lint`; `npm --prefix web run build`;
switch Personal ↔ lab in the running app and confirm feeds, projects, saves and
reminders are unchanged.

## Phase 3 — Scope in the URL

**What.** Make the URL the source of truth for scope, with `localStorage`
demoted to a *default for a bare `/app` entry* rather than the authority.

**How.** A `?ws=<key>` search param on the `(workspace)` routes, read in
`PortalProvider` and written by `setScope`. Precedence: explicit param → stored
default → personal. An unknown or no-longer-permitted key falls back to personal
rather than erroring, which is the self-healing behaviour the current code
already relies on (a removed lab resolves `currentLab` to null).

Preferred over a `/app/<scope>/…` path segment because the workspace route group
is flat and already stable; a path change would touch `routes.ts`,
`SECTION_ROUTES`, every `goToSection`, the nginx blocks and every emailed deep
link. A query param buys the same honesty for a fraction of the blast radius.
`/app/[labSlug]/dashboard` is a dead stub (a placeholder page with no real data)
— it is either deleted here or left alone, not extended.

**Why.** So a link is honest about what it points at, and so two tabs can hold
two workspaces. This is the one fix with no visual expression at all, which is
exactly why it never got done.

**Validation.** Paste a lab-scoped URL into a fresh private window as a member
(lands in that lab) and as a non-member (falls back to personal, no error);
confirm two tabs hold different workspaces; confirm bare `/app/overview` still
restores the last workspace.

## Phase 4 — Build the chosen switcher

**What.** Replace `lab-switcher.tsx` with the chosen variant, renamed
`workspace-switcher.tsx` (the component is no longer about labs).

**How.** Against the Phase 2 context and the Phase 3 URL behaviour. Radix
primitives where one fits — `@radix-ui/react-dropdown-menu` and
`react-dialog` are already dependencies, so the focus trap, roving tabindex and
dismissal behaviour come for free rather than being hand-rolled as the current
`useDismissable` does. Lab logos come from `labLogoUrl`, already used by
`LabIdentity`.

Must handle, because the current one only handles some of them: loading,
no labs and no departments, one workspace, many workspaces, a scope whose
membership was revoked mid-session, a long workspace name, and a lab with no
logo.

**Why.** This is the actual ask.

**Validation.** Lint, build, and drive it: switch between all three scope kinds
and confirm each lands on the right overview; confirm every state above.

## Phase 5 — Three-scope navigation

**What.** Teach `portal-sidebar.tsx` and `portal-mobile-nav.tsx` about
departments. Both currently branch on a boolean `inLab`, which cannot express a
third case.

**How.** Replace `const inLab = Boolean(currentLab)` with a switch on
`scope.kind`. A department scope gets: Overview, Labs, Members, Department
settings (managers), Projects, Saves, Reminders, Account (managers). It does
**not** get Papers / Grants / Fellowships / Conferences — per the constraint
above, those entries are absent rather than present-and-empty, because an entry
that always shows nothing teaches people the product is broken.

Also reconcile the sidebar identity block with the chosen switcher so the
workspace is stated once, authoritatively, rather than twice.

**Why.** A switcher that lands you somewhere the navigation cannot describe is
worse than no switcher.

**Validation.** Lint, build; walk all three scopes on desktop and at mobile
width; confirm manager-only entries stay manager-only. Confirm with a
non-manager account that nothing new leaked — the nav is not a permission
boundary (the API is), but it should not advertise what it cannot open.

## Phase 6 — Keyboard switching

**What.** ⌘K / Ctrl+K opens workspace switching from anywhere in the app;
type to filter, arrows to move, Enter to switch, Escape to dismiss.

**How.** If variant A wins this is already built in Phase 4 and this phase is
just the global hotkey and recents. Otherwise it is a second surface over the
same `workspaces` list. Registered once in `workspace-shell.tsx`, suppressed
while a text input or dialog has focus. Recents are a short MRU list in
`localStorage` — the one thing that legitimately belongs there.

Note the collision: `global-search.tsx` is the header's search. Whichever of
the two owns ⌘K, the other needs its own shortcut and both need their hint
visible. I will check what `global-search.tsx` currently binds before wiring.

**Why.** You named it a must-have, and it is the only mechanism that stays
constant-time as workspace count grows.

**Validation.** Drive it with the mouse untouched; confirm typing in a feed
search box does not trigger it; confirm it does not fight global search.

## Phase 7 — States, accessibility, responsiveness

**What.** The pass `styles.md` and the ADA skill require, done deliberately
rather than assumed.

**How.** Against WCAG 2.2 AA: `aria-current` / `aria-checked` on the active
workspace, a real accessible name on the control, visible focus rings on the
`--focus` token, contrast checked in both themes, reduced-motion honoured for
any transition, and no state carried by colour alone — the active workspace
needs a label or a mark, not just a green dot. Plus touch targets ≥44px and no
horizontal overflow on a 320px viewport.

**Why.** It is a first-class requirement in this project, and the current
switcher's `aria-pressed` on a button that is sometimes a menu is already wrong.

**Validation.** Keyboard-only traversal; a screen reader pass on the switcher;
contrast check on the active and inactive treatments in both themes; 320px
viewport check.

## Phase 8 — Documentation and cleanup

**What.** Update `docs/repo-map.md` (the portal shell row names
`lab-switcher`), `docs/api-contract.md` only if a scope param is documented
there, `docs/architecture.md` if the URL-scope rule belongs in it, and
`docs/changelog.md` with one `MODIFIED` entry. Delete the prototype HTML and
delete this plan.

**Why.** The repo's own rule: a plan is a working document, and a stale doc is
worse than no doc.

**Validation.** `make validate-research` is not relevant here (no experiment).
Re-read the changed doc rows against the shipped code.

---

## Interfaces that change

| Surface | Change |
|---|---|
| `components/portal/lab-switcher.tsx` | Deleted, replaced by `workspace-switcher.tsx` |
| `components/portal/portal-context.tsx` | `labScope: string` → typed `WorkspaceScope`; adds `currentDepartment`, `currentWorkspace`, `workspaces`, `setScope`; `currentLab` kept as derived |
| `components/portal/{portal-sidebar,portal-mobile-nav}.tsx` | Branch on `scope.kind` instead of `inLab` |
| `components/portal/portal-header.tsx`, `workspace-shell.tsx` | Mount the new switcher; register the hotkey |
| `lib/portal/routes.ts` | Scope param helpers |
| URL surface | `?ws=<key>` on `/app/*` — additive, existing links keep working |
| Backend, API, DB | **Nothing.** No endpoint, serializer, model or migration changes |

## Risks

- **Silent scope leakage.** The most dangerous failure is a request built with
  the wrong scope — a department key reaching a `?lab=` param. Mitigated by the
  scope being a tagged union rather than a bare string, so the wrong kind cannot
  be passed without a type error. The API enforces permissions regardless; this
  prevents confusing behaviour, not a security hole.
- **Refactor blast radius.** `currentLab` has call sites across sections.
  Keeping it derived in Phase 2 means they keep working untouched.
- **⌘K collision** with global search — checked before wiring, not after.

## Explicit exclusions

- No department research feeds, and therefore no department `MatchTarget`, no
  nightly-run targeting change, no `?department=` scoping. Named as a follow-on.
- No change to what any feed shows, how anything is ranked, or how briefings are
  produced.
- No project-as-workspace tier. Projects stay sidebar navigation.
- No landing-site change.
- No backend, billing or entitlement change. The switcher lists memberships; it
  does not gate anything, so no new tier gate is introduced.

## Open questions

1. **Department feeds — confirm the exclusion.** A department scope will show
   overview, labs, roster, projects, settings and billing, with no Papers /
   Grants / Fellowships / Conferences entries. Building those means a department
   `MatchTarget` and a nightly-run target class. Is the exclusion right for now?
2. **Which variant** (Phase 1 output).
3. **`/app/[labSlug]/dashboard`** is a dead placeholder stub. Delete it while
   I'm here, or leave it?
