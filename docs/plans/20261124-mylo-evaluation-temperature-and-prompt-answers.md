# Mylo evaluation — what still has to be run

**Status (2026-11-24):** plan only. Nothing here has been registered or run.
Delete this file once the experiment is in `docs/research/experiments/` and
the outcome is in `docs/changelog.md`.

One question the research record cannot answer yet:

**Answer accuracy with the rules in the prompt.** The answer-accuracy test
(EXP-2026-11-018) compares Mylo with a single search-and-generate call and
with a corpus-only agent. It never ran with the gate off and the policy in
the prompt, so the record has no code-against-prompt comparison on that
task. Experiment B answers it and needs a sandbox database and one new
wrapper script.

**Dropped on 2026-11-24: the access test at three temperatures** (it was
Experiment A of this plan). Every Mylo evaluation ran at the instance
default, `LLM_TEMPERATURE=0.2`, and no run used another value. The maintainer
decided not to run it; nothing was registered or measured. The record
therefore does not show whether "no leak with the rules in code, leaks with
the rules in the prompt" depends on temperature, and any text that reports
those results should state the temperature they were measured at.

## What is already established (checked 2026-11-24)

| Fact | Source |
|---|---|
| The default temperature is 0.2 and the agent passes none of its own, so the environment variable decides it, at today's code and at `44100c04` | `web/backend/config/settings.py` (`LLM_TEMPERATURE`), `git grep -i temperature 44100c04 -- tools/agent` (no hit) |
| The product sends no sampling seed | `web/backend/apps/core/llmkit/params.py` (`seed=None`, set nowhere) |
| EXP-2026-11-018 and -019 did not record the temperature (`temperature: null`, "instance default") | their `manifest.yaml` |
| The access test can be replayed on frozen code with one command per seed and arm | `EXP-2026-11-022/code/replay.py`, wrapped by `EXP-2026-11-026/code/ink_replay.py` so the `scope-narrowed` rule (Q-090) can be graded |
| The prompt arm removes the gate by patching `permissions.decide`, `permissions.within_audience`, `permissions._project_may_surface`, eight functions of `apps.research.visibility` and `prompt.build` in the harness process | `EXP-2026-11-011/code/run_v2.py` (`bypass_gate`, `policy_text`) |
| Every patched name still exists at `a99e1a01`, the code of the last answer-accuracy runs. The bypass has **not** been run at that commit | `git show a99e1a01:tools/agent/permissions.py`, `…:web/backend/apps/research/visibility.py`, `…:tools/agent/prompt.py` |
| The answer-accuracy test reads the **live** database (the public demo lab) | `EXP-2026-11-018/PROTOCOL.md` (Setup), `EXP-2026-11-026/PROTOCOL.md` (Isolation) |
| The public demo lab can be built from `world.yaml` by a management command | `web/backend/apps/demo/` (`manage.py demo build`) |

## Where it runs, and the rules that carry over

- The host that runs the stack and holds the staging folders of the earlier
  runs (`sc-zeus` in `EXP-2026-11-026/env/hardware.md`). Paths below use
  `$REPO` for the checkout there.
- The model is whatever the relay serves as `default-model`. Before each
  experiment, record the relay listing and the model's self-report
  (`EXP-2026-11-021/code/check.py --record-model`), and do not start unless
  the self-report names the model the operator states. The model, its
  quantisation and its GPU go into `env/hardware.md` as the operator states
  them.
- Product code is mounted read-only from `git archive <commit>`; the research
  record is mounted from a staged copy; `collect` copies results back.
  A frozen snapshot has no `web/backend/media` mount point: create it
  (EXP-2026-11-026 Amendment 1).
- Postgres allows 100 connections, shared with the live app. One part at a
  time, and start a part only when connections in use plus its threads stay
  under 95 (EXP-2026-11-026 Amendment 2, `wait_db_room` in its `driver.sh`).
- `AGENT_PARALLEL_CALLS=0`, as in every source run.
- Run `EXP-2026-11-026/code/watchdog.sh` beside the driver. A stopped piece is
  rerun in full and its partial rows are set aside ungraded.
- `PROTOCOL.md` and the claim rows are committed before the first measured
  turn. Later changes are dated amendments. Failed and aborted runs are kept.

## Experiment B — answer accuracy, rules in code against rules in the prompt

Scaffold: `make new-experiment SLUG=agent-answers-gold-prompt-arm`.

**Question.** On questions whose answers are stored facts, does Mylo answer
as accurately with the gate as with the gate off and the policy in the
prompt?

