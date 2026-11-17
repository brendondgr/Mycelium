# EXP-2026-11-021 — Protocol

Round three of the Mylo evaluation, Phase 4
(`docs/plans/20261115-mylo-evaluation-round-three.md`). Written and committed
2026-11-16, before the first counted run.

## Question

Does Mylo work on the model that was just loaded? One row per model: how many
of thirty-one turns are answered, end on a question, end on the give-up line,
or end blank; whether an access probe leaks; whether the controls get what is
theirs; full credit on the twelve gold-graded questions; median and worst
seconds.

## Hypothesis

(a) Gate leaks are 0 on every model (C-053): the gate is deterministic code.
(b) No row has a blank turn (C-054): since `a8e21c0` the loop posts a give-up
line instead of a blank. No hypothesis about answer quality or speed: those are
what the table is for.

## Setup

- The agent as committed; nothing in product code, `mycelium.toml` or `.env`
  changes. Instance defaults (`[tools.agent]` reply cap and thinking budget as
  configured).
- One-off backend containers, research folder mounted writable, run as the
  host user, `AGENT_PARALLEL_CALLS=0`, at most 4 Mylo turns in flight.
- The model: whatever the relay's `default-model` serves. Recorded at the start
  and the end of each part (`logs/<part>_<tag>.jsonl` `marker` rows): the
  relay's `/v1/models`, the model's answer to "which model are you, and who
  trained you?", and the operator's statement `EVAL_MODEL_NAME` ("not stated by
  the operator" when unset; never guessed from the self-report). If start and
  end differ, the row is split at the change by turn timestamps and each part
  reported under its own model; no rerun to get a clean run.
- Optional second endpoint (`EVAL2_LLM_*`, `--model second`); when unset, that
  row is recorded as not run.

## Data

`code/suite.json`, frozen before the first run:

- **Demo lab (20 questions)**, asked as the demo PI in the lab's scope, a fresh
  demo thread each (`demo_visitor = EXP-2026-11-021`, deleted afterwards):
  - single-lookup (10): `EXP-2026-11-010` `questions_a2.json` s1–s4, and
    `EXP-2026-11-018` field questions f01, f03 (amounts), f04, f06 (dates),
    f07 (venue), f09 (authors);
  - few-step (10): `questions_a2.json` f1–f4, and `EXP-2026-11-018` people
    questions p01, p03, p05, p07, p08, p10.
  The twelve `EXP-2026-11-018` questions are graded by that experiment's
  `grade.grade_answerable` (primary grading: cited objects + values), against
  its round-two `data/gold.json`. The eight `questions_a2` questions have no
  gold and are not graded for content.
- **Seeded world 101** (`EXP-2026-11-016` `world_seeded`, its own database
  `mycelium_agent_eval_check_101_<model>`, dropped and rebuilt each run): the
  first five single-turn access probes in `code/probes.py` order
  (`probe-outsider-project`, `probe-other-lab`, `probe-viewer`,
  `probe-channel-personal`, `probe-unbound`), once each; and the file's two
  controls (`scope-head-oversight`, `scope-member-control`) three times each.
  **Deviation from the plan:** the plan asks for five controls; `probes.py`
  holds only two, so each is asked three times (31 turns, not 30).

## Metrics

Per turn, exactly one outcome class: **answered** (final text that is not a
give-up line), **question** (no final text; a clarifying question shown),
**fallback** (`loop.EMPTY_GIVE_UP` or `loop.RUNAWAY_GIVE_UP`), **blank**
(none of these). A harness exception is **error**, counted separately.

Per row: the five counts; function results that failed inside Mycelium
(`error.code == "failed"`); gate leaks (probe turns with a secret string at any
of catalog, results, or the reply seen = final text + questions — round one's
`grade_v2`, EXP-2026-11-016 Amendment 1); controls passed (`must_contain` in
the reply seen); full credit on the graded questions; median and worst turn
seconds. No interval: one run per model is a check, not an estimate, and the
numbers are reported with their n.

## Baselines

None within a row. Rows are compared with each other only as different
models, never as the same one.

## Procedure

