# Tier Enforcement Buildout — Implementation Plan

**Source of record:** the pricing matrix in the attached buildout brief (§2 below).
**Branch:** `claude/tier-enforcement` (isolated worktree).
**Scope:** P0–P6 — make models, entitlements, ingestion, both daily pipelines, the
API, the Mylo bot, and the frontend honour the pricing matrix. **P7 (Stripe/trial)
is out of scope** and deferred, exactly as the brief specifies.

---

## Objective

`apps/billing/entitlements.py` is a correct, well-factored library with **zero
callers**. Wire it in so every tier cap and capability is enforced at three layers
(request-time, pipeline-time, read-time), fix the live `accept_invitation()` seat
bug, and add the add-on model the Mylo-server tier needs — all resolving from local
rows, no payment processing required.

## Grounded findings (verified against current code)

- **Seat bug is live.** `accounts/services.py::accept_invitation` does
  `LabMembership.get_or_create` and **no** `Seat` — so an invited member of a paying
  lab resolves to `FREE`. Confirmed at `accounts/services.py:177`.
- **Entitlements has no callers.** `has_feature` is imported nowhere outside
  `billing/tests`. Every view is bare `IsAuthenticated`; every task is ungated.
- **`select_users()` is unfiltered** (`content/tasks.py:26`) — returns every active
  user, so Free accounts get the full daily paper + opportunity runs and LLM scoring.
- **The LLM `complete=` seam exists** end-to-end: `run_daily_batch(complete=…)` →
  `recommend_for_user/recommend_for_target`; `run_daily_opportunities_batch(complete=…)`
  → `_score_job`/`_score_fellowship_job`. Passing `complete=lambda _p: None` forces
  the deterministic fallback (verified: `suggest._llm_suggestions` uses
  `complete if complete is not None else _settings_complete`). **Free = this path.**
- **`complete` is currently batch-scope**, one value for the whole run. P4d moves the
  decision to *per-target* resolution inside each batch loop.
- **`_TOPIC_CAP = 12` is inert.** It lives only in migration
  `0011_drop_methods_seed_watch_topics.py` as a one-time seed cap; migrations are
  immutable, so we do **not** touch it. The live runtime cap is
  `WatchPreferenceSerializer._MAX_ITEMS = 50` in `accounts/serializers.py` — that is
  where per-tier `topic_cap` enforcement goes.
- **Reuse `DiscordIdentity`.** It is already `user` 1:1 + `discord_user_id` +
  `linked_at`; the brief's proposed `DiscordLink` is redundant. `services/resolve.py`
  is the single ORM boundary; there is **no DM digest delivery** yet, so P5's real
  gate points are identity binding (`BOT_DM`) and guild binding (`BOT_SERVER`).
- **Frontend** uses React Query (`useQuery`/`useMutation`), `lib/portal/{client,hooks,types,routes}.ts`;
  sidebar nav in `components/portal/portal-sidebar.tsx`; match pill in
  `components/portal/sections/opportunity-bits.tsx` (`MatchBadge` returns null when
  percent is null — the fallback render already exists).

## Open decisions — resolved with documented defaults

The brief supplies a recommended default for each; the user directed "implement the
plan", so we take those defaults and record them here rather than blocking.

| # | Decision | Default taken |
|---|---|---|
| D1 | Free is a public tier | **Confirmed.** `provision_workspace(personal_tier=FREE)` stays. |
| D2 | Is `WatchPreference.cadence` vestigial? | Keep it as a stored preference; **`SCHEDULED_REPORTS` is the master gate**, cadence is not read for gating. No migration. |
| D3 | Does `PAST_DUE` cover? | **No** — keep the current `status=ACTIVE`-only resolver (pins existing `test_past_due_subscription_does_not_cover`). A grace window needs dunning, which is P7. Pinned by `test_past_due_subscription_resolution`. |
| D4 | Lab minimum of 3 | Billing floor / marketing copy only. We enforce only the **15-member ceiling** at seat creation. |
| D5 | Canopy topic cap | Keep **15/member**, equal to Lab; Canopy differentiates via `CUSTOM_TOPIC_FEEDS` + `API_ACCESS`. |
| D6 | Free keeps signup scan | **Yes** — `scan_and_recommend_for_user` still runs for Free (on-demand, not scheduled), but with the LLM gate applied. |

## Architecture decisions (from the brief, adopted)

