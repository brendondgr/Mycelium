# Mylo evaluation follow-ups — what was fixed, what is left

**Status (2026-11-13):** the quick fixes below are in `main` and running on the
live stack. Everything under "Still open" is untouched and waits for a
decision or for the human ratings. Delete this file once the open items are
done or moved to their own plans; the evidence stays in `docs/research/`.

**Correlation ID:** `20261113-mylo-evaluation-fixes`

The overnight evaluation, plus one bug found while re-checking a fix
(EXP-2026-11-010, -011, -013, -014, -002, -015; see
`docs/research/INDEX.md`) found the problems below. Each entry gives one real
example, what was done, and where the evidence is.

## Fixed today

### 1. Mylo could not see any project's description, status or focus

- **Example.** Asked "What are the goals of the Marine heatwave early warning
  project?" (EXP-2026-11-013, `pr04`), Mylo answered "I can't see the goals…
  I only got its name, scope, and members." It was right: `projects_get`
  returned only those three lines.
- **Cause.** The app stores a project's details under `goals.description`,
  `goals.status`, `goals.progress`, `goals.interests` (statement, areas,
  keywords, themes), `goals.watch_topics` and `goals.watch_categories`.
  `tools/agent/memory.project_block` read only `summary`, `goals`, `methods`,
  `datasets`, `deadlines` and `needs` — keys no screen writes. On the live
  database all 12 projects were affected, not only the demo.
- **Fix.** `project_block` now reads what the app writes, through the same
  helpers the recommender uses (`tools/recommendation/targets.py`).
  `projects_get` gets a 6,000-character budget (prompt memory keeps 1,500). A
  project whose state was never confirmed now says so, so "when was it last
  confirmed?" is answered instead of searched for (`pr06` spent 16 of its 25
  steps loading functions looking for that date).

### 2. Deleting a Mylo chat left what Mylo learned from it

- **Example.** EXP-2026-11-011 attempt 4: a new member told Mylo a private
  plan, deleted the chat, and asked "what do you know about my plans?" The
  answer repeated the plan in 5 of 5 runs.
- **Cause.** `tools/agent/service.delete_thread` deleted only the thread.
  Its docstring said learned observations "follow ambient's own deletion
  path", but nothing called that path. The app's confirmation says the chat is
  removed "for good".
- **Fix.** Deleting a thread publishes `agent.thread_deleted`. Ambient
  retracts every message of that thread it recorded, as it does for a message
  deleted in Discord: the observations go, and a pending edge left without
  evidence goes. What the person already confirmed stays. If the retraction
  fails, the chat is not deleted.
- **Re-checked end to end (EXP-2026-11-011 attempt 6):** 0 leaks in 4 valid
  runs (the fifth was vacuous), against 5/5 before. Observations and pending
  edges drop to 0 in each run.

### 3. The answer checker removed correct amounts and passed invented venues

The checker is `tools/agent/verify.py`. All numbers below are re-scored on
last night's stored answers in `EXP-2026-11-013/data/rescore_v3.json`
(Amendments 3–4). The answers themselves were not regenerated.

- **Correct amounts were being removed.** Mylo wrote "€1.5–15M" where the call
  says "€1,500,000–€15,000,000". The checker matched text literally, flagged
  `1.5` and removed the sentence. This caused two of the three repairs
  overnight. Short forms ("1.5M", "15 million") are now read at their scale,
  with rounding at the written precision ("€8.9M" for "€8,925,000"). Both
  wrong removals are no longer flagged. The one correct flag, a "2.5 months"
  Mylo worked out itself, still is.
- **Invented venues were passing.** "Venue: Marine Forecasting Letters" passed
  because two of its three words ("marine", "forecasting") appeared somewhere
  in the evidence. Every distinctive word must now be present. Invented
  venues on a `Venue:` line: 95 → 144 of 147 caught.
