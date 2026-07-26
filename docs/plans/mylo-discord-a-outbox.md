# Phase A — Durable Discord Outbox

**Status:** Executable. Awaiting go-ahead.
**Correlation ID:** `20260726-mylo-discord-outbox`
**Umbrella:** [`mylo-discord-pipeline.md`](mylo-discord-pipeline.md) (decisions L1–L13, AD-1…AD-10)
**Branch:** `feat/mylo-discord-pipeline`
**Owner:** BDGR

---

## Objective

No outbound Discord message is lost because Discord was briefly unavailable, and no
message is ever delivered twice. Every existing sender moves behind one durable
queue, with two deliberate carve-outs.

**Why first:** B and D both depend on reliable delivery, and A touches every existing
sender — doing it later means rewriting the work.

---

## Baseline (measured on `main`, 2026-07-26)

`1105 passed, 3 failed` — all three are the same pre-existing defect (production code
reading the real clock against fixtures pinned to `TODAY = date(2026, 7, 16)`).
Postgres must be up (`docker compose up -d postgres`, published on `:11450`) or the
suite yields ~749 connection *errors* rather than results.

Two of the three sit in `reminders_tick` / `signals` — **exactly the blast radius of
this phase**. A red baseline there makes my regressions indistinguishable from the
existing rot, which is why A-0 exists.

---

## Steps

Each step ends in its own validation command and its own commit. No step begins
before the previous one is green.

### A-0 · Green the baseline

**Goal:** start Phase A from a suite that is honestly all-green, so every later red is
mine.

- `apps/content/signals.py::mark_reminders_stale_on_content_delete` reads
  `timezone.now().date()`. Make the reference date injectable and default it to the
  live clock, so the `pre_delete` hook can be driven deterministically. Because a
  Django signal receiver cannot take an extra argument, the cleanest shape is to move
  the body into a plain, testable function
  (`reminders.mark_stale_for_content(content, *, today=None)`) and have the receiver
  call it. The tests then call that function's owner with a pinned date, or freeze
  time around the `content.delete()`.
- `apps/content/management/commands/high_signal_shadow.py` gains a `--today
  YYYY-MM-DD` option, mirroring `run_reminder_tick`'s existing `--today`. The test
  passes it.

**Scope note:** this is a test-integrity fix, not feature work. It changes no
production behaviour on the live clock — only makes the clock injectable.

**Validation**

```bash
docker compose up -d postgres
export UV_PROJECT_ENVIRONMENT=/home/bdgr/.cache/mycelium-backend-venv
uv run --directory web/backend python -m pytest -q
```

Expect `1108 passed, 0 failed`.

**Commit:** `Make the prune-stale hook and high-signal command date-injectable`

---

### A-1 · Regression tests that must fail today

**Goal:** encode the two guarantees this phase exists to protect, before writing the
mechanism.

New `apps/content/tests/test_outbox_regressions.py`:

- `test_transient_discord_failure_is_retried_not_lost` — a personal reminder whose
  first attempt gets a 503 is delivered on a later drain. **Red today** (the failed
  send is sealed and never retried).
- `test_one_subscription_one_message_per_day_survives_queueing` — the anti-burst rule
  from `test_reminders_tick.py::test_worker_down_48h_no_burst`, re-asserted end to end
  through the queue: three triggered offsets produce one queued message, and one
  delivery.

Both are marked `xfail(strict=True)` at this step so the commit is green, and the
`xfail` markers are removed in A-5 when they genuinely pass. (`strict=True` means an
unexpected pass also fails the build, so the markers cannot rot.)

**Validation:** `pytest -q apps/content/tests/test_outbox_regressions.py` — 2 xfailed.

**Commit:** `Add the two outbox guarantees as strict-xfail regression tests`

---

### A-2 · The pure failure classifier

**Goal:** one place decides whether a Discord failure is worth retrying.

New `apps/integrations/services/discord_failure.py` — no model import, so the AST
boundary test covers it for free:

```python
class Verdict(StrEnum):
    OK = "ok"; TRANSIENT = "transient"; PERMANENT = "permanent"

@dataclass(frozen=True)
class Classification:
    verdict: Verdict
    retry_after: float | None = None
    reason: str = ""          # rate_limited | upstream | dm_blocked | no_permission
                              # | no_access | channel_gone | guild_gone | rejected
    error_code: int | None = None

def classify(*, status: int, error_code: int | None,
             retry_after: float | None = None) -> Classification
```

