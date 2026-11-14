# Configuring your instance

Everything the person running a Mycelium decides lives in **`mycelium.toml`** at
the repository root: who may sign up, whether email is sent, whether billing
exists, how much each person and lab may track, which optional features run,
and how much the nightly run may spend. Nothing here requires editing code.

`make setup` writes the file for you. Afterwards, change it with the CLI, or
edit it by hand — it is commented key by key:

```bash
ops/mycelium config show                    # every value and where it came from
ops/mycelium config set limits.clusters 6   # change a value (validated first)
ops/mycelium config validate                # check the combination works
make restart                                # the backend reads it at start
```

Your own agent can do all of this for you: [`skills/configure.md`](skills/configure.md)
tells it how to ask you a few questions, recommend a setup, and apply what you
agree to. Every command takes `--json`.

## Profiles

A profile is a starting point; any key you set overrides it.

| Profile | For | Billing | Limits | Sign-up | Verify email |
|---|---|---|---|---|---|
| `personal` | just you | off | none | closed — the admin creates accounts | no |
| **`lab`** (default) | one lab | off | none | invite | no |
| `department` | several labs | off | none (suggested numbers in comments) | invite | no |
| `institution` | a whole school | subscriptions | per tier | shared code | yes, through Resend |

Choose one at setup (`make setup PROFILE=personal`), or later:

```bash
ops/mycelium config profiles
ops/mycelium config set instance.profile department
ops/mycelium config recommend --people 120 --email resend   # a suggestion with reasons
```

## How values are resolved

Four layers, each overriding the one before:

1. built-in defaults,
2. the profile,
3. `mycelium.toml`,
4. environment variables — `.env` or the shell. Each key keeps an environment
   name (`config explain <key>` shows it), so a value set there wins over the
   file. `config show` marks those `env:NAME`.

An invalid file — an unknown key, a word where a number belongs — stops the
backend at start with the key that is wrong. `config validate` catches the same
mistakes, plus combinations that cannot work.

**Secrets are never in the file.** They stay in `.env` (mode 0600, written by
`make setup`): `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`,
`SIGNUP_ACCESS_CODE`, `DISCORD_TOKEN_ENC_KEY`, `RESEND_API_KEY`,
`EMAIL_HOST_PASSWORD`, `LLM_API_KEY`. `make status` warns, and `make doctor`
fails, if `.env` or `.env-mylo` can be read by other accounts.

## The sections

**`[billing]`** — `mode = "off"` (default) means there are no plans, tiers or
seats: every feature is available, labs and departments work as soon as they
exist, and limits come from `[limits]`. `"subscriptions"` turns the plan system
back on — personal tiers, per-seat lab and department plans, and the per-tier
numbers in `[limits.tiers.*]`. `enforce_features` additionally lets a tier
withhold features.

**`[limits]`** — each is `"unlimited"` or a number, and a number turns on that
one limit: `clusters`, `topics_per_cluster`, `watch_topics`,
`personal_projects`, `lab_projects`, `department_projects`, `lab_members`,
`lab_leads`. Staff can override a limit for one object without touching the
file: a person's watch limit and a lab's project and member limits on the admin
page, a department's project limit in Django admin (`/admin/`, the
department's `project_limit`). An override wins over the file.

**`[signup]`** — `mode` is one of `closed`, `invite`, `code` (the shared
`SIGNUP_ACCESS_CODE`), `domain` (any address at `allowed_domains`) or `open`.
An invite works in every mode but `closed`. `verify_email` makes a new account
answer a mailed code before it can create a lab or invite anyone; with it off,
accounts are active at once. `domain` always verifies, because that is how a
domain is proved.

**`[email]`** — `provider` is `none` (mail is printed to the backend log),
`resend`, or `smtp` (with `smtp_host`, `smtp_port`, `smtp_user`, `smtp_tls`).
`ops/mycelium config validate` tells you which `.env` secret is missing.

**`[features]`** — optional features, all off: Mylo listening in channels
(`ambient` and its parts), collaborator search, project alerts, Discord
announcements, high-signal messages, reranking, Slack, Teams.

**`[demo]`** — the public demo at `/demo`: a fictional department, lab and
people (`web/backend/apps/demo/world.yaml`) ranked every night against the real
corpus, shown in the real app, read-only, with no account. Build it first with
`manage.py demo build`; `enabled` then serves it (off: `/demo` and `/api/demo/`
answer 404 and the front page hides its demo links; the data is kept, and the
nightly run leaves the world out, so an off demo costs no model calls).
`manage.py demo refresh` runs the nightly's work for the demo world alone, now;
`manage.py demo status` shows what each of its people, the lab and its projects
holds, when it was last ranked and its latest report. `manage.py demo seed`
rebuilds the world's saves, lab reminders, a teammate's shared paper and Mylo's
open question from its current feed (`apps/demo/seed.py`); `build` and
`refresh` run it, and so does the nightly, after the prune.
`questions_per_visitor` (10), `questions_per_ip_per_day` (20) and
`questions_per_day` (500, every visitor together — it bounds the model bill; `0`
keeps the demo up with Mylo off) budget Mylo; `question_max_chars` caps one
question.

