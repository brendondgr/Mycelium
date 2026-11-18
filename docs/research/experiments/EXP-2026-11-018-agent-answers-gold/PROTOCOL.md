# EXP-2026-11-018 — Protocol

Written 2026-11-15, before any answer was generated; committed with the
frozen questions (`code/questions.json`), gold (`data/gold.json`), grader
(`code/grade.py`, `code/normalise.py`) and the claim rows C-043 to C-046.
Phase 3 of `docs/plans/20261115-mylo-evaluation-round-two.md`.

## Question

When the demo lab's PI asks Mylo a question whose correct answer is stored in
the database, how often is the answer exactly right — every gold object named
and nothing wrong stated — and is that better than one search plus one model
call, and better than Mylo without its lab, project and people functions?

## Hypothesis

Stated as claims before the run (CLAIMS.md):

- **C-043 (a)** Arm (a) earns full credit on at least 70% of answerable runs.
- **C-044 (b)** Arm (a) beats arm (b) on full credit: paired bootstrap 95%
  interval of the difference excludes zero.
- **C-045 (c)** Arm (a) beats arm (c) on the project, people and join kinds.
- **C-046 (d)** On unanswerable questions arm (a) states a fact in at most
  10% of runs.

Expectation, from reading the code: arm (b) fails the project, people and
list kinds almost entirely (it sees only the corpus); arm (c) fails project
and people questions it cannot reach through the system prompt; field
questions on tagged items are close between arms. The strict citation rule
for naming objects may cost arm (a) on people questions, which is why the
secondary grading is reported beside it.

## Setup

