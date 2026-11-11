# Discord Bot Standard (discord.py)

Use this skill whenever work touches a Discord bot: creating the application,
handling authentication, designing slash commands, responding to interactions,
building buttons/selects/modals, scheduling background jobs, handling errors, or
deploying the gateway process.

**Library:** `discord.py` **2.7.1** (the Rapptz library). Not Pycord, not
disnake, not nextcord — their APIs look similar and their docs will actively
mislead you. If a snippet uses `@bot.slash_command`, `ApplicationContext`, or
`ctx.respond`, it is Pycord and it is **wrong here**.

**Minimum Python:** 3.8+. This repo targets 3.13.

Reference implementations live in [`discord-bot/`](./discord-bot/). They are
verified to import against discord.py 2.7.1. Copy from them rather than writing
interaction plumbing from memory.

| I need to… | Read |
| --- | --- |
| Boot the bot, load cogs, sync commands | [`discord-bot/bot.py`](./discord-bot/bot.py) |
| Read config/secrets safely | [`discord-bot/config.py`](./discord-bot/config.py) |
| Add a new feature area | [`discord-bot/cog_template.py`](./discord-bot/cog_template.py) |
| Define slash commands, options, autocomplete, groups | [`discord-bot/slash_commands.py`](./discord-bot/slash_commands.py) |
| Respond correctly (defer, followup, ephemeral, long jobs) | [`discord-bot/responses.py`](./discord-bot/responses.py) |
| Buttons, selects, modals, persistent views, Components V2 | [`discord-bot/components.py`](./discord-bot/components.py) |
| Handle errors without leaking tracebacks | [`discord-bot/errors.py`](./discord-bot/errors.py) |
| Run scheduled/background work | [`discord-bot/tasks_loops.py`](./discord-bot/tasks_loops.py) |

---

## 1. The Non-Negotiables

These cause the overwhelming majority of Discord bot bugs. Internalize them
before writing any code.

1. **Answer every interaction within 3 seconds.** Discord gives you a 3-second
   window to acknowledge. Miss it and the user sees a permanent red *"The
   application did not respond"* — the interaction is dead and unrecoverable.
   If the work might take longer, `await interaction.response.defer()` **first**,
   then do the work, then use `interaction.followup.send(...)`.
2. **Respond exactly once, then follow up.** `interaction.response.*` may be
   called once. Every message after that goes through `interaction.followup`.
   Calling it twice raises `InteractionResponded`.
3. **The interaction token lives 15 minutes.** After the initial response, you
   have 15 minutes to send followups or edit the original response. Work that
   may exceed 15 minutes must not try to report back through the interaction —
   acknowledge, hand off to a background job, and deliver via a channel message,
   DM, or webhook.
4. **Never block the event loop.** One blocking call (`requests.get`,
   `time.sleep`, a sync DB driver, a CPU-heavy loop) freezes the entire bot:
   heartbeats stop, the gateway drops you, every user's command fails. Use
   `await`, `asyncio.to_thread(...)`, or a task queue.
5. **Sync the command tree deliberately, never on every boot.** See §5.
6. **The token is a credential.** It goes in the environment, never in code,
   never in a commit, never in a log line. A leaked token is a full account
   takeover of the bot; rotate it immediately in the Developer Portal.

---

## 2. What a Discord Bot Can Actually Do

A capability map, so design conversations start from what is possible rather
than what is familiar.

### Interactions (how users invoke the bot)

| Capability | What it is | discord.py |
| --- | --- | --- |
| **Slash commands** | `/command` with typed, validated, autocompleted arguments. The primary interface. | `@app_commands.command()` |
| **Subcommands & groups** | `/lab add`, `/lab remove`, `/config alerts set`. Max 2 levels of nesting. | `app_commands.Group` |
| **User context menu** | Right-click a user → *Apps* → your action. | `@app_commands.context_menu()` |
| **Message context menu** | Right-click a message → *Apps* → your action. | `@app_commands.context_menu()` |
| **Autocomplete** | Live suggestions as the user types an option. Max 25 results, must return in 3s. | `@option.autocomplete("name")` |
| **Modals** | Popup forms — text inputs, selects, checkboxes, radios. The only way to collect long/structured input. | `discord.ui.Modal` |
| **Buttons** | Up to 25 per message (5 rows × 5). Primary/secondary/success/danger/link/premium. | `discord.ui.Button` |
| **Select menus** | Dropdowns: string, user, role, mentionable, channel. Up to 25 options. | `discord.ui.Select` and friends |
| **Prefix commands** | `!command`. Legacy — requires the privileged Message Content intent. Avoid for new work. | `discord.ext.commands` |

