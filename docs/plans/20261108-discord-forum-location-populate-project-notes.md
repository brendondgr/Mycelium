# Discord opportunity forums: full location and continent tags, `/mylo populate`, project-aware "Who should look"

Status: **proposed, awaiting approval** (2026-11-08). Working document — delete it
once the work ships and record the outcome in `docs/changelog.md` and
`docs/discord-integration.md`.

## Objective

Three changes to Mylo's opportunity forums (grants, fellowships, conferences):

1. **Location.** A conference post shows its *full* location (venue city, region,
   country) and carries a **continent forum tag** a reader can filter by.
2. **`/mylo populate`.** After `/setup`, a manager fills each forum with the
   target's best open items, N per kind, in one command.
3. **"Who should look" in plain language, grounded in projects.** Each post says
   which project team (or, failing a project, which person) the item suits and
   *what it would do for their work*, instead of the canned "X's research on A
   directly matches the B focus of C".

Out of scope, by the user's decision: tagging people automatically from their
interests.

## What the data says (measured 2026-11-08, live database)

- **Only conferences have a place.** 2,171 grants and 818 fellowships carry no city,
  country or region field at all, so they get no location line and no continent tag.
- **912 conferences**, and their location data is uneven:

  | Records | What they carry | What the post shows today |
  | --- | --- | --- |
  | 380 | `city` + `country_code` + `country` (structured) | "Montreal, Canada" — fine, no continent yet |
  | 369 | only `place_text` ("Ann Arbor, MI", "Austin, Texas, USA", "Seoul, Republic of Korea") | the raw text; **no country fields, so no continent** |
  | 117 | `city` holds a *venue name* ("Royal Agricultural University (RAU)") and `place_text` the full address | **only the venue** — the "just a city" case. `item_host` prefers `city, country` and never falls back to `place_text` when `city` is non-empty |
  | 42 | nothing | nothing |
  | 3 | "Online" / "Virtual" | the word |

  So a continent read from the structured fields alone would tag 381 of 912 (42%).
  `place_text` has to be parsed for the rest.

## Decisions to confirm (recommendation first)

1. **Populate semantics — top up to N** (recommended): `count` is how many of each
   kind a forum should carry; items already posted there count, so running it twice
   posts nothing and asking for more later tops up. *Alternative:* add N more on
   every run.
2. **Retag existing conference threads with their continent — yes** (recommended):
   a one-off pass that patches `applied_tags` on live threads, so filtering works on
   what is already there. *Alternative:* new posts only.
3. **Rewrite existing posts' "Who should look" — no** (recommended): the new rubric
   applies to new posts; rewriting live threads re-bills the model for every one.
4. **Grants and fellowships stay untagged by place** — there is no location data to
   tag from. (Eligibility-by-country is a different question and not this plan.)

## Working-tree state before this plan

Drafts for phases 1 and 2 were written before the plan was asked for. They are
**uncommitted, untested, and incomplete**:

- `tools/retrieval/geography.py` (new) — continent by ISO code or country name;
  does **not** yet parse `place_text`.
- `tools/delivery/discord_announcements.py`, `tools/delivery/announce.py` — continent
  tags on the conference and department forums, a continent line in the embed,
  `continent` on the conference snapshot; `item_host` not yet fixed.
- `tools/delivery/announce_populate.py` (new), `mylo/linking.py`, `mylo/mycelium.py`
  (`db_long`), `mylo/bot/cogs/mylo_commands.py`,
  `web/backend/apps/integrations/services/gate.py` (`ann_populate`) — the populate
  command.

Each phase below starts by reviewing its draft against the plan rather than trusting
it. Phase 3 has not been started.

## How every phase ends

Every phase ends in the same three steps, and nothing moves to the next phase until
they pass:

1. **Validate** — run the phase's commands (listed in each phase) and read the
   output. A failing test that is not on the known pre-existing list (`MEMORY`:
   `test_site_and_resume_merge`, `test_high_signal::test_command_delivers_when_enabled`,
   the two `test_collect_ingest` pruning tests) stops the phase.
2. **Record** — add a `docs/changelog.md` entry (correlation ID
   `20261108-discord-forums-<phase>`) and update the docs the phase made wrong.
