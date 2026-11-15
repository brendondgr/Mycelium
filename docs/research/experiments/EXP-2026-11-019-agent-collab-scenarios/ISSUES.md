# EXP-2026-11-019 — Issues

## Before the run

1. **The shared sandbox was two months of migrations behind** (no agent
   tables). It was not migrated in place: the experiment copies it to
   `mycelium_sandbox_exp019` (`CREATE DATABASE … TEMPLATE mycelium_sandbox`) and
   migrates the copy, so `mycelium_sandbox` and earlier experiments' state are
   untouched. The copy also carried EXP-2026-09-007's consent plan (228
   settings, 60 personal addresses, 30 unverified accounts, 876 appearances,
   300 search logs); the overlay resets all of that (PROTOCOL.md "Data").
2. **Calls are not read by the slot reader.** The sandbox's 150 planted calls
   were not in the copy (0 requirement slots), and reading new ones would spend
   the model; the experiment's 12 calls carry their one slot written directly.
3. **Within a turn, a function loaded with `load_functions` was not added to
   the `tools` list sent to the model** in the dry run (the loop's
   `_visible_functions` reads `thread.settings` from the thread object fetched
   at the start of the turn; `load_functions` writes a fresh copy). The real
   model still calls such functions by name (round one's logs: `load_functions`
   followed by the loaded functions, and the gate decides each call), so this
   does not change what is graded here. Not fixed (plan rule); recorded as
   Q-087.
4. **`dirty: true`.** Other phases' agents were writing their own experiment
   folders in the same checkout during this run; nothing under `web/`,
   `tools/` or `ops/` was modified by anyone. The commit in the manifest is the
   one the run executed.
5. **Plan rows the product does not state** (S6 "not opted in themself", S4
   "restricted `open_to`"): decided before the run, PROTOCOL.md decisions 1–2;
   Q-085, Q-086.

## During the run

1. **Baseline directory, lexical match narrowed before the baseline's first
   counted run** (commit after `c52f5a00`). The dry run's query "the call's
   method" matched every concept called "method" because the directory also
   accepted any concept whose words appear inside the query. It now accepts a
   concept inside the query only when the concept is at least ten characters
   long; the embedding bars are unchanged. Only the baseline arm's harness
   changed; the gate arm (already running) does not use it.
2. **Empty turns.** Some turns end after one model step with no text, no
   function call and no error event (gate repetition 0: 5 of 103 under
   grading v2; baseline: 3). They are vacuous runs: kept in the logs, counted
   separately, out of the rates (PROTOCOL.md "Graders").
3. **Turns that end on a question** (`ask_user`; gate repetition 0: 2, both
   S8, Mylo asking for the target's username because it cannot see them) were
   graded empty by v1; Amendment 2 (grading v2) grades the question too.
4. **Refused calls in the shared rooms (S9) come from the model's arguments,
   not the gate's rules**: `corpus_item` on the tagged call was refused
   `not_visible` when the model quoted the reference (`"#1"` or `` `#1` ``),
   and `org_department` when it passed a lab's or the department's name instead
   of a reference. Calls with a well-formed `#1` passed.
5. **Empty answers (defect; Q-088; not fixed).** 49 of 309 gate turns and 7 of
   309 baseline turns ended after one model step with an empty final message
   (`repairs: ["empty_retry"]`, checker verdict ok): the person would see
   nothing. By repetition (gate) 5, 19, 25; 11 of 15 S10 "pressure" asks.
   Counted as vacuous runs (PROTOCOL.md), and shown beside claim (a).
6. **Recall across repetitions** (Amendment 3). The same seeker asks the same
   question in every repetition and arm, and Mylo recalls the person's own
   earlier conversations (279 of 309 runs per arm had a recall block, which
   carried the earlier question text). No recall named anyone outside consent.
   Repetitions are therefore not independent draws; a cleaner design deletes
   the seeker's earlier threads before each run.
7. **The first driver was stopped at 08:40 UTC** while baseline repetition 1
   was running (that run was left to finish and completed all 103 runs), so
   that repetition 2 could run at the coordinator's new allowance of three
   requests in flight (`code/drive_rep2.sh`). The time rule was applied as
   registered (pair 1 took 5,593 s at one request in flight; 8,005 s were
   left).
8. **Harness commits.** The gate arm ran `run019.py`/`world019.py` as committed
   in `3a77aef3`; the baseline arm also used `baseline019.py` as fixed in
   `1b953eae`. Later commits touched only drivers and analysis. No product
   code changed during the night.
