# Go-Public Readiness and Security Hardening — Implementation Plan

**Status (2026-11-12):** Phases 0–6 and 8 are built on branch
`go-public/hardening`, not yet merged to `main`. Still open:

- **Phase 0.4:** the production-host cleanup, done by the maintainer on that
  host. `docs/configuration.md` "If you ran an earlier version" lists the
  steps.
- **Phase 7:** the history rewrite and publishing. It waits until this branch
  and the scoping and settings branches are merged and every session has
  stopped.
- **Follow-ups found while building:**
  - a lab-settings card for answering department attach requests (the API
    exists);
  - a way for people to verify their own imported works (ORCID OAuth); until
    then a self-import does not feed co-authorship edges;
  - department ownership transfer;
  - deciding whether existing labs' stored `full` Discord guest level should
    drop to the new default;
  - suppressing link previews in the scheduled digest outbox;
  - parsing PDFs in a worker with limits;
  - pinning images by digest;
  - running the Node services without a read-write repository mount.

**Correlation ID:** `20261112-go-public-readiness`

## Objective

Make the repository safe to publish and safe to run in a university department:

- The repository and its full git history hold no private material: no real
  people's data, no paper, venue or grant plans, no traces of the retired
  ProQuest Pivot-RP scraper, no maintainer-specific defaults.
- A fresh clone sets itself up with secure defaults, says plainly which steps
  the operator must do by hand, and lands the first admin on a page that says
  what to do next.
- No known way for an outsider, or an ordinary member of a shared instance, to
  read or change what is not theirs.

This plan comes from a fresh-clone test run and four read-only reviews on
2026-11-12: private data and secrets, sign-in and accounts, authorization and
untrusted input, and deployment. No live secret was ever committed, so no key
needs rotating because of git. The reviews' findings are the work items below.

**Gate:** the repository is not made public until Phases 0–4 and Phase 7 are
done and the acceptance list at the end passes. This replaces the 2026-11-15
target in the publication plan. Set a new date once Phase 0 lands.

## Relation to other plans

- **`20261111-self-host-setup.md`.** Its Phase 0 ("Clear the traps") is folded
  into Phase 5 here. Its Phase 1 (`make doctor`) is pulled forward into
  Phase 5 in a minimal form. Its console, roster, model and Discord phases stay
  there and are not needed to go public.
- **`20261112-project-scoping-and-visibility.md`.** It owns "who can see and
  join a project". Two findings belong there (Phase 1, item 1.9). This plan only
  makes sure they are fixed before going public.

## Decisions already made (2026-11-12, by the maintainer)

- **Keep the GitHub repository and its full history.** Rewrite history in place
  with `git filter-repo` and force-push, rather than squashing or starting a new
  repository.
- **Remove the real-roster seeder** (`seed_fsu_sc.py`) from the tree and from
  history.
- **Remove every ProQuest / Pivot-RP trace** that is still in the tree. The
  scraper itself is already gone.
- **Paper, venue and grant material belongs in the private proposals
  repository only.** Make sure everything purged from history is preserved there
  first.
- **Setup must not ask for sudo.** It does what it can as the user and tells the
  operator exactly which commands they must run themselves.
- **No maintainer-specific defaults anywhere.** A fresh clone must not point at
  the maintainer's domain, model name or accounts.
- **Postgres and every other internal service are reachable only on the host,**
  never published to the network.

## Assumptions

- The maintainer's production instance runs on a separate host, not this
  workstation. Nothing runs here today: the Mycelium stack and `mylo-bot` are
  inactive. Phase 0 includes cleaning up that host.
- Coding agents in other sessions share the main checkout. The history rewrite
  (Phase 7) needs every session stopped and every checkout re-cloned afterwards.
- The pending scoping and settings plans keep their own scope and are not
  blocked by this one, apart from the ordering noted in Phase 7.

---

## Phase 0 — Stop the active leaks (do first, ships alone)

