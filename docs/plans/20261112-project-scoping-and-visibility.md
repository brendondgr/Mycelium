# Project Scoping and Visibility — Implementation Plan

**Status:** draft for discussion, nothing built. Open decisions are listed
first; do not start a phase past Phase 0 until they are answered.
**Correlation ID:** `20261112-project-scoping`
**Companion plan:** `20261112-settings-and-workspace-gating.md`

## Objective

Belonging to a lab or department stops exposing its projects. A project is
joined by invitation. Each project carries one visibility scope, and that one
scope decides who can see it in the app **and** where Mylo may mention it or
anything computed from it — in reports, Discord servers, forum threads and
chat.

## What the code does today

Checked on 2026-11-12. Paths are under `web/backend/` unless they start with
`tools/`.

| Area | Today |
|---|---|
| Visibility | No scope field. One boolean, `Project.share_in_lab_reports` (default off), gates the lab's shared surfaces. |
| Who sees a project | `ProjectQuerySet.visible_to` (`apps/research/models.py:45`): members, the personal owner, the lab's PI/owner/admin, and a department's owner/admin for **every project of every lab in the department**. |
| Hole 1 | `LabProjectsView` (`apps/research/views.py:255`) returns every project of a lab — goals and full roster — to any lab member. |
| Hole 2 | `ProjectJoinView` (`views.py:462`) lets any lab member join any lab project, and any department member join any department project by its id, with no approval and no visibility check. |
| Roles | `ProjectMember` has no role. Edit rights come from the scope (personal owner, or the lab's PI/owner/admin). |
| Who creates | Lab projects: PI, owner or admin only. Department projects: owner or admin — and then nobody can edit, archive or invite, because `user_can_edit_project` returns False for them. |
| Invitations | `ProjectInvitation`, existing accounts only. No request-to-join. |
| Lab surfaces | Daily post, PDF, weekly, alerts, announcements' project teams, ambient lab changes all read `share_in_lab_reports` through `report_projects_for_lab` (`tools/delivery/briefing.py:304`). |
| Mylo chat | Output width is `person` / `project` / `lab` / `department` (`tools/agent/functions/common.py:35`); a shared lab project is `lab`, everything else `project`. |
| Discord servers | A server holds bindings; each binding is one lab or one department. One server can hold several, and a lab can be bound into its department's server. Lab posts go to the lab's **oldest** live binding with the route. |

Leaks that exist today, beyond the two holes:

1. **Knowledge projection.** A lab project's concepts are minted in the lab's
   scope whether or not it is shared (`apps/knowledge/projection.py:208`), so
   they feed the lab's coverage and the "team fit" line on grant cards.
2. **Ambient visibility.** `reading._visibility` (`apps/ambient/reading.py:124`)
   marks an observation `lab` when the project belongs to the server's lab,
   without checking sharing. A member talking about their unshared project in
   the lab server produces lab-visible evidence.
3. **Ambient editing.** `editing.alternatives` lists every active lab project by
   name to a project editor choosing "this was a different project".
4. **Member fit.** For a lab project, every lab member is a candidate for "who
   is this for?" (`tools/recommendation/member_fit.py:515`,
   `tools/delivery/views.py:1263`).
5. **Stored alerts.** `open_alerts` does not re-check sharing when read, so an
   alert outlives a project being un-shared.
6. **Primary binding.** A lab bound into a department's server may have that
   binding as its primary one, so the lab's daily post — shared projects
   included — lands in the department's server.
7. **The hidden count.** "N private projects not shown" in the lab's Discord
   post tells the server that private projects exist.

## The model

### One field

`Project.visibility`, replacing `share_in_lab_reports`:

| Value | Seen by | Allowed on |
|---|---|---|
| `invite_only` (default) | Members only | every project |
| `lab` | The owning lab's members | lab projects |
| `department` | The lab's members and its department's effective members | lab projects whose lab is in a department; department projects |
| `public` | Any signed-in, verified account on the instance | every project |

Migration: `share_in_lab_reports=True` becomes `lab`; everything else becomes
`invite_only`. Department projects become `invite_only` (they have no shared
surface today). The boolean is dropped in the same release.

A lab has at most one department (`Lab.department` is a single foreign key), so
"the lab's department" is never ambiguous.

### Three questions, one answer each

The scope answers three questions that the code currently answers in different
places:

1. **Can this person see the project exists?** Member, or inside the scope.
2. **Is it one of this person's projects?** Only if they are a member.
   Visibility never puts a project in someone's project list, personal report
   or attention shares.
3. **May this surface mention it?** Only if the surface's audience is inside
   the scope (see "Surfaces").

One module — `apps/research/visibility.py` — holds all three:
`can_see(user, project)`, `is_participant(user, project)`,
`audience(project)` and `may_surface(project, place)`. Every caller listed in
"What the code does today" is moved onto it. `visible_to` stays as the queryset
form of `can_see`.

