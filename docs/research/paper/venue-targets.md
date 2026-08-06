# Venue Targets

Deadlines, page limits, and checklist requirements, tracked from day one rather
than assembled the week before submission. Every field a venue's reproducibility
checklist asks for is already a manifest field, by design.

Distance estimates come from [`../../research-audit.md`](../../research-audit.md)
§6.5 and assume one person working full-time.

## Current readiness

**L1** — a working deployed artifact with one external measurement. Near from a
demo track; far from an applied conference; far from top-tier archival.

| Axis | Score | What moves it |
|---|---|---|
| Claim clarity | 1/4 | `CLAIMS.md` now exists; W3 instrumentation is not started |
| Evaluation rigor | 2/4 | `EXP-2026-08-001` closed the zero; internal judgments (W5) are the next step |
| Baseline coverage | 2/4 | Published BM25 + Qwen3-4B are scored by our own harness |
| Positioning | 1/4 | `RELATED_WORK.md` seeded; the prose (W4) is not written |

## Targets

### Tier 3 — fast feedback (achievable now)

| Venue | Track | Distance | Requirements |
|---|---|---|---|
| ECIR | Demo | **2–4 weeks** | W0 + W1 + W2 done + write-up + video. Short paper, demo video, live system. |
| JCDL | Demo | 2–4 weeks | Same package. |
| CHIIR | Demo | 2–4 weeks | Same package; interaction framing helps. |

W0 (strike the overstated claims) is **done** and had to precede any demo
submission — a reviewer who greps the repository against the README finds the gap
in five minutes.

### Tier 2 — target (after the measurement spine)

| Venue | Track | Distance | Requirements |
|---|---|---|---|
| SCOLIA | Full/short | **10–16 weeks** | The W3→W5→W6 spine. Scholarly-document-processing framing. |
| AI4SciSci | Workshop | 10–16 weeks | Science-of-science framing suits the lab-level angle. |
| TPDL | Full/short | 10–16 weeks | Digital-libraries framing. |
| iConference | Short | 10–16 weeks | — |
| UMAP | LBR | 10–16 weeks | Personalization framing; the multi-interest profile is the hook. |

The spread is dominated by annotator availability for W5, the one item whose
duration is set by other people.

### Tier 1 — reach

**None reachable in 12 months.** Honest estimate: 40–70 weeks, and only via a
method or resource contribution that does not yet exist. The most plausible route
is the group-recommendation framing (Path B), not the current system.

## Shared tasks

| Task | Status | Note |
|---|---|---|
| CLEF LongEval 2026, Task 1 | **Submittable now** | Run files can be produced for TIRA today; only scoring is blocked by withheld qrels. Participation costs little and yields an external, dated, citable result. |

## The contribution, chosen

**Path A — eligibility-constrained fellowship and grant recommendation with
graded ineligibility.** It sits in the emptiest literature (G1: grant
recommenders are "the least studied scholarly recommendation systems"; G2: graded
eligibility exists only in clinical trials), it is not scooped, and the system
already implements the mechanism.

Runner-up: **Path B — group-level scholarly recommendation with item-to-member
routing** (G3, also unscooped). W7 and W8 are alternative *second* papers and
should not both be attempted.

**Not** the paper-feed framing: Scholar Inbox [B1] scoops it and shipped an
800k-rating dataset we do not have.

## Checklists

Venue reproducibility checklists live in [`checklists/`](checklists/) and are
treated as live to-do lists, not submission-week paperwork.
