# EXP-2026-11-026 — Protocol

Registered 2026-11-21, before any measured turn on this model (one identity
request only: "I am Inkling, developed by Thinking Machines Lab").

## Question

Do the demo paper's Mylo results, measured on Gemma 4 31B and Qwen 3.8 27B,
hold on Inkling 2 Mini, a mixture-of-experts model with about 3B active
parameters of 26B, quantised to NVFP4 — the kind of model that runs on small
local hardware?

## Hypothesis

- **Rules in code:** 0 leaks in the access probes and in collaborator search,
  as on both earlier models. The gate is code; the model cannot change what it
  is handed. A leak in the code arm would be a defect, not a model property.
- **Rules in the prompt:** exploratory — no prior on the rate; we expect it to
  be above zero, as on both earlier models.
- **Usefulness (answers, controls), memory, latency:** exploratory — no prior.
  A smaller active model may choose functions worse (lower full credit) and be
  faster per turn.

## Setup

- **Model:** relay endpoint `default-model` on `llm-tunnel:9090`. Operator
  statement (2026-11-21): *Inkling 2 Mini*, 26B total / 3B active parameters,
  mixture of experts, NVFP4, rated by the operator for 128 requests in flight.
  The relay lists `upstream_model: "Inkling 2 Mini"`. `EVAL_MODEL_NAME` =
  `Inkling 2 Mini (26B-A3B, NVFP4)`. The relay listing and self-report are
  recorded at the start and end of every part (`record_model`) and before each
  part (`logs/preflight.jsonl`); a part does not start unless the self-report
  names Inkling or Thinking Machines.
- **System:** each part runs the harness that produced the paper's numbers,
  unchanged, on the product code frozen at the commit the earlier models were
  measured on (`git archive <commit> tools web/backend`, mounted read-only into
  a one-off backend container):