**0.1 The public front page returns 500 on `main`.** Commit `fd7d686` deleted
`web/landing/src/components/landing/FeedTabs.astro`, but
`web/landing/src/pages/index.astro` and `lab.astro` still import it. Either
restore the component or switch both pages to its replacement (`FeedDeck`),
whichever the landing redesign intended. Update the `FeedTabs` rows in
`docs/repo-map.md` to match.

**0.2 Sign-in and sign-up can put the password in the URL.** The forms in
`web/app/src/components/auth/{login-form,signup-form,forgot-password-form}.tsx`
have no `method`. If the user submits before React hydrates (which is easy under
`next dev`), the browser sends `GET /login?username=…&password=…`. That URL is
written to the nginx log, browser history, and the `Referer` of every asset
fetched before hydration. `login-query-sanitizer.tsx` runs too late to help.
This is a regression from `3429feb`, which removed `method="post"` to stop
Firefox's resend prompt.

- Add `method="post"` with `action` pointing at a new route handler that only
  accepts POST: `app/{login,signup,forgot-password}/fallback/route.ts`. It
  discards the body and returns `303` to the page with `?nojs=1`. A 303 turns
  into a GET, so Firefox shows no resend prompt.
- Disable the submit button until the page has hydrated. Per the HTML spec, a
  disabled default button also blocks Enter-key submission.
- Do the same in `reset-password-form.tsx` defensively.
- Extend the sanitizer's key list to `password_confirm`, `access_code`, the
  name fields, `new-password` and `confirm-password`.

**0.3 Stop logging secrets.** In `web/infra/nginx/default.conf`, add a
`log_format` that logs `$request_method $uri` (no query string, no referer).
Exclude or mask `/join/<token>`, `/reset-password` and `/api/auth/invites/<token>`.
Delete `config/debug_middleware.py` (`CsrfDebugMiddleware`). It logs the Origin
and Referer of every POST, which include reset and invite tokens, and it reads
cookie names that no longer exist.

**0.4 Production-host cleanup** (on the maintainer's server, by the maintainer,
with the steps written into `docs/configuration.md` as a one-off note):

- Rotate the Postgres password and bind its port to `127.0.0.1` (Phase 4 makes
  this the default).
- Recreate the nginx container so its unrotated Docker log is dropped. Check any
  Cloudflare tunnel request logs as well.
- Ask users who signed in while 0.2 was live to change their password, or
  require a password reset for all of them.
- Delete any accounts created by `seed_fsu_sc` or `seed_demo` from the live
  database, and the `data/logins/*.csv` files they wrote. Those passwords are
  reproducible from the public seed code.
- Set `chmod 600` on `.env` and `.env-mylo`. This workstation's copies were
  fixed on 2026-11-12.

**Validation:** `make test`; `cd web && npm test && npm run lint`; a Playwright
test that blocks `/_next/static/**`, submits the login form, and asserts that
the URL has no query string and the nginx line is `POST /login/fallback`.
Run `curl -s localhost:11050/ -o /dev/null -w '%{http_code}'` and expect `200`.

## Phase 1 — Authorization between users, labs and departments

The reviews found per-object checks sound for projects, files, Mylo threads,
ambient, reminders and search. The gaps are in how labs and departments gain
members and labs.

