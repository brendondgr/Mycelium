# Lab recommendation feeds capped at ~25 — plan

> **Status: complete (2026-07-18).** Implemented `refit_targets_batch` +
> `run_refitting` lab coverage; verified on the live stack (`pulse-lab` grants
> 24→154, conferences 25→165, all threshold-mode with `embedding_match`); 76+
> content tests pass; merged into `main`.

## Objective

Make a lab's Research Papers / Grants / Conferences (and the lab-visible
fellowship union) feeds show **all** matched items — the same variable-length,
threshold-gated feed individual users already get — instead of the stale ~25-item
list the lab overview currently reports.

## Root cause (verified against the live stack)

The matcher already surfaces the full threshold feed for labs; the problem is that
**existing labs are never re-scored with the current code**, so their stored feed
is frozen at the pre-threshold-mode fixed top-25 slice.

Evidence (running `mycelium-backend-1`, 2026-07-17):

| Target | grants | conferences | papers | `embedding_match`? | latest `run_at` |
|---|---|---|---|---|---|
| user `bdgr` | 141 | 121 | 1105 | yes | 2026-07-17 |
| user `brendondgr` | 124 | 136 | 930 | yes | 2026-07-17 |
| lab `pulse-lab` | **24** | **25** | 50 (25×2 runs) | **no** | **2026-07-12** |

- The lab's stored opportunity rows are `source="fallback"`, `match_percent=null`,
  and carry **no** `embedding_match` signal — the fingerprint of the old fixed
  `DEFAULT_SURFACE = 25` slice, not the threshold path.
- A dry-run of the **current** code for `pulse-lab`
  (`opportunities._prepare_match`) surfaces **154 grants / 166 conferences**
  clearing `GRANT/CONFERENCE_MATCH_THRESHOLD` with `job.surface_limit = None`. So
  today's code is correct — it is the *data* that is stale.
- Why it never self-heals: the nightly run only **appends that day's new items**
  (`run_daily_opportunities_batch`, by design — see `docs/skills/global.md`); the
  whole-corpus **replace** pass is `refitting`, and `refit_batch` /
  `run_refitting` iterate **users only**. `refit_lab` / `refit_target` exist and
  are correct, but nothing re-personalizes existing labs in bulk. Individuals look
  "unlimited" simply because they *have* been refit under the new code; labs have
  not.

So the lab overview `window_counts` (uncapped in both API and UI) honestly reports
~25 because only ~25 stale rows exist.

## Assumptions / decisions

- The fix is **parity of coverage**, not a new cap number: whenever we bulk-refit
  users, also refit active-subscription labs + their lab-scoped projects — exactly
  the target set the nightly run already fans out to (`tasks.select_targets`).
- Fellowships stay user-only for labs (unchanged); institutional refit covers
  `papers / grants / conferences` (`refitting.TARGET_AREAS`).
- Labs are included **by default** in `run_refitting` (mirroring the nightly run
  and the user path); a `--no-labs` escape hatch preserves the old behaviour, and
  a `--user`-scoped run stays user-only (via `select_targets`' own short-circuit).
- No settings/threshold change — the 250 backstops are already correct.

## Implementation phases

### Phase 1 — batch refit for institutional targets (`refitting.py`)
- Add `llm_limit` pass-through to `refit_target` (mirror `refit_user`:
  `suggestion_limit` for papers, `llm_limit` for opportunities) so `--llm-limit`
  applies to labs too.
- Add `refit_targets_batch(labs, projects, *, areas=TARGET_AREAS, llm_limit=None,
  complete=None, persist=True, log=None) -> list[RefitResult]` — iterate
  `refit_lab` / `refit_project`, catching per-target errors like `refit_batch`.

### Phase 2 — wire labs into the bulk command (`management/commands/run_refitting.py`)
- Add `--no-labs` flag.
- After the user batch: `labs, projects = ([], []) if no_labs else
  select_targets(usernames)`; refit them via `refit_targets_batch` with the same
  `areas` / `llm_limit` / `complete` / `persist`.
- Extend the summary line to report user and lab/project refit counts.
- `manual_mylo.py` forwards all flags to `run_refitting`, so the human-invoked
  re-personalization run picks labs up automatically (no change needed there).

### Phase 3 — refresh existing lab data (dev stack) + verify
- Run the command against `mycelium-backend-1` to replace the stale feeds.
- Confirm `LabRecommendationsView` payload / `window_counts` for `pulse-lab` now
  report the full feed (>>25) with `embedding_match` present.

### Phase 4 — docs, changelog, commit, merge
- Update `docs/repo-map.md` rows for `refitting.py` and `run_refitting` /
  `manual_mylo.py` to note lab coverage.
- Add a `docs/changelog.md` entry.
- Commit (human-authored message, no AI attribution — per `docs/skills/global.md`).
- Merge this worktree branch into local `main`, resolving any conflicts.

## Interfaces that change

- `apps.content.refitting.refit_target` — new optional `llm_limit` kwarg.
- `apps.content.refitting.refit_targets_batch` — new function.
- `run_refitting` command — new `--no-labs` flag; default run now also refits
  active labs + lab projects. No HTTP/API contract change; no schema/migration.

## Validation & acceptance

- `uv run --project web/backend python web/backend/manage.py run_refitting --max 1
  --dry-run` runs clean and its output lists labs/projects.
- After a real refit, `pulse-lab`'s grants/conferences counts jump from ~25 to the
  threshold-feed size (~100+), each row carrying `embedding_match`, and the lab
  overview "What Mylo found" matrix reflects it.
- `ruff` clean on changed files.
- No user-scoped (`--user …`) behaviour change; `--no-labs` reproduces the old
  output.

## Explicit exclusions

- No change to the nightly append semantics, thresholds, or feed caps.
- No frontend changes (lab feed pages already render every returned item; the
  overview matrix already renders raw `window_counts`).
- Fellowship-for-labs behaviour is unchanged.
