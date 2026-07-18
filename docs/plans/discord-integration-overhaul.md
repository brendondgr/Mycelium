# Discord Integration Overhaul — Lab Activation & `/setup`

**Correlation ID:** `20260718-discord-integration-overhaul`

## Objective

Restructure the lab-side Discord flow into a clear two-step experience —
**Add Mylo → Activate Lab** — backed by a lab-scoped activation code, a dedicated
`/activate-lab` command, and an interactive `/setup` channel picker with separate,
optional deadline-announcement and daily/weekly-update channels. Restyle the lab
settings Discord card with Discord's brand colors + logo and add an adjacent
**Activate Lab** button.

## Resolved decisions (from the product owner)

1. **Command shape — replace, don't duplicate.** Add `/activate-lab code:<code>`
   (code-based, no personal-identity requirement — the manager-issued code is the
   authority). **Remove the `lab:` branch** from `/activate`, leaving `/activate`
   as personal-identity linking only (`code:`). The old autocomplete/Discord-native
   bind path and its tests are dropped.
2. **Daily/weekly updates channel — config only now.** `/setup` stores and toggles
   an updates channel (opt-in/opt-out), but wiring actual recurring delivery to
   Discord is a follow-up, out of scope here.
3. **`/setup` becomes a top-level interactive command** (replaces `/mylo setup`),
   rendering a menu (channel-select + turn-off buttons) for two independent,
   optional channels.

## Assumptions & invariants preserved

- **Auth invariant (load-bearing):** a Discord identity is *authentication only*;
  every state change terminates in `apps.accounts.permissions.user_can_manage_lab`.
  - **Lab activation code** carries the manager authority: it is *issued* only by a
    lab manager on the website (`user_can_manage_lab` at issuance). Possession +
    running `/activate-lab code:` in a guild binds that guild — no linked identity
    required for the redeemer. The bot-server add-on is re-checked at redemption.
  - **`/setup`** still gates on `can_manage_lab_via_discord` (a *linked* manager),
    because it is an ongoing config action with no per-action code. A caller who
    activated via code but has not linked their own Discord is told to link first.
- **Single ORM boundary:** every new DB touch on the Discord path goes through
  `apps/integrations/services/resolve.py` (enforced by
  `test_discord_path_imports_no_models_outside_resolve_module`).
- **Mylo owns no data:** the new code/channel rows live in Mycelium's Postgres.
- **Code format:** a **10-digit numeric** code, displayed grouped `XXXXX-XXXXX`;
  only its sha256 is stored, shown once at issue. Redemption is lockout-guarded
  (reuse `state.is_locked_out`/`record_failure`/`clear_failures`, keyed on the
  redeemer's snowflake), single-use, TTL-bound (`DISCORD_ACTIVATION_TTL_SECONDS`,
  default 15 min). Brute force is impractical: 6 guesses/hr vs 10^10, plus the
  add-on gate and one-guild-one-lab conflict guard.

## Ordered implementation phases

Each phase ends with an explicit validation gate; do not advance until it passes.

### Phase 0 — Isolation & baseline
- Create a git worktree off `main`; merge local `main` in (worktree base is
  `origin/main`, which lags — see the worktree memories). Hardlink-copy
  `web/node_modules` for the Next build.
- **Validate:** baseline `uv run --project web/backend pytest apps/integrations`
  is green before any edit; `git status` clean.

### Phase 1 — Backend data model (`apps/integrations`)
- New model `DiscordLabActivationCode` (`lab` FK, `issued_by` FK, `code_hash`
  sha256, `created_at`, `expires_at`, `consumed_at`, `consumed_by_discord_id`,
  `consumed_guild_id`), mirroring `DiscordActivationCode`'s hash-only discipline.
- Add to `DiscordGuildLink`: `updates_channel_id` (CharField, blank) +
  `updates_channel_verified_at` (nullable DateTime). `announcement_channel_id`
  stays the **deadline-announcements** channel.
- Migration `0003_*`.
- **Validate:** `makemigrations --check --dry-run` clean after adding; migration
  applies on SQLite; `pytest apps/integrations` green.

