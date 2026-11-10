# Public Demo (`/demo`) — Implementation Plan

**Status:** proposed, not started.
**Correlation ID:** `20261110-public-demo`

## Objective

Anyone who opens `/demo` sees Mycelium working: a fictional department, lab and
people, ranked every night against the **real** corpus and opportunity feeds,
in the **same** app the signed-in product uses, and may ask Mylo **one**
question. The operator switches it on or off in `mycelium.toml`. When the app's
UI changes, the demo has the change on the next rebuild without anyone
touching it.

## The design in one paragraph

The demo is not a second frontend and not a copy of the backend. `/demo/*` is
the existing Next.js route tree under `/app/*`, reached by a rewrite; its
browser calls go to `/api/demo/*`, which a Django middleware maps onto the
ordinary `/api/*` views with `request.user` set to a seeded demo person. The
middleware is **deny by default**: every unsafe method is refused except an
allowlist (asking Mylo). The data is real because the demo people are ordinary
users with watch topics, so the nightly run ranks and writes up for them like
anyone else. Parity is therefore structural: there is one set of pages, one set
of views, one ranking path.

```
browser /demo/grants?ws=demo-lab
  └─ Next proxy.ts: rewrite → /app/grants, header x-mycelium-demo: 1
       └─ same page + components; getPublicApiBase() → /api/demo
            └─ nginx /api/ (unchanged) → Django
                 └─ DemoMiddleware: 404 if off · path /api/demo/x → /api/x
                      · request.user = demo viewer · refuse unsafe methods
                      except the Mylo allowlist · tag request.demo
                        └─ the ordinary view, the ordinary permission checks
```

## Decisions (defaults; change them here before building)

1. **URL shape: the demo lives under `/demo/*`.** The alternative — log the
   visitor in as a demo user and send them into `/app/*` — would replace a real
   user's session and make `/app` mean two things. Under `/demo` a signed-in
   person keeps their own session untouched in another tab, and the banner and
   refusals can key off the path.
2. **Stateless demo identity.** The visitor never gets a Django login. The
   middleware sets `request.user` per request; the visitor's real session cookie,
   if any, is ignored on `/api/demo/*`. Nothing the demo does can sign anyone
   in, out, or as someone else.
3. **One viewer persona: the lab's PI**, who is also a member of the demo
   department. That reaches every surface — personal, lab, department — from one
   identity. A persona picker (PI / student) is a later addition, not v1.
4. **Read-only, refused at the API, not hidden in the UI.** Save, ignore,
   remind, edit buttons stay visible (it is the same UI) and a refusal shows one
   toast: "This is a demo — sign up to do this." Hiding controls per component
   would fork the UI, which is exactly what this design avoids.
5. **One question per visitor**, enforced three ways (signed visitor cookie, an
   IP-hash daily cap, and an instance-wide daily cap that bounds the model bill).
6. **Demo data is real data, fictional people.** Names, institution and
   projects are invented; their interest themes are realistic so the real
   corpus ranks against them. Emails are under `@showcase.mycelium.invalid`
   (RFC 2606, cannot deliver). There is already a `seed_demo` command that
   makes hundreds of synthetic org-chart users under `@demo.mycelium.test`; this
   is a different thing and uses a different name and domain so neither
   command's teardown touches the other's rows.

## Phases

### Phase 1 — Configuration and the switch

- Add a `[demo]` section in `web/backend/config/instance.py` (keys, help text,
  profile defaults) and `mycelium.example.toml`:

  | Key | Default | Meaning |
  |---|---|---|
  | `demo.enabled` | `false` | Serve `/demo` and `/api/demo/*`. Off ⇒ both 404 and the landing link is hidden. Data is kept, so turning it back on is instant. |
  | `demo.questions_per_visitor` | `1` | Mylo questions one visitor (signed cookie) may ask. |
  | `demo.questions_per_ip_per_day` | `3` | Backstop for a cleared cookie. |
  | `demo.questions_per_day` | `100` | Instance-wide; bounds the model bill. `0` turns Mylo off in the demo but keeps the rest. |
  | `demo.question_max_chars` | `500` | Longest question accepted. |
  | `demo.refresh_nightly` | `true` | Rank the demo targets in the nightly run. Off saves model calls; the demo then shows its last run's data. |

