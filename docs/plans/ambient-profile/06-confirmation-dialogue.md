# Plan 06 — The Confirmation Dialogue

**Status:** draft. **Depends on:** Plans 04, 05. **Unblocks:** Plans 07, 08, 10.
**Correlation ID:** `20260917-ambient-profile-06`

## Objective

When a person **consistently** talks about a topic, Mylo notices and asks them,
in plain language, whether they want it included — in their reports, as an
interest, as a new cluster if they have room — and does nothing until they
answer. The person never has to say "I'm interested in this" for the question
to arise, and they never have to keep track of what Mylo is watching. The
question is asked once; a no is respected permanently; a topic already in the
profile is never asked about at all.

Nothing Mylo understood changes a recommendation until confirmed, except a
project fact the person told Mylo directly, which is recorded as the fact it
is (OD-A3). Analysis runs **once a night over the last few days** of
conversation; confirmed changes take effect at the next run, and the person
is told so. Everything here is for people on a **paid effective tier with a
linked account** only.

## The trigger is consistency, not a sentence

1. **Consistency test** (computed by Plan 04's deliberation, read here). A
   topic becomes askable when, within the trailing window, the same person has
   discussed it on at least `AMBIENT_CONSISTENT_DAYS` distinct days (draft 3)
   across at least `AMBIENT_CONSISTENT_CONVERSATIONS` distinct conversations
   (draft 2), with at least one observation of force `preference`,
   `decision`, or `fact` rather than only `question` or `possibility`, and no
   `rejection` since. One long debugging session does not qualify. A single
   "I really enjoyed this" does not qualify on its own; it counts toward the
   test and, said directly to Mylo, gets a same-conversation reply (step 6).

2. **Already covered — no question.** Before anything is asked, the topic is
   compared to what the person already has: declared areas and keywords,
   cluster labels and their terms, confirmed explorations, learning goals, and
   preferences, by lexical match and embedding similarity above
   `AMBIENT_COVERED_SIMILARITY`. Covered means silence. If Mylo is unsure
   whether it is covered, it does not ask; it waits for more evidence.

3. **Declined — rests for a month.** A topic the person said no to is
   recorded on `InterestUnderstanding` as `rejected` and is not raised again
   for **30 days**. After that it is askable again only if the consistency
   test is met afresh from conversation after the no — the person actually
   came back to it. Similarity to a rejected topic above the covered
   threshold is treated the same, so a rename does not sneak the question
   back early. The topic stays visible on the web "declined" tab (Plan 07),
   where the person can reopen it themselves at any time. "Later" defers for
   30 days as well.

4. **What the question offers.** The question names the topic, says how Mylo
   came to it (step 8), and offers the choices that actually exist for this
   person:
   - *Include it in my reports* — a confirmed exploration (Plan 05): Mylo
     searches for it alongside declared themes, no cluster or topic budget
     spent, review date in 30 days.
   - *Add it to my interests* — a keyword or area within an existing cluster,
     if there is room, through the proposal path (Plan 08).
   - *Make it a new cluster* — only if the tier has a free cluster slot;
     otherwise offered as a swap for a stale one, or not offered.
   - *It's for a project, not me* — recorded as a project development or
     project intent (attributed per Plan 03), not an interest.
   - *Not now* / *No, and don't ask about this*.
   The person can also type anything; the reply extractor (step 7) reads it.

5. **Cadence.** The nightly run asks about whatever qualified that day,
   strongest evidence first, delivered with the person's daily or weekly at
   their delivery hour and on the web as a pending suggestion. In practice
   that is a question now and then, seen right where it is asked. Nothing on
   weekends. Nothing during a quiet period. Nothing at all when the person has
   shut it off (step 9).

## Explicit statements still get an answer

6. When a person tells Mylo something directly — a DM, a mention, a reply to a
   Mylo post — Mylo replies in that conversation with what it understood and
   what will happen: "Got it. I'll note that the annotation pipeline is
   blocked on labelling — it'll show in your project from tomorrow's run.
   Not right? Tell me." A project fact is recorded as a fact; an interest or
   preference stated outright becomes a pending
   suggestion answered right there. These replies are not capped; the person
   started them.

## The dialogue

7. **Shape and reply understanding** (`apps/ambient/dialogue.py`). Reuse the
   intake agent's bounded one-question-per-turn loop: one question, at most two
   follow-ups, then a one-line close stating the consequence and *when* it
   takes effect ("from tomorrow morning's run"). Free-text replies →
   `confirmed(choice)`, `rejected`, `corrected`, `defer`, `unclear`, read by
   the model; buttons are a shortcut, never the only way. `unclear` gets one clarifying turn and then a graceful close with
   no change.

8. **"Why?" is Mylo's account, in its own words.** Mylo does not keep the
   person's messages; it keeps its own account of what was said, when, and
   where (each observation's `text`), and the explanation is written by the
   model from those: "You brought up uncertainty estimation on four days in
   the last two weeks — in #methods on the 9th and 12th, and twice in DMs to
   me — and on Tuesday you said you'd like to try it on the imaging data, so
   I read it as something you want rather than something the project
   requires." There is no rule-based fallback; if the model cannot write it,
   the suggestion waits. "Forget that" retracts the observations behind it
   (Plan 01).

9. **Shut off.** In any conversation with Mylo, "stop asking", "shut off",
   "leave my interests alone", or the like turns ambient questions off for
   that person, immediately, with a one-line confirmation and a pointer to the
   setting. The same toggle is in the web settings (Plan 07). Listening can be
   turned off separately, or both at once ("stop listening too"). Turning
   questions back on is the same sentence in reverse or the toggle. Shut off
   is never overridden by a cap reset, a new server, or a new platform.

10. **Tone** follows `docs/styles.md`. Specific, short, one question. Never
    "I updated your profile"; always "shall I?" for anything that is not a
    stated project fact, and always "from tomorrow's run" for when.

## The record

11. Every asked question writes a `ValidationRecord`: the finding, the
    explanation, the choices offered, the surface, the verdict and choice, the
    correction if any, the reasoning trace id, and timestamps. Every verdict
    writes `ObservationFeedback` rows. This is the labelled dataset Plan 10
    measures and what Plan 07 shows as history.

12. **Consequences.** `confirmed(choice)` → applied per step 4 at the next
    nightly run, with a bell notification the morning it lands. `rejected` →
    permanent for that topic (step 3), and the evidence pattern is
    down-weighted. `corrected` → the correction is a stated edit (the person
    typed it). `defer` → 30 days, once.

## Mirroring and lab projects

13. A pending suggestion exists once with a state machine
    (`pending → asked_dm | asked_web → answered | expired`), read by both
    surfaces; the first answer wins and the other shows where it was answered.
    Expiry 14 days, matching reflection proposals.
14. A project-level suggestion on a lab project goes to that project's
    managers and PI as a thread under the lab's updates channel and on the
    lab's web review page; any of them can answer and the answerer is recorded.

## Eligibility

15. The dialogue, the suggestions, and the listening that feeds them exist
    only for people with an **active DiscordIdentity** (or the later
    platform's equivalent) whose **effective tier is paid** — their own
    subscription or the paid lab they belong to, resolved exactly as the caps
    are, so a PI on a paid lab is paid. A free-tier person sees the feature
    described in settings with an upgrade note and receives nothing. A lapse
    pauses questions and listening; the memory is kept, untouched, and
    resumes with the tier. Entitlement is published by
    `apps.billing.entitlements` (`ambient_enabled(tier)`), the same way caps
    are.

## Steps

16. `PendingSuggestion` model with the state machine and both-surface ids.
17. Consistency test, covered check, and declined check as pure functions
    over Plan 05 rows, with fixtures.
18. Explanation writer (model call over the observations' accounts; waits
    when the model is unavailable).
19. Dialogue loop, reply extractor, shut-off phrases.
20. Nightly application hook: confirmed choices applied in `manual_all.py`
    before ranking; morning bell.
21. `ValidationRecord` and feedback writes; export for Plan 10.
22. Entitlement gate and lapse handling.
23. Tests: consistency edge cases; covered topic silent; rejected topic never
    re-asked, including a near-synonym; cap and weekend; shut-off wins over
    everything; free tier receives nothing.

## Discussion gate

Before implementation the agent presents: the `PendingSuggestion` schema, the
consistency thresholds and the covered-similarity threshold with the fixtures
they were chosen on, the exact wording of each question kind and the
explanation template, the reply extractor's prompt and fallback, the shut-off
phrase list, and the entitlement name. No question wording ships without
sign-off.

## Open decisions

- **OD-06a** *Resolved (OD-A3):* a project fact told to Mylo is recorded as a
  fact. Interests and preferences always ask, even when stated outright.
- **OD-06b** Consistency thresholds. Draft 3 days across 2 conversations in
  the trailing 28; tuned in Plan 10 from the validation record.
- **OD-06c** Whether an exploration's 30-day "keep this?" check counts against
  the daily cap. Draft: yes; it is an ambient question like any other.
