# Contributing

Project direction and working rules live in [`CLAUDE.md`](CLAUDE.md) and
[`docs/skills/global.md`](docs/skills/global.md). This file covers the two things
that have their own process: running an experiment, and the checks a change is
expected to pass. Nothing runs automatically — the checks below are yours to run
locally before you commit.

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

## Changing ranking logic

A change to `retrieval.py`, `lexical.py`, `fusion.py`, `ranking.py`, or
`pipeline.py`'s pool construction requires a fresh evaluation run **and** an
experiment folder recording the before/after numbers. It is one command
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
| `uv run --project web/backend pytest` | Backend tests |
| `npm run lint` / `npm run build` | Frontend, from the repository root |

## Changelog

Every session that changes tracked files adds an entry to
[`docs/changelog.md`](docs/changelog.md) using the schema in
`docs/skills/global.md`. Entries are append-only; never edit a past one.