### Output

- **Embeds** — rich cards. Up to 10 per message.
- **Components V2** (`ui.LayoutView`) — containers, sections, text displays,
  thumbnails, media galleries, separators. Full layout control; mutually
  exclusive with `content`/`embeds` on the same message.
- **Ephemeral messages** — visible only to the invoking user. Use for errors,
  confirmations, personal data, anything that would be noise in the channel.
- **Files & attachments** — check `Interaction.filesize_limit` for the caller's
  actual ceiling instead of hardcoding one.
- **Polls** — native Discord polls with vote events.
- **Webhooks** — post into a channel without the bot being online. The right
  tool for "a backend job needs to announce something."
- **DMs** — may fail with `Forbidden` if the user has DMs closed. Always guard.

### Server surface

Threads and forum posts · scheduled events · reactions · pins · invites ·
roles and permission overwrites · nicknames · moderation (kick, ban, timeout,
AutoMod rules) · audit logs · emoji and stickers · voice channels (join, play,
record; DAVE E2EE supported in 2.7) · presence/status · guild onboarding and
guild tags · message forwarding.

### Application-level

- **User-installable apps** — install the app to a *user account* so its
  commands work in any server or DM, not just servers where it was invited.
  Controlled with `@app_commands.allowed_installs()` / `@app_commands.user_install()`
  and `@app_commands.allowed_contexts()`.
- **Monetization / entitlements** — paid SKUs, checked via `Interaction.entitlements`.
- **Activities** — launch an embedded activity from an interaction
  (`InteractionResponse.launch_activity()`).

### Hard limits worth memorizing

| Thing | Limit |
| --- | --- |
| Response window | **3 seconds** |
| Interaction token lifetime | **15 minutes** |
| Global commands per app | 100 top-level |
| Options per command | 25 |
| Choices per option / autocomplete results | 25 |
| Command name | 1–32 chars, lowercase, `^[-_'\p{L}\p{N}]{1,32}$` |
| Command description | 1–100 chars |
| Total command JSON (names + descriptions + values) | 8000 chars |
| Buttons | 5 per row, 5 rows → 25 per message |
| Select options | 25 |
| Modal top-level components | 5 |
| `custom_id` | 100 chars |
| Message content | 2000 chars |
| Embed | title 256 · description 4096 · 25 fields · field name 256 · field value 1024 · footer 2048 · **6000 total** · 10 embeds/message |
| Global REST rate limit | 50 requests/second |
| Invalid requests (401/403/429) | 10,000 per 10 min → **24-hour IP ban** |

---

## 3. Creating the Application (one-time setup)

