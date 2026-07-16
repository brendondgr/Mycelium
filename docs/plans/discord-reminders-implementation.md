# Discord Reminders & Announcements — Implementation Plan

**Status:** Executable plan, reconciled against the codebase (2026-07-16)
**Source:** `discord-reminders-plan.md` (architectural v2)
**Owner:** BDGR

This is the *implementation-ready* version of the architectural plan. Every `[verified]`
claim in the source was re-checked against the current tree; this document records where
reality diverges and pins exact insertion points, commands, and acceptance tests. Read the
"Reconciliation" section first — several source assumptions are wrong now.

---

## Objective

Ship deadline reminders (personal DM + lab channel) and high-signal notifications for
grants, conferences, and fellowships, built on a normalized deadline projection and a
daily compute-on-read tick. Discord delivery reuses the existing `integrations` ORM
boundary and stdlib REST client; scheduling reuses the host `manual_all.py` daily chain.

---

## Reconciliation — how reality differs from the source plan

| # | Source assumption | Reality (verified) | Consequence |
|---|---|---|---|
| A | Mylo has an **HTTP interactions endpoint**; read `app_permissions` off the interaction payload for channel preflight | Mylo is a **gateway bot** (`discord.py`, `mylo/bot/`). No interactions webhook. Authorization is **Mycelium's** permission model, never Discord `app_permissions`. | §8 channel preflight cannot read `app_permissions`. Preflight = **attempt a real post via REST and branch on status** (mirrors `probe.py` DM pattern). Scheduled sends run from Django/Celery via `integrations/services/discord_api.py`, **not** the gateway. |
| B | `signals.suggested is True` is the **abstention flag** | `suggested=True` means the item **passed** the match-percent floor and is surfaced; `suggested=False` is the abstention/below-floor state. | §10.1 gate logic is correct (`suggested==True` = a real surfaced pick) but the *rationale wording* in the source is inverted. Gate on `suggested==True`. |
| C | `SavedOpportunity` carries `next_deadline`/`next_kind` | It carries `deadline_date` + `deadline_kind` (singular). No `next_*` fields. | Snapshot fields on `ReminderSubscription` mirror `deadline_date`/`deadline_kind`. `DeadlineKind` (APPLICATION/ABSTRACT/MANUSCRIPT/EVENT/OTHER) is reusable for `ContentDeadline`. |
| D | `DiscordGuildLink` gains `announcement_channel_id` + `channel_verified_at` | Fields **absent**. | R4 migration adds them to `integrations.DiscordGuildLink`. |
| E | Fellowship `deadline.type` ∈ {true, continuous, rolling, anticipated, varies} | Also **`suspended`** and **`unknown`** (7 total). | Confidence map must handle all 7. |
| F | `/mylo setup` needs creating and must bind the channel | `/mylo setup` **already exists** (`mylo/bot/cogs/status.py`, calls `linking.setup_guild()`). | R4 *extends* it (channel picker), does not create it. |
| G | Prune is a distinct daily step, reorderable to run after the tick | `prune_expired` is **called inside `ingest_pivot`** (`scraper/pivot/ingest.py:206`). The daily batch ingests+prunes in one stage (`run_daily_opportunities`). | R2 decouples prune: pass `prune=False` in the daily path; run prune as its own later stage after the tick. The prune→stale hook is the belt-and-braces safety for any path that still prunes early. |
| H | `TargetRecommendations` class with fellowship exclusion | Implemented as functions: `_recommendations_payload()` + `_interested_members()` in `content/views.py`; exclusion is a comment at `views.py:451`. `INTEREST_MATCH_THRESHOLD=70`. | R8 edits those functions, not a class. |
| I | `create_message` needs an `allowed_mentions` with explicit user IDs | `discord_api.create_message()` hardcodes `allowed_mentions={"parse": []}` (no `users`). | R3/R5 extend it to accept explicit `users` while keeping `parse:[]` default — so `<@id>` pings resolve. |

Confirmed as stated by the source (no change): deadline metadata shapes (grant flat
`deadline_date`, conference raw `deadlines` + `event_date`, fellowship nested
`deadline.{type,date,previous_date}`); `_kind_deadline` collapses per kind; upsert on
`(source, external_id)` with immutable `first_seen`; `SavedOpportunity.content` is
`SET_NULL` + `snapshot`; papers skip existing on re-scan; `RelevanceScore` exactly-one
multi-target via `core/db.py:exactly_one`/`validate_exactly_one`; `Lab` has no timezone;
`user_can_manage_lab`/`user_has_lab_access` are the gates; eligibility lives in
`Profile.interests["eligibility"]`; `resolve.py` is the sole Discord ORM boundary
(AST-enforced by `test_import_graph.py`); `AuditEvent` + `record_audit_event()` with
string actions; `NotificationsView` is compute-on-the-fly, no `Notification` model.