- `GET /api/demo/status/` (public, no auth): `{enabled, questions_left,
  questions_today_left}`. Read by the `/demo` entry page, the landing link and
  the banner.
- Document the section in `docs/configuration.md` and the operator steps in
  `docs/skills/configure.md` ("show a public demo").
- Validate: `uv run --project web/backend pytest web/backend/apps/core/test_instance_config.py`.

### Phase 2 — The demo world (`apps/demo`)

- New Django app `web/backend/apps/demo/` with model `DemoWorld` (singleton:
  viewer user, department, lab, `built_at`, fixture version) and
  `Profile.is_demo` (indexed boolean) so exclusion filters are one `filter()`.
- `web/backend/apps/demo/world.yaml`, committed and hand-editable: one
  department, one lab inside it, ~5 people with titles, v2 interest clusters
  (`apps/accounts/interests.py` contract), two or three projects, and the
  lab profile. Written directly in the contract, not synthesised, so a build is
  reproducible and costs no model calls.
- `manage.py demo build|refresh|delete|status`:
  - `build` creates the world from the fixture (users active, email-verified,
    onboarded, with `WatchPreference` rows — without those the nightly does not
    see them), assigns a plan through the normal path if billing is on, and
    runs the on-demand refit for each target so the feeds and a first briefing
    exist immediately rather than the next morning.
  - `refresh` re-applies the fixture after edits; `delete` removes exactly the
    `DemoWorld` rows (by FK, plus the domain as a second check).
  - Wrapped as `make demo-build` / `make demo-delete`.
- Keep the demo out of everything instance-wide, through one helper
  `apps/demo/scope.py:exclude_demo(qs)`, applied where the instance looks across
  people: collaborator search and its exposure caps (`apps/collab`), the staff
  admin roster and counts (`apps/adminpanel`), billing seat totals, member-fit
  candidates outside the demo lab, ambient/listening, Discord delivery and the
  outbox, email sends, and the nightly when `demo.refresh_nightly` is off.
  Grep for every queryset that lists users or labs across orgs and decide each
  one in the PR description.
- Validate: `uv run --project web/backend pytest web/backend/apps/demo`.

### Phase 3 — The API door (`DemoMiddleware`)

In `web/backend/apps/demo/middleware.py`, placed after
`AuthenticationMiddleware` in `config/settings.py`:

- Only acts on `/api/demo/`. If `demo.enabled` is off or no `DemoWorld`
  exists → 404 (not 403: an off demo should not advertise itself).
- Rewrites `request.path_info` from `/api/demo/<rest>` to `/api/<rest>`, so
  URL resolution reaches the ordinary view. Sets `request.user` to the viewer
  and `request.demo = DemoContext(visitor_id, ip_hash)`.
- **Deny by default.** `GET`/`HEAD`/`OPTIONS` pass. Every other method is
  refused with `403 {"code": "demo_read_only"}` unless its resolved URL name is
  in `DEMO_WRITE_ALLOWLIST`: agent `threads` (create), `messages` (post),
  `cancel`. The status endpoint and nothing else is reachable without the
  rewrite.
- Always refuse `auth/login`, `auth/logout`, password, email, invitation and
  billing-checkout routes, whatever the method.
- Issues the signed, HttpOnly, `SameSite=Lax` visitor cookie
  (`mycelium_demo_v`, path `/api/demo/`) and a CSRF cookie on first contact, so
  the one allowed POST passes CSRF like any other.
- Audit: one `AuditEvent` per demo question (visitor hash, IP hash, thread id),
  none for reads.
- **Side-effecting GETs:** before shipping, list every GET view that writes
  (marks notifications read, records a view, creates a briefing on demand) and
  either make it a no-op under `request.demo` or add it to a refuse list. A test
  pins the list.
- `/api/demo/auth/me/` adds `"demo": {"questions_left": n}` to the user payload
  so the frontend has one place to learn it is in the demo.
- Validate: middleware tests below.

