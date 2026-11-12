# Settings, Workspace Gating and Department Research — Implementation Plan

**Status:** decisions answered on 2026-11-12 and folded in; nothing built.
Two points are still open (last section). Nothing ships ahead of the rest:
the phases are an order of work inside one build, not separate releases.
**Correlation ID:** `20261112-settings-gating`
**Companion plan:** `20261112-project-scoping-and-visibility.md`

## Objective

1. One **Settings** area at the foot of the sidebar, where a person switches
   between themselves, each lab and each department they belong to, and sees
   only what they may change there.
2. Permissions decided in one place on the server and read — never
   recomputed — by the app.
3. A department does everything a lab does: the four research feeds, a daily
   post in its Discord server, forum threads, and a profile to rank against.

The workspace itself (Overview, feeds, Projects, Saves, Reminders) keeps its
sidebar and its look.

## What the code does today

Checked on 2026-11-12. `FE` is `web/app/src`.

| Area | Today |
|---|---|
| Where settings live | Spread across the Workspace group (Profile, Mylo & you, Lab settings, Department settings, Members) and an "Account" group pinned to the foot (`FE/lib/portal/nav.ts:126-237`). |
| Settings pages | Four flat routes — `/app/account`, `/app/profile`, `/app/members`, `/app/mylo-and-you` — wrapped by `SettingsShell`; which org they act on comes from `?ws=`. |
| Department settings | The nav entry points at `/app/profile?ws=<dept>`, which renders the **personal** profile (`profile-section.tsx:857`). The real page is `/app/department/[id]`, outside the shell, linked without `?ws=`. |
| Department members | `/app/members` in a department scope shows "Pick a lab". |
| Non-managers | A lab or department member who is not a manager has no settings entry at all. |
| Role checks | `canManageLab` is copied into five frontend files and includes `is_lead`; the backend's `user_can_manage_lab` does not. A lead PI who is not owner/admin is shown Discord and announcement cards the API refuses. |
| Department permissions | One predicate, `user_can_edit_dept_profile` (`apps/accounts/permissions.py:124`), gates every department write: profile, members, labs, invitations, billing, Discord, announcements, Mylo's policy. |
| Department rank | None. `DeptMembersView.post` accepts any role, so a department admin can create owners and admins. Still open from `20260920-account-and-lab-management.md` (5a, 5b). |
| Department head | `Department.owner` is a foreign key, not a membership row. |
| Ungated | `AgentPolicyCard` on the department page has no frontend gate. |
| Department profile | `DeptProfile` exists with interests and an API (`departments/<pk>/profile/`); **no screen edits it**. |
| Department research | `target_for_department` exists and is scored for grants, conferences and fellowships — but only while the department's announcements are on (`select_departments`). Papers are never scored. No feed endpoint accepts a department. The one page is Opportunities (department-level calls only). The nav comment saying there is no department target is stale. |
| Likely bug | `mylo/listening.py:306` reads `link.lab`; `DiscordGuildLink` has no such field. |

## Design

### Settings is one area with its context in the path

```text
/app/settings/you/<page>
/app/settings/lab/<slug>/<page>
/app/settings/department/<id>/<page>
```

The context is in the path, not `?ws=`. Managing a department must not depend
on which workspace the reader was last working in, and a link to a settings
page must mean the same thing for everyone who opens it. Entering Settings
from a workspace opens that workspace's context by default.

The old routes (`/app/account`, `/app/profile`, `/app/members`,
`/app/mylo-and-you`, `/app/department/[id]`, `/app/billing`) redirect.

### Layout

- The sidebar foot holds one entry, **Settings**, for everyone. The Workspace
  group loses Profile, Mylo & you, Lab settings, Department settings and
  Account.
- Inside Settings the workspace sidebar is replaced by a **top bar**: a
  context picker (You, then each lab, then each department, with the role
  beside each), and under it the pages of that context as a row of tabs that
  scrolls sideways on a phone.
- The body is a single column of stacked cards at one width. No side rail, no
  two-column cards.
