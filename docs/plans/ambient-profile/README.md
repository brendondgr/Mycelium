# Ambient Profile — Plan Series

**Status:** Plans 01–08 shipped; 09 onward in progress.
**Correlation ID:** `20260917-ambient-profile`
**Owner:** Brendon (product direction); plans are working documents and are
deleted as their work ships, with the outcome recorded in `docs/changelog.md`.

## The problem

A Mycelium user declares two things by hand: their interests, and the projects
they work on with each project's goals, ideas, and directions. Both go stale.
People do not come back to edit a profile, and a researcher's real focus drifts
faster than the declared one, so the recommendations follow what they last
remembered to type rather than what they are doing.

## The end state

Mylo maintains a **current understanding of what would help this researcher
next** from the conversation already happening on the platforms the lab uses:
Discord first, then Slack and Teams, and possibly meeting transcripts later. The
understanding covers their projects, what they enjoy, and where they want their
career to go. It is maintained from ambient activity, not from forms.

Two extracted stores feed back into the record:

- **Interest signal** — what this person keeps engaging with.
- **Update signal** — concrete developments in their ongoing work.

Every connected platform contributes to both through one shared observation
format. Discord is the first adapter, not the design.

## What Mylo understands

| Kind | Example | Effect on recommendations | Speed of change |
|---|---|---|---|
| Enduring interests | "I enjoy studying how people collaborate with AI." | Keeps literature discovery on course | Slow; strong evidence and a confirmed answer |
| Current curiosity | Repeated questions about uncertainty estimation | Widens coverage for a while, then fades | Fast; bounded and self-fading |
| Work preferences | Prefers empirical, reproducible work | Changes which papers win and how they are explained | Slow |
| Career direction | Wants to move toward clinical or industry research | Reweights fellowships, training, funding, collaborators | Slow; confirmed before replacing anything stated |
| Project intent | Wants to show a specific intervention works | Evidence, rivals, methods, resources for that aim | Proposal when evidence conflicts |
| Project developments | Dataset arrived; experiment failed; venue changed | Changes what is useful right now | Fast; dated events |

Two consequences the table forces. A week spent discussing a method the
researcher dislikes because the project needs it is a project development, not
an interest change. "I want to learn causal inference" is a learning goal, not
a claim of expertise.

## Principles every plan obeys

1. **Natural conversation is the primary capture path.** Slash commands, a
   message action, and a DM inbox exist as options, never as the way the system
   is meant to be fed. A user should never have to keep track of what Mylo is
   trying to extract.
2. **A reasoning step decides whether anything changes.** Extraction produces
   observations. A separate deliberation step decides: ignore, fold into the
   fast layer, propose, or ask. Nothing goes from a message to the profile
   without passing through it.
3. **Ambient signal can only help the declared profile, never crowd it.**
   Profiles are budgeted — clusters per tier, topics per cluster, projects per
   scope. The evolving layer lives beside the declared profile and never spends
   that budget on its own. Spending budget requires a confirmed answer from the
   person. A stated field is never auto-edited (`state.py` invariant 9).
4. **Validation is a conversation, and every answer is data.** Mylo asks in
   plain language over DM: "Did I get this right?" Each answer is stored as a
   labelled record. That record is how we learn whether the system is making
   correct changes or is an exercise in futility.
5. **The binding is a server, not a channel.** Mylo works out who is speaking
   and which project a conversation is about. Channel and thread bindings are
   optional accelerators for attribution, never a requirement.
6. **Personal and lab changes are reported separately.** A change to one
   person's profile reaches that person. A change to a lab-associated project
   reaches the lab's updates channel and each member on it.
7. **Visibility travels with memory.** A private career aspiration informs a
   personal report and never a lab one. Consent is per person and per server.
   Derived observations are kept; raw text is buffered briefly and discarded.
8. **Context must reach retrieval and ranking, not just prose.** Feeding
   summaries only to the writing prompt yields more personal paragraphs around
   the same unsuitable picks.
