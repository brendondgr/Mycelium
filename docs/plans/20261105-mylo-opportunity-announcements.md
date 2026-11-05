# Mylo Opportunity Announcements — plan

Status: **proposal, not started**. Revision 2 (2026-11-05) adds the review
feedback: no daily cap, updates replace their thread, Interested and Remind me
are per person, a morning closing-soon list, opt-in channel creation, poster
permissions, strong-match tagging, and search links into threads. Prototype
posts are in the Discord test server (`1507798835311673616`, category *Mylo
Opportunities (prototype)*, including `#mylo-previews` for DM and
only-you-can-see screens). The web mockup is the *Mylo Announcements Mockup*
canvas.

## Objective

Have Mylo announce **individual** grants, fellowships, and conferences to labs
and departments. Each kind gets its own channel, and every post says two
things: whether the item is *usable* (open, eligible, possible before its
deadline) and *why it matters* to the lab's or department's research goals.
After that, Mylo keeps each item current. A changed call is reposted as an
update, and the people who said they are interested are told.

Why: today the lab channel gets one long daily digest plus a PDF. People skim
it or mute it, so a fitting call gets lost among the papers. Funding and venues
are what a lab has to *act on*, and each has a date. They should each get a
short post with a clear action, somewhere people can follow it.

What stays the same: papers stay in the daily or weekly report and the updates
channel. This plan changes how opportunities reach a lab, not how papers do.

## Decisions (D1–D4 and D8 approved in review; the rest revised to match it)

| # | Decision | Choice | Why |
| --- | --- | --- | --- |
| D1 | Channel shape | **One forum channel per kind** (`#grants`, `#fellowships`, `#conferences`) under one Mylo category. Plain text channels are the fallback | A forum post *is* one item: it has a title, tags, its own discussion, and followers |
| D2 | What counts as "new" | **Entered the target's per-theme slate *and* never announced to that target before.** Posts are labelled **New call** (source posted ≤ 14 days ago) or **Newly relevant** | Keeps the slate rule: "new" is about what the reader is shown, not what was ingested |
| D3 | Departments | **A real `department` match target over `DeptProfile`**, for grants, fellowships, and conferences only, plus lab-fit ("which labs should look") | Departments have no feeds today. A union of their labs' slates would announce one call N times |
| D4 | "Agent" scope | **A bounded editor agent.** It decides whether to post and writes the post. It may drop an item but never add one, and it never writes a date, an amount, or an eligibility verdict | The model explains; the code decides the facts |
| D5 | Volume | **No cap.** The setting `daily_cap` defaults to `-1` (unlimited). The one guard kept: on first activation, a single **"What's open now" roundup** instead of announcing the whole slate | Reviewed: a cap hides real items. The roundup stops activation from posting ~40 threads at once |
| D6 | Opportunities in the digest | Once announcements are on, the digest keeps **one line per kind** ("2 grants announced → #grants") | So the same item isn't in two places |
| D7 | Mentions | A post tags someone in only two cases: **(a)** the update and deadline posts for an item they marked *Interested*, and **(b)** **strong-match tagging**, which names members whose interests fit an item very closely. Strong-match tagging is **off by default**, a per-lab switch | The person asked for it, or the lab switched it on |
| D8 | Tier | `OPPORTUNITY_ANNOUNCEMENTS`, **Lab and Canopy (department)**, read through `billing.entitlements`; also requires `BOT_SERVER` | Org-scoped Discord delivery |
| D9 | A changed call | **Delete the old thread. Post a new one titled `[🚨 Update <Mon D>] <title>`,** with a *What changed* block first and the Interested people tagged | Reviewed. One live thread per item, always current |
| D10 | Deadline nudges | **Only for people who asked.** *Interested* gives a default nudge **14 days** before, tagged in the thread. *Remind me* opens a picker only that person sees (lead times, DM or thread), and it overrides the default. No other nudges go to the channel | Reviewed. A nudge nobody asked for is noise |
| D11 | Daily list | Every morning, a **"Closing soon: next 14 days"** post in `#grants` and `#fellowships` (not conferences). It replaces yesterday's list, and nothing is posted on a day with nothing closing | Reviewed. One full list people can scan, in the roundup's format |
| D12 | Channel creation | Mylo creates the category and forums **only when a manager asks** ("Create them for me" in `/setup`, or the toggle on the website). It shows exactly what it will create first. Otherwise managers pick existing channels | Reviewed. Never changes a server unasked |
| D13 | Who can post | **Anyone can always reply in a thread.** Setup asks who can *start* new posts in the forums: **everyone (default)**, lab managers only, or chosen roles. Applied as forum permission overwrites | Reviewed. Lets a lab keep the forums Mylo-only or open them up |

