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
  `/activate code:CODE` in **any Discord server Mylo is already in** →
  `DiscordIdentity`. The portal panel is three steps in the order they are done:
  join the server (`DISCORD_INVITE_URL`; the step is dropped when unset rather
  than offering a dead link), copy the command, wait. The command and the invite
  are composed by the API, not assembled in the client, so renaming the slash
  command cannot leave the portal quoting the old one. The response carries an
  absolute `expires_at`, and while a code is live the profile card polls
  `discord/status` every 3s and stops on success — the gateway writes the link, so
  nothing else would tell the browser it happened. Joining the Mycelium hub is
  *not* a prerequisite: a guild slash
  command proves in one shot that Mylo is installed there and that the caller is a
  member of it, which is the whole requirement. The hub's `#activation` channel is
  still enforced, but only *inside the hub guild* (`DISCORD_HUB_GUILD_ID`), to keep
  that server tidy; in every other server any channel works. A user-install
  invocation from a server Mylo is absent from is refused before any code lookup.
  Binds the identity but does **not** grant DM rights the way A does — expect a
  higher `dm_ok=False` rate; the split is instrumented by `link_method`.
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
     lockout-guarded (shared with Path B). **No billing/add-on gate applies** — Mylo is already in the
     server (a slash command only runs where the bot is present) and a manager issued
     the code, so a valid code binds it; any billing checks live on the delivery path,
     not activation. `verified_via_code_grant` stays whatever the install set it to
     (True for a prior website install).

* **Departments:** `/activate-department code:<code>` does the same for a department.
  The code comes from `POST discord/department-code?department=<id>`
  (department-manager-gated). It binds the department only, never its labs.

  **Servers, bindings, routes.** A server (`DiscordGuildLink`) records install and
  presence only. Each lab or department activated in it is a
  **`DiscordTargetBinding`** (lab XOR department, unique per server), and each
  binding has its own **`DiscordChannelRoute`** rows (`deadlines`, `updates`, and the
  opportunity forums `grants` / `fellowships` / `conferences`). A department server
  can hold the department and several labs, and a lab can also have a server of its
  own; binding a lab into its department's server needs the lab's own code. Each
  binding is configured and switched off on its own
  (`POST discord/bindings/<id>/remove`, that binding's own managers only), and
  removing one leaves every other binding working. A kicked server silences its
  bindings without deleting their routes. The older lab features (deadline
  reminders, the lab digest, weekly and report re-sends) read the lab's **primary**
  binding — its oldest live binding with the route in question — so they behave
  exactly as they did with one server per lab. Server-scoped commands that need a
  lab (listening, `lab_digest`) find it only when the server holds exactly one lab
  binding; otherwise the lab must be named.

  **`/activate` is personal-only** (`code:` → Path B identity). **`/activate-lab`**
  and **`/activate-department`** are the server flows above. No
  `default_member_permissions` gates them — the code is the authority. After a
  binding is `ACTIVE`, the top-level **`/setup`** command is the *post-activation*
  step for one binding: an interactive menu (native channel pickers + turn-off
  buttons) to choose, or opt out of, two independent optional channels — **deadline
  announcements** (route `deadlines`) and **daily/weekly updates** (route
  `updates`). In a server with several bindings it first asks which lab or
  department to configure. Each selection is preflighted (post-a-confirmation)
  before binding. `/setup` requires an `ACTIVE` binding **and** the caller to be a
  *linked* manager of that binding's lab or department (the gate's `binding_id`
  check terminates in `user_can_manage_lab` / `user_can_manage_department`).
  The **Lab settings** card shows the live sync state (`discord/guild/status`), and
  the profile card's **Test** button re-runs the DM reachability probe on demand
  (`discord/probe`).

**Authorization invariant:** a Discord identity is authentication, never
authorization. Every action terminates in the existing
`apps.accounts.permissions` (`user_can_manage_lab`, `user_can_manage_department`).
Guild membership, guild ownership, and Discord roles grant nothing.

## Opportunity announcements

