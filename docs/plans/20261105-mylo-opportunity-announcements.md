# Mylo Opportunity Announcements — implementation plan

Status: **approved, in progress** (revision 5, approved 2026-11-05). Every
behaviour below was reviewed against the prototype in the Discord test server
(`1507798835311673616`, category *Mylo Opportunities (prototype)*) and the
*Mylo Announcements Mockup* canvas. All review questions are answered (see
**Answered in review**). Phase 0 is done; progress is recorded per phase in
`docs/changelog.md`.

## Objective

Mylo announces **individual** grants, fellowships, and conferences, one forum
thread per item, each kind in its own channel. Every post says whether the item
is *usable* (open, eligible, possible before its deadline) and *why it matters*
to that lab's or department's research. Mylo then keeps each item current: a
changed call is reposted as an update and the people who said they were
interested are tagged. A lab and a department are **independent audiences**,
each with its own servers, settings, and posts.

Papers are unchanged: they stay in the daily or weekly report.

## Locked decisions

| # | Decision |
| --- | --- |
| D1 | **Forum channels**, one per kind (`#grants`, `#fellowships`, `#conferences`), one thread per item. Every Mylo surface in Discord is a thread; there are no text-channel posts. |
| D2 | **"New" = entered the target's per-theme slate and never announced to that target.** Posts are labelled *New call* (source posted ≤ 14 days ago), *Newly relevant*, or *Already open* (see D5). |
| D3 | **Departments are their own target** (`DeptProfile`) and see only department-level calls (see **What a department sees**). |
| D4 | **A bounded editor agent** decides whether to post and writes the headline, *Why it matters*, and *Next step*. Code supplies every date, amount, and eligibility check. A verifier enforces this, and a template is the fallback. |
| D5 | **No cap** (`daily_cap = -1`). **Activation seeds six:** when announcements are first switched on, Mylo posts the **six most relevant open items** for that lab or department, labelled *Already open*, with no tags. It also posts the closing-soon list straight away. From the next night on, only new entrants are posted. |
| D6 | With announcements on, the daily report keeps one line per kind ("2 grants announced → #grants") instead of listing them. |
| D7 | Tags happen only for: (a) people who clicked *Interested* (on updates and their default nudge), and (b) **strong-match tagging**, which is **off by default** per target. |
| D8 | Feature `OPPORTUNITY_ANNOUNCEMENTS` on Lab and Canopy plans, plus `BOT_SERVER`, read through `billing.entitlements`. |
| D9 | **A changed call updates its existing thread in place.** Mylo edits the opening post to the current facts with *What changed* at the top, renames the thread `[🚨 Update <Mon D>] <title>`, adds the `Updated` tag, and replies in the thread tagging the interested people. The reply bumps the thread to the top of the forum. The thread, its link, and its discussion are kept; nothing is deleted or reposted. |
| D10 | **Nudges only for people who asked.** *Interested* gives a default **2 weeks before** tag in the thread. *Remind me* opens a picker only that person sees: **2 days, 1 week, 2 weeks (preselected), 3 weeks, 1 month, 2 months**, several allowed, sent by **DM (default)** or as a thread tag. Choices already past are hidden. |
| D11 | **Closing-soon list** every morning in `#grants` and `#fellowships`: everything on the list closing within 14 days, as one thread that replaces yesterday's. Nothing is posted on a day with nothing closing. |
| D12 | Mylo **creates channels only when a manager asks** ("Create them for me", with a preview). Otherwise managers pick existing channels. |
| D13 | **Anyone can always reply in a thread.** Setup chooses who can *start* posts: everyone (default), managers only, or chosen roles. |
| D14 | **Interested DMs the full details** (every round, the award, the checks, why it fits them, their reminder) with *Change reminder*, *Open the thread*, and *Stop following*. |
| D15 | **`/mylo search` links to existing threads** in the server it ran in, and a manager can announce an unannounced result. This must be **verified live** in the test server (Phase 5). |
| D16 | **Lab and department are fully separate.** A lab can have its own server, can *also* have a category in its department's server, or both. A department can have its own server. Each binding is set up, configured, and switched off on its own, and none depends on another. There are **no cross-links** between a lab's posts and a department's posts. |
| D17 | **On the web, every link into Discord shows the Discord logo and the channel name, and opens in a new tab.** This replaces text such as "Open thread in #grants" and "Open thread in #dept-opportunities". |

