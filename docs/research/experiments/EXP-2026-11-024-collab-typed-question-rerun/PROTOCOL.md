# EXP-2026-11-024 — Protocol

Written 2026-11-19 at about 18:43Z, after the fix was committed (`2cc179d9`) and
before the database copy, the imports or any search for this experiment.

## Question

After the slot-reader fix, how many of the 14 faculty of EXP-2026-11-023's
department get at least one suggestion when they type the same question, "Who
in the department should I collaborate with on `<their research areas>`?"
EXP-2026-11-023's product arm gave 7 of 14.

## The fix under test

`2cc179d9` ("Collab: a typed question gets its own slot prompt and a
fallback"), in `web/backend/apps/collab/slots.py` and `matcher.py`:

1. typed text is read with its own prompt ("list the topics, methods, data or
   kinds of partner this person names"), with the same checks as a call (short
   phrases, every slot's words in the text, one repair);
2. if the reader still returns no slots, or the model is unreachable, the text
   after "collaborate with … on" becomes one `problem` slot;
3. if there is still nothing, the search is refused with `no_topic` and a
   sentence for the person, instead of an empty search.

## Hypothesis

Stated before the run, from the code:

- **H1 (mechanical).** After the fix, no seeker's search runs with zero slots:
  every one of the 14 questions contains "collaborate with … on", so step 2
  always applies when step 1 fails. Zero `no_topic` refusals expected.
- **H2.** More seekers get at least one suggestion after the fix than before it
  on the same copy. No number is predicted. The ceiling is near
  EXP-2026-11-023's manual arm (12 of 14 with slots built from the areas
  directly): one seeker there had nobody in their field, and one had every
  shortlisted person dropped by the rerank.

## Setup

- **Arms**, both on the same database copy, same day, same model:
  - `before` — code frozen at `b45c1211` (the commit before the fix; the slot
    reader is the one EXP-2026-11-023 ran, `181ca3c4`, unchanged since);
  - `after` — code frozen at `2cc179d9` (the fix).
  Each frozen with `git archive <commit> tools web/backend`.
- **Database:** `mycelium_sandbox_fsusc24`, a new `pg_dump | pg_restore` copy of
  the live database taken today. EXP-2026-11-023's copy
  (`mycelium_sandbox_fsusc`) has been dropped, so its imports cannot be reused;
  they are redone through the same product path. The sandbox guard refuses any
  other database name.
- **Harness:** `code/run024.py`, which imports EXP-2026-11-023's `run023.py`
  for the roster, the in-process settings, the copy-only stand-in, the import
  path and the rerank capture, and redirects its outputs (this folder's
  `logs/`, private files under `<private>/exp024/`). The in-process changes are
  exactly 023's (PROTOCOL.md there, Setup): stand-in domain resolved to the real
  institution, `COLLAB_SEARCH_ENABLED` on, billing enforcement off, appearance
  cap and daily search limit raised, `WRITEUP_LLM_CONCURRENCY` = 4, four seekers
  searched at a time.
- **Cache:** at the start of each arm, the 14 seekers' search logs and
  appearances are deleted in the copy, so the day's search cache never answers
  one arm with the other's result.
- **Model:** relay endpoint `default-model` (the instance's model, as in 023),
  shared with live use, at most 4 requests in flight. The relay listing and the
  model's self-report are recorded before the prepare step and after the last
  search (`identity`). Temperature as deployed. The model may differ from the
  one 023 ran on (Gemma 4 31B per the maintainer then); that is why the
  comparison that measures the fix is `before` against `after` on the same
  copy, and 023's 7 of 14 is reported beside it, not subtracted from it.
- **Container:** one-off `docker compose run --rm --no-deps` backend container,
  as the host user, `docs/research` and the private directory writable.

## Data

The same 14 faculty (F01–F14) and 10 student stand-ins as EXP-2026-11-023, from
the same private roster (`people.json`, unchanged, outside the repository), the
same anonymous ids, the same opt-in in the copy, the same OpenAlex author
records, imported through the same product path (the 50 most-cited works, as
OpenAlex has them today). The same 14 query texts (`run023.query_text`). No
judgments: nothing in this run is rated.

## Metrics

Per arm, n = 14 seekers, one run:

- **Primary:** seekers shown at least one suggestion (any lane, after the
  rerank) — the number to set beside 023's 7 of 14.
- Seekers whose search ran with zero slots; seekers refused `no_topic`; per
  seeker, where the slots came from (`reader`, `fallback`, `none`).
- Suggestions shown in total and per lane; distinct people shown; shortlisted;
  dropped by the rerank; unexplained searches.
- Exploratory, post hoc in kind but named now: of the `after` arm's shown
  (seeker, candidate) pairs, how many were rated in EXP-2026-11-023 and how
  those were rated. Pairs not on 023's sheet are unrated.

## Baselines

`before` on the same copy (the measure of the fix), and EXP-2026-11-023's
product arm (7 of 14) beside it.

## Procedure

```bash
FROZEN_B=<dir>/b45c1211; FROZEN_A=<dir>/2cc179d9   # each: git archive + COMMIT file
docker compose exec -T postgres sh -c 'createdb -U mycelium mycelium_sandbox_fsusc24 && pg_dump -U mycelium -Fc mycelium | pg_restore -U mycelium -d mycelium_sandbox_fsusc24 --no-owner'
D=docs/research/experiments/EXP-2026-11-024-collab-typed-question-rerun/code/drive.sh
PRIVATE_DIR=<private> FROZEN=$FROZEN_A $D check
PRIVATE_DIR=<private> FROZEN=$FROZEN_A $D identity
PRIVATE_DIR=<private> FROZEN=$FROZEN_A $D prepare
PRIVATE_DIR=<private> FROZEN=$FROZEN_A $D works
PRIVATE_DIR=<private> FROZEN=$FROZEN_B $D search --arm before
PRIVATE_DIR=<private> FROZEN=$FROZEN_A $D search --arm after
PRIVATE_DIR=<private> FROZEN=$FROZEN_A $D identity
python3 docs/research/experiments/EXP-2026-11-024-collab-typed-question-rerun/code/analyse.py
```

One retry per seeker if the rerank is unavailable, as in 023. A failed or
partial arm is kept and reported, not rerun silently.

## What would falsify this

- H1 fails if any `after` seeker's search runs with zero slots or is refused
  `no_topic`: the fallback does not do what it is for.
- The fix is read as not helping if `after` shows suggestions to no more seekers
  than `before` on the same copy.