9. **Confirmation before effect.** Nothing Mylo understood changes a
   recommendation until the person confirms it, or unless it is their own
   explicit first-person statement of a project fact made directly to Mylo.
   Confirmation is real time, on the surface the person is on, never a weekly
   batch. What it costs in "self-maintaining" it repays in accuracy, and the
   accuracy is measured (Plan 10).
10. **Messages are not saved.** Raw text lives only long enough to be read
    once, in a transient buffer measured in hours, and is then gone. What is
    kept is the observation: a short summary of an interest or a project
    change, its dates, and the kind of place it came up. Nothing verbatim is
    kept. When Mylo explains itself, the evidence is an explanation it wrote
    — what, on which dates, where, how often, and why it read it that way —
    never a quote. This is stated to the person in the settings and in the
    listening marker, in those words.
11. **Everything is opt-in, and opt-out at any time.** Per person and per
    platform, default off. Opting out drops that person's messages at the edge
    and, on request, deletes their observations and every derived influence.
    "Shut off", said to Mylo in any conversation or toggled on the web, stops
    the questions at once.
14. **Paid, linked accounts only.** Listening, suggestions, and questions
    exist only for a person whose **effective tier** is paid — their own
    subscription or the paid lab they belong to, exactly as the existing caps
    are resolved — and who has a linked platform identity. A server member
    without a Mycelium account is not involved in any way: their messages are
    discarded on arrival and nothing about them is recorded. Free-tier users
    receive nothing from this feature.
15. **Consistency asks; covered is silent; a no rests for a month.** Mylo
    asks about a topic when the person has shown a true interest in something
    new that is not on their profile, by discussing it consistently, not
    because they said one sentence. It never asks about something already in
    their profile. A declined topic is not raised again for 30 days, and only
    then if the person has kept coming back to it.
16. **Changes land with the nightly run.** Analysis runs once a day over the
    last few days of conversation. A confirmed change takes effect at the
    next run, and Mylo says so. There is no real-time refit and no continuous
    evaluation.
17. **Memory is long-lived and the person's to edit.** What Mylo understands
    about a person accumulates over time and is never discarded on a lapse;
    it pauses. Every entry is editable and deletable on the web. This memory
    is what Mylo's suggestions are grounded in: Mylo suggests what the person
    has already shown they want, because they said it, never a direction it
    invented.
18. **Model-written, no rule-based fallback.** Extraction and explanation are
    done by a model reading the conversation. When the model is unavailable
    the stage does not run that night and is retried the next; nothing
    rule-based stands in for it. This is a deliberate departure from the
    repo's usual deterministic-fallback convention, made for this feature
    only, because a rule-based reading of conversation would produce
    confident nonsense.
19. **What conversation teaches Mylo is never used to make a person
    findable.** Understanding lives in the shared knowledge core
    (`apps/knowledge`, collaboration-network CN-01, shipped 2026-09-18)
    as `conversational` edges. Those edges shape the person's own
    recommendations once confirmed and are read by nobody else — not a
    lab-mate, not collaboration search. The collaboration app can read only
    `declared` and `demonstrated` edges, and a boundary test enforces it.
12. **Everything is visible on the web.** What changed, how it was applied,
    and why Mylo thought so, with undo, on a page the person will see, plus a
    bell notification for every pending question and applied change (Plan 07).
    Nobody guesses.
13. **A discussion gate before every plan.** No plan is implemented until the
    implementing agent has laid out what it will change, how, and with what
    defaults, and that brief has been approved. Each plan carries its own
    gate section naming what the brief must contain.

## What already exists and is reused