### Phase 2 — Backend services (`resolve.py` + `lab_activation.py`)
- `resolve.py`: `store_lab_activation_code(lab, user, code_hash, expires_at)`
  (supersedes prior live codes for the lab); `consume_lab_activation_code(
  code_hash, discord_user_id, guild_id, guild_name)` → atomic: classify
  not_found/expired/already_used, bind guild ACTIVE via the existing one-guild-one-lab
  guard (reuse `bind_guild_via_command` semantics), stamp consumed, audit;
  `set_updates_channel`/`get_updates_channel_for_lab`; `clear_announcement_channel`/
  `clear_updates_channel`.
- New `services/lab_activation.py`: `issue_code(user, lab)` (10-digit numeric,
  store hash, return display form) + `redeem(code_input, discord_user_id,
  guild_id, guild_name)` → `RedeemResult` with outcomes {ok, locked_out,
  not_found, expired, already_used, conflict, bot_server_required}. Add-on gate
  (`lab_has_feature(lab, Feature.BOT_SERVER)`) checked before binding.
- **Validate:** new `pytest` unit tests for issue/redeem/lockout/conflict/add-on;
  import-graph test still passes (no model import outside `resolve`).

### Phase 3 — Backend HTTP (`views.py` + `urls.py` + serializers)
- `DiscordLabActivationCodeView` (POST, `IsAuthenticated`, `_manager_lab_or_error`
  gate on `?lab=<slug>`) → `{code, expires_in}`. Route `discord/lab-code`
  (both slash + no-slash via `_both`).
- Optionally surface `updates_channel_id` on `DiscordGuildStatusSerializer` (read
  side; low priority — include if cheap).
- **Validate:** `pytest apps/integrations/tests/test_views.py` incl. new cases
  (manager issues; non-manager → 403; unknown lab → 404).

### Phase 4 — Bot: `/activate` (personal only) + `/activate-lab`
- `mylo/linking.py`: drop `lab_slug` handling from `activate()` and remove
  `_activate_lab_sync`/`_activate_help_sync`/`managed_lab_choices`/
  `_managed_lab_choices_sync`/`_needs_bot_server`/`_require_linked`. Add
  `activate_lab(discord_user_id, guild_id, guild_name, code)` →
  `_activate_lab_code_sync` calling `lab_activation.redeem`.
- `mylo/bot/cogs/link.py`: `/activate` keeps only `code:` (personal); remove the
  `lab` param + autocomplete. Add `/activate-lab code:` (guild-only, ephemeral).
- **Validate:** `mylo/tests/test_linking.py` updated (remove lab-branch tests, add
  `/activate-lab` redeem/lockout/conflict/no-guild/wrong-code cases); `pytest`
  green. `test_bot.py` command-registration expectations updated.

### Phase 5 — Bot: interactive `/setup`
- New cog `mylo/bot/cogs/setup.py` with a top-level `/setup` command (guild-only).
  Handler: defer ephemeral → require ACTIVE guild link + `can_manage_lab_via_discord`
  → render an ephemeral `discord.ui.View` with two `ChannelSelect`
  (`channel_types=[text, news]`) rows — **Deadline announcements** and
  **Daily/weekly updates** — plus **Turn off** buttons for each. Selecting a
  channel runs `preflight_channel` (post-a-confirmation proof) then binds via
  `resolve.set_announcement_channel` / `set_updates_channel`; turn-off clears the
  field. Every item is optional; the menu shows current state.
- `mylo/linking.py`: sync helpers `setup_state(discord_user_id, guild_id)` (auth +
  current channels), `bind_deadlines_channel`/`bind_updates_channel`/
  `clear_deadlines_channel`/`clear_updates_channel`.
- Register `mylo.bot.cogs.setup` in `client.py` `EXTENSIONS`. Remove `/mylo setup`
  from `status.py`.
- **Validate:** `pytest mylo/tests` for the new linking helpers (auth gate, bind,
  clear, not-active). Interactive View round-trip is manual-smoke only (needs a
  live guild) — document it.