**Still open, for you to decide:**

- **Q1. Deleting a thread that people replied in.** D9 deletes the old thread,
  and any human discussion in it goes with it. Recommendation: delete when the
  thread has no human replies. When it has some, lock it, archive it, rename it
  `[Superseded]`, and link to it from the update post. Say if you would rather
  always delete.
- **Q2. "Manny".** Is that Mylo's current digest, or a person posting papers by
  hand? If it's a person, the "Mylo, file this" path in Phase 6 matters more.

## How an announcement is made (the nightly path)

The new command `announce_opportunities` runs in `manual_all.py` after
scoring, member-fit, and team-fit, and before reports are sent. Its stages:

1. **Select.** For each lab or department with announcements on, take the
   entrants to its grant, fellowship, and conference slates (`slates.py`
   already diffs each theme against the previous run). Drop anything that
   already has an `Announcement` for that target.
2. **Check usability (code only).** A new module, `apps/content/usability.py`.
   Each check gives a status (`ok` / `warn` / `block` / `unknown`), a short
   label, and the source field it read:
   - **Open:** status and next round (`liveness.py`, `deadlines_projection.py`).
   - **Feasible:** days left against the target's buffer (`matchers/timeline.py`,
     `timeline_settings.effective_timeline`).
   - **Applicant eligibility:** the collector's `applicant_types` and the
     funder's region, against the org's institution type and country. For
     example, an EU Horizon call for a US public university gives `warn`, "EU-led
     consortium; US partners usually join unfunded". This needs a new
     institution-type and country fact on the org, from the verified
     institution directory.
   - **Award fit:** the record's floor and ceiling against an optional org
     preference.
   - **Fellowships:** which members pass the existing rule engine
     (`fellowships.py`). For a department, the count across its labs.
   - **Team coverage:** the existing team-fit line (`collab/team_fit.py`).

   A `block` (closed, deadline inside the buffer, ineligible applicant type)
   stops the item. It is stored as `skipped` with the reason and shown under
   "Mylo held back".
3. **Align to goals (facts).** Which theme the item entered (cluster
   attribution), which projects match it (project slates and matchers), and who
   it suits: members (member-fit) or labs (lab-fit). For a department, the
   department goals it serves. Strong-match tagging (D7b) reads this step: a
   member above `ANNOUNCE_STRONG_MATCH_COSINE` on member-fit, and only when the
   lab has turned it on.
4. **Edit (the agent).** The agent gets a closed packet: the item's précis, the
   checks, the alignment, and the org's themes and goals. It returns
   `{announce, headline, why_it_matters, who_should_look[], next_step, skip_reason?}`.
   Its tools are read-only (`get_item`, `get_project`, `get_member_profile`);
   it has no web access. Write-ups are keyed on (item, target, rubric version,
   theme-areas fingerprint), so a re-run costs nothing. A verifier, following
   the `weekly_verify.py` pattern, checks the output: cited ids must exist in
   the packet, and no digit may appear in the agent's prose. If verification
   fails, a deterministic template is used and the item is still posted.
5. **Render and enqueue.** `discord_announcements.py` builds the forum thread
   (title, tags, embed, buttons) and enqueues it on the outbox with dedupe key
   `announce:<target>:<item>`. Then it writes the `Announcement` row. The outbox
   gains two send modes: **create-forum-thread** (`POST /channels/{forum}/threads`,
   which records the thread id) and **delete-thread**.

After that, a separate stage, `announce_opportunity_updates`, runs:

- **Changed call → replace (D9).** A change counts when, since posting, the
  item's deadline, round, award range, eligibility, or status has changed
  (`ContentDeadline.changed_at`, as `reminders_announce.py` detects it, plus a
  fingerprint of the facts the post showed). Mylo posts the new thread
  `[🚨 Update <Mon D>] <title>` with *What changed* first (old value struck
  through, new value in bold) and tags everyone with a live *Interested*
  reaction. Then it deletes the old thread (or archives it, per Q1). The
  `Announcement` row keeps its history in `superseded_thread_ids`.
- **Conference dates published.** A conference in the slate with no submission
  deadline yet is not announced. Its announcement fires the night it first
  gains one.
