# Plan 02 — Discord Server Listening

**Status:** draft. **Depends on:** Plan 01. **Unblocks:** Plans 03, 04, 06.
**Correlation ID:** `20260917-ambient-profile-02`

## Objective

Mylo listens to the **whole server** a lab has activated, with consent, and
hands what it hears to the evidence ledger. People talk normally. Nobody
types a command to be understood. Commands, a message action, and the DM inbox
remain available as explicit options, but they are not the design.

## What Discord allows, and when

Verified 2026-09-17 (README, "Discord platform facts"):

- **Without any privileged intent** the bot receives the content of: direct
  messages to it, messages that @mention it, and messages a user selects through
  a context-menu command. It also receives reactions on its own messages.
- **Reading everything else in a channel** requires the **Message Content**
  intent. It is a portal toggle until the app reaches 10,000 total users, then
  a review with annual renewal.

The staging below uses the first set to prove the extractor before the second
is turned on, so a review, if it comes, is applied for with a working feature.

## Consent model

Three layers, each independent, all default off:

1. **Server.** A linked lab manager turns listening on for the server through
   `/setup`, which gains a third section beside the two channel pickers:
   *Listening*: on / off, and an exclusion list of channels Mylo must never
   read. This creates the `Source` row (Plan 01). Turning it off purges the
   raw buffer for that source immediately.
2. **Person.** Default **off**. Each linked member chooses, in the web
   settings (Plan 07) and in a DM from Mylo, whether their own messages may be
   observed at all, and whether personal-kind observations (career,
   preferences) may be drawn from lab channels or only from DMs. Off means
   their messages are dropped at the adapter, before the buffer, and the
   adapter records only a count. Opting out later is one click and offers
   "also delete what Mylo has summarised about me" (Plan 01, step 9). The
   settings page states, in these words: *Mylo does not keep your messages. It
   keeps short summaries of interests and project changes, and only after you
   confirm them do they affect anything.*
3. **Channel.** Managers can exclude channels; any member can ask Mylo in a DM
   to exclude a channel they are in, and the manager is told.

A visible marker: when listening is on, Mylo posts one pinned message in the
server's updates channel saying it is, which channels are excluded, that
messages are not stored, and how to opt out or in. Discord shows the bot in
the member list regardless. A member who has not opted in is told once, by
DM, that the server is listening and that their messages are being dropped
unless they choose otherwise.

## Steps

1. **Stage A — the paths that need no intent.** Add a `listen` cog under
   `mylo/bot/cogs/listen.py` handling `on_message` for DMs to Mylo and for
   messages mentioning Mylo in an activated server, plus `on_raw_reaction_add`
   on Mylo's own messages. Each is forwarded to the backend as a raw message
   through the Discord adapter (Plan 01). This ships first and exercises Plans
   03 to 06 end to end on real conversation.

2. **The DM inbox is a conversation, not a command.** A person can DM Mylo
   anything: "we dropped the simulation approach", "I keep reading about
   annotation cost lately". No syntax. The message is a raw message like any
   other; the reasoning agent decides what it means. Mylo replies briefly and
   in plain language (Plan 06 owns the dialogue rules).

3. **Optional explicit paths, kept small.** `/mylo note text:` and `/mylo
   update project: text:` write the same raw message with `explicit = true`
   so the agent can weight it higher. A context-menu action *Tell Mylo about
   this* attaches any message to the ledger with `explicit = true`. These are
   conveniences for people who like them; nothing depends on them.

4. **Stage B — server-wide listening under the intent.** Enable Message
   Content in the portal and in `client.py` intents behind a config flag
   `MYLO_LISTEN_ENABLED`. The listen cog then receives every message in
   activated servers, applies the two server-side gates — server on, channel
   not excluded — and forwards the rest. The backend's ingest endpoint then
   applies the person gates before anything enters the buffer: an active
   `DiscordIdentity`, a paid **effective** tier (own subscription or paid
   lab, resolved as the caps are), and opted in. A message failing any gate
   is discarded on arrival with no record beyond an aggregate daily count per
   server (OD-A2). Server members without a Mycelium account are never
   involved.
   Discord edits and deletions (`on_raw_message_edit`, `on_raw_message_delete`)
   are forwarded as reconciliation events (Plan 01, step 8).

5. **The buffer and the handoff.** The cog does no analysis. It batches raw
   messages and posts them to a backend endpoint under `/api/ambient/ingest/`
   authenticated with the bot's service credential, the way `mylo.reporting`
   already talks to the backend over REST. On backend outage it spools to disk
   and retries; the nightly extraction is batch anyway, so latency of minutes is
   fine.

6. **Rate and volume.** Discord will deliver far more than is useful. The
   adapter drops: bot messages other than Mylo's, messages under a minimum
   length with no link, and channels flagged as social by the manager. Volume
   per source per day is recorded on the `Source` so the reasoning agent's
   window sizes can be tuned from data.

7. **Eligibility is decided on the backend, once, on arrival.** The cog
   forwards the snowflake and nothing else about identity. The ingest
   endpoint has the database and resolves eligibility there, so an opt-out
   or a lapse takes effect on the very next message. No cache, no polling.
   Plan 03 resolves the user from the same snowflake.

8. **Threads and forums.** Thread and forum-post messages carry their parent
   ids so Plan 03 can treat a thread as one conversation and a forum post
   title as an attribution hint. No binding is required for either.

9. **Observability.** Extend `/mylo health` with listening state per server and
   the buffer depth; the run analytics report gains a line for messages heard,
   dropped by consent, and forwarded.

10. **Docs.** Update `docs/skills/discord-bot.md` (the intent threshold), the
    `/setup` description in `docs/repo-map.md`, and `docs/architecture.md`.

## Acceptance

- With listening off, a message in a lab channel produces no raw row.
- With listening on and a person opted out, their messages produce no raw row.
- A DM to Mylo produces a raw row with `explicit = false` and a reply within
  the dialogue rules of Plan 06.
- Turning listening off purges the raw buffer for that source.

## Open decisions

- **OD-02a** Whether Stage B waits for Plan 10's first result on Stage A data.
  Recommendation: yes; the intent is easier to justify with a measured feature.
- **OD-02b** Whether the pinned "Mylo is listening" marker is mandatory.
  Recommendation: mandatory; the whole feature rests on people knowing.

## Discussion gate

No step in this plan is implemented until the implementing agent has presented,
and the owner has approved, a short design brief: the files and models it will
touch, every migration, every prompt and what happens when the model is
unavailable, every
default value and setting name, and what is deliberately not being done. A
deviation discovered mid-implementation stops the work and reopens the brief.