| Part | Source experiment (paper section) | Harness, tag | Code | In flight |
|---|---|---|---|---|
| 1 | EXP-2026-11-021 model check (App. C, Table 4) | `check.py`, tag `ink` | `640d7fe0` ("all fixes" rows) | 8 |
| 2 | EXP-2026-11-010 latency (§4.5) | `run_a6.py`, tags `inkidle` (3 reps, one at a time), `inkp8` (8 processes) | `a99e1a01` | 1, then 8 |
| 3 | EXP-2026-11-016 access probes, code vs prompt (§4.1, §4.3, Table 2) | EXP-2026-11-022 `replay.py` (round two's harness and world, imported unchanged, plus a raw log of every model call) through `code/ink_replay.py`, which also keeps the `scope-narrowed` flow's first reply so Q-090's rule can be applied, label `ink`, seeds 101/202/303 × gate/prompt_only × 3 reps | `44100c04` (round two) | 6 × 8 |
| 4 | EXP-2026-11-018 answers vs stored facts, 3 arms (§4.4, Table 1) | `r4.py` gold/grade/partial + `drive_r4.sh`, gold and tag `ink` | `a99e1a01` (Qwen's r7) | 60 |
| 5 | EXP-2026-11-019 collaborator scenarios, gate vs baseline (§4.2, Table 3) | `run019_q.py`, tag `maini`, copy `mycelium_sandbox_exp019maini` | `a99e1a01` (Qwen's mainq) | 60 |
| 6 | EXP-2026-11-017 memory lifecycle (§4.5) | `code/lifecycle_ink.py` (EXP-2026-11-017's `lifecycle_q.py` with the database renamed `…_ink`), tags `ink_a`–`ink_e` | `a99e1a01` (Qwen's A3) | 5 × 12 |
| 7 | EXP-2026-11-019 S1/S2/S10 after the two S1 fixes (§4.3) | `drive_r4.sh`, tag `r6i` | `a99e1a01` (Qwen's r6q) | 32 |

- **Why the earlier models' commits, not today's:** the comparison is the
  model, with the product held fixed. Gemma's and Qwen's paper numbers come
  from these commits (Gemma's EXP-2026-11-017/-018/-019 rows are from the same
  day's code, a few fixes earlier; recorded in their own experiments).
- **Isolation:** every harness writes into its own experiment folder. The
  whole research record is copied to a staging folder
  (`Mycelium-runs/inkling-20261121/stage/docs/research`) and containers mount
  that copy; the repository's record is not written by any run.
  `code/collect.sh` copies the files the runs created back into this
  experiment's `data/raw/<source experiment>/`. Each part has its own
  databases (`…x022_ink_*`, `…exp019maini`, `…exp019r6i{rep,fresh}`,
  `…lifecycle_ink`; part 1 recreates `…check_101_instance`, as every model
  check row does). Parts 1, 2, 4 read the live demo lab; part 4's cleanup
  deletes its demo threads, as before.
- **Fixed:** temperature and every product setting as in the frozen code;
  `AGENT_PARALLEL_CALLS=0` where the source run set it (parts 1, 3–7).

## Data

All people, labs, projects and secrets are invented (the seeded worlds of
EXP-2026-11-016 and -017, the collaboration sandbox of EXP-2026-11-019, the
demo lab of EXP-2026-11-018/-021). Part 4's gold is recomputed from the
database at the start of its run and again at the end (it changes nightly).
No human judgment is made in this experiment; every grade is the source
experiment's code grader. The paper's "real researchers" test
(EXP-2026-11-023 to -025, a copy of a real department) is **not** repeated
here: its headline is a human rating that cannot be redone, and its files
involve real people.

## Metrics

Each part's registered metrics, computed by the source experiment's own
analysis script on this run's tag, unchanged:

1. Model check: answered / 31, leaks / 5 probes, controls / 6, correct / 12.
2. Latency: median and worst seconds per turn by group (one lookup, a few,
   compound), idle and with 8 at once; model calls and tokens.
3. Access probes (**primary**): replies that leaked over replies received, per
   arm, with Q-090's rule for `scope-narrowed` (EXP-2026-11-016
   `regrade_q090.py`'s logic: a secret counts only when absent from the first
   turn); turns with no reply are reported and left out of the rate; controls
   (entitled askers who got their answer).
4. Answers: full credit by question kind and arm (Mylo, single call,
   corpus-only), lists presented as complete when partial.
5. Collaborators (**primary**): runs that named a must-not-name person over
   runs with a reply, gate vs baseline, per scenario; S1/S2 named rates.
6. Lifecycle: what remained after each deletion, member isolation, opt-out,
   exclusion.
7. S1/S2/S10 after the fixes: named rates per cell.

`code/analyse.py` gathers the tagged outputs into `data/metrics.json` and a
three-model table beside the Gemma and Qwen numbers the paper reports, read
from those experiments' own metric files.

## Baselines

Gemma 4 31B and Qwen 3.8 27B on the same harnesses (the paper's numbers), and
within each part its own baseline arm (prompt arm, prose directory, single call,
corpus-only).

## Procedure

```bash
RUN=/home/bdg20b/Projects/Mycelium-runs/inkling-20261121
for c in 44100c04 640d7fe0 a99e1a01; do mkdir -p $RUN/snap-$c; git archive $c tools web/backend | tar -x -C $RUN/snap-$c; done
mkdir -p $RUN/stage/docs $RUN/stage/web/backend && cp -a docs/research $RUN/stage/docs/research
ln -s $PWD/web/backend/media $RUN/stage/web/backend/media
cp docs/research/experiments/EXP-2026-11-026-inkling-2-mini-rerun/code/driver.sh $RUN/driver.sh
setsid nohup bash $RUN/driver.sh > $RUN/driver.out 2>&1 < /dev/null &
# afterwards
bash docs/research/experiments/EXP-2026-11-026-inkling-2-mini-rerun/code/collect.sh
python3 docs/research/experiments/EXP-2026-11-026-inkling-2-mini-rerun/code/analyse.py
```

Order (driver `ITEMS="1 2 34 56 7"`): part 1, then part 2 alone (latency needs
an otherwise idle server; the nightly does not run before 12:00 UTC), then
parts 4 and 3 together (108 in flight), then 5 and 6 together (120), then 7.
Part 4 starts only in a window clear of 22:00–24:00 and 10:00–15:30 UTC, so its
gold and run fall on one UTC day. Deviation from the Qwen run: EXP-2026-11-019's
no-model dry runs before part 5 are skipped (they check the harness, which is
unchanged since).

## What would falsify this

- Any leak in a code-arm reply (parts 1, 3, 5, 7): the claim "0 leaks with the
  rules in code" would not hold on this model, and the leak is a defect to fix.
- Rules-in-the-prompt leak rates at or near 0 on this model would mean the
  code/prompt gap the paper reports is model-dependent.
- Full credit far below the earlier models' 88–90% would mean Mylo is not yet
  usable on a model this small, whatever its access rules.

## Amendment 1 (2026-11-21 17:40 UTC, after part 1, before any part-3 turn)

Part 1 ran (17:35–17:39 UTC). Before part 3 started it was found that
`replay.py`'s rows do not keep the `scope-narrowed` flow's first reply, which
the paper's Q-090 rule needs; `code/ink_replay.py` (a wrapper, no grading
change) now keeps it, and the driver was stopped after part 1 and restarted
with `ITEMS="2 34 56 7"`. A first start at 17:34 UTC failed at its first
container (the frozen snapshots had no `web/backend/media` mount point) before
any model turn; its logs are in `data/raw/run/aborted-1/`.

## Amendment 2 (2026-11-21 18:13 UTC, part 3 stopped after 4 minutes; no part-3 result read for its leak counts)

Parts 3 and 4 started together at 18:07–18:08 UTC. Within four minutes 34 of
67 part-3 turns failed with `FATAL: sorry, too many clients already`: every
harness thread holds a Postgres connection, the instance's Postgres allows
100, and part 4 (60 threads on the live database), part 3 (6 × 8) and the live
app together exceeded it. Part 4's rows had no such error and it was left
running. Part 3 was stopped at 18:12 UTC; its partial files are kept in
`data/raw/run/aborted-2-part3/` and are not counted. The only thing read from
them before stopping was the error count and the share of turns without a
reply; the replies themselves were not graded for the decision.

From here, **one part at a time**, each starting only when the connections in
use plus the part's threads stay under 95 (`wait_db_room` in the driver).
Part 3 is rerun in full (fresh databases, as `replay.py` drops and recreates
them), then parts 5, 6 and 7, from a second driver started with
`ITEMS="3 5 6 7" WAIT_PID=<part 4's process>` so it begins after part 4. The
in-flight figures in the Setup table are unchanged; only parts no longer
overlap.

## Amendment 3 (2026-11-21 21:25 UTC, during part 3; no part-3 grade read)

Part 3's seed-101 code-arm process wrote its last row at 19:17 UTC and then
waited for over two hours on one model request: the process held an open
connection to the relay (`llm-tunnel:9090`) with no reply, its database
connections idle. The other five processes kept running. At 21:24 UTC the
process was stopped and its 16 rows set aside without grading
(`data/raw/run/aborted-3-part3-s101gate/`). Seed 101's code arm is rerun in
full (3 repetitions, fresh database, same command, container
`i-016-101-gate-r2`), beside the other part-3 processes and then part 5; the
connection guard still holds (about 75 in use at most). Only the rerun's rows
are counted for seed 101's code arm.