- System under test: Mylo (`tools/agent/`) at the commit in `manifest.yaml`
  (contains `60ae301`, round one's fixes), instance model `default-model` via
  `llm-tunnel` (see `env/hardware.md`: the model behind it changed since round
  one and is identified only by its self-report), instance defaults.
- Asker: the public demo world's PI (`demo.mara`, fictional), lab scope
  (`coastal-ocean-lab`), `surface="web"`, audience `person`. One fresh demo
  thread per job (`demo_visitor="EXP-2026-11-018"`): no learning pass; deleted
  at the end of the run. Nothing else is written to the live database.
- The corpus and slates are the live ones at the snapshot in `data/gold.json`
  (2026-11-15 05:43 UTC). The nightly run, which re-ranks, starts at 12:00
  UTC; every run here ends before 11:15 UTC, so gold and answers see the same
  slates. Date windows ("next 30 days") are relative to 2026-11-15.
- `AGENT_PARALLEL_CALLS=0` (one request in flight per turn; shared server).

## Data

`code/build_gold.py` (read-only) computes every gold answer from the stored
rows the product's functions read, and writes `code/questions.json` and
`data/gold.json` (per question: the query, gold object ids, gold values, the
values stored on the records involved, the snapshot). Sixty questions, ten
per kind:

| kind | what | gold |
|---|---|---|
| `field` | a stored field of a tagged item: 3 amounts, 3 deadlines, 2 venues, 2 author lists | values |
| `list` | a filtered list from the **lab's feed** (`in_slate` rows for the lab): grants/fellowships/conferences by deadline window, amount, currency | item ids (2–7 each) |
| `project` | a project's progress, watched topics, other members, and four facts in its stored status text | values or people |
| `people` | who declares an interest (6), "involving machine learning" (1), a named member's declared interests (2), who is not on a project (1) | people or values |
| `join` | a watched topic → the project → the first paper of its feed (2); a topic or member → the project → the first grant, conference or fellowship (4); project members × interests (1); grants in both projects' top three (1); a member's project → its progress (1); earliest deadline among a feed's top three grants (1) | mixed |
| `unanswerable` | a fact absent from every record the agent can read for it: an amount on three grants with none stored, citation counts of two papers, a conference's acceptance rate, two project budgets... | declining |

The final unanswerable set is u01–u10 in `questions.json`: three grant amounts,
two citation counts, an acceptance rate, a project budget, a member's email,
a member's phone number, a member's h-index. The builder rejects any whose
fact pattern appears in the record text the agent could read (`corpus_item`,
`projects_get`, `org_person` output). The plan's example join "a member's
career stage → fellowships whose eligibility rule admits them" is **not**
included: career stage (`Profile.academic_title`) is not exposed by any agent
function, so the question would test nothing Mylo can reach. Candidates are
listed in a fixed order in the builder; the first ten valid per kind are
kept (`l12` was rejected for 11 gold items; `u11`–`u14` were not needed).
Questions were written by the implementing agent; no question names a real
person (the people are the demo's fictional members; items are real corpus
records).

## Arms

Same model, same port, three repetitions each (`code/run.py`):

- **(a)** Mylo as shipped: `EXP-2026-11-013/code/mylo_turn.run_question`.
- **(b)** one `corpus_search` and one model call: `EXP-2026-11-013/code/generate.arm_b`
  unchanged (tagged items' records first, then search results' full records,
  numbered `#1..k`, cite `#n`, no tools), budget fixed at 27,100 tokens (round
  one's arm (a) mean; the 20-result search cap keeps arm (b) below it).
- **(c)** Mylo with only the corpus functions loaded: arm (a) with the
  function catalog reduced, inside the harness process, to the agent's own
  housekeeping functions (`ask_user`, `update_todos`, `find_functions`,
  `load_functions`, `read_skill`, `read_result`, `thread_search`) plus
  `corpus_*` and `fulltext_*`. Removed: `feeds_*`, `projects_*`, `org_*`,
  `me_*`, `knowledge_*`, `files_*`. The system prompt is unchanged, so arm (c)
  still sees the lab block and the asker's own profile and project names.

540 jobs (60 × 3 arms × 3 reps), shuffled with seed 20261115, 3 in flight.
A job that raises, hits the 900 s deadline or ends with no final text is
recorded as failed and retried once after all jobs; both rows are kept.

## Metrics

Grading is code only (`code/grade.py`, `code/normalise.py`; not
`tools/agent/verify.py`):

- An answer **names an object** when it cites `#n` and the harness resolves
  `#n` to that object's id (arms a/c: the thread's reference table; arm b: its
  numbered evidence). Only objects of the gold's kinds (and, for items, the
  gold's corpus types) count. **Secondary grading**, reported beside every
  number: also a gold object whose title (first eight folded words), project
  name, or person's first name or surname appears in the text.
- **Values**: dates, amounts (currency-marked; scale words; ranges; equal
  within 1%), percentages (±0.5) by the normaliser; phrases by folded
  substring with listed alternates. A stated date/amount/percentage of a
  question's checked type that matches nothing stored on the involved records
  (or today's date) is a wrong statement.
- Per question: recall of gold units; precision of named units (objects plus
  checked values; 1 when nothing is named); **full credit = recall 1 and
  precision 1** (primary metric).
- Unanswerable: `states_fact` if the question's fact pattern (amount,
  percentage, or the regex in `gold.json`) matches; `declines` if the decline
  pattern matches; full credit = declines and states no fact.
- A job is graded on its first non-failed attempt; a job with no successful
  attempt scores 0 and is counted as failed.

Intervals: Wilson 95% for rates over runs; for arm (a)'s answerable rate and
for every arm difference, a bootstrap over **questions** (per-question mean
over the three repetitions; 10,000 resamples, seed 20261115, percentile
interval), paired by question for differences.

## Decision rules (fixed now)

- **C-043** supported if arm (a)'s full-credit rate over the 150 answerable
  runs (primary grading) is ≥ 0.70; the bootstrap interval is reported.
- **C-044** supported if the paired bootstrap 95% interval of
  (arm a − arm b) full credit over all 60 questions (primary) lies above zero;
  refuted if it includes zero or lies below. Answerable-only and per-kind
  differences are reported.
- **C-045** supported if the paired interval of (arm a − arm c) over the 30
  project, people and join questions lies above zero **and** the point
  difference is positive in each of the three kinds; partial if the pooled
  interval is above zero but one kind is not; refuted otherwise.
- **C-046** supported if arm (a) states a fact in ≤ 10% of its 30
  unanswerable runs (Wilson interval reported).
- Every claim is decided on the primary grading. The secondary grading is
  reported and never substituted.

## Baselines

Arm (b) (retrieve-then-answer, as round one) and arm (c) (the agent without
its lab, project and people functions).

## Procedure

```bash
R="docker compose run --rm --no-deps -T --user $(id -u):$(id -g) -e HOME=/tmp -e AGENT_PARALLEL_CALLS=0 -v $PWD/docs/research:/app/docs/research backend uv run --no-sync --project web/backend python"
E=docs/research/experiments/EXP-2026-11-018-agent-answers-gold
$R $E/code/build_gold.py            # once, before this protocol was committed
$R $E/code/run.py --dry-run         # job list and arm-c catalog, no model call
$R $E/code/run.py --conc 3          # 540 jobs → data/runs.jsonl
python3 $E/code/grade.py            # → data/graded.jsonl, metrics.json/.csv, tables/summary.md
python3 $E/figures/make_figures.py
$R $E/code/cleanup.py               # delete this experiment's demo threads
```

## What would falsify this

C-043 fails below 70% full credit. C-044 fails if the paired interval
includes zero or favours arm (b). C-045 fails if the pooled interval includes
zero. C-046 fails above 10% fact-stating on unanswerable questions.

## What it cannot show

Usefulness; correctness on questions with no stored answer; anything about
real labs (one fictional lab, its two projects and five members, on the live
corpus). C-033 and C-034 need people and stay `unsupported`; C-043 to C-046
are new rows beside them. Questions and grader were written by the
implementing agent.

## Amendment 1 — 2026-11-15 ~06:20 UTC, during the run, before any grading was recorded

Prompted by EXP-2026-11-016's Amendment 1: a turn can end with `ask_user`;
the person then sees a clarifying question (an event of type `question`) and
the turn has no final answer. The pre-registered grading treats such a job as
**failed** (`no_final_text`), retries it once, and scores a job with no
successful attempt as 0 — and, for an unanswerable question, as *not* stating
a fact (`states_fact` 0) and not declining (full credit 0). That grading stays
the primary one and is unchanged. Added, and reported beside it:

1. **Count of turns that end on a question**, per arm and per attempt
   (`state == "waiting"`), and the question texts, read from the threads'
   events before they are deleted (`code/asked.py` → `data/asked.jsonl`).
2. **First-attempt grading** (`grade.py --first-attempt`): only each job's
   first attempt is graded, so the retry's second chance is removed; a first
   attempt that ended on a question scores 0 and states no fact. This shows how
   much the retry rule moves each arm.
3. A turn that ended on a question is reported as its own category
   (`asked`) in RESULTS.md, separate from harness failures (exception,
   deadline).

Partial grades were looked at once mid-run (from a scratch copy, to check
that the grader reads real answers as intended); no question, gold value,
grader rule or bar was changed.

## Amendment 2 — 2026-11-15 ~07:05 UTC, after the run, grader found wrong

Reading the graded answers, every arm (a) answer to `u08` ("What is Sun-hee
Park's email address?") was "Sun-hee Park's email address is not visible to
me." — a refusal, stating no fact — but the pre-registered decline pattern has
no verb for "visible", so all three runs scored `declines` 0 and no full
credit. The pattern gains `visib` (`normalise.DECLINE_V2`, `grade.py
--decline-v2`). Both gradings are reported (`data/metrics.json` is the
pre-registered one, `data/metrics_amend2.json` the amended one); the claims
are decided on the pre-registered grading. `states_fact` (C-046) does not
depend on the decline pattern and is the same under both.

## Amendment 3 — 2026-11-16, round three, Phase 2, before its first answer (tag `r3`)

Plan: `docs/plans/20261115-mylo-evaluation-round-three.md`, Phase 2 (Q-079,
Q-075, C-043). Measures `a8e21c0` (feed lists say when they show only part;
a project's exact name resolves as its reference) on whatever model serves.

1. **Gold recomputed before any answer** (done 2026-11-16 ~17:10 UTC, before
   this amendment was committed; no answer had been generated):
   `code/build_gold_r3.py` = `build_gold.py` with three listed changes
   (frozen questions only, a rejected one dropped not replaced, writes
   `data/gold_r3.json`). Kept 59; **dropped `l02`** (gold size 12 > 8). Gold
   changed for `l03`, `l04`, `l05`, `l06`, `l07`, `j01` (the feeds moved);
   round two's `data/gold.json` is kept beside it.
2. **Runs.** `code/run.py` unchanged — all three arms, three repetitions, the
   59 kept questions (`--only` with every arm:rep:qid key except `l02`;
   `code/jobs_r3.txt`), `--conc 4`, `--out data/runs_r3.jsonl`. A failed job is
   retried once at the end, as before. Graded by `code/grade.py` unchanged —
   primary and secondary gradings, and first-attempt — against `gold_r3.json`
   (`code/grade_r3.py` points `grade.py` at it and writes `_r3` outputs).
3. **New measure for list questions, fixed now.** For each arm-(a) and
   arm-(c) run of a `list` question (`code/partial_r3.py`):
   - the run *saw a partial list* when any function result it received
     contains `only the first <n> of <m>` or `<n> more deadline(s) fall(s)
     after`;
   - **(i) fetched the rest**: a later result of the same function in that
     run carries no such marker;
   - else, when the run has no final text (it ended on a question; the
     harness keeps no question text), **no answer** — nothing was presented;
   - else **(ii) said it was partial**: the final text matches, case-insensitively, `\b(first|top|only)\s+\d+\s+(of|out of)\s+\d+`,
     `\bpartial\b`, `\bnot (a )?(complete|full|exhaustive)\b`,
     `\b\d+\s+more\b`, `\bmore (items|results|grants|fellowships|conferences|calls|papers|deadlines)\b`,
     `\bnot all\b`, `\b(and|plus) others\b`, `\bincomplete\b`;
   - else **(iii) presented as complete** — the old defect.
   Reported per arm: (iii) over all list runs, and (iii) over runs that saw a
   partial list.
4. **`j08`** (round two's blocked corrected call) is reported on its own:
   every attempt's calls, errors and grade.

**Claims.** C-043 to C-046 re-read against their own bars on this model,
beside (never pooled with) round two's numbers. C-056 (new, written first): on
list questions Mylo (arm a) presents a partial view as complete in at most 10%
of runs (measure 3, (iii) over all arm-a list runs).

**Model.** Recorded with the operator's statement at the start and end of the
run; numbers reported beside it. A failed turn (relay error) is a failed
attempt as before.

## Amendment 4 — 2026-11-16 20:40 UTC, before the rerun on Qwen 3.8 27B (round three)

- **The model.** The operator stated **Qwen 3.8 27B** on the relay's `default-model`. Preflight (`EXP-2026-11-021-agent-model-check/logs/preflight_qwen38.jsonl`, 20:33 UTC): endpoint healthy; self-reports Qwen, Alibaba / Tongyi Lab, and is instructed not to give a version, so the version rests on the operator's statement. Recorded at the start and end of every part, as registered.
- **The earlier counted run failed.** Amendment 3's first run (MiniCPM 4.7 35B-A3B, 2026-11-16 17:06–18:36 UTC) met a server outage and is recorded as a failed run (RESULTS.md AMENDMENTS); its files are in `outage-20261116/`. This run uses the registered file names.
- **8 in flight, not 4.** The operator asked for about 8 Mylo turns in flight (16 at most). The harness limit is raised from 4 to 8 and Phase 2 (`run.py --conc 8`) runs with `--conc 8`, one part at a time.
- **Other load on the server.** The operator is running 8 concurrent sequences of their own against the same server for the whole run, so the server carries about 16 streams. Seconds measured here are under that load and are not compared with earlier rounds' idle seconds. Outcome classes and grades are read as registered; a server failure or timeout may be more likely, and is counted, not rerun beyond the registered single retry.
- Nothing else changes: questions, gold, graders, classes and hypotheses are as registered.

## Amendment 5 — 2026-11-16 20:50 UTC, before any run on the second server (round three)

- **The server.** The operator moved the run to a second server, the relay's `default-model-2`, which serves **Qwen 3.8 27B** (the operator: both endpoints serve Qwen 3.8 27B) and carries nothing else. Every one-off container runs with `LLM_MODEL=default-model-2`, so the instance's own model route answers from that server; the harness code is unchanged apart from the limit below, and every log records the model name `default-model-2`. Preflight 20:41–20:42 UTC: endpoint healthy, self-reports Qwen (Alibaba / Tongyi Lab) without a version, server `vllm-0.31.1rc1.dev344+g5b0b8f251-98b23dce`; 64 requests sent at once all returned 200 in 4.3–6.2 s.
- **Up to 64 in flight.** The operator said the second server takes 64 concurrent requests. The harness limit is raised to 64. No Mylo function calls the decision server (only the nightly opportunities pipeline does), so only `default-model-2` carries this load; the host's Postgres (100 connections) and CPU are shared with the live instance as before.
- **The run on `default-model` was stopped** at 20:41 UTC, three minutes into Phase 1, when the operator moved the work; it is not counted (ISSUES.md).
- **Concurrency.** `code/drive_r3_s2.sh`: `run.py --conc 64`, the 531 registered jobs, alone on the second server.
- Nothing else changes: questions, gold, graders, classes and hypotheses are as registered.

## Amendment 6 — 2026-11-17 05:30 UTC, after three product fixes, before the first answer (tag `r4`)

Plan: `docs/plans/20261116-mylo-overnight-fixes.md`, Phase 4. Measures three
fixes committed tonight, on the instance model (the operator: **Qwen 3.8 27B**
on the relay's `default-model`, shared with the operator's own work):

- `f81d2837` — feed lists take a deadline filter applied before any cut, page
  with `offset`, and end by saying whether they are complete (Q-079, C-056);
- `035c9066` — a malformed call no longer uses up a function's failure limit
  (Q-075; `j08`);
- `3ea9c144` — every person and project a function returns carries a
  reference, and the prompt says to cite each one named and only those (C-043);
- `62c9fa17` — the slate reader keeps its old name, because `build_gold.py`
  imports it (no behaviour change).

1. **Gold recomputed before any answer** (2026-11-17 05:24 UTC):
   `code/r4.py gold` runs `build_gold_r3.py` unchanged and writes
   `data/gold_r4.json`. Kept 59; `l02` dropped again (gold size 12 > 8). No
   question's gold objects differ from `gold_r3.json`.
2. **Runs.** `code/run.py` unchanged: three arms, three repetitions, the 59
   kept questions (`code/jobs_r4.txt`, 531 jobs), `--conc 8` (the plan's limit
   on the instance model), `--out data/runs_r4.jsonl`, a failed job retried
   once at the end as before (`code/drive_r4.sh`).
3. **Grading and the partial-list measure, unchanged.** `code/r4.py grade`
   (primary and secondary; `--first-attempt`) runs `grade.py` against
   `gold_r4.json`; `code/r4.py partial` runs `partial_r3.py` with its
   registered patterns and classes. `r4.py` only stages file names; it holds
   no grading code.
   - The fix changed how a cut list reads. A cut result still says
     `only the first <n> of <m>` (now in its last line), so the registered
     marker still finds it; a complete result says `all <n> of <n>` and carries
     no marker, as before.
4. **`j08`** reported on its own, as in Amendment 3.
5. **A frozen copy of the code.** The run's containers mount
   `git archive 62c9fa17` of `tools/` and `web/backend/` read-only over the
   checkout's, so every job reads that commit while the checkout is edited.

**Claims, read against their own bars, beside (never pooled with) round two's
and round three's rows:** C-043 (full credit ≥ 70% of answerable runs), C-044,
C-045, C-046, C-056 (a partial list presented as complete in ≤ 10% of arm-(a)
list runs). **What would count against a fix** (the plan's words): fix 1 —
C-056's bar missed again; fix 2 — `j08`'s corrected call refused again; fix 3 —
the gap between the primary and the secondary grading not narrower than round
three's (0.61 against 0.71 on this model).

**Model and load.** Recorded at the start and end (`logs/model_r4.jsonl`). The
server is shared, so seconds are not compared with any earlier round. No new
turn after 11:40 UTC (the nightly run starts 12:01 UTC and moves the feeds).

**Added 2026-11-17 05:56 UTC, still before the first answer.** The go-live check
(one question to the public demo after the restart) found two things, fixed
before any run: `ce976d2f` — a deadline-filtered slate keeps "who should look",
as the rank-order view has it; `55cfdb1c` — calls sent together in one step
with the same slip count once toward the failure limit, and a reference passed
with its title after it (`#7 Some title`) is read as `#7`. In that check Mylo
sent 24 calls at once with such references, all were denied, the limit was
used up, the corrected batch was refused, and the turn ended `context_full`.
**The frozen copy every run of this amendment mounts is `55cfdb1c`**, not
`62c9fa17`.

## Amendment 7 — 2026-11-17 08:50 UTC, before any answer on Gemma 4 31B (tag `r4g`)

Not asked for by the plan, which measures on the instance model. Added because
the second server is free once `EXP-2026-11-019`'s runs have ended, and round
two's rows (the only earlier rows on Gemma 4 31B: full credit 0.72, list 0/30)
then have a row on the same model after the fixes.

- **Runs.** Amendment 6's design unchanged: the same 531 jobs
  (`code/jobs_r4g.txt` = `jobs_r4.txt`), `code/run.py` unchanged, the gold of
  Amendment 6 (`data/gold_r4.json`, computed 05:24 UTC), `--out
  data/runs_r4g.jsonl`, `code/drive_r4.sh` with `TAG=r4g`,
  `LLM=default-model-2`. `--conc 16` (the plan's limit of 8 is for the instance
  model; this server carries nothing else).
- **Code under test:** a frozen copy of `127428f3` — the commit Amendment 6's
  run reads (`55cfdb1c`) plus the lost-call retry that `EXP-2026-11-019`
  Amendment 8 found Gemma needs. The two models' rows therefore differ by that
  one commit as well as by the model; the retry fires only on an empty reply
  whose finish reason is `tool_calls`.
- **Grading and the partial-list measure:** `R4_TAG=r4g code/r4.py grade`
  (and `--first-attempt`), `R4_TAG=r4g code/r4.py partial`, unchanged code.
- **Read as:** C-043 to C-046 and C-056 on their own bars for this model,
  beside round two's Gemma row; never pooled with Qwen's.
- **Model:** the operator states Gemma 4 31B on `default-model-2`; recorded at
  the start and end (`logs/model_r4g.jsonl`). No new turn after 11:40 UTC. Both
  runs ask in the demo lab at the same time (at most 24 turns in the live
  database); threads are deleted after both have ended (`code/cleanup.py`).

## Amendment 8 — 2026-11-17 17:10 UTC, after seven more fixes, before the first answer (tags `r5`, `r5g`)

The maintainer's instruction of 2026-11-17 (afternoon): fix what Amendments 6
and 7 left wrong, then measure again. The fixes, all committed before this
amendment:

- `14b758d2` — `load_functions` and `update_todos` no longer write the
  thread's settings back whole (last night's fix, not yet measured);
- `90882479` — the loop reads the thread's settings fresh each step and every
  writer changes only its own key: a function the model had just loaded was
  not offered, with its arguments, until the turn after (so the model called
  it blind), and clearing old results could undo references numbered since
  (Q-094);
- `522d7eb7` — a step runs at most 12 calls (`tools.agent.step_calls`), and a
  turn that read more than the window holds answers from what is left instead
  of ending `context_full` (Q-091);
- `ed27c8b8`, `640d7fe0` — a feed can be listed by what its grants and
  fellowships pay (`amount_min`, `amount_max`, `currency`), checked over the
  whole slate; every slate row states the amount; a filter says what it left
  out for being in another currency (Q-091);
- `f9a784ee` — Gemma's own call markup is read as a call, and call markup is
  never posted as the answer (Q-093);
- `0ebaed72` — a person or project named without its reference number gets
  it, and the prompt says to name only what answers the question, not what
  was ruled out (C-043);
- `29d1bd92` — the search beyond the lab says it lists no lab-mates and points
  to `knowledge_people_for_call` (EXP-2026-11-019, S1).

1. **Gold recomputed before any answer** (2026-11-17 17:05 UTC, after the
   12:01 UTC nightly run moved the feeds): `R4_GOLD=r5 code/r4.py gold` runs
   `build_gold_r3.py` unchanged and writes `data/gold_r5.json` (`r4.py` now
   takes the gold's name from `R4_GOLD`; nothing else in it changed). Kept 59;
   `l02` dropped again (gold size 12 > 8). The gold objects of `l04`, `l05`,
   `l07` and `l10` differ from `gold_r4.json`; the other 55 are the same.
2. **Runs.** Amendment 6's design unchanged: `code/run.py` unchanged, three
   arms, three repetitions, the 59 kept questions (`code/jobs_r5.txt`, 531
   jobs), a failed job retried once at the end, `code/drive_r4.sh` with
   `TAG=r5`, `--conc 8`, on the instance model.
3. **Grading and the partial-list measure, unchanged:** `R4_GOLD=r5 R4_TAG=r5
   code/r4.py grade` (and `--first-attempt`), `… code/r4.py partial`. The
   partial-list marker is as registered: a cut result still says `only the
   first <n> of <m>`; an amount-filtered result ends with the same closing
   line as a deadline-filtered one.
4. **`j08`** reported on its own, as before.
5. **A frozen copy of the code:** every container mounts `git archive
   640d7fe0` of `tools/` and `web/backend/` read-only.
6. **Counted from the run rows, with no new grader:** arm-(a) runs that failed
   on both attempts, by question; turns with at least one denied call, and
   their full credit beside the turns with none (Q-094); turns whose step
   limit refused a call (`too_many_calls`) and turns that ended through the
   answer-from-what-fits path (verdict `fit_final`); final answers that are
   call markup; final answers in which a name was numbered (`numbered`), if
   the run rows carry it.

**Claims, on their own bars, beside (never pooled with) the earlier rows on the
same model:** C-043, C-044, C-045, C-046, C-056. **What would count against a
fix:** the amount filter and the step limit — an arm-(a) run on `l08` or `l09`
that ends with no answer on both attempts, or C-056's bar missed; the citation
fix — full credit on the nine people questions not above Amendment 6's 16 of
30 runs on this model, or the gap between the primary and the secondary
grading wider than Amendment 6's; the settings fix — more turns with a denied
call than Amendment 6's 17 of 181.

**Model and load.** Preflight 16:41 UTC
(`EXP-2026-11-021/logs/preflight_afternoon_20261117.jsonl`): `default-model`
healthy and self-reports Qwen (the operator's statement of 2026-11-16: **Qwen
3.8 27B**, shared with the operator's own work); **`default-model-2` (Gemma 4
31B last night) is down** — the relay reports `failed`, "All connection
attempts failed". So the run is `r5` on Qwen 3.8 27B. **`r5g`** is the same
run on `default-model-2` (`code/jobs_r5g.txt` = `jobs_r5.txt`, `--conc 16`,
the same gold and frozen copy), started only if that server is healthy again
and self-reports as Gemma before 05:00 UTC on 2026-11-18 (local midnight:
after it "today" in the questions is another day than the gold's); otherwise
recorded as not run. The model is recorded at the start and end of each run
(`logs/model_r5.jsonl`, `logs/model_r5g.jsonl`). No new turn after 11:40 UTC
on 2026-11-18 (the nightly run starts 12:01 UTC). Demo-lab threads named
`EXP-` are deleted after the runs (`code/cleanup.py`).

**Added 2026-11-17 17:31 UTC, during the run.** The maintainer raised the limit
on the instance model from 8 to 32 turns in flight ("You can do 32
concurrently"). The run was stopped after 64 of 531 jobs had been recorded
at `--conc 8` and started again with `--conc 32`; `run.py` skips the jobs
already in `data/runs_r5.jsonl`, and the jobs in flight when it was stopped are
asked again. Nothing else changes. Seconds were already not compared with any
earlier round; within this run they now come from two loads, so they are not
compared with each other either. A job that hits `run.py`'s deadline under the
higher load is retried once at the end as registered, and counted as failed if
it fails again: the count of such jobs is reported beside Amendment 6's.

**Added 2026-11-17 17:34 UTC, before any `r5g` answer.** The maintainer is
starting the second server again for Gemma 4 31B and asked for 32 turns in
flight on it. `r5g` runs with `--conc 32` (not 16) once `default-model-2` is
healthy and self-reports as Gemma; the watcher asks every two minutes.

**Added 2026-11-17 20:36 UTC, before any `r5g` answer.** The maintainer is
restarting the second server now. The watcher asks every 30 seconds instead of
every two minutes; nothing else changes (`--conc 32`, the same gold, frozen
copy and 05:00 UTC limit). The same watcher then starts EXP-2026-11-021's
Gemma row and EXP-2026-11-019's `r6` as their protocols register them.


**Added 2026-11-17 22:05 UTC, before any `r5g` answer.** The second server did
not come back. The maintainer restarted the first one instead, and it now
serves Gemma: at 22:04 UTC `default-model` is healthy and answers "I am a large
language model, trained by Google" (vLLM 0.21.0), while `default-model-2` is
still `failed` (`EXP-2026-11-021/logs/preflight_evening_20261117.jsonl`). The
watcher was asking the wrong endpoint. The maintainer states the model is
Gemma 4 31B and that it takes 32 in flight. So `r5g` runs on `default-model`
(`LLM=default-model`), `--conc 32`; everything else is as registered (the same
jobs, gold, frozen copy of `640d7fe0`, graders and 05:00 UTC limit). The model
is recorded at the start and end of the run in `logs/model_r5g.jsonl`. This
endpoint is also the instance model, so the instance's own use shares the
server with the run; seconds are not compared with any other run.

## Amendment 9 — 2026-11-18 02:37 UTC, after the feed fix, before the first answer (tag `r6g`)

- **What `r5g` left open (Q-095).** On Gemma 4 31B three list questions about
  "the lab's feed" were 0/3 each: `l07` (the deadline list labelled an item
  that is in the person's feed and the lab's as "from your feed" only, and the
  answer left it out), `l08` and `l09` (the model filtered each project's
  feed instead of the lab's).
- **The fix, committed before this amendment** (`36e1ee03`): a deadline row
  names every save list and feed the item is in; the one-line index entries
  and descriptions of `feeds_slate`, `projects_feed` and `feeds_deadlines`
  say which of them reads the lab's feed.
- **The run: only what the fix can move.** Arm (a) only, the nine kept list
  questions and the ten join questions (the join questions call the same feed
  functions, so they are where the rewording could do harm), three
  repetitions: 57 jobs (`code/jobs_r6g.txt`, a subset of `jobs_r5g.txt`).
  `code/run.py` and `code/drive_r4.sh` unchanged, `TAG=r6g`, `--conc 32`, on
  `default-model` (operator-stated Gemma 4 31B since the evening of
  2026-11-17; recorded at the start and the end in `logs/model_r6g.jsonl`; if
  it does not self-report as Google's the run is not started), a frozen copy
  of `36e1ee03`. A failed job is retried once at the end as before.
- **Gold unchanged:** `data/gold_r5.json` (no nightly run has moved the feeds
  since it was computed; the run must start before 05:00 UTC on 2026-11-18,
  after which "today" in the questions is another day).
- **Grading unchanged:** `R4_GOLD=r5 R4_TAG=r6g code/r4.py grade` and
  `… partial`; `code/r5_counts.py r6g r5g`. With one arm there is no
  comparison between arms and no claim about C-044 or C-045; field, project,
  people and unanswerable questions are not asked, so no overall full-credit
  rate is reported and C-043 and C-046 keep `r5g`'s rows.
- **Read as.** List full credit beside `r5g`'s 15 of 27, by question; join
  beside 27 of 30; C-056's marker beside 3 of 27. **What would count against
  the fix:** `l07`, `l08` or `l09` still 0/3; any list or join question that
  was 3/3 in `r5g` and is not now.

**Added 2026-11-18 02:50 UTC, after the `r6g` run (a correction, not a change
to it).** The day limit above is wrong, and so is Amendment 8's: the instance's
day is UTC (`TIME_ZONE = "UTC"`), so "today" became 2026-11-18 at 00:00 UTC,
not at 05:00 UTC. `r5g` (22:05–22:46 UTC on the 17th) ran on the gold's day;
`r6g` (02:40–02:42 UTC on the 18th) ran a day after it. Three of its questions
depend on the day (`l04`, `l05`, `l07`). Checked after the run, with the gold
builder unchanged: `R4_GOLD=r6g code/r4.py gold` at 02:47 UTC
(`data/gold_r6g.json`, today 2026-11-18) gives the same gold objects as
`gold_r5.json` for all 59 questions. The registered grading against
`gold_r5.json` stands, and it is the same as grading against the day's own
gold.


## Amendment 10 — 2026-11-18 ~17:40 UTC, before any answer: the full run on Qwen 3.8 27B after the feed fix (tag `r7`)

- **Why.** Qwen 3.8 27B's full row (`r5`, 87%) is from before the feed fix (`36e1ee03`, Amendment 9); Gemma 4 31B's full row is `r5g`. The maintainer asked for a full run on Qwen after the last list fix.
- **The run: Amendment 8's design, unchanged.** `code/run.py` unchanged, three arms, three repetitions, every kept question, a failed job retried once at the end, `code/drive_r4.sh` with `TAG=r7`, `LLM=default-model-2`, `EVAL_MODEL_NAME="Qwen 3.8 27B"`, **`--conc 60`** (at most 60 in flight: a turn makes one request at a time; the maintainer allows 64 on that server, which carries nothing else), a frozen copy of **`a99e1a01`** (contains `36e1ee03` and the Q-096 fix `8dc27349`). Model recorded at the start and end in `logs/model_r7.jsonl`.
- **Gold recomputed immediately before the first answer**, with the builder unchanged: `R4_GOLD=r7 code/r4.py gold` → `data/gold_r7.json`; the job list is `R4_GOLD=r7 code/r4.py jobs` → `code/jobs_r7.txt` (expected 531 jobs, the same as `jobs_r5g.txt`; if the kept set differs it is the gold's and is reported). The run starts only in a window that keeps the gold and every answer on one UTC day and clear of the nightly run (12:00 UTC): not after 22:00 UTC, not between 10:00 and 15:30 UTC, never while `mylo-daily.service` is active; it waits otherwise. After the run, `R4_GOLD=r7end code/r4.py gold` is computed again and compared with `gold_r7.json`; a difference is reported.
- **Grading unchanged:** `R4_GOLD=r7 R4_TAG=r7 code/r4.py grade` (and `--first-attempt`), `… code/r4.py partial`, `code/r5_counts.py r7 r5 r5g r6g`. Demo threads are deleted after the run (`code/cleanup.py`).
- **Claims, on their own bars, beside (never pooled with) the earlier rows on the same model:** C-043, C-044, C-045, C-046, C-056, read as Amendment 8 registers them; lists beside `r5`'s 24/27 and `r6g`'s 24/27; `l07`, `l08`, `l09` by question. Reported whatever it shows.
- Run fourth in `EXP-2026-11-019/code/drive_qwen_20261118.sh`.