Do this in the [Discord Developer Portal](https://discord.com/developers/applications).
Nothing here belongs in code.

1. **New Application** → name it. The application is the identity; the bot is a
   facet of it.
2. **Bot** tab → copy the **token**. This is shown once. Put it in `.env` as
   `DISCORD_BOT_TOKEN`. If you ever paste it anywhere else, click **Reset Token**.
3. **Privileged Gateway Intents** — leave all three OFF unless a feature
   genuinely requires them:
   - **Message Content** — needed only to read message text you weren't
     mentioned in. Slash-command bots do not need this. Do not enable it out of
     habit; it is the main thing that blocks bot verification.
   - **Server Members** — needed for member joins/leaves and full member lists.
   - **Presence** — needed for online status. Almost never worth it.

   **The threshold is 10,000 total users, not 100 servers** (verified
   2026-09-17; Discord replaced the old server-count rule). Below it you toggle
   these yourself in the portal. At 10,000+ the app must be verified and each
   privileged intent justified and approved, with **annual re-application** and
   a 90-day grace period if access lapses. Enabling an intent in code that is
   not enabled in the portal makes the bot fail to connect with a
   `PrivilegedIntentsRequired` error — so a feature that needs one ships behind
   a config switch that leaves the intent unrequested until somebody has the
   grant. See
   <https://discord.com/blog/updated-requirements-to-how-apps-access-data-in-servers>.

   Mylo's own use: ambient listening (`docs/plans/ambient-profile/`) needs
   Message Content for server-wide reading, and ships with it **off**. DMs,
   @mentions, message actions and reactions on the bot's own posts are
   delivered without any privileged intent, which is why the feature's first
   stage uses only those.
4. **Installation / OAuth2 → URL Generator** — build the invite link:
   - Scopes: **`bot`** and **`applications.commands`**. Slash commands do not
     appear without `applications.commands`.
   - Permissions: tick only what the bot uses. `Administrator` is a red flag in
     review and a liability in practice.
   - The generated URL looks like
     `https://discord.com/oauth2/authorize?client_id=...&permissions=...&scope=bot+applications.commands`.
     `discord.utils.oauth_url()` can generate this programmatically.

**Bot vs. user OAuth2.** Adding a bot to a server is a callback-less OAuth2
flow — you do not need to build a login page, handle a redirect, or exchange a
code. You only need the full authorization-code flow if you want users to log
into a *website* with Discord (`identify`, `guilds`, `email` scopes) or to link
a Discord account to an existing account in your system. For a bot that lives in
Discord and is driven by slash commands, the invite URL is the entire auth story.

**Permissions are two-layered.** The bot's role permissions in the server (what
it can do) and the command's default permissions (who may invoke it). Set the
second with `@app_commands.default_permissions(...)` — server admins can then
override per-role in **Server Settings → Integrations**. Check the bot's own
effective permissions at runtime with `Interaction.app_permissions` before
attempting a privileged action, so you can fail with a clear message instead of
a raw `Forbidden`.

---

## 4. Project Structure

Keep the bot a self-contained package. One file per feature area; the entrypoint
does nothing but wire things together.

```
bot/
├── __main__.py         # python -m bot  → entrypoint, logging, run
├── client.py           # Bot subclass: setup_hook, extension loading, tree
├── config.py           # env parsing, typed settings, fail-fast validation
├── errors.py           # CommandTree subclass + user-facing error mapping
├── cogs/
│   ├── __init__.py
│   ├── admin.py        # owner-only: sync, reload, health
│   └── <feature>.py    # one cog per feature area
├── ui/
│   ├── views.py        # persistent views, buttons, selects
│   └── modals.py       # modal forms
└── services/           # pure logic — no discord imports, unit-testable
```

Rules:

- **Cogs are the unit of organization.** Every command lives in a cog. A cog is
  a class extending `commands.Cog` and is loaded as an *extension* — a module
  exposing `async def setup(bot)`. This gives hot reload and a per-cog error
  handler for free.
- **`services/` must not import `discord`.** Business logic that takes plain
  arguments and returns plain data is testable without a gateway connection.
  Cogs are the adapter layer: parse the interaction, call the service, render
  the result.
- **`ui/` holds view classes**, not command logic. Views must be constructible
  without a live interaction so persistent views can be registered at startup.

---

## 5. Command Syncing — Read This Before You Debug "My Command Isn't Showing"

Registering a command in code does **not** put it in Discord. The command tree
must be *synced* to Discord's API. This is the single most common source of
confusion.

**The rules:**

- **`tree.sync()` (global)** registers commands for every server. Propagation
  can take up to an hour. Rate limited. **Never call this on every startup.**
- **`tree.sync(guild=discord.Object(id=...))` (guild)** registers to one server
  and is **effectively instant**. This is what you use while developing.
- Syncing on every `on_ready` is an anti-pattern: `on_ready` fires again on
  every reconnect, so you burn the rate limit and eventually get throttled.

**The strategy:**

- **Development:** in `setup_hook`, if a `DISCORD_DEV_GUILD_ID` is configured,
  `tree.copy_global_to(guild=dev_guild)` then `await tree.sync(guild=dev_guild)`.
  Instant iteration, and no pollution of the global command set.
- **Production:** sync globally **only when the command definitions actually
  change** — from a deliberate action, not from process start. Provide an
  owner-only prefix command (`!sync`) or a deploy step that calls it once.
- Guild-scoped and global commands are separate registries. A command can appear
  twice if you sync globally *and* copy it to a guild. Clear a guild's copies
  with `tree.clear_commands(guild=g)` followed by `await tree.sync(guild=g)`.

See `discord-bot/bot.py` and the `admin` cog pattern in `discord-bot/cog_template.py`.

