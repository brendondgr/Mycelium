# Self-Host Setup — Implementation Plan

**Status:** planned, nothing built.
**Correlation ID:** `20261111-self-host-setup`

## Objective

Someone who clones the repository gets a working instance — stack, model,
people, Discord bot — from one command and one page, without opening a file in
an editor or reading a reference doc, and is told plainly what works and what
does not.

Three things are set up, and one thing checks them:

1. **The instance and its people**: a department, labs inside it, and people,
   in any combination and quantity, with interests where known.
2. **The language model**: a server the operator runs, or a provider API key.
3. **The Discord bot**: the operator's own application, in their own server.
4. **The checks**: one list that says, for each of the above, pass or fail,
   why, and what to do. Every surface reads it.

## Decisions already made

- **A web page is the main surface, and it may write secrets.** The operator
  types a key, saves, and it takes effect.
- **The terminal stays equal.** Every action on the page is also a command, so
  an agent or a headless server needs no browser.
- **The bot runs inside the Docker stack by default.** The host systemd unit is
  kept as an alternative.
- **People created ahead of time get a claim link**, which the operator sends
  on. The person sets their own password.

## What exists and what does not

| Area | Exists today | Missing |
|---|---|---|
| First run | `make setup` (`ops/setup/bootstrap.py`): profile, `.env` secrets, build, migrate, first admin | Any test of what it wrote; a page |
| Checks | `ops/mycelium status` (always exits 0), `GET /api/health/` (a fixed string), `config validate` (no network), `llm_check`, `llm_probe`, `decision_check`, `embedding_device`, `send_test_email`, `discord_check`, `smoke_reports` | One command that runs them and explains failures |
| People | Lab and department creation in the app, one at a time; `OrgInvite` links; two demo seeders; `provision_from_author` (login plus drafted interests from an ORCID or OpenAlex id, called only by `seed_demo`) | A roster; accounts made ahead of time |
| Model | Eight server kinds, `[llm.routes]`, `llm.allow_cloud`, `llm.port_relay`, a plain-language error classifier in `llmkit/discovery.py` | Guided setup; the classifier on the chat path; detection of a host-only server |
| Discord | One bot identity from env, no hardcoded servers, add-on gate off when billing is off, `/activate`, `/activate-lab`, `/activate-department`, `/setup` | A token-only path; automatic command registration; an invite link outside the OAuth flow; any check that talks to Discord |

## The design

### One engine, three faces

```text
checks + actions (Python, importable)
   ├── terminal:        make setup · make doctor · ops/mycelium setup <step>
   ├── setup console:   a local page on the host, for the operator
   └── Instance page:   inside the app, staff only, no secrets
```

### The setup console runs on the host, not in the app

The console is a small local web server started by `make setup` (and by
`make console` afterwards). It is **not** a route in the Next.js app and not a
service in `compose.yaml`. Three reasons:

- It must exist **before** the stack is built.
- It restarts containers and writes `.env`. A page inside the app could only do
  that if the backend container held the Docker socket, which is root on the
  host for anyone who compromises the app.
- It settles who may reach it. Only someone with a shell on the machine can
  start it, so a group running a shared instance gives ordinary accounts no
  path to the secrets, whatever roles the app grants.

Shape:

- `ops/setup/console/server.py`: standard library only (`http.server`,
  `tomllib`), like `bootstrap.py` and `config_cli.py`, so the prerequisites
  stay Docker and Python 3.
- `ops/setup/console/static/`: one HTML page, plain CSS and JavaScript, no
  build step. It uses the Mycelium tokens from
  `web/packages/config/src/theme.css` (copied at start, not imported at build).
- It calls the same functions the commands call. In-stack work goes through
  `docker compose exec backend … manage.py <command> --json`, the pattern
  `ops/nightly/_runner.py` already uses.

### Who does what

| Who | Surface | Can change |
|---|---|---|
| Operator (shell on the host) | Console, terminal | Secrets, model, bot token, policy in `mycelium.toml`, restarts, roster |
| Instance admin (staff account) | Instance page in the app | Roster, claim links; reads every check |
| Lab or department manager | Existing settings pages | Their own Discord server, their own invites |

