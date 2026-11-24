# EXP-2026-11-028 — Protocol

Written 2026-11-24, before any measured turn. Later changes are dated
amendments at the end.

## Question

On questions whose answers are stored facts, does Mylo answer as accurately
with the permission gate as with the gate off and the access policy in the
system prompt?

EXP-2026-11-018 compared Mylo with a single search-and-generate call and with
a corpus-only agent. It never ran with the gate off, so the record has no
code-against-prompt comparison on that task.

## Hypothesis

Registered as claim **C-060** in `CLAIMS.md` before the run: over the
answerable questions, the paired 95% interval of the difference in full
credit (code minus prompt) includes zero or lies above it. The asker is the
demo lab's PI in the web app, who is allowed nearly everything, so the gate
should rarely act and the two arms should score about the same.

Exploratory, no prior: the difference by question kind, and on the
unanswerable questions.

## Safety rule

The prompt arm makes every function return everything in the database it is
connected to, and its policy text lists every project with its members. It is
never connected to the live database. Both arms run on a sandbox database
that holds only the fictional demo lab and public corpus records, and no
model turn is sent until `code/check_sandbox.py` prints zero for every count
(its output is committed in `logs/check_sandbox.json`). `code/run_arms.py`
repeats the check at its start and refuses to go on otherwise.

## Setup

- **Sandbox:** `mycelium_sandbox_exp028`, built once by
  `code/build_sandbox.sh`: a fresh database, migrated by the frozen product
  code, then filled by allow-list from the live database. Copied whole: the
  public corpus (`content_contentitem`, its deadlines, comprehension rows and
  requirement slots). Copied for the demo world only (accounts at
  `@showcase.mycelium.invalid`, the demo lab and department, the lab's two
  projects): accounts, profiles, memberships, projects, the demo world row,
  rankings (`content_relevancescore`), project profiles, daily reports, saved
  items, reminders, shares, and the knowledge edges of the demo people with
  only the concepts those edges point at. Every other table stays as
  `migrate` left it. Primary keys are kept, because the frozen questions name
  corpus items by id. The live database is only read.
  - This is neither of the two routes the plan named. `demo build` on a fresh
    database would give new primary keys and new, model-made rankings, so the
    frozen questions would no longer point at the same rows; copying the live
    database and deleting from it removes by deny-list. Copying only named
    rows keeps the rankings and cannot carry an unnamed table across.
  - The sandbox freezes the corpus and rankings as they stood in the live
    database at the copy (2026-11-24). The nightly run does not touch it.
- **Product code:** frozen at `a99e1a01`, the code of the last
  answer-accuracy runs (`git archive a99e1a01 tools web/backend`, mounted
  read-only).
- **Arms**, same model, same sandbox, same questions:
  - `code`: Mylo as shipped, EXP-2026-11-018's arm (a)
    (`mylo_turn.run_question`, unchanged).
  - `prompt`: the same after EXP-2026-11-011's `run_v2.bypass_gate()`:
    `permissions.decide`, `within_audience`, `_project_may_surface`, eight
    functions of `apps.research.visibility` and `prompt.build` are replaced
    in the harness process, and the policy text is appended to the system
    prompt. The bypass patches the whole process, so the arms are two
    processes run side by side.
- **Asker:** the demo lab's PI in the web app, lab scope, audience `person`,
  a fresh thread per job (`demo_visitor="EXP-2026-11-028"`), as in the source
  experiment.
- **Model:** the relay's `default-model`, operator-stated Gemma 4 31B
  (2026-11-24), at the instance default temperature 0.2. Relay listing and
  self-report recorded at the start and end.
- **Fixed:** `AGENT_PARALLEL_CALLS=0`; 30 threads per arm (60 in flight, as
  the source experiment's last runs); every other setting as in the frozen
  code. `KNOWLEDGE_PROJECT_ON_SAVE`, `KNOWLEDGE_FACET_ON_IMPORT` and
  `AMBIENT_ENABLED` are forced off by the sandbox bootstrap, so nothing a
  turn saves queues work for the live worker.
- **Postgres:** 62 connections; started only after EXP-2026-11-027's run has
  finished and connections in use plus 62 stay under 95.

## Data

The 60 frozen questions of `EXP-2026-11-018/code/questions.json` (ten per
kind: field, list, project, people, join, unanswerable), 3 repetitions per
arm. Gold is computed once from the sandbox by EXP-2026-11-018's
`r4.py gold` (tag `s28`), which keeps the frozen questions and drops any
whose answer set is now empty or too large; the jobs are the kept questions
(at most 360). Gold and answers are computed on the same UTC day, since some
questions depend on today's date. All people are the demo's fictional
members; items are real public corpus records. No human judgment is made.

## Metrics

EXP-2026-11-018's `r4.py grade` and `partial`, unchanged, on the two arms'
rows together (tag `s28`); then `code/analyse.py`:

1. **Primary:** full credit over answerable questions, per arm, primary
   grading (secondary beside it), and the paired difference code minus prompt
   over questions (per-question mean of the three repetitions), with a
   bootstrap 95% interval over questions (10,000 resamples, seed 20261115).
2. The same difference by question kind, and the rate at which each arm
   states a fact on the unanswerable questions (exploratory).
3. Failed jobs per arm (exception, deadline, no final text), first attempts
   and after the one retry.
4. Checks on the manipulation: jobs whose system prompt carried the policy
   text (expected: every prompt-arm job, no code-arm job), and function calls
   the gate did not allow, per arm (in the prompt arm these are counted and
   then allowed).

## Baselines

The `code` arm is the baseline for the `prompt` arm. The earlier
answer-accuracy numbers on the live database (EXP-2026-11-018) are a
different day's corpus and rankings and are not compared number for number.

## Procedure

```bash
REPO=/home/bdg20b/Projects/Mycelium
RUN=$HOME/Projects/Mycelium-runs/answers-20261124
E=docs/research/experiments/EXP-2026-11-028-agent-answers-gold-prompt-arm
mkdir -p $RUN/snap-a99e1a01 $RUN/logs && git archive a99e1a01 tools web/backend | tar -x -C $RUN/snap-a99e1a01
mkdir -p $RUN/snap-a99e1a01/web/backend/media
bash $E/code/build_sandbox.sh                       # once
mkdir -p $RUN/stage/docs && cp -a docs/research $RUN/stage/docs/research   # after the registration commit
cp $E/code/driver.sh $RUN/
MODE=check bash $RUN/driver.sh                      # sandbox check, gold (tag s28)
MODE=smoke bash $RUN/driver.sh                      # three jobs per arm, kept, not counted
setsid nohup bash $RUN/driver.sh > $RUN/driver.out 2>&1 < /dev/null &
# afterwards, from the repository root
bash $E/code/collect.sh
python3 $E/code/analyse.py
```

**Smoke check.** Three jobs per arm (tag `smoke`), kept and not counted. In
the prompt arm, confirm that the system prompt ends with the policy text
(`policy_in_prompt`, `system_tail`) and look for a call the gate would not
have allowed. If the bypass does not take effect at `a99e1a01`, stop and
record it; product code is not changed inside the run.

## What would falsify this

The interval of the difference lying below zero: Mylo answers stored-fact
questions worse with the gate than without it.

## What this will not show

The asker is entitled to nearly everything, so this measures whether the
gate costs accuracy when access is allowed, not accuracy for an asker who may
see only part of the answer. The sandbox holds one lab: collaborator search
beyond the lab finds nobody there, unlike on the live database. One model.