## Answered in review

- **Q1. Changed calls:** update the existing thread in place and bump it,
  rather than deleting or archiving it (D9).
- **Q2. "Manny"** was Mylo. The digest people aren't reading is Mylo's own
  daily report, which D6 slims down. No paper-filing command is needed.
- **Q3. Activation:** start with the next night's entrants, seeded with the
  six most relevant open items and the closing-soon list (D5).
- **Q4. Limited-submission calls** count as department-level (*Institutional
  selection*).

## Labs, departments, and servers (D16)

Today one server binds to one lab (`DiscordGuildLink`, `OneToOne` to `Lab`,
`guild_id` unique). That can't express "a department server with several labs
in it, while those labs also have servers of their own". The new model:

- **`DiscordGuildLink` describes the server only:** install, verification,
  state, health, and who installed it. It no longer points at a lab.
- **`DiscordTargetBinding`** links one guild to one target (lab XOR department).
  Fields: `activated_by`, `activated_at`, `state`, and unique (guild, target). A
  guild can hold many bindings, and a target can be bound to many guilds.
- **Activation per target.** `/activate-lab code:` (unchanged for users) adds
  a lab binding to the server it runs in. A new `/activate-department code:`
  does the same for a department. The code is issued on the website by that
  lab's or department's manager, so the authority comes from the target, never
  from the server. Binding a lab into its department's server needs that lab's
  own code; the department cannot bind its labs.
- **Routes belong to a binding.** `DiscordChannelRoute(binding, purpose,
  channel…)`. A lab's forums in its own server and its forums in the
  department server are configured separately. In a shared server, each binding
  gets its own category: the department's, and one per lab.
- **One decision, many posts.** `Announcement` is one row per (target, item):
  the checks, the write-up, and the reactions. `AnnouncementPost` is one row
  per binding it was posted to, holding the thread id. A lab bound in two
  servers gets the same post in both, but one *Interested* per person, one DM,
  and one set of reminders.
- **Buttons resolve to the target, not the server.** A click looks up its
  post's target and checks membership of that lab or department through
  `apps.accounts.permissions`. Being in the Discord server grants nothing.
- **Switching off is local.** Removing a binding, unbinding a route, or a
  lapsed plan stops that binding's posts only. Other bindings carry on.
- **Migration:** each existing `DiscordGuildLink` becomes a guild row plus one
  lab binding. The two existing channel columns move into that binding's
  routes. Lab digest, reminders, ambient listening, reconcile, and the admin
  move to bindings. Today 7 non-test modules touch the link:
  `content/reminder_access.py`, `integrations/{models,serializers,admin}.py`,
  `services/{resolve,reconcile}.py`, and `ambient/models.py`. All ORM access
  stays in `resolve.py`.

## What a department sees

A department channel is for calls **only a department can take on**, not calls
a lab could apply for alone. An item is posted to the department only when it
enters the department's slate (fit to `DeptProfile`) **and** its record shows
one of these:

| Reason (forum tag) | What qualifies | How it's detected (code, with the quoted evidence stored) |
| --- | --- | --- |
| **Department applicant** | The applying unit must be a department, institution, or academic unit, not an individual PI's group. Examples: department transformation, curriculum, or departmental training programmes | Applicant-type and eligibility-text patterns |
| **Institutional selection** | A limited submission or institutional nomination: someone above the lab must choose | "Limit on the number of proposals per organization", "nominated by the institution", and similar patterns |
| **Department-scale programme** | Training programmes (traineeships, REU sites), centres or institutes with a lead institution, and shared facilities run for the unit | Mechanism and funding-instrument patterns |

- **Fit to two or more labs is not a reason.** Labs can apply for those
  themselves, so they stay with the labs.
- **No reason, no department post.** The department's web page lists only
  department-level items.
