# Portal Home — Authenticated Lab Dashboard

**Branch:** `claude/portal-home-dashboard` (merged to `main` on completion; no push)
**Status:** In progress — planning complete; implementation underway.

## 1. Objective

Replace the placeholder authenticated home feed at `/app` with a full **Portal Home**
lab-intelligence dashboard, ported from the supplied design proposal
(`Portal Home.html`, a self-contained Design-Component bundle) into the Mycelium
Next.js stack. The new home feed must:

- Be **compartmentalized** — every part (header, switcher, sidebar, each content
  section, each card) is its own reusable component, not one monolith.
- Be **converted to our stack** — React + Next.js App Router + TypeScript +
  Tailwind semantic tokens, replacing the proposal's inline `style="…"` /
  `var(--token)` markup and the `dc-runtime` template language.
- **Animate** purposefully — section transitions, card hover lift, pulsing status
  dots, progress-bar fills, mycelium motifs — all reduced-motion aware.
- **Follow the style guide** (`docs/styles.md`) — warm botanical SaaS, Fraunces
  headings + Inter UI, gold reserved for opportunities, honest empty states.
- **Connect to the backend** so it is real per signed-in account, not the mock's
  hardcoded "Dr. Reyes / Reyes Lab". Where no pipeline exists yet, show honest
  empty / "coming soon" states structured so real data drops in later.

The proposal is a **template**, not a paste target: content adapts to what the
Mycelium backend actually knows about the signed-in user.

## 2. Locked decisions (user-confirmed + codebase patterns)

| ID | Decision |
|----|----------|
| D1 | **Backend scope = read endpoints.** Add read-only DRF endpoints for the user's labs+roles, visible projects, and lab members; wire those plus existing `me`/`profile`/`watch`. No write actions (create project, invite, edit goals) this pass. |
| D2 | **Empty sections = honest states.** Daily Reports, Opportunities, Deadlines, Reports, Mylo's weekly summary, and project recommendations have no pipeline yet → on-brand "Mylo will surface this after your first scan" / "Coming soon" states, clearly labeled, never fabricated per-user data. Matches `styles.md` honesty rules and the mock's own Reports state. |
| D3 | **Replace, don't add.** The `/app` workspace page (`web/app/src/app/app/page.tsx`) is replaced by the portal. The reserved `/app/[labSlug]/dashboard` route stays as-is for now. |
| D4 | **Semantic tokens, not inline hex.** Port the proposal's `var(--bg)`/`var(--text)`/etc. onto the app's existing tokens in `web/packages/config/src/theme.css`. Add the two missing tokens the design uses — `--clay` / `--clay-soft` (terracotta urgency) — to both light and dark. |
| D5 | **Theme toggle is real.** A light/dark toggle sets `data-theme` on `<html>`, persists to `localStorage`, and is applied pre-paint by an inline script to avoid flash. `theme.css` already keys dark off `[data-theme="dark"]`. |
| D6 | **Stats adapt to real metrics.** The four Overview stat cards surface metrics we actually have per account (your projects, your labs, profile completeness, watch topics) rather than fabricated paper/grant counts. Layout preserved; data honest. |
| D7 | **Animations via CSS transforms** for section/slide motion (reduced-motion aware), reusing the onboarding `OnboardingStage` approach; framer-motion only for decorative SVG (as in `mycelium-branch.tsx`). Per memory [[frontend-animation-and-preview]]. |
| D8 | **Commits human-authored, no AI attribution / co-author trailers** (per `docs/skills/global.md`, which overrides the harness default). Per-phase commits; no push until the final merge to `main`. |

## 3. Grounded facts (verified by exploration)

### Design proposal
- `Portal Home.html` is a bundled DC page; the real UI is the `<x-dc>` template +
  `<script data-dc-script>` logic class (decoded to scratchpad for reference).
- Sections (`defaultSection` enum): `overview`, `daily`, `opportunities`,
  `deadlines`, `projects` (list + detail), `goals`, `members`, `reports`.
- Chrome: sticky header (logo, lab switcher dropdown, global search, notifications,
  theme toggle, user menu), 244px sidebar (Workspace / Research / Lab nav groups,
  expandable Projects sub-nav), sticky footer status bar.
- Logic state: `theme`, `switcherOpen`, `currentLab`, `nudgeDismissed`, `section`,
  `activeProject`, `projectsExpanded`, `selectedDay`, `addedRecs`. Lab switch
  filters projects; `addRec` moves a recommendation into the project feed.
- Design tokens already match Mycelium's palette exactly; extra tokens used:
  `--clay`/`--clay-soft`, plus `--gap`/`--pad` density vars and a `pulseDot` keyframe.

