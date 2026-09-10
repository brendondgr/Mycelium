# Mycelium Architecture

**Scope:** how the system is put together and who owns what. For *where* code
lives, read [`repo-map.md`](repo-map.md). For HTTP shapes, read
[`api-contract.md`](api-contract.md). For product direction, read
[`purpose.md`](purpose.md) and [`goals.md`](goals.md).

Mycelium is a full-stack monorepo with **root-level orchestration**: editable
config (`compose.yaml`, `.env.example`, `package.json`, the systemd units) lives
at the repository root, and all implementation and install state lives under
`web/`, separated by service boundary.

## Tech stack

| Layer | Technology | Location |
|---|---|---|
| Public marketing site | Astro 6, Tailwind v4, MDX — no framework JS shipped | `web/landing/` |
| Authenticated app | Next.js 16 App Router, React 19, Tailwind v4, Radix UI, TanStack Query/Table | `web/app/` |
| Shared design tokens | Tailwind v4 theme | `web/packages/config/src/theme.css` |
| Backend API & orchestration | Django 5, Django REST Framework | `web/backend/` |
| Background work | Celery 5 + Beat | `worker` / `beat` services |
| Relational store | PostgreSQL 17 + pgvector | `postgres` service |
| Cache / broker / job state | Redis 8 | `redis` service |
| Embeddings | fastembed / ONNX Runtime (`BAAI/bge-small-en-v1.5`), CPU or CUDA | `apps/scraper/embedding.py` |
| LLM | OpenAI-compatible endpoint (self-hosted vLLM is the reference target) | `apps/core/llm.py` |
| Edge gateway | Nginx, single origin | `web/infra/nginx/` |
| Python deps & commands | `uv` | `web/backend/` |
| Node workspace | npm workspaces | `web/` |

**Declared but unused.** `compose.yaml` runs **Neo4j** and **MinIO**, and
`settings.py` reads their env vars, but no application code touches either — the
graph phase and object-storage phase are not built. `cytoscape` is an unused
`web/app` dependency. Treat all three as reserved, not as working infrastructure.

## Repository layout

```text
mycelium/
├── CLAUDE.md, README.md, package.json, compose.yaml, .env.example   # root orchestration
├── run.py, manual_all.py, manual_mylo.py, scrape_fellowships.py     # host runners
├── mycelium*.service, mylo-daily.{service,timer}, mylo-bot.service  # systemd units
├── mylo/                          # host Discord bot package + daily-run observability
├── utils/                         # per-stage manual runners, vendored grants prototype
├── eval/                          # retrieval evaluation harness (own uv project)
├── docs/                          # direction, reference, skills, changelog
└── web/
    ├── landing/                   # Astro public site
    ├── app/                       # Next.js authenticated app
    ├── packages/config/           # shared theme tokens
    ├── art/, scripts/             # artwork masters + sync/dev-gateway scripts
    ├── backend/                   # Django API + Celery
    │   ├── config/                # settings, urls, celery, asgi/wsgi
    │   └── apps/                  # Django apps (see boundaries below)
    └── infra/nginx/               # gateway config
```

## Service boundaries

**The browser never talks directly to Postgres, Redis, the worker, or the vector
store** — only to the public site and, through the Next.js proxy, the Django API.

| Concern | Owner | Notes |
|---|---|---|
| Public content | `web/landing/` (Astro) | Marketing, pricing, explanation; no private data |
| Authenticated app behavior | `web/app/` (Next.js) | Session-gated UI; calls the API via a same-origin proxy |
| Backend orchestration | `web/backend/` (Django + DRF) | Auth, permissions, business logic, admin, audit, API contracts |
| Background work | Celery worker + Beat | Reminder ticks, outbox drain, project-profile recompute, seeding |
| Scheduled pipeline | Host `mylo-daily.timer` → `manual_all.py` | The nightly research run (see below) |
| Discord gateway | Host `mylo-bot.service` → `python -m mylo.bot` | Slash commands, drift events, run observability |
| Data storage | Postgres / Redis | Durable records, vectors, queue/cache |

Single-origin routing through Nginx at `http://localhost:11050`:

| Path | Service |
|---|---|
| `/` and public pages | Astro landing |
| `/login`, `/signup`, `/app/*`, `/_next/*` | Next.js app |
| `/api/*`, `/admin/*` | Django |

