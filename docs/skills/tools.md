# Tools Skill

Use this skill when adding, changing, moving code into, disabling or removing a
tool under `tools/`, or when a tool will not load.

The reference is [`../../tools/README.md`](../../tools/README.md): the folder
layout, the `Tool` declaration, the load states, configuration, and the import
rules. This skill holds the rules an agent must follow on top of it.

## Core Rules

- **Platform or tool?** A feature that is a research capability built on the
  lab's context (retrieval, recommendation, delivery, screening, stance,
  expertise…) is a tool. Identity, organizations, profiles, projects, billing,
  integrations and the app shell are the platform (`web/backend/apps/`).
- **Start from the template:** `make new-tool NAME=<name>`. Never hand-wire a
  tool into `INSTALLED_APPS`, `config/urls.py`, the Beat schedule,
  `ops/nightly/manual_all.py` or `config/instance.py`; declare it in `tool.py`
  and the framework does the wiring.
- **`tool.py` declares, other modules act.** It imports only the standard
  library and `tools._framework.spec`; behaviour is a dotted string.
- **Doors.** Other code reads a tool through its `exports` (default `read`,
  `service`, `events`). A tool imports another tool only if it lists it in
  `depends_on`. The platform imports no tool. Any remaining platform import is
  listed in `tools/_framework/platform_imports.txt`, and that list may only
  shrink.
- **Events instead of reverse calls.** A foundation tool publishes events
  (`tools._framework.events`); whatever must react subscribes. Never make a
  tool call into something built on top of it.
- **Configuration.** A setting a tool owns is a `Setting` in its `tool.py`,
  with `env=` set to its existing environment-variable name (so deployments do
  not change) and `django=` set to its existing Django setting name (so call
  sites and `override_settings` do not change). Universal, operator-wide
  policy stays in `config/instance.py`.
- **URLs stay put.** A tool that takes over existing routes mounts them at the
  same prefix and position (`Mount(prefix, after=…)`). The golden URL table
  must not change. New URL schemes for tools are a product decision still to
  be made; do not invent one.
- **Migrations move with models.** A model that changes tool keeps its
  `db_table`; move it with `SeparateDatabaseAndState`, state only, and the
  database must not change (schema diff against a migrated baseline).

## Validation

- `make test`: platform and tool tests run strict, and include the golden
  snapshots, the boundary rules and the delete-each/break-each matrix.
- `make tools-check` against the running stack: every tool `LOADED`.
- After moving ranking code: the parity run in
  `docs/research/experiments/EXP-2026-11-003-tools-refactor-parity/`.
- After adding, moving or removing a tool: update `tools/README.md`'s
  installed-tools table, `docs/repo-map.md`, and the tool's own `README.md`.
