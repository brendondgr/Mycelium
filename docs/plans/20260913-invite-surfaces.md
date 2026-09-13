# Put the invite panel where people invite from

**Status:** proposed, 2026-09-12.
Working document — delete on ship and record the outcome in `docs/changelog.md`
and `docs/repo-map.md`.

---

## Objective

Make the two ways of inviting — **per-person email invitations**, each locked to
the address it was sent to, and **one open link** anybody may join through —
available from the two places a manager actually invites from: the lab's
**Members** page and **Lab settings**. One panel, mounted everywhere, rather than
three surfaces disagreeing about what inviting is.

## What is wrong now

The invite work landed in the service layer, the API, and a component — but the
component is mounted on a surface nobody invites from.

| Surface | Route | Invite UI today |
|---|---|---|
| **Members** | `/app/members` → `MembersSection` | `members-section.tsx:54-65`: the button is hardcoded `disabled` with `title="Inviting — coming soon"`. Dead control. |
| **Lab settings** | `/app/profile` in lab scope → `LabSettingsSection` | `lab-settings-section.tsx:93` mounts only the **legacy** `InviteCard` — one username, existing accounts only, nothing mailed. |
| Labs → lab detail | `/app/labs` → `LabDetail` | `labs-section.tsx:392` — the only place `OrgInviteCard` renders, stacked above the legacy card. |

Two further defects fall out of the same cause:

- The legacy card's own helper text reads *"To reach someone who may not have an
  account, use an invitation above."* On Lab settings **there is nothing above**.
  The sentence was written for the labs-detail layout and is simply false on the
  page most managers land on.
- `LabDetail` shows two invite cards doing adjacent jobs, so the same lab offers
  two different invite UIs depending on which way you came in.

## Decisions taken

- **The Members button opens a dialog**, rather than linking away to Lab
  settings. The intent to invite forms while looking at the roster; bouncing the
  manager to another page to act on it loses the thing they were looking at.
- **The legacy username invite becomes a third tab** on the same panel, not a
  second card. The user's call was "do what you think is best": three tabs on one
  control is what makes every surface show the same thing, and it retires the
  false "above" copy rather than rewording it per surface.

## Assumptions

- **No backend change.** Every endpoint this needs already exists and is tested:
  the batch/link routes from the last change, and the legacy
  `labs/<slug>/invitations/` route behind `useInviteToLab`.
- **The username tab is lab-only.** `LabInvitation` has no department form, so the
  panel shows two tabs for a department and three for a lab. The component already
  branches on `kind`, so this is a condition, not a fork.
- **Departments keep what they have.** `department-section.tsx` already mounts the
  panel on the department's own settings page, which *is* the surface a department
  manager invites from. Nothing to move there.
- **Members is lab-scoped via the workspace switcher**, not a route param — it
  reads `currentLab` from `usePortal()`. With no lab picked it already shows "Pick
  a lab to see its members", so the invite button must be absent in that state
  rather than open a dialog with nothing to invite to.

---

## Phase 1 — One panel with three ways in

**What.** Fold the legacy username invite into `org-invite-card.tsx` as a third
tab and make the panel reusable in a dialog.

**How.**

- Add `"member"` to the `Tab` union; tab strip renders `By email`, `Share a link`,
  and — only when `kind === "lab"` — `Already on Mycelium`.
- Move the body of `InviteCard` (`labs-section.tsx:557-625`) into the new tab:
  username field, role select, submit, its own success/error lines. It keeps using
  `useInviteToLab(id)`; on a department the hook is never reached.
- Rewrite that tab's helper text. The old sentence pointed "above" at a card that
  may not be there; the new one states the trade the tab actually makes — lands in
  that person's notifications, nothing mailed, only works if they already have an
  account.