---

## Key code coordinates (from recon)

- Deadlines: `web/backend/apps/scraper/pivot/deadlines.py` (`parse_deadlines`, `submission_status`, `conference_status`, `_kind_deadline`, `first_event_date`); `pivot/status.py` (`opportunity_status`, `is_visible`); `content/search.py:_deadline_of`.
- Metadata build: `pivot/records.py:build_pivot_item` / `_build_fellowship_item`. Fellowship deadline parse: `pivot/fellowships/parsers.py:parse_deadline`.
- Ingest: `pivot/ingest.py` — `upsert_pivot_items` (L81), `prune_expired` (L147), `ingest_pivot` (L179, prunes at L206). Daily batch: `content/opportunities.py:run_daily_opportunities_batch` (L821).
- Models: `content/models.py` — `ContentItem` (L14), `SavedOpportunity` (L184, `DeadlineKind` L201), `RelevanceScore` (L90), `TARGET_FIELDS` (L11). Helpers: `core/db.py:exactly_one`/`validate_exactly_one`.
- Accounts: `accounts/models.py` — `Lab` (L48), `LabMembership` (L69), `Profile` (L154), `AuditEvent` (L462). `accounts/permissions.py` (gates). `accounts/services.py:record_audit_event` (L17). `accounts/interests.py:EligibilityContract`.
- Notifications: `content/views.py` — `DEADLINE_ALERT_DAYS` (L272), `NotificationsView` (L684), `_recommendations_payload` (L448), `_interested_members` (L414), `INTEREST_MATCH_THRESHOLD` (L47). Signals producers: `content/pipeline.py`, `content/opportunities.py`, `content/opportunity_llm.py`, `content/pinning.py`.
- Fellowships: `content/fellowships.py` — `Elig` (L71), `eligibility_from_profile` (L83), `evaluate_eligibility` (L115), `match_fellowships` (L307).
- Discord ORM: `integrations/models.py` (`DiscordIdentity` L24, `DiscordGuildLink` L104); `integrations/services/resolve.py` (boundary); `integrations/services/discord_api.py` (`create_message` L117, `open_dm_raw` L108 — no `get_guild_channels`); `integrations/services/probe.py` (send-and-branch pattern); `integrations/services/audit.py:discord_audit`.
- Mylo bot: `mylo/bot/cogs/status.py` (`/mylo setup` L90), `mylo/linking.py`, `mylo/mycelium.py` (`setup_django`, `db()`), `mylo/reporting.py` (stdlib REST `report()`).
- Orchestration: `manual_all.py` (`CONTAINER_STAGES` L99). Command pattern: `content/management/commands/`.
- Frontend: `web/app/src/components/portal/sections/saves-section.tsx` (`SaveMeta` L63, `SavedRow` L138), `notification-bell.tsx`, `profile-section.tsx:DiscordCard`. Data layer: `lib/portal/{client,hooks,mutations,types,routes}.ts`. Card exports: `GrantRow`, `FellowshipRow`, `ConferenceCard`, `SuggestionCard`, `SaveButton` (`opportunity-bits.tsx`).
- Tests: pytest + pytest-django. Run: `uv run --project web/backend pytest web/backend`. Migrations: `uv run --project web/backend python manage.py makemigrations|migrate`. Default DB SQLite (pgvector/FTS no-op in tests). New reminder models carry **no VectorField** → no pgvector migration dependency.

---

## Phased implementation

Ordering and dependencies preserve the source's phase graph. Each phase ends with a
commit (per the global skill) and its own validation.

### R0 — `ContentDeadline` projection + rebuild + change detection + `deadlines[]` API

**New model** `content.ContentDeadline` (plain relational, no VectorField):
`content` FK→ContentItem CASCADE `related_name="deadline_rows"`; `kind` (reuse
`SavedOpportunity.DeadlineKind`); `due_date` DateField null; `label` Char(200) blank;
`confidence` (new TextChoices CONFIRMED/ANTICIPATED/ROLLING/UNKNOWN); `changed_at`
DateTimeField null; `previous_due_date` DateField null (fellowship corroboration).
`UniqueConstraint(content, kind)`; `Index(due_date, kind)`.

