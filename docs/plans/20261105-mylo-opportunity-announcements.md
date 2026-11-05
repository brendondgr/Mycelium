# Mylo Opportunity Announcements — plan

Status: **proposal, not started** (2026-11-05). Prototype posts live in the
Discord test server (`1507798835311673616`, category *Mylo Opportunities
(prototype)*). The web mockup is linked from the session that wrote this.

## Objective

Make Mylo announce **individual** grants, fellowships, and conferences to labs
and departments, each in a channel for its kind, with every post saying whether
the item is *usable* (open, eligible, feasible before its deadline) and *why it
matters* to that lab's or department's research goals. Then keep each announced
item alive: deadline nudges, moved dates, and "dates now published" go into that
item's own thread, not into a fresh broadcast.

Why: the lab channel today receives one long daily digest plus a PDF. People skim
or mute it, so a fitting call is easy to miss among papers. Funding and venues
are the items a lab has to *act on*, and they each have a date. They deserve
their own short, actionable post, in a place people can follow.

What stays the same: papers stay in the daily or weekly report and the updates
channel. This plan changes how opportunities reach a lab. It does not touch
paper delivery.

## Decisions this plan assumes (confirm or overturn)

| # | Decision | Recommendation | Why |
| --- | --- | --- | --- |
| D1 | Channel shape | **One forum channel per kind** (`#grants`, `#fellowships`, `#conferences`) under one Mylo category; plain text channels as fallback | A forum post *is* one item: it has a title, tags (`Closing soon`, theme), its own discussion, and followers. Updates land in the thread, so the channel list stays one row per item |
| D2 | What counts as "new" | **Entered the target's per-theme slate *and* never announced to that target before** | Keeps the slate rule (new = what the reader is shown, not what was ingested). The post labels **New call** (source posted ≤ 14 days ago) apart from **Newly relevant** (older call that entered because the profile changed) |
| D3 | Departments | **A real `department` match target over `DeptProfile`, for grants / fellowships / conferences only**, plus a "which labs should look" layer (lab-fit, the department version of member-fit) | Departments have no feeds today. A union of their labs' slates would announce the same call N times and miss department-level calls (training grants, infrastructure, centres) |
| D4 | "Agent" scope | **A bounded editor agent**: it chooses whether to announce and writes the post, using read-only tools over facts the code has already computed. It may drop an item; it may not add one. It never writes a date, an amount, or an eligibility verdict | Same rule as member-fit and the weekly verifier: the model explains, the code decides facts. It keeps posts trustworthy and testable |
| D5 | Volume | **At most 3 posts per channel per day** (configurable); the rest roll into one "Also entered today" post. On first activation, **one "What's open now" roundup** instead of announcing the whole slate | Without the backfill guard, activation would post ~40 items at once, which trains people to mute the channel |
| D6 | Opportunities in the digest | Once announcements are on for a lab, the digest keeps **one line per kind** ("2 grants announced → #grants") instead of re-listing them | The same item in two places is how people learn to ignore one of them |
| D7 | Mentions | **No pings by default** (matches `lab_digest`). Optional per-kind role mention for posts the code marks *closing soon* | Opt-in only. A post that pings people unasked becomes a summons, not an update |
| D8 | Tier | New feature `OPPORTUNITY_ANNOUNCEMENTS`, **Lab and Canopy (department)**, read through `billing.entitlements`; also requires `BOT_SERVER` | Org-scoped Discord delivery, same family as the lab digest |

Open question: the brief says "Manny" is posting the papers people don't read.
Confirm whether that is Mylo's current digest or a person posting by hand. If
it's a person, the import path in Phase 6 matters more.

## How an announcement is made (the nightly path)

Runs in `manual_all.py` after scoring, member-fit, and team-fit, before reports
are sent. The new command is `announce_opportunities`. Each stage, in order:

1. **Select.** For each lab or department target with announcements on: take
   the entrants to its grant, fellowship, and conference slates
   (`slates.py`, which already diffs each theme against the previous run). Drop
   anything already in `Announcement` for that target. Retired-then-re-entered
   items are not re-announced. They can get a thread update ("back on your
   list") if the old thread still exists.
2. **Check usability. Code only, no model.** This is the new
   `apps/content/usability.py`. Every check gives a status (`ok` / `warn` /
   `block` / `unknown`), a short label, and the source field it read:
   - **Open:** status and next deadline round (`liveness.py`,
     `deadlines_projection.py`).
   - **Feasible:** days left against the target's buffer (`matchers/timeline.py`,
     `timeline_settings.effective_timeline`).
   - **Applicant eligibility:** the collector's `applicant_types` and the
     funder's region, checked against the org's institution type and country.
     Example: an EU Horizon call against a US public university gives `warn`,
     "EU-led consortium; US partners usually join unfunded". Needs a new
     institution-type and country fact on the org (from the verified
     institution directory).
   - **Award fit:** floor and ceiling from the record, against an optional org
     preference (min/max award).
   - **Fellowships:** which members pass the existing eligibility rule engine
     (`fellowships.py`). For a department: how many members across its labs.
   - **Team coverage:** the existing team-fit line (`collab/team_fit.py`).
   A `block` (closed, deadline already inside the buffer, ineligible applicant
   type) stops the item: it is logged on the `Announcement` row as `skipped`
   with the reason, and never posted.
3. **Align to goals.** Facts again, not prose. Which theme it entered (cluster
   attribution), which projects match it (project slates and matchers), and which
   members (member-fit) or labs (lab-fit, D3) it suits. For a department, which
   department goals or themes it serves.
4. **Edit. The agent.** The input is a closed packet: the item's précis, the
   checks from step 2, the alignment from step 3, and the org's themes and
   goals. The output is a schema:
   `{announce: bool, headline, why_it_matters (≤ 2 sentences, must cite a theme
   or project id), who_should_look[], next_step, skip_reason?}`.
   Tools are read-only (`get_item`, `get_project`, `get_member_profile`) so the
   agent can look things up but not fetch the web. Write-ups are keyed on
   (item, target, rubric version, theme areas fingerprint), like the existing
   verdicts, so a re-run costs nothing. Free-text claims run through a verifier
   (the `weekly_verify.py` pattern): every id it cites must exist in the packet,
   and no digit may appear in the agent's prose. A failed verify falls back to a
   deterministic template. It does not skip the item.
5. **Throttle.** Order by slate position, then post the top N per channel
   (D5). The rest go in one rollup post.
6. **Render and enqueue.** `discord_announcements.py` builds a forum thread
   (title, applied tags, embed, buttons) and puts it on the outbox with dedupe
   key `announce:<target>:<item>`. Then it writes the `Announcement` row.
   The outbox gains a **create-forum-thread** send mode
   (`POST /channels/{forum}/threads`) and records the thread id. Plain text
   channels use the existing message path.

Then, as a separate stage, **`announce_opportunity_updates`** runs for already-announced
items whose thread is still open:

- Deadline nudges at T-30, T-14, and T-7 by default, and T-2 if anyone marked
  the item *Interested*. They post **in the thread**. The `Closing soon` tag
  goes on at T-14.
