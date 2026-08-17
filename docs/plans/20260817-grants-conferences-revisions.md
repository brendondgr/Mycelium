# Grants & Conferences Revisions — Implementation Plan

**Correlation ID:** `20260817-grants-conferences-revisions`
**Mode:** B — direct on `main`, no worktree.
**Status:** working document. Delete once shipped; record the outcome in
`docs/changelog.md` + `docs/api-contract.md` + `docs/repo-map.md`.

---

## Objective

Seven revisions to the grants/conferences surface, ordered so the highest-value
and highest-risk work (stale-conference removal, per-round alerts) lands on a
foundation the rest builds on.

The single most important outcome: **a conference that has completely passed is
removed, hidden, and shown to nobody.**

---

## Decisions taken (from the user, this session)

| # | Decision |
|---|---|
| D1 | **Full per-round deadline rows.** Widen `ContentDeadline` beyond `(content, kind)` so every dated round is individually addressable and remindable. |
| D2 | **Dateless conferences: hide from feeds + prune when stale.** Never serve a conference with no actionable future date; delete it once the collector has not re-seen it inside the staleness window. |
| D3 | **`@everyone` is opt-in, manager-only.** `parse: []` stays the default; `parse: ["everyone"]` is set only when a lab PI/owner/admin explicitly chose it for that alert. Scraped text stays escaped regardless. |
| D4 | **Mention targets: any guild member**, plus roles, plus `@everyone` — presented as a **tabbed** picker (Roles / Everyone / People) so the three do not flood one another. |

## Assumptions

- A1 — "Alert" and "reminder" are the same feature. All work lands on the
  existing `ReminderSubscription` stack; no second notification system.
- A2 — Reminders stay behind the existing entitlement gate
  (`apps.content.reminder_access`: a paid plan + synced Discord). Per-round
  selection and mention tagging add no new tier gate; they are refinements of a
  capability that is already gated. Read through `billing.entitlements` only.
- A3 — Lab mention targeting stays **PI / owner / admin only**, matching the
  existing `user_can_edit_lab_profile` rule for creating a lab reminder.
- A4 — Grants get per-round rows too. `_grant_deadlines` already computes
  `rounds`; once the schema is round-aware, emitting one row per round is the
  same code path. Flagged rather than silently scoped out — see Exclusions.
- A5 — Everything the feed does must work identically for personal / lab /
  project targets, through the shared `_accumulated_scores` path.

## Open questions (non-blocking; resolve during Phase 3)

- Q1 — `round_key` stability. The key must survive a re-scrape so a reminder
  keeps pointing at the same round and `changed_at` stays meaningful. Preference
  order: the collector's own `round_label` (slugified) → ordinal within its kind
  by instant. **Measure `round_label` coverage on the live corpus first**, then
  pick; record the number in the changelog entry.

---

## Phase 1 — Delete the trust-tier system (item #3)

Trust tier labels reputable venues as "has not demonstrated legitimacy". It is
removed outright, not softened. Rank badges (CCF / CORE) and the dblp registry
stay — only the tier goes.

**Backend**

- `apps/scraper/collect/conferences/resolve.py` — drop `assign_trust_tier`.
- `apps/scraper/collect/conferences/store.py` — drop the `trust_tier` column /
  field from the series store (migration of the collector SQLite store).
- `apps/scraper/collect/mapping.py` — stop writing `metadata["trust_tier"]`.
- `apps/content/serializers.py` — remove `trust_tier` from `ConferenceSerializer`.
- `apps/content/views.py` — drop `TRUST_TIER_EXPLANATIONS` and the `trust_tiers`
  key from `RankingReferenceView`.
- `apps/content/briefing.py`, `apps/content/daily_report.py` — drop the field.
- `manual_all.py` — drop the `assign_trust_tier` reference in the stage prose.

**Frontend**

- `sections/conferences-section.tsx` — delete `TrustTierBadge`,
  `TRUST_TIER_TOKEN`, its render site, and the now-unused `ShieldIcon` import.
- `sections/conference-filters.tsx` — delete the `trustTier` facet from state,
  defaults, options, the filter predicate, and the rail UI.
- `lib/portal/types.ts` — delete `TrustTier` and `RankingReference.trust_tiers`.

**Docs** — `docs/api-contract.md` (the conference payload + ranking-reference
sections), `docs/repo-map.md` (the "dblp venue registry (trust tiers, CORE
ranks)" row).

