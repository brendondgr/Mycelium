# EXP-2026-08-018 — Issues

## 1. This experiment measures invariance, not quality

Deliberately. It cannot say the rerank stage is any good, and nothing in it should
be quoted as if it could. The evidence for shipping the stage at all is
`EXP-2026-08-015` … `-017`, which is a **preference from one reader** — no
interval, not W5, and `Q-033` is the open question.

## 2. The protocol was fixed in the plan, not in this folder

`PROTOCOL.md` was typed after the run, but the gate it records — "flag off ⇒
byte-identical, any difference is a bug in the wiring, not a result" — was
committed in `docs/plans/cross-encoder-rerank.md` at `0c1844f`, before
`apps/content/reranking.py` existed. That plan is deleted when the work ships (the
planner skill treats a plan as a working document, not a record), which is why the
gate is copied here.

`EXP-2026-08-016` recorded a genuine version of this failure. This one is a
bookkeeping seam rather than a retrofit, and the distinction is worth keeping
rather than blurring in either direction.

## 3. `positions_moved` varies by one across processes

100, 101, 100, 100 over four runs. Chased rather than waved away, because this
record has been burned by tie ordering before:

- the cross-encoder is **bitwise identical** across processes (same SHA over the
  score vector, three runs);
- the pgvector pull is identical across processes;
- flag-off and flag-on orders are each identical *within* a process.

The variation is `combine_interests`' set iteration — RESULTS §3, `Q-035`. It is
**not** introduced by the rerank stage; the stage merely made it visible by giving
a reason to run the same fusion twice.

## 4. Cost is one profile on one CPU

Two interests, 200 candidates, no GPU. A 22-interest profile is bounded by
`RERANK_MAX_PAIRS` rather than measured, and the deployment target has CUDA, so
the +2.59 s here is an upper bound on the wrong hardware. Treat it as "the shape
of the cost", not the cost.

## 5. The harness is forced, not defaulted, to keep the flag off

`eval/run.py` now sets `RERANK_ENABLED=false` outright rather than via
`setdefault`. The profile arms call `fuse_interests_pool`, so a stray environment
variable would otherwise change numbers this record treats as historical. An arm
that wants reranking has to be written as an arm.

## 6. Working tree dirty

`code.dirty: true`. The branch `feat/cross-encoder-rerank` carries the stage
itself; this folder records its verification.
