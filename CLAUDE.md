# Mycelium Agent Instructions

At the start of every Mycelium session, read `docs/skills/global.md`. That global
skill points to the canonical project direction in `docs/purpose.md`,
`docs/styles.md`, and `docs/goals.md`.

Keep work aligned with those documents unless the user explicitly changes the
product direction. When direction changes, update the canonical docs instead of
leaving the decision only in code or chat.

## First-time setup

On a fresh clone, run `make setup`. It writes `mycelium.toml` for a deployment
profile, writes `.env` with generated secrets, builds and starts the stack,
applies migrations, and creates the first admin. Without a terminal it asks
nothing, so an agent passes the model endpoint as `LLM_BASE_URL`, `LLM_API_KEY`
and `LLM_MODEL` in the environment (and `PROFILE=…`, default `lab`). `make help`
lists every other command; `make test` runs the backend suite and every tool's
tests; `make tools-check` shows which tools loaded.

Operator policy — sign-up, email, billing, limits, optional features, the
nightly budget — lives in `mycelium.toml`, not in code or `.env.example`. Change
it with `ops/mycelium config` and follow `docs/skills/configure.md` when a user
asks to set up or reconfigure their instance. A new operator-facing setting is
added as a key in `web/backend/config/instance.py`, not as a bare env var — or,
if a tool owns it, as a `Setting` in that tool's `tool.py` (its
`[tools.<name>]` section).

## Tools

Research capabilities are modular **tools**, one folder each under `tools/` at
the repository root. A tool is declared by one class in `tools/<name>/tool.py`
and loaded by discovery; a tool that cannot load never runs. Read
`docs/skills/tools.md` and `tools/README.md` before adding, changing or moving
code into a tool, and start a new one with `make new-tool NAME=<name>`.

## Navigating the code

To find where something lives, read `docs/repo-map.md` first — it maps every task
and feature to a concrete path. Prefer it over blind `find` / `grep` / `ls`
sweeps, which waste tokens. Only search the tree when the map does not resolve
your target. When you add, move, or rename a top-level area (a Django app, an app
route group, a `lib/` module, an infra file), update `docs/repo-map.md` in the
same change so it stays trustworthy.

Use root-level commands when possible. Use `uv` for Python backend dependency
management, backend commands, linting, and tests.

If working inside `web/`, also follow `web/CLAUDE.md`.

## Research record (mandatory)

- Any experiment, benchmark, baseline, ablation, or evaluation run MUST be
  recorded under `docs/research/experiments/` following
  `docs/research/AGENT_INSTRUCTIONS.md`.
- Never report a metric in chat or a commit message without also writing it to
  the corresponding `manifest.yaml` and `RESULTS.md`.
- Never hand-edit a figure. Never hardcode a number in a plotting script.
- Failed and abandoned runs are recorded, not deleted.
- If asked to "just quickly check" a number, still create the experiment folder.
- Scaffold with `make new-experiment SLUG=<slug>`; check with
  `make validate-research`. There is no CI enforcement — run it yourself before
  finishing.

## Documentation rules

- `CLAUDE.md` is the only agent-instruction file. There is no `AGENTS.md`; do not
  reintroduce one.
- Docs live in `docs/`. Keep them accurate and compact — a claim that is no
  longer true of the code is worse than no claim at all.
- Record completed work in `docs/changelog.md` using the schema in
  `docs/skills/global.md`. Implementation plans are working documents: delete
  one once its work has shipped rather than leaving a stale plan behind.