3. **Commit** — one focused commit per phase, staging only that phase's files.
   Other sessions edit this checkout (`docs/changelog.md` and
   `docs/research/RELATED_WORK.md` already carry someone else's uncommitted edits),
   so commits are made from a dedicated `git worktree` on a branch, never with
   `git add -A` in the main checkout, and the changelog hunk is staged on its own.

## Phase 1 — Full location and continent tags

**Build**

- `tools/retrieval/geography.py`: one function, `place_for(metadata) → Place(display,
  country, continent)`, that every surface uses.
  - `display` is the richest honest string: structured `city, country` when both
    exist and `city` is a real city; otherwise `place_text`, trimmed (trailing
    period, postcode noise), with the country appended when it was parsed but not
    written. Never a venue name alone when `place_text` says more.
  - `country` comes from the structured code first, else from the tail of
    `place_text`: country names and aliases ("USA", "UK", "Republic of Korea"), US
    states and their two-letter codes → United States, Canadian provinces → Canada.
    No fuzzy matching: an unrecognised tail ("Saudi Arabi") gets no country and no
    continent, never a guess.
  - `continent` from the country; *Online* for a virtual-only event (hybrid events
    keep their physical continent).
- `tools/delivery/announce_facts.item_host` uses `place_for(...).display` for
  conferences — the fix for the venue-only line.
- Forum tags: *North America, South America, Europe, Africa, Asia, Oceania, Online*
  added to the conferences forum (5 → 12 tags) and the department forum (9 → 16),
  inside Discord's 20 per forum. A thread carries at most 5 tags, so the order kept
  is: label or kind, status (*Updated*/*Closed*), continent, then department
  reasons. `ensure_forum_tags` adds the new tags to existing forums on the next post
  (needs Manage Channels on a forum Mylo didn't create; without it, posts go out
  untagged, as today).
- The embed's description reads `**Ann Arbor, Michigan, United States** · 🌎 North
  America`.
- Retag pass (decision 2): `manage.py retag_announcement_threads [--dry-run]`
  queues one `thread_update` patch of `applied_tags` per live conference thread
  (no rename, no reply, no edit), through the outbox.
- The web app's conference filter keeps its own continent table
  (`continentOf` in `web/app/src/components/portal/sections/conference-filters.tsx`);
  the same six names are used, and the duplication is noted in both files. Making
  the web read the backend's continent is a follow-up, not this plan.

**Validate**

- New tests `tools/delivery/tests/test_geography.py`: each of the five data shapes
  in the table above, including the venue-name case and an unrecognised country.
- Tests for `_post_tags` (lab and department, five-tag cap keeps the status tag) and
  for the embed description.
- `uv run --project web/backend pytest tools/delivery/tests -q` (plus the retrieval
  tool's tests for `geography.py`).
- Measured on the live corpus with a read-only shell script: how many of the 912
  conferences now get a full location and a continent. Recorded as an experiment
  (`make new-experiment SLUG=conference-continent-coverage`, then
  `make validate-research`), since CLAUDE.md requires every reported number to live
  there.
- `manage.py retag_announcement_threads --dry-run` lists what it would change.

**Commit** — "Discord forums: full conference location and continent tags".

## Phase 2 — `/mylo populate`

**Behaviour**

- `/mylo populate count:<1–10, default 5> [target:<lab or department>]`, server
  only. `target` autocompletes the server's bindings and is needed only when the
  server holds more than one.
- Authority: new gate action `ann_populate` (manage right + `bot_server` add-on,
  the same as `/setup`), and `announce.target_entitled` for the
  `OPPORTUNITY_ANNOUNCEMENTS` feature. Refuses while announcements are off or not
  yet seeded — the activation seed is what marks the rest of the slate as seen;
  populating before it would make the next nightly run announce the backlog again.
- Walks each kind's slate best position first, for the forums this binding routes:
  - posted here with a live thread → counts toward `count`;
  - posted to another server of the same target but not here → posted here;
  - held back, closed, or deleted by hand → skipped (a decision populate keeps);
  - never announced or passed over at activation → the nightly path's checks,
    alignment and editor, labelled *Already open*, recorded with origin *manual*
    and the manager who asked; an editor "not worth a post" is recorded as skipped
    and the walk moves on.
- Model budget: at most `2 × count` editor calls per kind.
- Ceiling: a forum can't carry more than the target's slates hold (grants and
  conferences 10 per theme, fellowships 5); the reply says when it ran out.
- Runs off the bot's shared database thread (`mycelium.db_long`) so a few minutes of
  model calls don't stall every other command; the interaction is deferred and
  answered once, within Discord's 15-minute window.
- Audit log entry `announcements.populated` (binding, count, posted per kind).
- The `/setup` "Turn on" confirmation mentions `/mylo populate`.
- Up to 30 new threads at once go through the outbox (batch of 50, Discord's
  per-route rate limits honoured by the outbox's retry).

**Validate**

- Tests `tools/delivery/tests/test_announce_populate.py`: refusal when off /
  unseeded / unentitled / not a manager; top-up idempotency (second run posts
  nothing); held-back and hand-deleted items skipped; editor skip moves on; budget
  stops at `2 × count`; department filter (department-level calls only); audit row.
- Gate test for `ann_populate` in the integrations suite.
- `uv run --project web/backend pytest tools/delivery/tests web/backend/apps/integrations -q`.
- The bot imports and registers the command: load the cog in a test bot and list
  `/mylo`'s subcommands.
- Live check on a test server: `@Mylo sync global` (a new subcommand needs a
  global sync), run `/mylo populate count:3`, confirm the threads, run it again and
  confirm nothing new is posted.

**Commit** — "Discord: /mylo populate fills a server's opportunity forums".

## Phase 3 — Project-aware "Who should look"

**Today:** `announce.align` hands the editor up to three people from
`signals["member_fit"]`, each with member_fit's one-line reason, and the project
*names* only. The editor tends to echo that reason, which is where the canned
sentence comes from. `align` also includes any project marked `suggested`, without
checking `share_in_lab_reports` — a channel post naming an unshared project breaks
the "a lab surface shows only shared projects" rule. That is fixed here.

**Build**

- `announce.align` (labs): `project_teams` — the lab's **shared, non-archived**
  projects whose own score marked this item `suggested`, each with an id (`j1`…),
  name, a focus line (≤200 characters, from `project_interests`) and its members'
  display names. Each person gains their shared projects and a short interest
  summary (`member_fit._profile_text`).
- `announce_editor`:
  - The packet lists project teams and people with that context.
  - The prompt's rule for *Who should look*: when the item fits a project, name the
    project (by its id) and say in one plain sentence what the opportunity would do
    for that project's work; otherwise name a person and ground the sentence in
    their stated interests. Do not restate the match ("X's research on A matches
    the B focus of C"); say what they would do with it.
  - The verifier accepts project ids as well as people ids, keeps the no-digit
    rule, caps entries at four, and still rejects anyone not offered.
  - The template fallback lists matched projects first, then people.
  - `RUBRIC_VERSION` `ann-1` → `ann-2`. Write-ups are keyed on it, so new posts use
    the new rubric and existing posts are untouched (decision 3).
- Rendering: the Discord embed shows a project as `**Name** project (Alice, Bob) ·
  why`; `announcement_views` (web) and `manage.py announce_opportunities` show the
  same entries.
- Departments are unchanged: they name labs, never people or projects.
- `tools/recommendation/member_fit.py` is unchanged — its reason line also feeds the
  web card, and changing it is a separate decision.

**Validate**

- Tests: an unshared or archived project never reaches the packet; a project-fit
  item yields a project entry; a no-project item yields a person entry; the verifier
  accepts `j` ids, rejects an unknown id and a digit; the template fallback;
  embed rendering; the web serializer.
- `uv run --project web/backend pytest tools/delivery/tests -q`.
- Prose check on real data: `manage.py announce_opportunities --dry-run` for a lab
  with shared projects, read every write-up, and record before/after examples in
  the changelog entry. If the editor's reply fails the verifier on more than a few
  items, stop and adjust the prompt before committing.
- `make test` once, as the last gate before the final commit.

**Commit** — "Announcements: project-aware, plain-language Who should look".

## Docs that change

- `docs/discord-integration.md` — continent tags, the location line, `/mylo
  populate`, the new *Who should look* shape.
- `docs/repo-map.md` — `tools/retrieval/geography.py`,
  `tools/delivery/announce_populate.py`.
- `docs/changelog.md` — one entry per phase.
- This plan — deleted when phase 3 ships.

## Exclusions

- Automatic tagging of people by interest (deferred by the user).
- Location for grants and fellowships (no data).
- Changing member_fit's reason line, or rewriting existing threads' write-ups.
- Moving the web app's continent table onto the backend's.