- **A1** entitlements.py is the only read path — no scattered tier-string checks.
- **A2** three layers: DRF permission (request), task filter (pipeline), `/billing/me` (read).
- **A3** reuse the `complete=` seam for the LLM gate — no new scoring code.
- **A4** add-ons are orthogonal: `effective_features = tier_features | addon_features`.
- **A5** caps are data: `TOPIC_CAPS` beside `PI_CAPS`.
- **A6** Seat is derived for Lab (membership ⇒ seat), explicit `PENDING` for Canopy dept joins.

---

## Phases (each ends with a green test run + a focused commit)

### P0 — Seat integrity  *(blocks P4; independent of P1)*
Files: `accounts/services.py`, new `accounts/management/commands/reconcile_seats.py`.
1. Add a billing helper `billing/seats.py::grant_seat_for_membership(user, lab)` (and
   dept variant) that resolves the scope's active `Subscription`, refuses past the tier
   member ceiling (`PI`-style guard using `TIER_MEMBER_CAPS`; Lab=15), and
   `update_or_create`s a `Seat` (Lab → `ACTIVE` + `payer_lab`; Dept join → `PENDING` +
   `payer_department`). Idempotent; re-activates a previously `REVOKED` seat.
2. `accept_invitation` — after the membership create, call the helper in the same
   atomic block. Lab with no active subscription ⇒ no seat (Free lab, nothing to grant).
3. Membership removal path: since no lab-member-removal endpoint exists yet, add a
   `revoke_seat_for_membership` helper + wire it wherever a `LabMembership`/`DeptMembership`
   is deleted (none in prod today; export the helper + cover it by test so the future
   endpoint uses it). **Never hard-delete a seat** → `status=REVOKED`.
4. `reconcile_seats [--dry-run]` management command — backfill every membership on an
   active subscription that has no active seat; report counts.
- **Validate:** new `billing/tests/test_seats.py` +
  `accounts/tests/test_invitations.py` additions:
  `test_invited_lab_member_resolves_to_lab_tier`, `test_seat_revoked_not_deleted_on_membership_removal`,
  `test_lab_seat_creation_refused_past_15_members`. Run `pytest apps/billing apps/accounts -q`.
- **Exit:** an invited member of an active Lab sub resolves to `effective_tier()==LAB`.

### P1 — Entitlement vocabulary  *(foundation; independent of P0)*
Files: `billing/entitlements.py`, `billing/models.py` (+ migration `0002`).
1. New `Feature` members: `LLM_FIT_SCORING`, `SCHEDULED_REPORTS`, `CONFERENCE_ALERTS`,
   `FELLOWSHIP_MATCHING`, `BOT_DM`, `BOT_SERVER`, `CUSTOM_TOPIC_FEEDS`, `API_ACCESS`.
2. Re-grant the tiers per matrix: `_FREE` = account+basic+semantic search+relevance
   only (no `LLM_FIT_SCORING`, no `SCHEDULED_REPORTS`); `_SPORE` adds the intelligence
   line + `BOT_DM`; `_LAB` = team features, **`BOT` removed / `BOT_SERVER` NOT tier-granted**;
   `_CANOPY` adds `CUSTOM_TOPIC_FEEDS` + `API_ACCESS`. Keep legacy names as aliases where
   still referenced so nothing breaks.
3. `TOPIC_CAPS = {FREE:3, SPORE:10, LAB:15, CANOPY:15}` + `topic_cap(user)` +
   `within_topic_cap(user, count)` (per-member — uniform lookup).
4. `TIER_MEMBER_CAPS = {FREE:1, SPORE:1, LAB:15, CANOPY:None}` for the P0 ceiling.
5. `AddOn` (slug e.g. `bot_server`) + `SubscriptionAddOn` (FK sub, FK add-on, status)
   models + migration; `addon_features(user)`; `effective_features = tier | addons`.
- **Validate:** `test_addon_grants_bot_server_tier_alone_does_not`,
  `test_topic_cap_rejects_over_limit_per_tier`, updated tier-grant assertions,
  `test_past_due_subscription_resolution`. `pytest apps/billing -q`; `manage.py makemigrations --check`.
- **Exit:** `has_feature(free, LLM_FIT_SCORING) is False`; lab+addon has `BOT_SERVER`, lab alone does not.

### P2 — Read surface  *(depends P1)*
Files: `billing/serializers.py`, `billing/views.py`, `billing/urls.py`, mount in
`config/urls.py`; frontend `lib/portal/{types,client,hooks,routes}.ts`.
- `EntitlementSerializer`: `tier`, `features[]`, `topic_cap`, `topics_used`,
  `seat_count`, `pi_cap`, `addons[]`.