| Foundation | Where | Reused for |
|---|---|---|
| Stated / inferred provenance on project state | `web/backend/apps/research/state.py` | Every conversation-derived field is `inferred` until confirmed |
| Grounded extraction with a bounded repair | `web/backend/apps/research/state_extract.py` | The extractor's shape |
| Deterministic proposals with accept / reject / expiry / cooldown | `web/backend/apps/content/reflection.py`, model `ReflectionProposal` | The apply path for slow-layer changes |
| Append-only weak labels with config weights | `RelevanceEvent` in `web/backend/apps/content/models.py` | Engagement evidence; the same table carries report-button events |
| Time-decayed engagement blended into a vector | `web/backend/apps/content/team_profile.py` | The curiosity drift component |
| The interests contract and its `sources` dict | `web/backend/apps/accounts/interests.py` | Provenance on interest fields |
| One-question-per-turn bounded loop | `web/backend/apps/accounts/intake/agent.py` | The validation dialogue |
| Discord identity by snowflake, guild ↔ lab link | `web/backend/apps/integrations/models.py` | Attribution of speakers and servers |
| Closed packet + verifier for the weekly | `weekly_packet.py`, `weekly_verify.py` | The "what changed" section |
| Cadence and push routing | `web/backend/apps/content/delivery.py` | Personal vs lab notification routing |

## Shared with the collaboration-network series

Topics are not strings here. They are **concepts** in the knowledge core
(`apps/knowledge`, collaboration-network Plan CN-01), shared with the
[collaboration-network](../collaboration-network/README.md) series. That is
what lets Plan 04 count one topic said three different ways as one topic, lets
"already covered" and "declined near-synonym" be one lookup, and lets a
person's declared profile, their papers, and what Mylo understood from
conversation sit side by side with their evidence tier.

**Decided 2026-09-19 (overnight build):** raw text is *read* hourly within
the buffer's unchanged 6-hour TTL and *decided on* nightly (option C); the
buffer runs on its own Redis with persistence off (`redis-ambient`). Plans 04
onward were built without a stop at each discussion gate, on the owner's
instruction; each plan's judgement calls are in its changelog entries.

**Owed before `AMBIENT_DRIFT_ENABLED` is ever turned on:** the evaluation
harness before/after the Plan 05 ranking hook (`fusion.combine_clusters`'s
`cluster_weights`). Tonight's run could not finish re-embedding the harness's
pooled corpus on the shared CPU within its 45-minute cap; the hook is exactly
inert while drift is off, which a unit test pins
(`test_without_exploration_weights_the_merge_is_byte_identical`), and Plan 10's
drift ablation (its EXP 8) is where the harness runs with drift on.

**Build order (decided 2026-09-18):** the collaboration-network series is built
first (CN-01 to CN-06). This series then resumes at Plan 04, which, like Plans
05, 07, and 10, is already written against the knowledge core, so resuming
means plugging in rather than redesigning. Until then Plans 01–03 stay shipped
and dark: `AMBIENT_ENABLED` is off, so nothing is captured. The rules for
keeping the two series apart are in that README's "Keeping the two series
apart".

## The plans, in order

Each plan depends on the ones before it unless stated. A plan is many steps;
the sequence is the point. A plan is a working document: once its work has
shipped the file is deleted and the row below says so, because a plan that
describes code which already exists is worse than no plan at all. What was
built, what deviated from the plan, and why, is in `docs/changelog.md` under
the correlation id named in the row.