| # | Severity | Change | Where |
|---|---|---|---|
| 1.1 | Critical | Attaching an existing lab to a department needs the lab owner's consent. Either the actor is that lab's owner, or attaching creates a request the lab owner accepts. Today any verified user can create a department, attach any lab that has no department, and then read every project of that lab (including project state) and every member's email. | `apps/accounts/views.py` `DeptLabsView.post`, `services.py` `attach_existing_lab_to_department` |
| 1.2 | High | Apply the role-rank rule to every path that grants a lab role: `add_lab_member`, `invite_to_lab`, `create_invite(s)`. Reuse `user_can_grant_lab_role`, as `set_lab_member_role` already does. A link or invitation never grants `owner`, and only the owner grants `admin`. | `services.py`, `invites.py` (`_clean_role`), `LabInvitationsView`, `_OrgInvitesView` |
| 1.3 | High | Joining needs consent. A direct "add by username" becomes an invitation the person accepts. Until they accept, the person does not appear in the roster and their email is never returned. The response must not reveal whether the username exists. | `LabMembersView.post`, `DeptMembersView.post`, `add_dept_member`, roster serializers |
| 1.4 | High | Add a department role-rank rule matching the lab one (owner > admin > member) for adding, changing and removing department members. | `apps/accounts/permissions.py`, department views |
| 1.5 | High | A legacy `LabInvitation` is matched and accepted only by an account whose address is proved (`Profile.is_verified`). Alternatively, retire `LabInvitation` in favour of `OrgInvite`. | `register_view` → `claim_pending_invitations`, `InvitationRespondView` |
| 1.6 | Medium | The transcript preview checks lab membership before returning anything. | `apps/ambient/views.py` `_meeting_scope` |
| 1.7 | Low–Med | A reminder's `channel_id_override` must be one of the lab's own server channels. | `tools/delivery/reminders_views.py`, `reminders_discord.py` |
| 1.8 | Low–Med | Throttle invitations per creator and per org per day, so the instance cannot be used to send bulk email. | `_OrgInvitesView`, `invites.py` |
| 1.9 | Low | Owned by the scoping plan; must land before going public. `ProjectLeaveView` checks visibility (or returns 204 with no body). A lab `viewer` cannot self-join a project, and joining follows the project's visibility. | `apps/research/views.py` |
| 1.10 | Low | ORCID and OpenAlex imports of someone else's id: store the works as unverified and leave them out of co-authorship and "demonstrated" edges until the id is verified. | `ImportAuthorView`, `store_author_works` |
| 1.11 | Low | With `billing.mode = "subscriptions"`, activating a plan needs payment or staff approval. Billing is dormant by default, so this only blocks turning billing on. | `apps/billing/views.py` |

**Validation:** add one pytest per row in `apps/accounts/tests/`,
`apps/ambient/tests/`, `tools/delivery/tests/` and `apps/research/tests/`. The
reviews gave test outlines, for example `test_dept_head_cannot_attach_foreign_lab`,
`test_admin_cannot_add_owner`, `test_direct_add_requires_consent` and
`test_transcript_preview_requires_lab_membership`. Run them with
`uv run --project web/backend pytest` against the Compose Postgres.

## Phase 2 — Sign-in and account hardening

- **Brute force.**
  - Add a login throttle keyed on the normalised username and the real client
    IP, covering `/api/auth/login` and `/admin/login/` (django-axes or a
    custom throttle).
  - Remove `BasicAuthentication` from `REST_FRAMEWORK`.
  - Restrict `/admin/` in nginx (Phase 4).
- **Client IP cannot be spoofed.**
  - nginx sets `X-Forwarded-For $remote_addr` and forwards `$scheme`, trusting
    a front proxy only when it is named.
  - Set DRF `NUM_PROXIES = 1`.
  - `signup_gate.client_subject` uses the same rule.
  - Trust `CF-Connecting-IP` only behind a configured tunnel.
- **CSRF on login and sign-up.** Wrap `login_view` and `register_view` with
  `csrf_protect` and limit the parsers to `JSONParser`. This blocks login CSRF:
  a hostile page signing a visitor into the attacker's account.
- **Verification gate.** When `signup.verify_email` or domain mode is on, add a
  default DRF permission that requires a proved address. Exempt only `me`,
  verify, resend and logout.
- **Tokens.**
  - Store `OrgInvite` tokens as `sha256(token)` and look them up by hash. Show a
    share link once, and let it be regenerated.
  - Take the password-reset token out of the logged URL: exchange it on load and
    call `history.replaceState`.
  - Increase the sign-up code from 32 bits to `token_urlsafe(16)`.