**Why the nightly run is split across host and container.** `manual_all.py` runs
on the host but executes almost every stage *inside* the backend container, where
the database and the PDF renderer are. Exactly one stage is genuinely host-bound:
the Illinois Fellowship Finder scrape (`scrape_fellowships.py`), which drives
Playwright the container does not carry. The grants/conferences collector is pure
HTTP and runs in-container like everything else. A third stage, the weekly dblp
venue-registry refresh (`refresh_dblp_registry`), is also in-container but sits on
its own slower cadence and **must precede** the conference collection, because the
collector's resolve stage joins against that cache for venue identity and ranks.

## Backend app boundaries

| App | Responsibility |
|---|---|
| `core` | Shared infrastructure: health endpoint, the pgvector extension migration, the exactly-one-FK helper (`db.py`), the OpenAI-compatible LLM client (`llm.py`), and transactional email (`mail/`) |
| `accounts` | Identity & organization: users, profiles, departments, labs, memberships, permission roles, academic titles, audit events, derived membership. Owns session auth (CSRF, login/logout/me), the invite-only sign-up gate, lab invitations, the interests contract, and profile/lab intake (`intake/`) |
| `research` | Projects scoped to a user, lab, or department: membership, visibility over the org hierarchy, plan-gated creation and archiving, team collaboration (shares, feed, link ingest, seen ledger, events), and collections |
| `content` | The matching and delivery layer — the largest app. Deduplicated `ContentItem`s, per-target `RelevanceScore`s, the four feeds, clustering and fusion, the daily briefing and PDF report, saves, addressable deadlines, reminders, notifications, unified search, member fit, and the Discord digest producers |
| `billing` | Subscriptions, per-seat billing, add-ons, and tier-based entitlement resolution. `entitlements.py` is the single read path; an expired plan reverts to Free at read time with no cleanup job |
| `integrations` | Discord identity and lab linking: OAuth, activation codes, guild install, the durable outbox, and the single ORM boundary in `services/resolve.py` |
| `adminpanel` | Platform-admin API (staff/superuser only): user and lab rosters, subscription assignment, watch quotas. Every write records an `accounts.AuditEvent`. Mounted at `/api/admin/` |
| `scraper` | Ingestion: OpenAlex / PubMed / Semantic Scholar paper sources with a scan window and cross-source dedup, the open-source grants/conferences collector (`collect/`, pure HTTP, in-container), the Illinois Fellowship Finder scraper + ingest (`fellowships/`, host-side Playwright), the fellowship eligibility rule engine (`eligibility/`), the device-aware embedder, and the external DOI/arXiv/URL resolver |

There is no `graph`, `reports`, or `planner` app. Reporting lives in `content`;
query-planning logic lives in `accounts/intake/agent.py` and `core/llm.py`; the
graph phase has not started.

## Data ownership

- **PostgreSQL + pgvector** — the source of truth for everything: users, labs,
  departments, memberships, permissions, profiles, projects, content items,
  relevance scores, saves, deadlines, reminders, notifications, subscriptions,
  seats, Discord identities, the outbox, and audit logs. Vector columns
  (`Profile.embedding`, `Project.embedding`, `ContentItem.embedding`) carry
  semantic vectors; `ContentItem.search_vector` is a trigger-maintained tsvector
  and there is a pg_trgm title index for fuzzy search.
- **Redis** — Celery broker/result backend plus several named caches (`signup`
  lockouts, the `scan` status flag, query embeddings).
- **Filesystem** — Discord outbox attachments (`DISCORD_OUTBOX_ATTACHMENT_DIR`)
  and the daily-run state file. Object storage is not wired up.

## Configuration & secrets

- Settings load through **django-environ**. `config/settings.py` reads the root
  `.env` **and** `.env-mylo` (the Discord bot's token and channel ids — Django
  needs them too), then falls back to environment variables and safe defaults
  (SQLite when `DATABASE_URL` is unset).
- `.env.example` documents every variable. Real `.env` files are git-ignored.
- `compose.yaml` overrides per-service URLs so containers reach `postgres:5432`
  and `redis:6379` on the Compose network, while host tooling uses the published
  `11450` / `11550` ports.

