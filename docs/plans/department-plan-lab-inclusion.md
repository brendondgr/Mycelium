# Department plan: per-lab inclusion (opt-in)

**Status:** in progress
**Worktree:** `.claude/worktrees/dept-plan-inclusion` (branch `worktree-dept-plan-inclusion`, based on `main`/`6e5e221`)

## Objective

Today, when a department's plan is active, **every** lab under it is automatically included — its members are seated ACTIVE department-paid (`activate_department_subscription` / `attach_lab_to_department` seat `effective_member_ids`, and `seat_sync.paying_scope_for_lab` routes any dept-attached lab's members to the department). The department head has no say over *which* labs the plan pays for.

Make lab inclusion an **explicit, opt-in choice** by the department head (owner/admin): a lab under a department is on the plan only when the head includes it. Excluding a lab stops the department from paying for its members (they fall back to the lab's own plan, or Free), without hiding the lab/its people from the department.

## Decision (user, 2026-07-20)

- **Opt-in (default OFF).** A newly-attached lab is not on the department plan until the head includes it. **Grandfather** already-attached labs to included=True via a data migration so no current member loses their seat on deploy.
- Inclusion affects **billing/seats only** — never `effective_member_ids` (which drives department visibility/access and profile aggregation). Excluding a lab from the *plan* must not remove its people from the *department*.

## Design

`seat_sync.paying_scope_for_lab(lab)` is the single chokepoint that decides who pays for a lab's members; gating its "department" branch on the new flag makes every membership path (invite-accept, member endpoints) respect inclusion automatically.

### Backend
1. `accounts/models.py` — `Lab.department_plan_included` (BooleanField, default False, help text). Only meaningful while `department_id` is set.
2. Migration + **data migration**: set `department_plan_included=True` for every lab with a non-null `department_id` (grandfather existing setups).
3. `accounts/services.py` — `plan_member_ids(department)` = direct dept members ∪ members of **included** labs (the billing-only twin of `effective_member_ids`).
4. `billing/seat_sync.py` — `paying_scope_for_lab`: the department branch requires `lab.department_plan_included`.
5. `billing/services.py`:
   - `activate_department_subscription`: seat `plan_member_ids` (not `effective_member_ids`).
   - `attach_lab_to_department`: gate the seating loop on `lab.department_plan_included` (a freshly-attached, not-yet-included lab is a no-op on seats — it just gets the FK).
   - New `set_lab_plan_inclusion(lab, included)`: flip the flag; if the dept plan is active, on **include** seat each lab member department-paid + schedule removal of their now-redundant lab seat; on **exclude** schedule removal of the dept seat for members no longer covered by `plan_member_ids`, re-seating them lab-paid when the lab has its own active plan (B2 fallback).
6. `accounts/services.py` — `detach_lab_from_department`: use `plan_member_ids` for the "remaining" set; reset `department_plan_included=False` on detach. `department_labs_payload`: add `included_in_plan`.
7. `accounts/views.py` `DeptLabDetailView`: add `patch` → `{included_in_plan: bool}` → `set_lab_plan_inclusion` (owner/admin gated). Routes already exist (slash + no-slash).

### Frontend
8. `lib/portal/{mutations,hooks,types}.ts`: `DeptLabRow.included_in_plan`; `setLabPlanInclusion(deptId, slug, included)` + `useSetLabPlanInclusion`.
9. `components/portal/sections/department-section.tsx`: an "In plan" toggle per lab (manager-only), with a hint that excluding stops the department paying for that lab's members.

## Validation
- `uv run --project web/backend pytest apps/billing apps/accounts -q` — new tests: `paying_scope_for_lab` respects the flag; `plan_member_ids`; activation seats only included labs; toggle include/exclude grants/defers seats; grandfather migration; detach resets the flag. Existing activation/seat-sync/org-management suites stay green.
- Frontend: `tsc --noEmit` + `eslint` + `next build` clean.

## Security / permissions
- Toggle gated on `user_can_manage_department` (owner/admin), matching attach/detach.
- Audit event `dept.lab.plan_inclusion` on every change.
- No change to visibility/access (`effective_member_ids` untouched).

## Exclusions
- No proration/credit changes (removal stays deferred via `schedule_seat_removal`/the billing tick).
- Direct department-member seating unchanged.
- No bulk "include all" action this pass (per-lab toggle only).
