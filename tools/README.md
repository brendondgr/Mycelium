# Tools

Mycelium is a platform — people, labs, departments, profiles, projects,
billing, integrations and the web app — with **tools** built on it. Each tool
is one folder here, and everything the tool is lives inside that folder: its
models and migrations, API routes, Celery tasks, management commands, nightly
stages, configuration, tests and this kind of README. Nothing outside the
folder has to be edited to add a tool, and deleting a leaf tool's folder
removes it completely.

```text
tools/
├── README.md            this file
├── _framework/          the machinery: finds, checks and loads tools (not a tool)
└── <name>/              one tool
    ├── tool.py          the declaration: one Tool subclass (stdlib + spec imports only)
    ├── apps.py          two lines binding Django to the tool
    ├── read.py          the read door: what others may read
    ├── service.py       the write door: what others may change
    ├── events.py        the events it publishes
    ├── models.py, migrations/, urls.py, views.py, tasks.py, management/ …
    ├── README.md        what it owns, its doors, its config keys, its stages
    └── tests/
```

## Installed tools

| Tool | Depends on | Core | What it does |
|---|---|---|---|
| [`retrieval`](retrieval/README.md) | — | yes | The grounded corpus: sources, collectors, dedup, embeddings, deadlines, search |
| [`recommendation`](recommendation/README.md) | `retrieval` | yes | Ranks and filters the corpus for every person, lab, department and project |
| [`delivery`](delivery/README.md) | `retrieval`, `recommendation` | yes | The feeds' API, saves, reports, reminders, alerts, Discord/Slack delivery, announcements |
| [`fulltext`](fulltext/README.md) | `retrieval` | no | Gets the paper itself: checks for a legal copy, fetches it from open sources or the instance's publisher keys, keeps the original plus markdown |
| [`agent`](agent/README.md) | `retrieval`, `recommendation` | no | Mylo as a read-only conversational agent: answers from everything a person may see, cites it, remembers, changes nothing |
| [`files`](files/README.md) | — | no | Stores uploaded files in structured folders, reads their text, and lets Mylo read them |

`make tools-check` prints the live list with each tool's state.

## How a tool is declared

```python
# tools/<name>/tool.py
from tools._framework.spec import Mount, Setting, Stage, Tool

class ScreeningTool(Tool):
    name = "screening"
    summary = "Ranks abstracts so reviewers read the likely includes first."
    depends_on = ("retrieval", "recommendation")
    settings = (Setting("recall_target", "float", 0.95, "Stop at this recall.",
                        env="SCREENING_RECALL_TARGET", django="SCREENING_RECALL_TARGET"),)
    stages = (Stage("run_screening", "rank", "Screening queued reviews…"),)
    mounts = (Mount("api/tools/screening/"),)
    health = "tools.screening.health:check"
    agent = "tools.screening.agent"   # optional: functions Mylo may call
```

A tool that gives the Mylo agent something to read declares `agent`: a module
exporting `FUNCTIONS` (`AgentFunction`s) and `REFS` (`RefKind`s), written with
`tools/_framework/agentspec.py` only. It is imported only while the tool is
loaded, so a disabled tool's functions never reach Mylo, and the contributing
tool never imports the agent (see `tools/files/agent.py`).

The class only *declares*. Anything that needs Django is referenced by a
dotted string and imported once the tool is allowed to load. That is why the
host CLI, the configuration layer and the nightly runner can all read every
tool without starting Django.

Start a new tool with `make new-tool NAME=<name>`, which copies
`_framework/template/`.

## The import script: a tool that cannot load never runs

Before Django starts, `tools/_framework/loader.py` walks the tools in
dependency order and gives each exactly one state:

| State | Meaning |
|---|---|
| `LOADED` | every check passed: installed, routed, scheduled, configured |
| `DISABLED` | switched off in `mycelium.toml` |
| `MISSING` | depends on a tool whose folder does not exist |
| `BLOCKED` | depends on a tool that is not `LOADED` |
| `FAILED` | its own check failed: declaration, cycle, config, missing secret, import error, health check |

The last check is a **probe**. It starts Django in a subprocess with only that
tool and its dependencies installed, imports the tool's modules and runs its
health check. An import error in a tool therefore cannot take the main process
down. Only `LOADED` tools are put in `INSTALLED_APPS`, the URL table, the Beat
schedule and the nightly plan. A tool that does not load contributes nothing,
and neither does anything that depends on it. The nightly run reports every
stage it skipped, with the reason.