### Console security (it handles secrets)

- Binds `127.0.0.1` only. A flag to bind elsewhere is refused in this plan; for
  a remote server the console prints the `ssh -L` line to use.
- A 256-bit one-time token in the printed URL, exchanged for an `HttpOnly`,
  `SameSite=Strict` cookie. Compared in constant time. The session ends when
  the process stops or after an idle timeout.
- Every request: `Host` must be the console's own loopback address (DNS
  rebinding). Every write: `Origin` must match and carry the session (CSRF). No
  CORS headers.
- Secrets are **write-only**. A read returns "set" or "not set", never the
  value. Nothing secret is logged.
- Writes go through one allowlist of known keys (the keys in
  `web/backend/config/instance.py` plus the named `.env` / `.env-mylo`
  variables). The console cannot write an arbitrary file or key.
- `.env` and `.env-mylo` are rewritten atomically, mode `0600`, keeping every
  other line and comment.
- `data/setup/console.log` records which key changed and when, never a value.

## Assumptions

- No product-direction change. `docs/purpose.md` already says any lab can run
  it on its own computers.
- Operator policy stays in `mycelium.toml` and secrets stay in `.env` /
  `.env-mylo`. The console is another writer of those files, not a new store.
  New operator settings are keys in `web/backend/config/instance.py`.
- The console is not a tier capability and reads no entitlement. The Instance
  page is gated by `IsStaffOrSuperuser`, as `apps/adminpanel` is today.
- The nightly run stays on the host `mylo-daily.timer`. This plan only checks
  that it is installed and shows the command that installs it.
- Roster interest drafting from an ORCID or OpenAlex id runs as a Celery task
  per person; typed interests need no model.

## Phases

Each phase ships on its own and leaves the instance working.

### Phase 0 — Clear the traps

Small corrections found while researching. None needs the rest of the plan.

- `PUBLIC_FALLBACK_HOSTNAME` defaults to `mycelium.brendondgr.com`
  (`.env.example`, `config/settings.py`), so a fresh clone writes links to the
  maintainer's site into Discord and `discord_check` can print that domain as
  the redirect URI to register. Default it to blank; the maintainer's instance
  sets it in its own `.env`.
- `.env.example` sets `LLM_MODEL=skynet`. Blank it, and make `llm_check`'s
  "LLM_MODEL is empty" error apply only when a component is routed to `local`.
- The host bot reads `.env` and `.env-mylo` but not `.env.example`, and
  `bootstrap.py` writes no `DATABASE_URL`, so it falls back to SQLite
  (`config/settings.py`). Read from the settings, not yet run. Have
  `bootstrap.py` write `DATABASE_URL`, and have `install-service` refuse when
  it is absent.
- `mylo/config.py` `require_bot` refuses to start without `ERROR_CHANNEL`.
  Make it optional: without it, operational messages go to the log only.
- A blank token under `Restart=always` is a restart loop (inferred, not run).
  Exit cleanly with "no token, staying off".
- Wrong instructions: the footer of `ops/systemd/mylo-bot.service`
  (`scripts/mycelium`, `@Mylo sync global`), the `/opt/mylo-bot/venv` section
  of `docs/discord-integration.md`, the variable names in
  `docs/skills/discord-bot.md`, and the `provision_user` reference in
  `apps/accounts/provisioning.py`.
- Check whether `LLM_REASONING_STYLE=thinking` sends `chat_template_kwargs` to
  a cloud OpenAI endpoint that rejects it. If so, apply the style per server
  kind in `apps/core/llm.py`.

**Validation:** `make test`, `make test-mylo`; `ops/mycelium config validate`
on a fresh `--env-only` setup.

### Phase 1 — The checks, and `make doctor`

- A check returns `id`, `group`, `title`, `status` (`ok`, `warn`, `fail`,
  `off`), a one-sentence `reason`, and a `fix` (a command, or a console panel).