- Split the panel in two exports so it can live in a card *or* a dialog:
  `OrgInvitePanel` (the form and the open-invitations list, no card chrome) and
  `OrgInviteCard` (today's `Card` + heading wrapper around it). Existing mounts
  keep using `OrgInviteCard` and do not change.
- Keep the unverified-account note on the card wrapper, where it is today.

**Why.** Three surfaces must not drift. One component with one set of tabs is the
only arrangement where fixing invite copy fixes it everywhere.

**Validate.** `npx tsc --noEmit --incremental false -p app/tsconfig.json` and
`npx eslint src` from `web/app`.

## Phase 2 — Lab settings gets the panel

**What.** Mount `OrgInviteCard` in the Lab settings left rail, replacing the
legacy card.

**How.**

- In `lab-settings-section.tsx`, swap `<InviteCard lab={lab} />` for
  `<OrgInviteCard kind="lab" id={lab.slug} canInvite isVerified={user.isVerified} />`.
  The section is already manager-gated as a whole (`canManageLab`, line 59), so
  `canInvite` is settled; `isVerified` comes from `usePortal()`.
- Keep it in the same slot in the rail — between the logo card and the Discord
  cards — so the page's shape does not move for anyone used to it.
- Delete the now-unused `InviteCard` export from `labs-section.tsx`, and its
  `useInviteToLab` import.

**Why.** This is the page whose own subtitle already promises "invite members",
and the page whose invite card was telling people to use a control that was not
on it.

**Validate.** As Phase 1, plus load `/app/profile` in lab scope.

## Phase 3 — The Members button comes alive

**What.** Replace the disabled "Invite member" button with one that opens the
panel in a dialog.

**How.**

- `members-section.tsx`: derive `canManage = currentLab ? canManageLab(currentLab)
  : false` and render the button only when there is a lab **and** the viewer may
  manage it. A non-manager sees the roster with no button, which is honest — there
  is no permission error to explain because there is no control to press.
- Button opens `<Modal label="Invite people to <lab>">` (the existing primitive —
  it already traps focus, restores it to the opener, and closes on Escape) with
  `ModalHeader` plus `OrgInvitePanel`.
- Keep the `PlusIcon` and the label so the control the user already knows is the
  one that now works.
- After an invitation sends, leave the dialog open. A manager inviting from the
  roster is usually inviting several people, and the sent/refused report and the
  open-invitations list are both inside the panel.

**Why.** This was the control the user pressed. It has read "coming soon" while
the whole mechanism behind it shipped.

**Validate.** As Phase 1, plus `/app/members` in lab scope as a manager, as a
plain member, and with no lab picked.

## Phase 4 — Lab detail stops showing two cards

**What.** `LabDetail` keeps one panel.

**How.** Drop the `<InviteCard lab={lab} />` line at `labs-section.tsx:399`; the
`OrgInviteCard` above it now carries the username tab that card used to be.

**Why.** Same lab, same question, one answer, whichever route the manager took.

**Validate.** As Phase 1, plus `/app/labs`.

## Phase 5 — Documentation

- `docs/repo-map.md` — the invite row names all three lab surfaces plus the
  department one, and records that the panel carries all three ways in.
- `docs/changelog.md` — one entry, correlation ID `20260913-invite-surfaces`.
- Delete this plan file.

---

## Interfaces that change

| Surface | Change |
|---|---|
| `org-invite-card.tsx` | New `OrgInvitePanel` export; `OrgInviteCard` wraps it; new lab-only `Already on Mycelium` tab |
| `labs-section.tsx` | `InviteCard` export removed; second invite card unmounted |
| `lab-settings-section.tsx` | Mounts `OrgInviteCard` in place of `InviteCard` |
| `members-section.tsx` | Live, manager-gated "Invite member" button opening a dialog |

No API, model, migration, or backend change. No new route.

## Acceptance criteria

- From **Members**, a lab manager can invite several people by email in one go and
  can create a share link, without leaving the page.
- From **Lab settings**, the same, in the left rail.
- Both surfaces offer the identical panel, because it is the identical component.
- A plain member sees no invite button on Members; with no lab picked, none either.
- No page shows two invite cards, and no copy refers to a control that is not on
  the page.
- An unactivated manager is told to verify, as before.
- Typecheck and eslint clean for `web/app`.

## Excluded

- Any backend, API, or model change; the endpoints are done and tested.
- Any change to how invitations behave once sent — binding, budget, expiry,
  redemption, auto-join at sign-up are all unchanged.
- A department Members page (there is none; the department's roster is a card on
  its settings page).
- Retiring the legacy `LabInvitation` mechanism itself.