- **Detection is code, never the agent.** Each reason stores the sentence it
  matched. Before departments switch on, precision is measured on a
  hand-labelled sample of real records and recorded as an experiment under
  `docs/research/experiments/`. A pattern that misfires is removed, not tuned
  to pass.
- **The department post names labs, never people:** "Labs that could lead:
  Coastal Hazards Group, Ocean ML Lab". Fellowships at department level
  (nomination programmes) give counts only. Each eligible person is told by
  DM.

## The nightly path

The new command `announce_opportunities` runs in `manual_all.py` after
scoring, member-fit, and team-fit, and before reports are sent.

1. **Select.** For each target with announcements on, take its slate entrants
   for grants, fellowships, and conferences. Drop items that already have an
   `Announcement` for that target. For a department, keep only items with a
   department-level reason.

   **First run for a target (D5):** don't announce the whole slate. Take the
   six best-ranked open items across the enabled kinds, interleaving kinds by
   slate position so one kind can't fill all six. They go through steps 2–5
   as *Already open*, and the closing-soon list is posted the same night.
   Everything else already on the slate is marked as seen, so it is never
   announced later. The number is a setting, `activation_seed = 6`.
2. **Check usability (code, `apps/content/usability.py`).** Each check gives
   `ok` / `warn` / `block` / `unknown`, a label, and the field it read:
   - open, and next round
   - feasible against the buffer
   - applicant eligibility against the org's institution type and country
   - award fit against an optional preference
   - fellowship eligibility (counts, never names, in a channel)
   - team coverage

   A `block` stops the item, which is shown under "Mylo held back" with its
   reason. A missing field gives `unknown`, never `ok`.
3. **Align (facts).** The theme it entered, matching projects, and who it suits
   (member-fit for labs, lab-fit for departments). Strong-match tagging reads
   this step, and only when the target has turned it on.
4. **Edit (agent).** The input is a closed packet. The output is
   `{announce, headline, why_it_matters, who_should_look[], next_step,
   skip_reason?}`. Write-ups are keyed on (item, target, rubric version,
   theme-areas fingerprint), so a re-run costs nothing. The verifier requires
   every cited id to exist in the packet and allows no digit in the prose; on
   failure, the template is used.
5. **Post.** For each of the target's live bindings, `discord_announcements.py`
   enqueues a forum thread on the outbox, with dedupe key
   `announce:<binding>:<item>`, and writes an `AnnouncementPost`. The outbox
   gains three modes: **create-forum-thread**, **edit-message** (the thread's
   opening post), and **update-thread** (name, tags, unarchive). Forums Mylo
   creates sort by **recent activity**, so an updated thread rises to the top.

Then **`announce_opportunity_updates`** runs:

- **Changed call (D9).** A change in deadline, round, award, eligibility, or
  status is detected by comparing against a fingerprint of the facts the post
  showed. In every binding, Mylo then updates the same thread:
  1. Unarchive the thread if it was archived.
  2. Edit the opening post to the current facts, with *What changed* (old
     value struck through, new value in bold) above *Why it matters*.
  3. Rename the thread to `[🚨 Update <Mon D>] <title>`; a later update
     replaces the date.
  4. Add the `Updated` tag.
  5. Post a reply, `🚨 Update <Mon D>: <one-line change>`, tagging the people
     who are currently interested.

  The reply is what bumps the thread to the top of the forum. Each update is
  appended to the post's `update_log`, so the thread's history stays readable.
  Discord limits how often a thread can be renamed, so updates are coalesced
  to at most one per thread per night.
- **Conferences** are announced the night they first gain a submission
  deadline.
- **Nudges** go out at each person's chosen time and place, and move with the
  deadline.
- **Closing-soon list** in `#grants` and `#fellowships`, replaced daily.
- **Close.** After the last deadline, the thread is archived and tagged
  `Closed`.

## Discord surfaces

- **Announcement thread:** the title, then *Why it matters*, *Can we use
  this?*, *Who should look*, and *Next step*, with buttons **👍 Interested ·
  🔔 Remind me · 🚫 Not for us · View the call**. No percentages ever.
