# Mycelium Agent Instructions

At the start of every Mycelium session, read `docs/skills/global.md`. That global skill points to the canonical project direction in `docs/purpose.md`, `docs/styles.md`, and `docs/goals.md`.

Keep work aligned with those documents unless the user explicitly changes the product direction. When direction changes, update the canonical docs instead of leaving the decision only in code or chat.

## Navigating the code

To find where something lives, read `docs/repo-map.md` first — it maps every task and feature to a concrete path. Prefer it over blind `find` / `grep` / `ls` sweeps, which waste tokens. Only search the tree when the map does not resolve your target. When you add, move, or rename a top-level area (a Django app, an app route group, a `lib/` module, an infra file), update `docs/repo-map.md` in the same change so it stays trustworthy.

Use root-level commands when possible. Use `uv` for Python backend dependency management, backend commands, linting, and tests.

If working inside `web/`, also follow `web/AGENTS.md`.