### Membership

- Membership comes from an accepted `ProjectInvitation`, or from an approved
  join request. Self-join is removed.
- `ProjectMember.role`: `owner`, `editor`, `member`. The creator is the owner.
  Owner and editors invite, remove, edit and archive. Only the owner changes
  visibility or hands over ownership.
- **Request to join** (`ProjectJoinRequest`: project, user, note, state,
  decided_by, decided_at) is possible only when the project is not
  `invite_only` and the requester is inside its scope. Owner and editors
  decide. One open request per person per project; a refusal is not announced
  to the lab.
- A scoped project is listed in a **directory** ("Projects in this lab" /
  "…in this department"), separate from "My projects". A directory row shows
  name, one-line focus, owner and member count — not goals, state, feed,
  files or the roster.

### Oversight

- **Lab projects.** The lab's PI and owner keep a ledger row for every project
  in the lab (name, owner, member count, visibility) and may take ownership of
  one, with an audit entry and a notice to its members. They do not see its
  contents unless they are members. Lab admins lose blanket access.
- **Department heads** lose the cascade into lab projects. They see a lab's
  project only when its visibility is `department` or `public`, or they are
  invited.
- **Department projects** get the same ledger for the department head.
- **A project nobody but its members may know about** is a personal project
  (`scope_user`) with invited members. That is the answer to "if the owner
  wants nobody to see it, nobody sees it anywhere".

### Surfaces

Every place Mylo can speak has an audience width. A project — its name, state,
team, alerts, developments, and every item scored for the project target — may
appear only where `audience(project)` is at least as wide as the place.

| Place | Width |
|---|---|
| A DM, a personal report, a member's own web view | member |
| A lab's web surfaces (overview, lab report, lab weekly) | lab |
| A Discord server holding exactly one binding, a lab | lab |
| A Discord server holding a department binding, or labs of one department | department |
| A Discord server holding labs of different departments, or of none | public |
| A department's web surfaces | department |

The width of a server is decided by **everything bound in it**, not by which
binding a post travels on. That closes leak 6 and is the rule behind the
example in the brief: a `lab` project never reaches the department's server,
reaches the lab's own server if there is one, and otherwise reaches only its
members' DMs.

Members' personal reports are unchanged: a member always gets their own
projects, whatever the scope.

## Phases

### Phase 0 — close the holes (ship alone, first)

- `LabProjectsView` returns only what `visible_to` allows.
- `ProjectJoinView` refuses unless the caller already passes `visible_to`;
  removed outright in Phase 2.
- `open_alerts` re-checks sharing at read.
- Make department projects editable by the department's owner/admin, so they
  are not stranded while the rest is built.

Validation: `uv run --project web/backend pytest apps/research tools/delivery/tests/test_project_alerts.py`.

### Phase 1 — the field and the one module

