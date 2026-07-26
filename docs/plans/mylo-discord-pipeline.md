# Mylo Discord Pipeline — Implementation Plan

**Status:** Complete. All five phases built and merged. Q-11 (the department-plan
inclusion asymmetry in `entitlements._lab_subscriptions`) remains open as a separate
billing change, and umbrella step E-7 (rendering `has_unlinked_targets`) is deferred
for want of a reminder-management UI to hang it on.
**Correlation ID:** `20260726-mylo-discord-pipeline`
**Source:** `mylo-discord-pipeline-handoff.md` (behavioural brief, supplied 2026-07-26)
**Owner:** BDGR

**This document is the umbrella.** Each phase gets its own executable plan doc,
written immediately before that phase begins and reconciled against the code as it
actually stands at that moment:

| Phase | Plan doc | Status |
|---|---|---|
| A — Outbox | `docs/plans/mylo-discord-a-outbox.md` | **done** |
| B — Authorization gate | `docs/plans/mylo-discord-b-gate.md` | **done** |
| C — Slash commands | `docs/plans/mylo-discord-c-commands.md` | **done** |
| D — Cluster digests + lab channel | `docs/plans/mylo-discord-d-digest.md` | **done** |
| E — Drift + portal health | `docs/plans/mylo-discord-e-drift.md` | **done** |

Phases are implemented **one at a time, sequentially**. Within a phase, every step is
validated and committed before the next begins.

---

## Objective

Make Mylo's Discord surface *reliable*, *authorized*, *interactive*, and *honest about
its own health*, without changing what Mycelium recommends or who may see it.

Five workstreams, in dependency order:

- **A — Outbox.** No outbound Discord message is lost because Discord was briefly
  unavailable. Delivery is durable, retried, classified, and dead-lettered.
- **B — Authorization gate.** Every inbound Discord interaction passes one gate:
  identity → account → object permission → entitlement → rate limit → audit.
- **C — Five slash commands.** `/mylo search`, `/mylo digest`, `/mylo saves`,
  `/mylo snooze`, `/mylo cancel`.
- **D — Lab digest to the updates channel.** The channel labs already bind in
  `/setup` finally receives something, once per lab per day.
- **E — Drift detection + portal surfacing.** When Discord changes underneath us
  (bot kicked, channel deleted, member left, add-on lapsed), Mycelium notices and
  a human can see why in the portal.

Sequencing: **A → B → (C ‖ D) → E**.

---

## Locked decisions (from the user, 2026-07-26)

| # | Decision | Consequence in this plan |
|---|---|---|
| L1 | Build **all five** slash commands. | Phase C ships `search`, `digest`, `saves`, `snooze`, `cancel`. |
| L2 | **Snooze is date-based**, computed as a follow-up from when the user runs the command. | `ReminderSubscription.snoozed_until` (a `DateField`), set to *the caller's local today + the requested amount*. Confirms the handoff's "suppress until" recommendation. Offsets and `ReminderFire` idempotency stay untouched. |
| L3 | **Free tier uses only what already exists.** Free search and free digest are built from data and code paths Mycelium already has — no new scoring, no new LLM spend, no new gating branch. | `/mylo search` reuses `run_search` exactly as `/app/search` does. `/mylo digest` reads a Free user's *stored* `RelevanceScore` rows through the existing deterministic (LLM-declining) seam. See Q-2. |
| L4 | **Dead-letter after 5 attempts, 5 minutes apart.** Must not spam: one logical message is delivered **once**, never five times, and the user is told **once** if it fails for good. | Fixed 300 s retry interval (not exponential — deliberate deviation from the handoff), `max_attempts = 5`, one `Notification` per dead-lettered outbox row keyed on the row id. Discord-side `nonce` + `enforce_nonce` guards the ambiguous-timeout double-send. |
| L5 | **The lab digest is structured like the user digest** — broken down by the sections the user actually cares about, i.e. by interest **clusters** where clusters exist. If the individual user digest is not already like this, make it so. | Phase D-2 restructures the digest to be cluster-first for both targets. **This is the largest scope item in the plan and is blocked on Q-3**, because opportunities carry no cluster attribution today. |
| L6 | **A lapsed bot add-on never makes the bot leave the server.** It downgrades to free behaviour: nothing is removed, nothing is deleted, only the *cycle and process* stop. | Phase E-4: `lab_has_feature(lab, BOT_SERVER)` is re-checked at delivery time. On lapse, scheduled channel delivery stops; the guild link stays `ACTIVE`, channel bindings stay bound, all history stays. Interactive commands keep working. |
| L7 *(closes Q-3)* | **Full cluster attribution now.** Grants, conferences and fellowships get real cluster attribution, so every cluster section of every digest is complete — no "Across your focus" catch-all bucket. | Phase D grows a matcher sub-phase (`D-1`) before the presentation and send work. Confirmed cheap on the frontend: the opportunity cards **already** render `{item.cluster ? <ClusterBadge/> : null}` and `types.ts:296` documents the field as *"reserved — grants/conferences/fellowships"*, so the UI lights up as soon as the backend populates it. |
| L8 *(closes Q-2)* | **`/mylo digest` for a Free user replies honestly and stops.** No live assembly from stored scores. | The command reports that Mylo has not written them a report and that daily research reports are part of Spore. No new content path, no LLM spend, no half-report that could be mistaken for the real thing. |
| L9 *(closes Q-1)* | **`/mylo search` mirrors `/app/search` exactly.** No invented match percentage. | `SearchView.get`'s body is factored into one shared helper the view and the bot both call, so the two can never disagree about the same query. Results show title, cluster badge (2+ clusters), and `matched_on` in plain language. |
| L10 *(closes Q-12, part)* | **One plan doc per phase; phases run sequentially; validate and commit at every step.** | See the phase table above. No phase begins before its own plan is written and reconciled against the code as it then stands. |

---

## Reconciliation — how the handoff differs from the codebase

Verified by direct read, 2026-07-26. Rows marked **⚠** change the shape of the work.

