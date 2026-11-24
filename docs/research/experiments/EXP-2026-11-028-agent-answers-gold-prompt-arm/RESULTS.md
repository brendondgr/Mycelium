# EXP-2026-11-028 — Results

**Status: complete** (2026-11-24). Every number below comes from
`tables/summary.md` and `data/metrics.json` (`code/analyse.py`), computed
from EXP-2026-11-018's unchanged grader output and the two arms' rows in
`data/raw/`.

## 1. Headline

On stored-fact questions asked by an entitled person, Mylo scored about the
same with the permission gate as with the gate off and the rules in the
prompt, and never higher. **Answerable questions: 136/144 full credit with
the rules in code, 139/144 with the rules in the prompt; paired difference
−0.021, 95% interval [−0.056, 0.000].** The registered criterion (the
interval includes zero or lies above it) is met only at its edge: the upper
end is exactly zero, and no question went the code arm's way.

## 2. Results table

`tables/summary.md` (generated). Gemma 4 31B, 58 questions × 3 repetitions
per arm, 348 jobs, none failed. Primary and secondary grading gave the same
counts everywhere.

| arm | field | list | project | people | join | answerable | unanswerable: full credit | unanswerable: states a fact |
|---|---|---|---|---|---|---|---|---|
| code | 28/30 | 21/24 | 30/30 | 30/30 | 27/30 | 136/144 = 0.944 [0.875, 1.0] | 15/30 | 6/30 |
| prompt | 30/30 | 21/24 | 30/30 | 30/30 | 28/30 | 139/144 = 0.965 [0.910, 1.0] | 19/30 | 3/30 |

Paired difference in full credit, code minus prompt (per-question mean of
three repetitions; bootstrap over questions, 10,000 resamples, seed
20261115):

| questions | code | prompt | difference | 95% interval | n | questions where code / prompt is higher |
|---|---:|---:|---:|---|---:|---|
| answerable (**primary, C-060**) | 0.944 | 0.965 | −0.021 | [−0.056, 0.000] | 48 | 0 / 2 |
| all, unanswerable included | 0.868 | 0.908 | −0.040 | [−0.086, −0.006] | 58 | 0 / 4 |
| field | 0.933 | 1.000 | −0.067 | [−0.200, 0.000] | 10 | 0 / 1 |
| list | 0.875 | 0.875 | 0.000 | [0.000, 0.000] | 8 | 0 / 0 |
| project | 1.000 | 1.000 | 0.000 | [0.000, 0.000] | 10 | 0 / 0 |
| people | 1.000 | 1.000 | 0.000 | [0.000, 0.000] | 10 | 0 / 0 |
| join | 0.900 | 0.933 | −0.033 | [−0.100, 0.000] | 10 | 0 / 1 |
| unanswerable | 0.500 | 0.633 | −0.133 | [−0.333, 0.000] | 10 | 0 / 2 |

- **The whole gap is four questions.** `f06` (code 1 of 3, prompt 3 of 3),
  `j10` (0 and 1), `u04` (0 and 3), `u07` (0 and 1). The other 54 questions
  scored the same in both arms.
- **Jobs.** 174 per arm, 0 failed first attempts, 0 retries, every turn
  ended idle. Median turn 120 s (code) and 109 s (prompt) with 60 in flight.
- **The manipulation took effect.** The system prompt carried the policy
  text in 174 of 174 prompt-arm jobs and 0 of 174 code-arm jobs.
- **What the gate did.** In the code arm 37 of 494 function calls were
  refused, all with the code `not_visible` at the gate's reference check:
  the model passed a reference such as `#1` that the conversation had not
  yet established. Sandbox threads (smoke jobs included) show 32 on
  `corpus_item`, 3 on `org_lab_members` and 3 on `projects_get`. They fall
  on 13 questions, nearly all of them questions that tag an item; the model
  then searched and asked again, which is why the code arm made more calls
  (494 against 429). In the prompt arm no call was refused; the harness
  counted 10 calls the gate would not have allowed.
  None of these refusals is an access rule turning the asker away from
  something they may not see.