- **Smaller fixes.**
  - Make the email-code attempt counter atomic (`F()` increment or
    `select_for_update`).
  - Return generic sign-up errors, and send reset mail through `on_commit` /
    Celery so the response time does not reveal which accounts exist.
  - Set `SESSION_COOKIE_AGE` and add "sign out everywhere".
  - Make `ADMIN_USER_PASS` one-time: bootstrap prints it once, and it is
    removed from `.env` after the first admin exists.
  - Drop the localhost origins from CORS and CSRF when `PUBLIC_HOSTNAME` is set.
- **Privacy rights.** Add `DELETE /api/auth/account/` (re-authentication plus a
  mailed code; cascades; audited) and `GET /api/auth/account/export/`. Add both
  to the account section of the app and to `docs/api-contract.md`. University
  deployments will be asked for erasure and export.

**Validation:**
- 30 bad logins return 429.
- `curl -u user:pass /api/auth/me/` no longer authenticates.
- A cross-origin form POST to `/api/auth/login` returns 403.
- 25 register POSTs with different `X-Forwarded-For` values return 429 after 20.
- The `OrgInvite` row holds no usable token.
- Tests cover account-deletion cascade and export contents.

## Phase 3 — Untrusted content

- **Lab logos.** Reject SVG, or serve it as an attachment with
  `Content-Security-Policy: default-src 'none'; sandbox`. Today a lab lead can
  plant a script that runs when a member opens the logo URL
  (`accounts/views.py` logo upload and serving).
- **Mylo in Discord.**
  - Send with `suppress_embeds=True` and wrap model-written URLs in `<…>`, so a
    prompt-injected link cannot leak data through Discord's link preview
    (`mylo/bot/cogs/chat.py`, `tools/agent/surfaces/discord.py`).
  - Change the guest defaults in `tools/agent/tool.py` so a Discord user with no
    Mycelium account cannot list a lab's members or their interests unless the
    lab raises the level.
- **Outbound fetches.** The full-text fetcher refuses private, loopback and
  link-local addresses on every redirect hop, and only uses http(s) on ports
  80/443 (`tools/fulltext/engine/fetcher.py`).
- **Report PDF.** Escape `"` in URLs and allow only http(s) schemes
  (`tools/delivery/daily_report_pdf.py`).
- **Uploads.**
  - Résumé parsing checks `upload.size` before reading and caps the page count
    (`accounts/intake/resume.py`, `research/views.py`).
  - Move PDF parsing into a Celery task with time and memory limits.
  - The files list filters in SQL (`tools/files/access.py`).
- **Markdown.** `markdown-prose.tsx` reuses the agent renderer's link-scheme
  allowlist (`SAFE_LINK`).

**Validation:**
- An SVG logo containing `<script>` is rejected or served sandboxed.
- The chat cog's send arguments include `suppress_embeds=True`.
- A guest caller is denied `org_lab_members`.
- A mocked redirect to `127.0.0.1` is refused.
- A URL containing `"` stays inert in the PDF.

## Phase 4 — Secure-by-default stack

**Network (`compose.yaml`).**
- Publish only nginx, on `${BIND_ADDR:-127.0.0.1}:${NGINX_PORT:-11050}`. To
  serve the network, the operator sets `BIND_ADDR`, or better, puts TLS in front.
- Postgres on `127.0.0.1:11450` only, because the host Mylo bot needs it.
- Remove the published ports of landing, web, backend, both Redis instances,
  Neo4j and MinIO. Dev ports move to `compose.dev.yaml`.
- Docker's published ports go around ufw and firewalld, so binding to loopback
  is the real control.

**Credentials.**
- Bootstrap generates `POSTGRES_PASSWORD`, `REDIS_PASSWORD` and, if those
  services are enabled, the Neo4j and MinIO passwords. Compose interpolates them.
- No credential is written as a literal in `compose.yaml` or `.env.example`.
- Redis runs with `--requirepass`.
- Bootstrap writes `.env` mode `0600`, and `ops/mycelium status` warns if
  either `.env` file is not `0600`.

