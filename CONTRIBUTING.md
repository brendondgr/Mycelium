# Contributing

Project direction and working rules live in [`CLAUDE.md`](CLAUDE.md) and
[`docs/skills/global.md`](docs/skills/global.md). This file covers the things
that have their own process: running an experiment, adding a tool, and the
checks a change is expected to pass. CI (`.github/workflows/ci.yml`) runs the
tests, lint, type-check, research-record validation and a dependency and secret
scan on every pull request; run the checks below locally before you push.
Security problems are reported privately — see [`SECURITY.md`](SECURITY.md).
Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md).

## Running an experiment

1. `make new-experiment SLUG=<slug>` — scaffolds the folder from templates and
   pre-fills date, commit, branch, and dirty-tree status.
2. Fill `PROTOCOL.md` **before** running anything.
3. Run via the recorded entrypoint so the manifest stays true.
4. Fill `RESULTS.md`, then `make figures && make research-index &&
   make validate-research`.
5. Commit the experiment folder in the same pull request as any code change it
   depends on.

Full contract: [`docs/research/AGENT_INSTRUCTIONS.md`](docs/research/AGENT_INSTRUCTIONS.md).

Failed and abandoned runs are recorded, not deleted. A deleted dead end is a
dead end somebody walks into twice.

## Adding a tool

Research capabilities are tools under [`tools/`](tools/README.md), one folder
each. `make new-tool NAME=<name>` scaffolds one; declare it in its `tool.py`
(dependencies, settings, nightly stages, URL mount) rather than wiring it into
settings, URLs or the nightly runner by hand. Rules:
[`docs/skills/tools.md`](docs/skills/tools.md).

## Changing ranking logic

A change to `tools/retrieval/index.py`, `tools/retrieval/lexical.py`,
`tools/recommendation/fusion.py`, `tools/recommendation/ranking.py`, or
`tools/recommendation/pipeline.py`'s pool construction requires a fresh
evaluation run **and** an experiment folder recording the before/after numbers. It is one command
precisely so this is never skipped:

```bash
uv run --project eval eval/run.py --config eval/configs/<arm>.toml
```

See [`docs/evaluation.md`](docs/evaluation.md).

## Checks

| Command | Checks |
|---|---|
| `make validate-research` | The research record: manifests, figures, pointers, claims, index |
| `make research-ci` | The full check — validation plus index and figure staleness |
| `make test` | Backend and tool tests (strict: a tool that fails to load fails the run) |
| `make tools-matrix` | Removes and breaks each tool in turn and checks the rest |
| `npm run lint` / `npm run build` | Frontend, from the repository root |

## Changelog

Every session that changes tracked files adds an entry to
[`docs/changelog.md`](docs/changelog.md) using the schema in
`docs/skills/global.md`. Entries are append-only; never edit a past one.
