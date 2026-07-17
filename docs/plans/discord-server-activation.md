# Plan — Discord server activation via `/activate`

**Status:** complete
**Correlation ID:** 20260717-discord-server-activation

## Objective

Make activating Mylo in a Discord server a first-class, discoverable flow. After a
lab manager clicks **Add Mylo** (the bot invite, already working), they run
`/activate` in the server, pick a lab they administer, and the server is bound to
that lab (synced to the website) so Mylo can post reminders/announcements there.

The command name `/activate` currently belongs to the *personal identity*
code-redemption flow (Path B). Per the product decision, `/activate` becomes
**context-aware and does both jobs**, and `/mylo setup` is **kept but repurposed**
to the post-link step (choosing where reminders post).

## Decisions (from the user)

- **`/activate` does both.** `/activate code:XXXX-XXXX` links a personal Discord
  identity (today's Path B). `/activate lab:<lab>` binds *this server* to a lab the
  caller administers. A brand-new user links their identity first, then activates
  the server — one command, both jobs.
- **`/mylo setup` is retained**, repurposed as the *after-link* configuration step:
  set/verify the announcements channel for the server's already-bound lab.
- **Authority = Mycelium lab admin/PI**, enforced by the existing
  `apps.accounts.permissions.user_can_manage_lab` (via
  `resolve.can_manage_lab_via_discord`). This is *not* a Discord "Manage Server"
  role, so we deliberately set **no** `default_member_permissions` — that would
  wrongly block regular members from the identity-linking path.

## Current state (as built)

- **Add Mylo** = bot install OAuth (Path C) → `DiscordGuildLink` `PENDING_SETUP`.
- **`/activate <code>`** (`mylo/bot/cogs/link.py`) = Path B identity redemption,
  gated to the hub activation channel; ephemeral.
- **`/mylo setup [lab] [channel]`** (`mylo/bot/cogs/status.py`) = binds this guild
  to a lab the caller manages (or confirms a pending website install) **and** sets
  the announcements channel — the flow we are splitting.
- ORM boundary `web/backend/apps/integrations/services/resolve.py` already exposes
  everything needed: `can_manage_lab_via_discord`, `labs_managed_by_discord_user`,
  `get_guild_link`, `confirm_guild`, `bind_guild_via_command`, `GuildConflict`,
  `set_announcement_channel`, `get_announcement_channel_for_lab`, guild-state
  constants, plus billing `lab_has_feature(lab, Feature.BOT_SERVER)`.

**Consequence:** this is largely a `mylo/` orchestration + cog refactor plus
frontend copy. No new backend models or migrations. `resolve.py` is unchanged.

## Design

### `/activate` — top-level, `guild_only`, context-aware (`mylo/bot/cogs/link.py`)

Options (both optional): `code: str | None`, `lab: str | None` (autocomplete →
`linking.managed_lab_choices`). Dispatch (in `mylo/linking.activate`):

1. **both `code` and `lab`** → reject: "Use one at a time."
2. **`code`** → identity redemption (current Path B, incl. activation-channel gate).
3. **`lab`** → bind *this guild* to the chosen lab:
   - caller must have a linked identity (else nudge to `/activate code:` / OAuth),
   - caller must administer the lab (`can_manage_lab_via_discord`),
   - lab must have the `BOT_SERVER` add-on (`_needs_bot_server`),
   - if a verified `PENDING_SETUP` link exists → `confirm_guild`; otherwise
     `bind_guild_via_command`; `GuildConflict` surfaced,
   - success message points to `/mylo setup` to pick the reminders channel.
4. **neither** → context help: not linked → how to link; pending website install for
   this guild + caller manages it → confirm; linked + manages labs → show
   `/activate lab:<name>`; linked + no managed labs → the no-labs message.

### `/mylo setup` — post-link channel config (`mylo/bot/cogs/status.py`)

`/mylo setup [channel]`. Requires this guild to be **ACTIVE**-linked; if not,
nudge to run `/activate lab:<name>` first. With a channel → preflight
(`reminders_discord.preflight_channel`) + `set_announcement_channel`. Without →
show the current binding + tip. The `lab` option and all guild-binding logic move
out of setup into `/activate`.

### Orchestration (`mylo/linking.py`)

- `activate(discord_user_id, *, code, lab_slug, guild_id, guild_name, channel_id)`
  — context-aware dispatcher; sync bodies `_activate_lab_sync` / existing
  `_activate_sync` / `_activate_help_sync` run under `mycelium.db`.
- `setup_channel(discord_user_id, guild_id, *, channel_id)` — replaces the
  binding responsibility of `setup_guild`; ACTIVE-required channel config.
- `managed_lab_choices`, `status` — unchanged.

### Frontend copy (point users at the new flow)

- `web/app/src/components/portal/sections/profile-section.tsx` — `installed`
  message + the `/activate {code}` hint → `/activate code:{code}`.
- `web/app/src/components/portal/sections/labs-section.tsx` — the three connection
  hints → "run `/activate lab:<lab>`".
- `web/app/src/lib/portal/mutations.ts` — code-issue comment.

## Implementation phases

1. **Refactor `mylo/linking.py`** — context-aware `activate`, new `setup_channel`,
   keep `_activate_sync` for the code path, add `_activate_lab_sync` /
   `_activate_help_sync` (lift bind/confirm/pending logic from the old
   `_setup_sync`), add `_setup_channel_sync`. Validate: `mylo` unittests.
2. **Rewrite the cogs** — `link.py` `/activate` gains `code`/`lab` + lab
   autocomplete; `status.py` `/mylo setup` becomes channel-only. Validate: bot
   construction/extension-load tests.
3. **Frontend copy** — update the three files above. Validate: `tsc`/lint if quick.
4. **Tests** — extend `mylo/tests/test_bot.py` (activate options, setup subcommand);
   add a dispatch unit test that patches `mylo.linking.mycelium.db` to assert
   code/lab/both/neither routing without Django; confirm
   `apps.integrations.tests.test_resolve` still green.
5. **Docs** — update `docs/discord-integration.md` (Path B/C wording, the new
   `/activate` + `/mylo setup` split), `docs/repo-map.md` cog rows, and
   `docs/changelog.md`. Refresh the `discord-identity-linking` memory.
6. **Commit** (worktree), then **merge to main** (merge `origin/main` + local main
   first, per the worktree-base rule), resolving any conflicts.

## Validation & acceptance

- `uv run python -m unittest discover -s mylo` green.
- `uv run --project web/backend python manage.py test apps.integrations` green.
- Bot builds; `/activate` exposes `code` + `lab`; `/mylo` still exposes
  `health/lastrun/status/setup`.
- Manual smoke (runtime, documented not executed in CI): re-`@Mylo sync global`,
  then in a lab server an admin/PI runs `/activate lab:<lab>` → server binds
  ACTIVE; `/mylo setup channel:#x` → reminders channel bound; a non-manager is
  denied; a code still redeems via `/activate code:`.

## Exclusions

- No change to the OAuth invite ("Add Mylo") flow or `bind_guild`/`resolve.py`.
- No new Discord permission gating (`default_member_permissions`).
- No reminder/announcement delivery changes — this only governs *binding*.
