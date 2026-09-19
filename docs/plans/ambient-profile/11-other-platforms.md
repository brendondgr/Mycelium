# Plan 11 — Other Platforms: Slack, Teams, Transcripts

**Status:** draft. **Depends on:** Plans 01–10 proven on Discord.
**Correlation ID:** `20260917-ambient-profile-11`

## Objective

Add a second and third conversation platform without touching attribution,
extraction, deliberation, validation, or reports. Each platform is an adapter
that writes the Plan 01 raw-message shape and resolves platform identities to
`speaker_external_id`. If a plan below needs to change anything outside
`apps/ambient/adapters/` and `apps/integrations/`, the abstraction in Plan 01
was wrong and gets fixed there first.

## Slack

1. **Identity and workspace binding.** A `SlackIdentity` (Slack user id is the
   key) and a `SlackWorkspaceLink` (workspace ↔ lab) mirroring the Discord
   models, linked by the same activation-code flow from the web.
2. **Events.** Slack's Events API over HTTPS (`message.channels`,
   `message.groups` for private channels the app is invited to, `message.im`
   for DMs, `app_mention`, `message_changed`, `message_deleted`). The bot
   needs a public endpoint with signature verification; it lives in the backend
   as `/api/integrations/slack/events/`, not in a gateway process.
3. **Consent.** Slack's model is channel membership: the app only sees channels
   it is added to. The Plan 02 layers map directly: server → workspace on/off,
   channel → invite the app or not, person → the same opt-in.
4. **The DM dialogue** (Plan 06) over Slack DMs and Block Kit buttons as the
   optional shortcut.
5. **Reports.** The weekly and its "what changed" section post to a lab
   channel and DM through a Slack outbox mirroring `DiscordOutboxMessage`.

## Teams

6. **Identity and team binding.** Azure AD object id as the key; a team ↔ lab
   link via the Teams app installation flow.
7. **Events.** Bot Framework messaging endpoint; channel messages require the
   app be installed in the team and, for reading without a mention, resource-
   specific consent (`ChannelMessage.Read.Group`) granted by a tenant admin.
   Model that as the Plan 02 "server" consent held by an admin rather than a
   lab manager.
8. **Same adapter contract; same dialogue over Teams personal chat.**

## Transcripts (Zoom, Teams meetings, Discord voice)

9. **A transcript is one window** with speaker labels, at a much lower
   per-sentence influence (`AMBIENT_TRANSCRIPT_WEIGHT`), because spoken
   speculation is cheap and abundant.
10. **Meeting-derived developments only.** From a transcript the extractor is
    asked for decisions, blockers, and commitments — the project-development
    kind — and not for interests, until Plan 10 shows interest extraction from
    speech is precise enough.
11. **Consent** is per meeting: the organiser enables Mylo's transcript access;
    every participant who is a Mycelium user is told; non-users' and
    free-tier participants' speech is dropped before the buffer (their turns
    are removed from the transcript window), as OD-A2 requires.
12. **Ingestion** is a file upload or a recording-completed webhook, written as
    a `Source` of kind `transcript` with a short raw retention.

## Cross-platform rules

13. **One person, several identities.** A `speaker` resolved on Slack and on
    Discord is the same user; repetition across platforms counts as distinct
    conversations but forwarded text (same hash) counts once.
14. **Visibility is per source.** A Slack DM is personal; a Slack lab channel
    is lab; the same rules as Discord.
15. **Reports go where the lab is.** A lab connected to both Discord and Slack
    chooses a primary surface for the lab weekly; personal weeklies follow each
    person's own preference.

## Open decisions

- **OD-11a** Order: Slack before Teams. Recommendation: yes; more labs use it
  and its consent model maps cleanly.
- **OD-11b** Whether transcripts wait for a second text platform.
  Recommendation: yes.

## Brief as built (2026-09-19)

Implemented overnight on the owner's instruction. The plan's own gate
("Plans 01–10 proven on Discord") is not met: the pilot (EXP-2026-09-020) has
not run. So everything here ships **off** (`SLACK_ENABLED`, `TEAMS_ENABLED`,
`AMBIENT_TRANSCRIPTS_ENABLED`), and turning any of it on waits for the pilot.

- **The abstraction held** (EXP-2026-09-021). One corpus through Discord,
  Slack's signed Events API and the Teams Bot Framework endpoint left the same
  ledger: the same messages kept and the same refusals, by reason. The only
  things changed outside the adapters and `integrations`, both additions:
  - `askable` accepts a Slack or Teams identity;
  - reading keeps only developments from a transcript.
- **Slack** (steps 1–5):
  - `SlackWorkspace` (bot token encrypted), `SlackIdentity`, `SlackOutboxMessage`
    and the platform-neutral `LinkCode`;
  - all Slack ORM access goes through `services/slack_resolve.py`, which the
    import-graph test now guards;
  - signed events (HMAC, five-minute replay window) and interactions;
  - OAuth install with a session-bound `state`;
  - a person links by DMing a code; a lab manager links the workspace by
    mentioning Mylo with a lab code in the channel for reports;
  - listening is a lab manager's switch, and each person opts in to Slack
    separately;
  - questions as Block Kit buttons with the same `ambient:<id>:<choice>` ids;
  - a DM reply read as a dialogue turn off the request, because Slack wants
    its 200 in three seconds;
  - `app_mention` is ignored: the message event carries every mention.
- **Teams** (steps 6–8):
  - `TeamsTeamLink`, `TeamsIdentity`, `TeamsOutboxMessage`, and
    `services/teams_resolve.py` as the ORM boundary;
  - every activity's JWT is verified by hand with `cryptography`: RS256
    against the keys Microsoft publishes, the issuer, the audience (the app
    id), expiry and not-before with five minutes' skew, and the `serviceurl`
    claim;
  - the bot token is only ever sent to Microsoft's hosts;
  - group chats are not listened to, since no consent layer covers them;
  - the speaker key is the Azure AD object id, because tenant and id
    together exceed the ledger's 64-character key;
  - Adaptive Card answers.
  - Teams never delivers a bot's own messages, so Mylo's lines are missing
    from Teams chat windows (EXP-2026-09-021 §4).
- **Transcripts** (steps 9–12):
  - an upload is the per-meeting consent;
  - the uploader maps each speaker label to a member, and turns that are
    unmapped, from outsiders, or from people not opted in to transcripts
    never reach the buffer;
  - a 3-hour buffer, read at the next hourly read, keeps only project
    developments, at 0.3 of their weight;
  - everyone named is told on the bell;
  - the project's channel hint attributes the meeting to its project.
- **Cross-platform** (13–15):
  - one person, several identities, all resolved to the same user;
  - visibility per source;
  - reports go where the reader or lab is: Discord first when linked, then
    Slack, then Teams, and a lab may make Slack or Teams primary (the Discord
    senders then skip it);
  - the "shut off" switch stays one switch, stored with the Discord consent
    row.
- **Not built, deliberately:**
  - a PDF attachment on Slack or Teams, which needs extra scopes;
  - a person's own choice of report surface when linked on several: the
    first linked wins;
  - Discord voice transcripts;
  - interest extraction from speech, until Plan 10 shows it is precise.

## Discussion gate

No step in this plan is implemented until the implementing agent has presented,
and the owner has approved, a short design brief: the files and models it will
touch, every migration, every prompt and what happens when the model is
unavailable, every
default value and setting name, and what is deliberately not being done. A
deviation discovered mid-implementation stops the work and reopens the brief.
