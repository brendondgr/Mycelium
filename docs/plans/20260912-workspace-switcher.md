# Workspace Switcher — Implementation Plan

**Status:** design chosen (rail + mobile sheet), implementing.
**Correlation ID:** `20260912-workspace-switcher`
**Prototype:** `docs/plans/assets/20260912-workspace-switcher/prototypes.html`
(open it and use the toolbar; `#v=B&n=9&m=1&open=mSheet` is the mobile sheet).

## Objective

Replace the two-position Personal/Lab slider in the app header
(`web/app/src/components/portal/lab-switcher.tsx`) with a workspace switcher that
carries the org model the backend already has — **personal, lab, and
department** — and that stays usable for a PI in eight labs.

## The chosen design

**Desktop — a workspace rail.** A 60px always-visible column at the far left, to
the left of the existing sidebar: personal avatar, then department marks, then
lab marks, then a `+`. The active workspace carries a green edge indicator and a
ring. Switching is one click with nothing to open. The header keeps a small
caption naming the current workspace and its kind.

**Mobile — one sheet, and nothing else.** At phone width the rail is *hidden
entirely* (a rail is a desktop idea; shrunk to a strip it is unrecognisable) and
the secondary tab strip (`portal-mobile-nav.tsx`) is **deleted**. In their place,
a single control in the header opens one sheet containing:

1. The current workspace as an expand-in-place block (the same interaction the
   desktop sidebar uses), **collapsed by default**.
2. Directly beneath it, every navigation entry — Workspace group, Research
   group, Account.

Expanding the block swaps the sections for the workspace list, with a filter
field once there are more than five. Choosing a workspace switches and
re-collapses.

**Why collapsed by default.** With nine workspaces an always-open list pushes
"Overview" below the fold, making the common action (change section) pay for the
rare one (change workspace). This was visible in the first prototype pass and is
the reason the block collapses.

**Keyboard.** ⌘K / Ctrl+K opens a workspace palette from anywhere. The shortcut
is **not advertised on the surface** — no `⌘K` badges in the product chrome.
`global-search.tsx` binds no keyboard shortcut, so there is no collision.

## The constraint that governs the department scope

**A department has no research feeds, and giving it some is a backend project.**

- `tools/recommendation/targets.py` builds exactly three `MatchTarget` kinds: `user`,
  `lab`, `project`. There is no department builder.
- `apps/content/views.py` never mentions a department; every feed, save, reminder
  and briefing route scopes with `?lab=<slug>` only.

So a department workspace offers overview, its labs, roster, projects, profile,
settings and billing. Papers / Grants / Fellowships / Conferences are **absent
from the navigation, not empty** — an entry that always shows nothing teaches
people the product is broken.

This needs a guard, not just a hidden nav entry. Today every feed section reads
`if (currentLab) return <LabFeed/>` and otherwise renders the *personal* feed —
so a department scope would silently show personal results on
`/app/grants?ws=d-sc`. Phase 5 adds a redirect for sections a scope does not
offer.

## Assumptions

- No product-direction change; `purpose.md` / `goals.md` unaffected,
  `styles.md` governs appearance.
- **No backend change in any phase.** `GET /api/auth/labs/` and
  `GET /api/auth/departments/` already return what the switcher needs, and both
  hooks (`useMyLabs`, `useMyDepartments`) already exist.
- `web/app` has no frontend test runner, so validation is `lint`, `build`, and
  driving the real app. Stated per phase rather than pretended otherwise.

---

## Phase 2 — Typed scope, behind the existing control

**What.** Replace `labScope: string` in `portal-context.tsx` with a tagged union
in a new `lib/portal/workspace.ts`:

```ts
export type WorkspaceScope =
  | { kind: "personal" }
  | { kind: "lab"; slug: string }
  | { kind: "department"; id: string };
```

Context gains `scope`, `setScope`, `workspaces`, `currentWorkspace`,
`currentDepartment`, `departments`. **`currentLab`, `labScope` and `setLabScope`
stay, derived**, so the ~25 existing call sites keep compiling untouched.

**How.** Ship it with the *old* switcher still mounted, narrowed to personal/lab.
No visual change.

**Why.** Every later phase depends on scope being expressible. A refactor that
lands with its own UI change gives no way to tell which half broke.

**Validation.** `npm --prefix web run lint`; `npm --prefix web run build`;
switch Personal ↔ lab and confirm feeds, projects, saves, reminders unchanged.

## Phase 3 — Scope in the URL

**What.** `?ws=<key>` on the workspace routes becomes the source of truth;
`localStorage` is demoted to the default for a bare `/app` entry.

