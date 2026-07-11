# Plan — Mylo Daily Briefing, Host Daily Run, & Discord Error Bot

**Status:** DRAFT for review (do not implement yet)
**Author:** session 2026-07-11
**Correlation ID base:** `20260711-mylo-briefing-discord`

## 1. Objective

Turn the daily research run into an observable, host-driven pipeline that
produces a written **"Mylo Report"** briefing, and give Mylo a persistent
Discord presence that reports errors and run status to a dedicated channel.

Three woven outcomes:

1. **Daily run uses `manual_all.py`** (scrape → search → match → refit →
   **+ new: synthesize briefing**), triggered by a **host systemd timer**
   instead of the in-container Celery Beat schedules.
2. **Mylo Discord bot** — a persistent `discord.py` service that posts run
   errors and status to `ERROR_CHANNEL`, so unattended failures (Pivot re-login
   needed, LLM down, a stage crashed) are visible without watching logs.
3. **"Mylo Report" briefing UI** — the three-zone home surface: a 2–3 paragraph
   LLM briefing (left), numeric per-category summaries (top-right), and a
   top-items showcase (bottom-right), gated on `WatchPreference.categories`.

## 2. Current State (verified this session)

- **No daily "search" service exists.** Systemd units are only
  [`mycelium.service`](../../mycelium.service) (stack up) and
  [`mycelium-update.service`](../../mycelium-update.service) (image pull). The
  daily run is **Celery Beat inside the container**:
  `web/backend/config/settings.py:174` `CELERY_BEAT_SCHEDULE` →
  `run_daily_suggestions` (6am, `CELERY_DAILY_SUGGESTIONS_HOUR`),
  `run_daily_opportunities` (1am, `CELERY_DAILY_OPPORTUNITIES_HOUR`), and
  `recompute_project_profiles` (3am). The `beat` service in `compose.yaml:155`.
- **`manual_all.py`** already chains scrape (host Pivot) → `run_daily_suggestions`
  → `run_daily_opportunities` → `run_refitting`. Its scrape stage needs host
  `uv` + Playwright + a saved Pivot session; **non-interactive runs skip login
  and silently match the existing corpus** — the core observability gap.
- **`GET /api/daily-report/`** (`apps/content/views.py`) is papers-only:
  `suggestions` + a deterministic `summary`. Grants/conferences/fellowships have
  their own `RelevanceScore` rows and pages. LLM seams already exist with
  deterministic fallback: `suggest.py`, `opportunity_llm.py`. Reachability check:
  `apps/accounts/management/commands/llm_check.py`.
- **Category toggle already exists:** `WatchPreference.categories`
  (`apps/accounts/models.py:317`) — JSON list `["papers","grants",...]`.
- **Mylo creds staged:** `.env-mylo` has `DISCORD_API_KEY` + `ERROR_CHANNEL`
  (`.env-mylo.example` mirrors names). No bot code exists yet.
- **Discord standard** is `discord.py` 2.7.1 (`docs/skills/discord-bot.md` +
  reference impls in `docs/skills/discord-bot/`).
- Frontend section keys/routes: `web/app/src/lib/portal/routes.ts` has
  `daily` → `/app/daily`, `papers` → `/app/research-papers`; the Daily section is
  `web/app/src/components/portal/sections/daily-reports-section.tsx`; Overview
  right-rail is `daily-digest-panel.tsx`.

## 3. Decisions (confirmed with user)

- **Scope:** all three pieces, woven into one sequenced plan.
- **Bot model:** persistent `discord.py` gateway service (own systemd unit).
- **Trigger:** host systemd `.service` + `.timer` runs `manual_all.py` daily;
  **retire the two in-container daily Beat schedules** (`run_daily_suggestions`,
  `run_daily_opportunities`). Keep `recompute_project_profiles` on Beat.

## 4. Assumptions & Open Questions

- **A1 — Env var name.** The Discord skill recommends `DISCORD_BOT_TOKEN`, but
  `.env-mylo` already ships `DISCORD_API_KEY` with a real value. Plan **keeps
  `DISCORD_API_KEY`** to avoid breaking your setup; the bot config module reads
  it. (Flag if you'd rather rename to the skill's convention.)