- In-stack checks: `web/backend/apps/core/doctor.py` and `manage.py doctor
  [--json] [--group …]`. Host checks: `ops/setup/checks.py` (standard library).
  `ops/mycelium doctor` runs both and merges; `make doctor` calls it. Exit 1 on
  any `fail`.
- Groups and what they cover:

  | Group | Checks |
  |---|---|
  | Stack | Docker and Compose present; containers up; migrations applied; a real query; Redis answers; pgvector installed |
  | Config | `config validate`; sign-up mode against whether the instance is public |
  | Model | filled in by Phase 3 |
  | Embeddings | model downloaded; one string embeds; dimension matches the index |
  | Email | provider configured; optional send to an address given on the command line |
  | Discord | filled in by Phase 5 |
  | Nightly | timer installed; last run and its result; `tools check` |

- Tools contribute checks through an optional `Tool.checks` reference in
  `tools/_framework/spec.py`, beside the existing load-time `Tool.health`
  (which stays configuration-only). Read `docs/skills/tools.md` first.
- `GET /api/admin/doctor/` (staff only) returns the in-stack half.
- `GET /api/health/` stays a liveness probe. `ops/mycelium status` stops
  listing Neo4j and MinIO as endpoints to watch.

**Validation:** `web/backend/apps/core/test_doctor.py` with each check forced
to each status; `make doctor --json` on a running stack.

### Phase 2 — The console shell

- `ops/setup/envfile.py`: read, set and unset keys in a dotenv file, keeping
  comments and order, atomic, `0600`.
- `ops/setup/console/`: the server, the auth above, and these panels: Overview
  (every check, re-run button), Settings (every key from `config explain`,
  with its source layer and a save that runs `config validate` first), Secrets
  (the write-only fields), Restart (runs `ops/mycelium restart`, streams its
  output).
- `make setup` becomes: prerequisites → profile and generated secrets → build
  → first admin → start the console and print its URL. With `--yes` or no
  terminal it starts no console and ends by running `doctor`.
- `make console` reopens it later.

**Validation:** `web/backend/apps/core/test_setup_console.py` (beside
`test_config_cli.py`): token and cookie, wrong `Host`, wrong `Origin`, a key
outside the allowlist, a secret never returned by a read, file mode and
comments preserved.

### Phase 3 — The model step

- `ops/mycelium setup model` and a console panel, same code.
- **A server I run.** Probe the usual ports (Ollama 11434, LM Studio 1234,
  vLLM 8000, llama.cpp 8080, LiteLLM 4000) from the host and from inside the
  backend container. If only the host answers, set the URL to
  `host.docker.internal` and turn on `llm.port_relay`. List the models the
  server serves and let the operator pick; never accept a name it does not
  list without a warning.
- **An API key.** Pick OpenAI, Anthropic, Gemini, DeepSeek, or another
  OpenAI-compatible address; paste the key (to `.env` under that provider's
  variable); pick from the provider's model list. Writes
  `[llm.providers.<name>]`, `llm.default`, and `llm.allow_cloud = true` only
  after showing the sentence from `docs/skills/configure.md` that prompts will
  leave the machine.
- **Verify.** Model checks for Phase 1: the server answers; the chosen model is
  served; a plain reply; structured output (the sample profile extraction
  `llm_check` already runs); a function call; a stream. Report by feature —
  profile drafting, nightly write-ups, reports, Mylo chat — using the component
  names in `[llm.routes]`.
- One classifier for every failure, on the chat path too: unreachable, timed
  out, key rejected, model not served (with the served list), server is on the
  host's loopback (with the relay fix).
- `llm_check` gains `--json`.

**Validation:** the mock servers in `apps/core/llm_testservers.py` for each
kind and each failure; `test_llmkit.py`; a manual pass against one local
server and one cloud key.

### Phase 4 — Roster and claim links

