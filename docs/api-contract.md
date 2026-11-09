# Mycelium API Contract

Committed shapes for frontend consumers.

**Conventions**

- Session authentication with Django session cookies plus a CSRF token. Never
  store credentials in browser storage. Cookies are namespaced
  (`mycelium_sessionid` / `mycelium_csrftoken`) so a co-hosted localhost app
  cannot collide with them.
- Almost every route is registered **both** with and without a trailing slash.
  The Next.js `/api` proxy strips the trailing slash and Django's `APPEND_SLASH`
  cannot redirect an unsafe method, so a POST must resolve either way. Add both
  forms for any new POST-able route.
- Every endpoint requires an authenticated session unless stated otherwise.
  Anonymous callers get `401`; authorized-but-forbidden callers get `403`.
- Reads return the signed-in user's own data unless the path names a lab,
  department, or project the caller may access.

---

## Route index

Everything mounted under `/api/`. One line each; detailed shapes follow for the
routes clients depend on most.

### Auth & profile — `/api/auth/`

| Route | Methods | Purpose |
|---|---|---|
| `csrf/` | GET | Ensure the CSRF cookie is set |
| `login/` `logout/` `me/` | POST / POST / GET | Session lifecycle + current user |
| `signup-policy/` | GET | The instance's sign-up mode, whether it verifies email, allowed domains |
| `register/` | POST | Create one solo account (per the sign-up mode, or an invite token) |
| `account/` | GET, PATCH | Name, affiliation, career stage, verification state |
| `email/verify/` `email/resend/` | POST | Submit a six-digit code; ask for a new one |
| `email/change/` | POST | Start a move to a new address (code to the new one) |
| `email/check/` | POST | Whether an address is free (invite-code gated) |
| `password/change/request/` | POST | Mail a code authorising a password change |
| `password/change/` | POST | Spend that code on a new password |
| `password/reset/` | POST | Mail a reset link; answers the same either way |
| `password/reset/verify/` | POST | Whether a link is still live |
| `password/reset/confirm/` | POST | Spend a link on a new password |
| `profile/me/` | GET, PATCH | The caller's own profile |
| `watch/me/` | GET, PATCH | What Mylo watches for the caller |
| `departments/` | GET, POST | The caller's departments; create one (verified only) |
| `labs/<slug>/invites/` `departments/<id>/invites/` | GET, POST | Join invitations: list, create a share link, or email one or up to 15 people |
| `…/invites/<id>/revoke/` | POST | Withdraw a join invitation |
| `invites/<token>/` | GET | **Anonymous** preview of a join link; `410` when dead |
| `invites/<token>/accept/` | POST | Spend a join link and join the org |
| `intake/import/` | POST | Author draft from one publication source |
| `intake/synthesize/` | POST | LLM-built interest profile from a source and/or résumé |
| `intake/session/` | POST | One step of the bounded intake loop |
| `intake/clusters/` | POST | Propose / sort / instruct interest clusters |
| `intake/confirm/` | POST | Validate + save interests |
| `labs/` | GET, POST | The caller's lab memberships; create a lab |
| `labs/<slug>/profile/` | GET, PATCH | Lab interest profile, plus `institution_type` (`higher_ed` \| `nonprofit` \| `government` \| `company` \| `""`) and `country` (two-letter code, upper-cased; 400 otherwise). The department profile takes the same two fields |
| `labs/<slug>/watch/` | GET, PATCH | Lab watch preference |
| `labs/<slug>/intake/synthesize/` | POST | Lab profile synthesis |
| `labs/<slug>/logo/` | GET, POST, PUT, DELETE | Lab logo, served through the API |
| `labs/<slug>/members/` | GET, POST | Roster; add a member (manager) |
| `labs/<slug>/members/<username>/` | PATCH, DELETE | Change role / remove |
| `labs/<slug>/invitations/` | GET, POST | Lab's invitations; invite someone |
| `labs/<slug>/invitations/<id>/cancel/` | POST | Withdraw an invitation |
| `invitations/` | GET | The caller's pending invitations |
| `invitations/<id>/respond/` | POST | Accept / reject / ignore |
| `departments/<id>/profile/` | GET, PATCH | Department interest profile |
| `departments/<id>/labs/` `…/labs/<slug>/` | GET, POST / DELETE | Labs under a department |
| `departments/<id>/members/` `…/members/<username>/` | GET, POST / PATCH, DELETE | Department roster |

### Recommendations & content — `/api/`

Served by the delivery tool (`tools/delivery/urls.py`), mounted at `/api/`
exactly where the old `apps.content` include was, so every path is unchanged.

