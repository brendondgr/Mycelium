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

None. Two changes were made before the measured run and are recorded in
`ISSUES.md`: the sandbox check prints one line, and the harness counts gate
refusals on real calls only.
