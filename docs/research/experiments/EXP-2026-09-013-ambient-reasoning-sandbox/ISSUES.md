# EXP-2026-09-013 — Issues

## Pre-run: the smoke run and what it changed (2026-09-19, before the registered run)

A smoke run on a one-lab, two-person world (`--labs 1 --people 2`, 8 workers,
3 min 48 s, not the registered world) exercised the harness end to end. Its
numbers are not results and are not reported as such. It found:

1. **One topic split across kinds.** An emerging interest said three times was
   extracted once each as `current_curiosity`, `learning_goal` and
   `project_intent`. Deliberation grouped by (concept, kind), so no single kind
   reached the floor. **Changed before the registered run:** enduring
   interest, current curiosity and learning goal are one family — one finding
   per topic, its kind the one said most (`deliberate.INTEREST_FAMILY`).
2. **Unresolved project chatter asked about.** Filler logistics were read as
   `project_development` with no project, and `repeated()` (days and
   conversations, any force) raised `ask: attribution_unresolved`. **Changed:**
   an unresolved project topic is asked about only for a fact told to Mylo or
   talk that passes the full consistency test.
3. **A capability read as a project development.** "I ran X on our data" came
   back as `project_development`. **Changed:** the extractor prompt says a
   first-person use of a named method is a capability even when it was for a
   project (prompt version `a1` → `a2`).
4. **The quote check fired on a name.** One explanation shared the 6-word run
   "that the baltic tide dataset for" with a message — the dataset's own name
   plus filler. **Amended (H1 definition):** a shared 6-word run counts as a
   quote only when it carries at least two content words outside the topic
   phrase and the project names. The same rule is now in the extractor's
   validator (`extract.quoted_runs`), so the pipeline and the harm check agree.
5. **Scoring a told fact by topic.** The model titled "the Quarry audio dataset
   has arrived" as "Project A1 data arrival", which shares no word with the
   plant's topic. **Amended (H2 matching):** a told-fact plant matches on its
   message, speaker and the `project_development` kind; every other plant still
   needs a topic-word match.

Each change has a unit test in `apps/ambient/tests/test_reasoning.py`.
