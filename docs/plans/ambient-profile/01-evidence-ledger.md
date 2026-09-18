# Plan 01 — The Evidence Ledger

**Status:** draft. **Depends on:** nothing. **Unblocks:** every later plan.
**Correlation ID:** `20260917-ambient-profile-01`

## Objective

One platform-independent table of **observations**: what was said, by whom,
about what, when, and with what kind of force. Every adapter (Discord, Slack,
Teams, transcripts) writes this shape and nothing else. Every downstream stage
(attribution, extraction, deliberation, validation, reports) reads it. Nothing in
this plan touches a profile or a project.

## Why a ledger and not a queue

The reasoning agent (Plan 04) needs to look back across days to count repeated
engagement, detect supersession ("we decided against X" retiring "we might try
X"), and cite the exact sentence a proposal rests on. The validation dialogue
(Plan 06) needs to show the person what Mylo saw. The evaluation (Plan 10)
needs to replay. All three need the evidence to still exist after the
extraction ran.

## Steps

1. **Create the `ambient` Django app** under `web/backend/apps/ambient/`. It
   owns the ledger, the adapter contract, retention, and deletion. It imports
   from `integrations` (identities) and `research` (projects) and is imported
   by `content` only through a small read API. Add the app to `docs/repo-map.md`
   and `docs/architecture.md` in the same change.

2. **Model `Source`.** One row per connected surface: kind (`discord_guild`,
   `discord_dm`, `slack_workspace`, `teams_team`, `transcript`), external id,
   the lab it belongs to (nullable for a personal DM), consent state, and the
   retention window. A Discord guild `Source` is created by Plan 02 from the
   existing `DiscordGuildLink`.

3. **The transient buffer — messages are not saved.** Raw text is held only
   long enough to assemble one window for extraction: in Redis with a TTL
   (`AMBIENT_RAW_TTL_HOURS`, default 6, hard maximum 24), never in Postgres,
   never on disk, never in a backup. After extraction the window is deleted
   explicitly; the TTL is the safety net. A `RawMessageRef` row in Postgres
   keeps only external ids and timestamps so an edit or deletion can be
   reconciled against derived observations. This is the mechanism behind the
   promise shown to every person: *Mylo does not keep your messages.*

4. **Model `Observation` — the durable record.** Fields:
   - `source`, `external_message_ids` (one or several; a window may yield one
     observation from three messages), `observed_at`.
   - `speaker` (a Mycelium user, **required**) and `speaker_external_id`,
     plus `speaker_kind`: `linked` or `mylo`. The ingest endpoint checks
     eligibility (linked identity, paid effective tier, opted in) before the
     buffer, so messages from bots and from anyone ineligible are discarded
     on arrival and no observation can exist for them.
   - `text` is the model's own account of what was said and when — "on
     12 Sep in #methods they said they wanted to try conformal prediction on
     the imaging data" — not the person's words. This is what the explanation
     and the web history are written from.
   - `subject`: `self`, `colleague`, `project`, `lab`, `unknown`. A person
     discussing a colleague's idea is not stating their own interest.
   - `project` (nullable) and `project_confidence` (0 to 1) — set by Plan 03.
   - `understanding_kind`: one of the six in the README table.
   - `force`: `fact`, `question`, `preference`, `possibility`, `decision`,
     `rejection`. "The experiment finished" and "we should finish the
     experiment" are different rows.
   - `text`: the extracted statement in Mylo's words, one or two sentences.
     **No quote is stored, ever.** `grounded = true` records that the
     extractor's grounding check passed against the transient window before
     it was discarded. `place_kind` (`dm`, `channel`, `thread`, `forum`,
     `transcript`) and `place_label` (a channel name, not an id the person
     cannot read) are kept so an explanation can say where.
   - `explanation`: written at deliberation (Plan 04) for findings that reach
     a suggestion — what, on which dates, where, how often, and why Mylo read
     it as it did. This is the only evidence a person ever sees (OD-A6).
   - `extraction_confidence` (how sure the extractor is it read the message
     right) kept separate from `influence` (how much it should move anything),
     which Plan 04 sets and Plan 05 reads.
   - `supersedes` (self-FK, nullable) and `superseded_at`.
   - `visibility`: `personal` or `lab`. A DM observation is `personal`. A lab
     channel observation is `lab` unless the speaker is talking about their own
     career, in which case Plan 04 marks it `personal` and it never enters a lab
     packet.
   - `origin`: `model` or `rule`, following the project's convention that a
     fallback is never mistaken for a judgement.
   - `context_version` (Plan 05) is added later; leave the column nullable now.

5. **Model `ObservationFeedback`.** The person's own verdict on an observation:
   `confirmed`, `rejected`, `corrected` (with corrected text), `ignored`, with
   the channel it came through (`dm_dialogue`, `web_review`, `undo`). Plan 06
   writes it; Plan 10 reads it as labels. Append-only.

6. **Define the adapter contract** in `apps/ambient/adapters/base.py`: an
   adapter turns platform events into `RawMessage` rows and a platform identity
   into a `speaker_external_id`. It does no extraction and no attribution. A
   `discord` adapter is written in Plan 02; the interface is written here with
   a fake adapter for tests.

7. **Dedupe forwarded and repeated material.** A content hash on the normalised
   text; a message whose hash already exists from the same speaker within 30
   days is recorded as a repeat (`repeat_of`) and counts as one piece of
   evidence, not two. Mylo's own messages (`speaker_kind = mylo`) are stored so
   the window is coherent but are never evidence (Plan 04 excludes them).

8. **Edit and deletion reconciliation.** A platform edit updates the
   `RawMessage` and marks derived observations `stale` for re-extraction. A
   platform deletion, or a person's request to remove evidence, deletes the raw
   row and any observation citing it, and records a `Retraction` row naming the
   downstream things that must be recomputed (Plan 05 and Plan 08 subscribe).

9. **Retention and deletion.** The transient buffer expires by TTL and is
   deleted on extraction. Observations are kept until the person retracts them
   or opts out with deletion; they are the person's record and are exportable.
   Opt-out with "delete my observations" removes every observation, feedback
   row, pending suggestion, and derived influence for that person and records
   a retraction (step 8) so Plans 05 and 08 recompute.

10. **Read API for downstream** (`apps/ambient/read.py`): windows by source and
    time, observations by speaker and kind since a date, evidence for a project,
    and the feedback for an observation. `content` imports only this module.

11. **Tests.** Model constraints (speaker required, visibility set, repeat
    detection), retention purge, retraction fan-out, and the fake adapter end to
    end.

## Acceptance

- A fake adapter can write raw messages, and a window can be read back.
- An observation cannot be saved without a speaker, a visibility, and
  `grounded = true`; the model has no quote column.
- Deleting a raw message removes its observations and records a retraction.
- The purge task removes raw rows past the window and nothing else.

## Open decisions

- **OD-01a** Whether attachments (a PDF pasted into a channel) become raw
  messages. Recommendation: store the URL only; content extraction from
  attachments is a later plan.
- **OD-01b** Buffer TTL default. Recommendation: 6 hours, hard maximum 24.
- **OD-01c** *Resolved 2026-09-17 (README OD-A6):* nothing verbatim is
  stored. Grounding is checked at extraction against the transient window;
  what survives is the summary, the dates, the place kind and label, and
  Mylo's written explanation.

## Discussion gate

No step in this plan is implemented until the implementing agent has presented,
and the owner has approved, a short design brief: the files and models it will
touch, every migration, every prompt and what happens when the model is
unavailable, every
default value and setting name, and what is deliberately not being done. A
deviation discovered mid-implementation stops the work and reopens the brief.