**Derivation** (`content/deadlines_projection.py`, pure, reuses existing status fns):
- Conference → `parse_deadlines(metadata["deadlines"])` + `submission_status(...)`/`conference_status(metadata, today)` → ABSTRACT/MANUSCRIPT/EVENT rows; confidence CONFIRMED when a date parses, else UNKNOWN.
- Grant → `opportunity_status(metadata, "grant", today)` → one APPLICATION row.
- Fellowship → `metadata["deadline"]` → one APPLICATION row; confidence from `type`: `true`→CONFIRMED, `anticipated`→ANTICIPATED, `continuous`/`rolling`→ROLLING, `varies`/`unknown`/`suspended`→UNKNOWN; `due_date` null when ROLLING/UNKNOWN; carry `previous_date`.

**Rebuild hook:** inside `upsert_pivot_items` (after the upsert loop, before the
function returns / before `ingest_pivot` prunes). Read existing `ContentDeadline` rows
for the item, recompute, and for each kind: if `due_date` changed, set `changed_at=now`,
`previous_due_date=old`, emit `record_audit_event(action="opportunity.deadline.moved", target_type="content_deadline", target_id=<id>, metadata={old,new,kind})`,
and enqueue a change-announcement marker (consumed in R6). Upsert rows in place; delete
rows for kinds no longer present.

**Backfill:** management command `rebuild_content_deadlines` that iterates all
GRANT/CONFERENCE/FELLOWSHIP `ContentItem`s and rebuilds (idempotent; `changed_at`
untouched on first build).

**API:** add `deadlines: [{kind, due_date, confidence, label}]` to the opportunity/save
serializers (`content/serializers.py`), keeping existing scalar `deadline_date`/
`deadline_kind`. Frontend types updated in R9; scalars keep current cards working now.

**Validation:** `uv run --project web/backend pytest web/backend/apps/content/tests/test_content_deadlines.py`
+ smoke items from §13. Acceptance: conference→3 rows; rolling fellowship→ROLLING/NULL;
re-ingest unchanged→`changed_at` untouched; moved→`changed_at` set + AuditEvent;
`first_seen` still immutable; scalars still populated.

### R1 — Reminder models + daily tick + `Notification` model + in-app delivery

**Models (`content/models.py` or new `content/reminders.py` app-local):**
- `ReminderSubscription`: `TARGET_FIELDS=("target_user","target_lab")` via `exactly_one`/`validate_exactly_one`; `content` FK SET_NULL; `deadline_kind`; snapshot `area/title/url/due_date/confidence` (survives prune, resynced each tick); `channel_id_override` (lab only); `created_by`; `state` (active/fired_out/cancelled/stale). Unique `(target_user, content, deadline_kind)` and `(target_lab, content, deadline_kind)`.
- `ReminderOffset`: `amount` PositiveSmallInt + `unit` (day/week/month/year); unique `(subscription, amount, unit)`.
- `ReminderMention`: `subscription` + `member` FK→User; unique `(subscription, member)`. **No `role_id`.**
- `ReminderFire` (fired-ledger): `subscription`; `idempotency_key` unique = `f"{sub_id}:{due_date:%Y-%m-%d}:{amount}{unit}"`; `fired_on`; `days_remaining`; `channel` (in_app/discord_dm/discord_channel); `state` (sent/skipped/failed); `skip_reason`; `discord_message_id`, `attempts`, `error_code`, `sent_at`.
- `LabReminderPolicy`: OneToOne Lab; `default_offsets` JSON (default 1mo/1wk/1day); `default_mentions` M2M User.
- `Notification`: `kind` (reminder/deadline_moved/high_signal); `user`; `content` SET_NULL; `title/body/url` snapshot; `created_at/read_at/dismissed_at`; `dedupe_key` unique.

**Tick** (`content/reminders_tick.py` + command `run_reminder_tick`): compute-on-read per
the source §7 algorithm — resync snapshot from `ContentDeadline`; STALE if no date;
FIRED_OUT if past; `triggered = offsets where today >= due_date - relativedelta(unit=amount)`
minus already-sealed (by key); dedupe by computed `fire_date`; **fire at most one message
per subscription per day**; `days_remaining=(due_date-today).days`; seal **every**
triggered offset. **Seal-on-create**: creating a subscription seals already-past offsets as
`skipped(backdated_on_create)`. Calendar math via `dateutil.relativedelta` (add
`python-dateutil` if absent). R1 delivery is **in-app only** → writes `Notification`
rows; Discord channels wired in R3/R5.

