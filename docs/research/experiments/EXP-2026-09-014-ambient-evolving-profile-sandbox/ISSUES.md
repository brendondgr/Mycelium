
## Run 1 — failed: a harness bug in the ranking step

Worktree `d79b9eb`, 06:38–06:45 UTC. The Plan 04 pass and the eight-week
simulation ran; the ranking step then crashed
(`AttributeError: 'tuple' object has no attribute 'item'` — the harness read
fusion's slate entries as objects; they are `(item, score)` pairs). The
harness wrote nothing before the crash, so the simulation's results were lost
with it. No metric from run 1 exists or is reported.

**Fixes (harness only):** slate entries read as pairs; the nights' results are
written to `<out>.nights` before the ranking step starts. **Run 2** reruns the
registered protocol from a worktree pinned at the fix.
