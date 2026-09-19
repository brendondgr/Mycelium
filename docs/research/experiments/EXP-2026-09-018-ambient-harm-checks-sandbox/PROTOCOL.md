# EXP-2026-09-018 — Protocol

Written 2026-09-19. **Deviation, stated up front:** before writing this
protocol, the evaluation command was run once on the sandbox copy to check
that it ran. That look showed 7 person-days over the question cap and zero on
every other check. H1 below is written knowing that, and says so.

## Question

Plan 10's harm checks are the go/no-go gate for the pilot, and each must read
zero. Two questions:
- Does each one read zero on a record the real pipeline produced?
- Does each one catch the single violation it exists for, without firing on
  anything else?

A check that never fires is indistinguishable from one that cannot.

## Hypotheses

- **H1 (the record).** On `mycelium_sandbox_ambeval`, EXP-2026-09-017's end
  state, every check reads zero except `questions_over_the_daily_cap`. Its
  hits must all be person-days on which a harness asked more than the cap on
  purpose: EXP-2026-09-015 raised it to 50, and EXP-2026-09-016's prep
  re-asked questions. Each hit is checked by hand against the harness logs.
- **H2 (detection, pre-registered bar: 11/11 injections across the 10 checks).** Injecting one violation of
  each kind raises exactly its own check by exactly one, and leaves the other
  nine unchanged (0 cross-talk). This is measured one injection at a time,
  each in a transaction that is rolled back.
- **H3 (budget).** Under 10 minutes.

Reported without a bar:
- validation precision on the sandbox's simulated answers, by kind and
  surface (simulated people, so no claim);
- the maintenance numbers.

## Setup

- Database: `mycelium_sandbox_ambeval`, a copy of `mycelium_sandbox_ambrep`.
- `code/run.py` computes the clean report through `apps.ambient.read.evaluation_report`,
  passing the stored lab reports. It then makes each of the ten injections
  inside `transaction.atomic()`, re-runs the checks, and rolls back. The
  injections are the same shapes the unit tests use, but applied to the real
  record: a profile edit with no yes, a state edit with no proposal, a
  confirmation with no answer, a personal row in a lab report, a third
  question on one day, a quotation, an observation older than an opt-out, an
  observation of an unlinked speaker, a declined topic re-asked inside 30
  days, a covered topic asked, and a rule-written observation.

## Procedure

```bash
docker compose exec -T backend sh -c 'cd /app && export DATABASE_URL=${DATABASE_URL%/*}/mycelium_sandbox_ambeval && \
  uv run --project web/backend python web/backend/manage.py shell < docs/research/experiments/EXP-2026-09-018-ambient-harm-checks-sandbox/code/run.py'
```

## What would falsify this

- A non-zero check on the record, other than the cap hits explained by a
  harness.
- Any injection that is missed, counted twice, or moves another check.