**Validation:** the §14 regression suite (subset applicable to R1) —
`test_subscribing_with_backdated_offsets_sends_nothing_immediately`,
`_equivalent_offsets_one_week_and_seven_days_fire_once`,
`_forward_jump_past_multiple_offsets_sends_one_message`,
`_moved_deadline_unseals_offset_and_fires_with_current_days_remaining`,
`_relativedelta_months_are_calendar_not_thirty_days`, `_tick_is_idempotent_within_a_day`,
`_reminder_never_fires_after_deadline_passes`, `_reminder_survives_content_prune_via_snapshot`,
`_snapshot_due_date_resyncs_from_content_deadline_each_tick`. All on SQLite.

### R2 — Job ordering + prune→stale hook

- Decouple prune from the daily path: `run_daily_opportunities` gets a `--no-prune` flag; `manual_all.py CONTAINER_STAGES` becomes `run_daily_suggestions → run_daily_opportunities (--no-prune) → run_reminder_tick → prune_opportunities → generate_daily_briefing`. New `prune_opportunities` command calls `prune_expired`.
- Prune→stale hook: when a `ContentItem` (grant/conf/fellowship) is deleted, set `state=stale` on subscriptions pointing at it (pre-delete signal or explicit call in `prune_expired`). Belt-and-braces regardless of ordering.
- Keep `ingest_pivot(prune=True)` default for standalone host runs (`pivot.py import`); the stale hook covers the early-prune case.

**Validation:** `_deadline_moved_earlier_prunes_item_and_marks_subscription_stale`,
item-pruned-with-future-deadline renders+fires from snapshot, and an assertion that tick
precedes prune in the daily chain (unit test over the stage list).

### R3 — Personal reminders → Discord DM

- Extend `discord_api.create_message(channel_id, *, content, embed, allowed_mentions=None)` — default stays `{"parse": []}`; when provided, merge so `users` can carry explicit IDs while `parse` stays `[]`.
- Shared send helper (`integrations/services/reminders_send.py`, importing only through `resolve.py`): resolves recipient identity (ACTIVE only), opens DM (`open_dm_raw`), posts embed with `allowed_mentions={"parse":[],"users":[...],"roles":[]}`, escapes `@` in interpolated titles/labels, records `ReminderFire`. Tick sets `channel=discord_dm` when the target user has an ACTIVE identity + `dm_ok`, else in-app only.
- Personal reminder timezone: user zone if a profile timezone exists (none today → default `America/New_York`; note onboarding follow-up).

**Validation:** `_scraped_title_containing_everyone_produces_no_ping`,
`_allowed_mentions_parse_is_always_empty` (assert in the shared helper), DM path unit
tests with **mocked** `discord_api` RawResponses (200/403/429). Live DM send requires a
real bot token + a linked test account → flagged for production verification.

### R4 — `Lab.timezone` + `LabReminderPolicy` bind + channel picker + preflight

- `Lab.timezone` Char(64) default `America/New_York`, `Lab.send_hour_local` PositiveSmallInt default 9. Use IANA zone (DST-correct); display "Eastern".
- `DiscordGuildLink.announcement_channel_id` Char(32) blank + `channel_verified_at` DateTime null (migration in `integrations`).
- Add `discord_api.get_guild_channels(guild_id)` (GET `/guilds/{id}/channels`, Bot auth), filter to text/announcement types.
- Extend `/mylo setup` (gateway cog) to fetch channels, present a select menu, then **preflight by posting a visible confirmation via REST** and branch on status (403 → refuse with specific error, persist nothing; 2xx → persist `announcement_channel_id` + `channel_verified_at`). New `resolve.py` functions to set/read the channel binding. Re-verify on the reconciliation sweep → `ERROR_CHANNEL` state + portal warning on failure. Setup does not complete without a bound, verified channel.

**Validation:** channel-picker filtering unit tests; bind-refused-without-send-permission
(mocked 403); model/migration tests. Live guild verification flagged for production.

### R5 — Lab reminders + mention resolution + embed + send + override

- Mention resolution through `resolve.py`: ACTIVE identities → `<@id>` + `allowed_mentions.users`; unlinked/non-ACTIVE members → **plain display name, no ping, flag subscription** `has_unlinked_targets`. Mention targets must pass `user_has_lab_access`.
- Lab send: channel = `channel_id_override` or `DiscordGuildLink.announcement_channel_id`; embed render; one shared send helper enforces `parse:[]`.
- Authorization: create/edit/delete lab reminder → `user_can_manage_lab`; be a mention target → `user_has_lab_access`; personal reminder never surfaces in a lab channel; item visibility respected (`ProjectQuerySet.visible_to`).