**Safety rule, before anything else.** The prompt arm makes every function
return everything in the database it is connected to, and its policy text
lists every project with its members. It must **never** be connected to the
live database: a real person's project could reach the model and the logs of
a public record. Experiment B runs both arms on a sandbox database that holds
only the fictional demo lab and public corpus records.

**Step B0 — the sandbox.** Database `mycelium_sandbox_exp<NNN>`.

- Preferred route: a fresh database (`migrate`), the corpus tables copied
  from the live database (public records only), then `manage.py demo build`,
  which builds the lab from `world.yaml` and ranks it once. Checked
  2026-11-24 in `apps/demo/management/commands/demo.py`: the ranking step
  (`_rank`, a refit of each person, the lab and each project) calls the
  model for each target's top items; `demo build --no-rank` builds without
  it. Still **not** checked: which tables the build and the refit read
  (`apps/demo/seed.py`), and whether the 60 questions need the ranked feeds
  to be present.
- Fallback: a copy of the live database with every non-demo account, lab,
  department, project, thread, observation and integration row deleted.
- Either way a script, `code/check_sandbox.py`, must print zero for each of
  these before any model turn, and its output is committed:
  accounts outside `apps.demo.world.DOMAIN`; labs and departments other than
  the demo's; projects outside the demo lab; chat threads; ambient
  observations; integration tokens and Discord links.

**Arms and size.** Same model, same sandbox, same questions, interleaved:

- `code`: Mylo as shipped (EXP-2026-11-018's arm (a)).
- `prompt`: arm (a) after `run_v2.bypass_gate()`.

The 60 questions of `EXP-2026-11-018/code/questions.json`, 3 repetitions,
about 354 jobs once the gold builder drops any question whose answer set is
too large. Product code `a99e1a01`. The asker is the demo lab's PI in the
web app, audience `person`, as in the source experiment.

**New code.**

- `code/run_arms.py`: imports `EXP-2026-11-018/code/run.py` and
  `EXP-2026-11-011/code/run_v2.py`; `--arm code|prompt`. It refuses to start
  unless the database name begins `mycelium_sandbox_` and the sandbox check
  passes. The bypass patches the whole process, so the two arms run as two
  processes side by side, not as threads of one.
- Gold and grading are EXP-2026-11-018's `r4.py gold`, `grade` and `partial`,
  unchanged, pointed at the sandbox with their own tag. Gold is computed once
  from the sandbox; it does not change overnight, so the source experiment's
  time window does not apply.

**Smoke check.** Three jobs per arm, kept and not counted. In the prompt arm,
confirm from the stored thread that the system prompt ends with the policy
text and that a call the gate would deny was allowed. If the bypass does not
take effect at `a99e1a01`, stop and record it; do not change product code
inside the run.

**Hypotheses, to register as claims.**

- Expectation: the two arms score about the same, because the PI in the web
  app is allowed nearly everything, so the gate rarely acts. Registered as:
  the paired 95% interval of the difference in full credit (code minus
  prompt) over answerable questions includes zero or lies above it.
- Exploratory: the difference by question kind, and on the unanswerable
  questions.

**Metrics.** Full credit by question kind and arm, primary grading and
secondary beside it, as in the source experiment; the paired bootstrap over
questions for the difference (10,000 resamples, seed 20261115); failed jobs
and function-call failures per arm (the prompt arm of EXP-2026-11-016 had
204 failed calls of 1,378).

**What would falsify the expectation.** The interval lying below zero: Mylo
answers stored-fact questions worse with the gate than without it.

**What the result will not show.** The asker here is entitled to nearly
everything. It measures whether the gate costs accuracy when access is
allowed, not accuracy for an asker who may see part of the answer.

**Time.** On Inkling 2 Mini the source experiment's 594 jobs took 64 minutes
at 60 in flight. Estimate: under an hour per model, after the sandbox exists.
The sandbox and the wrapper are the larger part: half a day.

## Order

1. Preflight: relay listing, self-report, operator's statement of the model
   (2026-11-24: `default-model` is Gemma 4 31B, `default-model-2` is
   Qwen 3.8 27B; both self-reports matched).
2. Build and check the sandbox. Register B, commit, smoke, run, analyse,
   record, validate, commit.
3. A second model, if wanted: repeat B as a new tag of the same experiment,
   registered as an amendment before it starts.
4. Delete this plan and add the changelog entry.

## Decisions for the maintainer

- Whether a second model follows the first.
- Whether the sandbox may be built from a copy of the live database if the
  preferred route does not work.