- **A2 — Error delivery must survive a down bot.** Errors are high-value and the
  daily run is a separate host process. Plan delivers errors via an
  **authenticated REST POST to `ERROR_CHANNEL`** (bot token, no gateway needed) —
  the skill's "out-of-process announcement uses a webhook/REST, not the gateway"
  guidance (§10). The **persistent bot** is a parallel concern: it owns the
  gateway presence, slash commands (`/mylo health`, `/mylo lastrun`), and future
  two-way actions (ack a re-login request, trigger a re-scrape). This keeps
  "must-deliver error reporting" decoupled from "bot process is up."
- **A3 — Bot deployment shape.** Plan runs the bot as a **host systemd service**
  (`mylo-bot.service`), matching your "service file that starts Mylo" ask and the
  existing host-systemd pattern. *Alternative:* a `mylo-bot` service in
  `compose.yaml` (most portable via `docker compose up`). **Open: host unit vs.
  compose service?** Plan assumes host unit; easy to switch.
- **A4 — Briefing storage.** New `DailyBriefing` model (per user, per run)
  rather than overloading `RelevanceScore.signals`, because the briefing spans
  categories and needs its own lifecycle/audit. (Confirm you're OK with one new
  small model + migration.)
- **A5 — Briefing scope is per-user for v1** (not lab-aggregated), per the
  earlier discussion. Lab-aware briefings are a later phase.
- **A6 — Placement.** The "Mylo Report" becomes the **Daily** section
  (`/app/daily`, `daily-reports-section.tsx` rebuilt) and supersedes the Overview
  `daily-digest-panel`. (Confirm: rebuild Daily in place vs. new route.)
- **A7 — Timer time.** Host timer runs once daily after both legacy hours; plan
  proposes **07:00 local** (after the old 6am search) with `Persistent=true` so a
  powered-off machine catches up. Adjustable via the unit.

## 5. Architecture of the woven daily flow

```
mylo-daily.timer  ──fires──▶  mylo-daily.service  ──runs──▶  manual_all.py (host)
                                                              │
   stage 1 scrape (Pivot, host) ─┐                            │  each stage wrapped;
   stage 2 run_daily_suggestions │  on failure / notable      │  structured events →
   stage 3 run_daily_opportunities  condition ────────────────┼──▶ mylo.reporting.report()
   stage 4 run_refitting         │                            │        │ REST POST
   stage 5 generate_daily_briefing (NEW) ─────────────────────┘        ▼
                                                               ERROR_CHANNEL (Discord)
                                                                        ▲
   mylo-bot.service (persistent discord.py)  ── slash cmds, heartbeat, run summary
   DailyBriefing rows ──▶ GET /api/daily-briefing/ ──▶ "Mylo Report" three-zone UI
```

## 6. Implementation Phases

Each phase ends with **validation + a focused commit** (no push). Phases 1–2 and
3 are largely independent and are good candidates for parallel subagent
implementation (see §10).

### Phase 0 — Branch & scaffolding
- Create a worktree/branch `mylo-briefing-discord` off `main` (see §11).
- Add plan to `docs/plans/` (this file). Add `docs/changelog.md` entry when work
  starts touching tracked files.
- **Validate:** branch builds clean (`python run.py status`, backend import).

### Phase 1 — Mylo error-reporting seam + secrets (foundation)
Delivered first so later stages can report through it.
- New host-side package `mylo/` (repo root, run with root `uv`/venv like
  `pivot.py`). `mylo/config.py` loads `.env-mylo` (`DISCORD_API_KEY`,
  `ERROR_CHANNEL`), fail-fast validation, never logs the token.
- `mylo/reporting.py`: `report(event)` builds a structured error/status embed and
  POSTs to `ERROR_CHANNEL` via authenticated Discord REST (`Authorization: Bot`).
  Severity levels (`error`/`warn`/`info`), a title, a body, a source stage, and
  an optional "action needed" line (e.g. "run `uv run pivot.py login`"). No-op
  with a local log warning if creds are absent (never crash the daily run).
- Message-length safe (2000-char content / 6000 embed caps).
- **Public interface changes:** none (internal module). `.env-mylo.example`
  unchanged (already correct).