**Validation**

```bash
uv run --project web/backend pytest web/backend/apps/scraper/tests web/backend/apps/content/tests -q
```

Plus `npm --prefix web run lint` and a typecheck. Acceptance: no `trust_tier`
identifier survives anywhere in the repo (`grep -rn trust_tier` is empty except
a changelog entry).

---

## Phase 2 — Remove and hide passed / dateless conferences (item #6 + the headline outcome)

Measured on the live corpus (2026-08-17): 912 conferences, **156 with no date at
all** (`prune_after == ""` — no deadline, no event date; mostly OpenReview
journals and rolling CFPs). `prune_expired` can never remove those, so they show
forever. Zero conferences currently have a *past* `prune_after`, so the dated
half of expiry already works; the gaps are the dateless half and read-time
hiding.

**2a — Prune the dateless-and-stale (`apps/scraper/collect/ingest.py`)**

Extend `prune_expired` with a second rule, kept separate and separately logged:

- an item whose `prune_after` is empty **and** whose `last_seen` is older than
  `settings.OPPORTUNITY_STALE_DAYS` (default **60**) is deleted.
- `last_seen` is already stamped on every upsert that sees the record, so an
  entry the source still lists is never removed by this rule.
- deletion continues to go through the ORM `.delete()` so the `pre_delete`
  reminder-stale backstop fires.

**2b — Hide at read time (`apps/content/views.py`)**

The prune is nightly; the feed must not depend on it having run. Add one shared
predicate and apply it wherever conference scores are read:

- a conference is **shown** only if it has at least one future dated deadline or
  a future event date;
- generalise `_drop_passed_conferences` (today digest-only, and it *keeps*
  blank-deadline rows) into that predicate and apply it in `_accumulated_scores`
  so personal, lab, and project feeds all inherit it (A5).

**2c — One-off purge of what is already in the database**

Extend `prune_opportunities` with `--stale-only` / `--dry-run` so the existing
156 rows can be reviewed and then removed in one pass, rather than waiting out a
60-day window.

**Validation**

```bash
uv run --project web/backend pytest web/backend/apps/scraper/tests/test_collect_ingest.py web/backend/apps/content/tests -q
```

Then, against the Compose Postgres, a dry run:

```bash
docker compose exec backend sh -lc 'cd /app/web/backend && uv run python manage.py prune_opportunities --stale-only --dry-run'
```

Acceptance: the conferences feed serves **zero** items whose every date is in
the past or absent; the dry run names the 156 rows; a rolling CFP the collector
re-saw today is not pruned.

---

## Phase 3 — Per-round deadlines (item #5, backend)

The core change. Today `ContentDeadline` is unique on `(content, kind)` and
holds only the *next future* date per kind — plan D1 in the old design said "a
specific non-next round is never individually remindable". D1 above reverses
that.

**3a — Schema**