One forum thread per newly fitting grant, fellowship or conference, in each server
binding of a lab or a department that routes that kind. Behind
`OPPORTUNITY_ANNOUNCEMENTS_ENABLED` (off), the `OPPORTUNITY_ANNOUNCEMENTS` plan
feature (Lab and Canopy) and the `BOT_SERVER` add-on.

* **Engine** (`apps/content/announce*.py`): slate entrants only, never twice; the
  first run seeds the six best open items (kinds interleaved) and passes over the
  rest for good; a bounded editor writes each post behind a verifier (no digits,
  only offered people) with a template fallback.
* **Delivery** (`apps/content/discord_announcements.py`) produces outbox rows in
  two thread modes: `forum_thread` (start a thread; its id lands on
  `AnnouncementPost.thread_id`) and `thread_update` (one retry-safe unit: patch the
  thread, edit its opening post, reply, then an optional `after_patch`). A changed
  call **updates its own thread in place** — unarchived, renamed `[🚨 Update <Mon
  D>] <title>`, tagged *Updated*, opening post edited with *What changed*, and a
  reply tagging exactly the people following it — at most once a thread per night.
  Forums Mylo creates sort by recent activity, so that reply moves the thread to
  the top. Finished calls are tagged *Closed* and archived. The closing-soon list is
  a new thread each morning in `#grants` and `#fellowships`; yesterday's is
  deleted, and a day with nothing closing posts nothing and still takes it down.
* **Buttons** (`mylo/bot/cogs/announcements.py`, persistent ids
  `ann:<post>:<action>` handled by an `on_interaction` listener) →
  `apps/content/announcement_actions.py`, each through the gate's `ann_follow` /
  `ann_not_for_us` actions against the post's own lab or department.
  *Interested* reacts, saves, sets the target's default nudge (2 weeks, a tag in the
  thread) and DMs the full details with *Change reminder* / *Open the thread* /
  *Stop following*. *Remind me* is an ephemeral picker (2 days … 2 months, 2 weeks
  preselected, past choices hidden, up to five): by DM it is an ordinary
  `ReminderSubscription` (so it follows a moved date and shows on the Reminders
  page); as a thread tag it is an `AnnouncementNudge`, whose fire date is computed
  nightly from the current deadline. One tag per person per night, and a nudge
  whose moment has already passed is never sent late. *Not for us* is managers
  only and keeps the reason.
* **`/setup` step** (`📣 Opportunity announcements…` in the `/setup` menu →
  `apps/content/announcement_setup.py`) configures one binding: **Create them for
  me** (a category and three tagged forums), or pick existing forums (each proven
  by starting and deleting a thread), who can start posts (everyone, managers only,
  or chosen roles — replies stay open to everyone), and **Turn on**, which runs the
  activation seed and the closing-soon list straight away.
* **Search links** (`apps/content/announcement_links.py`): `/mylo search` passes
  the server it ran in; a result announced in one of that server's bindings shows
  "💬 Already discussed here → thread", and a manager of a binding there gets
  "📣 Announce to …" (`annx:<binding>:<content>`, gate action `ann_manual`), which
  posts once and is removed from the result. A DM, or a server without
  announcements, shows neither. The web search card's `discord` list does the same
  for every server the reader's labs and departments are bound in. A thread deleted
  by hand is marked `deleted_at` — by the gateway's raw thread-delete event, by a
  send that finds it gone, or by the nightly `verify_threads` backstop — and is
  never linked again; announcing it again starts a fresh thread.
* **Permissions Mylo needs:** Send Messages and Embed Links in the forums; Manage
  Threads to rename, retag, archive and unarchive its threads; Manage Channels only
  for **Create them for me** and for adding its tags to a forum you chose; Manage
  Roles only for the "who can start posts" rules.

* **Departments** hear only about calls a lab could not take on alone
  (`apps/content/dept_level.py`: institutional selection, department applicant,
  department-scale programme). A department has one `#dept-opportunities` forum
  routing all three kinds, tagged by kind and reason; its post adds *Why it's here*
  (the reason and the quoted sentence) and names *Labs that could lead*
  (`lab_fit.py`), never people, and never tags anyone. A department fellowship
  shows counts only; each member who may be eligible gets one DM. A department is
  scored only while its announcements are on.

## Developer-portal setup (one time)

