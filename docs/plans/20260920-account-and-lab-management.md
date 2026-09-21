# Account and lab management: invites, affiliation, removal, ownership

Four requests from the product owner, 2026-09-20. Two are smaller than they
look because the backend already exists; one is larger than it looks because it
cannot be done safely without closing a privilege-escalation hole first.

## Objective

Make a lab's roster governable by the people who run it: an invited person is
never silently stranded outside the lab they were invited to, a PI or admin can
remove someone, and the person who stood the lab up can hand it to the person
who actually leads it.

## What already exists (verified against the running system, not assumed)

| Request | Status |
|---|---|
| 1 — pending invite at sign-up | **Not built.** `register_view` redeems an invite only when an `invite_token` is posted ([views.py:256](../../web/backend/apps/accounts/views.py:256)). `claim_pending_invitations` covers the *legacy* `LabInvitation` model only, never `OrgInvite`. |
| 2 — school email enforcement | **Largely shipped 2026-09-19** (`324f2d5`, `c670562`). An institution is derived from the verified address and cannot be typed; `Profile.institution` is written only by `institution.sync`. The remaining gap is that a personal address is *allowed*, it just proves nothing. |
| 3 — member removal | **Backend exists**: `DELETE /api/auth/labs/<slug>/members/<username>/` (`LabMemberDetailView`), owner/admin gated, refuses to drop the last owner, schedules seat removal. **The UI never calls it** — `member-row.tsx` is display-only. |
| 4 — ownership transfer | **Not built**, and blocked on a security fix (below). |

### The blocker found while scoping request 4

`LabMemberDetailView.patch` gates on `user_can_manage_lab`, which is true for
**owner or admin**, and `set_lab_member_role` accepts `role="owner"` from
anyone who passes that gate. So today **any lab admin can promote themselves to
owner**, and nothing is logged as unusual when they do.

That is a privilege-escalation bug in its own right. It also makes request 4's
"irreversible" requirement unimplementable: a transferred-away owner is demoted
to admin and could immediately `PATCH` themselves back to owner. Phase 0 closes
it, and everything in phase 4 depends on that.

## Assumptions and open questions

1. **Sign-up must not become an email-enumeration oracle.** No public
   "does this address have an invite?" endpoint. The notice appears only to
   someone who has completed registration on that address, and it names no
   organisation until the address is verified. Assumption: naming the lab only
   post-verification is an acceptable trade for not leaking org membership to an
   unverified stranger.
2. **The mailbox is the proof.** An email invite redeemed via its token is
   already treated as proof of mailbox control (the account skips verification,
   [views.py:265](../../web/backend/apps/accounts/views.py:265)). A pending
   invite matched by *typed* address is not proof, so it is claimed on
   verification rather than at sign-up. The existing `email_verified` signal
   ([email_verification.py:205](../../web/backend/apps/accounts/email_verification.py:205))
   is the hook.
3. **DECIDED — request 2.** The substance already ships: an address that proves
   no institution is listed at none, so nobody can say they are at FSU on a
   gmail address. What is missing is an *exception* — Olmo Zavala is to count as
   FSU despite `olmozavala@gmail.com`. That needs an explicit, audited grant
   rather than a typed value, because "proved, never typed" is a documented
   invariant and a quiet override would make the field mean two things.
   `SIGNUP_REQUIRE_INSTITUTION_EMAIL` ships **default off**: blocking every
   personal-domain sign-up is a larger behaviour change than was asked for, and
   the flag is there to turn on deliberately.
4. **DECIDED — labs first.** Department head transfer is phase 5 and is not
   built in this pass.
5. Transfer moves authority only. Seats, billing scope and the paying
   subscription are untouched — `transfer` adds and removes no members.

## Phases

### Phase 0 — a role can only be granted downward (security)

Today any manager may grant any role, so an admin can mint an owner (including
themselves) or another admin. Both are closed by one rule rather than two
special cases.

Rank the roles `OWNER(3) > ADMIN(2) > MEMBER(1) > VIEWER(0)` and require:

- an actor may only modify a target of **strictly lower** rank, and
- may only grant a role **strictly lower** than their own.

Which yields exactly what was asked:

| Actor | May grant | May act on |
|---|---|---|
| Owner (PI) | admin, member, viewer | anyone below them |
| Admin | member, viewer | members and viewers only |
| Member / viewer | — | — |

- Only the PI creates admins; only the PI creates owners, and only through
  phase 4's dedicated transfer route, never a plain role edit.
- An admin can no longer touch another admin or the owner — which is also what
  makes a demoted ex-owner unable to climb back.
- `permissions.lab_role_rank(user, lab)` is the single read; `set_lab_member_role`
  refuses with 403 `reason="role_above_you"`.
- Audit the refusal as `lab.member.role.refused`, so escalation attempts are
  visible rather than merely blocked.

**Note on PI vs owner.** The model has two fields — `role=OWNER` and
`is_lead=True` (the PI badge). They are the same person by construction once
phase 4 moves them together, so the permission keys on `role` and carries
`is_lead` alongside it. A lab keeps exactly one lead.

**Validation:** new tests in `apps/accounts/tests/test_lab_roles.py` —
admin→owner refused, admin→admin refused, admin→member allowed, owner→admin
allowed, admin cannot modify the owner, admin cannot modify another admin.