---

## 6. The Interaction Response Lifecycle

This is the core mental model. Everything else is detail.

```
interaction arrives
        │
        ├── work is fast (< 3s)?
        │      └── await interaction.response.send_message(...)     ← the one response
        │
        └── work is slow (> 3s)?
               ├── await interaction.response.defer(thinking=True)  ← the one response
               │        (shows "Bot is thinking…"; buys you 15 minutes)
               ├── ... do the work ...
               └── await interaction.followup.send(...)             ← as many as you need
```

- `defer(thinking=True)` shows a visible loading state. `defer()` with no args on
  a component interaction acknowledges silently — use it when you intend to
  `edit_original_response` and don't want a "thinking" flicker.
- `defer(ephemeral=True)` — ephemerality is decided at **defer** time, not at
  followup time. You cannot defer publicly and then make the result private.
- `interaction.followup.send(...)` is a webhook send. It returns a `Message` only
  if you pass `wait=True`.
- `interaction.edit_original_response(...)` updates the deferred/first message —
  ideal for progress updates ("Scanning 1/5…").
- Component callbacks (button clicks) get their own fresh interaction with its
  own 3-second window. `interaction.response.edit_message(...)` updates the
  message the component is attached to.
- Autocomplete callbacks respond with `interaction.response.autocomplete(choices)`
  and must be **fast** — they fire on every keystroke. Never hit a slow API from
  one; query a cache or an index.

**Ephemeral by default for anything the channel doesn't need.** Errors,
confirmations, personal results, and admin actions should be `ephemeral=True`.
Public messages are a shared resource; don't spam them.

Concrete implementations of all of the above are in `discord-bot/responses.py`.

---

## 7. Designing Slash Commands

- **Name for the user's intent, not your schema.** `/paper find`, not
  `/query_contentitem`.
- **Let Discord validate.** Type annotations *are* the schema:
  - `str`, `int`, `float`, `bool`
  - `discord.Member`, `discord.User`, `discord.Role`, `discord.abc.GuildChannel`,
    `discord.Attachment`
  - `app_commands.Range[int, 1, 100]` — bounded numbers; Discord enforces the
    bounds in the client, so bad input never reaches you.
  - `Literal["a", "b"]` or `app_commands.Choice[str]` — fixed choice sets.
  - `Optional[...]` / a default value — makes the option optional.
  - `app_commands.Transformer` — custom parsing/validation with a clean error.
  - Every option needs `@app_commands.describe(...)`. The description is the
    only in-client documentation the user gets.
- **Autocomplete for open-ended lookups** (a lab, a paper, a grant). Choices are
  capped at 25 — return the 25 best matches, not an arbitrary 25.
- **Group related commands** with `app_commands.Group`. `/config alerts set` reads
  better than `/set_alert_config`. Two nesting levels maximum.
- **Guard with checks, not `if` statements**:
  `@app_commands.default_permissions(manage_guild=True)` (who sees it),
  `@app_commands.checks.has_permissions(...)` (who may run it),
  `@app_commands.guild_only()`,
  `@app_commands.checks.cooldown(1, 30.0, key=lambda i: i.user.id)` (abuse control).
  Failed checks raise typed errors your handler renders consistently.

See `discord-bot/slash_commands.py`.

---

## 8. Components — Buttons, Selects, Modals

- A `View` holds components and has a **timeout** (180s default). On timeout,
  `on_timeout` fires — disable the children and edit the message so the user
  isn't clicking dead buttons.
- **Persistent views survive restarts.** Requirements: `timeout=None`, every
  child has an explicit `custom_id`, and the view is registered with
  `bot.add_view(MyView())` in `setup_hook`. Without registration, buttons on old
  messages silently fail after a redeploy.
- **`ui.DynamicItem`** encodes state *in* the `custom_id` via a regex template —
  the right tool when a button needs to know which record it belongs to without
  a database lookup or an in-memory registry.
- **Guard interactions.** Anyone can click anyone's button. Use
  `View.interaction_check` to reject users who didn't invoke the command.
- **Modals cannot be opened from a modal**, and cannot be opened after you've
  already responded — `send_modal` *is* the response. A command that opens a
  modal must not defer first.
