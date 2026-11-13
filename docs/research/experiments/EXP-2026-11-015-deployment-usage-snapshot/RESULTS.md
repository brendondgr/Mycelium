# EXP-2026-11-015 — Results

Counts as of 2026-11-13 04:55 UTC (2026-11-12 23:55 EST), read from
`data/metrics.json`. One read-only pass, counts only.

## 1. Headline

**Usage is small.** The instance has 11 real accounts (6 with a proved email
address, 1 staff) in 1 lab with real members; **2 people** did anything in
the last 30 days (logged in, messaged Mylo, gave feed feedback or saved an
opportunity), the same 2 in the last 7 days. The public demo, open since
2026-11-10 21:12 UTC, has taken **19 questions from 6 visitor cookies** (3
distinct hashed addresses). The nightly run wrote daily briefings on 28 of
the last 30 days. The corpus holds 184,195 items.

## 2. Results table

| Measure | Count |
|---|---:|
| Real accounts (active / email proved / staff) | 11 (11 / 6 / 1) |
| Fictional demo accounts (excluded above) | 6 |
| Labs / departments / labs with a real member | 2 / 2 / 1 |
| People active, last 7 days / last 30 days | 2 / 2 |
| … of whom logged in to the web app, 7 / 30 days | 1 / 1 |
| Mylo threads created in the last 30 days: Discord / web / demo | 2 / 1 / 3 |
| Mylo turns (user messages), last 30 days: Discord / web / demo | 23 / 1 / 13 |
| Demo questions since opening / visitor cookies / hashed addresses | 19 / 6 / 3 |
| Days with daily briefings written, last 30 days | 28 |
| Daily briefings written, last 30 days | 235 |
| Run-analytics reports in `data/analytics/`, last 30 days | 27 |
| Corpus: papers / grants / conferences / fellowships / total | 179,285 / 1,397 / 2,664 / 849 / 184,195 |

## 3. Figures

None.

## 4. Interpretation

- The deployment is a single-lab pilot. Every per-person number in the system
  paper about live use rests on two active people, and should be written that
  way, not as a percentage.
- Demo threads are deleted after 24 hours, so "threads created in the last 30
  days" under-counts the demo; `DemoQuestion` (19) is the demo's real count.
- Nightly reliability is the strongest usage number: briefings on 28 of 30
  days. "A run happened" is not "a report was read" (one linked Discord
  identity receives the nightly reports).

## 5. Threats to validity

- "Active" is defined by four signals (login, Mylo message, feed feedback,
  saved opportunity). Reading a Discord post or an emailed briefing leaves no
  trace, so passive readers are not counted.
- Threads created by this session's experiments (`demo_visitor` starting
  `EXP-`) are excluded; the evaluation's demo-world threads would otherwise
  dominate the demo count.
- Counts were taken while the nightly run was in progress; a briefing written
  later that night is not included.

## AMENDMENTS

None.