- **Validate:** unit test with a stubbed HTTP client asserts payload shape,
  truncation, and no-creds no-op; one manual live post to `ERROR_CHANNEL`.
  **Commit.**

### Phase 2 — Host daily run + retire in-container Beat daily schedules
- **Refactor `manual_all.py` error handling:** wrap each stage; on the known
  conditions, call `mylo.reporting.report(...)`:
  - Pivot session missing/expired **and** non-interactive → **actionable error**
    ("Mylo needs a manual Pivot login on <host>").
  - Scrape/import failed (session likely expired).
  - A container stage (search/match/refit/briefing) exits non-zero.
  - **LLM unreachable** (reuse `llm_check` logic or detect fallback) → **warn**
    ("ran on deterministic fallback").
  - Success → optional `info` run-summary (counts) — can be posted by the bot
    instead (Phase 4) to avoid duplication.
  - Preserve current behavior: scrape stage stays non-fatal; a failed
    recommend/refit stage still stops the run (now *reported*, not silent).
- **New host units** (repo root, mirroring `mycelium*.service`):
  - `mylo-daily.service` (`Type=oneshot`, `WorkingDirectory=/home/bdgr/Agents/Mycelium`,
    `ExecStart=/usr/bin/python3 manual_all.py`, `User=bdgr`, journald). Requires
    the stack: `After=mycelium.service`.
  - `mylo-daily.timer` (`OnCalendar=*-*-* 07:00:00`, `Persistent=true`,
    `WantedBy=timers.target`).
  - Document enable steps in the unit header (like `mycelium-update.service`).
- **Retire in-container daily schedules:** remove `run_daily_suggestions` and
  `run_daily_opportunities` entries from `CELERY_BEAT_SCHEDULE`
  (`web/backend/config/settings.py`), leaving `recompute_project_profiles`. The
  management commands and Celery tasks **remain** (used by `manual_all.py` and
  manual runs); only the *schedule* moves to the host timer. Add a settings
  comment explaining the host timer now owns the daily run.
- **Docs:** update `docs/repo-map.md` (systemd units row, run/build row) and
  `docs/plans/proquest-integration.md` cross-refs if they assert the Beat hours.
- **Validate:**
  - `python manual_all.py --help` unchanged; dry structure review.
  - Backend test suite green (`uv run --project web/backend pytest`) — proves the
    Beat-schedule edit didn't break config import.
  - `systemd-analyze verify ./mylo-daily.service ./mylo-daily.timer` (syntax).
  - Simulate each error condition (e.g. move the Pivot session file, stop the LLM)
    and confirm a correctly-classified Discord post.
  **Commit.**

### Phase 3 — Briefing backend (new synthesis stage + model + API)
- **Model:** `apps/content/models.py` → `DailyBriefing` (`id`, `user` FK,
  `run_at`, `generated_at`, `body` text (the 2–3 paragraphs), `counts` JSON
  (per-category), `showcase` JSON (top item refs per category), `origin`
  (`llm`/`fallback`), `categories` JSON snapshot of what the user watched).
  Object-level: a user reads only their own briefing. Migration depends on the
  latest content migration.
- **Synthesis:** `apps/content/briefing.py` →
  `generate_briefing_for_user(user)`: read the latest-run `RelevanceScore` rows
  across the categories in `WatchPreference.categories`
  (papers + grants + conferences + fellowships), assemble counts + top items,
  call the LLM to write a grounded 2–3 paragraph briefing that **references the
  showcase items only** (no fabrication), with a **deterministic template
  fallback** (mirrors `suggest.py`/`opportunity_llm.py`). Persist a
  `DailyBriefing`.
- **Command + stage:** `management/commands/generate_daily_briefing.py`
  (all users / `--user`). Add as **stage 5** in `manual_all.py`
  (`CONTAINER_STAGES`), after refit. Errors/fallback → `mylo.reporting`.
- **API:** `GET /api/daily-briefing/` (`DailyBriefingView`, `IsAuthenticated`)
  returns `{ generated_at, categories, counts, showcase, briefing: {body,
  origin} }`, gated on the user's watched categories; honest empty state when no
  run yet. Keep `GET /api/daily-report/` for the Research Papers page.