- **Nudges (D10).** At each person's chosen lead time: a DM, or a tag in the
  thread. With no choice made, *Interested* means a thread tag 14 days before.
  If the deadline moves, every pending nudge moves with it (the existing
  reminder rebuild).
- **Closing-soon list (D11).** Covers grants and fellowships on the target's
  slate, plus anything the lab saved, closing within 14 days. It is posted as a
  `Daily list` forum post, and yesterday's list is deleted.
- **Close.** After the last deadline passes, the thread is archived and tagged
  `Closed`.

## What a post contains

```
[Grant · Newly relevant]  The Genesis Mission: Transforming Science and Energy with AI
DOE Office of Science · DE-FOA-0003612 · $500K – $16M

Why it matters  Fits Ocean forecasting with deep learning and the Loop Current
                forecasting project …
Can we use this? ✅ Open · deadline Dec 17 (42 days; your buffer is 14)
                ✅ Applicant type: unrestricted
                ⚠️ Interdisciplinary team expected; no national-lab partner yet
Who should look Ana R. (data assimilation) · Marco T. (HPC workflows)
Next step       Decide by Dec 3 whether to build a team.

[👍 Interested] [🔔 Remind me] [🚫 Not for us] [View the call ↗]
```

Update post: same body, title prefixed `[🚨 Update Nov 5]`, a first line tagging
the interested people, and a *What changed* field above *Why it matters*.

Numbers and dates come from code. The model writes only the headline, *Why it
matters*, and *Next step*, and no percentage ever appears.

## The buttons (gateway, persistent ids `ann:<id>:<action>`)

All four go through `integrations/services/gate.py` (identity → rate limit →
permission → entitlement → audit). They live in a new `announcements` cog that
calls `mylo/linking.py`, and the logic lives in `apps/content`.

- **👍 Interested.** Records an `AnnouncementReaction`. Saves the item for
  that person, and for the lab when the lab saves on interest (default on).
  Then **DMs them the full details**: every deadline round, the award, the
  checks, why it fits *them*, and their reminder, with *Change reminder*,
  *Open the thread*, and *Stop following*. The post's button shows the count.
  An unlinked Discord user gets an ephemeral "link your account" prompt, and
  nothing is recorded anonymously. If DMs are closed, a one-time ephemeral
  message says so; the follow and the thread-tag nudge still work.
- **🔔 Remind me.** An **ephemeral picker**: lead times (30, 14, 7, or 2 days,
  several allowed, 14 preselected) and *where* (DM by default, or a tag in the
  thread). It creates a **personal** `ReminderSubscription` through the
  existing reminders code, so it shows on the Reminders page and moves with the
  deadline. Clicking it also counts as *Interested*.
- **🚫 Not for us.** Managers only. Adds a lab-scope `IgnoredItem` (the item
  retires from the slate) and asks for one reason: *wrong topic / not eligible
  / too small / timing*. Reasons are labelled data for tuning the checks;
  nothing re-ranks automatically.
- **View the call.** A link button; the gateway doesn't need to handle it.

## Search links into threads

`/mylo search` already runs the site's search (`search_service.search_for_user`
via `discord_commands.search`). Two changes:

1. `mylo/linking.py` passes the **guild id** of the server the command ran in.
   `_search_row` adds `thread_url` when that item has a live `Announcement` in
   that guild, read through `resolve.py`. The result line shows "💬 Already
   discussed here → #grants thread · 👍 N". A search in DMs, or in a server that
   never announced the item, behaves exactly as it does today.
2. For a result with no thread, a **manager** sees **"Announce to #grants"**.
   It runs steps 2–5 for that one item and records `Announcement.origin = manual`.
   It's subject to the same never-twice rule.

The web search card gets the same link ("Discussed in Discord") when the
reader's lab has a thread for the item.

## Data model (new)

These go under `apps/content` unless noted.

- **`Announcement`:**
  - Target: lab XOR department, with a check constraint.
  - `content` FK (SET_NULL plus a snapshot).
  - `category`, `origin` (`nightly` / `manual`), `state` (`posted` /
    `skipped` / `superseded` / `closed`), `skip_reason`, and `label`.
  - `checks` JSON, `alignment` JSON, `write_up` JSON plus fingerprint, and
    `facts_fingerprint`.
  - `channel_id`, `thread_id`, `superseded_thread_ids` JSON, `posted_at`, and
    `closed_at`.
  - Unique on (target, content).
- **`AnnouncementReaction`:** announcement, user, `kind` (`interested` /
  `not_for_us` / `unfollow`), reason, and created_at. Append-only.