Mapping per **AD-2** in the umbrella. Note `discord_api._request` raises
`DiscordHTTPError(0, …)` for DNS/timeout/connection — `status == 0` classifies as
`TRANSIENT`, not `PERMANENT`.

Then rewrite `probe.run_probe` to branch on `classify(...)`. Its observable behaviour
must not change; `ProbeTests` passes untouched.

**Also in this step:** verify Discord's `nonce` / `enforce_nonce` contract.

> **Finding (verified 2026-07-26).** `enforce_nonce` is real and behaves as assumed:
> with `enforce_nonce: true` and a `nonce` present, Discord checks the nonce for
> uniqueness **"in the past few minutes"**; if the same author already sent a message
> with that nonce, *that* message is returned and no new one is created.
>
> Two constraints the design must absorb:
>
> 1. **`nonce` is capped at 25 characters.** A UUID (32 hex / 36 with dashes) does not
>    fit. → **A-3 uses an integer `BigAutoField` primary key**, not a UUID, so the
>    nonce is simply `str(outbox.id)`. This also gives the claim query a cheap,
>    monotonic ordering.
> 2. **The dedup window is only "a few minutes", but L4 mandates a 5-minute retry
>    interval.** So `enforce_nonce` reliably protects a fast in-drain retry, and may
>    *not* protect the 5-minutes-later attempt. It is a strong mitigation, not a
>    total guarantee.
>
> Residual risk, stated plainly rather than papered over: a send that Discord accepted
> but whose response we never received (a timeout at exactly the wrong moment) can
> still duplicate when retried outside Discord's dedup window. The claim-before-send
> in AD-4.2 means this requires a genuinely ambiguous outcome, not merely a crash.
> Narrowing it further would mean overriding L4's 5-minute interval for the first
> retry, which is the user's decision, not mine — flagged, not silently changed.

**Validation**

```bash
uv run --directory web/backend python -m pytest -q apps/integrations/tests/test_discord_failure.py apps/integrations/tests/test_services.py
```

New `test_discord_failure.py` covers every row of the AD-2 table; `ProbeTests` green.

**Commit:** `Extract Discord failure classification into one pure module`

---

### A-3 · The outbox model and its `resolve` accessors

**Goal:** durable state, reachable only through the sanctioned boundary.

- `DiscordOutboxMessage` in `apps/integrations/models.py` — fields per the umbrella's
  A-3 block. Index `(status, next_attempt_at)`; `dedupe_key` unique.
- Accessors in `services/resolve.py` **only** (AD-1): `enqueue_outbox`,
  `claim_outbox_batch`, `mark_outbox_sent`, `mark_outbox_retry`,
  `mark_outbox_permanent`, `mark_outbox_dead`, `outbox_counters`, `purge_outbox`.
- `claim_outbox_batch` uses `select_for_update(skip_locked=True)` inside
  `transaction.atomic`, flipping `PENDING → SENDING` and incrementing `attempts`
  **before** the HTTP call (AD-4.2).
- Settings: `DISCORD_OUTBOX_RETRY_SECONDS` (300), `DISCORD_OUTBOX_MAX_ATTEMPTS` (5),
  `DISCORD_OUTBOX_RETENTION_DAYS` (30), `DISCORD_OUTBOX_ATTACHMENT_DIR`
  (`data/outbox`).

**Landmine:** `skip_locked` is Postgres-only. The concurrency test takes a
Postgres-gated fixture in the style of `test_retrieval.py:24-26`; every other test in
this phase stays SQLite-safe.

**Validation**

```bash
uv run --directory web/backend python web/backend/manage.py makemigrations integrations
uv run --directory web/backend python -m pytest -q apps/integrations/tests/test_outbox_model.py apps/integrations/tests/test_import_graph.py
```

Covers: dedupe (`get_or_create` on `dedupe_key`), claim-once under concurrency
(Postgres-gated), terminal-state transitions. `test_import_graph` must stay green.

**Commit:** `Add the Discord outbox model and its resolve-boundary accessors`