| # | Handoff assumption | Reality (verified) | Consequence |
|---|---|---|---|
| A | "It writes a record saying that reminder has fired… whether or not Discord actually accepted the message." | **Correct.** `reminders_tick._seal()` writes a `ReminderFire` row unconditionally (`state=FAILED` on failure), and `_triggered_keys()` only checks `.exists()`, so a failed row permanently blocks retry. `web/backend/apps/content/reminders_tick.py:122-130,189-206` | Phase A-4 is exactly the fix described. |
| B | "There is already a reachability-probe component that classifies Discord responses… reuse its logic." | **Correct but it is not reusable as-is.** `probe.run_probe()` classifies *inline*, branching on `RawResponse.status` and writing identity state in the same function. `web/backend/apps/integrations/services/probe.py:36-75` | A-2 extracts a **pure** classifier (`classify(status, code, retry_after) -> Verdict`) and rewrites `probe.py` to call it, so the judgment lives in one place with no duplication. |
| C ⚠ | "`/mylo search` … the existing cluster-scoped retrieval pipeline … the match percentage … the same attribution the web app shows on paper cards." | **Conflates two different pipelines.** The cluster-scoped, match-percent pipeline is the **digest** engine (`content/fusion.py`, `pipeline.py`) and is *interest-first*, not query-first. The user-facing search at `/app/search` is `content/search.py::run_search` — rank-only RRF, **no match percent**, no abstention, cluster badge attached post-hoc in the view. | **Q-1.** Recommendation: `/mylo search` mirrors `/app/search` verbatim (no invented percentage). |
| D ⚠ | "`/mylo digest` … deliberately valuable for free-tier users, who are excluded from scheduled delivery but not from asking." | **A Free user has no digest to pull.** `tasks.select_users()` filters on `Feature.SCHEDULED_REPORTS`, which Free does not hold, so Free users get **no `DailyBriefing` row and no daily `RelevanceScore` refresh at all**. `web/backend/apps/content/tasks.py:26-44`, `billing/entitlements.py:75-81` | **Q-2.** Recommendation: build the reply from the user's *stored* scores via the existing deterministic seam, labelled honestly. |
| E ⚠ | "the daily report … the same content the scheduled daily report contains" implies a shared digest shape. | **Both the user and the lab digest are sectioned by content CATEGORY, not by cluster.** Cluster grouping exists only as prose sub-structure *inside the Papers section*, and only when ≥2 clusters carry labels. `briefing_agents.py:39,132-169,206-224` | L5 therefore requires real restructuring, not a presentation tweak — see Q-3. |
| F ⚠ | (implicit) grants/fellowships/conferences can be grouped by cluster. | **They carry no cluster attribution.** `cluster_id`/`cluster_label`/`per_cluster` are written only by `pipeline._cluster_row` for `ContentItem.Type.PAPER`. `opportunities.py` and `fellowships.py` contain no cluster references at all. | Cluster-first opportunities = **new matching-engine work**. Q-3 decides whether it is in scope. |
| G | "Celery Beat was replaced by the host timer." (repo-map phrasing) | **Beat is still running.** `compose.yaml:155` runs `celery -A config beat`; `CELERY_BEAT_SCHEDULE` still owns `recompute-project-profiles` and `reconcile-discord`. Only the *daily research/opportunity* schedules moved to `mylo-daily.timer`. | The outbox drain has a proven home: a Celery task on a fast Beat crontab, exactly like `probe_identity`/`reconcile_discord`. |
| H ⚠ | "a slash command today, a button click later — the payload includes identifiers … some of that information originates on the user's client and is therefore untrustworthy." | **There is no HTTP interactions endpoint.** Mylo is a discord.py **gateway** client (`mylo/bot/__main__.py`, `bot.start(token)`), authenticated by the bot token at the WebSocket handshake. There is no Ed25519 payload to forge or verify. | Phase B drops all signature-verification work. The real risk it must address is narrower and still real: **never derive authority from a command argument, a custom_id, or a cached username** — only from `interaction.user.id`. |
| I ⚠ | "Listen for … a member leaving a server." | `on_guild_remove` and `on_guild_channel_delete` need only the `guilds` intent, already on. **`on_member_remove` needs the privileged `members` intent**, which `discord.Intents.default()` excludes (`mylo/bot/client.py:38`). Enabling it is a Developer-Portal toggle plus, past 100 guilds, Discord verification review. | **Q-4.** Recommendation: do not take the privileged-intent dependency; detect member departure REST-side in the reconcile sweep. |
| J | "A lab admin configures this, sees a success confirmation, and waits forever." | **Correct.** `updates_channel_id` is bound and verified by `/setup`, and `resolve.get_updates_channel_for_lab()` exists — but nothing in the repo ever posts to it. | Phase D is greenfield *send* logic over an already-solid binding. Do not rebuild the binding. |
| K | "Extend the [`has_unlinked_targets`] pattern rather than inventing a parallel one." | **Modelled and computed, but never rendered.** No component calls `useReminders()`; there is no reminder-management UI at all. `web/app/src/lib/portal/hooks.ts:327` is the hook's only reference. | E-6 must *build* the first render site, not add a badge to an existing one. |
| L | "Periodic reconciliation … is the safety net and it is not optional." | **Already exists and runs nightly.** `services/reconcile.py::reconcile()` diffs `get_bot_guilds()` against `resolve.active_guild_ids()` and marks kicked links, plus OAuth token health. It has **zero test coverage**. | E-2 extends this function; it does not create it. E-2 also adds its first tests. |
| M | "Preserve the existing send-limiting rules… one subscription produces at most one message per day." | **Correct, and structural rather than a check.** `run_tick` collects all triggered keys, calls `_deliver` **once**, and seals every key with that one delivery's outcome. | A-4 must keep the single `_deliver` call and move only the *transport* behind the queue. |
| N | (implicit) all senders should be treated uniformly. | Two senders must **not** be queued: `reminders_discord.preflight_channel` (a synchronous diagnostic — `/setup` needs an immediate 2xx/403 to tell the admin whether the bind worked) and `errors.post_embed` (the ops error channel — queueing it means an outbox outage silences the channel that reports outages). | **Q-5.** Recommendation: both stay direct-send, documented as deliberate carve-outs. |
| O ⚠ | (implicit) the daily PDF can be queued like any other message. | `daily_report_send.run_daily_report_send` renders PDFs into a temp dir and `shutil.rmtree`s it immediately after the synchronous send. A queued send would drain *after* the bytes are gone. There is a test asserting the dir is deleted (`test_daily_report.py::test_send_flow_is_phased_and_cleans_up`). | **Q-6.** Attachment lifetime must be decided before A-6. |
| P | "the ability to run the bot in a lab's server is a paid add-on … Check entitlements at the point of use." | `Feature.BOT_SERVER` is checked in exactly **one** place — `oauth.complete_guild_link` at install time (`services/oauth.py:109`). Never re-checked. Also, `entitlements._lab_subscriptions()` unions `scope_lab` **or** `scope_department` *without* honouring `Lab.department_plan_included`, unlike seat billing. | E-4 adds the delivery-time re-check. The inclusion asymmetry is **Q-11**. |
| Q | (implicit) `/mylo cancel` maps onto an existing cancel. | `ReminderSubscription.State.CANCELLED` exists but is unused — `DELETE /api/reminders/<id>/` **hard-deletes** the row. | **Q-7.** Soft-cancel is the auditable choice but changes existing web behaviour. |
| R | (implicit) `/mylo` subcommands can be added from a new cog. | discord.py forbids two cogs registering a top-level group of the same name. `/mylo` is `StatusCog.mylo` (`mylo/bot/cogs/status.py:30`), and `mylo/tests/test_bot.py` asserts its subcommand set is *exactly* `{health, lastrun, status}`. | C-1 extracts the group into a shared module before adding anything. The strict-shape test must be updated in the same commit. |

**Confirmed as stated by the handoff (do not re-litigate):** the single-ORM-boundary rule
and its AST test; "identity proves who, never what"; Mylo owns no database; the
`allowed_mentions.parse == []` guarantee; the `ReminderFire` idempotency-key trick
(embedding `due_date`); the `/setup` prove-postability-by-posting pattern.

---

## Key code coordinates (from recon)

**Outbound send (all of it)**
- `apps/integrations/services/discord_api.py` — `create_message`, `create_message_with_attachment`, `open_dm_raw` return `RawResponse(status, json, retry_after)`; everything else raises `DiscordHTTPError`. `_parse` reads `Retry-After` **only on 429** (`:293-299`). No retry anywhere.
- `apps/integrations/services/probe.py:36-75` — the de-facto failure classifier.
- `apps/content/reminders_discord.py` — `send_personal_dm` (`:73`), `send_personal_report` (`:106`), `send_lab_channel` (`:152`), `preflight_channel` (`:245`), `list_postable_channels` (`:229`). All return `SendOutcome`, none raise.
- `apps/integrations/services/oauth.py:121` — `_post_setup_nudge`, fire-and-forget, `except Exception: pass`.
- `apps/integrations/services/errors.py` — `note_incident` (dedupe + circuit breaker) → `post_embed` (its own urllib call, **not** through `discord_api`).
- `mylo/reporting.py` — the host daily-run reporter. Separate process, separate stdlib client, reads `.env-mylo`.

**Reminders**
- `apps/content/models.py` — `ReminderSubscription` (`:800`), `ReminderOffset` (`:917`), `ReminderMention` (`:954`), `ReminderFire` (`:981`, note `attempts` is defined but never written), `Notification` (`:1052`).
- `apps/content/reminders.py:54-67` — `offset_fire_date`, `idempotency_key`.
- `apps/content/reminders_tick.py:57-99` — `run_tick`; `_triggered_keys` (`:122`), `_deliver` (`:133`), `_seal` (`:189`).
- `apps/content/reminders_announce.py` — separate pass, reuses the same senders, idempotent only via `Notification.dedupe_key` prefix.