- **An updated thread:** the same thread, renamed `[🚨 Update <Mon D>] <title>`.
  Its opening post now shows *What changed* above *Why it matters*, and a new
  reply tags the interested people. The thread's link never changes.
- **Closing-soon thread:** one dated list, replaced every morning.
- **Buttons** are persistent ids `ann:<post>:<action>` in a new `announcements`
  cog. Each goes `mylo/linking.py` → `apps/content`, through `gate.py`
  (identity → rate limit → permission → entitlement → audit).
  - **Interested:** a reaction plus a save, then the D14 DM. If the person's
    DMs are closed, an ephemeral note says so instead. Unlinked users get a
    prompt to link their account.
  - **Remind me:** the D10 picker, which creates a personal
    `ReminderSubscription` and counts as Interested.
  - **Not for us:** managers only. Adds a target-scope `IgnoredItem` and asks
    for a reason, which is kept as data.
  - **View the call:** a link button.
- **`/setup` announcements step:** "Create them for me" or "Use channels I
  already have", plus who can start posts. It configures **the binding for the
  target being set up** in this server, so running it for a lab never touches
  the department's channels.
- **`/mylo search`:** passes the guild id. Results posted in any binding in
  this server show "💬 Already discussed here → thread". Managers get
  "Announce to #…" for the rest.

## Web surfaces: what each replaces

| Where | Today | Becomes |
| --- | --- | --- |
| Lab overview | `MyloFoundCard` (counts per area) | **Announced** panel: the last few posts, linking to the full list |
| Lab overview | `DeadlinesPanel` (saved items with a date) | **Closing soon · 14 days**, the same list as Discord's (saved items included) |
| Lab feed cards | `RecommendedFor`, `TeamFitLine`, and the Deadlines dropdown as three strips | One **"Can we use this?"** strip. The Deadlines dropdown stays as the per-round control |
| Lab feeds | `HiddenByFilters` at the bottom | Adds a **"Mylo held back"** group |
| Lab Mylo Report | Full opportunity lists | One line per kind (D6) |
| Lab settings | `DiscordSyncCard`'s two channel picks | **Announcements card**: settings for the lab, plus one block per server the lab is bound in, each with its own routes, who can post, and health |
| Department workspace | Nothing | **Opportunities** section (department-level items only, with reason tags and "labs that could lead"), plus a department Announcements card |
| Reminders page | Reminders | Unchanged. *Remind me* reminders appear here |

**Discord links (D17):** every link into a Discord thread or channel renders as
a link with the **Discord logo plus the channel name** (for example
`[Discord logo] #grants`), with `target="_blank" rel="noopener noreferrer"`
and an accessible name such as "Open #grants thread in Discord (new tab)". It
replaces every "Open thread in #…" text link: the Announced list, the card
strip's *Announced* row, the department page, and "Discussed in Discord" on
search cards.
- The icon is one shared primitive, `DiscordLink` in `portal/primitives/`,
  using the official mark as an inline SVG with `aria-hidden` and the brand's
  usage rules.
- When a target is bound in several servers, the link opens the first server,
  and a small menu lists the others.

## Data model

Under `apps/content` unless noted.

- **`Announcement`:**
  - Target: lab XOR department.
  - `content` (SET_NULL plus a snapshot), `category`, `origin`
    (`nightly` / `manual`), `state` (`posted` / `skipped` / `seeded_seen` /
    `closed`; `seeded_seen` marks slate items passed over at activation), and `label`.
  - `dept_reasons` JSON (with evidence).
  - `checks`, `alignment`, `write_up` plus fingerprint, and
    `facts_fingerprint`.
  - Unique on (target, content).
- **`AnnouncementPost`:** announcement, `apps.integrations` binding,
  `thread_id`, `update_log` JSON (date, what changed, reply message id),
  `posted_at`, `closed_at`. Unique on (announcement, binding).
- **`AnnouncementReaction`:** announcement, user, kind (`interested` /
  `not_for_us` / `unfollow`), reason. Append-only.