**How.** Precedence: explicit param → stored default → personal. An unknown or
no-longer-permitted key falls back to personal rather than erroring — the
self-heal the current code already relies on. A query param rather than a path
segment because a path change would touch `routes.ts`, every `goToSection`, the
nginx blocks and every emailed deep link, for the same benefit.

**Why.** So a pasted link opens the workspace being discussed, and two tabs can
hold two workspaces.

**Validation.** A lab URL in a private window as a member (lands there) and as a
non-member (falls back, no error); two tabs, two workspaces; bare
`/app/overview` restores the last workspace.

## Phase 4 — The desktop rail

**What.** `components/portal/workspace-rail.tsx`, mounted in
`workspace-shell.tsx` to the left of `PortalSidebar`, `hidden lg:flex`.

**How.** Lab logos via the existing `labLogoUrl`; a tinted initials tile as the
fallback, with the mark derived so `Dept. of Scientific Computing` reads `SC`,
not `DO`. Tooltip on hover and focus. Active state carries the edge bar **and**
`aria-current`, so it is not colour-alone.

Must handle: loading, no orgs at all, one workspace, many, a revoked membership
mid-session, a long name, a lab with no logo.

**Validation.** Lint, build, drive all three scope kinds.

## Phase 5 — Three-scope navigation and the mobile sheet

**What.** Three things that must land together:

1. `lib/portal/nav.ts` — one scope→sections model, consumed by both the sidebar
   and the sheet, so they cannot drift.
2. `portal-sidebar.tsx` switches on `scope.kind` instead of `inLab`.
3. `components/portal/workspace-sheet.tsx` replaces `portal-mobile-nav.tsx`,
   which is **deleted**.

Plus the scope guard: a redirect to overview when the active section is not in
the current scope's nav.

**Why.** A switcher that lands you somewhere the navigation cannot describe is
worse than no switcher, and the guard is what stops a department scope showing
personal feed results.

**Validation.** Lint, build; walk all three scopes at desktop and phone width;
confirm manager-only entries stay manager-only with a non-manager account;
confirm `/app/grants?ws=<dept>` redirects rather than showing personal grants.

## Phase 6 — ⌘K workspace palette

**What.** `components/portal/workspace-palette.tsx` — a Radix dialog over the
same `workspaces` list; type to filter, arrows, Enter, Escape.

**How.** Registered once in `workspace-shell.tsx`, suppressed while a text input
or another dialog has focus. Recents are a short MRU in `localStorage`. **No
visible shortcut badge.**

**Validation.** Drive with the mouse untouched; confirm typing in a feed search
box does not trigger it.

## Phase 7 — States, accessibility, responsiveness

Against WCAG 2.2 AA: `aria-current` on the active workspace, real accessible
names, focus rings on `--focus`, contrast in both themes, reduced-motion
honoured, nothing carried by colour alone, touch targets ≥44px in the sheet, no
horizontal overflow at 320px.

## Phase 8 — Documentation and cleanup

Update `docs/repo-map.md` (the portal row names `lab-switcher`), `architecture.md`
for the URL-scope rule, and `docs/changelog.md`. Delete the prototype HTML and
this plan.

---

## Interfaces that change

| Surface | Change |
|---|---|
| `lib/portal/workspace.ts` | **New** — scope union, workspace list, marks |
| `lib/portal/nav.ts` | **New** — the one scope→sections model |
| `components/portal/workspace-rail.tsx` | **New** — desktop rail |
| `components/portal/workspace-sheet.tsx` | **New** — mobile sheet |
| `components/portal/workspace-palette.tsx` | **New** — ⌘K |
| `components/portal/lab-switcher.tsx` | **Deleted** |
| `components/portal/portal-mobile-nav.tsx` | **Deleted** |
| `portal-context.tsx` | Typed scope; `currentLab` kept derived |
| `portal-sidebar.tsx`, `portal-header.tsx`, `workspace-shell.tsx` | Rewired |
| URL | `?ws=<key>` — additive; existing links keep working |
| Backend, API, DB | **Nothing** |

## Risks

- **Silent scope leakage** — a department key reaching a `?lab=` param. The
  tagged union makes passing the wrong kind a type error; the API enforces
  permissions regardless, so this is a correctness guard, not a security one.
- **Refactor blast radius** — `currentLab` has ~25 call sites; keeping it derived
  in Phase 2 means none of them change.
- **Two navigations to maintain** — desktop and mobile are now genuinely
  different components. `lib/portal/nav.ts` is the mitigation: one model, two
  renderers.

## Explicit exclusions

- No department feeds, no department `MatchTarget`, no nightly-run target class,
  no `?department=` scoping. Named as a follow-on.
- No change to what any feed shows or how anything is ranked.
- No project-as-workspace tier; projects stay sidebar navigation.
- No landing-site, backend, billing or entitlement change.