- **Docs:** `docs/api-contract.md` (new endpoint), `docs/repo-map.md`
  (content app row: `briefing.py`, `DailyBriefing`, command).
- **Validate:** unit tests for synthesis (LLM stubbed → asserts grounding on
  showcase items + fallback path + category gating); API test (auth, own-briefing
  only, empty state, populated shape); one live `generate_daily_briefing --user
  brendondgr` in the container after a real run. **Commit.**

### Phase 4 — Mylo persistent bot (gateway service) + run summary
- **Package `mylo/bot/`** per the discord.py standard (`__main__.py`, `client.py`,
  `config.py` shared with Phase 1, `errors.py` (CommandTree subclass), `cogs/`).
  Non-privileged intents only. Slash commands in a cog:
  - `/mylo health` (ephemeral): stack/LLM/Pivot-session status.
  - `/mylo lastrun` (ephemeral): last `manual_all.py` outcome + counts (reads a
    small run-state file the daily run writes, or the latest `DailyBriefing`).
  - (Stretch) a button to acknowledge a re-login request.
- **Run summary:** after a successful daily run, post a concise embed (counts per
  category, link to `/app/daily`) to `ERROR_CHANNEL` (or a future
  `SUMMARY_CHANNEL`). Delivered by the reporter seam (Phase 1) so it works even if
  the gateway is momentarily down; the persistent bot owns the interactive slash
  commands.
- **Command sync:** guild-scoped sync via optional `DISCORD_DEV_GUILD_ID` in dev;
  deliberate global sync via an owner-only path — **never on every boot** (§5 of
  the standard).
- **`mylo-bot.service`** (host systemd, `Restart=always`, `WantedBy=multi-user.target`,
  `User=bdgr`, journald, reads `.env-mylo`). Header documents `enable --now` and
  portability (copy unit + `.env-mylo` to another host). Add `discord.py==2.7.1`
  to the root/host dependency set (`pyproject.toml`), not the backend container.
- **Docs:** `docs/repo-map.md` (new `mylo/` area + units); note token handling in
  security terms.
- **Validate:** `python -m mylo.bot` imports and connects against the dev guild;
  `/mylo health` returns within 3s (defer if needed); `systemd-analyze verify
  ./mylo-bot.service`; confirm single-replica (no double-post). **Commit.**

### Phase 5 — "Mylo Report" three-zone UI
- **Hook + types:** `web/app/src/lib/portal/hooks.ts` → `useDailyBriefing()`;
  `types.ts` → `DailyBriefing`, `BriefingShowcase`, `CategoryCounts`.
- **Rebuild the Daily section** (`daily-reports-section.tsx`, or a new
  `mylo-report-section.tsx` wired to the `daily` key) as three zones:
  - **Left — Mylo Report:** the `body` briefing prose, Mylo voice/mascot, marquee.
  - **Top-right — Today's Summaries:** numeric `counts` per watched category only.
  - **Bottom-right — Briefing showcase:** top `showcase` item(s) per category,
    each linking into its existing page (papers/opportunities/etc.).
- **States** (per `global.md` UI rule): loading, briefing-not-yet-run (counts may
  still show), LLM-fallback body, user watches only some categories (zones
  collapse), error, empty, mobile stack order (briefing → summaries → showcase),
  reduced-motion, contrast.
- **Supersede** the Overview `daily-digest-panel` (repoint or retire).
- **Naming:** standardize the mascot spelling to **"Mylo"** (styles.md canonical)
  in all touched copy — current code mixes "Milo"/"Mylo".
- **Validate:** verify via the compose dev app at `localhost:11050` with
  DOM/console reads (per the frontend-dev memory), not screenshots on a worktree;
  `tsc` + `eslint` + `next build`; check every state incl. mobile + dark. **Commit.**

### Phase 6 — End-to-end validation, docs, merge
- Full run: bring stack up → `python manual_all.py` on host → confirm briefing
  rows, Discord posts (success + a forced error), and the UI renders.
- `docs/changelog.md` entries (one correlation ID per phase or a rollup).
- Confirm `docs/repo-map.md`, `docs/api-contract.md`, `docs/goals.md`
  (Daily Report "later phase" note → mark delivered) are consistent.