- **`AnnouncementSettings`** (one per target):
  - `enabled`, plus on/off per kind
  - `daily_cap = -1`
  - `default_nudge = 2w`
  - `closing_soon_list = on`
  - `strong_match_tagging = off`
  - `save_on_interest = on`
  - `activation_seed = 6`
  - an award preference, and `activated_at`
- **`apps/integrations`:**
  - `DiscordGuildLink`: server only.
  - `DiscordTargetBinding`: guild × target.
  - `DiscordChannelRoute`: binding, purpose, channel, type, forum tag ids,
    `created_by_mylo`, `poster_policy`, `poster_role_ids`, `verified_at`, `ok`.
  - `DiscordDepartmentActivationCode`: mirrors the lab code.
- **`content.targets`:** `MatchTarget(kind="department")`, for opportunities
  only.
- **`lab_fit.py`:** lab-fit, mirroring `member_fit.py` with lab vectors.
- **`dept_level.py`:** the department-reason detector.

## Phases, in order

Each phase ships green on its own behind `OPPORTUNITY_ANNOUNCEMENTS_ENABLED`
(default off). Backend commands use `uv run --project web/backend …`, and
vector tests need the Compose Postgres.

**Phase 0: Bring the prototype in line, then sign off.** Changes to the test
server and mockup:
- Switch the forums to recent-activity sort.
- Show the Genesis update the D9 way: one thread updated in place with a
  tagging reply.
- Remove the *Multi-lab* department example, its forum tag, and the lab
  thread's pointer to it.
- Re-tag MRI with *Institutional selection*.
- Keep Mid-scale RI only if its record shows a department-level reason.
- Add the Discord logo links to the mockup.

*Done when* you approve the prototype as the target.

**Phase 1: Prerequisites.**
- Fix the open billing gap: `entitlements._lab_subscriptions` grants a
  department plan's `BOT_SERVER` to a lab even when
  `Lab.department_plan_included` is false. Department servers make this
  matter.
- Refactor the guild link into server, binding, and route, with the migration
  above, plus `/activate-department` and its code.

*Validate:* the integrations, content, and ambient suites, plus
`uv run python -m unittest discover -s mylo`. Then a live smoke run in the test
server:
- The existing lab digest, reminders, and `/setup` behave exactly as before.
- One server can hold a lab binding and a department binding.
- The same lab can be bound in a second server.
- Unbinding one leaves the others working.

**Phase 2: Usability facts and the web strip.** `usability.py`, institution
type and country on orgs, and the "Can we use this?" strip in the shared
serializer.
*Validate:* `pytest apps/content/tests/test_usability.py` with real collector
records (an EU call, a US-only call, a closed round, missing fields giving
`unknown`).

**Phase 3: Engine (dry run).** Models, `announce_opportunities --dry-run`, the
agent, the verifier, the template fallback, the change detector, and the
closing-soon composer.
*Validate:* tests for:
- entrant-only selection, and never-twice
- activation posting exactly six (kinds interleaved), with the rest of the
  slate never announced later
- `-1` meaning unlimited
- a moved date counting as a change, but an identical re-scrape not
- verifier rejection Then a dry run on live
data, read by hand.

**Phase 4: Discord delivery for labs.** The outbox thread modes, the `/setup`
announcements step (create or pick, who can post), the `announcements` cog
with all four buttons, the Interested DM, the Remind me picker, the update
stage, nudges, the closing-soon list, and drift detection for routes.
*Validate:* the suites, then the test-server smoke run:
1. opt-in create → six *Already open* threads plus the closing-soon list
2. next-night entrants only
3. Interested → DM
4. Remind me → DM at the chosen time (clock override)
5. a forced change → same thread renamed `[🚨 Update]`, opening post edited,
   tagging reply posted, thread at the top of the forum, earlier replies
   intact
6. an archived thread reopens when its call changes
7. the closing-soon list replaced the next morning
8. a lab bound in two servers gets one DM and one reminder per person

