# Project Scoping and Visibility — Implementation Plan

**Status:** decisions answered on 2026-11-12 and folded in; nothing built.
Three points are still open (last section). Nothing ships ahead of the rest:
the phases are an order of work inside one build, not separate releases.
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
| `invite_only` (default) | Members, plus the overseers named under "Oversight" | every project |
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

The lab's PI is the lab's admin, and a department head sponsors its labs.
Both see everything, whatever a project's scope:

- **Lab projects.** The lab's PI, owner and admins can open every project in
  the lab, as they can today, and can take ownership of one (audited, members
  told).
- **Department heads** can open every project of every lab in the department,
  and every department project, as they can today. This is adjustable per lab:
  a lab setting, *What the department sees of this lab's projects* —
  **Everything** (default) or **Names only** (name, owner, member count,
  scope). See open point 1 for who holds that switch.
- **Seeing is not belonging.** An overseer who is not a member does not get
  the project in "My projects", their personal report, or their attention
  shares, and oversight never widens where Mylo may mention it.
- **A project nobody but its members may know about** is a personal project
  (`scope_user`) with invited members. `invite_only` on a lab project means
  "not the other lab members", not "not the PI". The scope picker says so.

### Outside collaborators

A lab project's owner may invite someone who is not in the lab. They are
shown as "outside the lab" on the team card, see that project only, and gain
nothing else in the lab: no feeds, roster, directory or server role.

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

### Phase 0 — close the holes (done first, released with the rest)

- `LabProjectsView` returns only what `visible_to` allows.
- `ProjectJoinView` is removed; nothing replaces it until Phase 2's requests.
- `open_alerts` re-checks sharing at read.
- Make department projects editable by the department's owner/admin, so they
  are not stranded while the rest is built.

Validation: `uv run --project web/backend pytest apps/research tools/delivery/tests/test_project_alerts.py`.

### Phase 1 — the field and the one module

