# Plan 04 — The Reasoning Agent

**Status:** draft. **Depends on:** Plans 01–03 and
CN-01, the shared knowledge core (`apps/knowledge`, shipped
2026-09-18). **Unblocks:** Plans 05, 06, 08.
**Correlation ID:** `20260917-ambient-profile-04`

## Objective

The step between "someone said something" and "something about this person's
record changes". It has two halves that must stay separate:

- **Extraction** turns a conversation window into grounded observations.
- **Deliberation** decides, for each observation, whether it should be
  ignored, folded into the fast layer, raised as a proposal, or turned into a
  question — and it does so under the profile's budget.

A model reads conversation; code applies policy. That is the same division the
project already uses in `state_extract.py` and `reflection.py`, and it is the
reason a machine never replaces a person's own words in their profile.

## Extraction

1. **Windowing.** Extraction runs in batch, nightly, inside `manual_all.py`
   as a stage before ranking (so today's observations can reach today's
   slates), and on demand for the DM inbox so a reply can come back in
   seconds. A window is one thread, or one channel over a bounded span (default
   4 hours, max 40 messages), attributed by Plan 03. DMs are their own windows.

2. **The extractor** (`apps/ambient/extract.py`) follows the trusted pattern:
   a fixed schema, deterministic validation, grounding, one bounded repair,
   then refusal. It asks the model for a list of observations, each with
   `understanding_kind`, `force`, `subject`, `text`, a `facet` (problem,
   method, setting, or area) with a short topic phrase, and, **for the check
   only**, the supporting sentence. The grounding check requires that sentence
   to appear in the transient window; it is then discarded and only
   `grounded = true` is kept (Plan 01, OD-01c). An observation whose sentence
   does not appear is dropped, and a window that
   yields nothing is a normal outcome.

2a. **Concept linking.** Each observation's topic phrase is linked to a
   concept through the shared knowledge core's linker
   (`apps/knowledge/service.py`, CN-01) and the observation stores that
   concept. This is what makes "conformal prediction" on Tuesday, "conformal
   methods" on Friday, and "CP intervals" in a DM one topic seen three times
   rather than three topics seen once — the repetition and near-synonym rules
   below depend on it. A concept minted here is born in the lab's or the
   person's scope and never enters the shared vocabulary on its own (CN-01).
   The linker is model-free; when the embedder is down, linking waits for the
   next run and the observation is kept unlinked until then.

3. **Force matters more than topic.** The schema forces the model to say
   whether a sentence is a fact, question, preference, possibility, decision,
   or rejection. "The dataset arrived" (fact) and "the dataset should arrive
   next week" (possibility) produce different downstream behaviour, and
   "we decided against X" (rejection) is what retires earlier possibilities.

4. **Subject discipline.** A speaker discussing a colleague's idea, quoting a
   paper's claim, or summarising a talk is `subject = colleague` or `unknown`,
   not `self`. Only `self` observations can move a personal interest. Project
   developments may come from any member.

5. **Self-recommendation exclusion.** Anything Mylo itself posted, and any
   message that is a reply to or a reaction on a Mylo recommendation, is
   engagement (a `RelevanceEvent`) rather than independent interest evidence.
   Otherwise the system reinforces its own suggestions.

6. **No rule-based fallback.** Extraction is a model reading the
   conversation, and nothing else may stand in for it (README principle 18).
   When the model is unreachable the stage records `skipped` in the run
   state, the windows stay in the buffer within their TTL, and the next
   night retries. The rest of the nightly run is unaffected. Link harvesting
   is not a substitute: a shared URL is a `RelevanceEvent` for the project
   seen ledger, not an interest observation.

## Deliberation

7. **Aggregate before deciding.** The agent (`apps/ambient/deliberate.py`)
   never acts on one observation. For each speaker and each project it gathers
   the observations since the last deliberation plus the trailing 28 days and
   computes, per **concept** (step 2a) and per project field:
   - **repetition** across distinct conversations and distinct days (one long
     debugging session counts once);
   - **recency** with a half-life;
   - **force mix** (a decision outweighs five possibilities);
   - **explicitness** (`explicit = true` messages and DMs weigh more);
   - **supersession** (a later rejection retires earlier possibilities on the
     same topic; a later fact closes an earlier question).
   The result is an `influence` score written back on the observations, and,
   per topic, the **consistency facts** Plan 06 reads: distinct days, distinct
   conversations, the force mix, and the last rejection date.

