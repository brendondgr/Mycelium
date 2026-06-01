# Mycelium Agent Instructions

At the start of every Mycelium session, read `docs/skills/global.md`. That global skill points to the canonical project direction in `docs/purpose.md`, `docs/styles.md`, and `docs/goals.md`.

Keep work aligned with those documents unless the user explicitly changes the product direction. When direction changes, update the canonical docs instead of leaving the decision only in code or chat.

Use root-level commands when possible. Use `uv` for Python backend dependency management, backend commands, linting, and tests.

If working inside `web/`, also follow `web/AGENTS.md`.