**Digest**
- `apps/content/briefing.py` — `generate_briefing_for_user`, `generate_briefing_for_lab`, `_suggested_scores`, `_is_new_today`, `LAB_BRIEFING_CATEGORIES` (`:43`).
- `apps/content/briefing_agents.py:39` `SECTION_ORDER`; `:132-169` `generate_report_body`; `:206-224` `_cluster_groups`.
- `apps/content/daily_report.py` / `daily_report_pdf.py` / `daily_report_send.py` — the personal PDF path. **No lab equivalent exists.**
- `apps/content/models.py` `DailyBriefing` (`:742`) — one row per `user` **or** `lab`, `exactly_one`.

**Search**
- `apps/content/search.py:464` `run_search(query, *, filters, sort, limit, offset, pool, query_vector) -> SearchResult`.
- `apps/content/query_embedding.py:46` `embed_query(normalized)` — Redis-cached, alias `"search"`.
- `apps/content/views.py:1281` `SearchView.get` — normalizes, embeds, calls `run_search`, then `_saved_content_ids`, `_saved_lab_slugs_by_content`, `_attach_search_clusters` (`:700-729`).

**Identity / boundary**
- `apps/integrations/services/resolve.py` — the only module permitted to import a model. `resolve_identity`/`resolve_user` (`:76,84`), `can_manage_lab_via_discord` (`:538`), `set_identity_dm` (`:168`), `get_updates_channel_for_lab` (`:408`), `mark_guild_kicked` (`:513`), `active_guild_ids` (`:526`).
- `apps/integrations/services/state.py:88-93` — `is_locked_out`, **fail-closed** (`return True` on cache error).
- `apps/integrations/services/audit.py` — `discord_audit(action=…, discord_user_id=…)`, sha256-hashes the snowflake, writes `accounts.AuditEvent`. No Discord audit table.
- `apps/integrations/tests/test_import_graph.py:20-24` — `_GUARDED = [views.py, tasks.py, services/*.py]`, `_EXEMPT_NAMES = {resolve.py, __init__.py}`. **Flat glob, one level.**

**Permissions / billing**
- `apps/accounts/permissions.py` — `user_has_lab_access`, `user_can_manage_lab`, `user_can_edit_lab_profile`, `user_can_invite_to_lab` (alias), department equivalents.
- `apps/billing/entitlements.py` — `Feature` (`:39`), `_FREE` (`:75`), `has_feature` (`:259`), `lab_has_feature` (`:460`), `can_dm` (`:464`), `_lab_subscriptions` (`:433`).
- Behaviour seam (Free = deterministic, no LLM): `pipeline._force_fallback` (`:141-147`) substituted per-user at `pipeline.py:711-722`, `opportunities.py:1096-1119`, `tasks.py:219-233`.

**Bot**
- `mylo/bot/client.py:33-42` — `Intents.default()`, `tree_cls=MyloCommandTree`, prod sync is manual.
- `mylo/bot/cogs/status.py:30` — `mylo = app_commands.Group(...)`.
- `mylo/bot/cogs/setup.py:44-141` — `SetupView`: `interaction_check` owner guard, `timeout=180`, `on_timeout` disables children, single `_apply` handler.
- `mylo/linking.py` — the async facade; every ORM body imports `resolve` **inside** the function.
- `mylo/mycelium.py:38` — `db(fn, ...)` = `sync_to_async(fn, thread_sensitive=True)`.

**Async substrate**
- `compose.yaml:122` `worker`, `:155` `beat`. `config/settings.py:191-209` `CELERY_BEAT_SCHEDULE`.
- `apps/integrations/tasks.py:32-53` `probe_identity` — `bind=True`, `max_retries=3`, `self.retry(countdown=retry_after or 2**n * 5)`. The retry template.
- `manual_all.py:113-128` `CONTAINER_STAGES` — **asserted by a source-text regex test** (`test_reminders_prune_ordering.py`).

---

## Architecture decisions (this plan)

**AD-1 — The outbox is an `integrations` model, reached only through `resolve.py`.**
`DiscordOutboxMessage` lives in `apps/integrations/models.py`. Every ORM touch goes
through new functions in `resolve.py`. Orchestration lives in a new
`apps/integrations/services/outbox.py`, which the AST test guards automatically
(`services/*.py` glob). This keeps the boundary literal at the cost of growing
`resolve.py` by ~120 lines. *Rejected alternative:* adding `outbox.py` to
`_EXEMPT_NAMES` — cheaper, but it weakens the one invariant the codebase actually
enforces mechanically.

**AD-2 — The classifier is pure and shared.**
`services/discord_failure.py` exports:

```python
class Verdict(StrEnum):
    OK = "ok"; TRANSIENT = "transient"; PERMANENT = "permanent"

@dataclass(frozen=True)
class Classification:
    verdict: Verdict
    retry_after: float | None = None
    reason: str = ""            # "dm_blocked" | "channel_gone" | "no_access" | …
    error_code: int | None = None

def classify(*, status: int, error_code: int | None, retry_after: float | None) -> Classification
```

Rules (derived from `probe.py` + the Discord error catalogue):

| Signal | Verdict | Reason |
|---|---|---|
| 200 / 201 | `OK` | — |
| 429 | `TRANSIENT`, honour `retry_after` | `rate_limited` |
| ≥ 500, or `status == 0` (transport/DNS/timeout) | `TRANSIENT` | `upstream` |
| 403 + code 50007 | `PERMANENT` | `dm_blocked` |
| 403 + code 50013 | `PERMANENT` | `no_permission` |
| 403/404 + code 50001 | `PERMANENT` | `no_access` |
| 404 + code 10003 | `PERMANENT` | `channel_gone` |
| 403 + code 50033 / bot removed | `PERMANENT` | `guild_gone` |
| any other 4xx | `PERMANENT` | `rejected` |

`probe.run_probe` is rewritten to branch on `classify(...)`. This module contains no
model import, so it satisfies the AST test.

**AD-3 — Retry policy follows L4, not the handoff.**
Fixed `OUTBOX_RETRY_SECONDS = 300`, `OUTBOX_MAX_ATTEMPTS = 5`, both settings-driven.
`next_attempt_at = now + max(OUTBOX_RETRY_SECONDS, classification.retry_after or 0)`
— a Discord-supplied `Retry-After` may only *lengthen* the wait, never shorten it.
Total window ≈ 20 minutes.

**AD-4 — "Once, not five times" is enforced three ways.**
1. **One row per logical message.** `dedupe_key` is `unique`; enqueue is
   `get_or_create`. Re-running a producer never creates a second row.
2. **Claim before send.** The drain claims rows with
   `select_for_update(skip_locked=True)` and stamps `attempts += 1` /
   `status = SENDING` *before* the HTTP call, so a crash mid-send cannot look like
   "never attempted".
3. **Discord-side nonce.** Every `create_message` carries
   `nonce=<outbox row id>` and `enforce_nonce: true`, so if attempt *n* actually
   landed but we never saw the response, attempt *n+1* returns the existing message
   rather than posting a duplicate. **Verify this field against the current Discord
   API reference during A-2 before relying on it**; if unavailable, fall back to
   accepting the (narrow) ambiguous-timeout duplicate risk and document it.

**AD-5 — The reminder seal moves to enqueue time.**
`ReminderFire.Result` gains `QUEUED`. `_seal()` writes `state=QUEUED` plus a new
`outbox` FK at enqueue time; the drain later stamps `state`, `channel`,
`discord_message_id`, `error_code`, `attempts`, `sent_at`. This preserves the
"don't send twice" guarantee (the seal exists immediately), fixes the pre-existing
crash-between-send-and-seal duplicate window, and keeps `_triggered_keys`
unchanged. The in-app `Notification` write stays synchronous and unconditional —
the bell must never depend on Discord.

**AD-6 — `preflight_channel` and the ops error sink stay direct-send.** (Q-5)
Both are diagnostics, not product messages. `preflight_channel` needs a synchronous
verdict for `/setup`; `errors.post_embed` must survive an outbox failure to report
it. Both are documented carve-outs in `outbox.py`'s docstring and asserted by a test.