- `roster.toml` (git-ignored; `roster.example.toml` committed):

  ```toml
  [department]
  name = "Scientific Computing"
  head = "chair@example.edu"

  [[labs]]
  name = "Example Lab"
  pi = "pi@example.edu"

  [[people]]
  name = "Ada Example"
  email = "ada@example.edu"
  lab = "Example Lab"
  role = "member"
  interests = ["graph neural networks"]   # or: orcid = "0000-…"
  ```

  Every table is optional: people with no lab, labs with no department, a
  department alone.
- `web/backend/apps/accounts/roster.py`: `plan(data)` and `apply(data,
  actor)`. Keyed on email for people and name for labs; creates what is
  missing, reports what is unchanged, never deletes. Uses
  `create_lab_workspace` / `create_department_workspace`
  (`apps/billing/services.py`), `validate_interests`, and `import_author` for
  an ORCID or OpenAlex id. Every creation is an audit event.
- `manage.py roster apply|plan|export <file> [--json]`; `ops/mycelium roster …`
  wraps it; the console gets a Roster panel (upload or edit, preview, apply).
- **Claim links.** Model `AccountClaim` (random token, single use, 30-day
  default expiry, regenerable). The password-reset link cannot be reused: its
  lifetime is one hour (`PASSWORD_RESET_TIMEOUT`). A pre-made account has an
  unusable password until claimed. Route `/claim/<token>` in the app, with its
  own nginx `location` block like `/join` and `/reset-password`;
  `POST /api/auth/claim/` in both slash forms.
- A claim does not mark the email verified. Where `signup.verify_email` is on,
  the person verifies with the existing six-digit code after claiming.
- A person with interests lands in the app; one without goes through
  onboarding on first sign-in, as today.
- With `billing.mode = "subscriptions"`, the roster stands orgs up with their
  plan inactive, as the app does. It never activates a plan.

**Validation:** `apps/accounts/tests/test_roster.py` (apply twice changes
nothing; partial files; bad rows refused one by one) and `test_claim.py`
(expired, used, regenerated, wrong token), against the Compose Postgres.

### Phase 5 — Discord, token-only

Start with a trial against a real Discord application, because two things are
unconfirmed: that a bot invited by a plain link (no OAuth code grant) can be
activated with `/activate-lab` and then run `/setup`, and what happens to that
link when "Requires OAuth2 Code Grant" is on. The code suggests it works
(`_ensure_guild` in `services/resolve.py` creates the server record). If it
does not, the fallback is to keep the OAuth install and have the console walk
through the redirect URIs.

- **The bot as a service.** `mylo` in `compose.yaml`, same image and mounts as
  `backend`, running `python -m mylo.bot`. It idles when there is no token or
  when the runner is not `compose`, the way `decision-relay` idles.
  `[discord] runner = "compose" | "systemd" | "off"` in `instance.py`;
  `install-service` installs the bot unit only for `systemd`.
- **One secret.** The bot token, in `.env-mylo` as today. Setup validates it
  against Discord (`/users/@me`, `/applications/@me`), which also yields the
  application id, so the operator copies nothing else.
- **The invite link.** Built from the application id with the permissions the
  features in use need (including forum, thread and file permissions when
  announcements or PDF reports are on), not the fixed `19456`.
- **Commands register themselves.** On start the bot compares a hash of its
  command tree with the last one registered and syncs when it differs.
  `!mylo sync` stays for manual use.
- **A heartbeat.** The bot writes a row (servers, registered commands, gateway
  latency, time). The backend reading it proves the bot is up and that both
  use the same database.
- **Linking by code is the default.** `/activate`, `/activate-lab` and
  `/activate-department` need no client secret, redirect URI or public
  address. The "Connect Discord" button and the OAuth install show only when
  `DISCORD_CLIENT_ID` is set; they become the optional path.
- **Discord checks for Phase 1:** token valid; bot process alive (heartbeat);
  in at least one server; commands registered; can post in the chosen channel
  (a real test message); each lab and department binding active; links Mylo
  writes point at this instance.
- `ops/mycelium setup discord` and a console panel walk the six steps in
  order — create the application, paste the token, invite, wait for the bot to
  appear, test message, link the first account — each step turning green from
  its check.
- Reconcile the two contradictory statements about whether a code is needed
  after an OAuth install (`labs-section.tsx`, `oauth.py`).

