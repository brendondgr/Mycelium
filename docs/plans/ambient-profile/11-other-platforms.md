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

## Discussion gate

No step in this plan is implemented until the implementing agent has presented,
and the owner has approved, a short design brief: the files and models it will
touch, every migration, every prompt and what happens when the model is
unavailable, every
default value and setting name, and what is deliberately not being done. A
deviation discovered mid-implementation stops the work and reopens the brief.