**AD-7 — The `/mylo` group is extracted before it is extended.**
`mylo/bot/cogs/_mylo_group.py` owns `mylo_group = app_commands.Group(name="mylo", …)`.
`status.py` imports it; two new cogs (`research.py` → search/digest/saves,
`reminders.py` → snooze/cancel) attach their subcommands to the same object.
`mylo/tests/test_bot.py`'s exact-set assertions are updated in the same commit.

**AD-8 — Every new command defers immediately.**
`await interaction.response.defer(ephemeral=True)` is the first statement of every
new command body, before the gate runs. The gate itself touches the ORM and Redis;
search additionally embeds a query. None of that fits Discord's 3-second window
reliably. `/mylo health` and `/mylo lastrun` keep their non-deferred file-read path.

**AD-9 — The gate returns a typed decision, and the cog renders it.**
Following the existing `mylo/linking.py` `(status, payload)` convention rather than
raising through `MyloCommandTree.on_error` (nothing in the repo raises
`UserFacingError` today; mixing the two idioms across five commands would be worse
than either). The gate is one function in the backend, called through
`mycelium.db`.

**AD-10 — Lab reachability gets its own model surface, mirroring `dm_ok`.**
`DiscordGuildLink` gains nullable `announcement_channel_ok` / `updates_channel_ok`
plus `*_checked_at` and `last_error_code`, exactly parallel to
`DiscordIdentity.dm_ok` / `dm_checked_at` / `last_error_code`. `null` = unknown,
`True` = verified postable, `False` = permanently failed. Written by the reconcile
sweep, by outbox permanent failures, and by gateway events.

---

## Phase A — Outbox (must land first)

### A-1 · Branch, baseline, and a red test

- Create the working branch (see Q-12). Run the full suite and record the baseline,
  **including** the known-failing `test_high_signal.py::test_command_delivers_when_enabled`
  (date flake, pre-existing — see memory `high-signal-test-date-flake`).
- Add `apps/content/tests/test_outbox_regressions.py` with two tests that fail today
  and must pass at the end of A:
  - `test_transient_discord_failure_is_retried_not_lost` — a personal reminder whose
    first send attempt gets a 503 is delivered on a later drain.
  - `test_one_subscription_one_message_per_day_survives_queueing` — the anti-burst
    rule from `test_reminders_tick.py::test_worker_down_48h_no_burst`, re-asserted
    end-to-end through the queue.

**Validation:** both new tests red; everything else at baseline.

### A-2 · The pure failure classifier

- New `apps/integrations/services/discord_failure.py` per **AD-2**. No model import.
- Rewrite `probe.run_probe` to call `classify(...)`; behaviour must not change.
- Verify Discord's `nonce` / `enforce_nonce` contract (**AD-4.3**) and record the
  finding in this document before A-3 depends on it.

**Validation:** `pytest web/backend/apps/integrations/tests/test_services.py -k Probe`
(existing `ProbeTests` must pass unchanged), plus new
`test_discord_failure.py` covering every row of the AD-2 table.

### A-3 · The outbox model + `resolve` accessors

New model in `apps/integrations/models.py`:

```python
class DiscordOutboxMessage(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"; SENDING = "sending"; SENT = "sent"
        FAILED = "failed"            # permanent, terminal
        DEAD = "dead"                # attempts exhausted, terminal

    class Target(models.TextChoices):
        DM = "dm"; CHANNEL = "channel"

    id = UUIDField(pk, default=uuid4)
    dedupe_key = CharField(200, unique=True)
    kind = CharField(40)               # reminder | deadline_moved | daily_report | lab_digest | …
    target_type = CharField(choices=Target)
    recipient_user = FK(User, null, SET_NULL)      # DM: whose identity to resolve
    channel_id = CharField(32, blank)              # CHANNEL: resolved at enqueue
    lab = FK("accounts.Lab", null, SET_NULL)       # provenance for channel sends
    content = TextField(blank)
    embed = JSONField(null, blank)
    allowed_mentions = JSONField(null, blank)
    attachment_ref = CharField(500, blank)         # see Q-6
    attachment_filename = CharField(200, blank)
    subject_type = CharField(40, blank)            # "reminder_fire" | "daily_briefing" | …
    subject_id = CharField(64, blank)              # traceability back to the producer
    status = CharField(choices=Status, default=PENDING)
    attempts = PositiveSmallIntegerField(default=0)
    next_attempt_at = DateTimeField(db_index=True)
    last_error_code = IntegerField(null)
    last_error_reason = CharField(40, blank)
    discord_message_id = CharField(32, blank)
    created_at / updated_at / sent_at / dead_at
```

Index: `(status, next_attempt_at)`.

New `resolve.py` functions (the *only* module touching this model):
`enqueue_outbox(...) -> tuple[DiscordOutboxMessage, bool]` (get_or_create on
`dedupe_key`), `claim_outbox_batch(limit, now)` (`select_for_update(skip_locked=True)`
inside `transaction.atomic`, flips `PENDING → SENDING`, `attempts += 1`),
`mark_outbox_sent`, `mark_outbox_retry`, `mark_outbox_permanent`,
`mark_outbox_dead`, `outbox_counters(since)`, `purge_outbox(before)`.

**Landmine:** `select_for_update(skip_locked=True)` is Postgres-only. The drain's
concurrency test must run against the compose Postgres at `localhost:11450`
(`DATABASE_URL` override); the rest of the suite stays SQLite-safe.

**Validation:** migration applies clean on Postgres and SQLite;
`test_outbox_model.py` covers dedupe, claim-once-under-concurrency (Postgres-gated
fixture, mirroring `test_retrieval.py:24-26`), and terminal-state transitions.
`test_import_graph.py` still green.

### A-4 · The sender + drain

