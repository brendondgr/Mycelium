# Discord × Mycelium — Identity & Lab Linking

Implements the three linkable relationships between Mycelium and Discord:

1. **Mylo joins a Discord server** (guild install, verifiably bound).
2. **A lab is authenticated to that server** (guild ↔ Lab, gated on real lab authority).
3. **A user links their Mycelium profile to Discord** (Discord identity ↔ User).

Out of scope (by design): digest content, delivery/routing, papers/grants/fellowships,
relevance, entitlements, mass-send. The one delivery-shaped thing here — the **DM
reachability probe** — sends no content; it only answers "is this link usable?"

## Architecture (as built)

**Core constraint: Mylo owns no data.** Everything is Mycelium's Postgres. There is
no Mylo database, schema, or migration history.

* **`web/backend/apps/integrations/`** — the Django app: models, OAuth HTTP views,
  Celery tasks, and the service layer. `services/resolve.py` is the **single ORM
  boundary** — the only module the Discord path allows to import a model
  (enforced by `test_discord_path_imports_no_models_outside_resolve_module`).
* **Slash commands run on the existing Mylo gateway** (`mylo/bot/`), not an HTTP
  interactions endpoint. Discord routes an app's interactions to *either* the
  gateway *or* an HTTP endpoint — never both — and the gateway already serves
  `/mylo health` + `/mylo lastrun`, so adding an interactions URL would break them.
  The new commands (`/activate`, `/mylo status`, `/mylo setup`) call the same
  services via `mylo/mycelium.py`, which configures Django in the gateway process
  (the root env mirrors the backend's deps) so ORM access stays on one database.
* **OAuth is HTTP** (browser redirects → Django views); it never needs the gateway.
* **Auditing** reuses `apps.accounts.services.record_audit_event` (no new table).
  The `discord_user_id` is always hashed in audit metadata; tokens/codes never appear.
* **OAuth tokens at rest** are Fernet-encrypted (`apps/integrations/fields.py`,
  `DISCORD_TOKEN_ENC_KEY`).
* **Ephemeral state** (OAuth `state` nonces, `/activate` lockout) lives in a
  dedicated Redis db (`DISCORD_CACHE_URL`), fail-closed, surviving a restart.

### The three link paths

* **Path A (primary user link):** portal → OAuth (`identify applications.commands`,
  `integration_type=1`) → callback → `DiscordIdentity` → reachability probe.
  `applications.commands` under user-install is what grants DM rights.
* **Path B (fallback user link):** portal issues a one-time code → user runs
  `/activate code:CODE` in the hub `#activation` channel → `DiscordIdentity`. Binds
  the identity but does **not** grant DM rights the way A does — expect a higher
  `dm_ok=False` rate; the split is instrumented by `link_method`.
* **Path C (lab link):** a two-step, code-based flow a lab admin/PI drives:
  1. **Add Mylo** — the lab's **Lab settings** → Discord card → "Add Mylo to
     Discord" → bot install OAuth (`bot applications.commands`,
     `integration_type=0`, `response_type=code`, **`integration_require_code_grant`
     ON**). The binding comes only from the authoritative `guild` object in the
     token exchange — the redirect's `guild_id`/`permissions` are forgeable and
     ignored. Install → `PENDING_SETUP`.
  2. **Activate the lab** — the same card's "Activate Lab" button issues a one-time
     **10-digit code** (`POST discord/lab-code?lab=<slug>`, manager-gated, sha256
     stored, shown once). The admin/PI runs `/activate-lab code:<code>` in that
     server → the calling guild is bound `ACTIVE`. The **manager authority is proven
     at issue time** (`user_can_manage_lab` on the website), so the redeemer needs no
     linked identity; the code carries the authority into Discord. Redemption is
     lockout-guarded (shared with Path B) and one-guild-one-lab / one-lab-one-guild
     conflict-guarded. **No billing/add-on gate applies** — Mylo is already in the
     server (a slash command only runs where the bot is present) and a manager issued
     the code, so a valid code binds it; any billing checks live on the delivery path,
     not activation. `verified_via_code_grant` stays whatever the install set it to
     (True for a prior website install).

  **`/activate` is personal-only** (`code:` → Path B identity). **`/activate-lab`**
  is the lab flow above. No `default_member_permissions` gates either — the code is
  the authority. After the server is `ACTIVE`, the top-level **`/setup`** command is
  the *post-activation* step: an interactive menu (native channel pickers + turn-off
  buttons) to choose, or opt out of, two independent optional channels —
  **deadline announcements** (`announcement_channel_id`) and **daily/weekly updates**
  (`updates_channel_id`). Each selection is preflighted (post-a-confirmation) before
  binding. `/setup` requires the server to be `ACTIVE` **and** the caller to be a
  *linked* lab manager (config actions still terminate in `user_can_manage_lab`).
  The **Lab settings** card shows the live sync state (`discord/guild/status`), and
  the profile card's **Test** button re-runs the DM reachability probe on demand
  (`discord/probe`).

