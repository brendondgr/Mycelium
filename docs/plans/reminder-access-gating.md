# Reminder Access Gating — Discord sync + paid plan

## Objective

Deadline reminders are a **Discord-delivered, paid** capability. Today they are
neither: `POST /api/reminders/` accepts any authenticated user, and the tick DMs
whoever has a linked identity regardless of tier. This change makes both
conditions explicit and enforced everywhere the affordance appears.

Two gates, applied identically to **grants, fellowships and conferences**, in both
personal and lab scope:

1. **Discord must be synced.** Personal → an ACTIVE `DiscordIdentity`. Lab → an
   active `DiscordGuildLink` for that lab.
2. **An active paid plan must cover the actor.** Personal → the user's effective
   tier is Spore or better, which by construction already includes a user seated on
   a lab's or department's paid plan (`covering_subscriptions` unions the personal
   plan with active seats). Lab → the lab (or its department) carries a paid tier.

Free accounts — personal or inside a free lab — cannot create a reminder and are
never messaged.

## Assumptions

- "Paid plan" = any tier above Free. Expressed as a named feature, not a tier-name
  check, per architecture decision A1.
- A user whose seat is paid for by their lab is individually entitled. This already
  falls out of `entitlements.covering_subscriptions`; no new billing logic.
- A lab reminder's Discord requirement is the **guild link**, not the creating
  manager's personal identity — the message posts to a channel, not a DM.
- In-app `Notification` rows stay outside this gate: the gate is on *creating* a
  reminder and on *Discord delivery*. A user who downgrades after subscribing keeps
  the in-app trail but stops being DMed. Nothing is deleted on a billing event.
- Reminders created without a `created_by` (system/internal paths, the tick's own
  bookkeeping) are not gated — mirroring the existing lab-manager check, which is
  likewise only applied to user-initiated creates.

## Phases

### 1. Entitlement vocabulary

- `web/backend/apps/billing/entitlements.py`: add
  `Feature.DEADLINE_REMINDERS = "deadline_reminders"` to the intelligence line
  (`_SPORE`), so Spore / Lab / Canopy inherit it and Free does not.

### 2. The access rule (one module, one answer)

- New `web/backend/apps/content/reminder_access.py`:
  - `ReminderAccess` dataclass — `allowed`, `plan_ok`, `discord_ok`, `reason`
    (`""` | `"plan"` | `"discord"` | `"plan_and_discord"`), plus a human `detail`.
  - `personal_reminder_access(user)` — `has_feature(user, DEADLINE_REMINDERS)` ∧
    `resolve.active_identity_for_user(user)`.
  - `lab_reminder_access(lab)` — `lab_has_feature(lab, DEADLINE_REMINDERS)` ∧ an
    active guild link via `resolve.get_guild_link_for_lab(lab)`.
  - Discord state is read only through `integrations.services.resolve` (the single
    ORM boundary); this module imports no integration model.

### 3. Enforcement at create + at delivery

- `apps/content/reminders.py::create_subscription` — the backstop, alongside the
  existing lab-manager rule: when `created_by` is set, refuse with `ReminderError`
  if the relevant access is not allowed.
- `apps/content/reminders_views.py` — map the refusal to **403** (not 400) so the
  UI can distinguish "you can't" from "bad input"; personal and lab both.
- `apps/content/reminders_discord.py` — refuse to queue when the recipient is no
  longer entitled: `send_personal_dm` checks the target user, `send_lab_channel`
  checks the lab. New `SendOutcome.not_entitled` flag; the tick keeps its in-app
  delivery and simply records no Discord channel. This closes a hole that predates
  this change (`entitlements.can_dm` existed and was never called from the reminder
  path).

### 4. Read surface for the UI

- `GET /api/reminders/access/?lab=<slug>` (`ReminderAccessView`) → the same
  dataclass, serialized. One authoritative answer so the button state cannot drift
  from the server rule. Unknown/inaccessible lab → 404/403 as elsewhere.

### 5. Frontend

- `lib/portal/types.ts`: `FEATURE.DEADLINE_REMINDERS`, `ReminderAccess` type.
- `lib/portal/client.ts` + `hooks.ts`: `fetchReminderAccess` / `useReminderAccess(labSlug?)`.
- `components/portal/sections/opportunity-bits.tsx` — `RemindButton` renders a
  **muted, still-clickable** bell when access is denied (never a silently missing
  control), `aria-disabled` styling plus a `title` naming the missing condition.
- `components/portal/reminder-composer.tsx` — when access is denied it renders a
  gate panel in place of the form: what's missing and where to fix it (Profile →
  Connected services for Discord; Profile → Your plans for the plan), no submit.
- Because both live in the shared `RemindButton` / `ReminderComposer` pair, grants,
  fellowships, conferences and the Saves page all inherit the behaviour with no
  per-section changes.

### 6. Tests

- New `apps/content/tests/test_reminder_access.py`: free → 403; paid without
  Discord → 403; paid + Discord → 201; **lab-seated** user (personal plan absent,
  seat on a lab plan) → 201; free lab → 403 on a lab reminder; paid lab without a
  guild link → 403; delivery-time refusal for a downgraded user; the access
  endpoint's payload for each combination; and the same create asserted for a
  fellowship and a conference, not only a grant.
- Existing reminder suites are entitled at fixture level (a Spore subscription + an
  ACTIVE identity, an activated lab plan + guild link) rather than being weakened.

### 7. Docs

- `docs/repo-map.md` — reminder API, composer, and billing rows.
- `docs/changelog.md` — one entry per the global schema.

## Interfaces that change

| Surface | Change |
|---|---|
| `POST /api/reminders/` | now 403 when the actor lacks Discord sync or a paid plan |
| `GET /api/reminders/access/` | **new** — `{allowed, plan_ok, discord_ok, reason, detail}` |
| `GET /api/billing/me/` | `features[]` gains `deadline_reminders` for paid tiers |
| Reminder Discord delivery | skipped (in-app still written) when unentitled |

## Validation

- `uv run --project web/backend pytest apps/content/tests -k reminder` and the
  billing suite.
- `npm run --prefix web/app typecheck` / `lint` / `build` (or the root delegate).
- Manual: a Free account sees a muted bell that explains itself; a Spore account
  with no Discord sees the Discord gate; both conditions met → the composer.

## Exclusions

- No payment/checkout work — activation remains where it is.
- No change to who may *save* an item; saving stays free.
- No change to in-app notification delivery or to the daily report's own gate.
- No new lab-level reminder policy UI.