The result is cached in `data/tools/` under a fingerprint of the code and the
configuration, so only a change re-probes.

- **Lenient by default.** In production a broken tool is set aside and
  reported, and the rest of the instance runs.
- **Strict mode.** `tools.strict = true` makes any failure stop startup. The
  test suite always runs strict.
- **Core tools.** A tool marked `core = True` is one the platform cannot run
  without: the platform still imports it (it appears in
  `_framework/platform_imports.txt`, and a test holds the two equal). It stops
  startup in every mode if it does not load, and it cannot be disabled.
  Deleting a core tool's folder stops startup with a message naming the missing
  folder. The core tools are probed together, because the platform needs all of
  them at once, and a failure is pinned on the tool whose code raised.

```bash
make tools-check     # every tool's state and reason (in the running stack)
make tools-plan      # tonight's stage order, and what would be skipped
make tools-matrix    # delete-each / break-each: remove or break each tool in turn
```

In the container, `manage.py tools migrations` checks that every loaded tool's
migrations are applied. `manage.py tools uninstall <name> --yes` drops a
non-core tool's tables before you delete its folder; without it, the tables
stay behind unused.

## Configuration: universal, plus a section per tool

Operators edit one file, `mycelium.toml`. The universal sections (`instance`,
`billing`, `limits`, `signup`, `email`, `features`, `nightly`, `tools`) are
defined in `web/backend/config/instance.py`. Each installed tool adds its own
section, with keys declared in its `tool.py`:

```toml
[tools]
strict = false            # any tool failure stops startup
disabled = []             # keep tools off without deleting them

[tools.screening]
enabled = true
recall_target = 0.9       # env SCREENING_RECALL_TARGET wins over this
```

Values merge in the same order as every other key: the tool's default, then
the deployment profile, then `mycelium.toml`, then the environment variable.

- **Where a tool's values appear.** A tool's values are published under the
  Django setting name it declares (`django=`), so `settings.X` and
  `override_settings(X=…)` keep working. They are published only while the tool
  is loaded.
- **Bad values.** A bad value or an unknown key in a tool's section fails that
  tool, not the instance.
- **Sections for deleted tools.** A section for a tool that is not installed
  is only a warning, so deleting a folder never stops startup.
- **Secrets.** Secrets stay in `.env`. A tool lists the names it needs in
  `secrets`, and a missing one fails the tool with a reason that names it.

## The rules that keep a tool removable

These are checked by `tools/_framework/tests/test_boundaries.py` on every
`make test`:

1. `tool.py` imports only the standard library and `tools._framework.spec`.
   A tool's `__init__.py` imports nothing.
2. A tool imports another tool only if it lists it in `depends_on`, and then
   only the modules that tool `exports` (by default `read`, `service`,
   `events`). A tool may use the platform (`apps.*`) freely: it is the host.
3. **The platform imports no tool.** Every platform import of a tool that
   remains while code is being moved out is listed in
   `_framework/platform_imports.txt`. That list is a ratchet: the test fails on
   a new import and on an entry that no longer matches anything, so it only
   ever shrinks.
4. A model's foreign keys point only into the platform, its own tool, or a
   declared dependency.

## Verifying a change

- `make test` runs the platform's tests and every tool's tests in strict mode.
  It includes:
  - `test_golden.py`, which fails if the URL table, Celery task names, Beat
    schedule, management commands, database tables, nightly stage order or
    configuration keys change. To accept an intended change, re-record the
    golden files with
    `uv run --no-sync --project web/backend python tools/_framework/golden.py write`
    and commit the diff.
  - `test_delete_matrix.py`, which removes and breaks each tool in turn. This
    is the same check as `make tools-matrix`.
  - `test_docs.py`, which fails if a living doc cites a repository path that
    no longer exists, if a tool has no README, repo-map section or row in the
    table above, or if a skill lacks one of its two entrypoints.
- A change to ranking code also needs the evaluation-harness parity run
  described in `docs/research/experiments/EXP-2026-11-003-tools-refactor-parity/`.

## Running one tool's tests

```bash
uv run --directory web/backend pytest -c pyproject.toml ../../tools/<name>
```

The `-c pyproject.toml` matters: given a path outside `web/backend`, pytest
would otherwise not find its configuration, and with it the Django settings.
