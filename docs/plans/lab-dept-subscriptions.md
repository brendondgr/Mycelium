# Lab & Department Subscription Plans — Implementation Plan

**Source of record:** the requirements brief (Lab & Department Subscription Plans)
plus the canonical data model in [`Mycelium_Data_Model_Briefing.md`](Mycelium_Data_Model_Briefing.md)
(§4 derived membership, §7 tiers/pricing, §11 open question "Seat lifecycle").
**Extends:** [`tier-enforcement.md`](tier-enforcement.md) (the entitlement read path this
builds on). **Branch:** isolated worktree, merged to `main` at the end.
**Scope boundary:** everything up to — but **not including** — real payment processing.
No Stripe coupling, no card capture, no charging. Amounts are *computed and ledgered*,
never billed.

---

## Objective

Turn labs and departments from "structure that silently carries an ACTIVE paid plan"
into a real, opt-in subscription lifecycle: an org is created **inactive** (structure
is free), a PI/head **adds people and labs**, then **activates** a seat-priced plan
whose cost tracks the number of covered people, with defined mid-cycle billing
behaviour — and with entitlement propagation (a lab's plan reaches its members; a
department's plan reaches every member of every lab under it) that today is only
half-wired. Deliver it full-stack in three clean layers: **backend → API → frontend**.

## Locked decisions (from the user, 2026-07-21)

| # | Decision | Consequence |
|---|---|---|
| L1 | **Both labs and departments start inactive** | Org (lab/dept) subscriptions are created in a new `INACTIVE` state and grant nothing until explicit activation. Changes today's active-on-create provisioning + affected tests. Personal subs stay ACTIVE (Free baseline). |
| L2 | **Department seats auto-entitle the effective membership on activation** | Overrides tier-enforcement **A6** (`PENDING` per-person). Activating a department seats every effective member ACTIVE + department-paid; later membership/lab changes auto-seat. Resolves briefing open-question #11. |
| L3 | **Prorate adds; no credit on removal** | Mid-cycle add → billed only for the remaining days of the period. Removal → seat stays ACTIVE + billed through `current_period_end`, access retained until then, then flipped REVOKED by a billing tick; no refund/credit. |
| L4 | **Full stack, strictly layered** | Complete the entire backend, then the API, then the frontend — in that order. |

## Grounded findings (verified against current code)

- **Org subs are ACTIVE-on-create.** `billing/services.py:73,113` create `Tier.LAB` /
  `Tier.CANOPY` subscriptions with the default `status=ACTIVE` and a founding seat.
  No `INACTIVE`/`DRAFT` status exists (`Subscription.Status` = active/past_due/canceled).
- **No billing-period model.** `Subscription` has `expires_at` (timed grants) but no
  `activated_at` / `current_period_start` / `current_period_end`, and no price anywhere —
  the tier prices ($0 / $10 / $12.50-member / $20-member) live only in briefing §7.
- **Seat removal is immediate.** `seats.py::revoke_seat_*` flips straight to `REVOKED`,
  with no "keep access until period end" concept. It is called **only in tests** — no
  production caller, because no member-removal path exists.
- **Rules 1 & 2 half-wired.** Seats are granted only in `accept_invitation` (lab invite)
  and founder provisioning. Department seats are `PENDING` and issued against *direct*
  `DeptMembership` only (`reconcile_seats`), never the effective set — so a lab-under-dept
  member never gets a department seat. `effective_member_ids` (`accounts/services.py:59`)
  computes the right set; nothing seats against it.
- **Org management is greenfield.** No API/UI to add/remove a department member, attach a
  lab to a department (`Lab.department` FK exists, is never set), remove a lab member, or
  change a role. `LabMembersView` is GET-only; departments expose only a profile GET/PATCH.
  No `user_can_manage_department` permission. No billing/plan/activation UI — only a
  read-only `useEntitlements()` gating the sidebar.
- **Model facts:** `Lab{name,slug,department→Dept(SET_NULL),timezone,send_hour_local,logo}`;
  `Department{owner(PROTECT),name,institution}`; memberships carry `role∈owner/admin/member/viewer`
  (LabMembership also `is_lead`). No billing fields on org models — billing is external via
  `Subscription.scope_*`.

## Architecture decisions (this plan)

- **B1 — Structure stays decoupled from billing (briefing D8).** Creating/joining labs &
  depts never requires an active plan; an inactive org degrades to "a set of individuals."
- **B2 — One paying scope per member.** A member is seated on the **closest active paying
  scope**: if their lab belongs to a department with an active plan, the department seats
  them (dept-paid) and the lab does not also seat them; otherwise the lab's own active plan
  seats them (lab-paid). Prevents double-billing. Enforced in the seat-sync service + tests.
- **B3 — Removal is deferred, never destructive.** Removing a member sets
  `Seat.ends_at = current_period_end` and leaves the seat ACTIVE (entitled + billed) until a
  billing tick flips it REVOKED at/after that instant. Never hard-deleted (audit survives).
- **B4 — Prices are data, computed read-time.** `TIER_PRICE_CENTS` lives beside the other
  caps in `entitlements.py`; a `billing/pricing.py` module computes recurring cost + add
  proration. Informational only (mirrors `AddOn.price_cents`); no charging.
- **B5 — Seat lifecycle is centralized and idempotent.** All membership create/remove routes
  through one billing service, backstopped by `post_save`/`post_delete` signals on both
  membership models, so no path (endpoint, seed, admin) can bypass seat sync.
- **B6 — A `SeatEvent` ledger records every add/remove/activation** with its effective date
  and prorated amount — the "checks and balances" audit trail and the seam a future payment
  processor would read. Reuses `accounts.AuditEvent` for actor-level audit; `SeatEvent` is
  the billing-math ledger.
- **B7 — `entitlements.py` stays the only read path (tier-enforcement A1).** New pricing/
  period logic never re-implements tier resolution.

---

## Phase B — Backend (data model + business logic). No HTTP.

Complete and green before any API work.

### B-1 · Subscription lifecycle + billing period
Files: `billing/models.py` (+ migration), `billing/period.py` (new),
`billing/management/commands/run_billing_tick.py` (new).
1. `Subscription.Status` gains `INACTIVE = "inactive"` (created state for org plans).
   `is_current()` unchanged (ACTIVE + unexpired) → an inactive plan grants nothing.
2. Add fields: `activated_at` (dt, null), `current_period_start` (date, null),
   `current_period_end` (date, null), `billing_interval` (default `"monthly"`).
3. `billing/period.py`: `activate(subscription, *, on)` (status→ACTIVE, stamp
   `activated_at`, set period = `[on, on+1mo)`), `roll_periods(now)` (advance any plan
   whose `current_period_end` passed), `end_lapsed_seats(now)` (flip ACTIVE seats whose
   `ends_at<=now` to REVOKED). Pure, timezone-aware, idempotent.
4. `run_billing_tick` command runs `roll_periods` + `end_lapsed_seats`; document that a
   host timer (sibling to `mylo-daily`) or Celery-beat schedules it daily. **Not** folded
   into the recommendation daily run (global rule).
- **Validate:** `billing/tests/test_period.py` — activation sets a 1-month window;
  `end_lapsed_seats` revokes only past-`ends_at` seats; inactive plan `is_current()==False`.

### B-2 · Seat lifecycle: deferred removal + `SeatEvent` ledger
Files: `billing/models.py` (+migration), `billing/seats.py`, `billing/pricing.py` (new).
1. `Seat` gains `ends_at` (date, null) — the access/billing cutoff for a scheduled removal.
   An ACTIVE seat with a future `ends_at` is "pending removal" (still entitled + billed).
2. New `SeatEvent` model: `seat` FK, `kind∈{added,activated,removed,expired}`,
   `effective_date`, `prorated_cents`, `created_at`. The billing-math ledger (B6).
3. `seats.py`: rework removal to `schedule_seat_removal(user, scope)` (set `ends_at=period
   end`, log `removed` event) instead of immediate REVOKE; keep an internal hard-revoke for
   the tick. `grant_*` idempotency preserved; log `added`/`activated` events with proration.
4. `billing/pricing.py`: `TIER_PRICE_CENTS`; `recurring_monthly_cents(subscription)` =
   active-seat count × per-seat price; `prorate_add(tier, added_on, period)` (remaining-days
   fraction, L3); `activation_quote(subscription)` and `add_members_quote(...)` preview
   objects. No credit path (L3).
- **Validate:** `billing/tests/test_pricing.py` — proration math (full-period add = full
  price; last-day add ≈ 1 day; removal writes no credit); `test_seats.py` additions —
  removal defers (seat still ACTIVE, `ends_at` set), tick then revokes.

### B-3 · Seat-sync service + membership signals (rules 1 & 2)
Files: `billing/seat_sync.py` (new), `accounts/signals.py`, `billing/apps.py`.
1. `seat_sync.py`:
   - `paying_scope_for_lab(lab)` → the department's active sub if the lab's dept has one,
     else the lab's own active sub, else `None` (B2).
   - `sync_lab_member(user, lab)` / `sync_dept_member(user, dept)` → grant the ACTIVE seat on
     the resolved paying scope (dept-paid or lab-paid), idempotent; no-op if inactive.
   - `unsync_lab_member` / `unsync_dept_member` → `schedule_seat_removal`.
2. `post_save`/`post_delete` signals on `LabMembership` + `DeptMembership` call the sync/
   unsync helpers (B5). Idempotent so explicit service calls + signals can't double-grant.
3. Rewrite `accept_invitation` to call `sync_lab_member` (keeps its ceiling behaviour).
- **Validate:** `billing/tests/test_seat_sync.py` — lab-under-active-dept member gets a
  dept-paid seat, not a lab seat (B2); standalone-lab member gets a lab-paid seat; removing
  the membership schedules (not revokes) the seat. `accounts/tests` invite test still green.

### B-4 · Activation seeds the effective membership (L2) + provisioning starts inactive (L1)
Files: `billing/services.py`, `billing/period.py`, `accounts/services.py`.
1. `provision_workspace` / `create_lab_workspace`: create lab/dept subs `status=INACTIVE`,
   founder seat `PENDING` (not an entitling ACTIVE seat) until activation. Personal
   unchanged.
2. `activate_lab_subscription(lab, *, actor)` / `activate_department_subscription(dept, *,
   actor)`: `period.activate(...)`, then seed ACTIVE seats — a lab across its
   `LabMembership`s; a department across `effective_member_ids` (direct ∪ all lab members),
   dept-paid (L2). Records `SeatEvent(activated)` + `AuditEvent`. Enforces the tier ceiling.
3. Attaching a lab to an active department re-seats that lab's members onto the dept sub and
   deactivates redundant lab seats (B2).
- **Validate:** `billing/tests/test_activation.py` — newly-created dept is INACTIVE and its
  members resolve to FREE; after `activate_department_subscription` every effective member
  (incl. a member of a lab under the dept) resolves to CANOPY on an ACTIVE dept-paid seat.

### B-5 · Reconcile + backfill
Files: `billing/management/commands/reconcile_seats.py`.
- Update the department sweep to iterate `effective_member_ids` and grant ACTIVE dept-paid
  seats (was: direct members, PENDING). Keep idempotent + `--dry-run`. Add a note it is a
  backfill, not the live path (signals are).
- **Validate:** `test_reconcile_seats.py` — a pre-existing lab-under-dept member with no seat
  is backfilled to an ACTIVE dept seat on an active dept plan.

**Phase B exit:** `uv run --project web/backend pytest apps/billing apps/accounts -q` green;
`manage.py makemigrations --check` clean; `ruff check`. Commit.

---

## Phase A — API (DRF endpoints exposing Phase B). No new business logic.

Every endpoint object-permission-gated + audited. Add `user_can_manage_department`
(owner/admin) to `accounts/permissions.py`.

### A-1 · Lab membership management
`accounts/views.py` + `urls.py` + `serializers.py`:
- `POST /api/labs/<slug>/members/` — manager adds an existing user (→ membership → seat sync).
- `DELETE /api/labs/<slug>/members/<user_id>/` — manager removes (→ deferred seat removal).
- `PATCH /api/labs/<slug>/members/<user_id>/` — role change (manager).
- `POST /api/labs/<slug>/invitations/<id>/cancel/` — inviter cancels a pending invite
  (uses the existing unused `CANCELLED` status).

### A-2 · Department members + labs
New `apps/accounts` department views (or a small `apps/billing` org surface):
- `GET/POST /api/departments/<id>/members/` — roster (effective, direct-vs-via-lab flag) + add
  direct member. `DELETE /api/departments/<id>/members/<user_id>/` — remove direct member.
- `GET/POST /api/departments/<id>/labs/` — list labs under the dept + attach an existing lab
  or create a new lab under it (sets `Lab.department`, re-seats members, B2).
  `DELETE /api/departments/<id>/labs/<lab_id>/` — detach (clear `Lab.department`).

### A-3 · Subscription billing + activation
New `billing/views.py` endpoints (+ serializers, urls):
- `GET /api/labs/<slug>/billing/` and `GET /api/departments/<id>/billing/` — plan state:
  tier, status, period, seat_count, `recurring_monthly_cents`, member breakdown, payer mix.
- `POST /api/labs/<slug>/billing/activate/` + dept equivalent — activate (head-gated); returns
  the activation quote + new state. **This is the payment boundary** — it flips state and
  seeds seats; it does not charge.
- `POST /api/.../billing/preview/` — proration/cost preview for activating or adding N members.
- `POST /api/.../billing/cancel/` — status→CANCELED, seats scheduled to end at period end.

### A-4 · Account visibility (read surface)
`billing/views.py` + `serializers.py`:
- Extend `GET /api/billing/me/` with `plans[]` — every plan covering the user (personal
  Spore/Free + each lab/dept seat), each `{scope_type, scope_name, tier, status, seat_status,
  payer_type, period}` — the "which of Spore/Lab/Canopy do I have active in total" answer.
- **Validate (A):** `billing/tests/test_billing_api.py` + `accounts/tests` — permission
  matrix (non-manager 403), add/remove member round-trips through seats, attach-lab re-seats,
  activate flips FREE→tier for the effective set, `/billing/me` lists all plans.
  `pytest apps/billing apps/accounts -q` green. Commit.

Update [`api-contract.md`](../api-contract.md) with the new shapes.

---

## Phase F — Frontend (integrate the API). Layered last.

Data layer first, then components, then routes. React Query + `lib/portal/{client,hooks,
mutations,types}.ts` conventions.

### F-1 · Data layer
- Types + `fetch*`/`use*`/mutations for: lab member add/remove/role, invite-cancel; department
  members + labs CRUD; org billing read/activate/preview/cancel; extended `/billing/me` `plans[]`.

### F-2 · Account visibility
- A **"Your plans"** card (profile section) listing active plans (Spore/Lab/Canopy) with tier
  badge, scope name, seat status, and role — the required "clear way to show which
  subscriptions a user has active in total." All entitlement/loading/empty states.

### F-3 · Lab management + plan
- Wire **remove-member** + **role-change** into the lab-settings `MembersCard`
  (`labs-section.tsx`); enable the disabled "Invite" affordance path where relevant.
- A **"Lab plan"** card: status (inactive/active/canceled), seat count, monthly cost, and an
  **Activate** flow (preview quote → confirm → activate). Manager-gated.

### F-4 · Department management (greenfield UI)
- New department route under `app/(workspace)/` (or lab-switcher "department" scope): a
  department settings/dashboard with **Members** (add/remove), **Labs** (attach/create/detach),
  and a **"Department plan"** card (member breakdown, seat count, cost, Activate/Cancel).
- Adding people/labs surfaces the resulting cost and routes into activation — the requirement's
  "adding users leads naturally into the subscription process."
- **Validate (F):** `npm run -w web/app typecheck` + `lint` + `build`. Browser-verify via the
  dev server (`localhost:11050`, StrictMode) where the checkout allows; a worktree can't be
  browser-previewed (memory: preview is pinned to the main checkout) so rely on
  typecheck+lint+build there and verify interactively after merge. Commit.

---

## Cross-cutting

- **Auth/permissions:** every mutating endpoint checks `user_can_manage_lab` /
  `user_can_manage_department`; every write records an `AuditEvent`. Object-level scoping on
  all reads.
- **Data safety:** no seat is ever hard-deleted; downgrades/cancels never delete topics, saves,
  or memberships — they change what is unlocked (mirrors existing `expires_at` behaviour).
- **Docs:** resolve briefing §11 "Seat lifecycle" open question + add decisions D18–D21
  (L1–L4) to the briefing decisions log; update §7 with the period/activation/price-in-model
  facts; update `repo-map.md` (new endpoints, `pricing.py`/`period.py`/`seat_sync.py`,
  `run_billing_tick`, dept UI), `architecture.md` billing note, `api-contract.md`, and
  `changelog.md` per the global schema. One focused commit per phase; concise human-authored
  messages, no AI attribution; **no push**.
- **Worktree:** isolated `git worktree`; merge local `main` in before finishing (worktrees base
  on origin/main which lags local); delete the worktree after merge.

## Validation summary (acceptance criteria)

1. A freshly created lab **and** department are INACTIVE; their members resolve to FREE.
2. Activating a lab seats its members ACTIVE lab-paid → they resolve to LAB.
3. Activating a department seats the **effective** membership (incl. members of labs under it)
   ACTIVE dept-paid → they resolve to CANOPY (rule 2). 
4. A member added mid-cycle produces a prorated `SeatEvent`; a removed member keeps access
   until `current_period_end`, then the tick REVOKES with no credit (L3).
5. `GET /api/billing/me/` lists every plan the user holds.
6. Non-managers are 403 on every management endpoint; no seat is ever hard-deleted.
7. Backend + API suites green; frontend typecheck+lint+build green.

## Explicit exclusions

No real payment processing, no Stripe/card capture/charging, no dunning/`PAST_DUE` grace
(kept as tier-enforcement D3), no per-member "prompt to choose payer" UX (Canopy default is
department-paid; self/lab-paid mixing stays a model capability, not a built flow this pass),
no institution-level billing (briefing D10, deferred).

## As-built deviations from this plan

- **Seat wiring is an explicit service, not global signals (B5 revised).** Every membership
  mutation routes through `billing.seat_sync` (invite-accept + the new member/lab endpoints),
  with `reconcile_seats` as the bulk backstop. Global `post_save`/`post_delete` signals were
  dropped to avoid surprising seat writes during seeding/admin/tests — since this work builds
  *every* runtime membership path, explicit calls cover them all.
- **Whole-plan cancel/deactivate deferred.** Single-member deferred removal (the requirement's
  "access until period end") is fully built; a whole-subscription cancel (which needs a
  `cancel_at_period_end` flag + tick finalization) is a small follow-up, not shipped this pass.
- **Frontend verified by typecheck + lint + build**, not the browser preview (the Preview MCP
  serves the main checkout, not this worktree). Interactive verification is a post-merge step.

---

## Follow-up: a tier belongs to a scope (2026-08-01)

**Decision.** Mycelium Lab is sold on a lab and nowhere else. Canopy likewise on a
department. Free and Spore are the only tiers a personal (`scope_user`) plan may hold.

**Why.** A team plan is priced *per member*, so it needs a roster to count. On a lab the
roster is the membership; on a personal account there is only the buyer, so a personal
Lab plan would grant team features to an account with no team and bill exactly one seat
however large the real group. Activating on the lab is also what makes the plan cover
everyone at once — the PI and every member are seated in the same transaction.

**Where it lives.** `apps/billing/tiers.py` states the rule once
(`PERSONAL_TIERS`/`LAB_TIERS`/`DEPARTMENT_TIERS`, `validate_tier_for_scope`,
`TierScopeError`). It is enforced at every point a plan is **granted**:

- `services.provision_workspace` (the signup entry point; signup itself never asks for
  a tier, so this is a guard, not a behaviour change)
- `services.activate_lab_subscription` / `activate_department_subscription` — a
  mis-tiered plan cannot be switched on however it got there
- `Subscription.clean()` — catches the Django admin and any `full_clean()` path
- both admin dashboard write paths, with narrowed serializer `choices` so an
  out-of-scope tier is a 400 on the `tier` field

Deliberately **not** a database `CheckConstraint`: the rule is about *selling* a plan,
not about which rows may exist. A constraint would break historical rows and force a
data migration on billing data, and the entitlement read path must stay untouched so a
downgrade never loses anything.

**Pricing before purchase.** `OrgBillingSerializer` gained `member_count` (the roster)
and `activation_monthly_cents`. `seat_count` cannot be used pre-activation — every seat
is still PENDING, so it reads 0 — and quoting from it would show a five-person lab $0
and then bill for five. The lab's plan card shows `member_count × per-seat = total`
before the manager commits, and the button reads "Activate for N members".
