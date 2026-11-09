# EXP-2026-11-008 — Results

## 1. Headline

No result. On 2026-11-09 the harness passed a dry run (seeding, threads,
graders, writing all work), and the real run stopped at its preflight call:
the model endpoint answered 502 (the relay's upstream was down).

## 2. Results table

<!-- BEGIN GENERATED TABLE -->
<!-- END GENERATED TABLE -->

No rows: no model answered. The dry run's numbers (`logs/dry_run.json`) come
from a stub that answers "I can't tell." to everything; they check the
harness and are **not** results.

## 3. Figures

None.

## 4. Interpretation

C-031 and C-032 stay **unsupported** as claims about the model's behaviour.
What the code guarantees independently of the model is covered by the test
suite, not by this experiment: the gate's permission matrix and its golden
per-persona catalog, object-argument checks, audience filtering, and recall
isolation between people (`tools/agent/tests/`).

## 5. Threats to validity

For the rerun: planted truth written by the same agent that wrote the code;
string graders reward wording overlap; one seeded world, one model.

## 6. What surprised us

Nothing yet.

## 7. Follow-ups

Rerun when the endpoint is up; then the equal-budget comparison and the
human-judged slice described in the protocol.