**Django.**
- `DJANGO_DEBUG=False` in `.env.example`, written explicitly by bootstrap.
- The app refuses to start with DEBUG on when `PUBLIC_HOSTNAME` is set.
- It refuses to start with an empty or default `SECRET_KEY` (`change-me`,
  `django-insecure-…`) outside tests.
- Secure cookies, HSTS and SSL redirect depend on "served over HTTPS"
  (`PUBLIC_HOSTNAME` set), not on DEBUG.
- Loggers at INFO.
- `manage.py check --deploy` runs from `ops/mycelium status`.

**Production processes.**
- A production profile: gunicorn for `config.wsgi`, `next build && next start`,
  and a static `astro build` served by nginx.
- `make setup` and `make up` use it by default. `make dev` keeps today's
  hot-reload stack.
- Neo4j and MinIO move under `profiles: ["experimental"]`. Drop backend's
  `depends_on` on them; nothing reads them.

**Containers.**
- Run as `user: "${UID}:${GID}"`.
- Mount the source read-only, with only `data/`, the venv and node_modules
  writable. No repository mount at all for the Node services in production.
- Use `npm ci` and `uv sync --locked`. Pin images by digest. Cap container logs
  (`max-size: 10m`, `max-file: 5`).

**nginx.**
- `server_tokens off`.
- Security headers with `always`: `nosniff`, `Referrer-Policy`,
  `Permissions-Policy`, and a CSP with `frame-ancestors 'none'` (Report-Only
  first). HSTS when TLS is in front.
- `limit_req` on `/api/auth/` and `/admin/`. `/admin/` allow-listed or moved.
- `client_max_body_size` 1m by default, 26m on `/api/` so the files tool's 25 MB
  limit works.
- In production, `/_next/` serves only built assets.
- Ship an example TLS front end in `docs/configuration.md`: Caddy, certbot, or a
  Cloudflare tunnel in front of a loopback-bound nginx.

**Relays.**
- `decision-relay` binds to a dedicated compose network or requires a token.
- `llm-tunnel` defaults its SSH mount to an empty directory instead of
  `/etc/ssh`.

**Host.**
- The systemd units gain hardening directives (`NoNewPrivileges`,
  `ProtectSystem=strict`, `ReadWritePaths=<root>/data`, `PrivateTmp`,
  `ProtectHome=read-only`).
- Fix the stale `scripts/mycelium` references.

**Dependencies** (all with published advisories; the reviews list the IDs):

| Package | Upgrade to | Note |
|---|---|---|
| next | ≥ 16.4.6 | Includes a middleware bypass and remote code execution in image optimization |
| astro | ≥ 7.3.2 | Major-version jump; test the landing site |
| django | ≥ 5.2.17 | |
| djangorestframework | ≥ 3.18.2 | |
| pypdf | ≥ 6.21.4 | Parses user uploads |
| aiohttp | ≥ 3.14.4 | |
| cryptography | ≥ 50 | |
| pillow | ≥ 13 | |

**Backups.** Add `make backup` (`pg_dump -Fc` plus a tar of `data/files`,
`web/backend/media` and `mycelium.toml`, mode 0600) and `make restore`, with
retention guidance in `docs/configuration.md`.

**Validation:**
- From a second machine, `nc -vz <host> 11450 11550 11551 11350 11250` is
  refused.
- `ss -ltn` shows only nginx on a non-loopback address, and only if `BIND_ADDR`
  was set.
- `curl :11050/api/nonexistent/` returns a short 404 with no URL list.
- `manage.py check --deploy` passes behind TLS.
- `npm audit --omit=dev` and `uvx pip-audit` report no high or critical
  advisory.
- `git status` is clean after `make restart`.
- A restore into a scratch stack brings back a known user.

## Phase 5 — Setup and first run

- **Neutral defaults.** `PUBLIC_FALLBACK_HOSTNAME` empty in `.env.example` and
  `config/settings.py`; links are left out when no public origin is known.
  `LLM_MODEL` and `LLM_BASE_URL` empty, so model features stay off until
  configured. Then `grep -rn brendondgr` over `.env*.example`,
  `mycelium.example.toml`, `web/backend/config/`, `ops/` and `web/infra/` must
  return nothing.