- **Components V2** (`ui.LayoutView`) gives real layout: `Container`, `Section`
  with an accessory, `TextDisplay`, `Thumbnail`, `MediaGallery`, `Separator`. A
  message using a `LayoutView` cannot also use `content` or `embeds`. Reach for
  it when an embed genuinely can't express the layout; embeds remain simpler.

See `discord-bot/components.py`.

---

## 9. Errors

Users should never see a traceback, and every failure should be logged with
enough context to debug.

- Subclass `app_commands.CommandTree` and override `on_error`. This is the single
  funnel for every app-command failure. Map known error types
  (`CommandOnCooldown`, `MissingPermissions`, `NoPrivateMessage`,
  `TransformerError`) to short, human sentences; log everything else with
  `logging.exception` and show a generic apology.
- Always check `interaction.response.is_done()` before replying from an error
  handler — you don't know whether the command deferred before it failed. The
  `safe_respond` helper in `discord-bot/errors.py` handles this.
- Raise your own `app_commands.AppCommandError` subclasses from service code for
  expected, user-facing failures ("That lab doesn't exist"). Reserve generic
  exceptions for genuine bugs.
- Per-cog handling: `Cog.cog_app_command_error` catches errors from that cog
  before the tree handler.
- **Do not retry 429s yourself.** discord.py's HTTP layer already respects
  `Retry-After` and queues per-bucket. Hand-rolled retry loops are how bots earn
  the 10k-invalid-requests IP ban.

See `discord-bot/errors.py`.

---

## 10. Background Work

- `discord.ext.tasks` for in-process schedules: `@tasks.loop(hours=24)`, or
  `@tasks.loop(time=datetime.time(hour=9, tzinfo=timezone.utc))` for a wall-clock
  schedule. Always pair with `@loop.before_loop` → `await bot.wait_until_ready()`
  so the loop doesn't fire against a half-connected client. Add
  `@loop.error` or the loop dies silently on the first unhandled exception.
- `tasks` is fine for lightweight polling and digests. It is **not** a job
  queue: it doesn't survive restarts, retry, or fan out. Anything that needs
  durability belongs in a real worker; the bot then only *delivers* the result.
- **Delivery from outside the bot process** should use a **webhook** rather than
  waking the bot — a webhook posts to a channel with a plain HTTP call and needs
  no gateway connection.

See `discord-bot/tasks_loops.py`.

---

## 11. Running and Deploying

- **One process, one gateway connection.** Two instances on the same token both
  receive every event and will double-respond. Guarantee a single replica.
- Use `discord.utils.setup_logging()` (or configure the `discord` logger
  yourself). Log at INFO; `discord.http` at DEBUG will print request details —
  useful locally, noisy and sensitive in production.
- Run with `async with bot:` / `await bot.start(token)` rather than `bot.run()`
  when you need to own the event loop (e.g. to start other services). `bot.run()`
  is fine for the simple case and installs signal handlers for clean shutdown.
- Close resources in `Bot.close()` — HTTP sessions, DB pools — and call
  `await super().close()`.
- The bot is a long-lived outbound WebSocket client. It needs **no inbound
  ports** and no public URL. (The alternative — an HTTP Interactions Endpoint —
  requires a public HTTPS endpoint and Ed25519 signature verification, and gives
  up gateway events entirely. Use the gateway unless you have a specific reason
  not to.)
- Restart policy: `restart: unless-stopped` / a supervisor. discord.py reconnects
  through transient network failures on its own; a crash loop means a real bug.
- **Sharding** only past ~2,500 guilds (`commands.AutoShardedBot`). Below that
  it is pure complexity.

---

## 12. Checklist Before Shipping a Command

- [ ] Responds or defers within 3 seconds on the slowest realistic path.
- [ ] Ephemeral unless the channel genuinely benefits from seeing it.
- [ ] Every option has a `describe`; bounded inputs use `Range`/`Choice`.
- [ ] Permission-gated with `default_permissions` / checks, not an `if` in the body.
- [ ] Cooldown on anything that hits an external service.
- [ ] Failure modes produce a sentence, not a traceback.
- [ ] Long output is truncated to Discord's limits (2000 content / 6000 embed)
      or paginated.
- [ ] No blocking I/O in the coroutine.
- [ ] If it uses components: timeout handled, `interaction_check` guards the
      owner, and persistent views are registered in `setup_hook`.
- [ ] Tested in the dev guild via guild sync before a global sync.

---

