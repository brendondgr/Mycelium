# Dedicated Reminders Page

## Objective

Give reminders a visible home. Today a reminder is created from a card and then
disappears: there is no surface that lists what is set, when it will fire, or how to
change it. This plan adds `/app/reminders` (sidebar entry directly under **Saves**),
a full manage surface (edit lead times, retarget the channel, snooze, cancel,
reinstate, delete), and fixes the "set a second reminder on top of an existing one →
*Could not create the reminder*" bug that falls out of the same gap.

## The bug, precisely

`ReminderSubscription` carries two partial unique constraints
(`content_reminder_unique_user_content_kind`, `…_lab_content_kind`) over
`(target, content, deadline_kind)`. `reminders.create_subscription` calls
`objects.create(...)` unconditionally, so a second reminder on the same item + kind
raises `IntegrityError`, which no handler catches — a 500 the composer reports as
"Could not create the reminder." It also bites *after* a cancel: the cancelled row
still occupies the constraint, so a user can never re-arm a reminder they cancelled.

The fix belongs in the service, not the view: a repeat create on the same
(target, item, kind) is an **update** of the existing subscription.

## Assumptions

- Soft cancel stays the default destructive action (`state=cancelled`), matching
  `/mylo cancel`; a hard delete is offered separately for tidying the page.
- Reminders remain day-granular. The page reports the send *date* plus the target
  local hour (`Lab.send_hour_local` / Eastern 09:00 for personal), which is what the
  tick actually honours — it must not imply minute precision it does not have.
- The reminders list is scope-aware like Saves: personal scope shows personal
  reminders, a lab workspace shows that lab's reminders.
- No new model fields, so no migration.

## Phase 1 — Backend: services

`web/backend/apps/content/reminders.py`

1. `find_subscription(*, target_user, target_lab, content, deadline_kind)` — the one
   place the uniqueness tuple is expressed.
2. `update_subscription(sub, *, offsets, mentions, channel_id_override, ...)` —
   replaces offsets (dedupe + cap reused), replaces mentions, re-seals backdated
   offsets against the current `due_date`, clears `snoozed_until`, and returns the row
   to `ACTIVE` when it was cancelled/stale/fired-out.
3. `create_subscription` delegates to `update_subscription` when a row already exists,
   returning `(subscription, created: bool)` via a new `create_or_update_subscription`
   so existing callers of `create_subscription` keep their shape.
4. `set_snooze(sub, until)` / `cancel(sub)` / `reinstate(sub)` small state helpers so
   the API, `/mylo`, and tests share one definition.

## Phase 2 — Backend: API

`web/backend/apps/content/reminders_views.py`, `urls.py`

- `ReminderSerializer` gains: `lab_name`, `snoozed_until`, `can_manage`,
  `next_fire_date`, per-offset `fire_date`, `send_hour_local`, `timezone`,
  `updated_at`. Fire dates are computed with the same `offset_fire_date` the tick
  uses, so the page cannot drift from delivery.
- `GET /api/reminders/` — unchanged shape, plus `?state=` filter and stable ordering
  (active first, then due date).
- `POST /api/reminders/` — now upserts: **201** on create, **200** on update. Kills
  the IntegrityError path.
- `PATCH /api/reminders/<id>/` — offsets, `channel_id_override`, mentions,
  `snoozed_until` (null to clear), `state` (`active` to reinstate, `cancelled` to
  cancel). Same authorization as DELETE (owner, or lab PI/admin) and the same
  entitlement gate as create.
- `DELETE /api/reminders/<id>/` — soft cancel (unchanged); `?purge=1` hard-deletes.

Authorization/audit: every write re-checks owner-or-`user_can_edit_lab_profile` and
`reminder_access`, so a lapsed plan cannot edit its way around the gate.

## Phase 3 — Frontend data layer

`web/app/src/lib/portal/{types,client,mutations,hooks}.ts`

- `Reminder` type extended to match the serializer; new `ReminderUpdateInput`.
- `updateReminder(id, input)`, `deleteReminder(id, { purge })`.
- `useReminderMutations()` gains `update` and keeps `remove`; both invalidate
  `["portal","reminders"]` and the bell.

## Phase 4 — Frontend page

- Route `web/app/src/app/app/(workspace)/reminders/page.tsx`.
- Section `web/app/src/components/portal/sections/reminders-section.tsx`:
  grouped **Upcoming**, **Snoozed**, **Finished & cancelled**; each row shows the
  item title (linked), area + deadline kind, due date with days-left, scope (Just me
  / lab + channel), the lead-time chips with their computed send dates, the next send
  date + local hour, and mentions.
  Actions per row: Edit, Snooze (1 day / 1 week / until a date), Cancel, Reinstate,
  Delete — gated by `can_manage`.
- `SectionKey` `"reminders"` + `SECTION_ROUTES` entry in `lib/portal/routes.ts`;
  sidebar entry under Saves (`portal-sidebar.tsx`) and mobile nav (`portal-mobile-nav.tsx`).
- The offset builder is extracted from `reminder-composer.tsx` into
  `reminder-offsets-field.tsx` and shared with the edit modal, so the two surfaces
  cannot disagree about what a valid lead time is.
- States covered: loading, empty, error, gated (reuses `ReminderGate` copy), lab
  member without manage rights (read-only), stale/pruned item (no link), mobile.

## Phase 5 — Docs + validation

- `docs/repo-map.md`: new rows for the reminders page and the manage API; update the
  reminder API row (upsert + PATCH).
- `docs/changelog.md` entry.

Validation, from the repository root:

- `uv run --project web/backend pytest apps/content/tests -k reminder`
- `uv run --project web/backend ruff check` on touched files
- `npm run lint --prefix web/app`, `npx tsc --noEmit`, `npm run build --prefix web/app`
  (the browser preview is pinned to the main checkout, so a worktree change is
  verified by type-check + lint + build rather than a live page)

Acceptance:

1. Setting a reminder twice on the same item + kind succeeds and shows one reminder
   with the newest lead times — no error.
2. Cancelling then setting again re-arms the same reminder.
3. `/app/reminders` lists every reminder with its due date and computed send dates.
4. Edit / snooze / cancel / reinstate / delete all round-trip and re-render.

## Exclusions

- No new delivery channels, no sub-day scheduling, no per-user timezone field.
- No changes to the tick, the outbox, or `/mylo` command behaviour beyond reusing the
  shared state helpers.
