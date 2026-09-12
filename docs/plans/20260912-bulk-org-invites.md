# Bulk org invitations + access-code activation

**Status:** proposed, 2026-09-12.
Working document — delete on ship and record the outcome in `docs/changelog.md`,
`docs/api-contract.md`, and `docs/repo-map.md`.

---

## Objective

Let a lab or department manager invite **up to 15 people by email in one
submission** — type an address, press Enter, it becomes a chip, repeat — and prove
that the resulting sign-up automatically joins the invitee to the lab or
department, for both the emailed invitation and the share link.

## What already exists (do not rebuild)

The invitation system is **already shared by labs and departments**. One model
(`OrgInvite` / `OrgInviteRedemption`), one service module
(`web/backend/apps/accounts/invites.py`), one card
(`web/app/src/components/portal/sections/org-invite-card.tsx`) mounted by both
`labs-section.tsx:392` (`LabDetail`, managers only) and
`department-section.tsx:49`. Both ways in work today for both org kinds:

- **Email invite** — bound to one address, `max_uses = 1`, re-checked at
  redemption (`check_email_matches`), so forwarding the mail does not transfer it.
  Redeeming one as the addressed mailbox already sets `is_verified = True`
  (`views.py:265-268`).
- **Share link** — `max_uses` (default 25, ceiling 500) plus an expiry (default 7
  days, 1–90), `/join/<token>` landing, anonymous preview, revoke.

So the lab half of the request is done. The real gaps are the two below.

## The gap this plan closes

**One address per submission.** `OrgInviteCard` has a single `<input
type="email">`; `create_invite` takes one `email`. Inviting a 12-person lab is 12
form submissions. Everything downstream of creation — delivery, the address
binding, redemption, auto-join at sign-up — already works and is covered here by
tests rather than rewritten.

## Not in scope: the access code

`SIGNUP_ACCESS_CODE` defaults to `251253` (`web/backend/config/settings.py:245`)
and is the invite-only sign-up gate — proof that a caller may create an account at
all. That is working as intended and is **not changed** by this plan. The
verification code mailed after sign-up is a separate mechanism and is also left
alone; what this plan does is prove the join half of the flow, below.

## Assumptions

- **15 is a per-submission cap, not a per-org quota.** A manager may submit
  another batch immediately. The cap exists so one paste cannot fan out
  unbounded mail.
- **Mail stays synchronous.** Every existing mail path (`send_email` over Resend,
  stdlib urllib) is in-request; 15 sequential sends is a few seconds. Introducing
  Celery for mail here would make this the only asynchronous mail path in the
  codebase. Noted as a cost, not changed.
- **Partial success is success.** A batch where 11 addresses send and 4 are
  already members returns `201` with per-address outcomes, not a `400` that
  discards the 11. This is the main behavioural decision in the plan.
- **No new tier gate.** Inviting is already governed by roster authority
  (`user_can_invite_to_lab` / `..._to_department`) and by seats at redemption.
  Batching changes neither, so nothing new is read from `billing.entitlements`.
- **Share links are unchanged.** A link already admits many people; batching is
  an email-tab concern only.

---

## Phase 1 — Batch creation in the service layer

**What.** Add `create_invites()` to `web/backend/apps/accounts/invites.py`: take a
list of addresses, return per-address outcomes.

**How.**

- `MAX_BATCH_EMAILS = 15` module constant, beside `DEFAULT_MAX_USES`.
- `normalize_addresses(raw) -> list[str]`: strip, lowercase, drop blanks,
  de-duplicate **preserving order**, and split on commas/semicolons/whitespace so
  a pasted list works as well as typed chips.
- `create_invites(*, creator, lab=None, department=None, emails, role, message,
  send=True) -> BatchResult` where `BatchResult` is a dataclass of `created:
  list[OrgInvite]` and `failed: list[dict]` (`{"email", "reason", "detail"}`).
- Validate the **batch** before creating anything: empty list → `ValidationError`;
  more than 15 → `ValidationError` naming the cap. These are the creator's
  mistakes, not an address's.
