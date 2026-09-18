# Plan 03 — Design Brief (the discussion gate)

**Status:** approved by the owner on 2026-09-18 with the instruction to
implement the plan. **Correlation ID:** `20260917-ambient-profile-03`.

## What is being built

For every message that reaches the ledger: **who** is speaking (already
settled by Plans 01–02 — a linked, paid, opted-in user or nothing), **whom they
mention**, and **which project** the conversation is about, with an explicit
confidence and a real "unresolved" answer. From those attributions, a rolling
**attention share** per person per project. And the manager tools that make
attribution correctable: project aliases, a channel hint, and a list of recent
attributions with a one-click correction.

## Phases, each its own commit

| # | Phase | Delivers |
|---|---|---|
| 1 | The scorer | `Project.aliases`; attribution columns on `RawMessageRef`; `ChannelHint`, `AttributionCorrection`; `attribution.py` — candidates, seven signals, the floor-and-margin rule |
| 2 | Attribution on arrival | mentions from the cog; scoring in `service.heard`; continuity and thread inheritance; the nightly `attribute_window` with the semantic signal; lapsed speakers dropped before any window is read |
| 3 | Attention share | `ProjectAttention`, the nightly recompute, the Beat entry |
| 4 | The manager API | aliases on the project serializers; `/api/ambient/projects/<id>/conversation/`, the channel hint, the correction endpoint |
| 5 | The manager UI | aliases in the project editor; a Conversation card on the project page |
| 6 | Docs | api-contract, repo-map, architecture; this plan deleted |

## When attribution runs, and why on arrival

**Attribution is scored when a message arrives**, in the same transaction that
records the reference, while the text is still in memory. Every signal but one
is a cheap deterministic lookup — a name, an alias, a dataset the project
already lists, a channel hint, the last confident attribution in the same place,
who else is talking — so doing it on arrival costs a few queries and keeps
continuity honest, since "the last attribution in this channel" is inherently a
stream question. No model is called on arrival, so this is not the continuous
evaluation the owner ruled out.

The one expensive signal — **semantic similarity** of the conversation to a
project's slow state, via the existing embedder — is computed by
`attribution.attribute_window`, which Plan 04's nightly pass calls on each
window *before* extraction, re-scoring only the references the arrival pass left
unresolved. It is `None` when no embedder is installed, as the plan says. Loading
an ONNX model into the Discord gateway process to embed every message is the
alternative, and it is the wrong trade.

Deterministic scoring here does not contradict principle 18 (no rule-based
fallback). That principle is about *reading meaning* — extraction and
explanation — and it stands. Attribution by names and known entities is what the
plan's own signal table specifies, and it is paired with an honest "unresolved"
rather than a guess.

## Models and migrations

* **`research.Project.aliases`** (research migration) — a list of short
  strings a project editor maintains: "the imaging pipeline", "IMG-seg".
* **`RawMessageRef`** gains `project` (nullable), `project_confidence`,
  `attribution` (the per-project signal scores and the *project vocabulary*
  that matched — an alias, a dataset name — never the person's words),
  `attributed_at`, `mentions_count`, and `mentioned_user_ids`.
* **`ChannelHint`** — an optional default project for one channel.
* **`AttributionCorrection`** — append-only: a person said "this was about a
  different project". It snapshots the signal scores at the time (numbers and
  ids only) so Plan 10 can set the floor and margin from real labels (OD-03b).
  Where an observation already rests on the corrected message, the correction
  also writes an `ObservationFeedback` row, as the plan asks.
* **`ProjectAttention`** — per user per project, 7- and 28-day shares.
* **`SourceActivity.dropped_lapsed`** — messages discarded at the nightly read
  because the speaker was no longer eligible.

## Settings and defaults (OD-03b: conservative, to be set from Plan 10's labels)

| Setting | Default | Meaning |
|---|---|---|
| `AMBIENT_ATTRIBUTION_FLOOR` | `0.6` | The top candidate's score must reach this |
| `AMBIENT_ATTRIBUTION_MARGIN` | `0.25` | …and lead the runner-up by this |
| `AMBIENT_CONTINUITY_MINUTES` | `30` | How long a confident attribution carries in the same place |
| `AMBIENT_THREAD_OVERRIDE` | `0.9` | Content score another project needs to break a thread's inheritance |

Signal caps: name or alias 1.0 exact / 0.6 fuzzy; known entities 0.25 each up
to 0.6; thread inheritance 0.7; continuity up to 0.75, decaying to zero over
the window; a forum-post or thread title naming the project 0.4; channel hint
0.3; participants up to 0.3; semantic similarity up to 0.5. A channel hint, a
title, participants or similarity can never resolve a message alone.

**Continuity is the exception, deliberately.** A reply a few minutes after a
message that named a project is about that project — that is how conversation
works, and a rule that left "nice, ship it" unresolved would leave most of a
lab channel unresolved. Two limits keep it honest, and both were added during
implementation when the first version failed its own fixture: it carries only
from an **anchor** — a message whose own words named the project, or one a
person corrected — so a chain of "ok"s cannot carry a project across an
afternoon; and it **yields** the moment another project is named outright, so
the last topic never outvotes the current one. Alone it decides for about the
first six minutes of the thirty-minute window.

## Who can see what

* **Candidates** are only projects the speaker is on — their personal projects
  and projects they are a member of — plus, in a lab channel only, the lab's
  projects shared into lab reports. A DM never attributes to a project the
  speaker is not on.
* **Mentions** record a count, and a user id only for a mentioned person who
  has themselves opted in. Somebody who never opted in is at most a number.
* **The attribution list** a project editor sees shows lab-channel messages
  attributed to that lab project — date, channel, speaker, confidence, and
  which project terms matched. **Never a DM**, never a personal project to
  anyone but its owner, and never any message text (none is kept).

## Prompts and model calls

None. The semantic signal uses the local embedder; nothing here writes prose.

## What is deliberately not being done

* **Mylo does not propose aliases** (OD-03a). That is an `inferred` proposal
  through Plan 08.
* **No extraction and no observations are written.** The attribution lives on
  the reference; Plan 04 copies it onto each observation it writes.
* **The floor and margin are not tuned.** They ship conservative and are set
  from Plan 10's labelled data, which the correction table collects.
* **No scheduling of the nightly window pass.** `attribute_window` is built and
  tested here; Plan 04 owns the nightly stage that calls it.
