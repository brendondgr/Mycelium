# Mylo overnight — fix what three rounds found, then measure again

**Status (2026-11-17 05:25 UTC):** in progress — fixes 1 to 3 committed (`f81d2837`, `035c9066`, `3ea9c144`), not yet live. Run by an agent on the live
host in one night, without a person present. Delete this file once every
phase is recorded; the evidence stays in `docs/research/` and the open list in
`docs/plans/20261113-mylo-evaluation-follow-ups.md`.

**Correlation ID:** `20261116-mylo-overnight-fixes`

## Tonight's execution (written before the first change)

The maintainer handed over the plan below and asked for everything "except E
& F". The plan has no lettered parts; its table has eight rows, so E and F are
read as the fifth and sixth: **phase 5 (collaborator search in the public
demo) and phase 6 (the answer checker) do not run tonight.** Everything else
does: phases 0–4, 7, 8 and the record.

**Models, as the maintainer stated them on 2026-11-16 (evening):** the relay's
`default-model` serves **Qwen 3.8 27B** (the instance model; shared with the
maintainer's own work, so slow) and `default-model-2` serves **Gemma 4 31B**.
Preflight 2026-11-17 04:44 UTC: both healthy; the first self-reports Qwen
(vLLM 0.31.1rc1), the second "trained by Google" (vLLM 0.21.0)
(`EXP-2026-11-021-agent-model-check/logs/preflight_overnight_20261117.jsonl`).

| Step | What | Where it runs |
|---|---|---|
| Phase 0 (04:42–05:17 UTC) | Clone equals `origin/main` (`4f81ca2e`); baseline suite; the "before" row of the model check | Qwen, 8 in flight; a second "before" row on Gemma |
| Phases 1, 2, 3 | One commit each, with tests and docs | no model |
| Go-live | Whole suite on the commit that holds the three fixes, `make restart`, one demo question | — |
| Phase 4 | `EXP-2026-11-018` (all arms), then `-021` "after" row, then `-010` arm A7 | Qwen, at most 8 turns in flight |
| Phase 7, beside phase 4 | A Gemma "after" row of the model check, then `EXP-2026-11-019` S1, S2, S10, both modes, three repetitions | Gemma, alone on `default-model-2` |
| Phase 8, beside phase 4 | Built in a separate worktree, merged and restarted only when no run is in flight; then S4's `open_to` variant | Qwen |
| Record | Follow-ups plan, ledgers, changelog, index, validation, push | — |
| **11:40 UTC** | **Hard stop for every run** (the nightly starts 12:01 UTC) | — |

How the rules are met tonight:

- **Fetch and push go over HTTPS with the host's `gh` login.** The SSH key is
  not available to an unattended session (`Permission denied (publickey)`); the
  `origin` remote itself is not changed.
- **The suite is red before any change: 4 tests** (`make test`, 5,055 tests,
  12 minutes): `apps/accounts/tests/test_synthesize_api.py::test_site_and_resume_merge`
  and three in `tools/delivery/tests/test_opportunity_clusters.py`. None is in
  a file a phase touches; they are not tonight's. "Green" below means "these
  four and no other".
- **A whole-suite run never reads a tree that is being edited.** Each one runs
  `make test`'s command in a `git worktree` of the commit under test, on its
  own test database. From a worktree six more tests error at setup
  (`apps/integrations/tests/test_setup_bindings.py`), on the untouched commit
  as well; they pass in the checkout. The tool suites named in the rules run in
  the checkout after every fix.
- **A measurement never reads a tree that is being edited either.** The live
  backend mounts the checkout, and so would a one-off container. Each
  measurement's containers therefore mount a `git archive` of the commit under
  test over `tools/` and `web/backend/`, with `docs/research` writable from
  the checkout. Product edits made while a run is in flight happen in a
  separate worktree.
- **One restart for fixes 1–3**, after the whole suite is green on the commit
  that holds all three, and before any phase-4 run starts (a restart would
  take the database and the model tunnel away from a running measurement).
- Dropped first if time runs out: phase 8, then phase 7's fix, then the
  `EXP-2026-11-010` arm. Phase 4's `EXP-2026-11-018` run is dropped last.

## Objective

Rounds two and three measured and fixed nothing. This night **changes product
code**, one defect at a time, and measures each change with the experiment
that found the defect.

| # | Defect | Found by | Phase | Time box |
|---|---|---|---|---|
| 1 | Mylo reads the first part of a feed and answers as if it were all of it. | `EXP-2026-11-018` (2 of 27 list runs right; C-056 refuted; Q-079) | 1 | 60 min |
| 2 | Two malformed calls use up the retry limit and the correct third call is refused. | `EXP-2026-11-021` (a department head refused their own project; Q-075) | 2 | 30 min |
| 3 | Mylo names the right people and projects without citing them. | `EXP-2026-11-018` (61% strict, 71% when a name counts; C-043) | 3 | 45 min |
| — | Measure 1–3 | `EXP-2026-11-018`, `-021`, `-010` | 4 | 90 min |
| 5 | A demo visitor cannot try collaborator search. | not checked | 5 | **not tonight** |
| 6 | The answer checker treats a listed reference as read, lets an unread citation through after repair, and shortens answers without saying so. | `EXP-2026-11-020` (C-049 refuted; Q-076, Q-077, Q-080; O3) | 6 | **not tonight** |
| 7 | One model ended turns with no reply; the cause is unknown. | `EXP-2026-11-019` round two (Q-070, Q-088) | 7 | 60 min, only if that model is served |
| 8 | `open_to` is decided to rank, and is not read; two settings texts are missing. | Q-085, Q-086 | 8 | 45 min |

Phases are in priority order. When a time box runs out, finish the commit in
hand or revert it, record where it stopped, and move on. Phases 5 to 8 are
dropped before phase 4 is.

## Rules

**Before anything**

- Bring the clone to GitHub's `main`: `git fetch origin`, then
  `git status`. If the working tree is clean and the local branch is not an
  ancestor of `origin/main`, `git reset --hard origin/main`. If the tree is
  **not** clean, stop and report; do not stash or discard.
- Record the model at the start and end of every phase, as round three did:
  the relay's `/v1/models`, the model's own answer to "which model are you",
  and the operator's `EVAL_MODEL_NAME`. Never guess a name. If the model
  changes mid-phase, split the phase's runs at the change.

**For every fix**

- One defect, one commit: the change, its tests, and the docs it makes wrong
  (`tools/agent/README.md`, `docs/architecture.md`, `docs/repo-map.md` where
  they apply).
- A fix is a general rule about behaviour. It must not mention, special-case
  or be tuned to a question, probe or scenario of any experiment.
- Before it goes live: `make test`, and
  `uv run --no-sync --project web/backend pytest tools/agent/tests tools/_framework/tests`.
  If they are not green after two attempts, revert the fix, write what was
  tried in the follow-ups plan, and move on.
- Go live with `make restart`, then ask the public demo one question and read
  the reply.
- **Not to be touched tonight:** the order or meaning of the permission
  layers (`tools/agent/permissions.py`), who may be found by collaborator
  search (`web/backend/apps/collab/consent.py`), any default in
  `web/backend/config/instance.py`, `mycelium.toml`, `.env`. If a fix seems
  to need one of these, stop that phase and record why.

**For every measurement**

- A fix is committed first; the measurement is a **new attempt** after it,
  under a numbered amendment in the experiment's `PROTOCOL.md` committed
  before the first run. Questions, probes, graders and bars are unchanged.
- One-off backend containers, seeded databases, demo-lab threads named
  `EXP-` and deleted afterwards, at most 8 Mylo turns in flight on the
  instance model, numbers in `data/metrics.json`, `manifest.yaml` and
  `RESULTS.md` with n and interval, failed runs kept.
- End each phase with `make research-index && make validate-research`,
  commit, and push.
- Stop every run before the nightly run (`mylo-daily.timer`), or record the
  overlap.

## Phase 0 — Preflight (15 min)

1. The clone and model steps above. `make test` on the untouched tree; if it
   is red before any change, record which tests and continue (they are not
   tonight's to fix unless a phase touches them).
2. One row of the model check (`EXP-2026-11-021`, `code/check.py`) as the
   "before" row for tonight's model.

## Phase 1 — Lists

`tools/agent/functions/feeds.py` (`feeds_slate`, `feeds_saved`,
`feeds_deadlines`) and `projects_feed` in `tools/agent/functions/projects.py`.

- **What must be true afterwards.** A question of the form "which grants,
  fellowships or conferences in this feed have a deadline between two dates"
  can be answered completely from one call. The functions take the filter
  (item type, deadline window, which deadline) and apply it in the database
  **before** any cut; they return every match, in compact rows (reference,
  title, the deadline asked about) when there are many, inside the
  `result_cap_tokens` budget.
- Every result ends with one line saying either that it is complete ("all 4
  of 4") or how to get the rest ("first 20 of 36; pass `offset=20`").
- Ranking is not changed. This reads the slate; it does not re-rank it.
- **Tests.** A slate of 36 conferences with 4 inside a window returns exactly
  those 4 and the "complete" line; a result too long for the budget returns
  the "first n of N" line and a second call with the offset returns the rest;
  a caller who may not see the feed is refused exactly as before.

## Phase 2 — The retry limit

`tools/agent/loop.py` (`FAILURE_LIMIT`, the `keeps_failing` refusal).

- **What must be true afterwards.** A call rejected because its arguments
  were malformed (an unknown argument name, a missing required one,
  `bad_arguments`, `need_project`) does not count toward `FAILURE_LIMIT`.
  Malformed calls get their own, higher ceiling so a model cannot loop on
  them forever. The error for a malformed call names the arguments the
  function accepts.
- A call that ran and failed for a real reason counts as before.
- **Tests.** Two malformed calls then a correct one: the correct one runs. A
  function that genuinely fails twice is still refused the third time.
  Malformed calls past their own ceiling are refused with a reason.

## Phase 3 — Citing people and projects

`tools/agent/functions/org.py` (`org_lab_members`, `org_person`),
`tools/agent/functions/projects.py`, `tools/agent/prompt.py`.

- **What must be true afterwards.** Every person and project a function
  returns carries its reference number on its own line, and the prompt tells
  Mylo to cite each person, project or item it names with that number, and to
  cite only the ones the answer is about, not a whole roster for context.
- **Tests.** The functions' results carry a reference for each member and
  project. The citation behaviour itself is a model's, so it is measured in
  phase 4, not unit-tested.

## Phase 4 — Measure 1 to 3

1. **`EXP-2026-11-018`, a new amendment and tag.** Recompute gold first with
   `code/build_gold.py` (the feeds move every night), then all three arms,
   three repetitions, graded as round three graded (primary, secondary,
   first attempt, and the partial-list classes). Re-read C-043 to C-046 and
   C-056 against their own bars, per model, beside round two's and round
   three's rows. Report the list kind, the people and project kinds, and
   question `j08` on their own.
2. **`EXP-2026-11-021`, a new row** for tonight's model after the fixes,
   beside phase 0's "before" row. The department head's control is the test
   of phase 2.
3. **`EXP-2026-11-010`, a new arm:** idle and 8 in flight, unchanged
   questions. Lists that page may cost more calls; this says whether they do.

**What would count against a fix.** Phase 1: a partial list presented as
complete in more than 10% of list runs (C-056's bar). Phase 2: the control
refused again. Phase 3: the gap between the primary and the secondary grading
not narrowing. A fix that fails its measurement stays in unless it made
something worse; either way the result is recorded as it is.

## Phase 5 — Collaborator search in the public demo — not tonight

Left as the maintainer wrote it, for another night: look first as a demo
visitor (the lab half and the outward half); only if outward search can be on
for the demo world alone, with fictional people who can never be returned to a
real account and no real account returned to a demo visitor, add them to
`web/backend/apps/demo/world.yaml` / `seed.py` with tests in
`web/backend/apps/demo/tests`.

## Phase 6 — The answer checker — not tonight

Left for another night: evidence kept per reference (Q-076, O3), a flagged
citation never survives the repair (Q-077), no silent shortening (Q-080),
measured with `EXP-2026-11-013` `code/rescore.py` (0 false alarms on the
stored originals must hold) and `EXP-2026-11-020` 5a and 5b.

## Phase 7 — Turns that end with no reply

Runs only if the operator states that Gemma 4 31B is being served, on the
instance endpoint or a second one. Otherwise record "not run" and skip.
**Tonight: stated, on `default-model-2`.**

1. `EXP-2026-11-019` Amendment 4's design, unchanged: S1, S2 and S10, the
   repeated and the fresh mode, three repetitions, every turn classed as
   answered, question, fallback line or blank, and what the model returned
   kept for every empty call.
2. Check the lead from `EXP-2026-11-010` arm A6: empty calls made with
   functions switched off (`tool_choice: none`) that still spent completion
   tokens. Count how many of this model's empty calls fit it.
3. **A fix only if one cause accounts for most of the empty calls.** Then:
   the fix, its tests, and the same run again. If the cause is unclear, record
   the table and change nothing.

## Phase 8 — `open_to` and two settings texts

1. **Texts.** The collaboration settings say that anyone may search without
   being open to collaboration themself (Q-085), and that `open_to` helps the
   right seekers find a person and hides them from no one (Q-086).
2. **Ranking.** If a collaborator search already carries the kind of
   collaboration sought, `web/backend/apps/collab/matcher.py` ranks a person
   whose `open_to` includes it above an equal match whose does not. It never
   removes anyone. If a search carries no such kind today, adding one is a
   larger change: stop and record it.
3. **Measure.** The `open_to` variant of S4 in `EXP-2026-11-019`: the person
   is still returned (9 of 9 before), and nobody outside consent is.

## Record (15 min, not optional)

1. `docs/plans/20261113-mylo-evaluation-follow-ups.md`: every row touched
   tonight, with what was done, what was measured and what is still open.
2. `docs/research/CLAIMS.md` and `docs/research/OPEN_QUESTIONS.md`.
3. `docs/changelog.md`: one row per fix that went live, one `EXECUTED` row
   for the measurements.
4. `make research-index && make validate-research && make test`; push.
5. A summary at the top of the follow-ups plan: which fixes are live, which
   were reverted, which phases did not run, and the model each number is on.

## Left for a person

- Whether everyone should be discoverable by default with an opt-out (Q-089).
  Not changed tonight: it is a decision, and the collaborator tests rest on
  today's opt-in rule.
- Whether Mylo may still name a project that was narrowed mid-conversation
  (Q-090).
- The quantisation and server version of each model, if the agent cannot read
  them from the model server.
- Phases 5 and 6 above.

## Exclusions

- No change to ranking, the nightly run, billing, or any tool other than
  `tools/agent` and the files named above.
- No new experiment questions, probes or graders.
- No outside raters.
