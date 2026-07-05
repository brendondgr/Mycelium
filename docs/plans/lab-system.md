# Lab System Implementation Plan

**Status:** In progress · **Session date:** 2026-07-05 · **Correlation ID:** `20260705-lab-system`

## Objective

Let Mycelium users create and run **labs** as shared research workspaces: an
existing user can create a lab (becoming its PI), invite people by email or
username, and the lab can declare a collective purpose/goals and organize work
into projects (focus areas). The lab workspace mirrors the individual account
interface, plus the already-built **Lab** area. Invitations surface in the
in-app notifications panel with **Accept / Reject / Ignore**.

Grounded in the canonical direction: labs are first-class research entities
(`docs/purpose.md`), object-level permissions and audit logging are mandatory
(`docs/skills/global.md`), and the collective interest surface already exists as
`LabProfile` (`docs/architecture.md`).

## Decisions (confirmed with user 2026-07-05)

1. **Header:** do **not** restructure. Keep the lab switcher and account menu.
   The one change to header elements is **activating the existing disabled
   notification bell** so invitations can surface — this is required by the
   invitations requirement, not a layout change. The "Remove Personal Workspace
   element" / "Left logo · Center search · Right notifications+theme" item from
   the brief is therefore **out of scope** per the user's direct instruction.
2. **Lab list behavior:** clicking a lab in the Lab-tab list **switches the
   active workspace** (sets `labScope`); the header switcher stays in sync.
3. **Invitations:** support **pending email invites** — a PI may invite an email
   with no account yet; the invitation is claimed and surfaced after that person
   signs up. Username invites require an existing account.
4. **Brand label:** the brief's "my ceiling" is a phonetic rendering of
   **Mycelium**; the wordmark stays "Mycelium" (confirmed in `portal-header.tsx`).

## Assumptions

- Adding a member to a lab (via accepted invite or lab creation) creates the
  `LabMembership` row; **seat/billing enforcement is out of scope** for this
  change (noted as follow-up). Every new lab still gets a `LAB` subscription +
  founding seat to preserve the "every account has ≥1 seat" invariant, by
  reusing the existing `provision_workspace` lab branch.
- **Ignore** dismisses the invitation from the invitee's feed
  (`status = ignored`, no membership, inviter not notified). Distinct from
  **Reject** (`status = rejected`), which is a definitive decline.
- The lab "Purpose & Goals" editor reuses the existing `LabProfile` +
  `LabProfileView` (GET/PUT). No LLM synthesis for labs in this pass (manual
  editor mirroring the individual profile form); LLM assist is a follow-up.
- Projects stay basic: name + optional goals JSON, scoped to a lab. No project
  detail/workflow beyond create + list.

## Ordered implementation phases

### Phase 1 — Backend: lab creation for existing users
- Factor the `lab` branch of `apps/billing/services.provision_workspace` into a
  reusable `create_lab_workspace(user, name, institution="")` and call it from
  both `provision_workspace` and the new endpoint (no behavior drift).
- Turn `MyLabsView` into list **+ create** (`POST /api/auth/labs/`): authed user
  submits `{name, institution?}`; creates the lab, makes them OWNER + `is_lead`
  (PI), records an audit event, returns the new lab in `MyLab` shape.
- Tests: create lab → membership OWNER + is_lead, LabProfile auto-created,
  appears in `GET /api/auth/labs/`; blank name rejected; unauthenticated 403.

### Phase 2 — Backend: invitations (with pending-email support)
- New model `LabInvitation` (accounts): `lab`, `inviter`, `invitee` (nullable),
  `invited_email`, `invited_username`, `role`, `status`
  (pending/accepted/rejected/ignored/cancelled), `created_at`, `responded_at`.
  Partial-unique on pending `(lab, invitee)` and pending `(lab, invited_email)`;
  invariant: at least one of `invitee` / `invited_email`.
- Resolution service: email → match existing user (case-insensitive) else keep
  as pending email; username → must match an existing user else clear error.
- `claim_pending_invitations(user)` called from `register_view` after user
  creation: attach `invitee` to pending email invites matching the new user's
  email (does **not** auto-accept).