**Validation:** `make test-mylo`; `apps/integrations` tests with Discord's API
mocked for each check; the manual smoke list in `docs/discord-integration.md`
run once on a new application and a new server.

### Phase 6 — Guides and pictures

- Step content lives once, as data: `ops/setup/console/guides/<name>.toml`
  (title, steps, each with text, an optional image and the check that proves
  it). The console renders it; `ops/setup/console/render_docs.py` writes
  `docs/setup/<name>.md` from the same files, so the page and the docs cannot
  drift.
- Guides: first run, the model, people, Discord, running it for a group on a
  shared server.
- Images in `docs/assets/setup/`. Text names the exact button; a screenshot
  illustrates and is never the only instruction, because Discord's portal
  changes. The Developer Portal screenshots have to be captured by the
  maintainer, signed in.
- README Quickstart rewritten around the console. `docs/configuration.md`
  gains the model and Discord sections it lacks. `docs/discord-integration.md`
  keeps the reference and loses the setup walk-through.

**Validation:** `render_docs.py --check` fails on drift; links checked.

### Phase 7 — The Instance page in the app

- `/app/instance`, staff only: the checks (read-only, from
  `GET /api/admin/doctor/`), the roster (preview and apply through
  `apps/accounts/roster.py`), claim links (create, copy, regenerate).
- No secrets and no restart. Each failing check that needs the host shows the
  command to run there.
- `admin-section.tsx` links to it. States: loading, all passing, some failing,
  permission denied, backend unreachable; phone width; keyboard.

**Validation:** `npm test` in `web/app`; `npm run lint`; staff and non-staff
requests against the API.

## Interfaces that change

- Commands: `make doctor`, `make console`, `ops/mycelium doctor`,
  `ops/mycelium setup model|discord`, `ops/mycelium roster plan|apply|export`.
- Management commands: `doctor`, `roster`; `llm_check --json`.
- Routes: `GET /api/admin/doctor/`, `POST /api/auth/claim/`, app routes
  `/claim/<token>` and `/app/instance`, one nginx `location`.
- Config: `[discord] runner`; `PUBLIC_FALLBACK_HOSTNAME` and `LLM_MODEL`
  defaults; `ERROR_CHANNEL` optional.
- Models: `AccountClaim`, the bot heartbeat.
- Compose: a `mylo` service.
- Files: `roster.example.toml`, `docs/setup/`, `docs/assets/setup/`.
- Docs to update as each phase lands: `docs/repo-map.md`,
  `docs/api-contract.md`, `docs/architecture.md`, `docs/configuration.md`,
  `docs/skills/configure.md`, `README.md`.

## Acceptance

On a machine that has never run Mycelium, following only the console:

1. `git clone`, `make setup`, open the printed link.
2. The model step ends with each feature marked working or not, with a reason.
3. A department, a lab and three people are created from the Roster panel, and
   each claim link signs its person in.
4. The Discord step ends with Mylo answering `/mylo health` in the operator's
   server and one account linked with `/activate`.
5. `make doctor` exits 0, and exits 1 with a plain reason when the model
   server is stopped or the bot token is removed.

No file is opened in an editor at any point.

## Exclusions

- Moving the nightly run off the host timer and into the stack.
- Production servers in place of `runserver` and `next dev`, and removing the
  unused Neo4j and MinIO services (the backend currently depends on both to
  start). Worth its own plan.
- Binding the console to anything but loopback, and any multi-user console.
- Roster deletion or sync from a directory service.
- Slack and Teams setup.
- Billing: the roster never activates or changes a plan.

## Open questions

- **Whose password-less accounts count against sign-up policy?** With
  `signup.mode = "closed"`, the roster is the only way in, which is the
  intent. With `domain` mode, should the roster refuse an address outside
  `signup.allowed_domains`, or is the operator's word enough? Proposed: the
  operator's word is enough, and the row is audited.
- **Does the console also install the systemd units?** It would need `sudo`.
  Proposed: it shows the command and re-checks.