- **Setup asks what it needs.** When run in a terminal, bootstrap asks for:
  - the public hostname (or "local only");
  - the model: a server, an API key, or "none for now".

  It writes no placeholder in their place. Without a terminal, it takes them
  from the environment and reports what is unset.
- **No sudo during setup.** Bootstrap and `ops/mycelium restart` never call
  `sudo`. When a step needs root (installing the systemd units for the nightly
  run and the bot), setup ends with a "You need to run these yourself" block:
  the exact commands, why each one is needed, and how to check it worked.
  `ops/mycelium status` shows the same block until the step is done.
- **The first run can be finished from inside the stack.**
  - The first collection runs in a container (`make nightly` runs it through
    `docker compose exec`, so no `uv` is needed on the host).
  - Staff get a "Run first collection" action on the overview page.
  - The host timer stays the scheduled path.
- **The first admin sees what to do next.** The overview page's empty state
  becomes a checklist for staff. Each item turns done from a real check:
  1. Connect a language model, or continue without one.
  2. Run the first collection, with progress shown.
  3. Fill in your profile.
  4. Invite people.
  5. Optional: Mylo in Discord.

  Non-staff users with no data see a plain explanation instead of zeros. This
  follows `docs/styles.md`, and covers loading, empty, error and mobile states.
- **A minimal `make doctor`.** One command that checks:
  - the stack is up;
  - migrations are applied;
  - the model answers (`llm_check`), or is off on purpose;
  - the embedding model has been downloaded;
  - the corpus is not empty;
  - secret files are `0600`;
  - no internal port is published beyond loopback;
  - `check --deploy` passes.

  It exits 1 on any failure, and prints the reason and the fix. The full version
  stays in `20261111-self-host-setup.md` Phase 1.
- Fold in the rest of that plan's Phase 0. Setup writes `DATABASE_URL`.
  `ERROR_CHANNEL` becomes optional. The bot exits cleanly when it has no token.
  Correct the wrong instructions in `ops/systemd/mylo-bot.service`,
  `docs/discord-integration.md` and `docs/skills/discord-bot.md`.

**Validation:** repeat the 2026-11-12 fresh-clone test: `git clone` into an
empty folder, then `make setup --yes` with no model.
- It finishes with no sudo prompt.
- `/` returns 200.
- The admin sees the checklist.
- The first collection fills the corpus.
- `make doctor` exits 0.
- Removing the model makes `make doctor` exit 1 with a plain reason.

## Phase 6 — Clean the tree

**Real people.**
- Delete `web/backend/apps/accounts/management/commands/seed_fsu_sc.py` and its
  references in `docs/repo-map.md` and `docs/changelog.md`. `seed_demo` (all
  fictional) stays the only seeder.
- Make both seeders use `secrets` with `set_unusable_password()` by default,
  refuse to run with DEBUG off, and write any login file as 0600.
- Remove the faculty username in `grant_institution.py` and its changelog entry.
  Make the command take the username as an argument.
- Remove another user's handle and production usage figures from
  `docs/research-audit.md`.

**ProQuest / Pivot-RP.** The scraper is gone. What remains:
- Comments and docstrings that narrate its history in about 40 files, including
  `tools/retrieval/collect/`, `tools/retrieval/fellowships/`,
  `tools/retrieval/host/scrape_fellowships.py`, `tools/delivery/serializers.py`,
  `ops/nightly/manual_all.py`, `web/backend/pyproject.toml`, `eval/pyproject.toml`
  and a few app components.
- The `data/pivot/` directory name and `_purge_stale_pivot_json`.
- Serializer fallbacks for Pivot-era keys (`sponsor`, `matched_topics`,
  `event_dates`).
- `pivot.proquest.com` URLs in four test fixtures.
- The `.gitignore` and `.env.example` lines.