| Route | Methods | Purpose |
|---|---|---|
| `daily-report/` | GET | The day's ranked paper suggestions |
| `daily-briefing/` | GET | The written personal "Mylo Report" |
| `labs/<slug>/daily-briefing/` | GET | The lab's written report |
| `briefings/` | GET | The caller's retained report history (dates + counts) |
| `briefings/<YYYY-MM-DD>/` | GET | One archived personal report |
| `labs/<slug>/briefings/` | GET | A lab's retained report history |
| `labs/<slug>/briefings/<YYYY-MM-DD>/` | GET | One archived lab report |
| `announcements/?lab=<slug>\|department=<id>` | GET | Opportunity announcements: `settings`, `can_manage`, `feature_on`, `announced` (each with `checks`, `write_up`, `interested`, `updated_on`, `dept_reasons` and a `discord` list of links), `held` (with `reason`), `closing_soon` (next 14 days, with links), and `servers` (one per binding, with `announcement_routes`). Members read (403 otherwise; 400 without a target) |
| `announcements/settings/?lab=\|department=` | GET, PUT | Announcement settings (`enabled`, the three kinds, `daily_cap` with `-1` for no limit, `default_nudge` `none\|2d\|1w\|2w\|3w\|1m\|2m`, `closing_soon_list`, `strong_match_tagging`, `save_on_interest`, `activation_seed`, `min_award`). Managers write; 400 with per-field messages. The first switch-on returns `activating: true` and queues the activation seed |
| `announcements/test/?lab=\|department=` | POST | A labelled test thread in each forum (once per forum: a department's kinds share one); `{"results": [{"guild_name", "purpose", "channel_name", "ok"}]}`. Managers only |
| `announcements/create-channels/?binding=<id>` | POST | "Create them for me" for one server binding (a category and three forums for a lab, one `dept-opportunities` forum for a department). That binding's managers only; 409 with `message` when Discord refuses |
| `announcements/department-opportunities/?department=<id>` | GET | The department's Opportunities page: `department`, `announcements_on`, and `items` — department-level slate items only, each with `reasons` (`key`, `label`, quoted `evidence`), `labs` that could lead (`name`, `why`; never people), `checks`, `announced` and a `discord` list of links. Department members read (403 otherwise; 400 without `department`) |
| `announcements/link-click/` | POST | `{thread_url, surface}` (`announced`, `closing_soon`, `card`, `search`, `dept_page`): a web link into an announcement thread was opened. Recorded as a `link_click` reaction only for a reader who can see that lab or department; always 204 so a link never waits on it |
| `opportunities/grants/` | GET | Ranked grants |
| `opportunities/conferences/` | GET | Ranked conferences |
| `opportunities/ranking-reference/` | GET | Static hover copy for conference rank badges |
| `opportunities/fellowships/` | GET | Eligibility-gated, ranked fellowships |
| `labs/<slug>/recommendations/` | GET | A lab's four feeds + counts + window counts |
| `projects/<id>/recommendations/[?digest=1]` | GET | A project's four feeds, or its short list |
| `reflections/` | GET | Mylo's pending proposals about the caller's project state |
| `reflections/<id>/action/` | POST | Accept (applies it) or reject one |
| `recommendations/window-counts/` | GET | The personal "what Mylo found" recency matrix |
| `search/` | GET | Unified query-first search over the corpus |
| `onboarding/match/` | POST | Live match for one area during onboarding |
| `opportunities/save/` | POST | Bookmark an item (personal or to a managed lab) |
| `opportunities/save/<content_id>/` | DELETE | Remove a bookmark |
| `opportunities/ignore/` | POST | Ignore an item — hide it from this reader's feeds |
| `opportunities/ignore/<content_id>/` | DELETE | Stop ignoring it |
| `opportunities/ignored/` | GET | Everything this reader ignored, with feed-parity cards |
| `saves/` | GET | Personal bookmarks with feed-parity cards |
| `labs/<slug>/saves/` | GET | A lab's shared saves |
| `deadlines/` | GET | Saved deadlines, soonest first |
| `notifications/` | GET | The header bell |
| `notifications/<id>/action/` | POST | Mark read / dismiss |
| `reminders/` | GET, POST | List / create-or-update a reminder |
| `reminders/<id>/` | PATCH, DELETE | Edit / cancel (`?purge=1` destroys) |
| `reminders/access/[?lab=<slug>]` | GET | The paid-plan + Discord gate state |
| `reminders/lab-channels/?lab=<slug>` | GET | Postable channels for the picker |
| `suggestions/` | GET | Cross-member fan-out suggestions |
| `suggestions/<id>/dismiss/` | POST | Dismiss one |

### Projects — `/api/projects/`

| Route | Methods | Purpose |
|---|---|---|
| `/` | GET, POST | Visible projects; create (plan-capped) |
| `lab/<slug>/` | GET | Every project of one lab, to browse and join |
| `<id>/` | GET, PATCH | Detail; edit name / description / status / progress / focus / watch categories / aliases |
| `<id>/archive/` | POST, DELETE | Archive / unarchive (never deletes) |
| `<id>/state/` | GET, PATCH | What the project claims, blocks on, and aims at |
| `<id>/state/confirm/` | POST | "Still true" — the date only |
| `<id>/state/extract/` | POST | Read a state **proposal** out of a document (saves nothing) |
| `<id>/join/` `<id>/leave/` | POST | Self-join / leave |
| `<id>/members/` | GET, POST | Roster; add a lab member directly |
| `<id>/members/<username>/` | DELETE | Remove a member |
| `<id>/invitations/` | GET, POST | Pending invitations; invite by username or email |
| `<id>/invitations/<iid>/cancel/` | POST | Withdraw a pending invitation |
| `project-invitations/` | GET | The caller's own pending project invitations |
| `project-invitations/<id>/respond/` | POST | Accept / reject / ignore one |
| `<id>/shares/` `<id>/feed/` | POST / GET | Share into, and read, the team feed |
| `<id>/ingest-link/` | POST | Resolve and ingest a pasted DOI / arXiv / URL |
| `<id>/items/<content_id>/seen/` | POST | Mark seen |
| `<id>/events/` | POST | Record a weighted engagement event |
| `<id>/collections/…` | GET, POST, PATCH, DELETE | Shared reading lists and their items |

### Billing — `/api/`

| Route | Methods | Purpose |
|---|---|---|
| `billing/me/` | GET | Resolved entitlements + active plans |
| `labs/<slug>/billing/` | GET | A lab plan's seat-priced state |
| `labs/<slug>/billing/activate/` | POST | Activate the lab plan |
| `departments/<id>/billing/` `…/activate/` | GET / POST | Same for a department |

### Discord — `/api/integrations/discord/`

| Route | Methods | Purpose |
|---|---|---|
| `start/` `callback/` | POST / GET | Personal OAuth link |
| `guild/start/` `guild-callback/` | POST / GET | Guild (server) install |
| `status/` `guild/status/` `health/` `probe/` | GET | Link state and reachability |
| `code/` `lab-code/` | POST | Mint a personal / lab activation code |
| `department-code/` | POST | Mint a department activation code (`?department=<id>`, department managers only) |
| `bindings/<id>/remove/` | POST | Switch one server binding off (that binding's own lab or department managers only) |
| `daily-report/` | POST | Toggle the daily PDF DM |
| `disconnect/` | POST | Unlink |

### Slack — `/api/integrations/slack/` (ambient Plan 11)

| Route | Methods | Purpose |
|---|---|---|
| `events/` | POST | Slack's Events API. Signed requests only (401 otherwise); 404 while `SLACK_ENABLED` is off |
| `interactions/` | POST | Block Kit button presses on Mylo's questions; signed |
| `install/` `oauth/callback` | GET | Install Mylo in a workspace (OAuth v2, session-bound `state`) |
| `link-code/` `lab-code/` | POST | A code a person DMs to Mylo, or a lab manager's code posted with a mention in the channel for the lab's reports (`?lab=<slug>`, managers only) |
| `status/` | GET | `{"enabled", "installable", "identities", "lab_workspace"}` (`?lab=<slug>` for a manager's view) |
| `unlink/` | POST | `{"team_id"}` |
| `listening/` | POST | A lab manager's switches: `{"on"?}` listening, `{"primary"?}` the lab's posts go to Slack |

### Teams — `/api/integrations/teams/` (ambient Plan 11)

| Route | Methods | Purpose |
|---|---|---|
| `messages/` | POST | The Bot Framework messaging endpoint. A bearer JWT verified against Microsoft's keys (issuer, audience = the app id, expiry, `serviceurl`) or 401; 404 while `TEAMS_ENABLED` is off |
| `link-code/` `lab-code/` | POST | Codes good on Teams only (a lab code needs `?lab=<slug>` and a manager) |
| `status/` | GET | `{"enabled", "identities", "lab_team"}` |
| `unlink/` | POST | `{"tenant_id"}` |
| `lab/` | POST | A lab manager's switches: `{"on"?, "primary"?}` |

### Ambient attribution — `/api/ambient/`

| Route | Methods | Purpose |
|---|---|---|
| `projects/<id>/conversation/` | GET | A project editor's view: recent attributions, heard channels, correction targets |
| `projects/<id>/channel-hints/` | POST | Point a heard channel at this project, or stop |
| `attributions/<ref_id>/correct/` | POST | "This was about a different project" |
| `suggestions/` | GET | My open questions from Mylo, strongest first (ambient Plan 06) |
| `suggestions/<id>/answer/` | POST | Answer one of my questions: `{"choice", "correction"?}`; 409 if it was already answered |
| `changes/` | GET | What changed: my changes, and lab-visible changes to projects I am on (ambient Plan 07) |
| `changes/<id>/undo/` | POST | Undo one change — never time-limited, logged as its own change; 403 if not mine (or not an editor of its lab project), 409 if already undone |
| `understanding/` | GET | What Mylo knows about me: every knowledge-core edge with its source, and the developments I may see |
| `understanding/<concept_id>/<relation>/` | PATCH, DELETE | Reword (`{"label"}`, it becomes mine) or delete one thing Mylo understood from conversation |
| `understanding/<concept_id>/<relation>/reopen/` | POST | Include a declined or faded topic after all |
| `settings/` | GET, PUT | Listening on Discord (and on Slack and Teams, `listening_slack` / `listening_teams`, once linked), Mylo's questions on/off, a quiet period; a free plan (under subscriptions) may turn things off only. GET also says whether transcripts are on |
| `observations/delete/` | POST | `{"confirm": true}` — delete every summary and everything derived from them |
| `projects/<id>/developments/` | GET | A project's development timeline, for anyone who can see the project; private ones for their speaker only |
| `labs/<slug>/changes/` | GET | A lab's "What changed": lab-visible changes to its shared projects; members only |
| `transcripts/` | POST | A meeting transcript (Plan 11): multipart `file` or `text`, `title`, `project` or `lab`. Without `speakers`, nothing is read: returns `{"labels", "members"}`. With `speakers` (JSON map label → user id) and `occurred_at`: reads the turns of mapped, opted-in members into the buffer, returns `{"meeting", "turns", "counts", "participants"}`. 403 while `AMBIENT_TRANSCRIPTS_ENABLED` is off or for a non-member |

### Collaboration — `/api/collab/`

| Route | Methods | Purpose |
|---|---|---|
| `settings/` | GET, PUT | The reader's own "open to collaboration" setting: `{"open", "audience": "institution" \| "country" \| "anywhere", "open_to": [...], "renew"?}`. GET adds `expires_at`, `verified`, the verified `institution` and `country`, and `allowed_audiences` (empty unless the verified email is at an institution — a personal address can be neither found nor search). 400 with `detail` on a refused choice. Never returns who searched or how often the reader appeared |
| `preview/` | GET | Exactly what a seeker would see: `{"name", "institution", "facets": {facet: [{"label", "sources"}]}}` — declared and paper-backed concepts only, never conversation or a project |
| `calls/<content_id>/slot-feedback/` | POST | Correct a call's requirement slots: `{"kind": "not_a_requirement" \| "we_cover_this", "slot_text"}` or `{"kind": "missed_one", "note"}`. Append-only; 201 |
| `search/` | GET | Whether the reader may search now: `{"available", "code": "" \| "not_enabled" \| "unverified" \| "paid_plan" \| "daily_limit", "reason", "max_scope"}` — so no surface offers a search that would only be refused |
| `search/` | POST | Find collaborators. `{"entry": "call", "content_id"}` \| `{"entry": "project", "project_id"}` \| `{"entry": "manual", "text"}`, plus optional `slots` (edited `[{"facet", "text", "required"}]`, which replace the pre-filled ones), `lanes`, `scope`, `outside_network`, `dry_run`. A dry run returns only `{"slots"}` and searches, logs and shows nothing. Otherwise `{"slots", "lanes": {lane: [hit]}, "groups": {"fills_a_gap", "shares_expertise"}, "explained", "search_id"}`; a hit is exactly `{"username", "name", "institution", "lane", "slot", "facet", "matched", "tier": "declared" \| "demonstrated", "reason"}`. Never a count of who was held back. 404 while `COLLAB_SEARCH_ENABLED` is off; 403 with `detail` on a refusal (unverified, verified at no institution, free plan while plans are enforced, the daily limit, a scope past `COLLAB_MAX_SCOPE` or past `country` — no search ever reaches past the seeker's own country — a project the reader cannot open) |
| `searches/<id>/feedback/` | POST | `{"candidate", "lane", "kind": "save" \| "not_relevant"}` on one of that search's results; 201 |
| `saved/` | GET | The reader's saved people who are still reachable: `{"people": [{"username", "name", "lane", "slots", "saved_at"}]}` — someone who has switched off drops out |
| `team/` | POST | "Assemble a team" (plan CN-07): the search input; `{"slots", "team": [{"username", "name", "institution", "covers": [{"slot", "facet", "matched", "tier"}], "distance"}], "uncovered", "search_id"}`. 403 with `code: "too_few_gaps"` under three gaps |
| `searches/<id>/introduction/<username>/` | GET | "Who can introduce me?" for someone that search showed: `{"hops", "path": [{"username", "name", "institution"}]}` through co-authors who are open to the reader, or `{"path": null}`. 404 for someone the search did not show or who is no longer reachable |

### Platform admin — `/api/admin/` (staff or superuser only)

| Route | Methods | Purpose |
|---|---|---|
| `users/` `users/<id>/` | GET / GET, PATCH | Roster; detail; assign plan + quota |
| `labs/` `labs/<slug>/` | GET / GET, PATCH | Lab roster; detail; assign plan |
| `llm/servers/` | GET | Read-only. `{default, allow_cloud, fallback, servers: [{server, label, kind, location, enabled, callable, default, model, ok, error, cached, base_url, api_key_env, has_key, models: [{id, label, context_window, capabilities, loaded}]}], routes: {"*" or component: {server, model, label, location, requested, problem}}}`. A dead server is `ok: false` with the reason, still HTTP 200. `?refresh=1` skips the discovery cache. Never carries a key, only the name of its variable |

### Tools — `/api/tools/`

| Route | Methods | Purpose |
|---|---|---|
| `tools/` | GET | Signed in. `{"tools": [{name, summary, state, core, depends_on}]}`, one per installed tool in dependency order; `state` is `LOADED`, `DISABLED`, `MISSING`, `BLOCKED` or `FAILED`. Staff also get `reason`. Served by `tools/_framework/views.py` |

### Mylo agent — `/api/tools/agent/` (tool `agent`; drawn by the web app's chat panel, `web/app/src/lib/portal/agent/`)

Session auth + CSRF; every route needs a verified email. A thread is readable
only by the person who started it — an org admin gets 404 like anyone else.
A Discord conversation in a thread or channel is a *shared* thread with no owner
(plan D): no route here lists or returns one (404). A Discord DM is the person's
own thread and is listed like a web one.
Errors are `{code, detail, fix}`. POST routes also answer without the trailing
slash; `stream/` and `events/` answer only with it, which is fine behind nginx
or the dev gateway (both send `/api` straight to Django) — through the bare
Next rewrite every slashed GET loops between Next's and Django's slash
redirects, agent routes included. The web app follows `stream/` only while a
turn runs (`until_idle=1`) and decides whether chat is available from
`catalog/` (the gate's `*` refusal row, or the web surface's 403 for an
unverified email) plus `status/`.

| Route | Methods | Purpose |
|---|---|---|
| `status/` | GET | `{model: {name, label, location}}` — `location` is `local`, `remote` or `cloud` (from the server `[llm.routes] agent` names; `label` is the server's label when the host set one, else the model name) — or `{model: null, code: "no_model", detail, fix}` when no model is configured. Every `assistant` event's payload carries the same `model` object |
| `catalog/?scope=&ref=` | GET | Every function with `allowed` and, if not, `layer`, `code`, `detail`, `fix` — the gate's own answer for this caller |
| `threads/` | GET, POST | List the caller's threads, pinned first, then most recent (`?q=` searches title, purpose and their own words; `?archived=1`; `?anchor=<kind>:<key>` keeps the threads about that object); create one in `{scope: personal\|lab\|department\|project, ref, anchor}` (lab slug, department or project id). 404 for a scope the caller cannot see. `anchor` — `{kind, key}` or `"kind:key"`, any reference kind (`item`, `project`, `lab`, `department`, …) — makes the thread about that object for good: it is reference `#1`, and every turn resolves it again for the caller (left out of the turn if they can no longer see it). 404 `anchor_not_visible` if the creator cannot see it, 400 `bad_anchor` for an unknown kind |
| `threads/<id>/` | GET, PATCH, DELETE | One thread (state, `anchor` or null, `pinned`, todos, `references`); rename, archive or pin (`{title, archived, pinned}`); delete it and its events |
| `threads/<id>/messages/` | POST | `{text, mentions: ["paper:<id>", "project:<uuid>", "file:<uuid>", …], attachments: [file ids], steer}` or multipart with `files`. 202 `{status: started\|queued\|steered}`. A mention the caller cannot see is refused (404) before the turn; 429 past `daily_turns`; 409 while Mylo waits for an answer |
| `threads/<id>/answer/` | POST | `{text}` answers Mylo's pending question and resumes; 409 when nothing is pending |
| `threads/<id>/cancel/` | POST | Stops the running turn before its next step; queued messages are dropped |
| `threads/<id>/fork/` | POST | `{seq}` → a new thread with events `1..seq` (a trailing unfinished step dropped) |
| `threads/<id>/events/?after=&view=` | GET | Stored events after a seq as `{seq, type, ts, payload}`, and the thread's state. `view=activity` (default) or `raw` (staff only, else 403 `raw_view_staff_only`) — see the activity view below |
| `threads/<id>/stream/?view=` | GET | Server-sent events: stored events after `Last-Event-ID` (or `?after=`), each with its seq as `id:`, then live events and transient deltas (no `id:`); a heartbeat comment every 15 s. `?once=1` replays and closes; `?until_idle=1` closes when the turn ends. `view` as for `events/` |
| `threads/<id>/export/?as=json\|md` | GET | The log as JSON, or a Markdown transcript with citations resolved; anything the caller can no longer see shows as unavailable |
| `refs/search/?q=&kinds=&thread=` | GET | Candidates for the `@` picker, each already visible to the caller |
| `preferences/` | GET, PATCH | `{chat_enabled, learning, discord_allowed, groups_off}`; `learning` is ambient's Mylo-chat consent (on unless turned off) |
| `policy/<lab\|department>/<slug or id>/` | GET, PATCH | The org's narrowing policy `{groups_off, discord_channels_off, max_risk, members_inform_org, discord_guests, discord_guests_ceiling, discord_guests_in_force, set}`; members read it, owners and admins change it (audited); it can never widen the instance or switch the agent on or off. `discord_guests` (`full`\|`no_people`\|`public`\|`off`) is what someone without an account is told in the org's Discord server; `discord_guests_ceiling` (the host's `[tools.agent] discord_guest_level`, `off` unless `discord_access = "public"`) is read-only, and `discord_guests_in_force` is the lower of the two |

**The activity view** (`tools/agent/activity.py`) is what a person may see of
a turn; Mylo's thinking never reaches a surface (S-9). Each message keeps the
stream envelope (`id`, `type`, `thread`, `ts`, `payload`):

- `thinking` events and thinking deltas → one `{type: "activity", payload:
  {state: "thinking"}}` per run of thinking, with no text.
- `tool_call` → `{type: "activity", payload: {state: "running", label,
  call_id, name}}`; its `tool_result` → the same with `state: "ok"` or
  `"failed"`. `label` is the function's `activity` text ("Searching the
  corpus for “cell segmentation”", "Reading “<title>”"); arguments and
  results are never sent. Both carry `ref: n` when the label names one of the
  thread's references, so a surface can open what Mylo looked at.
- `assistant` keeps `text`, `final`, `partial`, `removed`, `model`; a step
  with no text is dropped. `user` loses inlined file text. `note`s meant for
  the model are dropped.
- `usage`, `recall`, `verdict`, `compact` and transient `progress` are
  dropped; `user`, `answer`, `question`, `todos`, `error`, `state`, `note`,
  text deltas, `meter` and heartbeats pass through.

### Stored files — `/api/tools/files/` (tool `files`)

| Route | Methods | Purpose |
|---|---|---|
| `files/` | GET, POST | List visible files (`?owner_kind=&owner_id=`); upload multipart `file`, `owner_kind` (`user`\|`lab`\|`department`\|`project`), `owner_id`. 403 where the caller may not add, 413 over the size or quota limit, 400 for a refused type |
| `files/<id>/` | GET, DELETE | The row and its extraction status; soft delete (uploader, org owner/admin, project editor) — the bytes go at the next purge |
| `files/<id>/text/?offset=&limit=` | GET | Extracted text as numbered lines plus page offsets; 409 while not ready |
| `files/<id>/download/` | GET | The original, always as an attachment with `X-Content-Type-Options: nosniff` |

### Health — `/api/health/`

Unauthenticated liveness check.

---

## Auth

### `GET /api/auth/csrf/`

Ensures a CSRF cookie is set. `{ "detail": "ok" }`.

### `POST /api/auth/login/`

Request `{ "username", "password" }`. Success `200` — the user summary:

```json
{
  "id": 1, "username": "string", "email": "string",
  "name": "string", "initials": "AB",
  "is_staff": false, "is_superuser": false,
  "onboarding_completed": false
}
```

`name` is the full name when set (else the username); `initials` is its avatar
form. `onboarding_completed` is false until research interests are saved.

Errors: `400` `{ "non_field_errors": ["Enter both username and password."] }`;
`401` `{ "non_field_errors": ["Invalid username or password."] }`.

### `POST /api/auth/register/`

Creates the user and provisions a starting workspace atomically, then sets the
session.

```json
{
  "username": "string", "email": "string",
  "password": "string", "password_confirm": "string",
  "first_name": "string (optional)", "last_name": "string (optional)",
  "access_code": "string (mode \"code\", unless invite_token)",
  "invite_token": "string (optional)"
}
```

Sign-up always provisions a **personal** workspace: a user-scoped subscription
and a self-paid seat. It no longer takes `account_type` / `org_name`; labs come
from `POST /api/auth/labs/` and departments from `POST /api/auth/departments/`,
both of which require a verified account.

Who gets in follows the instance's `signup.mode` (`mycelium.toml`; read it
from `GET /api/auth/signup-policy/` → `{ "mode", "verify_email", "domains" }`):
`closed` refuses everyone (`403`, `reason: "signup_closed"`); `invite` needs an
`invite_token` (`403`, `reason: "invite_required"`); `code` needs the shared
`access_code` — a constant-time compare with a per-IP failure counter and a
one-hour shadow ban, enforced before any other validation; `domain` needs an
address at an allowed domain (`400`, `reason: "domain_required"`); `open` needs
nothing. A live `invite_token` (see **Join invitations**) is accepted in every
mode but `closed`.

When the instance verifies email (`signup.verify_email`, and always in `domain`
mode) the account is created **unverified** and a six-digit code is mailed; it
is active once answered. Otherwise it is active at once and nothing is mailed —
`is_verified` in the user summary means *active*, while the account endpoint's
`is_verified` still records whether the address itself was proved. An
`email`-kind invite redeemed by its own address proves it either way.
A redeemed invite also creates the lab or department membership, inside the same
transaction — a `400` there creates no account.

`email` must be unique. The serializer rejects a duplicate case-insensitively and
a partial unique index on `LOWER(email)` backs it, so two racing sign-ups cannot
both land.

Success `201` — the user summary; session set. `400` on field errors; `403` on
CSRF failure or a failed/locked-out access code.

### `POST /api/auth/logout/` · `GET /api/auth/me/`

`logout` returns `204`. `me` returns the user summary, `401` when anonymous.

## Account, email verification & password

Verification is **activation**. A user whose `is_verified` is false can sign in
and browse, but `POST labs/`, `POST departments/<id>/labs/`,
`PATCH labs/<slug>/profile/`, `PATCH departments/<id>/profile/` and
`POST labs/<slug>/invitations/` all answer `403` — Mycelium mails invitations to
strangers, so an account that has not answered its own inbox does not get to
originate that mail. Staff and superusers are exempt.

### `GET` / `PATCH` `/api/auth/account/`

```json
{
  "username": "string", "email": "string",
  "first_name": "string", "last_name": "string",
  "institution": "string", "institution_verified": false,
  "institution_from_email": "string", "academic_title": "researcher",
  "is_verified": false, "pending_email": ""
}
```

`institution` is **derived, never written**: the name the *verified* address's
domain resolves to in the affiliation directory (`apps/accounts/institution.py`),
`""` until the address is verified and for a personal one.
`institution_from_email` is what the current address would prove once verified.
`GET /api/auth/me/` carries the same three fields.

`PATCH` writes `first_name`, `last_name`, `academic_title` and nothing else. A
request carrying a *different* `institution` is refused with
`400 { "institution": [message], "code": "institution_from_email" }`; resending
the one held (or the one the address will prove) is a no-op. `username` is immutable (lab invitations and audit rows resolve
against it); `email` and the password each have their own endpoint because each
needs a proof this one does not ask for.

### `POST /api/auth/email/verify/` · `POST /api/auth/email/resend/`

`verify` takes `{ "code": "123456" }` and returns the account payload above.
Codes expire after 30 minutes, allow five wrong guesses, and are worth one use;
`400 { "code": [message] }` on any refusal. `resend` replaces the outstanding
code and returns `{ "detail", "email" }`, or `429` inside the 60-second cooldown.
Both endpoints settle a pending address change when one is in flight, otherwise
the sign-up confirmation.

### `POST /api/auth/email/change/`

`{ "new_email", "current_password" }` → `202 { "detail", "pending_email" }`. The
account is **not** changed here; the new address is parked until a code mailed to
it comes back through `email/verify/`.

### `POST /api/auth/email/check/`

`{ "email", "access_code" }` → `{ "email", "available" }`. Gated on the live
sign-up code because it is an account-enumeration oracle; `400` without it.

### `POST /api/auth/password/change/request/` · `POST /api/auth/password/change/`

Changing a password from inside the app takes two steps, and a signed-in session
is not authority for either. The proof is control of the account's mailbox — the
same proof `password/reset/` accepts, and the **only** one asked for. The current
password is deliberately not required: the person changing a password is often
the person who cannot remember it, and anyone who could produce it could sign out
and use the reset flow instead, so requiring it would have blocked the common
case while securing nothing.

`request/` takes an empty body → `202`, mailing a code to the account's address.
`429` inside the resend cooldown; abuse is bounded by that and the `email_verify`
throttle, as it is on the signed-out endpoint.

`change/` takes `{ "code", "new_password", "new_password_confirm" }` → `200`, or
`400` with `code` or `new_password` errors. The code is worth one use and is
looked up under its own purpose, so one issued to verify an address or settle an
email change cannot be redirected here. On success every other session for that
user dies with the old password hash; the caller's own is re-stamped so it stays
signed in.

Changing the **address** still asks for the current password (see
`email/change/`), and the asymmetry is deliberate: the mailbox is what proves a
password change, so moving the mailbox is the one move that would turn a borrowed
browser into a full takeover, and no signed-out flow offers it.

### `POST /api/auth/password/reset/`

`{ "email" }` → always `200` with the same body whether or not the address is
registered. Throttled at `password_reset`.

### `POST /api/auth/password/reset/verify/` · `POST /api/auth/password/reset/confirm/`

`verify` takes `{ "uid", "token" }` → `{ "valid": bool }`, so the page can say a
link is dead before the form. `confirm` adds `{ "password", "password_confirm" }`
→ `200`, or `400` with `token` or `password` errors. The token is Django's
`default_token_generator`, keyed on the current password hash, so it dies on use;
`PASSWORD_RESET_TIMEOUT` defaults to one hour. A successful reset also sets
`is_verified` — holding the link proves the mailbox.

## Profile & intake

### `POST /api/auth/intake/synthesize/`

Builds an editable research-interest draft from **at most one** publication
source plus an **optional** résumé. `multipart/form-data`:

| Field | Required | Notes |
|---|---|---|
| `source` | with `identifier` | `openalex`, `semantic`, `scholar`, or `orcid` |
| `identifier` | with `source` | The author id for that source |
| `resume` | optional | PDF or text, ≤ 5 MB. Parsed and discarded — never stored |

At least one of (`source` + `identifier`) or `resume` must be present. The
importer takes ~10 most-cited and ~10 most-recent works (titles, abstracts,
declared interests) plus the raw résumé text and asks the model for every
interest field at once, then runs `compose_clusters` over the same corpus so the
draft ships themed `clusters` alongside a widened `areas` union, clamped to the
caller's plan caps. A deterministic fallback keeps the endpoint contract-valid
when no model is reachable.

Success `200` — `{ "draft": {…}, "interests": {…} }`. The `interests` object is
contract-valid and ready to post to `confirm`. `400` for a missing/partial source
or an unreadable/oversize file; `502` when an upstream source fails.

### `POST /api/auth/intake/import/`

`{ "identifier", "source" }` → `{ "draft", "interests" }` from a single source.
The lighter sibling of `synthesize`.

### `POST /api/auth/intake/clusters/`

Three modes over the v2 interests contract:

- **instruct** — free-text `instruction` describing what the caller wants to
  research; Mylo composes theme clusters with concrete sub-topics.
- **propose** — group the caller's existing areas into labelled clusters.
- **sort** — route new areas into the existing clusters, keeping their ids.

Returns `{ "clusters", "areas", "watch_topics", "source" }`. The result is always
a valid partition; an LLM failure degrades to a geometric agglomerative fallback.

### `POST /api/auth/intake/session/`

One stateless step of the bounded intake loop. `{ "interests", "free_text"?,
"answer"? }` → `{ "interests", "question", "summary", "done" }`.

### `POST /api/auth/intake/confirm/`

Validates `{ "interests" }` against the contract and saves it to the caller's own
profile. `200` with the profile; `400` on contract violation.

### `GET` / `PATCH` `/api/auth/profile/me/`

Reads or updates the caller's own profile (`academic_title`, `interests`,
`eligibility`, external ids; `institution` is read-only and a differing one is
refused as on the account endpoint). Writes are **scoped to the columns
that changed** — a full-row update once let one concurrent save clobber another's
columns.

### `POST /api/auth/labs/<slug>/transfer-ownership/`

Hand a lab to another member: `{ "username": "..." }`. The caller must be the
lab's current **owner**; the target must already be a member and have a verified
email. The new owner gets `role=owner` and the PI badge (`is_lead`), the caller
drops to `admin`, and the lab keeps exactly one of each. Returns the new owner's
member row.

**Irreversible from the caller's side**, and not by a flag: an admin cannot
grant ownership (see the role rule below), so only the new owner can hand it
back. `400` if the target is not a member, is unverified, or is the caller;
`403` if the caller is not the owner. Registered with and without the trailing
slash.

### Lab roles: authority runs downward

`PATCH /api/auth/labs/<slug>/members/<username>/` and its `DELETE` obey one
rule, ranked `owner > admin > member > viewer`: an actor may only act on a
target **below** them, and may only grant a role **below** their own. So the PI
alone creates admins, the PI alone creates owners (and only through the transfer
route), and an admin can neither re-role nor remove another admin or the owner.
A refusal is `403` with `reason` `role_above_you`, and is recorded as
`lab.member.role.refused`.

### `GET` / `PATCH` `/api/auth/watch/me/`

What Mylo keeps an eye on: `{ "topics": [...], "categories": [...], "cadence":
"daily|weekly" }`. The cadence is the whole delivery rule: **daily** means a
Discord message every day, weekends included; **weekly** means Monday only.
Created on first access with defaults. `topics` and
`categories` are deduped string lists; the topic count is capped by the caller's
entitlement. An unknown cadence or non-list value returns `400`.

### `POST /api/auth/register/`

Adds `pending_invite: bool` to the created-account body: true when a live email
invitation is waiting for the address that just registered and no `invite_token`
was posted. The organisation is deliberately **not** named — nothing has proved
the caller owns that address yet — and the membership is granted when they
verify it, not here. With `SIGNUP_REQUIRE_INSTITUTION_EMAIL` on (default off),
an address that resolves to no institution is refused with `reason`
`institution_required`; an invited address is exempt.

## Workspace

### `GET /api/auth/labs/`

The caller's lab memberships, for the workspace switcher:

```json
[
  { "slug": "reyes-lab", "name": "Reyes Lab", "role": "owner", "is_lead": true,
    "department": "Biology", "has_logo": true, "logo_version": 1752719700 }
]
```

`role` is `owner | admin | member | viewer`; `is_lead` marks a PI. `logo_version`
is a cache-busting token (`null` when unset).

### `POST /api/auth/labs/`

`{ "name": "Ocean Lab" }`. The caller becomes OWNER and PI lead and a Lab
subscription + founding seat are provisioned. `201` with the membership row.
`403` unless the account is verified.

### `GET | POST /api/auth/departments/`

`GET` lists the departments the caller owns or is a direct member of — the ones
they can act on, not those they are folded into through a lab:

```json
[{ "id": "uuid", "name": "Biology", "institution": "Northgate University",
   "role": "owner", "is_owner": true, "can_manage": true }]
```

`POST { "name" }` creates one with the caller as head, a CANOPY plan that starts
**inactive**, and a pending founder seat. Its `institution` is the caller's
verified one; a differing `institution` in the body is refused with
`code: "institution_from_email"`. `403` unless the account is verified; `400` on
a blank name.

### `GET | POST | PUT | DELETE /api/auth/labs/<slug>/logo/`

Served **through the API** — there is no `MEDIA_URL` route. `GET` streams the
image to any member (`image/png|jpeg|gif|webp|svg+xml`, `nosniff`); `404` when
unset. `POST`/`PUT` take a multipart `file` (≤ 2 MB, validated by magic bytes),
restricted to lead PI / owner / admin, returning `{ "has_logo", "logo_version" }`.
`DELETE` clears it.

### `GET /api/auth/labs/<slug>/members/`

Any member may read. Leads sort first.

```json
[{ "username": "lena", "name": "Lena Reyes", "initials": "LR",
   "email": "l@uni.edu", "role": "owner", "is_lead": true }]
```

### Lab invitations

`POST /api/auth/labs/<slug>/invitations/` invites by email or username:
`{ "identifier", "role"? }`. An email with no account stays **pending** and is
claimed at signup; a username with no account is a `400`, as is an existing
member or duplicate invite. Managers only.

`GET /api/auth/invitations/` returns the caller's pending invitations;
`POST /api/auth/invitations/<id>/respond/` takes
`{ "action": "accept" | "reject" | "ignore" }`. Accept creates the membership
(idempotent). `403` if the invitation is not addressed to the caller; `409` if it
was already answered.

### Join invitations

The outward-facing invitation, for someone who may have no account. Unlike the
lab invitations above it works for departments too, and it is the only one that
sends mail.

`GET | POST /api/auth/labs/<slug>/invites/` and
`GET | POST /api/auth/departments/<id>/invites/`. Managers only (a lab's lead PI
or owner/admin; a department's owner or admin), and `POST` additionally requires
a verified account. The payload:

```json
{ "kind": "email | link", "email": "required for email", "role": "member",
  "max_uses": 25, "expires_in_days": 7, "message": "optional" }
```

An `email` invite is bound to one address and forced to one use; a `link` takes
`max_uses` (1–500, default 25) and `expires_in_days` (1–90, default 7). `role`
never resolves to `owner` — that is a transfer, not something a link confers, so
it lands as `admin`. `400` on a bad setting, an address that already belongs to a
member, or an address that already holds an open invitation to this org.

The response (and the `GET` list) carries the invitation including its `url`, so
a share link stays copyable:

```json
{ "id": "uuid", "kind": "link", "role": "member", "email": "", "message": "",
  "url": "https://…/join/<token>", "max_uses": 25, "used_count": 0,
  "uses_left": 25, "expires_at": "…", "revoked_at": null, "is_live": true,
  "created_at": "…", "created_by": "lena" }
```

The same `POST` takes a **batch of emailed invitations** when the payload carries
`emails` instead of `email`. Up to 15 addresses (`invites.MAX_BATCH_EMAILS`),
given either as a list or as one string delimited by commas, semicolons, or
newlines. `kind`, `max_uses`, and `expires_in_days` are not read — every row is an
email invite worth one use, on the default window. `role` and `message` apply to
all of them.

```json
{ "emails": ["a@uni.edu", "b@uni.edu"], "role": "member", "message": "optional" }
```

The batch answers `201` with per-address outcomes, **including when some addresses
were refused** — partial success is the normal case, and failing the whole
submission over one typo would make batching worse than sending one at a time:

```json
{ "created": [ <invitation>, … ],
  "failed": [ { "email": "sam@uni.edu", "reason": "already_member",
                "detail": "That person is already a member of this lab." } ],
  "requested": 2 }
```

`reason` is one of `already_member`, `already_invited` (a live, unspent
invitation to that address for this org already exists), `invalid_email`, or
`duplicate` (repeated within this submission). `400`, creating nothing, only when
the submission itself is wrong: no addresses, or more than 15.

An invitation created in a batch is the same object as one sent singly — bound to
its address, one use, activating the account that redeems it.

`POST /api/auth/labs/<slug>/invites/<id>/revoke/` and
`POST /api/auth/departments/<id>/invites/<invite_id>/revoke/` withdraw one,
returning the updated row. Idempotent.

`GET /api/auth/invites/<token>/` is **anonymous** — the recipient may have no
account — and returns what the join page shows: `org_kind`, `org_name`, `role`,
`kind`, `email` (the bound address, blank for a link), `message`, `invited_by`,
`expires_at`, plus `signed_in_as` and `email_matches` when the caller is signed
in. A dead link answers `410` with a `reason` of `invalid | revoked | expired |
exhausted`.

`POST /api/auth/invites/<token>/accept/` spends it as the signed-in caller and
returns `{ org_kind, org_name, slug, department_id, role }`. Membership goes
through the seat-syncing services, so a roster at its tier ceiling refuses the
whole redemption. Idempotent per person: following your own link twice keeps one
membership and spends one use. Deliberately **not** behind the verified-email
gate — that guards standing an org up, not being brought into one. `400` with a
`reason` (adding `wrong_email`) when it cannot be spent.

## Projects

### `GET /api/projects/[?lab=<slug>]`

Projects the caller may see under the org visibility cascade
(`Project.objects.visible_to`). `lab` narrows and never widens.

```json
[{ "id": "uuid", "name": "Drought study", "scope": "lab",
   "scope_name": "Reyes Lab", "scope_slug": "reyes-lab", "goals": {},
   "description": "…", "status": "Active", "progress": 40,
   "focus": { "clusters": [] },
   "watch_categories": ["papers"], "is_archived": false, "is_over_cap": false,
   "can_edit": true, "can_manage_members": true,
   "member_count": 3, "members": [{ "username", "name", "initials" }],
   "updated_at": "…" }]
```

`scope` is `user | lab | department`; `scope_slug` is the owning lab's slug and is
`null` for a personal or department project. `description`, `status`, and
`progress` are optional display fields read out of `goals` — `description` falls
back to the composed focus statement — and are `null` when unset. `can_edit` /
`can_manage_members` report the caller's rights on the row (the personal owner, or
a lab owner/admin/PI) so a client never has to infer them from the active
workspace. `is_over_cap` marks a project sitting above the plan's allowance after
a downgrade.

### `PATCH /api/projects/<id>/`

`{ "name"?, "description"?, "status"?, "progress"?, "focus"?, "watch_categories"?, "aliases"? }`
— editors only. `aliases` is a list of other names people use for the project in
conversation, read by ambient attribution: each 3–60 characters, at most 20,
duplicates collapse ignoring case, and one equal to the project's own name is
dropped. It is returned on every project row. An empty string (or `null` for `progress`) clears a display field
rather than storing a blank. A whole-corpus re-seed is triggered only when the
patch actually changes what the project searches on (its focus, watch topics, or
tracked areas); a rename or a status change does not buy one.

### Ambient attribution — `/api/ambient/`

Which project a lab conversation was about, for the people who can correct it.
Nothing here ever returns message text — none is kept.

**`GET projects/<id>/conversation/`** — project editors only (403 otherwise).

```json
{
  "scope": "lab",
  "listening": true,
  "channels": [{"place_id": "…", "label": "methods",
                "hinted_project": {"id": "…", "name": "…"} | null}],
  "hinted_channels": ["…"],
  "attributions": [{"id": 12, "sent_at": "…", "place_kind": "channel",
                    "place_label": "methods",
                    "speaker": {"id": 4, "name": "Ada Lovelace"},
                    "confidence": 0.82, "decided_by": "resolved",
                    "matched": ["IMG-seg"], "corrected": false}],
  "alternatives": [{"id": "…", "name": "Annotation study"}]
}
```

A lab project lists lab-channel messages from its own lab's server attributed to
it — never a DM and never another lab's server. A personal project lists only its
owner's own messages. `matched` is the project's vocabulary that matched (an
alias, a dataset name), never the person's words. `channels` are those Mylo has
heard in the lab's server, minus excluded ones; the 50 newest attributions are
returned.

**`POST projects/<id>/channel-hints/`** `{ "place_id", "on"? }` — editors of a lab
project. A hint raises that project's score in the channel and never decides on
its own; a channel hints one project, so pointing it here moves it. 400 when the
lab's server is not listening or the channel has never been heard.

**`POST attributions/<ref_id>/correct/`** `{ "project": <id> | null }` — the
message's own speaker, or an editor of the lab project it is filed under.
`null` means "not about a project". The target must be a project of the same
lab, or — for the speaker alone — their own personal project or a lab project
they are on. The reference is fixed with confidence 1.0, any observation resting
on it is updated and gets a `corrected` feedback row, and an append-only
correction records every signal's score as a labelled example. Returns
`{ "id", "project", "observations_updated" }`; 403 when not permitted.

**`GET suggestions/`** — the signed-in person's own open questions (ambient Plan
06). Never anybody else's.

```json
{"suggestions": [{"id": 7, "kind": "interest", "topic": "conformal prediction",
  "question": "You brought up … Shall I start looking for **conformal prediction** …",
  "explanation": "…", "choices": [{"key": "reports", "label": "Include it in my reports"}, …],
  "project": null | {"id": "…", "name": "…"}, "state": "pending" | "asked",
  "asked_at": "…" | null, "expires_at": "…"}]}
```

`kind` is `interest`, `skill`, `development`, `intent`, `clarify` or `review`.
`choices` holds only what exists for this person today (a new theme only with a
free slot; project choices only for their own projects).

**`GET changes/`** — `{"changes": [{"id", "kind", "kind_label", "topic",
"project": null | {"id", "name"}, "field", "old_value", "new_value", "surface":
"dm" | "web" | "told" | "", "explanation", "visibility": "personal" | "lab", "by":
{"id", "name", "you"}, "created_at", "undone_at", "undo_of", "can_undo"}]}`, newest
first. `kind` is one of `exploration_confirmed`, `exploration_kept`,
`exploration_dropped`, `understanding_confirmed`, `development_recorded`,
`development_confirmed`, `profile_edit`, `state_edit`, `undone`. A change one
member made privately is never in anybody else's list, nor in a lab's.

**`GET understanding/`** — `{"statement", "edges": [{"concept_id", "label",
"facet", "relation", "tier": "declared" | "demonstrated" | "conversational",
"status", "kind", "source": "You wrote this" | "Your papers show this" | "From
conversation", "first_seen", "last_reinforced", "review_on", "edited",
"editable", "eligible_again_on"?, "resting"?}], "developments": [...]}`. Only the
signed-in person's own edges; `editable` only for conversational ones.

**`GET/PUT settings/`** — `{"available", "paid", "linked", "listening":
{"discord"}, "questions_muted", "quiet_until", "statement", "observations"}`; PUT
takes any of `listening_discord`, `questions_muted`, `quiet_until`
(`YYYY-MM-DD` or null). Turning questions off withdraws open questions at once.

**`POST suggestions/<id>/answer/`** `{ "choice", "correction"? }` — the question's
own person only (404 otherwise). `choice` must be one of the offered keys (400
otherwise). A `correction` with a yes-like choice records the person's own
wording. The first answer wins across Discord and the web: a second answer gets
`409` and `{ "taken": false, "message": "That one's already answered on …" }`.
On success `{ "taken": true, "message": <what Mylo says back>, "suggestion": … }`.

### Project members and invitations

`POST <id>/members/` adds one of the owning **lab's** own members directly — no
invitation, because that person can already see the lab's work. Everyone else is
invited: `POST <id>/invitations/` takes `{ "identifier", "message"? }` where the
identifier is an existing account's username or email (project invitations do not
create accounts — that stays the lab invite path). Accepting creates a
`ProjectMember` row and nothing else, so an invited outside collaborator gains
that one project's feed, collections, and recommendations and no other part of the
lab. Both halves are gated on the same edit right as `PATCH`, and every write is
audit-logged.

### `POST /api/projects/`

`{ "name", "labSlug"?, "departmentId"?, "focus"? }`. Scope resolves to personal,
lab, or department; lab/department creation needs both the org's plan and PI or
admin rights. The per-scope **project cap** is enforced atomically (row-locked
count-then-create) and a breach returns `403`. `focus` accepts a Mylo-composed
cluster payload. On create the project is seeded over the existing corpus in the
background.

### `GET | PATCH /api/projects/<id>/state/`

A project's state: what it claims, what is blocking it, and what is due when.
Read by anyone who can see the project, written by its editors. This is the most
sensitive payload the API serves — unpublished research plans and what is not
working — so both gates are object-level, not scope-level.

```json
{
  "project_id": "…",
  "slow": {
    "problem": "Whether multi-hop QA benchmarks detect KG quality at all",
    "claimed_contribution": "A measurement-validity study",
    "method": ["multi-lens LLM extraction"], "planned_components": [],
    "data": ["MuSiQue"],
    "blockers": [{ "id": "b1", "text": "No labeled evaluation set" }]
  },
  "fast": {
    "stage": "experiments",
    "milestones": [{ "id": "m1", "kind": "results_by", "what": "MuSiQue pilot",
                     "date": "2026-10-09", "source": "stated" }],
    "venue_targets": [{ "venue": "TMLR", "slot": "", "fallback": "" }],
    "constraints": [], "exclusions": [],
    "timeline_overrides": { "deadline_buffer_days": 21,
                            "min_paper_window_days": null },
    "needs": { "expertise": [] },
    "known_literature": { "collections": [], "suppress_known": true }
  },
  "provenance": { "problem": "stated", "method": "inferred" },
  "state_version": 3, "slow_fingerprint": "…",
  "confirmed_at": "2026-09-14", "days_since_confirmed": 0, "is_empty": false,
  "effective_timeline": { "buffer_days": 21, "window_days": 60,
                          "buffer_source": "project", "window_source": "you" }
}
```

The split is load-bearing. **`slow`** is the research identity, and Mylo's written
reasoning about the project is keyed on a hash of it, so changing the claimed
contribution invalidates those write-ups and moving a milestone does not.
**`fast`** is operational and is read by deterministic matchers that cost nothing
to re-run.

`provenance` marks each populated field `stated` or `inferred`. A `stated` field
is never edited by anything but a person. An unrecorded field reads as `stated`,
because the only ways in without provenance are a hand edit and a migration.

PATCH is a **merge**, not a replace: send only the half or the field that
changed. A PATCH also sets `confirmed_at` to today — editing is confirming what
you just read — while `POST .../state/confirm/` sets only that date and leaves
`state_version` alone.

`timeline_overrides` uses `null` for **inherit**, which is why an out-of-range
number is stored as `null` rather than clamped: clamping would turn a typo into a
setting. `effective_timeline` reports what is actually in force for the calling
reader, resolved project → reader → lab → 14/60, with each half's source named so
a reader who disagrees with a verdict knows which dial to turn.

`is_empty` is true when nobody has answered yet, which a client should render as
a prompt rather than as a blank document.

### `POST /api/projects/<id>/state/extract/`

Multipart `file` (PDF or text) or JSON `text`. Reads the document and returns
`{ ok, reason, attempts, failures, proposal }` — and **saves nothing**. Every
field in `proposal` is marked `inferred`; applying it is a separate PATCH the
reader triggers, because an extractor that wrote directly would overwrite what
the team stated with what a model read.

`ok: false` is a real and common outcome. Every extracted claim is checked against
the document — a word-overlap floor for a claim long enough to carry one, and
"invent no numbers, dates or money" for a short one — and two ungrounded attempts
end in a refusal rather than a guess. `ok: true` with an empty proposal means the
document does not describe a project, which is a correct answer, not a failure.

### `POST | DELETE /api/projects/<id>/archive/`

Archives / unarchives. Never deletes: stored recommendations survive, the slot is
freed, and the cap is re-checked on restore.

### Collaboration & collections

`shares`, `feed`, `ingest-link`, `items/<content_id>/seen`, and `events` are all
participant- and visibility-gated. `ingest-link` resolves an external DOI, arXiv
id, or URL into a `ContentItem`. `events` records a weighted engagement signal
(`settings.RELEVANCE_EVENT_WEIGHTS`) that feeds the project's team vector.
`collections/…` are shared reading lists (create, rename, archive, add/remove
items).

## Recommendations

Papers come from `GET /api/daily-report/`. Grants, conferences, and fellowships
come from the daily opportunity matching. All four are also available per lab and
per project.

### `GET /api/daily-briefing/`

The written personal "Mylo Report" — the durable `DailyBriefing` produced by the
daily run, scoped to the categories the caller watches.

```json
{
  "generated_at": "2026-07-11T13:00:00+00:00",
  "generated_on": "2026-07-11",
  "categories": ["papers", "grants", "fellowships"],
  "counts": { "papers": 25, "grants": 25, "fellowships": 40 },
  "new_counts": { "papers": 4, "grants": 1, "fellowships": 0 },
  "project_summary": [
    { "key": "personal", "label": "Personal", "kind": "personal", "scope": "",
      "counts": { "papers": 3, "grants": 1, "fellowships": 0 } },
    { "key": "…uuid…", "label": "Coral Atlas", "kind": "project", "scope": "lab",
      "counts": { "papers": 1, "grants": 0, "fellowships": 0 } }
  ],
  "showcase": {
    "papers": [{ "content_id": "…", "type": "paper", "title": "…", "url": "…",
                 "verdict": "read", "headline": "…", "deadline_date": "",
                 "is_new": false }]
  },
  "stats": {
    "discovered_papers": 2140, "discovered_opportunities": 186,
    "matched": 41, "entered": 7,
    "by_category": { "papers": [6, 128], "grants": [0, 44] },
    "by_project": [["Personal", 3, 0], ["Coral Atlas", 1, 0]],
    "aggregate_label": "Personal",
    "by_theme": [["Agentic KG construction", 1]],
    "alerts": 0,
    "deadline_window_days": 14, "deadlines_in_window": 2,
    "nearest_deadline": { "title": "ECIR 2027 abstract", "url": "…",
                          "due_date": "2026-09-25", "days": 9, "label": "abstract" },
    "private_projects_hidden": 0
  },
  "kind": "daily",
  "briefing": { "body": "Good morning. Today's scan surfaced …", "origin": "llm" }
}
```

`origin` is `"llm"`, `"fallback"`, or `"carried"` — the last meaning nothing
entered the reader's slates that day, so the previous day's body was carried
forward verbatim rather than re-worded to reach the same conclusions.

The body is markdown organised **by research theme**: Mylo's lead paragraph, then
one `## <theme>` section per theme *that has news*, each opening with his read on
that theme, then a `###` section per category listing what entered, then a
`### Currently in your list` reference block of what is standing. A theme with a
slate but nothing new is one `**Quiet today:**` line at the end; a theme with no
matches at all does not appear. Projects follow as `## Project · <name>` parts,
flat and entrant-only — they rarely declare themes of their own, and inheriting
the parent's would attribute a project's matches to a strand it never declared.

The prose (`narrative` on the stored briefing) is a **paid layer**: an unentitled
reader gets the same sections, the same navigation and the same listings without
the lead or the theme reads. Quieter, not broken. Before the first run an honest
empty envelope is returned
(`generated_at: null`, empty `categories` / `counts` / `showcase` /
`project_summary`, `briefing: null`).

`project_summary` is the report's summary table — the reader's own row first, then
one per project, **including projects with an all-zero row** (that a project had a
quiet day is an answer). Its counts are how many items **entered** that part's
slates on the run, which is what the report announces as new. In the PDF the
reader's own row expands to one row per theme, so the table indexes the sections
beneath it.

An item enters a slate when it ranks into a **theme's** top N for its category,
having been outside that theme's slate on the previous run. Depth is per category
because the categories are different kinds of thing: papers are a *flow* (25 per
theme, a rolling window over arrivals) while grants, conferences, and fellowships
are a *stock* of currently-open calls (10, 10, and 5 — a live shortlist that
barely moves). Entry is keyed on **(theme, item)**, so the same paper entering a
second theme later is a separate entry event and is news again for that theme.

That is a fact about what the reader is being shown, not about ingestion: the
feed's "New" badge keeps its separate 7-day arrival window, and the two numbers
are deliberately different.
`counts` and `new_counts` at the envelope level still describe the feeds, which
every feed endpoint serves unchanged.

`generated_on` is the day the report covers — the history key. `generated_at` is
when it was last written, which a same-day rerun moves and `generated_on` does not.
This endpoint always serves the newest day.

`stats` is the run's own numbers, settled by the briefing stage and stored on the
row so the web header and the Discord post cannot quote different figures for the
same morning. `entered` equals the summary table's grand total by construction,
and `by_category` reads `[entered today, in the feed]`. The two `discovered_*`
figures are corpus-wide and are `null` — never `0` — when the analytics collector
could not answer, because "Mylo read nothing" and "Mylo does not know how much it
read" are different claims. Percentages, cosines and scores appear nowhere.
`stats` is `{}` on a briefing written before it existed, which a client must
render as "no numbers" rather than as zeros.

`kind` is `"daily"` or `"weekly"`. Every briefing endpoint accepts `?kind=` and
**defaults to `daily`**, so a caller that has never heard of the weekly keeps
reading exactly what it read before. Monday carries one row of each for a target,
which is why the read has to name a kind at all.

A weekly's `generated_on` is the **Monday its week starts**, not the day it was
written, so a re-run after a Monday outage re-finds that week's row rather than
adding a second copy of the week. Its `verification` carries the citation
verifier's record — `{claims, supported, removed, unresolved, removed_sentences}`
— and its body ends with a one-line footer saying the same thing. A weekly is
written from a closed evidence packet, and any sentence whose citation does not
resolve, or whose numbers the packet does not contain, is removed before the body
is stored. `verification` is `{}` on a daily, which cites nothing the model wrote
without a packet behind it.

### `GET /api/labs/<slug>/daily-briefing/`

The same envelope over the lab's aggregate matches, across all four areas. Any
member may read; the daily run writes it for entitled labs. Where an item carries
member-fit names, the prose says who it suits. `403` for a non-member.

### `GET /api/briefings/` · `GET /api/briefings/<YYYY-MM-DD>/`

Report history — one row per day, retained for `BRIEFING_RETENTION_DAYS` (90) and
swept by the daily run's `prune_briefings` stage. The index is newest-day-first and
carries **no bodies**, so it stays cheap across the whole window:

```json
[
  { "generated_on": "2026-07-11", "generated_at": "2026-07-11T13:00:00+00:00",
    "origin": "llm", "kind": "daily", "categories": ["papers", "grants"],
    "counts": { "papers": 25, "grants": 3 }, "new_counts": { "papers": 4 } }
]
```

Both routes take `?kind=daily|weekly` (default `daily`).

The detail route returns the same full envelope as `daily-briefing/` for that one
date, and `404` when the date has no report (including one aged out of retention).
A path that is not a `YYYY-MM-DD` date does not resolve, so it also `404`s. Own
history only.

Only the markdown is retained. The PDF a linked user is DM'd is an outbox
attachment and ages out with the outbox's own sweep, not with this window.

### `GET /api/labs/<slug>/briefings/` · `GET /api/labs/<slug>/briefings/<YYYY-MM-DD>/`

The same pair for a lab, readable by any member. `403` for a non-member.

### `GET /api/labs/<slug>/recommendations/` · `GET /api/projects/<id>/recommendations/`

All four areas from the target's own `RelevanceScore` rows, through the **same
serializers the personal pages use** — a lab feed is structurally identical to
its personal counterpart. The envelope adds:

- `counts` — per-area totals.
- `window_counts` — per-area today / week / month / year totals, cumulative.
- `interested` — lab members who personally matched the item.
- `recommended_for` — Mylo's read on which members it best suits: a shortlist
  computed from members' own profiles, a written reason, and (fellowships only)
  a consented eligibility flag. Mylo may drop a shortlisted member but can never
  add one; an unreachable model degrades to a stated overlap reason.

  Each row carries **two separate percentages**, never merged:
  `profile_cosine` (the item↔member-profile cosine ×100, a geometric measure that
  sits naturally in the 40–70 band) and `own_feed_percent` (the member's own
  personal-feed score, the model's 0–100 judgement). Either may be `null`. They
  are different estimators on different scales — a ~30-point gap is the expected
  steady state — so a consumer must label whichever it shows with its scope and
  must not compare or average them. Rows are ordered with the members Mylo wrote
  a rationale for first, each group sorted on its own scale.

  On a fellowship, eligibility also **subtracts**: a member the award hard-excludes
  is absent from the row entirely, whatever named them. That removal needs no
  `lab_visible` consent — it publishes nothing, unlike the `eligible` annotation.

`?digest=1` on a project returns the condensed short list (top 10 papers, 5 each
of grants / fellowships / conferences, passed-deadline conferences dropped) while
`counts` stays the full totals.

`GET /api/recommendations/window-counts/` is the personal equivalent of
`window_counts` alone.

### Provenance fields shared by every opportunity area

A matched grant, conference, or fellowship carries the same four provenance
fields. Every opportunity now comes from a public source that can be named and
attributed, so a client can always say where a row came from and under what
terms:

- `source` — which adapter produced the row, namespaced by area:
  `"grants:nsf"`, `"conf:ccf_deadlines"`, `"illinois-fellowship-finder"`. It is
  the adapter id, not a vendor: several adapters can contribute to one merged
  record, and `source_links` below is the full list.
- `license` — a short label (`"MIT"`, `"CC0-1.0"`, `"US Government Work — no
  copyright (17 U.S.C. § 105); public domain"`), never a URL. `""` when the
  source carries none.
- `license_url` — a machine-readable licence link. **Currently always `""`**:
  no adapter in the vendored collector attaches a licence URL to a field the
  mapper reads (the one adapter that fetches one — `openresearch` — stamps it
  on the raw fetch bundle, a provenance record the mapper never sees). Wired
  for the day a source publishes one; no serializer change will be needed then.
- `source_links` — `[{ "source": "nsf", "url": "https://…" }, …]`, one entry
  per contributing adapter (several adapters can merge into one record at
  dedupe time). `[]` for a fellowship, which has a single source and nothing
  to attribute.

### What a grant's or conference's `description` is

For grants and conferences (not fellowships), `description` is the **verified
model-written extraction** where one exists, and the raw source text otherwise.
Every extraction is produced under a fixed JSON schema and then checked by
deterministic code — schema and field bounds, venue identity, prose grounding
against the source, topic grounding, and a no-invented-specifics rule — with a
bounded repair loop. Output that never passes is **refused**: the record keeps
no `ai_summary`, falls back to truncated raw text so it stays retrievable and
searchable, and records why it was refused. A client therefore never receives a
confident-looking summary that no check passed — but it also cannot currently
tell the two apart from the payload, because the basis flag
(`metadata["search_text_source"]`, `"extracted"` | `"raw"`) is stored and **not
serialized**. Do not present `description` as an AI summary until that flag is
exposed.

### `GET /api/opportunities/grants/`

Ranked funding opportunities from the accumulated feed, pinned-first (a brand-new
high-fit grant floats to the top for its first week).

```json
{
  "generated_at": "2026-07-05T01:00:00+00:00",
  "items": [{
    "content_id": "uuid", "title": "…", "sponsor": "Amazon",
    "amount": "Upper: $70,000 USD", "matched_topics": "Agentic AI; Knowledge Graphs",
    "url": "https://…", "score": 1.19, "verdict": "read", "position": 1,
    "position_of": 10,
    "rank": 1, "caveat": "The cost-share level is not stated.",
    "beats": ["Why it matters to this theme.", "How to use it.", "What to take."],
    "headline": "Strong Fit", "reason": "Aligns with your agentic AI work.",
    "origin": "llm", "is_new": true, "pinned": true,
    "deadline_date": "2026-11-12", "deadline_kind": "application",
    "status_summary": "Application due 2026-11-12",
    "saved": false, "saved_labs": ["reyes-lab"],
    "addressable_deadlines": [
      { "kind": "application", "round_key": "", "round_label": "",
        "is_next": true, "due_date": "2026-11-12",
        "confidence": "confirmed", "label": "" }
    ],
    "cluster": { "id": "…", "label": "…" }, "bridge_clusters": [],
    "source": "grants:nsf",
    "license": "US Government Work — no copyright (17 U.S.C. § 105); public domain",
    "license_url": "",
    "source_links": [{ "source": "nsf", "url": "https://www.nsf.gov/…" }],
    "posted": "2015-03-02", "published_on": "2015-03-02",
    "opportunity_number": "PAR-25-144",
    "due_dates": ["2026-02-05", "2026-06-05", "2026-10-05"],
    "deadline_text": "Standard NIH cycle — see full announcement for details.",
    "dates_inferred": false, "original_deadline": "2026-02-05", "loi_date": "",
    "team_fit": {
      "covered": 1, "total": 2, "gaps": ["environmental health"],
      "roles": ["a local authority as a partner"],
      "slots": [
        { "text": "satellite remote sensing", "facet": "method", "required": true,
          "covered_by": "lab", "matched": "Remote sensing of reefs",
          "people": [{ "username": "ada", "name": "Ada Okafor" }] },
        { "text": "environmental health", "facet": "method", "required": true,
          "covered_by": null, "matched": "", "people": [] },
        { "text": "a local authority as a partner", "facet": "role",
          "required": true, "covered_by": null, "matched": "", "people": [] }
      ]
    }
  }]
}
```

`team_fit` (grants only; `null` when the call states nothing to bring) is
stored at scoring time (collaboration-network plan CN-03): the call's
requirement slots and who already covers each. `covered_by` is `"you"` on a
reader's own feed, `"lab"` on a lab or project feed — where a lab-mate is named
only on what their profile states — and `null` for a gap. A `role` is a kind of
partner, shown and never matched. Names resolve at read time.

`announcement` (lab and project feeds) is where the lab announced the item in
Discord — `{"label", "posted_at", "discord": [link…]}` — or `null`. A Discord link
is always `{"guild_id", "guild_name", "channel_id", "channel_name", "thread_url"}`;
the web renders it as the Discord logo plus `#channel`, opening in a new tab.

`usability` (every opportunity card, `null` when the view has no reader) is the
"Can we use this?" strip, computed by `tools/delivery/usability.py` from record
fields only: `{"verdict": "ok" | "warn" | "block" | "unknown", "checks": [{"key",
"status", "label", "field"}]}`. Keys: `open`, `deadline`, `feasible` (against the
deadline buffer), `applicant` and `country` (against the lab's or department's
profile `institution_type` and `country`), `award` (against an award minimum),
`eligibility` (fellowships, a count of people who may be eligible, never names) and
`team` (how many people the strip already names). A missing field gives `unknown`,
never `ok`. A personal feed carries only `open`, `deadline` and `feasible`; lab and
project feeds carry the rest.

**There is no `match_percent` anywhere in this API.** It implied a measurement
nobody made: a language model was asked to guess a similarity, and the result was
rendered beside a real embedding cosine with no way for a reader to tell which
was which. In its place:

- `verdict` — `read` / `skim` / `file` / `skip`. Model-judged on a plan that
  includes Mylo's reasoning, derived from the item's rank band within its own
  theme otherwise, so it means the same thing to every reader. `null` on an
  unscored row; `skip` is never chipped in the UI.
- `position` — place within the item's **own theme's** slate. A global position
  would compare scores that are not comparable across themes. **The app does not
  render this**, and nor does it render `verdict`: a feed interleaves themes, so
  a column of per-theme positions read as repeated and unsorted numbers, and
  Read / Skim / File said nothing a reader could act on about a conference or a
  grant. Both remain in the payload, and the report, the PDF and the digest still
  use them, so putting a display back is a frontend change and nothing more.
- `position_of` — how long that theme's slate actually ran, so a card can print
  "10th of 25" and say plainly that two adjacent positions are counts in
  different lists. It is the *realised* length, not the configured depth, so a
  theme that produced seven candidates reports 7. `null` on a row written before
  slates recorded their length; the nightly run fills it in, and
  `backfill_slate_size` recovers it for existing rows.
- `beats` — the reason's three parts: why it matters to this theme, how to use
  it, what to take from it. The printed report carries only the first.
- `caveat` — the strongest reason it might not be worth the reader's time.
  Mandatory on a model-written judgement.

`rank` remains the row's place in the surfaced feed and is unrelated to
`position`. `saved_labs` lists managed labs already holding the item.

`is_updated` marks a listing whose **source page** moved something actionable —
a deadline added, moved, or the call reopened — within the pin window. It is
never true at the same time as `is_new`: conferences and grants are largely
extracted from pages that host many events, and such a page gaining an event
leaves the old entries in place, so "the page changed" and "this arrived" are
different facts. Cosmetic drift (a re-worded title, a moved URL) does not
qualify, or every listing would be "updated" every night.
`addressable_deadlines` is **every** deadline the item can be alerted on, in
date order — one entry per *round*, not per kind. A conference routinely carries
a workshop deadline, more than one full-paper round, a camera-ready, and its own
event date, and each is separately remindable. Each entry is
`{ kind, round_key, round_label, is_next, due_date, confidence, label }`:

- `round_key` identifies the round within its item and is what a client sends
  back as `deadline_round_key` to set a reminder on that specific round. `""` is
  the single-round case — every grant and fellowship, and a conference's event
  row.
- `round_label` is the source's own free-text wording ("round 2", "workshop
  track"). 287 distinct values appear in the corpus, so print it, never switch
  on it.
- `is_next` marks the earliest future entry of its kind — what a card's headline
  deadline shows.
- `due_date` is ISO or `null` for a rolling/unknown deadline, and `confidence`
  is `"confirmed" | "anticipated" | "rolling" | "unknown"`.

A conference's `kind: "event"` entry is the conference itself rather than a
submission, so "remind me the week before it starts" has something to point at.
`generated_at` is `null` before the first run.

`published_on` is the funder's own publication date
(`metadata["published_on"]`, `""` when the source published none), distinct
from `posted`. `posted` **prefers `published_on`** and falls back to
`signals["first_seen"]` — Mycelium's own ingest date — only for a row whose
source gave no publication date. Reading `first_seen` unconditionally was the
old behaviour and it was wrong: a grant the funder posted in 2015 showed the day
Mycelium happened to collect it. Treat `posted` as "best available date", and
`published_on` as the only one that is the funder's.

`opportunity_number` is the funder's own identifier (`"PAR-25-144"`), `""` when
none was published. `due_dates` is the complete application-round array behind
the single next-due `deadline_date` — every round, oldest first, ISO dates —
what the multi-deadline hover renders in full; it can differ from
`deadline_date` on a multi-round grant where every round but the last has
already passed. `deadline_text` is the funder's own free-text deadline line,
kept verbatim alongside the parsed date. `dates_inferred` is `true` when the
collector estimated rather than read the dates verbatim. `original_deadline`
is the first-ever recorded close date, kept even after the funder moves it, so
a reader can see that a deadline shifted rather than only what it is now.
`loi_date` is the letter-of-intent date some funders require ahead of the full
application; `""` for the large majority that don't.

### `GET /api/opportunities/conferences/`

The same base shape with `location`, `country`, `event_dates`, `deadlines`,
`keywords`, `matched_subjects`, and a venue `description` where the listing has
one. Filter-rail fields computed at ingest: `event_date` (ISO, or `""`),
`abstract_open` / `manuscript_open`, `status` (`open|closed|unknown`), and a
`scope` label. `deadline_kind` is the next actionable kind
(`abstract` / `manuscript` / `event`). Continent is derived client-side from
`country`.

**A conference that is over is never returned.** Every opportunity feed —
personal, lab, and project — drops a row whose last written date has passed,
on every request rather than waiting for the nightly prune. For a conference
that also covers a listing with **no date at all** (no deadline, no event
date): there is nothing a reader could act on, and expiry can never reach it,
so it is hidden. A *grant* or *fellowship* with no date is the opposite case —
a rolling call — and is still returned. See `tools/retrieval/liveness.py`.

Plus the quality-signal fields. These are **visual only**: rankings never
affect match order, thresholds, or the LLM verdict. Ranking on them would
systematically bury non-CS venues, since only about a quarter of series carry
any rank at all.

```json
{
  "acronym": "SIGMOD", "year_label": "2026",
  "rankings": {
    "ccf": { "rank": "A", "edition": "" },
    "core": { "rank": "A*", "edition": "" },
    "thcpl": { "rank": "A", "edition": "" }
  },
  "rank_badges": [
    { "system": "ccf", "rank": "A", "edition": "" },
    { "system": "core", "rank": "A*", "edition": "" },
    { "system": "thcpl", "rank": "A", "edition": "" }
  ],
  "red_flags": [], "quality_warnings": [],
  "deadlines_structured": [
    { "kind": "abstract", "raw": "2025-01-10 23:59:00 AoE",
      "instant": "2025-01-10T23:59:00+00:00", "basis": "AoE",
      "round_label": "round 1", "source": "conf:ccf_deadlines",
      "is_estimated": false, "extension_count": 0 }
  ],
  "source": "conf:ccf_deadlines", "license": "MIT", "license_url": "",
  "source_links": [{ "source": "ccf_deadlines", "url": "https://ccfddl.com/…" }]
}
```

`acronym` and `year_label` are de-duplicated from each other at ingest (a
source that embeds the year in its acronym, e.g. `"NOVAS 2026"`, does not also
render `"NOVAS 2026 2026"`). `rankings` is the raw `{system: {rank, edition}}`
map, `"N"` ("not ranked by this system" — a real statement, not an absence)
included; `rank_badges` is the display-ready flattening with `"N"` already
dropped, for a client that only wants to render claimed ranks. **`edition` is
always `""`** — no ranking in this dataset is dated to a specific year, so a
client must not print one next to a badge. Roughly three-quarters of series
carry no rank at all; an empty `rank_badges` means no ranking body has
assessed the venue, which is the common case and not a judgement about it.
`red_flags` and `quality_warnings` are free-text arrays (e.g. a venue
whose only future date is a `notification`, not a submission deadline).
`deadlines_structured` is the complete 8-key round array — every kind, not
just the submission-type ones that gate `abstract_open`/`manuscript_open` — the
multi-deadline hover's data source. Note the split of duties: `deadline_date`
carries the **next** actionable submission deadline, while expiry keys on the
**last** written deadline, so a venue with several rounds neither disappears
early nor lingers past its final one. The event date never gates either.

Hover copy for `rank_badges` is not repeated on every card — see
`GET /api/opportunities/ranking-reference/` below.

### `GET /api/opportunities/ranking-reference/`

Static, cacheable reference copy explaining what a conference rank badge
means — authored text, since no such explanation exists as data anywhere in
the open collector. Not a feed and not personalized: fetch once, cache, and
resolve each card's `rank_badges[].system` / `.rank` against it, rather than
re-fetching per card or per page.

```json
{
  "rank_systems": {
    "ccf": { "label": "CCF", "about": "The China Computer Federation's…" },
    "core": { "label": "CORE", "about": "The Computing Research and…" },
    "thcpl": { "label": "THCPL", "about": "Tsinghua University's…" }
  },
  "rank_explanations": {
    "ccf": { "A": "CCF's top band: …", "B": "…", "C": "…" },
    "core": { "A*": "CORE's highest band…", "A": "…", "B": "…", "C": "…" },
    "thcpl": { "A": "…", "B": "…" }
  }
}
```

`rank_explanations` covers every rank a badge can carry (CCF A/B/C, CORE
A*/A/B/C, THCPL A/B) — `"N"` is excluded because `rank_badges` never carries
it.

### `GET /api/opportunities/fellowships/`

The same base shape plus `fields`, `stages`, `award_class`, `citizenship`, and an
eligibility `tier`. For a **person** eligibility is a hard gate applied before
research fit. A **lab or project** has no citizenship or career stage, so its
fellowships rank on research fit alone and carry no eligibility verdict.

`tier` is `qualified` | `conditional` | `unverified` | `""`. `unverified` says
the award published no eligibility details for us to read — such a record passes
every facet test trivially and would otherwise read as a clean match for
everybody — not that the applicant is a poor fit.

The personal envelope adds `stage_set`: whether the reader's career stage
resolved at all (from the eligibility step, the intake answer, or their academic
title). The stage gate is asymmetric and deliberately silent for anyone it cannot
place on the ladder, so a feed built without a stage is genuinely less filtered
and the page says so rather than claiming otherwise.

### `POST /api/onboarding/match/`

Live match for one area during onboarding, reusing the whole-corpus refit path.
For papers it is a hybrid: if the latest batch yields too few high-quality
matches it fires a background scan and returns `scanning: true`.

### `GET /api/search/`

Query-first search over the whole corpus — the digest retrieval pipeline pointed
at a search box instead of a profile. Reads the **global** corpus, so it is not
user-scoped. Params:

- `q` — the search text. Blank returns an empty result, not an error.
- `type` — repeatable/comma (`paper|grant|fellowship|conference`).
- `year` / `sponsor` / `award_class` / `country` — per-type facet filters.
- `date_from` / `date_to` — ISO dates over ingest date.
- `sort` — `relevance` (default) | `date` | `deadline`.
- `limit`, `cursor` — bounded page size and the opaque cursor from `next_cursor`.

Search **never abstains**: an in-corpus query always returns its best matches,
blending a lexical (full-text), a semantic (pgvector), and a fuzzy (pg_trgm)
channel through rank-only reciprocal-rank fusion. `confidence` is `"low"` when
the top semantic match is weak — a display cue, never an empty page.

```json
{
  "query": "protein folding", "normalized": "protein folding",
  "sort": "relevance", "confidence": "ok",
  "count": 559, "pool_truncated": true,
  "facets": { "type": [{ "value": "paper", "count": 85 }],
              "year": [{ "value": "2026", "count": 80 }] },
  "limit": 20, "offset": 0, "next_cursor": "20",
  "results": [{
    "content_id": "uuid", "type": "paper", "title": "…", "summary": "…",
    "url": "https://…", "created_at": "…", "score": 0.021,
    "matched_on": ["lexical", "semantic", "fuzzy"], "saved": false,
    "ignored": false,
    "authors": ["…"], "venue": "Nature", "year": 2026,
    "sponsor": "", "amount": "", "location": "", "event_dates": "",
    "award_class": "", "deadline": ""
  }]
}
```

`facets.type` is always present and its counts ignore the `type` filter. A
per-type facet appears **only when exactly one `type` is selected**, is capped to
its top values, and ignores its own selection. `pool_truncated` is true when
matches exist beyond the bounded relevance pool. `score` is the fused rank weight
— for ordering, not display. `ignored` reports whether the caller has manually
ignored the item; search still returns it either way (see below). `discord` lists
the threads that announced the item in the servers of the reader's own labs and
departments (`[{"guild_id", "guild_name", "channel_id", "thread_id",
"thread_url"}]`, oldest binding first, threads deleted by hand left out), and
`discord_thread_url` is the first of them or `""` — the card's "Discussed in
Discord" link.

## Saves, ignores, deadlines, notifications

### `POST /api/opportunities/save/`

Bookmark a paper, grant, conference, or fellowship. Body
`{ "content_id", "note"?, "lab_slug"? }`. With `lab_slug` the save belongs to
that lab and requires manage rights on it. The display and deadline fields are
snapshotted so the save survives the daily prune. `201` with the snapshot; `400`
without `content_id`; `404` for an unknown item.

`DELETE /api/opportunities/save/<content_id>/[?lab=<slug>]` removes it. `204`, or
`404` if not saved.

A personal save also clears any **ignore** on the same item — see below.

### `POST /api/opportunities/ignore/`

Manually ignore a paper, grant, conference, or fellowship: stop surfacing it to
this reader. Body `{ "content_id" }`. Personal only — there is no `lab_slug`,
because an ignore is a fact about the reader, not about a lab.

Ignoring hides the item from **every feed this reader looks at** — their papers,
grants, fellowships and conferences pages, the lab and project feeds they read,
their window counts, and their next briefing and PDF report. It hides it from
nobody else. Nothing is deleted: the `ContentItem` and its `RelevanceScore` rows
are untouched, the item stays rankable, and each theme's slate is computed exactly
as before — the filtering is a per-reader read, not a change to the ranking.

Search is the deliberate exception: `GET /api/search/` still returns ignored
hits, flagged `ignored: true`, because suppressing a result the reader explicitly
queried for would be dishonest — and it is how they find one again.

Ignoring also drops any **personal** save of the item (the two controls mean
opposite things), and saving an ignored item clears the ignore. A **lab** save is
left alone; it belongs to the lab.

`201` on the first call, `200` on a repeat (idempotent, and only the first logs a
`dismiss` relevance event); `400` without `content_id`; `404` for an unknown item.

`DELETE /api/opportunities/ignore/<content_id>/` undoes it. `204`, or `404` if
not ignored. Scoped to the caller — it can never clear anyone else's row.

### `GET /api/opportunities/ignored/`

Everything this reader has ignored, newest first, with the same feed-parity
`card` the Saves page renders. Unlike a save there is no snapshot: an ignore row
cascades with its item, so `card` is never `null`.

```json
{ "items": [{
  "id": "uuid", "content_id": "uuid", "area": "grant",
  "ignored_at": "2026-08-17T21:40:00Z",
  "card": { "content_id": "uuid", "title": "…", "verdict": "read" }
}] }
```

### `GET /api/saves/` · `GET /api/labs/<slug>/saves/`

Every bookmark, newest first, with **feed-card parity**: each save is joined back
to the relevance score for the item and `card` carries exactly the payload that
item's own feed page renders. The lab variant reads the lab's scores and its
envelope carries `can_manage`, which gates the remind and remove affordances.

```json
{ "items": [{
  "id": "uuid", "content_id": "uuid", "area": "paper",
  "title": "…", "url": "https://…", "subtitle": "NeurIPS",
  "deadline_date": null, "deadline_kind": "other", "note": "",
  "days_remaining": null, "within_week": false, "saved_at": "…",
  "card": { "content_id": "uuid", "title": "…", "verdict": "read", "saved": true }
}] }
```

`card` is `null` once the source listing was pruned or was never scored for this
caller — the envelope fields are then the fallback display.

### `GET /api/deadlines/`

All saved deadlines, soonest first: `id`, `content_id`, `area`, `title`, `url`,
`subtitle`, `deadline_date`, `deadline_kind`, `note`, `days_remaining`,
`within_week`. `content_id` is `null` once the source item was pruned.

### `GET /api/reflections/` · `POST /api/reflections/<id>/action/`

What Mylo thinks the caller's project state should say, and their answer. Own
proposals only — a proposal is a request to change what someone wrote about their
own work, so it belongs to them and to nobody else.

```json
[{ "id": "uuid", "project_id": "uuid", "project_name": "Synapse",
   "kind": "add_exclusion", "proposal": { "fast": { "exclusions": ["federated"] } },
   "evidence": { "dismissed": 6, "shared_term": "federated" },
   "status": "pending", "expires_on": "2026-10-05", "created_at": "…" }]
```

The rules behind these are **deterministic** — counts with thresholds over what
the reader saved, dismissed and left undated — and the model only phrases them. A
model deciding on its own that a project's method has changed, and writing it in,
is what invariant 9 forbids.

`POST .../action/` takes `{ "action": "accept" | "reject" }`. **Accepting is the
only thing that applies a proposal**: nothing else in the product writes one into
a project's state, and the endpoint re-checks the project's edit permission rather
than trusting that whoever was proposed to can still edit it. Accepting also sets
`confirmed_at`, because saying "yes, add that" is also saying the state is right.
A pending proposal lapses after 14 days and a decided one is not raised again for
28 — declining is a decision the system respects, not a question it repeats next
Monday. `400` on a proposal already decided, `403` when the caller cannot edit the
project, `404` for someone else's.

**From conversation (ambient Plan 08).** Kinds `close_blocker` and
`drop_method` (and `add_method`) are also raised from a project development Mylo
understood in conversation and someone told or confirmed. Their `evidence` is
`{ "source": "conversation", "development": 12, "topic": "annotation budget",
"field": "slow.blockers", "occurred_on": "2026-09-14", "account": "…",
"explanation": "…", "visibility": "lab" | "personal" }`. A lab one goes to the
project's editors, a personal one only to the person who said it. Accepting one
also records an ambient `state_edit` change, shown in `GET /api/ambient/changes/`
with undo; a pending one is expired when its development is undone or forgotten.

### `GET /api/notifications/`

The header bell, backed by the `Notification` model — **not** an on-the-fly scan
of saves. Five kinds: `reminder` (one fired), `deadline_moved`, `high_signal`,
`delivery_failed` (Mylo gave up reaching Discord, which only in-app can carry),
and `project_alert`. Saving something no longer produces an alert; a reminder
created *from* a save does. Returns undismissed notifications, newest first, with
the unread count.

`project_alert` fires for **every cadence**, and that is what makes "cadence
governs Discord and nothing else" true rather than merely stated: a
weekly-cadence reader opening the app on a Wednesday sees exactly the alerts a
daily-cadence reader was DM'd that morning. A lab's alerts do not fan out to its
members' bells — one finding ringing eight times is how a bell gets ignored — and
reach people through the lab report instead.

```json
{ "count": 1, "items": [{
  "id": "uuid", "kind": "reminder", "content_id": "uuid",
  "title": "…", "body": "…", "url": "https://…",
  "created_at": "…", "read_at": null }] }
```

`POST /api/notifications/<id>/action/` takes `{ "action": "read" | "dismiss" }`.

## Reminders

Deadline reminders are a **paid, Discord-delivered** capability.

### `GET | POST /api/reminders/`

`GET` lists the caller's reminders, narrowed by `?state=` and `?lab=`.

`POST` creates a personal or lab reminder from a content item:
`{ "content_id", "deadline_kind", "deadline_round_key"?, "offsets": [{ "amount",
"unit" }], "lab_slug"?, "channel_id_override"?, "mentions"? }`. Dateless
deadlines are rejected; a lab reminder needs manage rights.

`deadline_round_key` selects **which** round of that kind, taken verbatim from
the matching `addressable_deadlines` entry. Omitting it means `""` — the
single-round key every grant, fellowship, and conference event row carries — so
a client that never sends it keeps working unchanged.

`mentions` (lab scope only) is who the post @-mentions:
`[{ "kind": "user" | "role" | "everyone", "id"?, "username"?, "name"? }]`. A
bare list of Mycelium usernames is still accepted and still means "these lab
members". Every raw `id` is validated against **that lab's own guild** before it
is stored — a role against the guild's roles, a person against its members — so
an alert can tag a collaborator who has no Mycelium account without Mylo
becoming a way to ping an unrelated server. An id that isn't in the guild is a
`400`, never a silent drop: an alert that reaches fewer people than the person
who set it believes is worse than an error.

`@everyone` is the one target with no id, so it is the one that reopens
`allowed_mentions.parse`. That happens only when a manager explicitly chose it
for that alert; scraped title text stays escaped either way, so a conference
called "@everyone submit now!" can never ping a server.

### `GET /api/reminders/lab-mention-targets/?lab=<slug>`

Who a lab alert may tag: `{ roles, members, everyone_allowed, detail }`.
Manager-only (PI / owner / admin) — a mention reaches a whole server, so the
roster is itself a management view. Always `200`: an unlinked guild, a Discord
hiccup, or the **Server Members** privileged intent not being enabled all return
empty lists with `detail` explaining which, so the picker can say why instead of
looking broken. Bots and Discord-managed roles are excluded (pinging either
reaches nobody), as is the `@everyone` pseudo-role, which is offered as its own
explicit choice.

**POST upserts.** A repeat request for a (target, content, deadline_kind,
deadline_round_key) that already has a row reconfigures it and answers **200**;
`201` is only for a genuinely new one. This is also how a cancelled reminder is
re-armed. A *different round of the same kind* is not a repeat — "warn me about
both paper deadlines" creates two reminders.

`403` with a `reason` slug when the gate is not satisfied.

### `PATCH | DELETE /api/reminders/<id>/`

`PATCH` accepts `offsets`, `channel_id_override`, `mentions`, `snoozed_until`
(explicit `null` un-snoozes; a past date is rejected), and `state`
(`active` | `cancelled`). An absent key is left alone. `DELETE` soft-cancels;
`?purge=1` destroys the row.

**Neither is entitlement-gated** — delivery is already gated at send time, and
locking someone out of stopping their own reminders would only trap them.

### Read shape

Each reminder carries `scope`, `lab_slug`, `lab_name`, `content_id`,
`deadline_kind`, `deadline_round_key`, `round_label`, `area`, `title`, `url`, `due_date`, `confidence`, `state`,
`snoozed_until`, `channel_id_override`, `has_unlinked_targets`, `mentions`,
`can_manage`, and timestamps — plus, per offset, the `fire_date` it resolves to,
the overall `next_fire_date`, and `send_hour_local` / `timezone`. The hour is a
real configured value for a lab and **`null`** for a personal reminder, which
rides the daily run rather than an hour anything honours. Offset dates are
computed with the same function the tick uses, so the page and delivery cannot
drift.

### `GET /api/reminders/access/[?lab=<slug>]`

`{ "allowed", "plan_ok", "discord_ok", "reason", "detail" }` — the one
computation the UI's lock state and the server's enforcement both read. Personal
access needs the `DEADLINE_REMINDERS` feature (a lab-paid seat entitles the
member) **and** an active `DiscordIdentity`; lab access needs the lab's feature
**and** an active guild link (`PENDING_SETUP` does not count). It is enforced
again at send time: a lapsed plan stops the Discord delivery but the in-app
notification still fires, and nothing is deleted on a billing event.

### `GET /api/reminders/lab-channels/?lab=<slug>`

Postable Discord channels for the composer's picker, plus the `/setup`
announcement channel as the labelled default. Manager-gated. Degrades to an empty
list — never a 500 — when the guild is unlinked or Discord is unreachable.

## Billing

### `GET /api/billing/me/`

The caller's resolved entitlements — what the UI locks affordances against
instead of discovering limits through 403s.

```json
{ "billing_mode": "subscriptions", "tier": "spore",
  "features": ["deadline_reminders", "…"],
  "topic_cap": 20, "cluster_cap": 6, "cluster_topic_cap": 10,
  "topics_used": 4, "seat_count": 1, "pi_cap": null,
  "addons": ["mylo_server"],
  "plans": [{ "tier": "spore", "status": "active", "expires_at": "…" }] }
```

`billing_mode` is the instance's `billing.mode` (`mycelium.toml`). Every cap is
`null` when unlimited. With `billing_mode: "off"` the caps come from the
instance's `[limits]` (unlimited by default) and `features` lists everything;
with `"subscriptions"` they come from `[limits.tiers.<tier>]`. `tier` is the
maximum across every covering plan, with expired plans excluded at read time.

### `GET | POST /api/labs/<slug>/billing/[activate/]` · `/api/departments/<id>/billing/…`

`GET` returns the org plan's seat-priced state: `scope_type`, `scope_slug`,
`scope_name`, `tier`, `status`, `is_active`, `is_comped`, `seat_price_cents`,
`seat_count`, `member_count`, `mylo_included`, `can_manage`. `member_count` is
the roster the plan would cover; `seat_count` counts seats already ACTIVE. Org
plans start inactive; `activate/` turns the plan on and auto-entitles the
effective membership. Nothing is charged here — payment processing is out of
scope.

## Discord

`POST /api/integrations/discord/start/` begins the personal OAuth link and
`GET …/callback` completes it (Discord redirects the browser to the exact
registered no-slash URI). `guild/start/` and `guild-callback` do the same for
installing Mylo into a server. `code/` and `lab-code/` mint the activation codes
used by the in-Discord `/mylo` commands as the alternative link paths. `code/`
returns `{code, expires_in, expires_at, activation_channel, invite_url, command}`
— `command` is the whole line to paste (`/activate code:ABCD-EFGH`) and
`invite_url` is `DISCORD_INVITE_URL` or `null`; both are composed server-side so
the portal cannot quote a renamed command, and `expires_at` is absolute so a
countdown does not depend on the browser's clock. Redemption is by the gateway,
so the portal polls `status/` while a code is live to notice it landed.
`department-code/` mints the department twin, redeemed with
`/activate-department`. `bindings/<id>/remove/` switches off one lab-or-department
binding in one server; other bindings, in that server and elsewhere, keep working.
`status/`, `guild/status/`, `health/`, and `probe/` report link and reachability
state; `guild/status/` and `health/` describe the lab's primary server, and
`health/` also returns `servers`, one entry per server the lab is bound in (each
with `binding_id`, `state`, `guild_name`, `channels`, and `routes`). `daily-report/` toggles `DiscordIdentity.daily_report_opt_out` (the
profile card's "Daily research report" switch). `disconnect/` unlinks.

Slash commands are served by the persistent gateway process (`mylo/`), not by an
HTTP interactions endpoint. Outbound messages go through a durable outbox with a
nonce and dedupe key, drained on a schedule. See
[`discord-integration.md`](discord-integration.md).

## Platform admin

Base path `/api/admin/`. **Every endpoint requires staff or superuser**; anyone
else gets `403`. This is the authorization boundary — the frontend nav gate is
only a rendering hint. Every write records an `AuditEvent`. Standalone admins are
minted out-of-band by the `create_admin` command, never through this API.

### `GET /api/admin/users/`

Paginated, searchable roster (default 25/page, max 100). Params `page`,
`page_size`, `q` (username / email / first / last name).

```json
{ "count": 412, "next": "…?page=2", "previous": null,
  "results": [{
    "id": 7, "username": "marie.curie", "email": "mc@lab.test",
    "name": "Marie Curie", "is_staff": false, "is_superuser": false,
    "is_active": true, "date_joined": "…", "effective_tier": "spore",
    "subscription": { "tier": "spore", "status": "active", "expires_at": "…" },
    "watch_topics_used": 4, "watch_topic_cap": 10, "watch_topic_limit": null }] }
```

`subscription` is the personal (`scope_user`) plan or `null`; `effective_tier` is
the resolved maximum across covering plans, excluding expired ones.

### `GET | PATCH /api/admin/users/<id>/`

`GET` adds `academic_title`, `watch_topics`, `watch_categories`, and
`lab_memberships`. `PATCH` assigns the plan and/or quota — all fields optional,
send at least one:

```json
{ "tier": "spore", "duration_days": 90,
  "subscription_status": "active", "watch_topic_limit": 20 }
```

- `tier` — `free` | `spore` | `lab` | `canopy`.
- `duration_days` (≥ 1) **or** `expires_at` (ISO 8601), mutually exclusive; either
  sent as `null` clears the expiry. Omit both to leave it untouched. Expiry is
  enforced at read time: a lapsed plan reverts to Free and nothing is deleted.
- `subscription_status` — `active` | `past_due` | `canceled`.
- `watch_topic_limit` — 0–200, or `null` to clear back to the instance (or tier) limit.

`400` on an empty body, on `duration_days` + `expires_at` together, or on an
out-of-range limit.

### `GET | PATCH /api/admin/labs/[<slug>/]`

The same roster / detail / plan-assignment pattern for labs. The detail also
carries `limits: { project_limit, member_limit, project_cap, member_cap }` —
the lab's staff overrides (`null` = none) and the limits in effect (`null` =
unlimited). PATCH `project_limit` / `member_limit` (≥ 0, or `null` to clear) set
the overrides, which win over `mycelium.toml`; a limits-only PATCH touches no
plan. A department's project override is set in Django admin
(`Department.project_limit`).