- **Merge worktree → local `main`**, resolving conflicts; re-run backend tests +
  `next build` post-merge (worktree base lags local main — see memory). Final
  commit. **No push.**

## 7. Public Interfaces / Files That Change

- **New backend:** `apps/content/models.py` (`DailyBriefing` + migration),
  `apps/content/briefing.py`, `management/commands/generate_daily_briefing.py`,
  `DailyBriefingView` + URL `GET /api/daily-briefing/`.
- **Changed backend:** `config/settings.py` (`CELERY_BEAT_SCHEDULE` — remove two
  daily entries).
- **New host code:** `mylo/` (config, reporting, `bot/` package), root
  `pyproject.toml` dep `discord.py==2.7.1`.
- **New infra:** `mylo-daily.service`, `mylo-daily.timer`, `mylo-bot.service`.
- **Changed root:** `manual_all.py` (structured error reporting + stage 5).
- **New/changed frontend:** `daily` section rebuilt (three zones), `hooks.ts`,
  `types.ts`; Overview `daily-digest-panel` superseded.
- **Docs:** `repo-map.md`, `api-contract.md`, `goals.md`, `changelog.md`,
  and this plan.

## 8. Security / Trust / Ownership

- **Object-level auth:** `/api/daily-briefing/` returns only the caller's
  briefing; `DailyBriefing` scoped by `user`.
- **Grounding:** the briefing body references only real showcase items;
  deterministic fallback when the LLM is down (honest, no fabrication) — matches
  `purpose.md`.
- **Secrets:** `DISCORD_API_KEY` stays in `.env-mylo` (git-ignored), read via
  config, never logged/committed. Bot uses non-privileged intents, minimal invite
  perms.
- **Audit/observability:** error routing to Discord is the observability win;
  keep the existing verbose daily logs under `data/logs/`.

## 9. Validation & Acceptance Criteria

- `manual_all.py` daily run is triggered by `mylo-daily.timer`; the two
  in-container daily Beat schedules are gone; `recompute_project_profiles`
  remains.
- A forced Pivot-session-missing run posts an **actionable** message to
  `ERROR_CHANNEL`; an LLM-down run posts a **warn**; a healthy run posts a
  **summary**.
- `mylo-bot.service` stays connected; `/mylo health` and `/mylo lastrun` respond
  < 3s; single replica (no double posts).
- `GET /api/daily-briefing/` returns a grounded 2–3 paragraph body + per-category
  counts + showcase, gated on `WatchPreference.categories`, own-user only.
- The Daily page renders the three zones across all UI states, mobile + dark,
  with correct Mylo spelling.
- Backend suite green; `tsc`/`eslint`/`next build` clean; worktree merged to
  `main`; all changes committed (not pushed).

## 10. Execution Strategy (Agent Workflows)

Per the requested model — **Opus plans, Haiku searches, Sonnet implements**:

- **Independent workstreams** good for parallel Sonnet subagents in a worktree:
  Phase 1 (reporting seam), Phase 3 (briefing backend), Phase 4 bot scaffolding.
  Phase 2 depends on Phase 1; Phase 5 depends on Phase 3.
- Use Haiku subagents for any path/symbol lookups the plan left open (e.g. exact
  `content` URL router, latest content migration name).
- Keep each subagent's output to a validated, committed slice; integrate on the
  branch. This maps to the Workflow tool only if you explicitly opt into
  multi-agent orchestration; otherwise implement sequentially with single agents.

## 11. Worktree & Git

- Implement in a worktree branch off `main`; hardlink-copy `web/node_modules`
  into the worktree if a Next build is needed there (per memory), and remember the
  worktree base is `origin/main` which **lags local `main`** — merge local `main`
  in before finishing.
- Commit after each validated phase with concise, human-authored messages (no AI
  attribution). **Do not push.** Merge to local `main` at the end (Phase 6).

## 12. Explicit Exclusions (v1)

- No lab-aggregated briefing (per-user only; lab-aware is later).
- No two-way "trigger a re-scrape from Discord" beyond the optional
  acknowledge-button stretch.
- No compose-service bot deployment (host systemd chosen; noted as alternative).
- No new opportunity sources or scraper changes; briefing reads existing rows.
- No push to remote; no changes to auth/session model.
```