### Phase 6 — Frontend (`web/app`)
- Add `DiscordIcon` (official Discord logo SVG mark) to
  `components/portal/icons.tsx`.
- `lib/portal/client.ts`: `issueLabActivationCode(slug)` → POST
  `discord/lab-code?lab=<slug>`. `types.ts`: response type.
  `hooks.ts`: `useIssueLabActivationCode()`.
- `sections/labs-section.tsx` `DiscordSyncCard`: restyle the primary button to
  Discord blurple (`#5865F2`) with the logo + white text ("Add Mylo to Discord");
  add an adjacent **Activate Lab** button that issues the code and renders
  `/activate-lab code:XXXXX-XXXXX` + expiry. Update copy to reference
  `/activate-lab` (not `/activate lab:`). Two-step affordance: Add (step 1) →
  Activate (step 2).
- Update the `installed`/pending copy in `profile-section.tsx` +
  `labs-section.tsx` that still says `/activate lab:<...>`.
- **Validate:** `npm run -w web/app typecheck` (tsc) + `lint` + `build` all green
  (frontend can't be browser-previewed from a worktree — preview is pinned to the
  main checkout). Light-and-dark button styling reviewed against `styles.md`
  (blurple is the one sanctioned exception to the botanical palette — it is
  Discord's brand, used only for the Discord affordance).

### Phase 7 — Docs, changelog, memory
- Update `docs/discord-integration.md` (Path C is now code-based `/activate-lab`;
  `/setup` interactive two-channel picker; `/activate` personal-only), the smoke
  checklist, and `docs/repo-map.md` rows (integrations, mylo cogs).
- Add `docs/changelog.md` entry (schema: `MODIFIED`,
  `20260718-discord-integration-overhaul`).
- Update the `discord-identity-linking` memory to reflect the new command shape.
- **Validate:** links/paths resolve; repo-map rows match the code.

### Phase 8 — Full validation, commit, merge
- **Validate:** whole `apps/integrations` + `mylo` suites green;
  `makemigrations --check`; frontend tsc/lint/build green; run the `verify` skill
  reasoning over the changed flow.
- Commit in the worktree (concise, no AI attribution). Merge the worktree branch
  into local `main`, resolving any conflicts; re-run the backend + frontend
  validation on `main` post-merge. (No push.)

## Public interfaces that change

| Surface | Change |
|---|---|
| `POST /api/integrations/discord/lab-code?lab=<slug>` | **New.** Manager-only. → `{code, expires_in}` |
| Slash `/activate` | `lab:` option **removed**; personal `code:` only |
| Slash `/activate-lab code:` | **New.** Redeems a lab code, binds this guild |
| Slash `/mylo setup` | **Removed** → replaced by top-level `/setup` |
| Slash `/setup` | **New.** Interactive two-channel picker (opt-in/opt-out) |
| Model `DiscordLabActivationCode` | **New** table + migration |
| `DiscordGuildLink.updates_channel_id` / `updates_channel_verified_at` | **New** columns |

## Acceptance criteria

- Lab settings shows a Discord-branded **Add Mylo to Discord** button (blurple +
  logo) and an adjacent **Activate Lab** button that yields a 10-digit code with
  `/activate-lab code:` instructions and an expiry.
- A manager-issued code, run via `/activate-lab code:` in a guild where Mylo is
  present, binds that guild to the lab ACTIVE (add-on-gated, conflict-guarded,
  lockout-guarded), and the lab card flips to "Synced".
- `/setup` presents an interactive menu; a linked manager can set/clear the
  deadline channel and the updates channel independently; nothing is mandatory;
  the bot verifies it can post before binding.
- `/activate` no longer offers `lab:`; `/mylo setup` no longer exists.
- All backend + bot suites green; frontend tsc/lint/build green;
  `makemigrations --check` clean.

## Explicit exclusions

- Actual recurring delivery of daily/weekly updates to the updates channel (config
  stored only).
- Any change to Path A OAuth, personal identity linking, or the reminders tick /
  delivery beyond reading the two channel fields.
- Live Discord OAuth / interaction round-trips (manual smoke only; not in CI).