### Frontend stack
- Next.js App Router under `web/app/src`. `providers.tsx` already wraps a
  `@tanstack/react-query` `QueryClientProvider`. Fonts (Fraunces/Inter/Geist) loaded
  in `layout.tsx`. Tokens in `web/packages/config/src/theme.css`.
- Auth/data patterns: `lib/auth-server.ts` (`getCurrentUser`, `requireOnboardedUser`,
  SSR fetch with `Cookie` header), `lib/auth-client.ts` (CSRF-aware `fetch`,
  `buildApiUrl`), `lib/api-url.ts`. Reusable parts: `components/ui/button.tsx`
  (cva variants), `components/brand/mylo-mark.tsx`, onboarding `OnboardingStage`
  (CSS-transform slide) and `MyceliumBranch` (framer-motion SVG).
- `framer-motion` v12 installed. `cn()` in `lib/utils.ts`.

### Backend (Django + DRF, session auth)
- Routes today live under `/api/auth/…` (`apps/accounts/urls.py`) + `/api/health/`.
  No projects / labs-list / members / content endpoints exist yet.
- Existing & wired-ready: `GET /api/auth/me/`, `GET|PATCH /api/auth/profile/me/`,
  `GET|PATCH /api/auth/watch/me/`, `GET|PATCH /api/auth/labs/<slug>/profile/`.
- Models: `accounts.Lab` (slug, name, department), `accounts.LabMembership`
  (user, lab, role ∈ owner/admin/member/viewer, `is_lead`), `accounts.Department`,
  `accounts.DeptMembership`, `accounts.Profile` (academic_title, institution,
  interests JSON, external ids, is_verified), `accounts.WatchPreference`
  (topics, categories, cadence).
- `research.Project`: UUID id, exactly one of `scope_user`/`scope_lab`/
  `scope_department`, `name`, `goals` (JSON dict), `members` (M2M via
  `ProjectMember`). **No `status`/`progress`/`description` columns** — those live in
  `goals` JSON if at all. `Project.objects.visible_to(user)` encapsulates the
  member/owner/lab-head/dept-head cascade (`research/models.py`).
- Discover a user's labs: `user.lab_memberships.all()` → `(lab, role, is_lead)`.
- DRF style: `RetrieveUpdateAPIView`/`APIView`/`@api_view` with **inline
  `get_object()` object-permission checks** (helpers in
  `apps/accounts/permissions.py`: `user_has_lab_access`, `user_can_manage_lab`, …).
  Default permission `IsAuthenticated`; session auth + CSRF.

### Validation (host venv per [[backend-local-validation]])
- `export UV_PROJECT_ENVIRONMENT=/home/bdgr/.cache/mycelium-backend-venv`
- tests: `DATABASE_URL="sqlite:////<abs>/test.db" uv run --directory web/backend python -m pytest -q`
- lint: `uv run --project web/backend ruff check web/backend`
- migrations: `uv run --project web/backend python web/backend/manage.py makemigrations --check`
- fresh pgvector: throwaway `pgvector/pgvector:pg17` on `:5433` (see memory).
- frontend: `npm --workspace @mycelium/app run lint`; `… run build`. (Note: the
  Docker-created `web/app/.next` + `next-env.d.ts` are root-owned; renamed aside so
  the host build can write a fresh dir.)
- Baseline confirmed green: backend 266 passed, ruff clean, no migration drift;
  app lint clean, `next build` succeeds.

## 4. Public interfaces that change

**New backend endpoints** (all session-auth, read-only, object-safe):
- `GET /api/auth/labs/` → `[{ slug, name, role, is_lead, department }]` for the
  caller's lab memberships (+ owned/effective departments where useful).
- `GET /api/auth/labs/<slug>/members/` → `[{ name, username, email, role, is_lead,
  initials }]`; gated by `user_has_lab_access`.
- `GET /api/projects/?lab=<slug>` → caller's `visible_to` projects, optional lab
  filter → `[{ id, name, scope, goals, status?, progress?, member_count, members[] }]`
  (status/progress derived from `goals` JSON when present, else null).

**New frontend surface:**
- `app/app/page.tsx` rewritten to SSR-fetch the user + initial labs/projects and
  render `<Portal>`.
- `components/portal/**` — chrome (`portal.tsx`, `portal-header.tsx`,
  `lab-switcher.tsx`, `global-search.tsx`, `theme-toggle.tsx`, `notification-bell.tsx`,
  `user-menu.tsx`, `portal-sidebar.tsx`, `sidebar-nav-item.tsx`, `projects-nav.tsx`,
  `portal-footer.tsx`), `components/portal/sections/*` (one file per section + cards),
  `components/portal/primitives/*` (`card`, `pill`, `progress-bar`, `avatar`,
  `icon-button`, `section-header`, `empty-state`), `components/portal/icons.tsx`,
  `components/portal/section-stage.tsx` (animated switcher).