- **`AnnouncementSettings`** (one per org):
  - `enabled`, plus on/off per kind.
  - `daily_cap` (default `-1`, unlimited).
  - `default_nudge_days` (default `14`).
  - `closing_soon_list` (default on for grants and fellowships).
  - `strong_match_tagging` (default **off**).
  - `save_on_interest` (default on), an award preference, and `backfill_done_at`.
- **`apps/integrations`: `DiscordChannelRoute`.** Fields: guild link, purpose
  (`grants` / `fellowships` / `conferences` / `deadlines` / `updates`), channel
  id, channel type, forum tag ids, `created_by_mylo`, `poster_policy`
  (`everyone` / `managers` / `roles`), `poster_role_ids`, `verified_at`, and
  `ok`. The two existing columns on `DiscordGuildLink` migrate into routes and
  are dropped one release later.
- **`DiscordGuildLink`** binds **a department or a lab** (XOR), replacing the
  `OneToOne` to `Lab`. Every accessor stays in `resolve.py`.
- **`content.targets`:** `MatchTarget(kind="department")` from `DeptProfile`.
  Plus `lab_fit.py`, which works like `member_fit.py` but uses lab vectors.

## Phases

Each phase is green on its own and can ship behind
`OPPORTUNITY_ANNOUNCEMENTS_ENABLED` (default off).

**Phase 0: Prototype and sign-off.** The test-server posts, the previews
channel, and the mockup. *Done when* Q1 and Q2 are answered.

**Phase 1: Usability facts.** `usability.py`, the institution type and country
on the org, and the award preference. The checks show on the **web** card as
the "Can we use this?" strip through the shared serializer (personal readers
see the checks that apply to a person). No Discord yet.
*Validate:* `uv run --directory web/backend python -m pytest apps/content/tests/test_usability.py`,
with fixtures from real collector records (an EU call, a US-only call, a
closed round). A missing field yields `unknown`, never `ok`.