- `ContentDeadline` gains `round_key` (stable slug, `""` for a single-round
  item), `round_label` (human, e.g. "Workshop track"), and `is_next` (this row
  is its kind's next future occurrence — what the card headline reads).
  Unique key becomes `(content, kind, round_key)`.
- `ReminderSubscription` gains `deadline_round_key` + a `round_label` snapshot
  field. Both partial unique constraints widen to include it.
- Migration backfills `round_key = ""` on every existing row, then rebuilds the
  projection.

**3b — Derivation (`apps/content/deadlines_projection.py`)**

- `_conference_specs` emits **one spec per future dated entry** of
  `deadlines_structured`, not one winner per kind. `is_next` marks the earliest
  per kind.
- Add the **EVENT row** conferences have never had, derived from
  `metadata["event_start"]`. The requirement explicitly allows an alert that
  "concerns the event itself", and there is currently nothing to point it at.
- `_grant_specs` emits one row per round from the rounds `_grant_deadlines`
  already computes (A4), `is_next` on the selected next round.
- Resolve Q1 (round-key stability) here and document the rule in the module
  docstring.

**3c — Reminder services (`apps/content/reminders.py`)**

`find_subscription`, `create_or_update_subscription`, `resync_snapshot`,
`idempotency_key`, and `reminder_copy` all become round-aware. `reminder_copy`
must name the round when the item has more than one deadline — "Full paper
(Round 2) due Mar 3 — 14 days left" — and say "Event" when it is the event row.

**3d — Announcements (`apps/content/reminders_announce.py`)**

Match on `(content, kind, round_key)` so a moved round announces against its own
subscription, not the kind's.

**3e — API (`serializers.py`, `reminders_views.py`, `docs/api-contract.md`)**

- `addressable_deadlines[]` entries gain `round_key`, `round_label`, `is_next`.
- Reminder create/read carry `deadline_round_key` + `round_label`.
- New POST routes (if any) register both trailing-slash forms.

**3f — Discord `/mylo`**

The `/mylo` reminder subcommands and the outbox copy must state which deadline
an alert is for whenever the item has more than one.

**Validation**

```bash
uv run --project web/backend pytest web/backend/apps/content/tests -q
```

pgvector-touching tests need the Compose Postgres (`DATABASE_URL` at `:11450`).
Acceptance: a conference with an abstract deadline, two paper deadlines, and an
event date exposes five addressable rows; two independent reminders can be set
on the two paper deadlines; a date move on round 2 re-opens only round 2.

---

## Phase 4 — The alert composer as a true full-page modal (item #1)

**Root cause found.** `ReminderComposer` already renders `fixed inset-0 … 
backdrop-blur-sm`. It behaves as an inline panel because every feed card is
wrapped by `RevealOnScroll`, whose `portal-fade-up` animation is declared
`animation-fill-mode: both` — so the wrapper retains `transform: translateY(0)`
forever, and a non-`none` transform makes that wrapper the containing block for
any `position: fixed` descendant. The modal is therefore scoped to its card, the
backdrop covers only the card, and everything outside stays clickable. Exactly
the reported symptom.

**Fix**

- Add a shared `components/portal/primitives/modal.tsx` that renders its
  children through `createPortal(…, document.body)`, escaping every transformed
  ancestor by construction.
- It owns: centered layout, dimmed + blurred backdrop, Escape to close,
  click-outside to close, body scroll lock, focus trap, focus restore on close,
  `role="dialog"` + `aria-modal`, and a reduced-motion-respecting entrance.
- Port `ReminderComposer` and `ReminderEditor` onto it; audit
  `primitives/editor-modal.tsx` and the profile/lab/project editor modals for
  the same containing-block trap and port any that are affected.

**Validation** — browser-verified against the Compose stack at
`http://localhost:11050`: open the composer from a card deep in the feed,
confirm the backdrop covers the viewport, that a control behind it cannot be
clicked or tabbed to, and that Escape returns focus to the bell.

---

## Phase 5 — Deadlines listed under Save / Set a reminder (item #4)

Replace the `DeadlineRoundsButton` popover on the conference card with an
inline list in the actions area, beside Save and Set a reminder.

- Each row: kind + round label, the date, an estimated marker when the
  collector flagged it, and a per-row **Set alert** control that opens the
  Phase 4 modal **pre-selected to that round** — which is what makes items #4
  and #5 one gesture rather than two.
- Rows for passed deadlines are shown struck/muted rather than hidden, so a
  reader can see the round they missed; they are not selectable for an alert.
- Same treatment on the grants and fellowships cards wherever
  `DeadlineRoundsButton` is used today, and on the Saves page card.
- Keep the states `docs/styles.md` requires: loading, empty (no dated
  deadline), populated, permission-denied (the entitlement gate), mobile,
  keyboard, contrast, reduced motion.

**Validation** — lint + typecheck + browser verify at three widths (mobile,
tablet, desktop), and confirm the list scrolls inside its own container rather
than widening the card.

---

## Phase 6 — Discord tagging for alerts (item #2)

**6a — Discord API (`apps/integrations/services/discord_api.py`)**

- Add `get_guild_roles(guild_id)` and `get_guild_members(guild_id)`.
- `create_message` / `create_message_with_attachment` gain an explicit
  `mention_everyone: bool = False`. Only that flag can set
  `parse: ["everyone"]`; absent it, `parse` stays `[]`. `escape_mentions` on
  interpolated scraped text is unchanged, so a scraped `@everyone` still cannot
  ping (D3, defense in depth).
- Document that the bot needs the **Mention Everyone** permission in the guild,
  and degrade honestly when it does not have it.

**6b — Model**

`ReminderMention` widens from "a Mycelium lab member" to a target union:
`kind ∈ {user, role, everyone}` + `discord_id`, with the existing `member` FK
kept nullable for a linked Mycelium user. The lab-membership check stays for the
`member` path; a raw `discord_id` is validated as belonging to **that lab's
guild** before it is stored, so Mylo can never be pointed at an unrelated server.

**6c — API**

`GET /api/labs/<slug>/discord/mention-targets/` → `{roles, members,
everyone_allowed}`. PI/owner/admin only (A3), object-level checked, audit-logged
like the other lab Discord reads. Degrades to an empty list with a reason when
the guild is unlinked or Discord is unreachable, matching `ChannelField`.

**6d — UI**

A **tabbed** mention picker in the composer (D4): **Roles · Everyone · People**,
one list at a time so the three never flood each other. Selected targets show as
removable chips beneath the tabs. Lab scope only — a personal DM has nobody to
tag. `@everyone` is a single explicit toggle inside its own tab with a plain
warning about who it reaches.

**Validation**

```bash
uv run --project web/backend pytest web/backend/apps/content/tests web/backend/apps/integrations/tests -q
```

Acceptance: a message with no explicit everyone opt-in still sends
`parse: []`; a scraped title containing `@everyone` never pings under any
combination; a non-manager gets 403 from the mention-targets endpoint.

---

## Phase 7 — Detect updated source pages and re-suggest (item #7)

Conferences (and grants) are extracted from pages hosting many events; when a
page gains new content the old entries stay. `upsert_items` already computes
`unchanged` per record — that is the hook.

- On a **material** change (a new future entry in `deadlines_structured`, a
  changed `event_start`/`event_end`, or `open` flipping to true), stamp
  `metadata["refreshed_at"]` + `metadata["refresh_reason"]`. Cosmetic drift
  (a re-worded title, a moved URL) must not qualify, or everything is "updated"
  every night.
- `apps/content/pinning.py` re-pins on `refreshed_at` inside the pin window, the
  way `first_seen` pins a new item.
- Surface it as **"Updated"**, distinct from **"New"**. This respects the
  non-negotiable that *new* means "entered the Top-25", never "arrived today":
  the nightly whole-corpus re-rank already decides slate membership, and this
  only pins and labels an item whose source actually moved.
- No extra LLM spend: a refreshed item is re-written-up only if it enters the
  Top-25, which is the existing rule.
- Serializer gains `is_updated`; the card renders the tag.

**Validation**

```bash
uv run --project web/backend pytest web/backend/apps/scraper/tests/test_collect_ingest.py web/backend/apps/content/tests/test_pinning.py -q
```

Acceptance: re-ingesting a record with a new future round marks it updated and
re-pins it; re-ingesting a byte-identical record writes nothing and marks
nothing.

---

## Phase 8 — Documentation, changelog, commit

- `docs/api-contract.md` — conference payload (trust tier gone,
  `addressable_deadlines` widened, `is_updated` added), reminder create/read,
  the new mention-targets endpoint.
- `docs/repo-map.md` — the dblp registry row, the new `modal.tsx` primitive,
  any new module.
- `docs/architecture.md` — only if a boundary moved.
- `docs/changelog.md` — one entry per phase, schema per
  `docs/skills/global.md`, correlation ID `20260817-grants-conferences-revisions`.
- Delete this plan file.

Commit after each phase validates. Do **not** push.

---

## Public surface that changes

| Surface | Change |
|---|---|
| `GET /api/conferences/` | `trust_tier` removed; `addressable_deadlines[]` gains `round_key`/`round_label`/`is_next`; `is_updated` added; passed & dateless conferences no longer served |
| `GET /api/ranking-reference/` | `trust_tiers` key removed |
| `POST /api/reminders/` | accepts `deadline_round_key`; accepts role / user / everyone mention targets |
| `GET /api/reminders/` | rows carry `deadline_round_key` + `round_label` |
| `GET /api/labs/<slug>/discord/mention-targets/` | **new** |
| `manage.py prune_opportunities` | `--stale-only`, `--dry-run` |
| DB | `ContentDeadline` +3 columns, new unique key; `ReminderSubscription` +2 columns, widened unique keys |

## Explicit exclusions

- No change to ranking, retrieval, fusion, or scoring logic — so the evaluation
  harness is not implicated and no research-record experiment is required.
- No new billing tier or entitlement (A2).
- Fellowship deadlines stay single-row (they are genuinely one application
  deadline); only the schema becomes round-aware.
- No redesign of the conferences filter rail beyond deleting the trust-tier
  facet.
- Grants get per-round rows (A4) but no other grant-specific UI work.