**`[llm]`** — the language model. `enabled = false` runs the instance without
one on purpose: write-ups, profile drafts and Mylo's answers use their
deterministic drafts, and neither `make doctor` nor the nightly run reports the
missing model as an outage (with it `true` and no model answering, the nightly
run skips rather than fill the feeds with drafts). `make setup` sets it when you
answer "none for now". The endpoint itself (`LLM_BASE_URL`, `LLM_MODEL`,
`LLM_API_KEY`) is in `.env`; further servers are `[llm.providers.<name>]`
sections, chosen per component in `[llm.routes]`
([`skills/configure.md`](skills/configure.md)).

**`[nightly]`** — cost controls. `model_calls` caps the language-model calls one
nightly run may make (`"unlimited"` by default — set it if your model bills per
call); the rest bound parallelism and per-night batch sizes.

**`[tools]` and `[tools.<name>]`** — `strict` and `disabled` for every tool,
then one section per installed tool with `enabled` and the keys its `tool.py`
declares (`make config ARGS="explain tools.<name>"`; see
[`tools/README.md`](../tools/README.md)). A tool's API keys are secrets and live
in `.env` only. For example the full-text tool's publisher keys —
`ELSEVIER_API_KEY`, `ELSEVIER_INST_TOKEN`, `SPRINGER_API_KEY`,
`WILEY_TDM_TOKEN`, `CORE_API_KEY` — are one set for the whole instance; without
them only those publishers' APIs are off, and
`manage.py fulltext_sources --check` says whether a key is rejected or valid
but not entitled from this network.

## Common changes

```bash
# Let anyone at your university sign up (needs email)
ops/mycelium config set email.provider resend signup.mode domain signup.allowed_domains fsu.edu

# A private instance on your own network: anyone who can reach it may join
ops/mycelium config set signup.mode open

# Put a ceiling back on clusters and watch topics
ops/mycelium config set limits.clusters 6 limits.watch_topics 20

# Sell seats: today's tiered plans
ops/mycelium config set billing.mode subscriptions

# Show anyone a working demo lab (build it once, then switch it on)
docker compose exec backend uv run --no-sync --project web/backend python web/backend/manage.py demo build
ops/mycelium config set demo.enabled true
```

## The stack: production and development

`make setup` and `make up` run the production stack: gunicorn for Django,
`next build && next start` for the app, and the public site as static files
nginx serves itself. `make dev` runs the hot-reload stack instead
(`compose.dev.yaml`: `runserver` with DEBUG on, `next dev`, `astro dev`, each
also on `127.0.0.1` at `11350`, `11250` and `11150`). `make restart` keeps
whichever mode last ran. Django refuses to start with DEBUG on while
`PUBLIC_HOSTNAME` is set, so development mode is for a machine that is not
serving anyone.

Only nginx listens beyond the containers, on `BIND_ADDR:NGINX_PORT`
(`127.0.0.1:11050` by default). Postgres and the two Redis instances are on
`127.0.0.1` only (`11450`, `11550`, `11551`), for the Mylo bot on the host, and
each needs its generated password. Docker's published ports go around ufw and
firewalld, so the loopback binding is the real protection: to let other
machines in, put a TLS front end in front of nginx (below). Setting
`BIND_ADDR=0.0.0.0` serves plain HTTP to your whole network; do that only on a
network you trust, and name the address people will type in `.env` so Django
accepts it: `DJANGO_ALLOWED_HOSTS=192.168.1.20` and
`DJANGO_CSRF_TRUSTED_ORIGINS=http://192.168.1.20:11050`.

The app containers run as the checkout's owner (`UID` and `GID` in `.env`) and
see the repository read-only; they write only `data/` and
web/backend/media/. Container logs are capped at 5 × 10 MB per service.

## Serving it to others: a TLS front end

Set `PUBLIC_HOSTNAME` in `.env` to the name people will use (no scheme), then
`make restart`. Django then trusts that origin alone, sets secure cookies and
HSTS, and builds every emailed and Discord link from it. TLS ends in front of
nginx, which stays on loopback. Any of these works:

**Caddy** (gets and renews the certificate itself). `/etc/caddy/Caddyfile`:

```
mycelium.lab.example.edu {
    reverse_proxy 127.0.0.1:11050
}
```

**nginx with certbot** on the host:

```nginx
server {
    listen 443 ssl;
    server_name mycelium.lab.example.edu;
    ssl_certificate     /etc/letsencrypt/live/mycelium.lab.example.edu/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mycelium.lab.example.edu/privkey.pem;
    client_max_body_size 26m;
    location / {
        proxy_pass http://127.0.0.1:11050;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 300s;
    }
}
server { listen 80; server_name mycelium.lab.example.edu; return 301 https://$host$request_uri; }
```

(`sudo certbot --nginx -d mycelium.lab.example.edu` writes the certificate
lines for you.)

**A Cloudflare tunnel**, with no open port at all:

```bash
cloudflared tunnel create mycelium
cloudflared tunnel route dns mycelium mycelium.lab.example.edu
cloudflared tunnel run --url http://127.0.0.1:11050 mycelium
```

The stack's nginx believes `X-Forwarded-For` and `X-Forwarded-Proto` only from
loopback and Docker bridge addresses, so a front end on the same machine is
trusted and a client cannot claim another address or HTTPS. Then
`make doctor` runs Django's `check --deploy` for the public name.

## Checking an instance

`make status` shows the containers, the endpoints through nginx, the Discord
bot, and the steps that need an administrator (the systemd timer for the daily
collection, the bot) until they are done. Setup never runs `sudo`; it prints
those commands instead.

`make doctor` checks the whole instance and exits 1 on any problem, with the
reason and the fix: the stack is up and the API answers, migrations are
applied, the model answers (`llm_check`) or is off on purpose, the embedding
model is downloaded, the corpus is not empty, `.env` and `.env-mylo` are 0600,
no internal port is published beyond loopback, and, with `PUBLIC_HOSTNAME`
set, `manage.py check --deploy` passes.

The first collection: `make nightly` runs the whole nightly pipeline now. Every
stage runs inside the backend container, so the host needs only Docker and
Python 3; `uv` is needed only for the Illinois fellowship scrape, which drives a
browser on the host and is skipped (with a note) without it.

## Backups

```bash
make backup                                   # → data/backups/mycelium-<stamp>.tar.gz (0600)
make restore FILE=data/backups/mycelium-20261112-030000.tar.gz
```

A backup holds a `pg_dump -Fc` of the database, the files people uploaded
(`data/files/`), lab logos (web/backend/media/) and `mycelium.toml`. It does
not hold `.env`: keep a copy of that separately and somewhere safe, because
`DJANGO_SECRET_KEY` and `DISCORD_TOKEN_ENC_KEY` are needed to read what the
database stores (sessions, encrypted Discord tokens). The corpus is not worth
backing up file by file: it is rebuilt by collecting again. `make restore`
stops the app services, replaces the database and the files, keeps the
previous `mycelium.toml` as `mycelium.toml.before-restore`, and starts the
stack again.

Retention is yours to set. A reasonable default is a nightly backup from cron
that keeps two weeks locally and copies each one off the machine:

```bash
# crontab -e
30 3 * * * cd /path/to/mycelium && make backup >/dev/null && find data/backups -name 'mycelium-*.tar.gz' -mtime +14 -delete
```

Test a restore now and then into a scratch checkout; a backup nobody has
restored is a hope, not a backup.

## If you ran an earlier version

Before 2026-11-12 the stack published every service on all interfaces, with
Postgres on the fixed password `mycelium`, Redis without one, and development
servers with DEBUG on. After pulling:

1. Hand back files the old root-run containers left (`make up` prints the exact
   command when it finds any): `sudo chown -R $(id -u):$(id -g) data
   web/backend/media web/app/.next web/app/public web/landing/public/images`.
2. Give the database a real password: `python3 ops/mycelium rotate-db-password`
   (it also writes `REDIS_PASSWORD` and the host URLs into `.env`), then
   `make setup` adds any other missing secret, then `make restart`.
3. Nothing but nginx is published now, and only on `127.0.0.1`; check with
   `make doctor`. If the old ports were reachable from the network, assume the
   database was readable and act on that.
4. Recreate the nginx container (`make restart` does) so its old access logs,
   which recorded full URLs, are gone.
5. Before 2026-11-12, passwords and reset tokens could appear in URLs and so in
   logs. Consider asking users to reset their passwords.
6. Delete any seeded demo accounts (`seed_demo`) from a live database.
7. `ADMIN_USER_PASS` no longer needs to sit in `.env`: `make admin NAME=<you>`
   uses it once and removes it, or prompts for a new password.
