# Mylo evaluation follow-ups — what was fixed, what is left

**Status (2026-11-13):** the quick fixes below are in `main` and running on the
live stack. Everything under "Still open" is untouched and waits for a
decision or for the human ratings. Delete this file once the open items are
done or moved to their own plans; the evidence stays in `docs/research/`.

**Overnight 2026-11-17 (correlation `20261116-mylo-overnight-fixes`; details in
the last section):**

- **Live:** feed lists that filter before any cut, page, and say whether they
  are complete (`f81d2837`, `ce976d2f`); a slip in a function call no longer
  uses up the function's failure limit (`035c9066`, `55cfdb1c`); every person
  and project carries a reference and the prompt says to cite each one named
  (`3ea9c144`); two sentences in the collaboration settings (`2c5abce8`);
  a function call the server reports and does not return is asked for again
  with functions on (`127428f3`, live since the 11:07 UTC restart);
  `load_functions` and `update_todos` no longer undo the references another
  call of the same step numbered (`14b758d2`, live since the 11:32 UTC
  restart, not measured by a run).
- **Reverted:** none.
- **Not run:** the public-demo collaborator search and the answer-checker work
  (phases 5 and 6, left out by the maintainer's instruction); ranking by
  "Open to" in phase 8 (stopped: the search carries no kind of collaboration,
  and adding one is a ranking change the plan excluded; Q-086); the 8-process half of the loop-cost arm A7 (33 minutes were left; its rule asked for 80).
- **Which model each number is on:** Qwen 3.8 27B is the instance model
  (relay `default-model`, shared with the maintainer's own work): the answers
  experiment's tag `r4`, the model check's two `qwen38-…-20261117` rows, the
  loop-cost arm A7. Gemma 4 31B (relay `default-model-2`, nothing else on
  it): the collaborator scenarios' tags `r4` and `r5`, the model check's two
  `gemma4-…-20261117` rows, the answers experiment's tag `r4g`. Never pooled.

**Afternoon 2026-11-17 (correlation `20261117-mylo-afternoon-fixes`; the
maintainer: "fix everything, run it"):**

- **Live since the 17:02 UTC restart:** the loop reads the thread's settings
  fresh each step, so a function loaded in one step is offered in the next
  (it was not, until the turn after), and clearing old results no longer
  undoes references (`90882479`); a step runs at most 12 calls and a turn
  that read more than fits answers from what is left (`522d7eb7`); feed lists
  filter by what a grant or fellowship pays and say what they left out for
  its currency (`ed27c8b8`, `640d7fe0`); Gemma's call markup is read as a
  call and never posted (`f9a784ee`); a person or project named without its
  number gets it, and the prompt says not to list what was ruled out
  (`0ebaed72`); the search beyond the lab points to who in the lab covers the
  call (`29d1bd92`).
- **Measured on Qwen 3.8 27B** (`EXP-2026-11-018` Amendment 8): 87% of
  stored-data answers fully right (72% twelve hours earlier, 61% before any
  fix); lists 24 of 27; people 25 of 30; no partial list presented as
  complete; no Mylo turn failed twice; the most function calls in a turn 8
  (was 72). The model check's third row: no leak, no blank turn, 10 of 12.
- **Not measured:** anything on Gemma 4 31B — its server was down all
  afternoon. That leaves the call-markup fix and the first-ask collaborator
  fix covered by unit tests only, and Gemma's amount questions (6 of 27
  partial lists presented as complete last night) unchecked. The loop-cost arm
  was stopped after 9 turns when the maintainer asked for the Qwen server
  back; compound questions with 8 in flight are still not re-measured.
- **Still wrong:** a right answer that also names what it compared against
  loses credit on six questions; no filter takes a deadline's confidence;
  Mylo still looks people up by name where a reference belongs (denied calls
  did not fall: 19 of 178 turns); in the go-live check the answer checker cut
  converted currency figures out of one answer and left broken lines.
- **Not built:** ranking by "Open to" (Q-086): it needs the maintainer's word
  on where the kind of collaboration sought comes from, how far it outranks
  match quality, and what an empty "Open to" means.
- **Also added:** `make test-fast` (the whole suite in about five minutes) and
  `make test-changed` (only the test directories a change touches).

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

## Round two measured (2026-11-15) — what changed for the open items

The second evaluation round (`EXP-2026-11-016` to `-020`, `-010` A5, `-013`
Amendment 5) ran overnight. What it says about the items above:

| Item | Now |
|---|---|
| O1–O3 | Still deferred, and now measured as mattering: a second model read 50 regenerated answers sentence by sentence and marked 51 details unsupported (18 of 50 answers had one); the checker flagged none of them. 40 of the 51 are claims with no number (O2). Model-judged; the 30-answer calibration sheet (`EXP-2026-11-020/data/sheets/calibration.csv`) is for a person. |
| O7 | Common on tonight's instance model: 23 of 144 gate-arm turns ended on a clarifying question (`EXP-2026-11-016`). Separately, turns that end with **no reply at all** — 11% of gate turns, 16% in collaborator search — are a defect (Q-070, Q-088). |
| O8 | Kept. Compound turns with 8 in flight: median 79 s (round one 73–78 s), worst 109 s (234 s). Idle turns are 3–6× slower than round one because every model call is slower on the relay model now answering as `default-model` (self-reports Google); not separable from the loop fixes. |
| O9 | Measured: the `unread` check flags 0 of 20 surfaced-but-unread references, because a search listing counts as "seen" (Q-076); an `unread` citation that survives the repair is posted (Q-077). |
| O11 | Done: the 50 questions regenerated after the fixes (`EXP-2026-11-013` Amendment 5, sheets in `data/sheets_fix1/`). By code against stored facts, Mylo earned full credit on 72% of 60 questions and beat one search plus one call by +0.42 (`EXP-2026-11-018`); no list question was answered fully, because feed functions return truncated views presented as complete (Q-079). |

New, for the owner to decide (not defects of the run): what "Delete my
observations" should stop — it removes every derived row but Mylo still reads
the undeleted chats back (53 of 100 runs; Q-072, against O4's wording); and
whether ambient should record health or immigration facts about a person
(Q-071). Defects found and left unfixed, as the plan required: Q-069 / Q-075
(a project name instead of a reference fails, and the retries use up the
function's failure budget), Q-070 / Q-088 (empty replies), Q-076 / Q-077
(`unread`), Q-078 (a single model call that streams for 15 minutes; no output
cap), Q-079 (truncated feed lists), Q-087 (a loaded function missing from the
tool list).

Two sheets wait for a person (about an hour): `EXP-2026-11-016/data/sheets/adjudication.csv`
(20 rows; the key says which project was narrowed in `scope-narrowed`) and
`EXP-2026-11-020/data/sheets/calibration.csv` (30 answers).

## Found 2026-11-14 while checking the demo — done the same day

Decided 2026-11-14: D2, D1, D4 and D5 were fixed in that order and are live
(correlation `20261114-demo-pages-and-run-guards`); D3 stays (the demo PI is a
fictional account, so "not a recognised institution" is right). Nothing in
this table is open.

| # | What | Done |
|---|---|---|
| D1 | **A model outage during the report stage gave everyone a template report.** On 2026-11-14 the tunnel to the model dropped between about 12:15 and 13:08 UTC; all 19 daily reports came out `fallback`. The pre-flight had passed at 12:04. | `ops/nightly/manual_all.py` checks the model again right before the report stage (`model_ready_for_reports`). If it is down, the run re-checks every 2 minutes for up to 30; if it never answers, the reports are written as templates and Discord is told. Tests: `mylo/tests/test_report_model_check.py`. |
| D2 | **Empty demo pages.** Saves, Reminders, Suggested and Mylo & you were empty for a visitor. | `manage.py demo seed` (`apps/demo/seed.py`) rebuilds them from the demo's own current feed: the PI's best-ranked open paper, grant and fellowship; the lab's best grant and conference at least three weeks off, saved by a teammate, each with a lab reminder; a teammate's share of the project's best paper, which delivery's fan-out suggests to her; one open question about a project topic her profile lacks, with the number of papers in her feed about it; and the project statuses as changes. It runs after `build`/`refresh` and as the nightly's platform stage after the prune. "What Mylo knows" already showed her declared interests. Tests: `apps/demo/tests/test_seed.py`. |
| D3 | The demo PI's account page says her email isn't at a recognised institution. | No change: she is fictional. |
| D4 | **The SBIR grant source returned HTTP 403** every night. SBIR.gov's API page says its APIs are "currently undergoing maintenance". | When the API refuses with 403, the adapter reads the public topic listing (`www.sbir.gov/topics?status=Open`, fresh each run) and each topic's page (cached), shaped like the API's rows, so parsing is unchanged. Tests: `tools/retrieval/tests/collect/grants/test_sbir_site.py`. |
| D5 | **Beat stalled twice and nobody knows why** (2026-08-04, 2026-11-14). The leading suspect was its `dbm.sqlite3` schedule file. | Beat now runs `config.beat:HeartbeatScheduler`: the schedule in memory, no file, and a heartbeat file touched on every tick that the healthcheck reads. If it ever stalls again the file was not the cause; take a `py-spy dump` before the healthcheck (900 s) kills it. |

## Overnight 2026-11-17 — three defects fixed, each measured by the experiment that found it

One defect, one commit, then the same questions, probes and graders as
before, under a numbered amendment registered before the first run. The suite
was green at each fix apart from four tests that were already red before any
change (`apps/accounts/tests/test_synthesize_api.py::test_site_and_resume_merge`
and three in `tools/delivery/tests/test_opportunity_clusters.py`).

| Item | Done | Measured | Still open |
|---|---|---|---|
| Truncated feed lists (Q-079, C-056) | `feeds_slate`, `feeds_saved`, `feeds_deadlines` and `projects_feed` take `due_from`, `due_to`, `deadline` and `offset`; the filter runs in the database over the whole slate; every list ends "This is the complete list…" or "This is not the complete list… pass offset=N". | `EXP-2026-11-018` Amendment 6, Qwen 3.8 27B: list questions fully right in 12/27 runs (was 2/27); a partial list presented as complete in 2/27 (was 7/27; bar 10%, interval 0.02–0.23). Amendment 7, Gemma 4 31B: 16/27 (round two 0/30); presented as complete in 6/27, all on the two amount questions, so the bar is missed on that model. | A *confirmed* deadline cannot be asked for (`l04`); conference paper deadlines come back with one item too many (`l06`, `l07`); nothing filters by amount, so Mylo reads every grant one call at a time and 3 of 6 such runs never answered (`l08`, `l09`; Q-091). |
| A slip in a call used up the failure limit (Q-069, Q-075) | Unknown or missing arguments are caught before the handler and answered with what the function accepts; they have their own ceiling of 4 and do not count toward the limit of 2; calls sent together in one step with the same slip count once; `#7 Some title` is read as `#7`. | `EXP-2026-11-021` Amendment 4: the department head's control on Gemma 4 31B ended on the give-up line before and passed after (controls 5/6 to 6/6; answered 28/31 to 31/31). `j08` on Qwen 3.8 27B: no refused call in 3 of 3. | A project *name* where a reference belongs is still denied. `j08` names the two right grants and earns no full credit, because it also cites the two it rules out. |
| People and projects named without a citation (C-043) | Every function that returns a person or a project gives it a `#n` reference; the prompt says to cite every item, person and project named, and only the ones the answer is about. | `EXP-2026-11-018` Amendment 6, Qwen 3.8 27B: full credit 72% of answerable runs (was 61%; bar 70%, interval 0.60–0.84); the gap to the name-matching grading fell from 0.10 to 0.04; project questions 30/30 (was 24/30); people 16/30 (was 15/30). `EXP-2026-11-021`: Qwen 7/12 to 9/12, Gemma 11/12 to 12/12. Amendment 7, Gemma 4 31B: 90% (round two 72%; interval 0.82–0.98), people and project 30/30 each. | People questions: Mylo cites the people it rules out (`p07`, `p10`, `j07`), or names the one right person with no number (`p01`). The graders count a cited person as named; that was not changed. |
| Empty replies (O7, Q-070, Q-088) | Measured first on Gemma 4 31B, then fixed: when the server says the model stopped to call a function and returns no call, the loop asks again with functions still on (once), instead of asking for an answer without functions. | `EXP-2026-11-019` Amendments 7 and 8, Gemma 4 31B, 180 asks each: 0 blank turns in both; 3 of 939 and 4 of 955 model calls empty, every one a call the server did not return; after the fix the path fired in 2 turns and both answered (before: one of two ended on the give-up line). | Round two's 16% blank on this model is not reproduced and nothing recorded says what differs. On Gemma, a seeker asking for the first time is answered without the planted lab-mate in 17 of 30 asks (C-050 not met in that cell); not investigated. |
| "Open to" and the collaboration settings (Q-085, Q-086) | The settings card now says that anyone may search whether or not they are findable, and that the "Open to" kinds help matching seekers find you and never hide you. | Not a measured change. | Ranking by "Open to" was not built: `matcher.Query` carries no kind of collaboration, so it would be a ranking change, which the plan excluded. The scenario that would measure it (S4) was not rerun. |
| O8, compound questions under load | No change. | `EXP-2026-11-010` arm A7, Qwen 3.8 27B, one turn at a time, 24 turns: the fixes did not raise model calls per turn (2 / 5 / 8 at the median by group, as before); tokens per turn are 6k to 11k higher on the larger questions, within run-to-run spread. | The 8-in-flight half was not run, so O8 itself is not re-measured. |

Found on the way, and where each stands:

- **The first go-live question failed.** After the first restart Mylo was asked
  one question on the public demo; it sent 24 calls in one step with
  references written as `#7 Some title`, all were denied, the failure limit
  was used up, the corrected batch was refused, and the turn ended
  `context_full` after 393 s. Fixed before any measurement (`ce976d2f`,
  `55cfdb1c`); the same question then got a full, cited answer (257 s).
- **References numbered in a step could be lost in the same step.**
  `load_functions` (and `update_todos`) wrote the thread's settings back from
  a copy read before another call of the step had numbered its results, so the
  next call on `#2` was refused as not visible and the failure limit then
  blocked it for the turn. Older than tonight's fixes (denied calls are as
  common in round three's rows). Fixed in `14b758d2`, with a test that fails
  on the old code; live since 11:32 UTC. Not measured by a run. Asked the
  question that had hit it, the demo opened the project and its feed and
  answered with citations; the first ask after the restart failed on the
  model server (relay 502) and was shown as an error, the second answered.
- **Nothing limits how many calls one step may make (Q-091).** A complete list
  invites a call per row. Seen again in the answers run. Not fixed.
- **A guest in a lab whose audience hides people still sees member names**
  in a project's member list (Q-092). Not changed: who may see whom is a
  permission question the plan put out of bounds.
- **Gemma's own call markup reached a person as the answer once (Q-093):**
  one of 177 turns ended with `<|tool_call>call:corpus_item{…}<tool_call|>` as
  its reply. Not fixed.
- **Two grader seams, not changed** (no new graders tonight): a cited item or
  person counts as named even when the answer rules it out, and the
  "states a fact" pattern reads digits in a paper's title as a citation count
  (both of Gemma's 2/30 on C-046).
- **The whole suite** (`make test`, finished 10:50 UTC, on the code that went
  live at 11:07): 5,076 passed, 4 failed — the four that were red before any change.
  The same at `14b758d2`, run from a worktree.
- **`mylo-bot.service` was not restarted** (it needs `sudo`). It holds no
  agent code — it calls the backend — so the fixes reach Discord as well.
- **Left on the database:** the four sandbox copies of tonight's scenario runs
  (`mycelium_sandbox_exp019r4rep`, `…r4fresh`, `…r5rep`, `…r5fresh`, about
  80 MB each), kept as round three's were.

