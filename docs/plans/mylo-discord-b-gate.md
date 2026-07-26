# Phase B — One authorization gate for inbound Discord interactions

**Status:** Executable.
**Correlation ID:** `20260726-mylo-discord-gate`
**Umbrella:** [`mylo-discord-pipeline.md`](mylo-discord-pipeline.md)
**Branch:** `feat/mylo-discord-pipeline`

---

## Objective

Every inbound Discord interaction passes through one function that, in order:
resolves identity → rate-limits → checks object permission → checks entitlement →
audits. Phase C's five commands cannot ship without it.

**Baseline entering this phase:** 1172 passed, 0 failed.

---

## Reconciliation

| # | Assumption | Reality | Consequence |
|---|---|---|---|
| A | "the payload includes identifiers … some originate on the user's client and are therefore untrustworthy" | **There is no HTTP interactions endpoint.** Mylo is a discord.py gateway client (`bot.start(token)`), authenticated at the WebSocket handshake. No Ed25519 payload exists to forge or verify. | Drop signature verification entirely. The real risk is narrower and still real: never derive authority from a command *argument*, a `custom_id`, or `username_cache` — only from `interaction.user.id`. |
| B | the gate is new | **Two of five stages exist**, uncomposed: `resolve.resolve_user` (who) and `resolve.can_manage_lab_via_discord` (→ `user_can_manage_lab`). | Compose, don't invent. |
| C | rate limiting is new | A lockout exists, but only for activation-code brute force (`state.is_locked_out`), keyed per snowflake, **fail-closed**. | Generalise that mechanism and keep the fail-closed property. |
| D | entitlement is checked per action | `lab_has_feature(lab, BOT_SERVER)` fires **once**, at guild install (`oauth.complete_guild_link:109`). Never again. | The gate becomes the point-of-use check Phase D and E rely on. |
| E | audit is centralised | `audit.discord_audit` is called ad hoc inside individual `resolve.py` write functions, never at a chokepoint. | The gate audits every outcome, allowed and denied. |
| F | `/activate-lab` should route through the gate | It was **deliberately** exempted from the billing gate on 2026-07-18 ("a valid code binds it; billing checks live on the delivery path"). It also cannot require a linked identity — it *is* the linking flow. | `/activate`, `/activate-lab` keep their own lockout path. Only post-link commands use the gate. |

---

## Steps

### B-1 · Generalised rate limiting (`services/state.py`)

`check_rate(key, *, bucket, limit, window) -> bool` on the same `discord` cache,
with the **same fail-closed contract** as `is_locked_out` — a Redis outage denies
rather than allows, because the alternative is an unmetered command surface.

Buckets from settings: `search` 5/60s (it can trigger an embedding plus five
Postgres queries), everything else 20/60s.

**Validation:** `test_gate.py::RateLimit*` — the nth call is refused; a different
snowflake is unaffected; a dead cache denies.

### B-2 · The gate (`services/gate.py`)

```python
def authorize(*, discord_user_id, action, lab_slug="", guild_id="",
              subject_id="") -> GateResult
```

Order is load-bearing: identity → rate limit → permission → entitlement → audit.
Rate limiting sits *second*, before any object lookup, so an unlinked or hostile
caller cannot use the gate itself as a database-probing oracle.

`Denial` values: `NOT_LINKED` (helpful — how to connect), `RATE_LIMITED`,
`NOT_ENTITLED` (upgrade prompt), `FORBIDDEN` (generic). **A missing object and a
forbidden object return the identical message**, so the gate never confirms that a
lab exists to someone who cannot see it.

Actions declare what they need in one table (`_ACTIONS`), rather than each command
re-deriving it — that table *is* the policy, and is what a reviewer reads.

**Validation:** `test_gate.py` — unlinked refused; non-manager refused generically;
a forged `lab_slug` naming a real lab the caller cannot see is indistinguishable
from a nonexistent one; entitlement refusal names the tier; every outcome audits
exactly once.

### B-3 · Route `/setup` through it

`mylo/linking.py::_setup_gate` becomes a call to `gate.authorize`. `/activate` and
`/activate-lab` keep their own path (row F).

**Validation:** `mylo/tests/test_linking.py` unchanged in intent; `/setup` still
refuses a non-manager and an unactivated guild.

### B-4 · Docs + changelog.

---

## Acceptance

1. Authority derives only from `interaction.user.id` — never an argument.
2. A nonexistent lab and a forbidden lab are indistinguishable to the caller.
3. Rate limiting denies when Redis is down.
4. Every interaction writes exactly one audit row, allowed or denied.
5. `/activate-lab`'s deliberate no-billing carve-out is preserved.
6. Full suite green.