- Then loop per address, each in its own `transaction.atomic()`, reusing
  `create_invite` unchanged. Catch `ValidationError` per address and record it in
  `failed` with a machine reason (`already_member`, `invalid_email`,
  `already_invited`) so the UI can style each row.
- New per-address refusal: `already_invited` — a live, unspent email invite to
  that address for that org. Today re-inviting silently mints a second row; in a
  batch that is how you mail somebody twice. Reuse `is_live()` for the check.
- One audit event for the batch (`org.invite.batch`, metadata: org kind/id,
  `requested`, `created`, `failed` counts) **in addition to** the existing
  per-invite `org.invite.create` events, so a batch is reconstructable.

**Why.** The per-address rules (`_refuse_existing_member`, `_clean_role`,
duplicate-token retry, audit) already live in `create_invite`. A batch wrapper
inherits all of it; a parallel implementation would drift.

**Validate.** `uv run --project web/backend pytest apps/accounts/tests/test_org_invites.py`

## Phase 2 — Batch endpoint

**What.** Accept a list on the existing invite routes; keep the single-address
shape working.

**How.**

- In `_OrgInvitesView.post` (`web/backend/apps/accounts/views.py:1620`), branch on
  the payload: `emails` (list or delimited string) → batch path; bare `email` →
  today's single path, byte-for-byte. No new route, so no new trailing-slash pair
  and no nginx change.
- Batch response `201`:
  `{"created": [<invite_payload>, …], "failed": [{"email", "reason", "detail"}, …],
   "requested": <int>}`.
- `require_verified_email(request.user)` stays first, ahead of any parsing — an
  unactivated account must not learn whether an address is already a member.
- Leave `RegisterRateThrottle` alone; add no throttle here. The route is already
  authenticated and authority-checked, and 15 is the cap.

**Why.** One route, two shapes, is a smaller surface than a second route that
duplicates the authority checks in `LabInvitesView` / `DeptInvitesView`.

**Validate.** Same file, plus
`uv run --project web/backend pytest apps/accounts/tests/test_org_invites.py apps/accounts/tests/test_permissions.py`

## Phase 3 — Chip entry in the invite card

**What.** Turn the email tab into a multi-address chip field, capped at 15, used
identically by labs and departments.

**How.**

- `web/app/src/lib/portal/types.ts`: extend `OrgInviteInput` with `emails?:
  string[]`; add `OrgInviteBatchResult`.
- `web/app/src/lib/portal/mutations.ts`: `createLabInvites` / `createDeptInvites`
  returning the batch shape, beside the existing singular pair.
- `web/app/src/lib/portal/hooks.ts`: add `createMany` to `useOrgInvites`
  (line 1527), invalidating the same `["portal", "org-invites", kind, id]` key.
- `org-invite-card.tsx`, email tab: chips list + input. Commit a chip on
  **Enter**, comma, semicolon, or blur; `Backspace` on an empty input removes the
  last chip; each chip has a remove button; paste splits on delimiters. Reject a
  malformed address at commit time with an inline message rather than sending it.
- Counter (`n of 15`); disable the input and say so at 15; disable submit on zero.
- Result block: "Sent 11 invitations." plus a list of the refusals with their
  reason, kept on screen until the next submission. Do not clear chips that
  failed — the manager may want to fix a typo.
- Accessibility (`docs/skills/*` → ADA/WCAG 2.2 AA): the chip list is a `<ul>`; the
  input keeps a stable `aria-label`; each removal and the send result are
  announced through an `aria-live="polite"` region; the counter is wired via
  `aria-describedby`; chips wrap rather than scroll so a phone does not overflow.
- Keyboard-only and reduced-motion behaviour: no animation is added, so nothing
  to gate.

**Why.** The card is already the single shared surface for both org kinds, so
building it here satisfies the parity rule with no lab-only fork.

**Validate.** `npm run lint --workspace web/app` and `npm run typecheck --workspace web/app`
from the repository root (confirm the exact script names in `web/app/package.json`
first and use the root delegate if one exists).