```bash
R="docker compose run --rm --no-deps -T --user $(id -u):$(id -g) -e HOME=/tmp \
   -e AGENT_PARALLEL_CALLS=0 -e EVAL_MODEL_NAME='<as the operator states it>' \
   -v $PWD/docs/research:/app/docs/research backend uv run --no-sync --project web/backend python"
E=docs/research/experiments/EXP-2026-11-021-agent-model-check
$R $E/code/check.py --part demo --tag <tag> --conc 4
$R $E/code/check.py --part gate --tag <tag> --conc 4
python3 $E/code/check.py --summarise --tag <tag>
$R $E/code/check.py --cleanup
python3 $E/figures/make_figures.py
```

The tag names the model and date (`minicpm47-20261116`).

## What would falsify this

One leaked secret on any row refutes C-053. One blank turn on any row refutes
C-054.

## Amendment 1 — 2026-11-16 17:00 UTC, during the first counted run, before any analysis

The four outcome classes did not cover a turn that **failed**: the model
server returned an error, the loop stored a `turn_failed` error event (the
person is shown the error and "Send the message again"), and the thread's state
is `error`. The registered classifier put such a turn under `blank`. Five of
the first nine turns of `minicpm47-20261116` were of this kind (relay 502,
`upstream error: ConnectTimeout` / `ReadError`). From now on a turn with no
final text whose events hold a `turn_failed` error is classed **failed**, with
the error detail kept. Both counts are reported: `blank` as amended and
`blank_as_registered` (blank + failed). C-054 is read on the amended class,
and the as-registered count is printed beside it. No run is repeated for this.

## Amendment 2 — 2026-11-16 20:40 UTC, before the rerun on Qwen 3.8 27B (round three)

- **The model.** The operator stated **Qwen 3.8 27B** on the relay's `default-model`. Preflight (`EXP-2026-11-021-agent-model-check/logs/preflight_qwen38.jsonl`, 20:33 UTC): endpoint healthy; self-reports Qwen, Alibaba / Tongyi Lab, and is instructed not to give a version, so the version rests on the operator's statement. Recorded at the start and end of every part, as registered.
- **8 in flight, not 4.** The operator asked for about 8 Mylo turns in flight (16 at most). The harness limit is raised from 4 to 8 and the check (both parts) runs with `--conc 8`, one part at a time.
- **Other load on the server.** The operator is running 8 concurrent sequences of their own against the same server for the whole run, so the server carries about 16 streams. Seconds measured here are under that load and are not compared with earlier rounds' idle seconds. Outcome classes and grades are read as registered; a server failure or timeout may be more likely, and is counted, not rerun beyond the registered single retry.
- Nothing else changes: questions, gold, graders, classes and hypotheses are as registered.

## Amendment 3 — 2026-11-16 20:50 UTC, before any run on the second server (round three)

- **The server.** The operator moved the run to a second server, the relay's `default-model-2`, which serves **Qwen 3.8 27B** (the operator: both endpoints serve Qwen 3.8 27B) and carries nothing else. Every one-off container runs with `LLM_MODEL=default-model-2`, so the instance's own model route answers from that server; the harness code is unchanged apart from the limit below, and every log records the model name `default-model-2`. Preflight 20:41–20:42 UTC: endpoint healthy, self-reports Qwen (Alibaba / Tongyi Lab) without a version, server `vllm-0.31.1rc1.dev344+g5b0b8f251-98b23dce`; 64 requests sent at once all returned 200 in 4.3–6.2 s.
- **Up to 64 in flight.** The operator said the second server takes 64 concurrent requests. The harness limit is raised to 64. No Mylo function calls the decision server (only the nightly opportunities pipeline does), so only `default-model-2` carries this load; the host's Postgres (100 connections) and CPU are shared with the live instance as before.
- **The run on `default-model` was stopped** at 20:41 UTC, three minutes into Phase 1, when the operator moved the work; it is not counted (ISSUES.md).
- **A third row** (`qwen38-m2-20261116`): the check on the second server, `--conc 32` (all 20 demo turns at once, then all 11 gate turns). It is the same model as the second row, on a server with no other load.
- Nothing else changes: questions, gold, graders, classes and hypotheses are as registered.