The fix:
- Rewrite the comments to describe what the code does now.
- Rename `data/pivot` to `data/fellowships`, with a one-off move in the nightly
  run.
- Before dropping the key fallbacks, check the production database for rows
  still carrying them, and migrate those rows first.
- Replace the fixture URLs with `example.org` ones.
- Do not edit applied migration logic; a comment-only edit is fine.
- Check the eligibility excerpts in `EXP-2026-11-001`'s `labels.csv` and
  `EXP-2026-11-002`'s `labfit_labels.csv` for text that came from Pivot. If any
  did, redact the excerpt column and record it in the experiment's `ISSUES.md`.
  Never silently edit research data.

**Private plans and paths.**
- `CLAUDE.md`'s "Papers, venues and grants" section becomes a generic line:
  plans for papers live outside this repository. No path.
- Replace absolute `/home/bdgr/...` paths with repo-relative ones in:
  - `tools/recommendation/fellowships.py`
  - three test files
  - `docs/research-audit.md`
  - the experiment code and protocols of `EXP-2026-08-006`, `-007`, `-012`,
    `EXP-2026-11-003` and `EXP-2026-11-012`
- Rename the venue-revealing changelog slugs, or redact them in Phase 7.
- Decide whether naming the real PULSE Lab in experiment data is acceptable; if
  not, pseudonymise it.

**Validation:**
- `make test`, `make validate-research`, `make tools-check`.
- `git grep -n -i -w -E 'proquest|pivot|pivot-rp'` returns nothing (a
  word-bounded search, so "pivotal" does not match).
- `git grep -n /home/bdgr` returns nothing.

## Phase 7 — Rewrite history in place, then publish

1. **Preserve first.**
   - Make a bare mirror backup: `git clone --mirror` to an off-repo location,
     kept private.
   - Confirm the private proposals repository holds every file being purged:
     - the old `docs/research/paper/` files;
     - the pre-redaction changelog entries;
     - the 145 lines cut from `docs/research-audit.md` in `af71418`.

     Copy whatever is missing, under `2026-mycelium/notes/`.
2. **Freeze.** Stop every agent session working in this repository. Commit or
   park their work. Remove the worktrees and the stash.
3. **Rewrite** with `git filter-repo`:
   - `--invert-paths` for:
     - `docs/research/paper/`
     - `seed_fsu_sc.py`
     - `data/logs/mylo-last-run.json`
     - `docs/plans/20260920-account-and-lab-management.md`, the commit that
       held a personal email (or replace-text that one address instead)
     - `web/backend/apps/scraper/pivot/`, `pivot.py`
     - `docs/plans/proquest-integration.md`
   - `--replace-text` for:
     - the personal email
     - the faculty username
     - the other user's handle
     - the internal hostname
     - the pre-redaction changelog and research-audit passages
   - Optionally, `--mailmap` the author address to the GitHub noreply address.
     **This is an open question.**
4. **Branches.** Rewrite `data-model` too, or delete it locally and on GitHub.
   It is merged.
5. **Verify before pushing.** Run `git log -p --all` through the same grep
   patterns the 2026-11-12 review used. Also run a secrets scanner (gitleaks)
   over the full history, and confirm `make test` still passes on the rewritten
   `main`.
6. **Push.** Force-push every branch and tag.
7. **GitHub keeps old commits.** Pull request #1 (merged) keeps its old commits
   under `refs/pull/1/head`, which a force-push cannot remove. Ask GitHub
   Support to delete the PR refs and garbage-collect the cached objects. Wait
   for confirmation before making the repository public. The repository has no
   forks.
8. **Re-clone everywhere:** this workstation, the production host, and any
   agent worktrees. Old clones must not be pushed again.
9. **Publish.**
   - Flip visibility.
   - Turn on secret scanning and push protection, Dependabot alerts, and private
     vulnerability reporting.
   - Update the proposals repository's dates (the JOSS six-month clock starts
     now).

Order with other work: land the scoping and settings plans before the rewrite
or after it, not across it. Their branches would need rebasing onto the
rewritten history.