### Phase 1 — a pending invite is never silently missed

- `invites.pending_for_email(email)` → the live, unrevoked, unexpired,
  unexhausted email-kind `OrgInvite` for an address, or `None`.
- `register_view`: when no `invite_token` is posted and
  `pending_for_email(email)` hits, create the account as normal and record the
  match. Response gains `pending_invite: true` (no org name).
- On email verification, claim it: extend the `email_verified` receiver to call
  `invites.redeem` for any live invite matching the now-verified address.
  Idempotent, and a `SeatCeilingExceeded` leaves the account intact and the
  invite unspent.
- App: a dismissible banner while unverified — *"An invitation is waiting for
  this address. Verify your email to accept it."* After verification the
  existing membership UI shows the lab, so no second surface is needed.
- Sign-up form: when the backend reports `pending_invite`, say so on the
  confirmation step rather than on the email field (which would make it a
  live-typing oracle).

**Validation:** `apps/accounts/tests/test_invite_signup_flow.py` — sign up with
an invited address and no token, verify, assert membership; assert no
membership before verification; assert the response names no org.

### Phase 2 — affiliation stays proved, with a named exception

An institution is already derived from the verified address and cannot be
typed, so "you cannot claim FSU on a gmail address" holds today. Two additions:

- **A granted institution.** `Profile.institution_granted`,
  `institution_granted_by` (staff FK) and `institution_granted_at`.
  `institution.sync` prefers a grant over the derived value, so the field still
  has exactly one writer and every value is either *proved by email* or
  *granted by a named person* — never typed by its subject. Recorded as
  `account.institution.grant` in the audit log.
- Command `grant_institution --user <name> --institution <name> [--revoke]`,
  which resolves the institution against the affiliation directory so a grant
  cannot invent one. Used once for `olmozavala` → Florida State University.
- `SIGNUP_REQUIRE_INSTITUTION_EMAIL`, **default `False`**. When on,
  `RegisterSerializer` refuses an address resolving to no institution
  (`reason="institution_required"`); an invited address is exempt.

**Validation:** `test_signup_institution.py` — a grant survives a re-sync, a
revoked grant falls back to the derived value, a grant to an unknown
institution is refused, gmail refused only when the flag is on.

### Phase 3 — the roster is manageable from the app

- `member-row.tsx` gains, for a manager only: a role select and a Remove
  action behind a confirm. The last owner and (post-phase-0) any owner seen by
  an admin render read-only.
- `useLabMembers` gains `useSetLabMemberRole` / `useRemoveLabMember` mutations
  in `lib/portal/hooks.ts`, optimistic with rollback, invalidating the roster.
- Empty/error/permission states per the global skill: a refused removal shows
  the server's reason, not a generic failure.
- Department roster gets the same treatment against `DeptMemberDetailView`.

**Validation:** `npm run --prefix web/app lint` and `build`; manual pass on the
Members section as owner, admin and member.

### Phase 4 — ownership transfer (lab)

- `services.transfer_lab_ownership(lab, new_owner, *, actor)`, atomic:
  new owner → `role=OWNER, is_lead=True`; actor → `role=ADMIN, is_lead=False`;
  any other `is_lead` cleared so a lab has exactly one PI.
- Guard: actor must be a current OWNER; target must be an existing member;
  target must have a verified email (they are about to hold the lab).
- Route: `POST /api/auth/labs/<slug>/transfer-ownership/` **and** the
  no-slash form, body `{"username": "..."}`.
- Irreversibility is phase 0's guard doing its job: the demoted admin can no
  longer grant ownership, so only the new owner can hand it back.
- UI: a confirm dialog in lab settings that states plainly that the action
  cannot be undone and names who will hold the lab.
- Audit: `lab.ownership.transfer` with both user ids.

**Validation:** `test_lab_ownership.py` — transfer moves both role and lead,
old owner cannot transfer back, non-owner refused, unverified target refused.

### Phase 5 — department head transfer (separable)

Same shape against `Department.owner` plus `DeptMembership`, once phase 4's
shape is settled and question 4 is answered.

## Interfaces that change

| Surface | Change |
|---|---|
| `POST /api/auth/register/` | response adds `pending_invite: bool`; may refuse `institution_required` when the setting is on |
| `PATCH /labs/<slug>/members/<username>/` | refuses a grant at or above the actor's own role (`role_above_you`) |
| `POST /labs/<slug>/transfer-ownership/` | **new**, both slash forms |
| `docs/api-contract.md` | all three of the above |
| `docs/repo-map.md` | rows for ownership transfer and the pending-invite claim |

## Explicitly out of scope

- Reworking the legacy `LabInvitation` path; it stays as it is.
- Any change to billing, seats or entitlements. Removal already defers seats;
  transfer touches neither.
- Backfilling `institution` for existing personal-domain accounts.
- Discord/Slack notification of a transfer or removal.

## Acceptance

1. An invited person who signs up separately with the invited address lands in
   the lab once they verify, without anyone re-sending anything.
2. A lab admin cannot make themselves owner, and cannot create another admin —
   only the PI can.
3. A PI or admin can remove a member from the app.
4. An owner can hand the lab to a member and cannot take it back.