- **Lists.** No list answer presented a partial view as complete in either
  arm (0 of 24 each, EXP-2026-11-018's `partial` measure).
- **Sandbox.** The check printed zero for every kind of non-demo row before
  the first turn and again after the last (`logs/check_sandbox.json`,
  `logs/check_sandbox_end.json`); the only new rows are this experiment's
  354 threads.
- **Time.** 17:41:47 to 17:54:39 UTC.

## 3. Figures

None.

## 4. Interpretation

The expectation was that the gate would rarely act for an asker who may see
nearly everything, so the arms would tie. They nearly do: 54 of 58 questions
are identical, and on answerable questions the arms differ by three jobs of
144. But the difference that exists runs one way. The code arm is never
ahead, and once the unanswerable questions are counted the interval excludes
zero (−0.040, [−0.086, −0.006]).

The registered claim is therefore met on its wording and no more than that.
It would be wrong to report "the gate costs nothing"; the supported
statement is "no measurable cost on answerable questions at this size, with
a small deficit that cannot be ruled out".

Where the gate acted, it was the reference check, not an access rule. That
check cost the code arm an extra search on item-tagged questions. The four
questions that differ are not explained by it alone: `f06` and `j10` had no
refused call in the code arm, and their misses read as wording (a month
given without the stored date). `u04` had one refused call per job, after
which the code arm named the paper while saying its citation count is not
visible; the prompt arm said only that it is not visible.

## 5. Threats to validity

- The asker is entitled to nearly everything. This measures the gate's cost
  when access is allowed, not accuracy for an asker who may see only part of
  the answer.
- One model (Gemma 4 31B, as the operator states it), one day's corpus and
  rankings, 58 questions. With 48 answerable questions an interval of
  [−0.056, 0.000] cannot separate "no cost" from a cost of a few points.
- The sandbox holds one lab. Collaborator search beyond the lab finds nobody
  there, unlike on the live database, and the earlier answer-accuracy
  numbers (EXP-2026-11-018, live database, other days) are not comparable
  number for number.
- The prompt arm lost the gate's reference resolution along with its access
  rules (as in EXP-2026-11-016), so the comparison is gate against no gate,
  not access rules alone.
- Grading is the source experiment's code grader; no person read the
  answers.
- Two questions were dropped by the gold builder on the sandbox (`l02`,
  `l06`: answer sets over its limit).

## 6. What surprised us

That the gate refused 37 calls for an asker who may see everything asked
about, and that every one was a reference the model had not yet earned
rather than a permission. That is a usability cost of the gate that the
access test does not measure (Q-105).

## AMENDMENTS

Two changes were made before the first measured run and are recorded in
`ISSUES.md`: the sandbox check prints one line, and the harness counts gate
refusals on real calls only.

### Amendments 1 and 2 (2026-11-24): Qwen 3.8 27B and Inkling 2 Mini

Registered as PROTOCOL Amendments 1 and 2 before any turn on each model.
Same harness, commit, questions and gold (the gold computed on each model's
sandbox copy equals the first run's). Qwen ran 18:43 to 18:54 UTC on
`default-model-2`; Inkling 19:30 to 19:46 UTC on `default-model`, which the
operator switched from Gemma to Inkling at about 18:49 UTC. Each sandbox
copy printed zero for every kind of non-demo row before its first turn and
after its last. Numbers from `tables/summary.md`; primary and secondary
grading gave the same counts on every model.

Answerable questions, full credit (48 questions × 3 repetitions per arm):

| Model | Rules in code | Rules in the prompt | Difference, code − prompt | 95% interval | Questions where code / prompt is higher |
|---|---:|---:|---:|---|---|
| Gemma 4 31B | 136/144 = 0.944 | 139/144 = 0.965 | −0.021 | [−0.056, 0.000] | 0 / 2 |
| Qwen 3.8 27B | 125/144 = 0.868 | 121/144 = 0.840 | +0.028 | [−0.021, +0.090] | 3 / 2 |
| Inkling 2 Mini | 107/144 = 0.743 | 106/144 = 0.736 | +0.007 | [−0.042, +0.063] | 3 / 3 |

All 58 questions, unanswerable included:

| Model | Rules in code | Rules in the prompt | Difference | 95% interval |
|---|---:|---:|---:|---|
| Gemma 4 31B | 0.868 | 0.908 | −0.040 | [−0.086, −0.006] |
| Qwen 3.8 27B | 0.879 | 0.856 | +0.023 | [−0.017, +0.075] |
| Inkling 2 Mini | 0.759 | 0.753 | +0.006 | [−0.040, +0.052] |

Jobs and the gate:

| Model | Jobs per arm | Failed first attempts (code / prompt) | Failed after one retry | Policy in the system prompt (code / prompt) | Calls refused in the code arm | Median turn, s (code / prompt) |
|---|---:|---|---:|---|---|---|
| Gemma 4 31B | 174 | 0 / 0 | 0 | 0 of 174 / 174 of 174 | 37 of 494 | 120 / 109 |
| Qwen 3.8 27B | 174 | 2 / 2 | 0 | 0 of 176 / 176 of 176 | 18 of 452 | 86 / 81 |
| Inkling 2 Mini | 174 | 0 / 0 | 0 | 0 of 174 / 174 of 174 | 10 of 687 | 136 / 123 |

- **C-060 is met on each of the three models.** The interval of the
  difference includes zero on all three, and on Qwen and Inkling it sits
  around zero, not at its edge.
- **Gemma's small deficit did not repeat.** On Qwen the code arm is ahead by
  about as much as it was behind on Gemma, and on Inkling the arms are level
  (three questions each way). The sign of the difference changes from model
  to model, which is what no real difference looks like at this size. The
  first run's reading stands as written for Gemma alone ("no measurable cost
  on answerable questions, a small deficit not ruled out"); across three
  models there is no sign that the gate costs an entitled asker accuracy.
- **Unanswerable questions.** Only Gemma differed between arms (full credit
  15/30 against 19/30). Qwen scored 28/30 in both arms and Inkling 25/30 in
  both.
- **The gate's refusals** fell with the model's care over references: 37 on
  Gemma, 18 on Qwen, 10 on Inkling, none in any prompt arm. The code arm
  made somewhat more calls on every model (494 against 429, 452 against 430,
  687 against 647) and its median turn was 5 to 13 s longer.
- **Accuracy by model** follows the earlier answer-accuracy record: Gemma
  highest, Inkling lowest, with Inkling's misses in people and join
  questions (16/30 and 13/30 in the code arm).
- **Lists.** EXP-2026-11-018's partial-list measure is in
  `data/raw/EXP-2026-11-018-agent-answers-gold/tables/partial_<tag>.md` for
  each model.

Threats added by these runs: the three models ran at different hours of one
day on servers under different load, so turn times compare loosely; the
Inkling model's quantisation and GPU were not restated; no person read any
answer.