**Phase 2: Announcement engine (dry run).** Models,
`announce_opportunities --dry-run` in `manual_all.py`, the agent, the verifier,
the template fallback, the change detector, and the closing-soon composer.
*Validate:* tests for entrant-only selection, never-twice, the roundup guard, a
cap of `-1` meaning unlimited, change detection (a moved date counts; a
re-scrape with identical facts doesn't), and verifier rejection. Then one dry
run against live data, reviewed by hand.

**Phase 3: Discord delivery.**
- `DiscordChannelRoute`, plus the outbox thread-create and thread-delete modes.
- `/setup`'s announcements step: create the channels (opt-in, with a preview)
  or pick existing ones, and set who can start posts.
- The `announcements` cog with all four buttons, the Interested DM, and the
  Remind me picker.
- The update stage, nudges, and the closing-soon list.
- Drift detection for the new routes.

*Validate:* the backend suite plus `uv run python -m unittest discover -s mylo`.
Then a manual smoke run in the test server: opt-in create → roundup → next-night
entrants → Interested (DM arrives) → Remind me (picker, then DM at the chosen
time with a clock override) → a forced change (old thread gone,
`[🚨 Update]` posted, interested people tagged) → closing-soon list replaced the
next morning → close.

**Phase 4: Search links.** Guild id through `linking.py`, `thread_url` on
search rows, the manager "Announce" action, and the web search link.
*Validate:* command tests for a search in an announcing guild, in another guild,
and in a DM.

**Phase 5: Web surfaces.** See below.
*Validate:* `tsc --noEmit` and eslint in `web/app`, then a browser check at
localhost:11050 covering loading, empty, populated, error, permission denied,
and mobile.

**Phase 6: Departments.** The department target, lab-fit, department guild
binding, department posts that name labs, and the department settings card.
This needs its own sub-plan that audits every `target.kind` switch.
*Validate:* target parity tests, the department pipeline under `manual_all.py`,
and pgvector tests on the Compose Postgres.

**Phase 7: Measure and tune.** Track:
- the *Interested* and *Remind me* rates
- *Not for us* reasons
- link-button clicks, through a redirect
- route health

Record these as an experiment under `docs/research/experiments/` before
changing any threshold, including the strong-match cosine. If Q2 turns out to
be a person posting by hand, add a "Mylo, file this" message command.

## Web surfaces (Phase 5): what each replaces

The rule: announcements take over from surfaces that already try to say "what's
new and what's due", instead of adding pages beside them.

| Where | Today | Becomes |
| --- | --- | --- |
| Lab overview, right column | `MyloFoundCard`: a today/week/month/year count matrix per area | **"Announced" panel**: the last few posts, each with kind, title, next deadline, interested count, and a link to its thread. Counts alone don't say what to do; this does |
| Lab overview, right column | `DeadlinesPanel`: the lab's saved items with a date, top 4 | **"Closing soon (14 days)"**: the same list as the morning Discord post, so the web and Discord never disagree. Saved items stay in it |
| Lab feed cards (grants, fellowships, conferences) | Three separate strips: `RecommendedFor` (who it suits), `TeamFitLine` (what the team covers), and the Deadlines dropdown | **One "Can we use this?" strip**: checks as chips, *Advances* (theme and project), *Who should look*, and *Announced* (thread link and interested count). Same data, one block. The Deadlines dropdown stays as the per-round reminder control |
| Lab feeds, bottom | `HiddenByFilters` lists rows the filter rail took out | Adds a **"Mylo held back"** group under it: items that fit but failed a hard check, with the reason. There's no separate page for this |
| Lab Mylo Report | Lists grants, conferences, and fellowships in full | With announcements on, one line per kind pointing to its channel (D6). Papers unchanged |
| Lab settings | `DiscordSyncCard`'s two channel picks (deadline announcements, updates) | **Announcements card**: channel routes (or "Create them for me"), who can start posts, default nudge, closing-soon list on/off, strong-match tagging (off), and award floor. *Send a test post*. `DiscordHealthCard` stays and lists the new routes |
| Department workspace | No research surface at all | **"Opportunities" section**: department grants, fellowships, and conferences with lab-fit chips and department goals. Needs `nav.ts` and `scope-guard.tsx` changes |
| Reminders page | Lists reminders | Unchanged. *Remind me* reminders from Discord appear here because they are ordinary reminders |

## Interfaces that change

- API (record in `docs/api-contract.md`):
  - `GET /api/announcements/?lab=|department=`
  - `GET/PUT /api/announcements/settings/?lab=|department=`
  - `POST /api/announcements/test/` (manager, rate-limited, both slash forms)
  - `POST /api/announcements/create-channels/` (manager, previews first)
  - `usability`, `alignment`, and `announcement` objects on the four
    opportunity serializers
  - `discord_thread_url` on search results
- Discord: forum channels, `/setup` announcement step, persistent `ann:` buttons,
  ephemeral reminder picker, `/mylo search` thread links.
- `manual_all.py`: two new stages and where they sit in the order.
- Docs: `repo-map.md`, `discord-integration.md` (routes, poster policy,
  department binding, required bot permissions: Manage Channels and Manage
  Roles only for opt-in creation and poster overwrites; Manage Threads for
  replacing threads), `architecture.md`.

## Security and trust

- Authorization stays in `apps.accounts.permissions`. A Discord identity
  authenticates; it grants nothing. Every button goes through `gate.py`.
- A department post names labs, never people. A member is named only in their
  own lab's channel.
- **Fellowship eligibility is never posted in a channel.** The post says "2
  people in the lab may be eligible", and each of them gets a DM. Nobody is
  ever named as *ineligible*.
- Tags happen only by the person's own action (Interested, Remind me) or a lab
  setting that is off by default. `allowed_mentions` always lists exactly the
  users being tagged and never `everyone` or roles.
- Audit events for: settings changes, channel creation, poster-policy changes,
  test posts, *Not for us*, manual announce, and thread replacement.
- The agent sees only its closed packet, with no web access and no other lab's
  data.

## Acceptance

- Activation gives exactly one roundup. After that, every slate entrant gets
  its own thread, with no cap by default, and the same item is never announced
  twice.
- A changed call shows up as `[🚨 Update <date>]` within one nightly run. The
  old thread is gone (or archived, per Q1), and only the people who marked it
  Interested are tagged.
- Interested always produces a DM, or an ephemeral note when DMs are closed.
  Remind me reminders fire at the chosen lead time in the chosen place and move
  with the deadline.
- On a day when anything closes within 14 days, `#grants` and `#fellowships`
  hold exactly one closing-soon list each.
- Mylo never creates a channel or changes permissions unless a manager asked.
- Every posted date, amount, and eligibility status traces to a record field.
  Every *Why it matters* cites a theme or project that exists.

## Out of scope

Slack and Teams delivery (the renderer stays channel-neutral). Paper
announcements. Drafting proposals. Cross-lab visibility outside a department.
Any change to ranking: announcements read the slate and never re-rank it, so
the eval harness is untouched.