- Migration adding `visibility`, backfilled from `share_in_lab_reports`;
  `ProjectMember.role` backfilled (`owner` for the creator where known, else
  the lab's PI).
- `apps/research/visibility.py`; `visible_to` rewritten on it, keeping the
  overseers; the per-lab *What the department sees* setting and its
  names-only serializer.
- Every reader of `share_in_lab_reports` switched: `report_projects_for_lab`,
  `hidden_lab_projects`, `_project_teams`, `weekly_changes`, ambient
  `candidate_projects` / `lab_changes` / `changes_between`, agent
  `visible_projects` / `project_output`, files `access.py`, `smoke_reports`.
- An AST test that fails if `share_in_lab_reports` or a raw
  `scope_lab=…` project query appears outside the module.

### Phase 2 — invitations, requests, directory

- `ProjectJoinRequest`, its endpoints (both slash forms), bell notifications.
- Lab and department directory endpoints.
- Project creation follows a lab setting, *Who can create projects*: any
  member (default) or managers only. The creator becomes owner; the cap is
  still the lab's. Departments get the same setting.
- Inviting an outside collaborator onto a lab project.
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
- What a project learns stays with the project. Developments and themes
  learned from an `invite_only` project are kept on the project and are not
  used to put a person's name in "who should look" on a lab or department
  announcement (open point 2).
- Saves and reminders made inside an `invite_only` project stay there. A
  deadline reminder goes to the person directly, in a DM or the bell, and is
  never announced in a lab or department channel. Sharing at lab scope is not
  offered from inside such a project.
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
- Leaving or being removed from a lab ends membership in that lab's projects
  automatically. The project's owner may invite the person back as an outside
  collaborator.
- An owner who leaves or deletes their account: ownership passes to an editor,
  else to the lab's PI (the department head for a department project).
- A lab that leaves its department: its `department` projects fall back to
  `lab`, the owners are told, and the department loses access to them. Before
  leaving, a project may instead be **transferred** to the department — the
  project's owner offers, the department head accepts, and it becomes a
  department project with its members kept.

## Interfaces that change

- `Project.visibility`, `ProjectMember.role`, `ProjectJoinRequest`; removal of
  `share_in_lab_reports`.
- `GET /api/projects/lab/<slug>/` narrows; new directory, join-request and
  transfer routes; `POST /api/projects/<id>/join/` removed.
- Lab and department settings: *Who can create projects*; lab setting *What
  the department sees of this lab's projects*.
- `ProjectSerializer` gains `visibility`, `my_role`, `can_request`; a new
  directory serializer with the reduced fields.
- `docs/api-contract.md`, `docs/repo-map.md`, `docs/discord-integration.md`,
  `docs/architecture.md` (the audience rule).

## Acceptance

- An ordinary lab member with no invitations sees no `invite_only` project by
  any route: list, directory, lab endpoint, id guess, search, agent, files,
  ambient editing.
- For each visibility value, a fixture project's name appears in exactly the
  places the surface table allows, checked across the daily post, PDF,
  weekly, alerts, announcement threads and agent chat.
- A lab bound into its department's server posts no `lab` project there.
- The lab's PI opens every project in the lab; a department head opens every
  project of a lab set to *Everything* and sees names only for a lab set to
  *Names only*. Neither finds those projects in their own report.
- A reminder set inside an `invite_only` project reaches its author and no
  channel.
- Narrowing a project removes it from the next run's lab post and from every
  read of stored alerts and changes.

## Exclusions

- No anonymous (signed-out) project pages.
- No per-project Discord channels.
- No change to how projects are scored, capped or billed.
- Ranking is untouched: every project is still scored nightly whatever its
  scope; only where results may be shown changes.

## Decisions made (2026-11-12)

| # | Decision |
|---|---|
| 1 | `public` means any verified account on this instance, in a directory. No signed-out page. |
| 2 | The lab's PI and admins see every project in the lab. |
| 3 | Who can create a lab project is a lab setting: any member (default) or managers only. |
| 4 | Department heads see every project of their labs by default, adjustable per lab down to names only. |
| 5 | Outside collaborators are allowed on a lab project and gain no lab access. |
| 6 | `lab` scope in Discord means the lab's registered server, guests included; the scope picker says so. |
| 7 | Not decided by the maintainer; this plan keeps what a project learns with the project (open point 2). |
| 8 | Reminders from inside an `invite_only` project go to the person, never a lab channel. |
| 9 | Leaving a lab ends project membership; the owner may re-invite as an outside collaborator. |
| 10 | A lab leaving its department: `department` projects fall back to `lab`; a project may be transferred to the department first. |
| 11 | The hidden-projects count leaves Discord and stays on the managers' web view. |
| 21 | No early release of Phase 0. |

## Things the product must say plainly

- **Items "related to" a restricted project.** What is enforced is
  provenance: anything scored for the project target follows the project's
  scope. Inference is not enforceable — the same grant can reach the lab's
  feed through the lab's own profile. If a PI writes a secret project into
  the lab profile, the lab's feed will show it.
- **Scope and membership are independent.** A `public` project is still
  joined by invitation or approved request.
- **Speaking is not scoping.** Someone who discusses an `invite_only` project
  in the lab's server has told the room. Mylo must not widen it, but cannot
  un-say it.
- **Operators see everything.** Platform staff and whoever runs the database
  can read every project.

## Still open

1. **Who holds the *What the department sees* switch.** This plan assumes the
   lab's PI sets it. If the department head should hold it instead, it is a
   department setting per lab and a PI cannot narrow it.
2. **Decision 7.** Assumed: themes learned from an `invite_only` project stay
   on the project and never name a person in a wider announcement. The cost
   is that a well-matched person may not be flagged for a call.
3. **Lab admins.** Assumed: admins see every lab project alongside the PI, as
   today, since the PI is described as the lab's admin.