**Authorization invariant:** a Discord identity is authentication, never
authorization. Every action terminates in the existing
`apps.accounts.permissions` (`user_can_manage_lab`). Guild membership, guild
ownership, and Discord roles grant nothing.

## Developer-portal setup (one time)

* Application → both `GUILD_INSTALL` (0) and `USER_INSTALL` (1) integration types.
* **`integration_require_code_grant` = ON** (load-bearing for Path C).
* Register the two redirect URIs — `/api/integrations/discord/callback` and
  `/api/integrations/discord/guild-callback`, on **every public origin** the
  portal answers on. By default nothing pins them: `services.oauth` derives each
  one from the origin of the live request (`_redirect_uri`), so the flow follows
  whatever hostname the visitor used and a leftover config value can never send a
  public visitor back to `localhost`. OAuth2 forbids a relative `redirect_uri`, so
  request-derived is as close as it gets. `DISCORD_OAUTH_REDIRECT_URI` /
  `DISCORD_GUILD_REDIRECT_URI` still exist to pin one fixed origin instead.
  * This needs Django to know the real scheme: nginx forwards the front door's
    `X-Forwarded-Proto` (it terminates plain HTTP itself) and settings set
    `SECURE_PROXY_SSL_HEADER`, so a tunnelled HTTPS site builds `https://` URIs.
  * `DISCORD_APP_BASE_URL` is now only for links Mylo writes *into* Discord
    messages, which are composed with no request in hand; it follows
    `PUBLIC_HOSTNAME`.
* **No privileged intents.** Slash-commands only; do not enable `MESSAGE_CONTENT`.
* Interactions Endpoint URL: **leave blank** — interactions come over the gateway.
* **Sync the gateway venv.** The Mylo bot runs from a venv at
  `/opt/mylo-bot/venv` — deliberately **outside `$HOME`**. systemd (`init_t`)
  resolves the `ExecStart` interpreter before dropping to `User=bdgr`, and
  SELinux forbids `init_t` from reading anything under `user_home_t`; a venv in
  the repo (or one whose `bin/python` symlinks back into `~/.local/share/uv`)
  fails with `203/EXEC`. The venv is built against the **system** `python3.13`
  (`/usr/bin/python3.13`, `bin_t`), not a uv-managed interpreter under home. The
  bot configures Django in-process (`mylo/mycelium.py`), so it imports the
  backend's models — including `apps/integrations/fields.py`'s `cryptography`
  import. After any backend dependency the gateway imports is added (as
  `cryptography` was), refresh the `/opt` venv and restart the bot:

  ```bash
  # regenerate the export, then install into the OUT-OF-HOME venv.
  # NOTE: use a real file, not <(...) — sudo can't read the process-sub fd.
  uv export --no-hashes --format requirements-txt > .mylo-requirements.txt
  sudo uv pip install --python /opt/mylo-bot/venv/bin/python -r .mylo-requirements.txt
  sudo restorecon -Rv /opt/mylo-bot          # relabel new site-packages -> lib_t
  sudo systemctl restart mylo-bot.service
  ```

  First-time build of the venv:

  ```bash
  sudo dnf install -y python3.13
  sudo uv venv --python /usr/bin/python3.13 /opt/mylo-bot/venv
  sudo uv pip install --python /opt/mylo-bot/venv/bin/python -r .mylo-requirements.txt
  sudo restorecon -Rv /opt/mylo-bot
  ```

  Skip the sync and every ORM-touching slash command (`/activate`,
  `/activate-lab`, `/setup`, `/mylo status`) dies at `django.setup()` with
  `ModuleNotFoundError`, surfacing to the user as the generic "something went
  wrong on my end."
