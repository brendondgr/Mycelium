# EXP-2026-09-003 — Issues

1. **Dirty tree.** The client (`web/backend/apps/core/systemone.py`), its
   command and tests, the settings block, the dependency, and this folder were
   all uncommitted when the manifest was scaffolded; they are committed together
   with the run, which is the "commit the folder with the code it depends on"
   rule.
2. **Host virtualenv.** `web/backend/.venv` is root-owned (created by a Docker
   build), so `uv run --project web/backend` cannot run on this host. Scripts
   and tests here run through the eval project's environment, which mirrors the
   backend dependencies and puts `web/backend` on `sys.path` — the same
   arrangement `EXP-2026-08-013` used.
3. **No judgements.** Both comparators are system outputs; see PROTOCOL §Data.
4. **Reader text sent off-host.** Recorded as a decision, not an accident: the
   reader instructed it for their own account. Not to be generalised to any
   other account without the data-processing terms read first.