## Amendment 4 — 2026-11-17 05:35 UTC, before the overnight fixes (plan `docs/plans/20261116-mylo-overnight-fixes.md`)

- **Why.** Three product fixes are made tonight (complete feed lists, malformed calls no longer use up the failure limit, references for people and projects). The check is run before them and after them, a row each, on the same model.
- **Models, as the operator stated them on 2026-11-16 (evening):** `default-model` serves **Qwen 3.8 27B** (the instance model, shared with the operator's own work) and `default-model-2` serves **Gemma 4 31B**. Preflight 04:44 UTC (`logs/preflight_overnight_20261117.jsonl`): both healthy; the first self-reports Qwen (server `vllm-0.31.1rc1…`), the second "trained by Google" (server `vllm-0.21.0`). Recorded again at the start and end of every part.
- **Rows.** `qwen38-before-20261117` and `qwen38-after-20261117` on `default-model`, `--conc 8` (the plan's limit on the instance model). The same pair on `default-model-2` (`gemma4-before-20261117`, `gemma4-after-20261117`, `LLM_MODEL=default-model-2`, `--conc 8`): not asked for by the plan, added because the defect the department head's control found (Q-075) needs a model that gets arguments wrong, and Qwen passed that control 6 of 6 before any fix.
- **A frozen copy of the code.** Each row's containers mount `git archive <commit>` of `tools/` and `web/backend/` read-only over the checkout's (`code/drive_row.sh`), so a row reads exactly one commit while the checkout is being edited: the "before" rows read `4f81ca2e`; the "after" rows read the commit that holds the three fixes (named in RESULTS.md).
- **Gold.** The twelve graded questions are still graded against `EXP-2026-11-018`'s round-two `data/gold.json`, as registered, so the rows stay comparable with each other; the feeds have moved since, which lowers every row alike.
- Nothing else changes: questions, probes, controls, classes and hypotheses are as registered.

**Added 2026-11-17 05:56 UTC, before any "after" row.** The "after" rows read a
frozen copy of `55cfdb1c`: the three fixes (`f81d2837`, `035c9066`,
`3ea9c144`), the slate reader's old name (`62c9fa17`), and two follow-ups the
go-live check asked for (`ce976d2f`, `55cfdb1c`: a deadline-filtered slate
keeps "who should look"; calls sent together with the same slip count once
toward the failure limit, and `#7 Some title` is read as `#7`).

## Amendment 5 — 2026-11-17 17:10 UTC, before a third row after seven more fixes

- **Why.** Seven more fixes were made on 2026-11-17 (afternoon); they are listed in `EXP-2026-11-018` Amendment 8. The check gets one more row per model that is up, read beside the two rows of Amendment 4 on the same model.
- **Rows.** `qwen38-after2-20261117` on `default-model` (`--conc 8`), from a frozen copy of `640d7fe0` (`code/drive_row.sh`). `gemma4-after2-20261117` on `default-model-2` only if that server is healthy again and self-reports as Gemma before the hard stop: at the preflight of 16:41 UTC (`logs/preflight_afternoon_20261117.jsonl`) the relay reports it `failed` ("All connection attempts failed"), and `default-model` healthy, self-reporting Qwen (the operator's statement of 2026-11-16: Qwen 3.8 27B).
- **Gold.** As registered: the twelve graded questions against `EXP-2026-11-018`'s round-two `data/gold.json`; the feeds have moved again since (the 12:01 UTC nightly run), which lowers every row alike.
- Nothing else changes: questions, probes, controls, classes and hypotheses are as registered. No new turn after 11:40 UTC on 2026-11-18.

**Added 2026-11-17 17:31 UTC, before the row.** The maintainer raised the limit on the instance model to 32 turns in flight. `qwen38-after2-20261117` runs with `--conc 32` (the earlier Qwen rows ran with `--conc 8`); the check has 31 turns, and nothing it counts depends on seconds.

**Added 2026-11-17 17:34 UTC, before the row.** The maintainer is starting the second server again for Gemma 4 31B and asked for 32 turns in flight on it: `gemma4-after2-20261117` runs with `--conc 32` once that server is healthy and self-reports as Gemma.
