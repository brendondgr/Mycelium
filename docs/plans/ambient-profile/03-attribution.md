# Plan 03 — Attribution: Who Is Speaking, About Which Project

**Status:** draft. **Depends on:** Plans 01, 02. **Unblocks:** Plan 04.
**Correlation ID:** `20260917-ambient-profile-03`

## Objective

Given a raw message in a server, decide two things with an explicit
confidence, and be willing to say "unresolved":

1. **Who** — which Mycelium user is speaking. Only linked, paid, opted-in
   speakers reach this step (Plan 02).
2. **Which project** — which of the lab's or the speaker's projects the
   conversation is about, if any.

The binding is the **server**. A conversation can move between channels and
projects, and the same channel can carry three projects in one afternoon.
Channel and thread bindings are hints that raise confidence; they are never
required and never override the content.

## Who is speaking

1. **Linked speaker.** Snowflake → `DiscordIdentity` (state `active`) → user.
   This is the only identity key; usernames are display only, as the model
   already insists.
2. **Unlinked members and bots** never arrive (OD-A2, resolved). If a
   snowflake reaches the backend that no longer resolves to an active, paid
   identity — a lapse or unlink between arrival and the nightly batch — the
   message is discarded and counted, not stored.
3. **Mylo's own messages** are kept in the window for coherence and excluded
   from evidence (Plan 04).
4. **Mentioned people.** A message that names or @mentions another member is
   about them as much as by the speaker. The attribution step records
   `mentions` (resolved to users where linked) so the extractor can set
   `subject = colleague` correctly.

## Which project

Attribution is a scored decision over the candidate projects the speaker can
see: their personal projects, the projects of the lab the server belongs to
that they are a member of, and, at lab visibility only, the lab's shared
projects. Signals, each producing a bounded score:

| Signal | Source | Notes |
|---|---|---|
| Project name or alias in the text | `Project.title` plus a new `aliases` list the manager can edit | Exact and fuzzy; the strongest single signal |
| Semantic similarity of the conversation window to the project's slow state | Embedding of `problem + claimed_contribution + method` against the window | Uses the existing embedder; `None` when absent |
| Named entities the project already knows | Milestone names, venue targets, dataset names, known literature titles from `ProjectState` | Cheap and precise when it fires |
| Speaker membership | Only projects the speaker is on are candidates at personal visibility | Hard filter, not a score |
| Conversational continuity | The last confident attribution in the same channel or thread within N minutes, decayed | Conversations stay on topic longer than a message |
| Channel or thread hint | An optional per-channel default project, or a forum-post title matching a project | Adds score; never decides alone |
| Participants | Which projects the set of active speakers in the window share | Two people on one project talking together |

5. **Decision rule.** The top candidate wins if its score clears an absolute
   floor **and** leads the runner-up by a margin. Otherwise the observation is
   `project = null, project_confidence = 0`, and it still exists — it can be an
   interest observation, or the validation dialogue (Plan 06) can ask "was this
   about the imaging pipeline or the annotation study?" when the answer would
   matter. Guessing is the failure mode; unresolved is a real answer.

6. **Thread as a unit.** A thread or forum post is attributed once for its
   opening window and inherits until the content disagrees strongly.

7. **Time on a project.** From attributed observations, compute per speaker
   per project a rolling **attention share**: the fraction of their attributed
   conversation over the last 7 and 28 days. This is what tells Mylo which
   project a person is actually spending their time on now, and it feeds Plan
   05 (what is useful now) and Plan 09 ("you spent most of this week on X").
   It is derived, recomputed nightly, never edited by hand.

8. **Manager tools.** In the web project editor: aliases, an optional default
   channel hint, and a view of recent attributions with a one-click
   "this was about a different project" correction that becomes an
   `ObservationFeedback` row and a training example for the margin.

9. **Tests.** Fixtures with two projects that share vocabulary; a conversation
   that switches projects mid-channel; a lapsed speaker discarded; a mention of a
   colleague; a thread that inherits then diverges.

## Acceptance

- A message naming a project alias attributes to it with high confidence.
- A message with two plausible projects and no margin is left unresolved.
- A message from a snowflake without an active, paid identity is discarded
  before any row is written.
- Attention share over a fixture week matches the hand count.

## Open decisions

- **OD-03a** Whether aliases are proposed by Mylo from the state text.
  Recommendation: yes, as `inferred` proposals through Plan 08.
- **OD-03b** The floor and margin values. Set from Plan 10's first labelled
  data, not by taste; ship with conservative defaults.

## Discussion gate

No step in this plan is implemented until the implementing agent has presented,
and the owner has approved, a short design brief: the files and models it will
touch, every migration, every prompt and what happens when the model is
unavailable, every
default value and setting name, and what is deliberately not being done. A
deviation discovered mid-implementation stops the work and reopens the brief.