**Phase 5: Search links (D15).** Guild id through `linking.py`, `thread_url`
on search rows, manager announce, and the web "Discussed in Discord" link.
*Validate (unit):* an announcing server, another server, a DM, an updated
thread, and a thread someone deleted by hand (no link, and no error).
*Validate (live, required):* run the real `/mylo search` against real data in
the test server and record the results in the changelog:
1. Announced items, and only those, show "Already discussed here".
2. Every link opens the right thread.
3. A DM, or a server without announcements, shows no links.
4. After a forced update, the same link opens the updated thread.
5. "Announce to #…" posts once and then disappears from that result.
6. The web search card shows the same links.

**Phase 6: Web surfaces.** The replacements table, the `DiscordLink`
primitive (D17), and the per-server blocks on the Announcements card.
*Validate:* `tsc --noEmit` and eslint in `web/app`. Then a browser check at
localhost:11050:
- every Discord link shows the logo and opens a new tab
- loading, empty, error, permission-denied, and mobile states

**Phase 7: Departments.** The department target, lab-fit, `dept_level.py` and
its precision experiment, department posts, the department Opportunities
section, and its Announcements card.
*Validate:* target-parity tests, a pgvector run, the experiment's recorded
precision, and a test-server smoke run:
- A department binding gets only department-level items.
- A lab in the same server keeps its own channels.
- Neither changes when the other is switched off.

**Phase 8: Measure and tune.** Interested and Remind me rates, Not-for-us
reasons, link clicks, route health, and department-reason precision, recorded
as an experiment before any threshold changes.

## Interfaces that change

- **API** (record in `docs/api-contract.md`):
  - `GET /api/announcements/?lab=|department=`
  - `GET/PUT /api/announcements/settings/?lab=|department=`
  - `POST /api/announcements/test/`
  - `POST /api/announcements/create-channels/`
  - `POST /api/integrations/discord/department-code/`
  - both slash forms on every POST
  - `usability`, `alignment`, and `announcement` objects (with a `discord`
    list of `{guild, channel, thread_url}`) on the opportunity serializers
  - `discord_thread_url` on search results
- **Discord:** forums, `/setup` announcements step, `/activate-department`,
  persistent `ann:` buttons, the ephemeral picker, and search thread links.
- **`manual_all.py`:** two new stages.
- **Docs:** `repo-map.md`, `discord-integration.md` (bindings, routes, poster
  policy, department activation, the permissions needed: Manage Channels and
  Manage Roles only for opt-in creation and poster rules, Manage Threads to
  rename, retag, and unarchive threads on update), and `architecture.md`.

## Security and trust

- Authorization lives in `apps.accounts.permissions`. A Discord identity
  authenticates and grants nothing; server membership grants nothing.
- Each binding is authorized by its own target's manager. A department can't
  bind or configure a lab, and a lab can't bind or configure a department.
- A department post names labs, never people. Fellowship eligibility is never
  posted in a channel, and nobody is named as ineligible.
- `allowed_mentions` lists exactly the users being tagged: never `everyone`,
  never roles.
- Audit events for: binding, unbinding, settings, channel creation, poster
  policy, test posts, Not for us, manual announce, and thread updates.
- The agent sees only its packet, with no web access and no other target's
  data.

## Acceptance

- A lab and a department each work with their own server, in a shared server,
  or with no Discord at all, and switching any one off affects nothing else.
- The department sees only items with a department-level reason, and each post
  carries that reason.
- New slate entrants each get a thread (no cap), and no item is announced twice
  to the same target.
- Activation posts six *Already open* threads and the closing-soon list, and
  never more.
- A changed call updates its existing thread within one night: it's renamed
  `[🚨 Update <date>]` and moved to the top, with a reply tagging only the
  people interested in it. Its link and discussion survive.
- Interested produces a DM. Remind me fires at the chosen time and place and
  follows deadline moves.
- `/mylo search` links to existing threads, verified live (Phase 5).
- Every Discord link on the web shows the Discord logo and opens in a new tab.
- Every posted fact traces to a record field.

## Out of scope

Slack and Teams delivery. Paper announcements. Drafting proposals. Any change
to ranking (announcements read the slate and never re-rank, so the eval harness
is untouched).