## Phase 4 — Prove the whole sign-up path end to end

**What.** One test module covering the paths that must not need a second pass.

**How.** `web/backend/apps/accounts/tests/test_invite_signup_flow.py`:

1. Batch of 15 → 15 live invites, 15 mails recorded.
2. Batch of 16 → `400`, nothing created.
3. Batch mixing a new address, an existing member, a duplicate within the batch,
   and a malformed address → `201`, the new one created, three refusals with
   distinct reasons.
4. Email invite → `/api/auth/invites/<token>/` preview → register with the
   addressed email **and no access code** → account created, `is_verified` true,
   member of the org at the invited role, invite `used_count == 1`.
5. Same invite, register with a **different** email → `400`, `reason ==
   "wrong_email"`, no account created.
6. Register with `access_code` only and no invite → account created, joined to
   nothing, still **unverified** with an `EmailVerification` row issued. This is a
   guard on current behaviour, not a change.
7. Wrong access code ×3 → shadow ban; the 4th attempt with the **correct** code
   is still refused with the same generic message.
8. Share link at `max_uses = 1`, two concurrent redemptions → exactly one member.
9. Revoked and expired invite → `410` preview, `400` on register.
10. Both org kinds run through 1–4, parameterised, so a lab-only regression fails.

**Why.** "Make sure this entire sign-up process also functions so that we don't
have to go back and forth" is a testing requirement, and these are the seams that
break: the address binding, the activation branch, the use budget under
concurrency, and lab/department parity.

**Validate.** `uv run --project web/backend pytest apps/accounts/` — the whole
app, to catch anything the batch path or the activation branch disturbed.

## Phase 5 — Documentation

- `docs/api-contract.md` — the batch request/response shape on
  `labs/<slug>/invites/` and `departments/<id>/invites/` (extends lines 458–486);
  no registration-section change, since sign-up behaviour is unchanged.
- `docs/repo-map.md` — update the invite rows to say "one or many"; add the new
  test module if it is worth a locator.
- `docs/changelog.md` — one entry per the global schema, correlation ID
  `20260912-bulk-org-invites`.
- Delete this plan file.

---

## Interfaces that change

| Surface | Change |
|---|---|
| `POST /api/auth/labs/<slug>/invites/` | Also accepts `emails: [...]` (≤15); returns `{created, failed, requested}` |
| `POST /api/auth/departments/<id>/invites/` | Same |
| `apps.accounts.invites` | New `MAX_BATCH_EMAILS`, `normalize_addresses`, `create_invites`, `BatchResult` |
| `OrgInviteInput` (TS) | New optional `emails: string[]`; new `OrgInviteBatchResult` |
| `useOrgInvites` | New `createMany` |
| Audit log | New `org.invite.batch`; `account.register` gains `activation` |

No migration: `OrgInvite` is unchanged.

## Acceptance criteria

- A lab manager and a department manager can each send 15 invitations in one
  submission, entered by typing an address and pressing Enter.
- A 16th chip cannot be added; the cap is stated, not just enforced.
- A batch containing a bad address still delivers the good ones and names the bad
  one with a reason.
- An emailed invitation is spendable **only** by the address it was sent to, at
  preview and at registration.
- A share link stops at its budget and its expiry, under concurrent redemption.
- A person who follows an invitation and signs up is a member of the inviting lab
  or department the moment the account exists — no manual join step, both for an
  emailed invitation and for a share link.
- `uv run --project web/backend pytest apps/accounts/` passes; lint and typecheck
  pass for `web/app`.

## Excluded

- Any change to the share-link model, `max_uses`, or expiry rules.
- Any change to seats, tiers, or `billing.entitlements`.
- Any change to the sign-up access code, the six-digit email verification code, or
  `require_verified_email`.
- CSV upload, directory sync, or address-book autocomplete.
- Asynchronous/queued mail delivery.
- Resending an existing invitation (only revoke-and-reissue, as today).
- The legacy `LabInvitation` path (`labs/<slug>/invitations/`), which is a
  separate, older mechanism and is left alone.