| Group | Variables |
|---|---|
| Django | `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CORS_ALLOWED_ORIGINS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `PUBLIC_HOSTNAME` |
| Frontend wiring | `NEXT_PUBLIC_API_BASE_URL`, `API_INTERNAL_URL` |
| Data services | `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` |
| LLM | `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_TIMEOUT`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `LLM_REASONING`, `LLM_REASONING_STYLE`, `LLM_THINKING_BUDGET` |
| Embedding | `EMBEDDING_DEVICE` (`auto`/`cuda`/`cpu`), `EMBEDDING_BATCH_SIZE_CPU`, `EMBEDDING_BATCH_SIZE_GPU` |
| Sign-up gate | `SIGNUP_ACCESS_CODE`, `SIGNUP_CODE_MAX_FAILURES`, `SIGNUP_CODE_FAILURE_WINDOW_SECONDS`, `SIGNUP_CODE_LOCKOUT_SECONDS` |
| Discord (`.env-mylo`) | `DISCORD_API_KEY`, `ERROR_CHANNEL`, `ACTIVATION_CHANNEL`, `SUMMARY_CHANNEL` |
| Email | `EMAIL_ENABLED`, `RESEND_API_KEY`, `DEFAULT_FROM_EMAIL`, `EMAIL_REPLY_TO`, `EMAIL_APP_BASE_URL` |
| Run analytics | `RUN_ANALYTICS_JSON_PATH`, `RUN_ANALYTICS_PDF_DIR`, `RUN_ANALYTICS_RETENTION_DAYS` |
| Opportunity collector | `COLLECT_CONTACT` |
| Reserved (unused) | `NEO4J_*`, `S3_*` |

`COLLECT_CONTACT` is the one variable that does **not** go through django-environ:
`apps/scraper/collect/core/http.py` reads it from `os.environ` **at import time**,
because it names the address in the outbound `User-Agent` every public source sees.
Setting it after Django has loaded has no effect, and — like the run-analytics
paths — a bare `KEY=` in an env_file arrives as an empty string and beats the
default, so `.env.example` ships it commented out rather than blank. The
extraction stage adds no variables of its own; it calls the same `LLM_*` client
every other model caller routes through.

`PUBLIC_HOSTNAME` backs every absolute URL Mycelium emits. Leaving it blank once
published `localhost` links into a lab's Discord channel; links that leave the
building now fall back to the public site rather than loopback.

Transactional email (`apps/core/mail/`) is the transport for anything that must
reach an inbox rather than a Discord DM — password resets, lab and department
invitations, verification codes — because those recipients are by definition not
yet linked to Discord. It is wired as a Django `EMAIL_BACKEND` over the Resend
API, so `django.core.mail` and Django's own password-reset machinery route
through it without a second transport to configure; `send_email` sits on top for
templated product mail, rendering a matched HTML and plain-text pair from
`web/backend/templates/email/`. There is no queue behind it: a flow that needs
delivery to survive an outage should copy the durable outbox in
`apps/integrations/services/outbox.py` rather than reinvent it.

`EMAIL_ENABLED` defaults to **off** and unset falls back to Django's console
backend, because real mail is irreversible and a development mistake reaches real
addresses. Two operational cautions: the sending domain must carry SPF, DKIM and
(for Gmail) DMARC or the API accepts a message that is then silently dropped, and
the API key is send-only, so acceptance is visible here while delivery is only
visible in the Resend dashboard. `manage.py send_test_email --to <addr>` exercises
the whole path.

Account security rides that transport. Two mechanisms carry it: a six-digit code
(`apps/accounts/email_verification.py`) proving control of an address, and a
password reset link (`apps/accounts/password_reset.py`) signed by Django's own
`default_token_generator` — keyed on the current password hash, so a link dies
when it is used and `PASSWORD_RESET_TIMEOUT` bounds the rest. Codes are scoped to
a purpose (sign-up, email change, password change) and looked up by it, which is
a security property rather than bookkeeping: no flow can spend another's proof.

**A signed-in session is not authority over the password.** Changing a password
from the Account page needs the current password *and* a code mailed to the
account's address, because the session and the password both live inside a
browser someone can walk away from. That is not a new way in — anyone who can
read the mailbox can already take the account through reset — and the code email
doubles as the alarm when the first two factors have been borrowed. Asking for a
reset, by contrast, changes nothing at all: `request_reset` only mails a link, so
an unauthenticated endpoint can never be used to lock a stranger out by typing
their address.

**Verification is activation.** An account that has not answered a code sent to
its own address may sign in and browse, but cannot create a lab or department,
edit either's profile, or send an invitation — `require_verified_email` in
`apps/accounts/permissions.py` is the single gate. The reason is outward-facing:
Mycelium mails invitations to people who have never heard of it, so an account
whose own inbox has never replied does not get to originate that mail. The gate
sits on those writes rather than on sign-up because registration provisions the
org row inside its own transaction, at an instant when nobody is verified yet.
Email uniqueness is enforced by a partial unique index on `LOWER(auth_user.email)`
as well as by the serializer, because reset now looks an account up by address.

The LLM client supports structured reasoning levels (`none`/`low`/`medium`/
`high`) sent either as `reasoning_effort` (`LLM_REASONING_STYLE=effort`) or as a
`chat_template_kwargs.enable_thinking` toggle, and reads back the server's
separated `reasoning_content`. It lazily imports the `openai` SDK and accepts an
injected transport, so tests run fully offline. The optional `llm-tunnel` Compose
service is an SSH forward to a remote LLM host, run inside the Compose network.

## Ranking, the slate, and what counts as new

The nightly run **ranks the whole corpus** for every target against the profile
that target has that night, and re-establishes each feed from that ranking. Rank is
the fused BM25 + embedding order (`fusion.py`) and nothing else: a language-model
verdict explains an item, it never moves one.

**What a grant or conference ranks *on* did change.** Since the open-collector
migration, an opportunity's embedded text is not its raw source description — it
is a schema-checked, model-written extraction, verified by deterministic code
(bounds, venue identity, prose grounding, topic grounding, no invented specifics)
before it is stored, shown, or embedded. That was the point: raw source text is
not a uniform basis, since one funder writes ten times longer than another and
conference rows carry no CFP text at all. A record whose extraction fails every
bounded attempt is **refused** — it falls back to truncated raw text so it stays
retrievable, shows no AI summary, and records the fact in
`metadata["search_text_source"]` (`extracted` | `raw`), so a degraded run is
queryable and re-runnable rather than invisible. Ordering logic itself is
untouched, and the conference rank badges (CCF / CORE / THCPL) are **display
only** — they never enter relevance, thresholds, or the verdict. The
embedding basis moving is nonetheless a relevance change, and per
`docs/skills/global.md` any claim about its effect is an experiment under
`docs/research/experiments/`, not an assertion here.

Cost is contained by carry-forward rather than by narrowing the scan. A verdict
Mylo has already written is reused (`opportunity_llm.load_prior_llm_verdicts`), so
what re-ranking nightly costs is retrieval. Items that drop out of a ranking are
**retired, not deleted** (`opportunities._retire`): they lose `signals.suggested`
and their slate place but keep the verdict, so an item that dips out and returns
costs no second model call.

Refitting (`refit_*`, `run_refitting`, `manual_mylo.py`) is still a separate
on-demand pass, run at sign-up and after a profile or focus edit. What makes it
different is `reuse_prior=False`: it re-sends every surfaced item to the model,
which is what a profile edit wants and what a nightly run must never do.

Each target keeps a **slate** per category — its top `top_feed.TOP_N` (25) by
relevance, recorded on the score rows as `top_rank` / `entered_top_on` /
`is_new_top`. The slate is the unit of the daily report, and **new means entered
the slate**, not arrived in the corpus. That inverts the test an item has to pass:
it is worth announcing when it is good enough to displace something the reader was
already being shown. It also makes the report answer to the reader — change a
focus, a cluster, or a watch term and the slate re-ranks, so whatever that change
promotes is reported as new, with no separate machinery.

The **daily report** (`briefing.report_scores`) shows the slate, every day, and
flags the entrants. Only entrants Mylo has not already written up go to the model;
the rest keep the write-up they have. When nothing entered, yesterday's body is
carried forward verbatim (`DailyBriefing.Origin.CARRIED`) rather than re-worded to
reach the same conclusions. Both the written briefing and the PDF read through that
one function, so they can never disagree about what the reader is being shown.

Feed reads still accumulate across runs (`views._accumulated_scores`,
`briefing._suggested_scores`), capped by `OPPORTUNITY_FEED_MAX`; the feed's own
week-long "New" pin is a separate, unchanged signal about arrival. Papers are the
exception to accumulation: retrieval is scoped to the latest gather batch, so the
Research Papers page shows only the current day's search.

`resend_user_report --user` and `repost_lab_report --lab` re-render and re-deliver
one target's report on demand (`content/report_resend.py`). They take their own
outbox dedupe key, because the daily key is per-day and made every same-day
re-send a silent no-op.

## Nightly run analytics

The nightly run measures itself. A final, non-fatal `run_analytics_report` stage
reads the rows the run just wrote — coverage, discovery, recommendations, report
delivery — plus the per-day LLM ledger (`core.LLMUsageDaily`, written from
`apps.core.llm.LLMClient.complete`, which is the one seam every LLM caller routes
through). It leaves the metrics at `RUN_ANALYTICS_JSON_PATH` and a PDF in
`RUN_ANALYTICS_PDF_DIR`.

The split exists because the two halves run in different worlds: the stages
execute in the backend container, where the database and the PDF renderer live,
while the Discord summary is posted from the **host**, by the same stdlib-only
runner that already reports a failed stage. The JSON file under the shared
`data/` bind mount is the seam; `mylo/analytics.py` reads it back and formats the
tables and bar charts, and `mylo/reporting.py` posts them with the PDF attached.

Both halves see the same bytes under **different roots** — `/app` inside the
container, the checkout path on the host — so the metrics file records the PDF's
location twice: `pdf_path` (the writer's own absolute path) and `pdf_relpath`
(relative to the shared root). The host resolves the attachment through
`analytics.resolve_pdf`, which re-anchors the relative form on its own checkout;
handing the container path straight to the reporter cost the attachment silently,
because an unreadable file is logged and the summary posts without it.

Both paths must also be left **unset** rather than set-and-blank. `.env.example`
is an env_file for the backend and worker, so a bare `KEY=` arrives as an empty
string and beats the setting's default; the empty path became `Path(".")`, which
put the PDF in the working directory and failed the JSON write outright. The data
paths therefore read through `env_str`, which treats blank as unset.

Measurement is deliberately outside `CONTAINER_STAGES`: a failure there means
users did not get their day, whereas a failure here only costs the summary its
detail. The run still announces itself either way.

## The ranking-stack seams

`apps/content/protocols.py` declares two structural protocols so the ranking
stack can run without a database — which is what lets an offline harness measure
the *production* code instead of a copy of it.

- **`Retrievable`** — a candidate the stack can score: a stringable `id`, a
  `metadata` dict, and an optional `embedding`. `ContentItem` satisfies it
  already; `lexical.py`, `fusion.py`, and `ranking.py` annotate against it. This
  is a typing change only, with no runtime effect.
- **`VectorIndex`** — anything that answers nearest-neighbour queries.
  `retrieval.PgVectorIndex` wraps the existing pgvector query and is what
  production uses; `pipeline._build_pool` takes an optional `index` that defaults
  to it, and that single parameter is the entire integration surface.

The substitution is exact, not approximate: there is **no ANN index** on
`ContentItem.embedding` (no `hnsw`, no `ivfflat`), so every production vector
query is already a sequential scan ordered by cosine distance. An in-memory
index therefore computes the identical ranking. See `docs/evaluation.md`.

## Running locally

| Goal | Command |
|---|---|
| Full stack, single origin | `docker compose up` (or `python run.py`) → `http://localhost:11050` |
| Backend + data services only | `docker compose up backend` |
| Host dev gateway | `npm run dev` |
| Backend management command | `uv run --project web/backend python web/backend/manage.py <cmd>` |
| Backend tests | `npm run test` (or `uv run --directory web/backend python -m pytest`) |
| GPU embedding | `docker compose -f compose.yaml -f compose.gpu.yaml up` |

Without `DATABASE_URL`, Django uses SQLite for quick checks — but pgvector tests
skip there, so anything touching vectors needs the Compose Postgres. Embedding
migrations depend on `core.0001_enable_pgvector`, so a fresh database provisions
the `vector` type before any table that uses it.