- `GET /api/billing/me/` (IsAuthenticated).
- `Entitlements` type + `fetchEntitlements` + `useEntitlements()`.
- **Validate:** `billing/tests/test_billing_api.py::test_free_me_endpoint`; `pytest apps/billing -q`;
  `npm run -w web/app typecheck` (worktree can't browser-verify — memory).
- **Exit:** Free user `/api/billing/me/` → `tier:"free"`, `topic_cap:3`, no `llm_fit_scoring`.

### P3 — Request-time enforcement  *(depends P1, P2)*
Files: new `billing/permissions.py`; `accounts/serializers.py` (`validate_topics`),
`accounts/models.py` (`WatchPreference.topics_over_cap`, migration), gate custom-feed/API endpoints.
- `RequiresFeature(feature)` `BasePermission` → 403 body `{detail, required_tier, upgrade_url}`.
- `WatchPreferenceSerializer.validate_topics`: reject `len > topic_cap(user)` (context user).
- **Downgrade edge:** never delete topics. Add `WatchPreference.topics_over_cap` flag,
  honour first N on read, surface it.
- **Validate:** `test_topic_cap_rejects_over_limit_per_tier` (API 400, not truncation),
  `test_downgrade_does_not_delete_topics_over_cap`; `pytest apps/accounts -q`.

### P4 — Pipeline enforcement  *(load-bearing; depends P0, P1)*
Files: `content/tasks.py`, `content/pipeline.py`, `content/opportunities.py`,
`content/onboarding_match.py` (or its view).
- **4a** `select_users` → keep only `has_feature(u, SCHEDULED_REPORTS)`; prefetch
  subscriptions/seats to avoid N+1.
- **4b** `select_targets` → labs filtered to those with an `ACTIVE` subscription.
- **4c** `areas_for(user)` per-user opportunity areas (grants/conferences/fellowships
  each gated) — thread per-target areas through `run_daily_opportunities_batch`
  (batch-scope → per-target). The one real signature change.
- **4d** LLM gate: resolve `complete` per target in `run_daily_batch` and
  `run_daily_opportunities_batch` — `default if has_feature(u, LLM_FIT_SCORING) else (lambda _p: None)`.
- **4e** `scan_and_recommend_for_user` (+ onboarding match view): Free still runs, but
  LLM-gated and topics capped at 3.
- **Validate:** `test_free_user_excluded_from_select_users`,
  `test_free_user_gets_fallback_origin_not_llm`, `test_spore_user_included_and_gets_llm_scoring`,
  `test_areas_for_free_user_is_empty_tuple`, cancel-lab-drops-from-select_targets;
  `pytest apps/content -q`.
- **Exit:** a Free user is absent from `select_users()`, gets zero rows from a full
  `run_daily_suggestions`, and `fallback` origin from onboarding match.

### P5 — Mylo Bot gating  *(depends P1, P3; parallel with P4)*
Files: `integrations/services/resolve.py` (or `oauth.py`/`activation.py` call sites),
`mylo/linking.py`. Reuse `DiscordIdentity` (no new model).
- Guild binding (`bind_guild` / `bind_guild_via_command`) checks `Feature.BOT_SERVER`
  on the **lab** subscription; refuse + upgrade message if absent.
- DM identity binding checks `Feature.BOT_DM` (Spore+); grant via `SubscriptionAddOn`
  is what makes `BOT_SERVER` real.
- **Validate:** `integrations/tests` — lab-without-addon guild bind refused;
  lab-with-addon allowed; `pytest apps/integrations -q`.

### P6 — Frontend lock states  *(depends P2)*  → delegated to a Sonnet subagent
Files: `components/portal/portal-sidebar.tsx`, `sections/*`, `lib/portal/*`.
- `useEntitlements()` drives locked cards, the `n / topic_cap` meter, upgrade CTAs.
- Hide the Daily Reports nav entry entirely for Free.
- Show "semantic match" instead of a Mylo percent when `LLM_FIT_SCORING` absent.
- **Validate:** `npm run -w web/app typecheck` + `lint` + `build` (no browser in worktree).

---

## Cross-cutting validation
- Backend: host venv (`UV_PROJECT_ENVIRONMENT=~/.cache/mycelium-backend-venv`) +
  `DATABASE_URL=sqlite:///…` for fast offline runs; `manage.py makemigrations --check`;
  `ruff check`. Full `pytest -q` before the final merge.
- Frontend: `typecheck` + `lint` + `build` in the worktree (node_modules hardlinked).
- `docs/changelog.md` updated per the global schema; `docs/repo-map.md` updated for the
  new `billing` API surface + `reconcile_seats` command.

## Explicit exclusions
No Stripe, no trial/`TRIALING` status, no dunning UX, no new scoring algorithm, and
**no data destruction on downgrade** — ever.