8. **The four outcomes.** Every aggregated finding gets exactly one:
   - **Ignore.** Below the floor, or superseded, or `subject != self` for an
     interest kind. Recorded so it is not re-evaluated tomorrow.
   - **Record.** A project fact a person told Mylo directly — "the dataset
     arrived", "we dropped the simulation approach", "the ICML deadline moved"
     — is a fact because they said it is part of the project. It becomes a
     dated development (Plan 05) and is shown in the web "what changed" feed
     with undo. Nothing inferred from ambient talk is automatic (OD-A3).
   - **Suggest.** A topic that passes the **consistency test** (Plan 06,
     step 1), is **not already covered** by the person's declared areas,
     keywords, clusters, explorations, or preferences (the same concept, or a
     concept above the coverage cosine, among the person's edges in the
     knowledge core), and was **never declined** (no `rejected` edge to the
     concept or a near-synonym of it) becomes a **pending suggestion** (Plan
     06), recorded as a `pending` conversational edge: visible on the web and
     in the DM, explained, and inert until confirmed. Covered or declined
     means silence, recorded so it is not re-evaluated tomorrow. The same
     path carries project developments inferred from ambient talk.
   - **Capability.** Repeated first-person statements of doing something —
     running a method, building a tool, teaching a technique — become a
     suggestion to add a `skill`, which feeds the team-gap matcher, and never
     an area. Until the person confirms it and it lands in their declared
     skills (Plan 08), it is a pending conversational `can_do` edge that no
     other person and no collaboration search can read (collaboration-network
     README, tier table). "I want to learn X" is a learning goal, not a skill.
   - **Propose.** Any edit to the declared profile or to project state becomes
     a proposal through Plan 08 and waits for a person.
   - **Ask.** The evidence is ambiguous (attribution unresolved, self vs
     colleague unclear, a possibility that never became a decision) and the
     answer would matter. Becomes a clarifying question through Plan 06.

9. **Budget rules — the load-bearing part.** The agent reads the caller's
   entitlements (`cluster_cap`, `cluster_topic_cap`, project caps) and obeys:
   - The evolving layer **never spends** cluster or topic budget. It is stored
     beside the declared profile (Plan 05) and blended in at ranking time.
   - A proposal that would add an area, a cluster, or a keyword to the declared
     profile is raised only if there is room, or is phrased as a **swap**
     ("replace *X*, which you have not engaged with in 90 days, with *Y*?").
     A swap is never applied without a confirmed answer.
   - A proposal never removes anything stated. Stale detection produces a
     question ("still current?"), not a removal.
   - Net effect on the declared profile is only ever what the person said yes
     to. Ambient signal can widen what Mylo looks at; it cannot narrow what the
     person declared.

10. **Explanation and trace.** For every finding that becomes a suggestion or
    proposal, the model writes the **explanation** the person will see (Plan
    06, step 8) from the observations' own accounts (`text`, each with its
    date and place): what the topic is, when and where it came up, how often,
    and why Mylo read it as interest, project need, preference, or
    capability. "You mentioned conformal prediction on 12 Sep in #methods and
    again in a DM on the 15th, saying you wanted to try it on the imaging
    data." No rule-based fallback: without the model the finding waits.
    Beside it, a compact **trace** records the scores, the outcome, and the
    rule that decided it, for the web (Plan 07) and for Plan 10's audit.

11. **Cost control.** Extraction is keyed on the window's content hash and is
    never re-run for an unchanged window. Deliberation is pure over the
    ledger and costs no model call. One model call per window per night, with
    a per-lab daily cap.

12. **Tests.** Fixture conversations for each force; a rejection retiring a
    possibility; a colleague's idea not moving a profile; the budget rule
    refusing to add a seventh cluster; the fallback producing only link
    observations.

## Acceptance

- A window with no groundable statements yields zero observations and no error.
- Two mentions on one day and none after do not reach the floor; the same two
  across two weeks do.
- A finding that would exceed the cluster cap becomes a swap proposal, never an
  edit.
- Mylo's own recommendation, replied to, yields a `RelevanceEvent` and no
  interest observation.

## Open decisions

- **OD-04a** Whether deliberation runs nightly only or also on DM receipt.
  Recommendation: both; the DM path runs a scoped deliberation for that
  speaker so the reply can be honest about what will happen.
- **OD-04b** Floors and half-lives. Defaults conservative; tuned by Plan 10.

## Discussion gate

No step in this plan is implemented until the implementing agent has presented,
and the owner has approved, a short design brief: the files and models it will
touch, every migration, every prompt and what happens when the model is
unavailable, every
default value and setting name, and what is deliberately not being done. A
deviation discovered mid-implementation stops the work and reopens the brief.
