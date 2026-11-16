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
