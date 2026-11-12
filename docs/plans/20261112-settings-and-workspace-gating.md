# Settings, Workspace Gating and Department Research — Implementation Plan

**Status:** draft for discussion, nothing built. Open decisions are listed at
the end; Phases 0 and 1 do not depend on them.
**Correlation ID:** `20261112-settings-gating`
**Companion plan:** `20261112-project-scoping-and-visibility.md`

## Objective

1. One **Settings** area at the foot of the sidebar, where a person switches
   between themselves, each lab and each department they belong to, and sees
   only what they may change there.
2. Permissions that are finer than "manager or not", decided in one place on
   the server and read — never recomputed — by the app.
3. A department gets the same four research feeds a lab has.

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
| **Lab** | General (profile and interests) · People (roster, roles, invitations) · Projects (who may create, default visibility, the oversight ledger) · Mylo & servers (Discord/Slack/Teams, channel routes, listening for the server, Mylo's policy) · Announcements · Plan · Your membership (your role, leave the lab) · Transfer & close |
| **Department** | General (profile and interests — the missing editor) · Labs · People · Projects · Mylo & servers · Announcements · Plan · Your membership · Transfer & close |

The People page in Settings is where a roster is **managed**. Seeing who is in
a lab stays in the workspace as a read-only directory.

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
- A role is a preset. An owner may **add or remove individual capabilities**
  for one admin (`LabMembership.capability_overrides`,
  `DeptMembership.capability_overrides`), which is what "several admins with
  different permissions" needs. Nobody can grant a capability they do not
  hold; `org.transfer` and `org.billing.manage` can never be granted beyond
  the owner unless the owner does it; every change is audited.
- The Discord gate's manage/edit/read levels map onto capabilities, so the
  bot and the web agree.

### Department research

A department scope offers Papers, Grants, Fellowships and Conferences, through
the same serializers as a lab with a department `MatchTarget`.

- Scoring stops depending on announcements: a department is scored when it is
  entitled and has a profile to rank against.
- Papers are added to the department run.
- Feed endpoints take a department the way they take a lab.
- The existing Opportunities page becomes a filter on the grants, fellowships
  and conferences feeds — "For the department itself" — rather than a
  separate page.
- Fellowships for a department follow the lab rule (ranked, with counts of
  members who may be eligible), not the personal eligibility engine.

## Phases

### Phase 0 — permission fixes (ship alone, first)

- `DEPT_ROLE_RANK` and downward-only granting for departments, mirroring
  `LAB_ROLE_RANK`; `DeptMembersView.post` refuses a role the caller cannot
  grant. Department head transfer (`transfer_department_ownership`). This
  completes and retires `20260920-account-and-lab-management.md`.
- Decide `is_lead` once (see decision 2) and make frontend and backend agree.
- Gate `AgentPolicyCard`.
- Fix `mylo/listening.py:306`.

Validation: `uv run --project web/backend pytest apps/accounts apps/integrations`.

### Phase 1 — capabilities

- `capabilities.py`, the role maps, `me` payload, `can()` on the client.
- A test that walks every org-scoped view and asserts it names a capability.
- No override UI yet; behaviour identical to today except Phase 0's fixes.

### Phase 2 — the Settings area

- Routes, redirects, the top bar and context picker, the stacked layout.
- Move existing cards onto their pages without redesigning them; delete
  `/app/department/[id]` as a standalone page.
- `nav.ts` loses the settings entries; `user-menu.tsx` lists contexts.
- Build the department General page on the existing `DeptProfile` API.
- "Your membership" pages for non-managers.
- nginx: no new signed-out routes, so no new `location` block.

Validation: `next build`, then DOM checks at phone and desktop widths for each
context as owner, admin, member and viewer.

### Phase 3 — per-admin overrides

- The two `capability_overrides` fields, the grant rules, the audit entries.
- A "Permissions" control on a person's row in People.

### Phase 4 — department research

- `select_departments` decoupled from announcements; papers added;
  entitlement and nightly-budget keys in `config/instance.py`.
- Department scope in `tools/delivery/views.py` feed endpoints.
- `nav.ts` department Research group; remove the stale comments in `nav.ts`,
  `workspace.ts`, `scope-guard.tsx`.
- Audit `ops/nightly/manual_all.py` stage order in the same change, as
  `docs/skills/global.md` requires for any pipeline change.
- Record the before/after run cost as an experiment under
  `docs/research/experiments/`.

### Phase 5 — what Mylo records, per person

Depends on decision 4. Extends `ListeningConsent` beyond per-platform on/off.

## Interfaces that change

- New `/app/settings/**` routes; six old routes redirect.
- `/api/auth/me/` gains `capabilities` per org.
- `LabMembership` / `DeptMembership` gain `capability_overrides`;
  `Department.owner` stays, with a matching membership row kept in step.
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
- A department with a profile shows four feeds the morning after the run.
- No settings card is wider than the column or sits beside another.

## Exclusions

- No redesign of the workspace sidebar, the switcher or the personal overview.
- No custom, named roles — presets plus overrides only.
- No institution-level context.
- No change to what a lab's feeds contain.

## Decisions needed

1. **How far the top menu goes.** Recommended: top bar inside Settings only;
   the workspace keeps its sidebar, which was just reworked to stay open. The
   alternative replaces the sidebar everywhere and is a much larger change.
2. **What a lead PI is.** `is_lead` currently grants profile, invitations and
   billing but not Discord, announcements or member management. Recommended:
   a lead PI holds every capability an admin does.
3. **How fine the permissions go.** Recommended: presets plus per-admin
   overrides from the closed list above. The alternative — fixed roles only —
   is simpler but does not give "admins with different permissions".
4. **What "prevent certain information from being recorded" covers.** Today a
   person can switch listening off per platform, mute questions, and delete
   what was observed. Candidates: per server, per lab, per project ("never
   record anything about this project"), and per kind of understanding.
   Recommended: per server and per project.
5. **What a department ranks against.** Its own written profile, or its labs
   combined when it has written none? No code writes the combined vector
   today. Recommended: the department's own profile only, with the General
   page saying plainly that feeds are empty until it is filled in.
6. **Who pays for department feeds.** They add one target per department to
   every nightly run, including model write-ups. Recommended: part of the
   department plan, off for a department with no profile.

## Reasoning gaps to settle

- **Two things called "context".** The workspace a person works in and the
  thing they are configuring are different, and today one URL parameter
  carries both. This plan separates them; anything that still reads `?ws=`
  inside Settings is a bug.
- **A member's own settings inside an org.** "Do not record me in this
  department's server" is the person's choice, not the department's. It
  belongs under You → Mylo & you, listed per org — not on the department's
  pages where a head could appear to control it.
- **A head's settings about members.** The reverse also holds: a lab can turn
  listening off for its server, and no member can turn it back on. Each
  control must say whose it is and which one wins.
- **The department head is not a member.** Capabilities resolve from
  membership rows, and the head has none. Either the foreign key is treated as
  an implicit owner row everywhere, or a row is created and kept in step.
  This plan chooses the second; the migration must cover existing departments.
- **Overrides and rank.** If an admin can be granted `org.people.manage`,
  they can act on other admins unless rank still applies. Rank stays: a
  capability says what you may do, rank says to whom.
- **A person with many orgs.** Someone in two departments and five labs gets a
  long context picker. It needs grouping and search from the start.
- **Appearance is per device, not per person.** It is listed under You but is
  stored in the browser; the page must say so, or people will expect it to
  follow them.
- **Department feeds and project scope.** A department feed is a
  department-width surface under the companion plan. Nothing computed from a
  `lab` or `invite_only` project may appear in it, and "labs that could lead"
  must not be derived from such projects either.
- **Department papers may be noise.** A department's interests are broad, and
  per-theme slates of 25 papers across many themes may be a feed nobody
  reads. Build it as asked, and measure whether anyone opens it.

## Order across both plans

1. Both Phase 0s (holes and permission fixes).
2. Capabilities (this plan, Phase 1) — the project plan's lab policy and
   oversight ledger read them.
3. Project visibility Phases 1–3.
4. The Settings area (this plan, Phases 2–3), which gives the project policy
   its page.
5. Project visibility Phases 4–5; department research; recording controls.