- New `apps/integrations/services/outbox.py`:
  - `enqueue(...)` — the single producer entry point. Resolves the DM channel *lazily
    at drain time*, not at enqueue (an identity's `dm_channel_id` may be stale).
  - `deliver_one(message) -> Classification` — resolves the destination, calls
    `discord_api.create_message` / `create_message_with_attachment` with the nonce,
    classifies, and writes state back through `resolve`.
  - `drain(limit=…, now=…) -> DrainResult` — claim → deliver → classify → settle.
  - On `PERMANENT` with `reason == "dm_blocked"` → `resolve.set_identity_dm(dm_ok=False)`.
  - On `PERMANENT` with a channel reason → `resolve.set_channel_health(...)` (AD-10).
  - On exhaustion → `mark_outbox_dead` + **one** `Notification` (see A-7) + one
    `errors.note_incident` (already deduped and circuit-broken).
- New Celery task `apps.integrations.drain_outbox` in `tasks.py`; Beat entry
  `crontab(minute="*")` in `settings.py`, alongside `reconcile-discord`.
- Management command `manage.py drain_discord_outbox [--once] [--limit N]` for host
  runs and manual recovery.

**Validation:** `test_outbox_drain.py` — a 503 retries and later succeeds; a
403/50007 marks the identity unreachable and does **not** retry; a 429 with
`retry_after=900` schedules 900 s, not 300 s; the 6th attempt never happens;
counters are correct.

### A-5 · Migrate the reminder senders

- `reminders_discord.send_personal_dm` / `send_lab_channel` become **enqueue-only**,
  returning a `SendOutcome` with a new `queued: bool` field and no `message_id`.
- `reminders_tick._deliver` keeps its single call and its single `_deliver_in_app`;
  `_seal` writes `state=QUEUED` + `outbox` FK per **AD-5**.
- `reminders_announce._announce_one` likewise. Note its Discord side currently has
  **no** idempotency of its own (it borrows `Notification.dedupe_key` via a
  `startswith` check); give it a real outbox `dedupe_key`
  (`deadline_moved:{sub.id}:{due_date}`), closing an existing double-send hole.
- Dedupe keys: `reminder:{fire.idempotency_key}` for tick sends.

**Validation:** rewrite `test_reminders_discord.py` and `test_reminders_lab.py` to
assert *an outbox row with the right payload*, then run `drain()` and assert the
transport call. `test_reminders_tick.py` must pass **unchanged** (it is in-app only).
The two A-1 regression tests go green.

### A-6 · Migrate the daily PDF report

Blocked on **Q-6** (attachment lifetime). Once decided:

- `daily_report_send.run_daily_report_send` gains an **enqueue** phase between render
  and cleanup; `_default_send` enqueues instead of sending.
- `test_daily_report.py::test_send_flow_is_phased_and_cleans_up` is rewritten to
  assert the chosen durability contract rather than immediate deletion.
- Dedupe key: `daily_report:{user.id}:{run_date}`.

**Validation:** `test_daily_report.py`, `test_daily_report_discord.py`;
one-failure-does-not-sink-the-batch is preserved.

### A-7 · Dead-letter user messaging (L4)

- `Notification.Kind` gains `DELIVERY_FAILED` (a pure enum addition — `choices=` is
  not a DB constraint here, so the migration is a no-op at the database level).
- On dead-letter, write **exactly one** `Notification` with
  `dedupe_key = f"discord_fail:{outbox.id}"`. Because the outbox row is itself
  unique per logical message, five attempts produce one notification.
- Recipient: for a DM, the intended user. For a channel post, every user who passes
  `user_can_manage_lab` for that lab (see Q-8).
- Copy follows `docs/styles.md` — name the uncertainty plainly, no hype:
  *"Mylo couldn't deliver your deadline reminder to Discord. Your DMs are closed —
  enable 'Allow direct messages from server members' and re-test from your profile."*

**Validation:** `test_outbox_deadletter.py` — five failed attempts produce one
notification, not five; a later identical enqueue does not produce a second.

### A-8 · Counters, retention, docs

- `outbox_counters(since)` → attempted / delivered / retried / dead — consumed by
  E-5 and by `manage.py drain_discord_outbox --stats`.
- Retention: a weekly Beat task purges `SENT` rows older than
  `OUTBOX_RETENTION_DAYS` (default 30). `DEAD`/`FAILED` rows are kept.
- Update `docs/repo-map.md` (new `integrations` row), `docs/architecture.md`, and
  `docs/changelog.md`.

**Validation:** `npm run lint`, full backend suite, changelog entry, commit.

---

## Phase B — Authorization gate

### B-1 · The gate

New `apps/integrations/services/gate.py` (AST-guarded automatically):

```python
class Denial(StrEnum):
    NOT_LINKED = "not_linked"          # helpful: how to connect
    RATE_LIMITED = "rate_limited"
    NOT_ENTITLED = "not_entitled"      # upgrade prompt
    FORBIDDEN = "forbidden"            # generic — never confirms the object exists
    NOT_FOUND = "forbidden"            # deliberately collapses into FORBIDDEN

@dataclass(frozen=True)
class GateResult:
    ok: bool
    user: User | None = None
    denial: Denial | None = None
    message: str = ""
    detail: dict | None = None

def authorize(
    *, discord_user_id: str, action: str,
    lab_slug: str = "", subject_id: str = "",
    guild_id: str = "",
) -> GateResult
```

Order, exactly as the handoff specifies:

1. `resolve.resolve_identity(discord_user_id)` → ACTIVE identity only. `None` →
   `NOT_LINKED` with the portal URL and the `/activate` hint.
2. Rate limit (B-2). Exceeded → `RATE_LIMITED`.
3. Object resolution + permission via `apps.accounts.permissions` — never a
   Discord-side rule. A missing object and a forbidden object return the **same**
   `FORBIDDEN` message.
4. Entitlement via `apps.billing.entitlements` (B-3).
5. `audit.discord_audit(action=f"discord.command.{action}", …)` on **every**
   outcome, allowed or denied, with the hashed snowflake, the action, the target,
   and the verdict.

**Non-negotiable:** authority derives only from `interaction.user.id`. Command
arguments, `custom_id`s, and `username_cache` are treated as untrusted display data.
`/activate-lab`'s deliberate no-billing-gate carve-out (decided 2026-07-18) is
preserved — it does not route through this gate.

### B-2 · Rate limiting

Extend `services/state.py` with the *same* Redis cache and the **same fail-closed
contract** as `is_locked_out`:

```python
def check_rate(discord_user_id: str, bucket: str, *, limit: int, window: int) -> bool
    """False = deny. Fails CLOSED (returns False) when the cache is unreachable."""
```

Buckets (settings-driven): `search` 5 / 60 s (the expensive one — it can trigger an
embedding call and up to five Postgres queries), everything else 20 / 60 s.

### B-3 · Entitlement checks per command

| Command | Check | Rationale |
|---|---|---|
| `/mylo search` | none beyond "linked" | Search is ungated on the web for every tier; gating Discord harder would make Discord users *less* privileged than web users for the identical capability. |
| `/mylo digest` | none beyond "linked"; a target with no `DailyBriefing` gets the honest empty reply (L8) | Pull, not push. Free users are told plainly rather than refused. |
| `/mylo saves` | none beyond "linked" | Personal read of the caller's own rows. |
| `/mylo snooze` / `/mylo cancel` | `user_can_edit_lab_profile` for a lab reminder; ownership for a personal one | Mirrors `ReminderDetailView` exactly. |
| lab-scoped anything in a guild | `lab_has_feature(lab, Feature.BOT_SERVER)` | Point-of-use enforcement, per the standing rule. |

### B-4 · Wire the existing commands through it

`/setup`'s `_setup_gate` in `mylo/linking.py:191-207` is replaced by a call to
`gate.authorize(action="setup", guild_id=…)`, so there is one gate rather than two
idioms. `/activate` and `/activate-lab` keep their own lockout paths (they *are* the
linking flow; they cannot require a link).

**Validation:** `apps/integrations/tests/test_gate.py` — an unlinked snowflake is
refused; a linked non-manager is refused for a lab action with the generic message;
a forged `lab_slug` argument naming a lab the caller cannot see returns the same
generic refusal as a non-existent lab; a rate-limited caller is refused; every path
writes exactly one audit row; the cache being down denies rather than allows.

---

## Phase C — Five slash commands

### C-1 · Extract the `/mylo` group (AD-7)

`mylo/bot/cogs/_mylo_group.py`; `status.py` imports it; `client.INITIAL_EXTENSIONS`
gains the two new cogs. Update `mylo/tests/test_bot.py`'s exact-set assertions.
Note in the plan and the changelog that **production requires a one-time
`@Mylo sync global`** after deploy — new commands do not appear otherwise.

### C-2 · `/mylo search <query>`

- `linking.search(discord_user_id, query, …)` → `mycelium.db(_search_sync, …)`.
- `_search_sync` calls a **new shared helper** rather than re-implementing the view:
  factor `SearchView.get`'s body into
  `apps/content/search_service.py::search_for_user(user, query, *, limit) -> list[SearchHit]`,
  and have `SearchView` call it too, so the bot and the web app can never disagree.
  This helper does: normalize → `embed_query` → `run_search` → `_saved_content_ids` →
  `_attach_search_clusters`.
- Reply: one embed, top 5, each line = title (linked to `item.url`, the external
  source — **there is no per-item portal permalink**), the cluster badge when the
  user has ≥2 clusters, and the `matched_on` channels rendered as a plain-language
  "matched on title text / meaning / close spelling". A footer links to
  `{DISCORD_APP_BASE_URL}/app/search?q=…` to continue in the portal.
- Ephemeral. Deferred. Rate-limited hardest.
- **No match percentage** (L9). Search does not compute one; inventing one at the
  presentation layer would make the bot and the portal disagree.

### C-3 · `/mylo digest [scope]`

- Optional `scope` choice: `personal` (default) or a lab the caller has access to
  (Q-9). Lab scope additionally requires `lab_has_feature(BOT_SERVER)`.
- Reads `DailyBriefing` for the target. Three honest outcomes:
  - **Fresh** (`generated_at.date() == local today`) → render it.
  - **Stale** → render it, with the date named plainly.
  - **None** → for an entitled user, "Mylo hasn't written today's report yet"; for a
    Free user (L8), *"Mylo hasn't written you a report. Daily research reports are
    part of Spore."* — plain, honest, no fabricated half-report.
- Rendering: the briefing body is markdown; Discord embeds render a useful subset.
  Cap at the embed limits (4096-char description, 6000 total, 25 fields) and link
  to `/app/daily` for the rest. Never fabricate an empty-looking report.

### C-4 · `/mylo saves`

- `SavedOpportunity.objects.filter(user=…).order_by("-created_at")[:10]`, reading the
  **snapshot** fields (`title`, `area`, `subtitle`, `deadline_date`, `url`) directly.
  Do **not** round-trip through `SavedItemSerializer.card` — that pulls four feed
  serializers and `RelevanceScore` batching into the bot's path for no benefit.
- Paginate with a `View` of Prev/Next buttons following the `SetupView` pattern:
  `interaction_check` bound to the invoking user, `timeout=180`, `on_timeout`
  disables children.
- Footer links to `/app/saves` (there is no per-save anchor).

### C-5 · `/mylo snooze` (L2)

- **New model surface:** `ReminderSubscription.snoozed_until = DateField(null=True, blank=True)`.
- `run_tick` consults it immediately after the `FIRED_OUT` check and before
  `_triggered_keys` — so a snooze suppresses the *send* without sealing anything.
  When the snooze lapses, the still-unsealed offsets trigger and the existing
  one-message-per-day collapse fires **one** message with the true days-remaining.
  This is why the suppression must not seal: sealing would silently swallow the
  reminder instead of deferring it.
- Command shape: `/mylo snooze reminder:<autocomplete> amount:<int> unit:<day|week|month>`.
  `snoozed_until = caller_local_today + relativedelta(...)`, reusing
  `offset_fire_date`'s calendar-correct arithmetic. Clamped to `due_date` — you
  cannot snooze past the deadline; attempting to does the sensible thing and says so.
- Idempotent: snoozing an already-snoozed reminder extends it and reports the new
  date rather than erroring.
- Autocomplete lists only reminders the caller owns or manages — the same gate call,
  run on the autocomplete interaction too.

**This closes D-12 in `docs/plans/discord-reminders-implementation.md`** ("per-member
mute of a lab reminder"), which otherwise stays dangling in two documents. Note the
distinction: `snoozed_until` is per-*subscription*, so snoozing a lab reminder
snoozes it for the whole lab. Per-member muting remains out of scope.

### C-6 · `/mylo cancel`

- Blocked on **Q-7** (soft cancel vs. the existing hard delete).
- Same autocomplete + gate as snooze. Idempotent; shows what changed.

### C-7 · Command tests

`mylo/tests/test_commands.py` (gateway-side, `unittest.IsolatedAsyncioTestCase`, the
existing `mylo/tests` idiom) + `apps/integrations/tests/test_command_services.py`
(the sync bodies, Django side). Cover: defer-then-followup on every command; a
forged/tampered argument is refused; ephemeral on every reply.

---

## Phase D — Cluster-first digests + the lab channel

Order within the phase: **D-1 (matcher) → D-2 (presentation) → D-3 (eligibility) →
D-4 (lab send) → D-5 (schedule)**. D-1 must land first, because a cluster-first
report over unattributed opportunities would ship a visibly broken shape.

### D-1 · Cluster attribution for opportunities (L7)

Give grants, conferences and fellowships the same cluster attribution papers have.

- **Backend matcher.** A per-cluster analogue of `fusion.combine_clusters` /
  `pipeline.fuse_clusters_pool` inside `opportunities.py` and `fellowships.py`:
  score each candidate per cluster, take the argmax for attribution, keep the
  runners-up as bridge clusters. Persist `cluster_id`, `cluster_label`,
  `per_cluster`, `bridge_cluster_ids` into `RelevanceScore.signals`, exactly as
  `pipeline._cluster_row` does for papers.
- **Dispatch rule, unchanged from papers:** cluster-scoped scoring engages only when
  the target declares **≥ 2 real clusters**; 0 or 1 (or the implicit `c-all`
  fallback) keeps today's flat path byte-for-byte. This invariant is preserved by
  every cluster feature in the repo and must be preserved here.
- **Serializer exposure.** Lift `cluster` / `per_cluster` / `bridge_clusters` from
  `SuggestionSerializer` (`serializers.py:31-33`) onto `_OpportunitySerializer`
  (`serializers.py:156`), so `GrantSerializer`, `ConferenceSerializer` and
  `FellowshipSerializer` inherit them. Views must set the `cluster_labels` context
  map so a renamed cluster re-labels without re-scoring.
- **Frontend: nothing to build.** `opportunities-section.tsx:74`,
  `conferences-section.tsx:86` and `fellowships-section.tsx:194` already render
  `{item.cluster ? <ClusterBadge cluster={item.cluster} /> : null}`, and
  `types.ts:296` already declares the field (documented as *"reserved"*). Optional
  follow-on: add a cluster tier to the grants/conferences/fellowships filter rails,
  mirroring `research-papers-section.tsx`'s existing `clusterSet` tier.
- **Cost note.** Cluster-scoped scoring multiplies per-target work by the cluster
  count. Papers already absorb this; opportunities will too. Re-check
  `OPPORTUNITY_LLM_CONCURRENCY` and the daily run's wall-clock after D-1.

**Validation:** new `test_opportunity_clusters.py` mirroring
`test_briefing_clusters.py` — a 2-cluster target attributes each grant to exactly
one cluster with bridges recorded; a 1-cluster and a clusterless target produce
output identical to today's; the fusion span-zero gotcha applies (a lone candidate
min-max normalizes to 1.0 in every cluster, so discrimination tests need competing
items). Then `run_refitting` over a real profile and eyeball the grants page.

### D-2 · Cluster-first digest structure (L5)

Invert `briefing_agents.generate_report_body` from category-first to cluster-first:
one `## <Cluster label>` section per cluster, categories inside it. With D-1 landed,
every category can appear under every cluster and no catch-all bucket is needed.

Touches: `briefing.py::_gather` (pivot bucketing to `cluster_id → category → items`),
the four section agents (one call per cluster, handed that cluster's items across
categories — a redesigned prompt contract and a rewritten `_section_fallback`),
`DailyBriefing`'s `categories`/`counts`/`new_counts`/`showcase` JSON shape
(+ migration), `DailyBriefingView` / `LabDailyBriefingView`, `mylo-report-card.tsx`,
and `daily_report_pdf.py` (promote `ReportItem.cluster_label` from a metadata chip to
a grouping key).

**Invariant:** a target with 0 or 1 real cluster still gets exactly today's
category-only report. This applies to the *user* digest too — L5 says make the user
digest match, so this is not lab-only work.

### D-3 · Preconditions and the eligibility function

`briefing.lab_digest_recipients()` — a lab is eligible only when **all** hold:

1. `Subscription.status == ACTIVE` covering the lab (reuse `tasks.select_targets`).
2. `lab_has_feature(lab, Feature.BOT_SERVER)` — re-checked here, not trusted from
   install time (L6, and Q-11 for the department-inclusion asymmetry).
3. `DiscordGuildLink.state == ACTIVE`.
4. `resolve.get_updates_channel_for_lab(lab)` is non-empty. **A blank value is a
   deliberate opt-out and is respected silently** — no warning, no incident.

Note the updates channel is independent of `announcement_channel_id`; a lab may have
one, both, or neither.

### D-4 · The lab digest compiler and sender

- `apps/content/lab_digest.py::compile_lab_digest(lab, *, today) -> LabDigest` —
  mirrors `daily_report.compile_report_for_user`, reusing `briefing._suggested_scores`
  with `{"target_lab": lab}` so the channel post can never drift from
  `/api/labs/<slug>/recommendations/`. Categories limited to `LAB_BRIEFING_CATEGORIES`
  (papers/grants/conferences — fellowships stay user-only by design).
- `reminders_discord.send_lab_digest(lab, digest)` → **enqueues** to the outbox with
  `dedupe_key = f"lab_digest:{lab.id}:{today:%Y-%m-%d}"`. This single unique key *is*
  the one-post-per-lab-per-day guarantee; re-running the pipeline is a no-op.
- **Discord shape:** a channel post is not a document. Hard limits: 2000 chars of
  content, 4096 per embed description, 6000 across all embeds, 10 embeds, 25 fields.
  L5's cluster breakdown must fit inside that or spill to the portal. Proposal
  (Q-10): one embed per cluster (max 8, matching `CLUSTER_CAPS`), each with the
  cluster's counts and its top 3 items, plus a footer linking to
  `{DISCORD_APP_BASE_URL}/app/{lab-slug}/daily`. `allowed_mentions.parse == []`
  holds; no member pings — this is an update, not a summons.

### D-5 · Scheduling

- New management command `send_lab_digests` and a new stage in `manual_all.py`'s
  `CONTAINER_STAGES`, **after `generate_daily_briefing`** (it needs the written body)
  and following `send_daily_discord_reports`' never-sink-the-run pattern.
- **Landmine:** `test_reminders_prune_ordering.py::test_tick_runs_before_prune_in_the_daily_chain`
  regex-parses `manual_all.py`'s literal `CONTAINER_STAGES` source text. Adding a
  stage is fine; reformatting the list is not.
- **No timezone work.** Explicitly out of scope, per the handoff. Note that
  `Lab.send_hour_local` exists, has a migration, and is **read nowhere** — it is dead
  configuration today and this plan does not wake it.

**Validation:** `test_lab_digest.py` — one post per lab per day; a re-run enqueues
nothing new; a blank `updates_channel_id` is silently skipped; a lapsed add-on is
skipped; a lab with no clusters gets the category-only shape.

---

## Phase E — Drift detection and portal surfacing

### E-1 · Live gateway events

New `mylo/bot/cogs/drift.py`, listeners only:

- `on_guild_remove(guild)` → `linking.guild_removed(guild.id)` → `resolve.mark_guild_kicked`.
- `on_guild_channel_delete(channel)` → if the channel is a bound announcement or
  updates channel, clear the binding and flag it.
- `on_member_remove` — **blocked on Q-4** (privileged `members` intent).

All three follow the existing async shape: cog → `mylo/linking.py` coroutine →
`mycelium.db(_sync_body)` → `resolve` imported inside the body. New write paths land
as new `resolve.py` functions, never inline in a cog.

### E-2 · Extend the reconcile sweep

`services/reconcile.py::reconcile()` gains, keeping its existing
skip-the-whole-sweep-on-a-blip guard:

- **Channel liveness** — for every ACTIVE link with a bound channel, verify it still
  exists and is postable. Use `discord_api.get_guild_channels(guild_id)` for
  existence (cheap, no user-visible side effect); reserve `preflight_channel`'s
  post-a-confirmation for bind time only, so the sweep does not spam a lab's channel
  nightly. Write `announcement_channel_ok` / `updates_channel_ok` (AD-10).
- **Membership** — if Q-4 lands on the REST path, re-verify each lab's linked
  members via `GET /guilds/{id}/members/{user_id}`.
- **Entitlement** — for each ACTIVE link, `lab_has_feature(lab, BOT_SERVER)`; on
  lapse, record it (E-4). This is the first `apps.billing` reference inside
  `apps.integrations`; import it lazily inside the function, as
  `oauth.complete_guild_link` already does.
- **Escalation** — if the guild sweep is skipped N consecutive runs, escalate the
  incident severity. Today a week of failures is silently invisible.

`reconcile()` currently has **zero tests**. E-2 adds its first.

### E-3 · Outbox failures feed the same state

`outbox.deliver_one`'s `PERMANENT` branch already writes identity/channel state
(A-4). E-3 adds the aggregate: repeated permanent channel failures for a lab clear
the binding and flag it, rather than retrying into a void every day forever.

### E-4 · Subscription lapse (L6)

- `lab_has_feature(lab, BOT_SERVER)` is checked at **delivery time** in D-1 and in
  `send_lab_channel`.
- On lapse: scheduled channel delivery stops. The guild link stays `ACTIVE`, channel
  bindings stay bound, reminders stay in the database, `/setup` still works,
  interactive commands still work. **The bot does not leave the server.** Nothing is
  deleted. If the lab re-subscribes, delivery resumes with no reconfiguration.
- The lab's managers get one in-app `Notification` and a portal banner. The shared
  channel is **not** nagged (Q-8).

### E-5 · Backend read surface

`GET /api/integrations/discord/health?lab=<slug>` → a new `DiscordHealthView`,
manager-gated by the existing `_manager_lab_or_error` helper, returning:

```json
{
  "guild": {"state": "active", "guild_name": "…"},
  "channels": {
    "announcements": {"bound": true,  "ok": true,  "checked_at": "…", "error": null},
    "updates":       {"bound": true,  "ok": false, "checked_at": "…", "error": "no_permission"}
  },
  "addon": {"active": true},
  "members": [
    {"username": "…", "name": "…", "linked": true,  "dm_ok": true,  "in_guild": true},
    {"username": "…", "name": "…", "linked": false, "dm_ok": null,  "in_guild": null}
  ],
  "outbox": {"dead_last_7d": 0}
}
```

Follows the repo's `.empty()` convention so an unlinked lab renders a clean empty
state rather than an error branch. All model access through `resolve.py`.

### E-6 · Portal surfacing

Five distinguishable states, in language a person can act on:

| State | Where | Copy direction |
|---|---|---|
| Never connected their Discord | member row + profile | "Not connected — connect from your profile." |
| Connected, DMs closed / bot blocked | member row + profile card | The existing `dm_ok === false` copy, reused verbatim. |
| Left the lab's Discord server | member row | "Can't be tagged in channel announcements." Note this does **not** break their personal DMs — the two are independent. |
| Channel deleted / bot lost permission | `DiscordSyncCard` | "Mylo can't post in #x — pick another channel or restore permissions." |
| Bot add-on lapsed | `DiscordSyncCard` + plan card | "Scheduled Discord updates are paused. Nothing was removed." |

- Extend `LabMember` (`types.ts:21`) with `discord_linked` / `discord_dm_ok` /
  `discord_in_guild`, and render a small `Pill` in **both** `MemberRow`
  (`member-row.tsx`) and `MemberTile` (`labs-section.tsx`) — they duplicate by design.
- Extend `DiscordGuildStatus` (`types.ts:801`) and `DiscordSyncCard`
  (`labs-section.tsx:750`) with channel health, reusing its existing
  `{tone, label}` badge function. Tones: `clay` = unreachable/error, `review` =
  setup incomplete/stale, `primary` = healthy.
- The individual case extends `DiscordCard` (`profile-section.tsx:499`) beside the
  existing reachability test.
- Data layer follows the four-file convention exactly: type in `types.ts`, fetch in
  `client.ts`, hook in `hooks.ts` (`useLabDiscordHealth`, `staleTime: 30_000`),
  component imports only the hook. **Note:** the Discord hooks live in
  `lib/portal/hooks.ts`, *not* `lib/auth-client.ts` (the handoff and repo-map both
  say otherwise; repo-map row 75 should be corrected in this change).
- Every state accounts for loading / empty / populated / error / permission-denied /
  stale, per `docs/skills/global.md`.

### E-7 · Reminder composer warning

Warn at creation time when a mention target has no linked Discord account, using the
already-computed `has_unlinked_targets` signal — but note (row K) this means building
the first render site for it, since nothing in the frontend reads reminders today.

---

## Cross-cutting

- **Boundary.** Every new `apps/integrations/services/*.py` file is auto-guarded by
  the AST test. `apps/content/reminders_discord.py`, `apps/content/lab_digest.py`,
  and the whole `mylo/` package are **not** guarded. This plan proposes extending
  `test_import_graph.py::_GUARDED` to cover `apps/content/reminders_discord.py` and
  `mylo/*.py` (module-scope model imports only), closing the convention-only half of
  the invariant. The flat `services/*.py` glob also misses subpackages — do not
  create `services/outbox/`.
- **Audit.** Every new write path calls `audit.discord_audit` with the hashed
  snowflake, extending the existing action vocabulary:
  `discord.outbox.enqueued|sent|dead`, `discord.command.<name>.{allowed,denied}`,
  `discord.guild.channel_unreachable`, `discord.guild.addon_lapsed`.
- **Voice.** All user-facing Discord copy follows `docs/styles.md` — calm, concise,
  source-aware, naming uncertainty plainly. No hype.
- **Secrets.** Two Discord credentials exist and must not be conflated: the gateway
  bot token (`DISCORD_API_KEY` in `.env-mylo`, read by `mylo/config.py`) and Django's
  `settings.DISCORD_BOT_TOKEN` (which falls back to the same value via
  `settings.py:488`). `not_configured` means the Django side, not the gateway.
- **New bot dependencies** require rebuilding `/opt/mylo-bot/venv` by hand — the bot
  does not use the repo venv (SELinux). This plan adds none.
- **Docs per phase:** `docs/repo-map.md`, `docs/api-contract.md` (E-5),
  `docs/discord-integration.md`, `docs/changelog.md`.

---

## Validation strategy

```bash
# Backend (host venv; the committed web/backend/.venv is root-owned from Docker)
export UV_PROJECT_ENVIRONMENT=/home/bdgr/.cache/mycelium-backend-venv
uv sync --project web/backend
uv run --directory web/backend python -m pytest -q
```

```bash
# Postgres-only paths (outbox claim concurrency, pgvector search)
DATABASE_URL=postgres://mycelium:mycelium@localhost:11450/mycelium uv run --directory web/backend python -m pytest -q
```

```bash
# Gateway package
uv run python -m pytest mylo/tests -q
```

```bash
# Lint + frontend (no frontend test runner exists in this repo)
npm --prefix web run lint && uv run --project web/backend ruff check web/backend && npm --prefix web run build
```

```bash
# Migrations
uv run --project web/backend python web/backend/manage.py makemigrations --check --dry-run
```

**Baseline note:** `apps/content/tests/test_high_signal.py::test_command_delivers_when_enabled`
fails on any date after ~2026-07-19 for reasons unrelated to this work (it compares
against the real clock instead of its hardcoded `TODAY`). Do not attribute it to this
change; consider fixing it opportunistically.

---

## Acceptance criteria

1. Killing Discord's API mid-run causes reminders to be **retried and delivered
   afterwards**, not lost. (`test_outbox_regressions.py`)
2. A blocked user is retried at most 5 times at 5-minute intervals, then marked
   unreachable, told **once**, and shown in the portal.
3. One logical message produces **one** Discord message, never five, even across an
   ambiguous timeout.
4. Every slash command refuses to act on an object the caller lacks permission for,
   verified against a **tampered** argument, not just a well-behaved one — and a
   non-existent object is indistinguishable from a forbidden one.
5. A slow search command still responds: deferred acknowledgment, then the answer.
6. A lab with a configured updates channel receives **exactly one** digest post per
   day; re-running the pipeline produces no duplicate.
7. Removing the bot from a test server marks the link inactive within one
   reconciliation window, whether or not the live event was received.
8. A lab lead opens the management page and sees which members are unreachable and
   why, plus channel and add-on health.
9. A lapsed add-on stops scheduled delivery and **nothing else** — the bot stays in
   the server, all data and bindings survive, interactive commands keep working.
10. **Regression tests specifically for the two duplicate-prevention guarantees:**
    one-message-per-subscription-per-day, and one-digest-per-lab-per-day.

---

## Explicit exclusions

- Timezone-aware or per-lab-hour delivery. `Lab.send_hour_local` stays dead.
- Weekly digests (only daily is in scope).
- Slack.
- Project-scoped reminders or digests (`ReminderSubscription` has no
  `target_project` and this plan does not add one).
- Per-member muting of a lab reminder (`snoozed_until` is per-subscription).
- A per-item portal permalink route (`/app/item/<id>` does not exist; links go to the
  external source or to a list page).
- Buttons/modals beyond the pagination `View` in C-4.
- Any real payment processing.
- An HTTP interactions endpoint. The gateway stays.

---

## Open questions — must be closed before build

**Closed 2026-07-26:** Q-1 → L9 (mirror the web). Q-2 → L8 (honest empty).
Q-3 → L7 (full cluster attribution now). Q-12 → L10 (per-phase plans, sequential,
validate+commit per step); the branch question is still open.

| # | Question | Blocks | Recommendation |
|---|---|---|---|
| **Q-5** | Two senders that arguably should **not** be queued: `preflight_channel` (`/setup` needs an immediate 2xx/403 verdict to tell the admin whether the bind worked) and `errors.post_embed` (queueing the outage reporter behind the outbox means an outbox outage is silent). Carve them out? | **Phase A** | **Yes, both.** Documented in `outbox.py` and asserted by a test, so nobody "finishes the migration" later by accident. |
| **Q-6** | The daily PDF's bytes are deleted immediately after the current synchronous send. Under a queue they must survive until the drain. (a) store bytes in the outbox row; (b) write to a durable path under `data/` and store a reference + a cleanup sweep; (c) keep the PDF on a synchronous send-with-inline-retry path and queue only text. | **Phase A** | **(b).** Reports are ~0.2–2 MB each; putting them in Postgres bloats the table and every `SELECT *`. A path plus the retention sweep is cheaper and debuggable. |
| **Q-8** | Who is told when a **lab channel** message dead-letters, or when the add-on lapses? Managers only (in-app + portal), or also a message in the channel? | **Phase A** | **Managers only.** Posting failures into the shared channel is noise for people who cannot fix it — and if the channel is the thing that is broken, it cannot be delivered anyway. |
| **Q-7** | `/mylo cancel`: today `DELETE /api/reminders/<id>/` **hard-deletes** and `State.CANCELLED` is unused. Switch both the API and the command to soft-cancel? | Phase C | **Yes** — soft-cancel both, so the bot and the web behave identically and cancellation is auditable. Small behavioural change to an endpoint with no listing UI. |
| **Q-9** | Should `/mylo digest` and `/mylo saves` be scope-aware (personal vs. a lab), or personal-only? | Phase C | **Scope-aware, defaulting to personal**, lab choices limited to labs the caller can access. Mirrors the portal's workspace switcher. |
| **Q-10** | The lab channel post shape. The handoff said "err short for a shared channel"; L5 says "structured like the user digest". Discord caps a message at 6000 embed characters. | Phase D | **One embed per cluster, top 3 items each, hard-capped at 8 embeds** (matching `CLUSTER_CAPS`), everything else behind the portal link. Honours L5's structure while staying scannable. |
| **Q-4** | "Member left the server" detection needs the **privileged Members intent** (Developer-Portal toggle, plus Discord verification review past 100 guilds). (a) enable it; (b) detect via REST in the reconcile sweep instead. | Phase E | **(b).** No external approval dependency, and the handoff already accepts reconciliation as the safety net. Revisit if real-time matters. |
| **Q-11** | `entitlements._lab_subscriptions()` unions `scope_lab` **or** `scope_department` **without** honouring `Lab.department_plan_included` — so a department that buys the bot add-on grants `BOT_SERVER` even to labs it explicitly excluded from its plan. Seat billing *does* honour the flag. Intentional? | Phase E (and billing generally) | Looks like an oversight. **Recommend aligning `_lab_subscriptions` with `seat_sync.paying_scope_for_lab`** — but it changes billing behaviour for existing labs, so it should be its own small, separately-reviewed change, not a side effect of this one. |
| **Q-13** | Branch. Other sessions share this checkout and a stray `git add -A` can sweep uncommitted files (memory `concurrent-agents-shared-worktree`); a worktree would isolate but cannot be browser-verified (memory `preview-pinned-to-main-checkout`). | **Phase A** | **A feature branch off `main`**, one per phase, merged to `main` when that phase's plan is complete and validated. Isolation without losing preview verification. |
