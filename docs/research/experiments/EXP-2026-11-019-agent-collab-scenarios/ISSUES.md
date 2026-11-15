# EXP-2026-11-019 — Issues

## Before the run

1. **The shared sandbox was two months of migrations behind** (no agent
   tables). It was not migrated in place: the experiment copies it to
   `mycelium_sandbox_exp019` (`CREATE DATABASE … TEMPLATE mycelium_sandbox`) and
   migrates the copy, so `mycelium_sandbox` and earlier experiments' state are
   untouched. The copy also carried EXP-2026-09-007's consent plan (228
   settings, 60 personal addresses, 30 unverified accounts, 876 appearances,
   300 search logs); the overlay resets all of that (PROTOCOL.md "Data").
2. **Calls are not read by the slot reader.** The sandbox's 150 planted calls
   were not in the copy (0 requirement slots), and reading new ones would spend
   the model; the experiment's 12 calls carry their one slot written directly.
3. **Within a turn, a function loaded with `load_functions` was not added to
   the `tools` list sent to the model** in the dry run (the loop's
   `_visible_functions` reads `thread.settings` from the thread object fetched
   at the start of the turn; `load_functions` writes a fresh copy). The real
   model still calls such functions by name (round one's logs: `load_functions`
   followed by the loaded functions, and the gate decides each call), so this
   does not change what is graded here. Not fixed (plan rule); recorded as
   Q-087.
4. **`dirty: true`.** Other phases' agents were writing their own experiment
   folders in the same checkout during this run; nothing under `web/`,
   `tools/` or `ops/` was modified by anyone. The commit in the manifest is the
   one the run executed.
5. **Plan rows the product does not state** (S6 "not opted in themself", S4
   "restricted `open_to`"): decided before the run, PROTOCOL.md decisions 1–2;
   Q-085, Q-086.

## During the run

(appended as it happens)