---

### A-4 · The sender and the drain

**Goal:** something actually delivers the queue, with the retry policy from L4.

New `apps/integrations/services/outbox.py`:

- `enqueue(...)` — the single producer entry point.
- `deliver_one(message)` — resolves the destination **at drain time** (an identity's
  cached `dm_channel_id` may be stale), sends with `nonce` + `enforce_nonce`,
  classifies, settles through `resolve`.
- `drain(limit, now)` — claim → deliver → classify → settle.
- Retry: `next_attempt_at = now + max(300s, classification.retry_after or 0)`. A
  Discord-supplied `Retry-After` may only *lengthen* the wait. Max 5 attempts.
- `PERMANENT` with `reason == "dm_blocked"` → `resolve.set_identity_dm(dm_ok=False)`.
- Exhaustion → `mark_outbox_dead` (the A-7 notification hangs off this).
- **Carve-outs (Q-5, AD-6):** `reminders_discord.preflight_channel` and
  `errors.post_embed` never route through here. Documented in the module docstring
  and asserted by a test, so nobody "finishes the migration" later by accident.

Wiring: Celery task `apps.integrations.drain_outbox` in `tasks.py`; Beat entry
`crontab(minute="*")` in `settings.py` beside `reconcile-discord`; management command
`drain_discord_outbox [--once] [--limit N] [--stats]` for host runs and recovery.

**Validation**

```bash
uv run --directory web/backend python -m pytest -q apps/integrations/tests/test_outbox_drain.py
```

Covers: a 503 retries then succeeds; a 403/50007 marks the identity unreachable and
does **not** retry; a 429 with `retry_after=900` schedules 900s not 300s; there is no
6th attempt; the two carve-outs still call Discord directly.

**Commit:** `Drain the Discord outbox with classified retry and a 5-attempt ceiling`

---

### A-5 · Move the reminder senders onto the queue

**Goal:** the original bug is fixed, and the anti-burst rule survives queueing.

- `send_personal_dm` / `send_lab_channel` become enqueue-only, returning
  `SendOutcome(queued=True)` with no `message_id`.
- `ReminderFire.Result` gains `QUEUED`; `ReminderFire` gains an `outbox` FK.
  `_seal()` writes `QUEUED` at enqueue time (**AD-5**) — this both preserves the
  don't-send-twice seal and closes the pre-existing crash-between-send-and-seal
  duplicate window. The drain later stamps the outcome fields.
- `run_tick` keeps its **single** `_deliver` call and its unconditional, synchronous
  `_deliver_in_app` — the bell must never depend on Discord.
- `reminders_announce._announce_one` gets a real dedupe key
  (`deadline_moved:{sub.id}:{due_date}`). Today its Discord side has no idempotency of
  its own (it borrows `Notification.dedupe_key` via a `startswith` check), so this
  closes an existing double-send hole.
- Dedupe key for tick sends: `reminder:{fire.idempotency_key}`.

Tests to rewrite (they assert a synchronous transport call today):
`test_reminders_discord.py`, `test_reminders_lab.py` — assert *an outbox row with the
right payload*, then `drain()` and assert the transport call. `test_reminders_tick.py`
must pass **unchanged** (it is in-app only).

Remove the `xfail` markers from A-1.

**Validation**

```bash
uv run --directory web/backend python -m pytest -q apps/content/tests/
```

Both A-1 regression tests green; `test_reminders_tick.py` untouched and green.

**Commit:** `Route reminder and announcement sends through the outbox`

---

### A-6 · Move the daily PDF report onto the queue

**Goal:** the report survives a queued send (Q-6: durable path + cleanup sweep).

- `render_report_pdf` output is written to
  `settings.DISCORD_OUTBOX_ATTACHMENT_DIR/<date>/<uuid>.pdf`; the outbox row carries
  `attachment_ref` (path) and `attachment_filename` (what the user sees in Discord).
- `run_daily_report_send` gains an **enqueue** phase between render and cleanup;
  `_default_send` enqueues. The batch no longer deletes the bytes — the retention
  sweep (A-8) does, once the row reaches `SENT` or `DEAD`.