**Validation:** `_lab_member_cannot_manage_lab_reminders`, `_mention_target_must_be_lab_member`,
`_unlinked_mention_target_renders_plain_text_not_dropped`, `_personal_reminder_never_appears_in_lab_channel`,
`_channel_bind_refused_without_send_permission_in_that_channel`, per-override-beats-default,
DST-boundary fire time. Live channel post flagged for production.

### R6 — `DEADLINE_MOVED` announcements

Consume R0's change marker: when a `ContentDeadline.due_date` moved on a row with live
subscriptions, send a change notice (same channel, mentions, one-per-day cap; one change
notice per subscription per day). Anticipated→confirmed reads specially. Mirror in-app as
`Notification(kind=deadline_moved)`.

**Validation:** change-notice unit tests over the R0 marker; rate-limit assertion.

### R7 — `HIGH_SIGNAL` gate (shadow-mode calibration first)

Gate on `signals`: `suggested==True` (passed floor — note reconciliation B), `match_percent >= HIGH_SIGNAL_FLOOR`
(placeholder 90 — **do not ship a guessed value**), `is_new==True`, `source=="llm"`,
an actionable deadline `[7,120]` days out; **≤2/user/week**; `dedupe_key=f"high_signal:{uid}:{cid}"`.
Ship a `high_signal_shadow` command that runs the gate over the existing `RelevanceScore`
corpus and **reports alerts/user/week without delivering**. Delivery (in-app only, D-10)
wired only after the floor is calibrated on real data.

**Validation:** `_high_signal_abstains_when_nothing_clears_floor`, `_high_signal_respects_weekly_cap`,
same-item-never-twice. Real-corpus floor calibration → flagged (needs production data, D-14).

### R8 — Fellowships for labs (BLOCKED on D-11)

Lift the fellowship exclusion in `_recommendations_payload`; surface lab fellowships as a
**union of eligible members**, naming only who **qualifies** (reuse `_interested_members`
shape). **Never render the ineligible case** (leaks immigration status by inference).
Requires a member consent model for lab-visible eligibility. **Do not build R8 until D-11
is decided** (see Open Decisions).

### R9 — Saves-page reminder affordance + composer + management UI

- Backend: reminder CRUD endpoints (personal + lab, authorization per R5) + list.
- Frontend: "Set reminder" affordance on the `SaveMeta` strip (`saves-section.tsx`); a composer modal (offsets, personal/lab, mentions, channel override) following the `useSaveOpportunity` mutation pattern; a management surface; disable/explain the affordance for ROLLING/UNKNOWN deadlines. Add `deadlines[]` + reminder types to `lib/portal/types.ts`; new `client.ts`/`hooks.ts`/`mutations.ts` entries; optional `/app/reminders` route (add to `routes.ts`).

**Validation:** `_rolling_fellowship_cannot_be_subscribed`,
`_conference_abstract_and_event_are_independently_subscribable`; frontend `tsc`+`eslint`+`build`
(worktree preview is pinned to the main checkout — browser verification not available in a
worktree, per project memory).

---

## Validation strategy (commands)

- Backend tests: `uv run --project web/backend pytest web/backend` (targeted: `... pytest web/backend/apps/content/tests/<file>::<test>`).
- Migrations: `uv run --project web/backend python manage.py makemigrations && ... migrate` (check for no-op drift each phase).
- Backfill/tick/shadow: run the new management commands with `--dry-run` where provided.
- Frontend (R9): `npm run lint` + `tsc --noEmit` + `next build` in `web/app`.
- Changelog + commit per phase (global skill). Commit, do not push. Final: merge worktree → main.

## Open decisions (carry into build)

- **D-10** High-signal to Discord vs in-app: **in-app only** for R7 (safe default).
- **D-11** Fellowship eligibility privacy — **blocks R8**. Eligible-only rendering + member consent flag required; the ineligible case is never shown. **Needs the owner's consent-model decision before R8 is built.**
- **D-12** Per-member mute of a lab reminder: out of R1–R9 scope; note as a follow-up (cheap to add later via a per-member suppression row).
- **D-13** Offset sanity bounds: cap offsets per subscription (5) and reject offsets landing before `first_seen`; implement in R1 validation.
- **D-14** `HIGH_SIGNAL_FLOOR`: placeholder 90; **must be calibrated on the production corpus in R7 shadow mode before delivery**.

## Exclusions

Digests; relevance-scoring internals; project/paper alerts (rail kept open via
`TARGET_FIELDS`); departments; role mentions (removed by D-5).