- Migration adding `visibility`, backfilled from `share_in_lab_reports`;
  `ProjectMember.role` backfilled (`owner` for the creator where known, else
  the lab's PI).
- `apps/research/visibility.py`; `visible_to` rewritten on it; the oversight
  ledger endpoint.
- Every reader of `share_in_lab_reports` switched: `report_projects_for_lab`,
  `hidden_lab_projects`, `_project_teams`, `weekly_changes`, ambient
  `candidate_projects` / `lab_changes` / `changes_between`, agent
  `visible_projects` / `project_output`, files `access.py`, `smoke_reports`.
- An AST test that fails if `share_in_lab_reports` or a raw
  `scope_lab=…` project query appears outside the module.

### Phase 2 — invitations, requests, directory

- `ProjectJoinRequest`, its endpoints (both slash forms), bell notifications.
- Lab and department directory endpoints; delete `ProjectJoinView`.
- Project creation opened per the lab's policy (see decision 3); the creator
  becomes owner.
- Frontend: "My projects" vs directory in `projects-list-section.tsx`; scope
  picker and its consequences spelled out in `create-project-wizard.tsx` and
  `project-editor-modal.tsx`; request/approve in `project-team-card.tsx`.

### Phase 3 — Mylo

- `may_surface(project, place)` with `place` built from
  `resolve.place_for` plus the server-width rule; used by `lab_digest`,
  `daily_report`, `weekly`, `alert_report`, `discord_announcements`,
  `announce._project_teams`, and the agent's `audience_allows`.
- Department posts may name `department`/`public` projects (today
  `align` returns none for departments).
- Agent widths gain `public`; `within_audience` checks scope, not just
  ownership.
- Remove the hidden-projects count from Discord posts; keep it on the
  managers' web view.
- Extend `smoke_reports` with one check per width.

### Phase 4 — the indirect paths

- Knowledge projection: a project's concepts take the project's scope —
  personal for `invite_only`, lab for `lab`, and so on. Re-project on a
  visibility change.
- Ambient: `Visibility` gains `project`; `_visibility` returns it for an
  `invite_only` project wherever it was said. `editing.alternatives` lists
  only projects the editor can see.
- Member fit: candidates for a project are its members, plus the scope's
  people only when the scope includes them.
- Collaborator search from a project: confirm nothing about an `invite_only`
  project reaches a candidate or the search log beyond the coarse pointers.

### Phase 5 — changing scope, and leaving

- **Narrowing** takes effect on everything not yet sent. Stored rows are
  re-checked at read. Open announcement threads are edited on the next update
  to drop the project's team. The editor is told plainly that posts, PDFs and
  DMs already delivered stay where they are.
- **Widening** is the owner's alone, shows who will newly see what, and
  notifies every member. It applies from the next run; nothing historical is
  back-posted.
- Leaving or being removed from a lab ends membership in that lab's projects,
  unless the project's owner keeps the person on as an outside collaborator.
- An owner who leaves or deletes their account: ownership passes to an editor,
  else to the lab's PI (the department head for a department project).

## Interfaces that change

- `Project.visibility`, `ProjectMember.role`, `ProjectJoinRequest`; removal of
  `share_in_lab_reports`.
- `GET /api/projects/lab/<slug>/` narrows; new directory, ledger and
  join-request routes; `POST /api/projects/<id>/join/` removed.
- `ProjectSerializer` gains `visibility`, `my_role`, `can_request`; a new
  directory serializer with the reduced fields.
- `docs/api-contract.md`, `docs/repo-map.md`, `docs/discord-integration.md`,
  `docs/architecture.md` (the audience rule).

## Acceptance

- A lab member with no invitations sees no `invite_only` project by any
  route: list, directory, lab endpoint, id guess, search, agent, files,
  ambient editing.
- For each visibility value, a fixture project's name appears in exactly the
  places the surface table allows, checked across the daily post, PDF,
  weekly, alerts, announcement threads and agent chat.
- A lab bound into its department's server posts no `lab` project there.
- Narrowing a project removes it from the next run's lab post and from every
  read of stored alerts and changes.

## Exclusions

- No anonymous (signed-out) project pages.
- No per-project Discord channels.
- No change to how projects are scored, capped or billed.
- Ranking is untouched: every project is still scored nightly whatever its
  scope; only where results may be shown changes.

## Decisions needed

1. **What "Public" means.** Recommended: any verified account on this
   instance, in a directory, with no signed-out page. The alternative — a
   public web page — is a new surface with its own review.
2. **Lab PI oversight of `invite_only` lab projects.** Recommended: the ledger
   row and take-over described above, with true secrecy reserved for personal
   projects. The alternative — the PI cannot even see that it exists — leaves
   projects that count against the lab's cap and can be orphaned with no one
   able to act.
3. **Who may create a lab project.** The brief says the creator "or
   individuals within the lab". Recommended: a lab setting, managers only or
   any member, default any member — with the cap still the lab's.
4. **Department heads lose sight of their labs' projects by default.** This
   removes access that exists today. Confirm.
5. **Outside collaborators.** May a lab project invite someone who is not in
   the lab? Recommended: yes, by the owner, shown as "outside the lab" on the
   team card; they never gain lab access.
6. **Lab servers contain non-members.** A lab's Discord server can hold
   guests, and Mylo cannot see who reads a channel. `lab` scope therefore
   means "the lab's registered server", not "verified lab members".
   Recommended: accept this, and say it where the scope is chosen.

## Reasoning gaps to settle

- **Items "related to" a restricted project.** What can be enforced is
  provenance: anything scored for the project target follows the project's
  scope. What cannot be enforced is inference — the same grant can reach the
  lab's feed through the lab's own profile, and a reader may guess why. If a
  PI writes a secret project into the lab profile, the lab's feed will show
  it. The scope picker should say so.
- **A person's own profile carries their projects.** Conversation about an
  `invite_only` project can still, with the person's yes, become a theme in
  their personal profile, and "who should look" on a lab announcement is
  built from personal profiles. The person's name beside a call is then a
  signal. Decide whether a theme learned from an `invite_only` project is
  kept out of member fit.
- **Scope and membership are independent.** A `public` project is still
  joined by invitation or approved request; an `invite_only` project can have
  forty members. The interface must not present scope as "who is on it".
- **Speaking is not scoping.** Someone who discusses an `invite_only` project
  in the lab's server has told the room. Mylo must not widen it, but cannot
  un-say it.
- **Operators see everything.** Platform staff and whoever runs the database
  can read every project. "Nobody sees it" means nobody through the product.
- **Saves and reminders.** An item saved or a reminder set from inside a
  project, at lab scope, announces the item in the lab's channel. Decide
  whether an action taken inside an `invite_only` project may be shared wider
  than the project at all.
- **Lab moves.** When a lab leaves or joins a department, `department`
  projects change audience overnight. Recommended: on leaving, they fall back
  to `lab` and the owner is told.