### Phase 4 — Mylo's one question (`tools/agent`)

- `AgentThread.demo_visitor` (nullable, indexed). Under `request.demo`,
  `ThreadsView` creates threads tagged with the visitor, and list / detail /
  events / stream / export filter by it — so a visitor sees only their own
  question, never another visitor's, though all of them "are" the same PI.
- The budget check lives in the agent's door, not the middleware, because it
  needs the turn: before enqueueing, atomically take one from the visitor,
  IP-day and instance-day counters (Redis `INCR` with expiry; the turn is
  refunded if it fails before the model is called). Out of budget →
  `may_chat` returns a new code `demo_question_used` (or
  `demo_closed_today`), which `availability.ts` and the state map in
  `components/portal/mylo/chat-panel.tsx` render as "Sign up to keep asking
  Mylo" → `/signup`.
- A demo turn is **read mode only** (risk layer), `max_risk = read`, no
  `external` functions, the caller's audience no wider than the demo lab.
  These are existing layers of `tools/agent/permissions.py`; the demo sets
  them, it does not add a tenth.
- No learning from visitors: skip `memory_after`, the learning pass, recall
  writes and the ambient `agent_chat` adapter for threads with
  `demo_visitor`. Otherwise strangers' questions would drift the demo PI's
  profile, and a hostile one could plant text there.
- Demo threads are deleted after 24 h by the existing `retention_sweep` in
  `tools/agent/tasks.py` (a `demo_visitor IS NOT NULL` branch).
- Validate: `uv run --project web/backend pytest tools/agent` plus the demo
  agent tests below.

### Phase 5 — The frontend: same pages, demo-aware plumbing

Only plumbing changes; no page or section component is forked.

- `web/app/src/proxy.ts` (new; Next 16 names it `proxy`, not `middleware`): `/demo` → the entry page;
  `/demo/:path*` → rewrite to `/app/:path*` with request header
  `x-mycelium-demo: 1`. `/demo` with the demo off → 404.