* Application → both `GUILD_INSTALL` (0) and `USER_INSTALL` (1) integration types.
* **`integration_require_code_grant` = ON** (load-bearing for Path C).
* Register the two redirect URIs — `/api/integrations/discord/callback` and
  `/api/integrations/discord/guild-callback`. Run `manage.py discord_check` and
  paste what it prints; it is the same resolution `services.oauth` performs.
  Discord matches these **byte-for-byte** and refuses anything else on its own
  page ("Invalid OAuth2 redirect_uri"), so the failure never reaches this stack's
  logs — which is why the value must not vary. It is built on
  `DISCORD_CALLBACK_ORIGIN`, which follows `PUBLIC_HOSTNAME`; a deployment that
  knows its public name therefore has exactly one URI per callback to register.
  * Deriving it from the live request was the earlier default and is now only the
    fallback for a local checkout with no public name. It emitted more than one
    value per deployment: a browser reaches `/api` through nginx (`Host`: the
    public name) or through the Next rewrite proxy (`Host: backend:8000`, since a
    rewrite target replaces the `Host` header), and only the first is an origin
    Discord could send anyone back to.
  * `DISCORD_OAUTH_REDIRECT_URI` / `DISCORD_GUILD_REDIRECT_URI` still pin a fully
    custom URL and win over everything.
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

## Drift detection and reconciliation

Two layers, deliberately:

- **Live gateway events** (`mylo/bot/cogs/drift.py`) — `on_guild_remove` (the bot
  was kicked or the server deleted) and `on_guild_channel_delete` (a channel
  Mylo may post to vanished), using the `guilds` intent only. `on_member_remove`
  is deliberately **not** used: it needs a privileged intent.
- **A nightly sweep** (`apps.integrations.reconcile_discord`, Celery Beat
  `DISCORD_RECONCILE_HOUR`, or `manage.py reconcile_discord`) marks absent guilds
  `KICKED` and refreshes or revokes lapsing OAuth tokens. It skips the guild
  sweep on a transient API failure rather than mass-marking links kicked.

## Verification status

The `apps/integrations` regression suite plus the `mylo` bot tests cover the
model, service, OAuth-flow, activation, guild-binding, authorization-invariant,
error-sink, and import-graph logic with Discord HTTP mocked. **Live OAuth and
interaction round-trips need a real Discord app and a test guild and are not
exercised in CI** — run the manual smoke checklist below against a real app
before enabling for users.

## Manual smoke checklist (needs a live Discord app + test guild)

**Path A** — link → probe DM lands → `dm_ok=True`; DMs off → `50007` →
`dm_ok=False`, state stays `ACTIVE`, portal shows remediation; tampered/replayed
`state` → 400, no row; snowflake already bound → 409; unlink → tokens revoked →
rows deleted → clean re-link.

**Path B** — valid `/activate code:` → ephemeral confirm, identity bound; reply
ephemeral in **all** branches; no code → ephemeral usage hint; expired code →
rejected, **not** consumed; reused code → rejected; 6 bad attempts → lockout,
survives a bot restart;
code for user A redeemed by a Discord account bound to user B → rejected, not
consumed; plaintext code in zero logs / zero DB columns. **Any-server linking** —
a valid code redeemed in a *non-hub* server Mylo is in, in an ordinary channel →
linked, no hub membership needed; the same command in the hub outside
`ACTIVATION_CHANNEL` → ephemeral pointer, no lookup; in a DM → ephemeral "run it in
a server", no lookup.

**Path C** — install → `PENDING_SETUP`, `verified_via_code_grant=True`, nudge
posted; forged `guild_id` on the redirect → ignored. Manager clicks **Activate Lab**
→ 10-digit code (non-manager → 403, unknown lab → 404). `/activate-lab code:<code>`
in the server → guild bound `ACTIVE` (the pending install's row flips); no linked
identity **and no billing add-on** required — the bot is already present and a manager
issued the code. Reused/expired code → rejected; bad code → rejected + counts to
lockout; 6 bad attempts → lockout; a server that already holds another lab or a department gains a second
binding, and the same lab redeemed in a second server gains one there (no conflict); plaintext code in zero logs / zero DB
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