- **A wrong year beside the authors** ("**Authors:** Cheon and Kakinuma
  (2024)" for a 2026 paper) is now checked.
- **"€2.5M" was never checked**, because a decimal followed by a letter was not
  read as a figure. It is now.
- **Two problems the re-score itself found:**
  - The first version flagged "€8.9M" in 3 of 149 real answers. Rounding
    tolerance fixed it.
  - A DOI's digits were being read as an amount. Links and DOIs are now
    ignored.
  - Both runs are recorded.
- **Result:** 0 false alarms on the 149 stored answers, and every other error
  class catches at least as much as before.
- **Repair wording.** A repaired answer opened "Here's the corrected
  picture…", although the person never saw a first version. The repair
  request now says not to mention a correction.

### 4. Answers that loop on function calls

Four of 50 answers stopped for repeating themselves, and one hit the step
limit.

- **Loading functions one at a time.** `pr06` made 16 single-function
  `load_functions` calls. Loading a function now loads the rest of its group
  (`projects_*`, `feeds_*`, …; at most six).
- **Calling a function that cannot work, over and over.** `co01` called
  `knowledge_introduction_paths` eight times on outside paper authors. That
  function only reaches people with an account here. Its error now says so,
  and any function that fails twice in a turn is refused for the rest of that
  turn with a reason (`FAILURE_LIMIT` in `tools/agent/loop.py`).
- **Re-reading an empty project record.** `pr04` and `pr06` looped because
  `projects_get` was empty (item 1).

### 5. The decision server can be overloaded by the nightly run

- **Example.** EXP-2026-11-014: the decision server ran out of GPU memory and
  restarted at 32 production-length requests in flight. Throughput is flat
  from about 4 in flight.
- **Cause.** The reranker runs up to 12 requests per theme, and themes run in
  parallel, so the total had no ceiling.
- **Fix.** The decision client shares one limit across the whole process:
  `[decision] port_max_in_flight`, default 8 (`apps/core/decisions.py`).

### 6. Learning from chats would stop once an instance had 200 idle chats

- **Found while re-checking fix 2.** The first re-run of the deletion probes
  (EXP-2026-11-011 attempt 5) learned nothing at all, so it could not test
  anything.
- **Cause.** `learning.run_pass` took the 200 oldest idle threads, including
  ones it had already read, and only then skipped those. Once an instance
  has more than 200 idle threads, a new chat never reaches the batch and Mylo
  silently stops learning from anyone. The evaluation database had crossed
  200.
- **Live site.** Not yet hit: 661 chats, but nearly all are demo-visitor
  chats, which the pass skips; 1 chat was due.
- **Fix.** `due_threads` now selects only threads with messages the pass has
  not read.

## Still open

| # | What | Example | What it needs |
|---|---|---|---|
| O1 | **Facts stated in a sentence are not checked.** Only `Label: value` lines, citation numbers and figures are. | "The lead author of #1 is Marchetti." (invented) passes; so does "presented at IEEE ICAC 2024" for 2026. Caught 0 of 147 times per class. | Deferred by decision on 2026-11-13. The ratings (C-035 recall) will show how often Mylo actually makes this kind of error. |
| O2 | **Claims with no number in them are not checked.** | "The record states how many days ahead the forecasts remain skilful" (it says the opposite) passes: 0 of 180. | A model-based judge. See the "replace TypeSafe with a local judge" direction; the same small yes/no judge could check a sentence against the item it cites. |
| O3 | **The checker compares a fact line with all the evidence of the turn, not the item it is about.** | "Authors: J. Whitcombe" passes because Whitcombe is a lab member who appears elsewhere in the evidence. | Tie a fact line to the `#n` it describes and check only that item's record. Medium-sized change in `verify.py` and `loop.py`. |
| O4 | ~~Turning learning off keeps what was already learned.~~ **Decided 2026-11-14: by design.** | EXP-2026-11-011: after opting out, the next answer still recalled the earlier plan (5/5). | Turning learning off stops future learning only. Past learning stops being used only when the person deletes it ("Delete my observations" under Mylo & you). The toggle's help text now says so. Nothing else to do. |
| O5 | **Asking the decision model a state's questions together changes its answers.** | Joint vs one-per-request: the most likely answer differs on 20.6% of questions (Q-064). | Human judgments to decide which form is closer to a person; until then, keep the production form. |
| O6 | **The weekly report's evidence is not stored**, so its checker's precision cannot be measured (C-025). | 7 model-written weeklies, 0 rebuildable. | Store the evidence packet with each weekly. |
| O7 | **Mylo sometimes asks back instead of answering.** | "Who runs this funding programme, and is it open now?" (`to03`, rep2) ended in a clarifying question with an empty answer. | Watch in the ratings; if it recurs, tell the prompt that a tagged item is what "this" means. |
| O8 | **Compound questions are slow under load.** | With 8 people asking at once, compound answers take 73–78 s at the median and up to 234 s (EXP-2026-11-010 A3). A 10-step limit cut that to 33.5 s but cut off half the answers. | Re-measure after fix 4 (fewer wasted steps) before changing the step limit. |
| O9 | **The `unread` check is untested.** | Single-turn questions cannot exercise it. | A multi-turn test set. |
| O10 | ~~Mylo still recalls a chat the person excluded from learning.~~ **Decided 2026-11-14: by design.** | EXP-2026-11-011 attempts 5–6: excluded content reached the answer through `thread_search` and the recall digest (Q-068). | It is the person's own chat, which still exists. Chats stop being readable when they are deleted, or when the lab or department they belong to is deleted. Nothing to do. |
| O11 | **Re-measure the answer fixes.** | — | EXP-2026-11-013 arm (a) on the project questions (answers should now use the project's description, with fewer loops). Not run today. |

## The human ratings: what they will tell you, and how to read them

The three questions that need people are written down before any answer was
seen, with thresholds, as claims C-033 to C-035 in
`docs/research/CLAIMS.md` (and in EXP-2026-11-013's `PROTOCOL.md`):

| Claim | Question | Bar | If it falls short |
|---|---|---|---|
| C-033 | Are Mylo's answers right? | Correct by majority of raters on ≥ 70% of 50 questions; ≥ 85% of citations support their sentence. | Answer quality comes before anything else above. The per-category breakdown shows where (project status, who fits, compound…). |
| C-034 | Is Mylo better than one search plus one model call? | Paired 95% interval of the difference excludes zero. | Mylo costs about 2.8× the tokens and 2.2× the time of that baseline (27.1k vs 9.6k tokens, 40.5 vs 18.8 s). If it is not better, the agent loop is not paying for itself on these question types. |
| C-035 | Does the checker catch what people catch, and is what it removes really wrong? | Removal precision ≥ 0.9; recall ≥ 0.5 of the unsupported details raters list. | Recall below 0.5 makes O1–O3 urgent. The raters' lists show which kind of error dominates, and so which of O1, O2 or O3 to build first. |

**Where the sheets are:**
`docs/research/experiments/EXP-2026-11-013-agent-answers-human-judged/data/sheets/`
- three blinded sheets of 100 answers each (Mylo and the baseline, shuffled);
- one sheet of what the checker removed;
- 101 evidence files;
- `RATER_INSTRUCTIONS.md`.

**To score them:** copy the filled sheets to `data/ratings/` and run
`code/score.py`. It writes the numbers into the experiment's results.

Note that the raters judge last night's answers. They were produced before
fixes 1–4, so the project-status questions will score low partly because of
fix 1's bug.

## Found 2026-11-14 while checking the demo (not yet fixed)

| # | What | What it needs |
|---|---|---|
| D1 | **A model outage during the report stage gives everyone a template report.** On 2026-11-14 the tunnel to the model dropped between about 12:15 and 13:08 UTC; all 19 daily reports came out `fallback`. The pre-flight passed at 12:04, so nothing stopped the run. | Check the model again before the report stage and retry it (or the whole stage) once the model is back, instead of writing fallbacks. |
| D2 | **Empty demo pages.** Saves, Reminders, Suggested and Mylo & you are empty for a visitor ("Nothing saved yet"). | Seed a few saves, one reminder, one shared paper and one pending Mylo question in `world.yaml`. |
| D3 | **The demo PI's account page says her email isn't at a recognised institution** (`showcase.mycelium.invalid`). | Give the demo people an affiliation, or hide that line in the demo. |
| D4 | **The SBIR grant source returns HTTP 403** every night, so it contributes nothing. | Look at whether the API moved or now needs a key. |
| D5 | **Beat's original stall (13:39 UTC, the second since August) is still unexplained.** The healthcheck now recovers it; the leading guess is still the `dbm.sqlite3` schedule store. | A `py-spy dump` the next time it stalls, before the healthcheck kills it. |

