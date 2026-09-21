# Department head transfer

What remains of the account/lab management pass of 2026-09-20. Phases 0–4
shipped (lab role authority, pending-invite claim, granted institution, roster
UI, lab ownership transfer) and are recorded in `docs/changelog.md`; the
department half was deliberately deferred so the lab shape could be proven
first.

## Objective

Let a department head hand the department over, the way a lab owner can now
hand over a lab.

## Why it is a separate edit

`Department.owner` is a **foreign key on the department**, not a row in
`DeptMembership`. So the lab implementation does not port across directly:

- `transfer_lab_ownership` moves `role` and `is_lead` on one membership row.
  The department equivalent has to move `Department.owner` *and* the matching
  `DeptMembership.role`, and keep them consistent.
- `permissions.user_can_manage_department` reads `department.owner_id` as well
  as membership, so the rank rule that phase 0 gave labs
  (`LAB_ROLE_RANK`) has no department twin yet. Without one, the same
  escalation hole phase 0 closed for labs is presumably still open for
  departments: check `DeptMemberDetailView` and whatever sets a dept role
  before building the transfer on top.

## Phases

### Phase 5a — department authority runs downward

Mirror `LAB_ROLE_RANK` for `DeptMembership.Role`, and gate the department
member endpoints on it. Confirm first whether a dept admin can currently
promote themselves; if so this is a security fix, not a refactor, and should
ship on its own.

### Phase 5b — `transfer_department_ownership`

- Service moving `Department.owner` and both membership rows atomically,
  outgoing head → admin, audited as `department.ownership.transfer`.
- Route `POST /api/auth/departments/<pk>/transfer-ownership/`, both slash forms.
- Reuse the lab confirm dialog; the department members UI needs the same
  role/remove controls the lab roster got in phase 3.

**Validation:** `test_dept_ownership.py`, mirroring `test_lab_ownership.py`;
`uv run --project web/backend pytest web/backend/apps/accounts/tests/ -q`.

## Open question

Does a department head stepping down keep access to the labs under the
department, or only to the department record? The lab answer was "becomes an
admin, does not leave" — the department version needs the same decision made
explicitly before 5b.