- A moved deadline, or "now confirmed" (`ContentDeadline.changed_at`, reusing
  `reminders_announce.py`'s detection), posts in the thread.
- Conference **dates or CFP published.** When a conference already in the
  slate gains its first submission deadline, the announcement fires then.
  Before that point it isn't actionable and is not announced.
- After the last deadline passes, the thread is archived and tagged `Closed`.

Existing reminders keep working unchanged. Clicking *Remind us* on an
announcement just creates a normal lab `ReminderSubscription`.

## What a post contains

```
[Grant · New call]  The Genesis Mission: Transforming Science and Energy with AI
DOE Office of Science · DE-FOA-0003612 · $500K – $16M

Why it matters  Fits Ocean forecasting with deep learning and the Loop Current
                forecasting project: the call funds AI-for-science teams that
                pair domain models with DOE computing.
Usable?         ✅ Open · next deadline Dec 17 (42 days; your buffer is 14)
                ✅ US public universities eligible
                ⚠️ Interdisciplinary team required; you cover method and data,
                   not an HPC partner
Who should look Ana R. (data assimilation) · Marco T. (HPC workflows)
Next step       Decide by Dec 3 whether to assemble a team.

[👍 Interested] [🔔 Remind us] [🚫 Not for us] [Open in Mycelium ↗]
```

Rules: numbers and dates come from code. The model writes only the headline,
"why it matters", and the next-step sentence. There is never a percentage,
following the same "no scores in prose" invariant as the reports.

## Feedback from the channel

The gateway handles the buttons with persistent custom ids `ann:<id>:<action>`
in a new cog. All four actions go through `integrations/services/gate.py`.
Each action:

- **Interested:** records `AnnouncementReaction` (user, kind). It also saves the
  item to the lab (`SavedOpportunity`, lab scope), and the post's footer shows
  the count ("3 interested"). Unlinked Discord users get an ephemeral "link your
  account" prompt. Nothing is recorded anonymously, because a count you can't
  attribute can't be trusted or undone.
- **Remind us:** opens an ephemeral picker for lead time, then creates a lab
  reminder into the deadlines channel.
- **Not for us:** managers only. It applies a lab-scope `IgnoredItem` (retires
  it from the slate) and asks for a one-tap reason (*wrong topic / not eligible
  / too small / timing*). The reasons are labelled data for tuning the
  usability checks later. Nothing re-ranks automatically.
- **Open in Mycelium:** a link button to the item in the lab feed. It needs no
  gateway handling.

## Data model (new)

Under `apps/content` unless noted:

- `Announcement`: target (lab XOR department, plus a check constraint),
  `content` FK (SET_NULL plus a snapshot, like `SavedOpportunity`), `category`,
  `state` (`posted` / `skipped` / `rolled_up` / `closed`), `skip_reason`,
  `label` (`new_call` / `newly_relevant`), `checks` JSON (step 2 output),
  `alignment` JSON, `write_up` JSON plus fingerprint, `channel_id`, `thread_id`,
  `message_id`, `posted_at`, `closed_at`. Unique on (target, content).
- `AnnouncementReaction`: announcement, user, kind, reason, created_at.
  Append-only: undoing a reaction adds a new row.
- `AnnouncementSettings` (one per org): enabled, per-kind on/off, daily cap,
  nudge offsets, award preference, closing-soon role id per kind, and
  `backfill_done_at`.
- `apps/integrations`: `DiscordChannelRoute` (guild link, purpose, channel id,
  channel type, forum tag ids JSON, `verified_at`, `ok`). Purposes:
  `grants` / `fellowships` / `conferences` / `deadlines` / `updates`. The two
  existing columns (`announcement_channel_id`, `updates_channel_id`) migrate
  into routes, and the old columns get dropped one release later.
- `DiscordGuildLink` must bind **a department as well as a lab** (lab XOR
  department, replacing the `OneToOne` to `Lab`). All accessors stay in
  `resolve.py`, which is the AST-enforced boundary.
- `content.targets`: `MatchTarget(kind="department")` from `DeptProfile`,
  scored for grants, fellowships, and conferences only. A lab-fit annotator
  (`lab_fit.py`) works like `member_fit.py`, using lab vectors in place of
  member vectors.

## Phases

Each phase ends green on its own and can ship behind the feature flag
`OPPORTUNITY_ANNOUNCEMENTS_ENABLED` (default off).

**Phase 0: Prototype and sign-off (this session, no product code).** Sample
posts in the test server, the web mockup, and decisions D1–D8 confirmed.
*Done when* you approve a post shape and a channel shape.

**Phase 1: Usability facts.** Add `usability.py` with the checks, institution
type and country on the org, and award preference. The checks also show on the
**web** card as a "Can we use this?" strip (D-parity: the same serializer
serves personal, lab, and project feeds; personal readers get the checks that
apply to a person). No Discord yet.
*Validate:* `uv run --directory web/backend python -m pytest apps/content/tests/test_usability.py`,
plus fixtures from real collector records (EU call, a US-only call, a closed
round). The check should be `unknown` (never `ok`) when a field is missing.

**Phase 2: Announcement engine (dry-run).** Add the models,
`announce_opportunities` in `manual_all.py` with `--dry-run` as the default, the
editor agent, its verifier, and the template fallback. Dry-run writes
`Announcement` rows and renders the posts to a file without sending them.
*Validate:* tests for selection (entrant-only, never twice, backfill guard),
throttle, the verifier's rejections, and fallback; one
`manage.py announce_opportunities --lab <slug> --dry-run` against live data,
reviewed by hand.

**Phase 3: Discord delivery.** Add `DiscordChannelRoute`, the outbox forum-thread
mode, `/setup` extended to pick the three forum channels (or have Mylo
**create** the category and forums when it has Manage Channels, with a preview
of exactly what it will create), the reaction cog, and the update stage. Drift
detection covers the new channels.
*Validate:* backend suite plus `uv run python -m unittest discover -s mylo`, then
the manual smoke against the test server: activate → roundup → next-night
entrants → button round-trips → T-14 nudge (with a clock override) → moved
deadline → close.

**Phase 4: Web surfaces.** See below.
*Validate:* `tsc --noEmit` and eslint in `web/app`, then a browser check at
localhost:11050 covering loading, empty, populated, error, permission-denied,
and mobile.

**Phase 5: Departments.** Add the department target, lab-fit, department guild
binding, department announcements ("Labs that should look: Ocean ML Lab,
Coastal Hazards Group"), and the department settings card. This is the largest
phase because it adds a target kind. It needs its own sub-plan before code,
with an audit of every `target.kind` switch.
*Validate:* target parity tests, the department pipeline under
`manual_all.py`, and pgvector tests on the Compose Postgres.

**Phase 6: Measure and tune.** Track per-post reads proxy (thread opens are not
exposed, so use reactions plus link-button clicks through a redirect),
*Interested* rate, *Not for us* reasons, and the mute signal (route
`ok=False`). Record this as an experiment under `docs/research/experiments/`
before changing any threshold. If the papers people ignore come from a person
posting by hand (the "Manny" open question), add an optional "Mylo, file this"
message command that turns a pasted link into an announcement.

## Web surfaces (Phase 4)

1. **Lab settings → Discord → Announcements card.** Shows each kind with its
   channel (or "not set"), forum vs text, the daily cap, nudge offsets, the
   closing-soon role, and a **Send a test post** button (one sample per kind,
   marked as a test). It shows live route health from `DiscordChannelRoute.ok`.
   Managers can edit it; members see it read-only.
2. **Lab overview → "Announced" panel.** The last 14 days of posts: kind, title,
   label, interested count, next deadline, and a link to the Discord thread.
   Skipped items are listed under "Mylo held back" with their reason, which is
   the honesty surface. Empty state: Mylo with "Nothing new cleared the bar this
   week."
3. **Feed card "Can we use this?" strip.** The step-2 checks as chips (✅ open ·
   ⚠️ consortium · ✅ 42 days) plus the alignment line ("Ocean forecasting ·
   Loop Current project"). It never shows a percent, consistent with the
   no-verdict app rule.
4. **Department workspace → "Opportunities" section.** Department grants,
   fellowships, and conferences with lab-fit chips. This is the department's
   first research surface; `nav.ts` and `scope-guard.tsx` need it added.

## Interfaces that change

- API (add to `docs/api-contract.md`):
  - `GET /api/announcements/?lab=|department=`
  - `GET/PUT /api/announcements/settings/?lab=|department=`
  - `POST /api/announcements/test/` (manager, rate-limited), registered with
    and without the trailing slash
  - `usability` and `alignment` objects on the four opportunity serializers
- Discord: forum channels, `/setup` routes, persistent `ann:` buttons.
- `manual_all.py`: two new stages and their place in the order.
- Docs: `repo-map.md` rows for every new module, `discord-integration.md` for
  routes and department binding, `architecture.md` for the target kind.

## Security and trust

- Authorization stays in `apps.accounts.permissions`. A Discord identity
  authenticates the user and grants nothing. Every button goes through
  `gate.py` (identity → rate limit → permission → entitlement → audit).
- A department post names labs, never people. Member names appear only in that
  lab's own channel. This is the same scoping as `member_fit`.
- **Fellowship eligibility is never posted in a channel.** Eligibility rests on
  citizenship and career stage. The channel post says "2 people in the lab may
  be eligible", and each of them gets a DM (with `BOT_DM`). Naming who is *not*
  eligible is never allowed.
- Audit events: settings change, test post, *Not for us*, and route bind or
  unbind.
- The agent sees only the closed packet. It gets no web access and no other
  lab's data.

## Acceptance

- A lab that turns announcements on gets exactly one roundup. After that it gets
  only slate entrants, at most N per channel per day, and never the same item
  twice.
- Every posted fact (date, amount, eligibility status) traces to a record field.
  Every "why it matters" cites a theme or project that exists.
- A blocked item never posts and is visible under "Mylo held back".
- Deadline changes reach the item's thread within one nightly run.
- Turning a kind off, unbinding a channel, or a lapsed plan stops delivery
  quietly at the next run. No error is posted to the lab.

## Out of scope

Slack and Teams delivery (the renderer is channel-neutral so it can follow
later). Paper announcements. Auto-applying or drafting proposals. Cross-lab
visibility outside a department. Any change to ranking: announcements read the
slate and never re-rank it, so the eval harness is untouched.