- `web/app/src/app/demo/page.tsx`: a short entry ("A fictional lab, real
  papers and opportunities, ranked last night") that sends the visitor to
  `/demo/overview?ws=<demo-lab-slug>`.
- `lib/api-url.ts`: `getPublicApiBase()` returns `/api/demo` when the page is
  under `/demo`; `getServerApiBase()` does the same when the request carries
  `x-mycelium-demo`. Every browser call already goes through it (`client.ts`,
  `mutations.ts`, `agent/`, `ambient/`, `collab/`, `auth-client.ts`).
- `lib/auth-server.ts`: in demo, `getCurrentUser()` reads `/api/demo/auth/me/`
  and `requireOnboardedUser()` redirects nowhere (the viewer is onboarded).
- **Links.** About 70 literals hard-code `/app/…` (`SECTION_ROUTES`,
  `projectRoute`, `router.push`, `href`, `window.location`). Add
  `appPath(path)` in `lib/portal/routes.ts`, which returns `/demo/…` in the demo,
  and move every literal onto it in one codemod commit. Then an ESLint
  `no-restricted-syntax` rule bans a string or template literal starting with
  `/app/` or `/api/` outside `routes.ts` and `api-url.ts`. **This rule is what
  makes parity automatic**: a new page or link written the ordinary way either
  works in the demo or fails lint.
- `components/portal/demo-banner.tsx`, mounted once in `workspace-shell.tsx`
  when `user.demo` is set: "Demo · a fictional lab on real data · Sign up".
- One handler for `demo_read_only` in the shared error path of `mutations.ts`
  (and `useCardUndo`) shows the demo toast instead of an error.
- nginx `web/infra/nginx/default.conf`: one `location /demo` block to
  `web:3000` (like `/login`). `/api/demo/` is already covered by `location /api/`.
- Landing (`web/landing`): a "See it working" link in `HomeHero` and
  `FinalCta`, rendered hidden and revealed by a few lines in the existing inline
  script after `GET /api/demo/status/` reports `enabled`. That keeps the toggle
  live without rebuilding the static site and ships no framework JS.
- Validate: `npm test` and `npm run lint` in `web/app`; `npm run build` in
  `web/landing` (in its container — see the root-owned cache note).

### Phase 6 — Nightly, cost, and freshness

- Nothing to build if `demo.refresh_nightly` is on: the demo targets are
  ordinary targets. Confirm in `ops/nightly/manual_all.py` that they are
  ranked and written up, and that carry-forward keeps their nightly model cost
  to the items that entered their Top-25 (the usual rule).
- When off, the nightly skips targets in `DemoWorld` via `exclude_demo`, and
  the demo shows its last run.
- `make tools-plan` and one manual run with the demo built, checking the demo
  lab gets a briefing and its feeds move.

### Phase 7 — Docs

- `docs/repo-map.md`: rows for `apps/demo`, `web/app/src/proxy.ts`,
  `app/demo/`, `appPath`, the banner, the nginx block.
- `docs/architecture.md`: the demo door (rewrite + middleware, deny by
  default) and why it cannot fork from the app.
- `docs/api-contract.md`: `/api/demo/*`, `demo_read_only`,
  `demo_question_used`, the `demo` block on `/me`.
- `docs/configuration.md`, `docs/skills/configure.md`: the `[demo]` keys.
- `docs/changelog.md`; delete this plan when it ships.

## Tests that carry the safety

Backend (`web/backend/apps/demo/tests/`):

- **The deny-by-default sweep.** Iterate every URL pattern Django resolves and
  every unsafe method; assert each is refused under `/api/demo/` unless
  allowlisted. A future endpoint is refused in the demo automatically; adding
  one to the allowlist is a deliberate, reviewed change.
- The demo is 404 when `demo.enabled` is off, and when on with no world built.
- A real session cookie sent to `/api/demo/*` is ignored: the response is the
  demo viewer's, and the real session is not modified.
- The viewer sees only the demo department, lab and people; a non-demo lab's
  slug in `?ws=` and a non-demo item id both fail the ordinary object checks.
- Visitors A and B: B cannot list, read, stream or export A's thread.
- Budget: the second question from a visitor is refused; the IP-day and
  instance-day caps refuse once reached; a turn that fails before the model
  call refunds its count.
- A demo turn writes no memory, recall, learning or ambient rows.
- `exclude_demo`: demo people never appear in collaborator search, the admin
  roster, seat counts, or another lab's member fit.
- `demo delete` removes the world and nothing else (a `seed_demo` user and a
  real user survive).

Frontend: vitest for `appPath` and `getPublicApiBase` in both modes; the lint
rule over the tree. End to end on the running stack: `/demo` → overview →
each feed → a project → the lab and department views → ask one question →
second question shows the sign-up state → a Save shows the demo toast → turn
`demo.enabled` off → `/demo` and `/api/demo/status/` 404.

## Security and data notes

- The demo gives the internet an unauthenticated read path onto the API. The
  middleware plus the ordinary object permissions bound what it reads to the
  demo world and the shared corpus; the sweep test bounds what it writes to the
  allowlist. Review both in the PR, and include the demo in the end-to-end
  permission review listed under "Operational hardening" in `goals.md`.
- Mylo in the demo answers a stranger with the full corpus behind it. Prompt
  injection can only reach what the demo PI can see, which is fictional.
- Put the demo routes behind the same rate limits as other anonymous
  endpoints (a DRF throttle scope `demo` on the API, e.g. 600/hour per IP).
- Entitlements: if billing is on, `demo build` gives the demo lab a plan that
  includes `agent`, through `billing.entitlements` like any lab; nothing reads
  entitlements around it.

## Exclusions (v1)

- Simulated writes (saves, reminders, ignores that "work" for the visitor only).
- A persona picker, or a demo per lab type.
- Discord, Slack and email in the demo.
- A CAPTCHA on the question; add Turnstile only if the caps prove too weak.
- Live editing of the demo world from the app; the fixture is the source.

## Open questions

- Which field should the demo lab be in? It decides how good the demo looks
  (a field the corpus covers densely is the right choice). The fixture makes it
  a one-file change.
- Should a signed-in user visiting `/demo` see a "back to my workspace" link?
  Cheap to add in the banner.