| # | Plan | Delivers |
|---|---|---|
| 01 | Evidence ledger — **shipped 2026-09-18** | `web/backend/apps/ambient/`: the observation model, the transient buffer, the adapter contract, retention, deletion. Plan deleted; the record is in `docs/changelog.md` under `20260917-ambient-profile-01` |
| 02 | Discord server listening — **shipped 2026-09-18** | `mylo/bot/cogs/listen.py` + `apps/ambient/service.py`: consented capture, the listen cog, `/setup`'s Listening section, the visible notice. Stage B (the Message Content intent) is written and **off**. Record: `20260917-ambient-profile-02` |
| 03 | Attribution — **shipped 2026-09-18** | `apps/ambient/attribution.py` + `attention.py`: which project a message is about (seven signals, floor and margin, an honest "unresolved"), mentions, attention share, and the editors' Conversation card. Record: `20260917-ambient-profile-03` |
| 04 | Reasoning agent — **shipped 2026-09-19** | `apps/ambient/windows.py`, `extract.py`, `reading.py`, `deliberate.py`, `explain.py`: conversations read hourly within the buffer's TTL (option C), grounded observations with no quotes, concepts linked through the knowledge core, one decided `Finding` per topic, model-written explanations. Validated in EXP-2026-09-013. Record: `20260917-ambient-profile-04` |
| 05 | Evolving profile layer — **shipped 2026-09-19** | `apps/ambient/evolve.py`, `ProjectDevelopment`, `content/explorations.py`, `content/understanding.py`: pending conversational edges and developments, fading and retraction, exploration themes behind `AMBIENT_DRIFT_ENABLED`, confirmed preferences/direction/learning goals in the prompts, attention-ordered reports, developments in the alerts, a report `context_version`. Validated in EXP-2026-09-014. Record: `20260917-ambient-profile-05` |
| 06 | Confirmation dialogue — **shipped 2026-09-19** | `apps/ambient/dialogue.py`, `PendingSuggestion`, `ValidationRecord`, the listen cog's buttons and DM routing, `deliver_ambient_questions`: nightly questions with only the choices that exist, answered by button or in words (reader r4, a chosen no is never a yes), "stop asking" in the person's own words, the bell. Validated in EXP-2026-09-015 (registered run failed; post-hoc r4 at 0.0079 harm; a fresh-seed run owed, Q-049). Record: `20260917-ambient-profile-06` |
| 07 | Web transparency — **shipped 2026-09-19** | `apps/ambient/review.py`, `AppliedChange`, `/api/ambient/` change, understanding, settings and lab endpoints; `components/portal/ambient/*` and `/app/mylo-and-you`: questions answerable on the web, what changed with undo, faded and declined, what Mylo knows, the switches, the lab and project cards, the bell. Validated in a browser in EXP-2026-09-016 (three defects found and fixed; run 4 clean, WCAG 2.1 AA by axe). Record: `20260917-ambient-profile-07` |
| 08 | Applying changes — **shipped 2026-09-19** | `apps/ambient/apply.py` (a yes carried into the declared profile at the next nightly run, through the contract, with provenance and exact undo), `apps/content/ambient_proposals.py` (developments proposed to a project's editors as reflection proposals; accepting applies and records an undoable change). Validated in EXP-2026-09-016. Record: `20260917-ambient-profile-08` |
| 09 | [Reports and notifications](09-reports-and-notifications.md) | The weekly "what changed", split personal vs lab, routed correctly |
| 10 | [Evaluation](10-evaluation.md) | The replay experiment and the validation-record metrics, under the research rules |
| 11 | [Other platforms](11-other-platforms.md) | Slack, Teams, transcripts as adapters over the same ledger |

## Cross-cutting open decisions

- **OD-A1** Where the evolving layer is stored: a sidecar JSON on `Profile`, or
  its own table. Plan 05 now recommends neither: `conversational` edges in the
  shared knowledge core (CN-01).
- **OD-A2** *Resolved 2026-09-17:* unlinked members are not involved. Dropped at
  the edge, nothing recorded.
- **OD-A3** *Resolved 2026-09-17:* a project fact a person tells Mylo
  directly is a fact and is recorded as one, with undo. Interests,
  preferences, and anything inferred from ambient talk ask first.
- **OD-A4** *Resolved 2026-09-17:* no elaborate cap. The nightly run asks
  about what qualified; in practice that is a question now and then, seen
  right where it is asked. None in a quiet period, none when shut off.
- **OD-A5** Whether the Message Content intent is requested at all before the
  DM and mention paths have proven the extractor. Plan 02 recommends staging it.
- **OD-A6** *Resolved 2026-09-17:* no quotes. Evidence is an explanation Mylo
  writes: topic, dates, place kinds, frequency, and why it read it as it did.

## Discord platform facts, verified 2026-09-17

Discord's privileged-intent review now triggers at **10,000 total users** with
**annual re-application**, replacing the old 100-server threshold. A 90-day
grace applies if access lapses. Source:
<https://discord.com/blog/updated-requirements-to-how-apps-access-data-in-servers>.
`docs/skills/discord-bot.md` was corrected on 2026-09-18 (it had stated the
old 100-server rule).