- A page the reader may not open is not listed. A page they may read but not
  change is shown read-only with the reason ("Only the department head can
  change the plan").

### Pages

| Context | Pages |
|---|---|
| **You** | Account (identity, email, password) · Profile & themes · Mylo & you (what Mylo records, questions, chat, what it knows) · Collaboration · Delivery (cadence, linked Discord/Slack/Teams) · Appearance (this device) · Subscription |
| **Lab** | General (profile and interests) · People (roster, roles, invitations) · Projects (who can create, default visibility, what the department sees) · Mylo & servers (Discord/Slack/Teams, channel routes, listening for the server, Mylo's policy) · Announcements · Plan · Your membership (your role, leave the lab) · Transfer & close |
| **Department** | General (profile and interests, the same editor a lab has) · Labs · People · Projects · Mylo & servers · Announcements · Plan · Your membership · Transfer & close |

The People page in Settings is where a roster is **managed**: roles,
invitations, adding and removing labs.

### One Members page in the workspace

The workspace's separate *Labs* and *Members* entries become one **Members**
page. In a department it shows two groups — the department's labs, then its
individual members. In a lab it shows the lab's people. It is a directory;
anyone with the right capability gets a "Manage" link to Settings → People.

### Capabilities

A closed list of capabilities per org, resolved on the server:

`org.profile.edit`, `org.people.view`, `org.people.manage`,
`org.invites.issue`, `org.projects.policy`, `org.projects.oversee`,
`org.servers.manage`, `org.announcements.manage`, `org.mylo.policy`,
`org.billing.manage`, `org.transfer`.

- `apps/accounts/capabilities.py` maps role → capabilities for labs and for
  departments, and is the only place that does. The existing permission
  functions become thin calls into it, so no endpoint changes behaviour in the
  step that introduces it.
- `/api/auth/me/` returns, for each lab and department, the caller's
  `capabilities`. The frontend's five copies of `canManageLab`, and
  `canManageDepartment`, are deleted in favour of `can(org, capability)`.
- Roles are fixed presets for now: owner, admin, member, viewer, and the
  lead PI. **A lead PI holds every capability an admin does**, which ends
  today's split where a lead can edit the profile but not the Discord
  settings.
- The capability list is the seam for later: giving one admin more or less
  than the preset becomes a data change, not a rewrite. It is not built now.
- The Discord gate's manage/edit/read levels map onto capabilities, so the
  bot and the web agree.

### A department works like a lab

Whatever a lab can do with research, a department can do, through the same
code with a department `MatchTarget`:

- **Profile.** The department's profile has the same structure as a lab's
  and is edited the same way, under Settings → General. Feeds rank against
  it. `DeptProfile` already has the fields; only the screen is missing.
- **Feeds.** Papers, Grants, Fellowships and Conferences in the department
  workspace, readable by every department member.
- **Discord.** A daily post in the department's server, the weekly, and the
  grants, fellowships and conferences forum threads — the same routes
  (`updates`, `grants`, `fellowships`, `conferences`, `deadlines`) a lab
  binding has.
- **Opportunities stays.** The page listing calls only a department can take
  on is kept as its own page, beside the four feeds.
- Scoring stops depending on announcements being on. A department is scored
  on the same terms as a lab.
- Fellowships for a department follow the lab rule (ranked, with counts of
  members who may be eligible), not the personal eligibility engine.

### What Mylo records

- A person can stop Mylo recording them **per server** and **per project**,
  beyond today's per-platform switch. These live under You → Mylo & you.
- A lab or department head can turn listening off for a server. **That wins.**
  A member cannot turn it back on, and their own switch for that server is
  shown as off and locked, with the reason.
- Both must be on for anything to be recorded.

## Phases

### Phase 0 — permission fixes (done first, released with the rest)

- `DEPT_ROLE_RANK` and downward-only granting for departments, mirroring
  `LAB_ROLE_RANK`; `DeptMembersView.post` refuses a role the caller cannot
  grant. Department head transfer (`transfer_department_ownership`). This
  completes and retires `20260920-account-and-lab-management.md`.
- A lead PI gets every admin capability, in the backend and the frontend.
- Gate `AgentPolicyCard`.
- Fix `mylo/listening.py:306`.

Validation: `uv run --project web/backend pytest apps/accounts apps/integrations`.

### Phase 1 — capabilities

- `capabilities.py`, the role maps, `me` payload, `can()` on the client.
- A test that walks every org-scoped view and asserts it names a capability.
- Behaviour identical to today except Phase 0's fixes.

### Phase 2 — the Settings area

- Routes, redirects, the top bar and context picker, the stacked layout.
- Move existing cards onto their pages without redesigning them; delete
  `/app/department/[id]` as a standalone page.
- `nav.ts` loses the settings entries; `user-menu.tsx` lists contexts.
- The merged workspace Members page; the department nav loses *Labs*.
- Build the department General page on the existing `DeptProfile` API.
- "Your membership" pages for non-managers.
- nginx: no new signed-out routes, so no new `location` block.

Validation: `next build`, then DOM checks at phone and desktop widths for each
context as owner, admin, member and viewer.

### Phase 3 — the department as a lab

- `select_departments` decoupled from announcements; papers added to the
  department run; entitlement keys in `config/instance.py` matching the
  lab's.
- Department scope in `tools/delivery/views.py` feed endpoints, through the
  lab's serializers.
- Department daily briefing, digest post, PDF and weekly: generalise
  `generate_briefing_for_lab`, `queue_lab_digest`, `compile_report_for_lab`
  and `send_lab_weeklies` to take a lab or a department rather than forking
  them.
- `nav.ts` department Research group beside Opportunities; remove the stale
  comments in `nav.ts`, `workspace.ts`, `scope-guard.tsx`.
- Audit `ops/nightly/manual_all.py` stage order in the same change, as
  `docs/skills/global.md` requires for any pipeline change.
- Record the before/after run cost as an experiment under
  `docs/research/experiments/`.

### Phase 4 — what Mylo records

- Per-server and per-project exclusions beside `ListeningConsent`, checked in
  `apps/ambient/eligibility.py` on arrival.
- The head's off switch on the `Source`, and the locked state on the member's
  page.
- The per-project exclusion also removes the project from attribution
  candidates for that person.

## Interfaces that change

- New `/app/settings/**` routes; six old routes redirect.
- `/api/auth/me/` gains `capabilities` per org.
- `Department.owner` stays, with a matching membership row kept in step.
- Per-server and per-project recording exclusions.
- Department briefing, digest and weekly; department channel routes in use.
- Feed endpoints accept a department.
- `[limits]` / entitlement keys for department feeds.
- `docs/repo-map.md`, `docs/api-contract.md`, `docs/architecture.md`,
  `docs/configuration.md`; delete `20260912-workspace-switcher.md` (shipped,
  now stale) and `20260920-account-and-lab-management.md` once Phase 0 lands.

## Acceptance

- In every context, every role sees exactly the pages its capabilities allow,
  and every API call behind a hidden page is refused for that role.
- A department head changes a department's permissions without visiting a
  workspace.
- A department admin cannot create an owner or another admin.
- A lab member who manages nothing can still open Settings, find their role
  and leave the lab.
- A department with a profile shows four feeds the morning after the run,
  and its server gets a daily post and forum threads as a lab's does.
- A lead PI can do everything an admin can.
- A member cannot switch listening back on in a server its head switched off.
- A department's Members page lists its labs and its people on one page.
- No settings card is wider than the column or sits beside another.

## Exclusions

- No redesign of the workspace sidebar, the switcher or the personal overview.
- No custom roles and no per-admin overrides — presets only for now.
- No institution-level context.
- No change to what a lab's feeds contain.

## Decisions made (2026-11-12)

| # | Decision |
|---|---|
| 12 | The top menu is inside Settings only; the workspace keeps its sidebar. |
| 13 | A lead PI can do everything an admin can. |
| 14 | Role presets only for now; the capability list leaves room for per-admin changes later. |
| 15 | A person can stop recording per server and per project. |
| 16 | A head's off switch wins; a member cannot turn listening back on. |
| 17 | A department ranks against its own profile, structured and edited like a lab's. |
| 18 | A department does everything a lab does: feeds, daily Discord post, forum threads. |
| 19 | Opportunities stays its own page beside the four feeds. |
| 20 | Labs and Members merge into one Members page with two groups. |
| 21 | No early release of Phase 0. |

## Things to hold to while building

- **Two things called "context".** The workspace a person works in and the
  thing they are configuring are different. Anything that still reads `?ws=`
  inside Settings is a bug.
- **Whose control is it.** A member's recording switches live under You; a
  head's live on the org's pages. Each says whose it is and which one wins.
- **The department head is not a member.** Capabilities resolve from
  membership rows, and the head has none. A row is created and kept in step;
  the migration must cover existing departments.
- **A person with many orgs.** The context picker needs grouping and search
  from the start.
- **Appearance is per device.** It is listed under You but stored in the
  browser; the page must say so.
- **Department surfaces and project scope.** A department feed or post is a
  department-width surface under the companion plan. Nothing computed from a
  `lab` or `invite_only` project may appear in it.

## Still open

1. **Where people are managed.** Assumed: the merged Members page is a
   directory, and roles, invitations and removals happen in Settings →
   People. If managing should happen on the Members page itself, Settings →
   People goes away.
2. **Department papers may be noise.** A department's interests are broad.
   Built as asked; worth measuring whether anyone opens the feed.

## Order across both plans

1. Both Phase 0s (holes and permission fixes).
2. Capabilities (this plan, Phase 1) — the project plan's lab settings read
   them.
3. Project visibility Phases 1–3.
4. The Settings area (this plan, Phase 2), which gives the project settings
   their page.
5. Project visibility Phases 4–5; the department as a lab; recording
   controls.

Nothing is released until all of it is done.