- Permission helper `user_can_invite_to_lab` = lead PI or owner/admin.
- Endpoints:
  - `POST /api/auth/labs/<slug>/invitations/` — manager invites `{identifier, role?}`.
  - `GET  /api/auth/labs/<slug>/invitations/` — manager lists the lab's invites.
  - `GET  /api/auth/invitations/` — caller's **pending** invitations (notifications feed).
  - `POST /api/auth/invitations/<id>/respond/` — invitee `{action: accept|reject|ignore}`.
    Accept creates `LabMembership` (idempotent) + audit; reject/ignore set status.
- Tests: invite by username (existing) and email (existing + pending); pending
  claimed on signup; accept adds membership; reject/ignore add none; only
  managers invite; only the invitee responds; duplicate-pending guarded.

### Phase 3 — Backend: projects within a lab
- Make project listing also creatable: `POST /api/projects/` with
  `{name, lab, goals?}`; permission = `user_can_manage_lab` for lab scope
  (personal scope allowed for self). New write serializer; model already
  enforces exactly-one scope.
- Tests: manager creates a lab project; non-manager rejected; project appears in
  `visible_to`; missing name rejected.

### Phase 4 — Frontend: data layer
- Types: `MyInvitation`, `LabInvitation`, create-lab / create-project / invite
  payloads. Client fns + TanStack hooks: `useMyInvitations`,
  `useRespondInvitation`, `useCreateLab`, `useInviteToLab`, `useCreateProject`,
  `useLabProfile`/`useUpdateLabProfile`. CSRF-aware POSTs through the proxy.

### Phase 5 — Frontend: notifications panel (activate the bell)
- Replace the disabled `NotificationBell` with a functional Radix popover:
  pending-invitation rows with Accept / Reject / Ignore, a count badge, empty
  state, loading/error states, keyboard + `aria` support. Header layout is
  otherwise unchanged.

### Phase 6 — Frontend: Labs list under the Lab tab
- Replace the sidebar **Lab** group (Members + Reports) with a single **Labs**
  entry → `/app/labs`: cards for each of the caller's labs (name, role, PI
  badge, department), a **Create lab** action, and — for a manager-selected lab
  — invite control, member roster (reuse `members-section`), Purpose & Goals
  editor (LabProfile), and projects list + create. Clicking a lab card switches
  the active workspace (`setLabScope`) in sync with the header switcher.
- Keep the member roster reachable (embedded in the lab detail); retire the
  standalone Members/Reports nav items.

### Phase 7 — Lab workspace mirroring
- When `labScope` is active, the **Profile** section renders the lab Purpose &
  Goals editor (vs. the user profile). Projects/Members already accept a lab
  slug. Keep this minimal — the lab surfaces reuse existing section components.

## Public interfaces / routes / schemas that change

- **Backend:** new `LabInvitation` model + migration; `create_lab_workspace`
  service; `claim_pending_invitations`; `user_can_invite_to_lab` permission;
  new/extended endpoints under `/api/auth/labs/…`, `/api/auth/invitations/…`,
  and `POST /api/projects/`. Update `docs/api-contract.md`.
- **Frontend:** `/app/labs` route + `LabsSection`; functional notifications
  popover; new hooks/client/types; sidebar nav change.

## Validation & acceptance criteria

- Backend: `uv run --directory web/backend python -m pytest` green (new tests
  included); `manage.py makemigrations --check` clean; `migrate` applies on
  SQLite.
- Frontend: `npm run build` (or `tsc --noEmit`) + lint clean; notifications
  popover and Labs page verified in a running app where feasible.
- Security: every new endpoint enforces auth + object-level permission (manager
  to invite, invitee to respond, member to read) and writes an audit event for
  create-lab, invite, and invite-response.
- End-to-end: user A creates a lab → invites user B by username and an unknown
  email → B sees the invite in notifications → accepts → B is a lab member →
  new user signs up with the invited email → sees the pending invite.

## Explicit exclusions

- No header restructuring / Personal-Workspace removal (per user decision).
- No seat/billing enforcement on invited members; no per-tier PI cap checks.
- No LLM synthesis for lab goals; no project detail/workflow beyond create+list.
- No email delivery for invitations (in-app notifications only).

## Execution & git

- Work on branch `feature/lab-system` off local `main`; commit each phase with a
  concise, human-authored message (no AI attribution). Update `docs/changelog.md`
  under correlation ID `20260705-lab-system`. Merge into `main` locally at the
  end; **do not push**. Leave the pre-existing uncommitted `.env.example`,
  `web/art/`, and `web/app/tmp-root-stale/` untouched.