- `lib/portal/{types,api,hooks,theme}.ts` — types, CSRF-aware fetchers, react-query
  hooks, theme persistence.
- Tokens: `--clay`/`--clay-soft` (+ density vars) in `theme.css`; portal keyframes
  in `globals.css`. Pre-paint theme script in `layout.tsx`.

**Docs:** `api-contract.md` (new endpoints), `changelog.md`, `goals.md`
(Week-6 note), this plan.

## 5. Phased plan (each phase: implement → validate → commit; no push)

- **Phase 0 — Baseline & branch.** ✅ Branch cut; backend + frontend baselines green.
- **Phase 1 — Plan.** This document. Commit.
- **Phase 2 — Backend read endpoints.** `accounts`: `MyLabsView`,
  `LabMembersView` (+ serializers, urls). `research`: new `serializers.py`,
  `views.py` (`ProjectListView`), `urls.py`; include in `config/urls.py` under
  `api/`. Object-permission via existing helpers; `visible_to` for projects. Tests
  (own-only, role visibility, lab filter, anonymous 401/403, non-member 403).
  api-contract. Validate (pytest + ruff + makemigrations --check). Commit.
- **Phase 3 — Frontend foundation.** Tokens (`theme.css`) + portal keyframes
  (`globals.css`) + pre-paint theme script (`layout.tsx`); `lib/portal/*`
  (types/api/hooks/theme); primitives + icon set. Validate (lint + build). Commit.
- **Phase 4 — Chrome.** Header (logo, lab switcher → `useMyLabs`, search,
  notifications, theme toggle, user menu), sidebar (nav groups + projects sub-nav →
  `useProjects`), footer status bar. Validate (lint + build). Commit. *(Fan-out:
  Sonnet builds isolated leaf files; Opus integrates.)*
- **Phase 5 — Content sections.** All eight sections + their cards, composed from
  primitives: Overview (Mylo summary, real stat cards, next actions, profile nudge),
  Daily Reports (empty), Opportunities (empty), Deadlines (empty), Projects list +
  detail (real), Goals & profile (real interests/watch), Members (real), Reports
  (coming soon). Loading/empty/error/permission states throughout. Validate
  (lint + build). Commit. *(Fan-out across independent section files.)*
- **Phase 6 — Integrate & verify.** `portal.tsx` composes chrome + sections with
  section/scope/theme state and animated transitions (`section-stage.tsx`,
  reduced-motion aware). Rewrite `app/app/page.tsx` (SSR). Browser walkthrough via
  Preview: light/dark, every section, lab switch, projects expand/detail, empty
  states, keyboard nav, mobile width. Fix issues. Commit.
- **Phase 7 — Docs + full validation + merge.** changelog (schema), api-contract,
  goals Week-6 note, plan status. Full backend suite on SQLite **and** fresh
  pgvector; app lint + build. Merge `claude/portal-home-dashboard` → `main`;
  re-validate. No push. Commit.

## 6. Validation & acceptance

- Per phase: targeted tests green, `ruff` clean, `makemigrations --check` clean;
  frontend phases lint + build (typecheck) clean. Commit per phase (human-authored,
  no AI trailer).
- Final: full backend suite green on SQLite **and** a fresh pgvector Postgres; app
  lint + build clean; branch merged to `main` still green.
- Acceptance:
  - Two different signed-in accounts see **their own** name, labs (switcher),
    projects, members, profile completeness, and watch topics — no hardcoded mock data.
  - The lab switcher scopes projects (and project-derived counts) to the chosen lab.
  - Sections with no pipeline render honest empty / "coming soon" states, never
    fabricated per-user content.
  - Theme toggle persists and applies without flash; honors `prefers-reduced-motion`.
  - Every part is an importable, reusable component; the page composes them.
  - New endpoints enforce auth + object-level permission (non-member → 403,
    anonymous → 401/403).
  - Keyboard- and mobile-usable; meets the contrast/semantics expectations in
    `styles.md` / the ada-compliance skill.

## 7. Exclusions

Write actions (create project, invite member, edit goals/profile from the
dashboard), the relevance/scoring/digest pipelines behind Daily Reports /
Opportunities / Deadlines / Reports, real recommendation generation, notification
backend, global-search backend, department-dashboard scoping beyond labs, the
`/app/[labSlug]/dashboard` route rework, and any scraper/graph work. These keep
their honest placeholders and wire in later.

## 8. Orchestration

Per the session request: **Opus** (this agent) plans, validates each gate, and
commits; **Haiku** sub-agents do repository/API search (backend map already done);
**Sonnet** sub-agents implement self-contained phases. Backend (Phase 2) is
sequential (shared `views.py`/`urls.py`). Frontend leaf components (Phases 4–5,
isolated new files) fan out across Sonnet agents and Opus integrates. Phase 6
integrates after the foundation, chrome, and sections land.