## Phase 8 — Public-project basics (can follow publication)

- **CI:** *dropped 2026-11-14 at the maintainer's request — nothing runs
  automatically on GitHub (the workflow and Dependabot were removed); the
  same checks are run locally.* It was a GitHub Actions workflow running:
  - backend and tool tests against a Postgres service, plus `make test-mylo`;
  - `npm run lint`;
  - `make validate-research`;
  - `npm audit --omit=dev`, `pip-audit`, and gitleaks.
- `SECURITY.md` (private reporting through GitHub, supported versions, response
  time), `CODE_OF_CONDUCT.md`, and issue and pull-request templates.
- In the README:
  - Hardware requirements: RAM, disk, the embedding-model download, GPU optional.
  - What works without a model.
  - A "Running it for a department" section linking the TLS and backup docs.
- A first tagged release, `v0.1.0`, with release notes.

## Interfaces that change

- **Routes:**
  - new `POST /login/fallback`, `/signup/fallback`, `/forgot-password/fallback`;
  - new `DELETE /api/auth/account/`, `GET /api/auth/account/export/`;
  - department lab attach becomes a request plus acceptance;
  - direct member add becomes an invitation.
- **Models:**
  - a lab-attach request;
  - `OrgInvite` stores a token hash;
  - ORCID and OpenAlex `AuthorWork` gains a verified flag.
- **Config:**
  - `BIND_ADDR`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`;
  - `DJANGO_DEBUG=False` by default;
  - `PUBLIC_FALLBACK_HOSTNAME` and `LLM_*` empty;
  - the agent's guest defaults.
- **Commands:** `make dev`, `make doctor`, `make backup`, `make restore`;
  `make nightly` runs in-stack.
- **Files:**
  - `compose.dev.yaml`;
  - nginx `log_format` and headers;
  - `SECURITY.md`, `CODE_OF_CONDUCT.md`, `.github/`.
- **Docs to update as each phase lands:**
  - `docs/api-contract.md`, `docs/architecture.md`, `docs/configuration.md`;
  - `docs/repo-map.md`, `README.md`;
  - `docs/skills/configure.md`, `docs/discord-integration.md`.

## Acceptance — the go-public gate

1. A fresh clone runs `make setup --yes` with no sudo prompt, serves `/` with
   200, and `make doctor` exits 0.
2. From another machine, only the nginx port answers, and only when the operator
   opted in.
3. A login submitted before hydration never puts credentials in the URL or the
   logs.
4. Every Phase 1 test passes. A verified stranger cannot attach a lab, plant an
   owner, read a member's email, or read a project they are not part of.
5. `npm audit --omit=dev` and `pip-audit` report no high or critical advisory.
6. `git log -p --all` on the rewritten repository has no hits for:
   - the private-data patterns;
   - `proquest` or `pivot` (word-bounded);
   - `/home/bdgr`;
   - the proposals path.

   gitleaks is clean.
7. GitHub Support has confirmed the PR refs are purged.

## Exclusions

- The setup console, roster, guided model and Discord steps
  (`20261111-self-host-setup.md` Phases 2–7).
- Project visibility scopes beyond items 1.9 (`20261112-project-scoping-and-visibility.md`).
- SSO / SAML / campus identity providers.
- A third-party penetration test. Worth doing before a large deployment, not
  before publishing.

## Open questions

- **Commit author email.** All 1,005 commits carry the maintainer's work
  address. Keep it, or remap it to the GitHub noreply address during the
  rewrite?
- **The real lab's name** in experiment data. Keep or pseudonymise?
- **Guest defaults for Mylo in Discord.** Is "no member list for people without
  a Mycelium account" the right default, or should guests see nothing until a
  lab opts in?
- **Legacy `LabInvitation`.** Retire it in favour of `OrgInvite`, or keep it
  gated on a proved address?
- **New publication date.** Set once Phase 0 lands and the size of Phases 1–4
  is clearer.