## 13. Mylo Chat (this repository)

Mylo answers questions in Discord with the same agent the web app uses
(`tools/agent/`). The bot only enqueues a turn and watches it; the turn runs in
the Celery worker. Rules that hold for any change here:

- **One listener.** `mylo/bot/cogs/listen.py` holds the only `on_message`. It
  asks `mylo/chat.py::route` first: a DM, an `@Mylo` (or its role) and a reply
  to Mylo are questions; a reply with the ping off arrives without text and
  gets "I can only read replies that ping me." at most once an hour. A DM that
  answers one of Mylo's ambient questions keeps going to `listening.dialogue`.
  No Message Content intent, no "Hey Mylo" (S-4).
- **The cog decides nothing.** `mylo/bot/cogs/chat.py` delivers; access is the
  Discord gate (`chat`, `chat_guest`, `chat_manage`, `chat_self`,
  `chat_forget`) and then the agent's own gate, both reached through the
  agent's Discord surface (`tools/agent/surfaces/discord.py`). The cog and
  the bridge hold no permission rule and no prompt text.
- **Nothing can ping.** Every send and edit uses `AllowedMentions.none()`;
  `chat_render.neutralise` defuses `<@…>`, `@everyone` and `@here` in model
  output. The only exception is a slow answer (over
  `discord_ping_after_minutes`): a new reply that allows the asker's id and
  nothing else.
- **Activity, never thinking (S-9).** The status line comes from the activity
  view; a status edit is throttled to one per 1.5 seconds.
- **Rendering is pure.** `mylo/bot/chat_render.py` imports neither Django nor
  Discord I/O: splitting under 2,000 characters without breaking a code fence,
  citations as masked links where they stand (embeds suppressed), the list
  of links posted after an answer only when Mylo ends it with `[[links]]`
  (the person asked for links or for things to open), the model line. There
  is no automatic Sources list; every link goes to the item's own page at its
  source, and only an item with no source page falls back to the app
  (`/app/<feed>?item=<id>`, members only).
- **Restarts lose nothing.** Each question has an `AgentDiscordTurn`; on
  `on_ready` and `on_resumed` the cog delivers pending answers once, or says
  "I lost track of this one. Ask again."
- **Replies continue a conversation.** The cog passes the replied-to
  message id (`reply_to_id`) with each question, and reports every message an
  answer was posted as to `finish`, so a reply to any part of an answer joins
  that conversation.
- **Commands.** `/mylo ask`, `/mylo new` (a fresh conversation here),
  `/mylo forget`, `/mylo chat on|off`,
  `/mylo chat here on|off`, `/mylo chat guests …` live in
  `mylo/bot/cogs/mylo_commands.py` (one `/mylo` group, a `chat` subgroup).
  They reach production only after the owner DMs Mylo `!mylo sync global`
  (`mylo/bot/cogs/admin.py`; the `!mylo` prefix is shared with `chat.route`,
  which skips it, so a command is never also answered as a question).
- **Tests** use fakes only: `mylo/tests/test_chat_cog.py` (fake transport) and
  `test_chat_render.py`; the backend side is `tools/agent/tests/test_discord_*`.
  `manage.py smoke_agent_discord` runs the whole path against the real model.

## Sources

- [discord.py documentation](https://discordpy.readthedocs.io/en/latest/) — API reference and changelog (v2.7.1)
- [discord.py — A Primer to Gateway Intents](https://discordpy.readthedocs.io/en/latest/intents.html)
- [Discord Developer Docs — Receiving and Responding to Interactions](https://docs.discord.com/developers/interactions/receiving-and-responding)
- [Discord Developer Docs — Application Commands](https://docs.discord.com/developers/interactions/application-commands)
- [Discord Developer Docs — Component Reference](https://docs.discord.com/developers/components/reference)
- [Discord Developer Docs — Rate Limits](https://docs.discord.com/developers/topics/rate-limits)
- [Discord Developer Docs — OAuth2](https://docs.discord.com/developers/topics/oauth2)
- [Discord Support — What are Privileged Intents?](https://support-dev.discord.com/hc/en-us/articles/6207308062871-What-are-Privileged-Intents)
- [Discord Support — My Bot is Being Rate Limited](https://support-dev.discord.com/hc/en-us/articles/6223003921559-My-Bot-is-Being-Rate-Limited)