* After deploy, run a one-time `@Mylo sync global` (owner-only) so the command set
  changes (`/activate-lab` and `/setup` added, `/mylo setup` removed) propagate.

## Configuration

See `.env.example` (backend: `DISCORD_*`) and `.env-mylo.example` (gateway:
`DISCORD_API_KEY`, `ERROR_CHANNEL`, `ACTIVATION_CHANNEL`). The bot token is reused
from the gateway so there is one bot identity.

> **Do not hardcode `DISCORD_CACHE_URL` to a `localhost` URL.** `.env.example` is a
> compose `env_file`, so any active value there is injected into the backend
> container, where `localhost` is the container — not the host — and the discord
> Redis db is unreachable, making the OAuth-start endpoint 503 and the "Connect
> Discord" button silently fail. Leave it unset so it derives db 4 from `REDIS_URL`
> (which compose sets per-context), exactly like `SEARCH_CACHE_URL`. Only set it to
> pin a non-default Redis.

Generate the token-encryption key:

```
python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
```

## Reconciliation (the HTTP-only tradeoff)

Without gateway `GUILD_DELETE`/deauthorize events, a nightly sweep
(`apps.integrations.reconcile_discord`, Celery Beat `DISCORD_RECONCILE_HOUR`, or
`manage.py reconcile_discord`) marks absent guilds `KICKED` and refreshes/revokes
lapsing OAuth tokens. It skips the guild sweep on a transient API failure rather
than mass-marking links kicked.

## Verification status

The `apps/integrations` regression suite (47 tests) + the `mylo` bot tests cover
the model, service, OAuth-flow, activation, guild-binding, authorization-invariant,
error-sink, and import-graph logic with Discord HTTP mocked. **Live OAuth /
interaction round-trips require a Discord app + a test guild and were not exercised
in CI** — run the manual smoke checklist below against a real app before enabling
for users.

## Manual smoke checklist (needs a live Discord app + test guild)

**Path A** — link → probe DM lands → `dm_ok=True`; DMs off → `50007` →
`dm_ok=False`, state stays `ACTIVE`, portal shows remediation; tampered/replayed
`state` → 400, no row; snowflake already bound → 409; unlink → tokens revoked →
rows deleted → clean re-link.

**Path B** — valid `/activate code:` → ephemeral confirm, identity bound; reply
ephemeral in **all** branches; no code → ephemeral usage hint; expired code →
rejected, **not** consumed; reused code → rejected; 6 bad attempts → lockout,
survives a bot restart; outside `ACTIVATION_CHANNEL` → ephemeral pointer, no lookup;
code for user A redeemed by a Discord account bound to user B → rejected, not
consumed; plaintext code in zero logs / zero DB columns.

**Path C** — install → `PENDING_SETUP`, `verified_via_code_grant=True`, nudge
posted; forged `guild_id` on the redirect → ignored. Manager clicks **Activate Lab**
→ 10-digit code (non-manager → 403, unknown lab → 404). `/activate-lab code:<code>`
in the server → guild bound `ACTIVE` (the pending install's row flips); no linked
identity **and no billing add-on** required — the bot is already present and a manager
issued the code. Reused/expired code → rejected; bad code → rejected + counts to
lockout; 6 bad attempts → lockout; guild already bound to another lab, or lab to
another guild → `CONFLICT`, not consumed; plaintext code in zero logs / zero DB
columns; bot kicked → sweep sets `KICKED`. **Post-activation `/setup`** — before activation → "run
`/activate-lab` first"; linked non-manager → denied; a linked admin/PI sees the menu,
picks a deadline channel and an updates channel independently (each preflighted
before binding), and can turn either off; a channel the bot can't post in → refused
with a specific message, nothing bound.

**Infra** — `/mylo status` answers in DM/guild/private channel; error cascade →
one `ERROR_CHANNEL` rollup, not N; no Discord module imports a model outside
`resolve.py`.

## Deviations from the plan (v2)

* **Gateway, not HTTP-only interactions** (plan D-1) — forced by the "one app →
  one interaction transport" rule and the existing working gateway commands.
* **`scopes` is `JSONField`, not `ArrayField`** — portable across SQLite (tests)
  and Postgres; scopes are never queried.
* **Ed25519 interactions-endpoint hardening (§4) is not built** — there is no HTTP
  interactions endpoint; discord.py handles gateway transport, defer, and ephemeral.
