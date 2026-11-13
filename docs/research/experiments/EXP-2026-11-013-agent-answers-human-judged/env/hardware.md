# Hardware and environment

| Field | Value |
|---|---|
| CPU | |
| RAM | |
| GPU | model and count, or "none" — say it explicitly rather than leaving it blank |
| Python | |
| Lockfile | path to the lockfile that pinned this run |
| Container | image digest, or "none — run on the host" |
| Total wall clock | |

## Where the time went

A per-stage breakdown when one stage dominates. Knowing that 90% of a run is one
embedding pass is what tells the next person which knob is worth turning.

## Anything about the hardware that affects the claim

CPU vs GPU, matched or unmatched compute against a baseline, memory limits that
forced a smaller batch size.
