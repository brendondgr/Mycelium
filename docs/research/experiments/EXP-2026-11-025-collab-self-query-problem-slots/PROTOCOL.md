# EXP-2026-11-025 — Protocol

Written 2026-11-19 at about 19:12Z, after the change was committed (`77166b9e`)
and before any search for this experiment.

## Question

After EXP-2026-11-024's fix, 3 of 14 faculty still saw nobody: each had 1–2
people shortlisted, all dropped by the rerank (Q-102). If the typed-text prompt
gives one `problem` slot per topic listed instead of at most one, how many of
the 14 get at least one suggestion?

## The change under test

`77166b9e`, `web/backend/apps/collab/slots.py`, typed-text prompt only: "problem
— … One slot for each one they list" in place of "At most one, first". Only
covered `problem` slots feed the in-field lane, which is the only lane a
question about one's own research reaches (Q-100). The funding-call prompt, the
validator, the lanes and the rerank are unchanged. Options (a) show the people
the rerank dropped and (b) say why the result is empty were not built: both
would tell the seeker that someone open to collaboration matched, which the
product deliberately never says (`search-panel.tsx`, `Results`).

## Hypothesis

- **H1.** `multi` reads more `problem` slots per seeker than `prev`.
- **H2.** `multi` shows at least one suggestion to at least as many seekers as
  `prev` and longer in-field shortlists. No number predicted. F09 is expected
  to stay at zero: nobody else in the department works in that field
  (EXP-2026-11-023's rater).

## Setup

- **Arms**, same copy, back to back, same model:
  - `prev` — code frozen at `2cc179d9` (EXP-2026-11-024's `after`), run again
    so that both arms come from the same time and model draw;
  - `multi` — code frozen at `77166b9e`.
- **Database:** `mycelium_sandbox_fsusc24`, EXP-2026-11-024's copy as prepared
  there (papers imported and read 2026-11-19 18:48–19:04Z). Nothing is
  re-imported. Each arm first deletes the 14 seekers' search logs and
  appearances in the copy (as in 024).
- **Harness:** `code/run025.py`, which reuses EXP-2026-11-024's `run024.py`
  (and through it 023's `run023.py`) unchanged, redirecting public logs to this
  folder and private outputs to `<private>/exp025/`.
- **Model:** relay `default-model`, at most 4 requests in flight; identity
  recorded before and after.

## Data

EXP-2026-11-024's: the same 14 faculty (F01–F14), the same 14 query texts, the
same copy. No judgments.

## Metrics

Per arm, n = 14 seekers, one run:

- **Primary:** seekers shown at least one suggestion.
- `problem` slots read per seeker (total and per seeker); in-field shortlist
  size; seekers whose whole shortlist was dropped by the rerank; shown in
  total and per lane; distinct people shown.
- Exploratory: shown pairs that were rated in EXP-2026-11-023, and how.

## Baselines

`prev` on the same copy at the same time; EXP-2026-11-024's `after` (11 of 14)
beside it.

## Procedure

```bash
D=docs/research/experiments/EXP-2026-11-025-collab-self-query-problem-slots/code/drive.sh
FROZEN=<2cc179d9> $D identity
FROZEN=<2cc179d9> $D search --arm prev
FROZEN=<77166b9e> $D search --arm multi
FROZEN=<77166b9e> $D identity
python3 docs/research/experiments/EXP-2026-11-025-collab-self-query-problem-slots/code/analyse.py
```

## What would falsify this

H1 fails if `multi` does not read more `problem` slots than `prev`. The change
is read as not helping if `multi` shows suggestions to fewer seekers than
`prev`.