- `test_daily_report.py::test_send_flow_is_phased_and_cleans_up` is rewritten to
  assert the new durability contract instead of immediate deletion. The
  one-failure-does-not-sink-the-batch property is preserved.
- Dedupe key: `daily_report:{user.id}:{run_date}`.
- `deliver_one` reads the file at send time; a missing file is a `PERMANENT` failure
  with `reason="attachment_gone"`, not an infinite retry.

**Validation**

```bash
uv run --directory web/backend python -m pytest -q apps/content/tests/test_daily_report.py apps/content/tests/test_daily_report_discord.py
```

**Commit:** `Queue the daily PDF report with a durable attachment path`

---

### A-7 · Dead-letter notification (L4, Q-8)

**Goal:** the person is told **once**, in the Mycelium app, and nowhere else.

- `Notification.Kind` gains `DELIVERY_FAILED`. `choices=` is not a DB constraint here
  and no write site calls `full_clean()`, so the migration is a no-op at the database
  level.
- On `mark_outbox_dead`, write exactly one `Notification` with
  `dedupe_key = f"discord_fail:{outbox.id}"`. The outbox row is unique per logical
  message, so five attempts yield one notification.
- Recipient: for a DM, the intended user. For a channel post, every user passing
  `user_can_manage_lab` for that lab.
- **In-app only** — no Discord channel notice, no ops error-channel incident for
  this. (Per your answer: alert the user on the Mycelium app rather than anywhere
  else.)
- Copy per `docs/styles.md` — plain, actionable, names the uncertainty:
  *"Mylo couldn't deliver your deadline reminder to Discord. Your direct messages are
  closed — enable 'Allow direct messages from server members', then re-test from your
  profile."*
- `notification-bell.tsx` renders any `kind` identically today, so this appears with
  no frontend change. Whether it deserves distinct styling is a Phase E question.

**Validation**

```bash
uv run --directory web/backend python -m pytest -q apps/content/tests/test_outbox_deadletter.py
```

Five failed attempts → one notification, not five; a later identical enqueue → no
second notification; a lab-channel dead-letter notifies managers and only managers.

**Commit:** `Tell the affected person once when a Discord message dead-letters`

---

### A-8 · Counters, retention, documentation

- `outbox_counters(since)` → attempted / delivered / retried / dead. Surfaced by
  `drain_discord_outbox --stats` and consumed by Phase E.
- Weekly Beat task purges `SENT` rows (and their attachment files) older than
  `DISCORD_OUTBOX_RETENTION_DAYS`. `DEAD` / `FAILED` rows are kept for diagnosis.
- Extend `test_import_graph.py::_GUARDED` to cover
  `apps/content/reminders_discord.py`, closing the convention-only half of the
  boundary rule. (`mylo/*.py` is deferred to Phase C, which is where new gateway-side
  service calls actually land.)
- Docs: `docs/repo-map.md` (integrations row + a new task→location row),
  `docs/architecture.md`, `docs/api-contract.md` (no new endpoints in A — confirm and
  note), `docs/changelog.md`.

**Validation**

```bash
docker compose up -d postgres
export UV_PROJECT_ENVIRONMENT=/home/bdgr/.cache/mycelium-backend-venv
uv run --directory web/backend python -m pytest -q
uv run --project web/backend ruff check web/backend
uv run --directory web/backend python web/backend/manage.py makemigrations --check --dry-run
```

Full suite green.

**Commit:** `Outbox counters, retention sweep, and docs`

---

## Acceptance criteria for Phase A

1. Killing Discord mid-run causes reminders to be **retried and delivered
   afterwards**, not lost.
2. One logical message yields **one** Discord message — never five — including across
   an ambiguous timeout.
3. A blocked user is retried at most 5 times at 5-minute intervals, then marked
   unreachable and told once, in-app.
4. `preflight_channel` still answers `/setup` synchronously; `errors.post_embed`
   still reports when the outbox itself is broken.
5. The one-message-per-subscription-per-day rule holds, asserted end to end through
   the queue.
6. The full backend suite is green, including the three previously-red date tests.

---

## Out of scope for Phase A

The authorization gate (B), any slash command (C), the lab digest and cluster
attribution (D), drift detection and portal health (E). No new HTTP endpoints. No
frontend work beyond what `Notification` already renders for free.
