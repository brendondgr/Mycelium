# Modular Tools — Plan

**Status:** discussion draft, nothing implemented.
**Correlation ID:** `20261108-modular-tools`
**Owner:** Brendon (product direction). This is a working document: delete it
once the work ships and record the outcome in `docs/changelog.md` and the
canonical docs listed under [Documentation](#documentation-re-registration).

## Decisions taken since the draft (2026-11-08)

These supersede the matching parts of the decisions below.

- **Location.** Tools live in `tools/` at the repository root (not
  `web/tools/`), one folder each, with `tools/README.md` as the guide.
- **Delivery becomes a tool** (Phase 4 is in scope).
- **URLs stay exactly as they are.** No `/app/t/<tool>/` route and no frontend
  move in this refactor. Tools mount their API routes at the prefix and
  position they had (golden URL table). Per-tool URLs are a later discussion.
- **Tools may use the platform freely.** D7 rule 2's fixed registry of platform
  doors is dropped: the platform is the host. The strict rules are tool→tool
  (only declared dependencies, only their `exports`) and platform→tool (a
  shrinking allowlist).
- **A bad value in a tool's section fails that tool, not the instance** (D4
  said `ConfigError`). This is consistent with "a tool that cannot load does
  not run".
- **Retrieval keeps the `content` app label.** `collab` and `knowledge`
  (platform) have foreign keys to `ContentItem`, and their migration history
  depends on `content` migrations. The retrieval tool therefore owns the
  `content` label and its whole migration history, and no table is renamed.
  Recommendation and delivery models leave it by state-only migrations, under
  their own labels, with their `db_table` unchanged.
- **Existing settings keep their names.** A tool's `Setting` carries its old
  environment variable (`env=`) and Django name (`django=`), so deployments,
  call sites and `override_settings` are unchanged.
- **The probe does not touch the database**, so a database outage at boot
  cannot disable tools. Migration state is checked by
  `manage.py tools migrations` instead.

## Objective

Make every research tool a **self-contained module**: one folder holds all of a
tool's code (models, migrations, API, jobs, nightly stages, config, UI, tests,
docs). The tool is declared by one Python class, and the platform loads it by
discovery, not by hand-edited wiring. Deleting a leaf tool's folder removes it
completely. A tool that cannot load never runs — and neither does anything that
depends on it — while the rest of the instance keeps working.

The first two tools are the layers Mycelium already has, pulled apart:

1. **Retrieval** — the grounded corpus: sources, scrapers and collectors, dedup,
   the embedder, `ContentItem`, prune and liveness. It knows nothing about users.
2. **Recommendation** — ranking and filtering against user, lab and department
   profiles: the ranking stack, `RelevanceScore`, clustering, admission, slates,
   matchers.

The **platform** (identity, labs, departments, profiles, billing, integrations,
the app shell) hosts them. Future tools — the stance engine, review screening,
the expertise finder, and the others in
[`goals.md`](../../goals.md#tools-on-the-grounding-layer) — are built on all
three.

## What is in the way today

- **A feature lives in about eight places.** Collaboration search is spread
  across `INSTALLED_APPS`, `config/urls.py`, the Beat schedule in `settings.py`,
  a `features.*` key in `config/instance.py`, `CONTAINER_STAGES` in
  `ops/nightly/manual_all.py`, `components/portal/collab/`, `lib/portal/collab/`,
  `nav.ts` and a `(workspace)/` route folder. Removing it means finding all of
  them by hand.
- **Retrieval and recommendation import each other.** `ContentItem` is defined
  in `apps/content`, but `apps/scraper` writes it (6 modules import content,
  including `embed_texts`, `rebuild_deadlines_for` and `liveness`). `apps/content`
  imports the scraper's embedder, dedup, `scan` and `ScanWindow` (7 modules).
- **`apps/content` is about 75k lines across 146 modules.** It mixes three jobs:
  corpus helpers, the ranking stack, and delivery (briefings, reports, weekly,
  announcements, reminders, notifications, Discord).
- **Other code reaches into its internals.** `collab` (8 modules), `knowledge`
  (3), `accounts` (3), `research` (2), `eval/` (9), `mylo/` (4) and `ops/` (2) all
  import `apps.content` modules directly.

What already works, and this plan generalizes:

- **Two-door modules with an AST lock:** `knowledge/read.py` + `service.py`, and
  `ambient/read.py` + `service.py`, enforced by `test_import_boundary.py`.
- **Ranking protocols:** `Retrievable` and `VectorIndex` in
  `apps/content/protocols.py`, which let the ranking stack run without a
  database.
- **Optional features as config:** the `billing.mode` and `features.*` keys in
  `instance.py`.

## The end state

```text
web/tools/
├── _framework/                 # Tool base class, loader, preflight, config, events,
│   │                           # boundary tests, UI codegen. Not a tool itself.
│   └── template/               # what `make new-tool NAME=x` copies
├── retrieval/
│   ├── tool.py                 # class RetrievalTool(Tool) — declaration only
│   ├── read.py                 # the read door
│   ├── service.py              # the write door
│   ├── events.py               # events this tool publishes
│   ├── models.py  migrations/  management/  tasks.py  urls.py  views.py
│   ├── sources/  collect/  fellowships/  eligibility/  embedding.py  …
│   ├── host/                   # host-side runners (the Playwright fellowship scrape)
│   ├── ui/                     # index.ts (routes, nav) + pages and components
│   ├── tests/
│   └── README.md               # what it owns, its doors, its config keys
├── recommendation/             # same shape
└── <future tools>/

                 ┌──────────────── future tools ────────────────┐
                 │ stance · screening · expertise · …           │
                 └──────────────┬───────────────────────────────┘
                                │ read/service doors only
         ┌──────────────────────▼──────────────────────┐
         │ recommendation  (depends_on: retrieval)     │
         └──────────────────────┬──────────────────────┘
         ┌──────────────────────▼──────────────────────┐
         │ retrieval       (depends_on: —)             │
         └──────────────────────┬──────────────────────┘
   ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─▼─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
   platform: apps/core · accounts · research · billing · integrations ·
             knowledge · ambient · collab · content (delivery) · app shell
```

Tools may import the platform's doors. The platform never imports a tool, apart
from the framework loader. Phases 1–3 relax that rule for `apps/content`'s
delivery code under a shrinking allowlist; see [D8](#d8-core-tools-and-leaf-tools).

## Decisions

### D1. Location and naming

- Tools live in **`web/tools/<name>/`**. The repo rule keeps implementation
  under `web/`, and a tool has both backend and frontend code. `web/` is already
  the Turbopack root (`turbopack.root` in `next.config.ts`), and compose mounts
  the whole repository, so the backend container already sees the folder.
- `web/tools/` is the Python package `tools`; `settings.py` puts `web/` on
  `sys.path` (`MYCELIUM_TOOLS_DIR` overrides the location for tests). Each tool
  is a Django app at `tools.<name>` with app label `<name>`.
- Folders whose names start with `_` are never loaded (`_framework`, scratch
  copies).
- Names are `[a-z][a-z0-9_]*` and must not clash with a platform app label. The
  loader refuses a clash.

### D2. The Tool class — `tool.py` declares, other modules act

```python
# web/tools/recommendation/tool.py
from tools._framework.spec import Tool, Setting, Stage, Beat, Nav, Event

class RecommendationTool(Tool):
    name = "recommendation"
    version = "1"
    summary = "Ranks the corpus for every person, lab and department."
    depends_on = ("retrieval",)
    platform = ("accounts.read", "billing.entitlements", "core.llm")  # platform doors it uses
    settings = (
        Setting("slate_depth.papers", "int", 25, "Papers per theme in a slate."),
        Setting("rerank", "bool", False, "Cross-encoder rerank.", env="RERANK_ENABLED"),
    )
    secrets = ()                                   # .env names: required ones block loading
    stages = (Stage("run_daily_suggestions", phase="rank"),
              Stage("run_daily_opportunities", phase="rank", args=("--no-prune",),
                    after=("run_daily_suggestions",)))
    beat = (Beat("recompute_project_profiles", "tools.recommendation.tasks.recompute", hour=4),)
    subscribes = {"retrieval.items_ingested": "tools.recommendation.hooks:on_ingested"}
    api_prefix = "api/"                            # legacy mount; new tools use api/tools/<name>/
    health = "tools.recommendation.health:check"   # import-time self-test, no DB writes
```

- **`tool.py` may import only the standard library and
  `tools._framework.spec`** (AST-enforced). Behaviour is referenced as dotted
  strings. That keeps the class readable by stdlib-only code: `instance.py`, the
  host CLI `ops/mycelium`, and the nightly runner on the host. All of them read
  the same declarations without starting Django. The class is the single source
  of truth, so there is no separate manifest file to drift.
- Each tool also has a two-line `apps.py`, scaffolded by the template, that
  binds a `ToolAppConfig` to the class, so Django sees an ordinary app with
  `label = name`.
- A tool owns its migrations. A foreign key to another tool's model is allowed
  only into a declared dependency (checked in a test against `_meta`).

### D3. Doors and events

- **`read.py`** — every function another tool or the platform may call to read.
  Returns plain views (dataclasses or the `Retrievable` protocol), never
  querysets that leak model internals. **`service.py`** — every write.
  **`events.py`** — the events it publishes.
- **Events replace the reverse calls that cause today's cycle.** Retrieval
  publishes `items_ingested(ids)` and `items_pruned(ids)` and calls nobody.
  Whatever used to be called directly (deadline projection, rescoring hooks)
  subscribes instead. The bus (`tools._framework.events`) is in-process and
  synchronous inside the publisher's transaction (`on_commit`). It delivers only
  to LOADED subscribers, and a failing subscriber is logged and reported without
  rolling back the publisher.
- A platform module may subscribe to tool events through
  `tools._framework.events.subscribe()`, declared in the platform's
  `apps.py.ready()`. This lets delivery react to ingestion without importing
  retrieval.

### D4. Configuration — one universal file, a section per tool

Operators keep editing one file, `mycelium.toml`. The existing four-layer merge
(defaults → profile → file → env) is unchanged and extended:

```toml
[tools]                       # universal tool policy
strict = false                # true: any FAILED tool stops startup (CI and tests set it)
disabled = []                 # tools to keep off without deleting them

[tools.retrieval]             # one section per tool; keys come from the Tool class
enabled = true
scan_window_days = 3

[tools.recommendation]
slate_depth.papers = 25
rerank = false
```

- **Universal keys** (`instance`, `billing`, `limits`, `signup`, `email`,
  `nightly`, and the new `tools`) stay in `config/instance.py`. A tool reads them
  read-only via `tools._framework.config.platform("nightly.llm_concurrency")`.
- **Per-tool keys** are declared in the tool's class with the same `Setting`
  dataclass and read via `self.config` / `config.of("recommendation")`. They are
  never re-exported as bare Django settings, so a tool's config dies with its
  folder.
- `instance.py` discovers tool settings by importing each `tool.py` (stdlib-only
  per D2). An unknown key inside a **present** tool's section is still a
  `ConfigError`. A section for a tool that is **not installed** is a warning, not
  an error, so deleting a folder never bricks startup.
- Profiles may set tool keys (`"tools.screening.enabled": True` in
  `institution`). Keys for absent tools are ignored.
- Moved settings keep their env names through `env=`, so existing `.env` files
  and deployments behave the same. `ops/mycelium config explain` lists tool
  sections, and `config set tools.retrieval.scan_window_days 5` works like any
  other key.
- A tool may add cross-key checks (`problems()`), and `Instance.problems()`
  includes them. Secrets stay in `.env`. A tool lists their names in `secrets`,
  and a missing required one blocks the tool with a clear reason instead of
  failing at 03:00.

### D5. The import script — preflight and load states

`manage.py tools check` (also `ops/mycelium tools check` and
`make tools-check`) is the **import script**. It walks tools in dependency order
and gives each exactly one state:

| State | Meaning | Runs? |
|---|---|---|
| `LOADED` | Every check passed | Yes |
| `DISABLED` | Switched off in config | No |
| `MISSING` | A dependency's folder does not exist | No |
| `BLOCKED` | A dependency is not `LOADED` (the report names which, and why) | No |
| `FAILED` | Its own check failed: bad declaration, dependency cycle, invalid config, missing required secret, import error, or failed `health` | No |

The checks, in order:

1. Discover folders.
2. Validate each `tool.py` against the spec.
3. Topologically sort; a cycle fails every tool in it.
4. Resolve config.
5. Check secrets.
6. **Import probe:** in a subprocess with `INSTALLED_APPS` = platform + this
   tool's dependency closure, run `django.setup()`, import every door, run
   `health`, and check that the tool's migrations are consistent with the
   database (`migrate --check` scoped to its label). Tools are probed only after
   all their dependencies are `LOADED`; dependents of a non-`LOADED` tool become
   `BLOCKED` without probing.

The result is written to `data/tools/load-report.json` with a **fingerprint**
(hash of every tool folder's source plus the resolved config).

**How the report gates every process:**

- **Django** (`settings.py`): only `LOADED` tools enter `INSTALLED_APPS`, URL
  mounts and the Beat schedule. If the report is missing or its fingerprint is
  stale, settings runs the preflight first (seconds, cached). So no process can
  boot with an unchecked tool.
- **The compose `backend` command** becomes `tools check → migrate → runserver`.
  The worker and Beat read the same report.
- **The nightly run** (`manual_all.py`) runs `tools check` first, builds its
  stage plan from `LOADED` tools only, and reports every skipped stage with its
  reason to the run-state file and Mylo's Discord error report. A skip is never
  silent. `manual_all.py --plan` prints the plan and the load states without
  running anything.
- **The frontend** asks `GET /api/tools/` for the loaded tools. Nav entries
  appear only for `LOADED` tools, and a tool route that is not loaded renders
  the shared "not available on this instance" state.
- **Strict mode** (`tools.strict = true`, set by `make test` and CI): any
  `FAILED` tool exits non-zero. Production defaults to lenient: a broken tool is
  isolated and reported, and the rest of the instance runs.
- `manage.py tools uninstall <name>` migrates the tool to zero (after refusing
  if any installed tool depends on it). Without it, deleting a folder leaves the
  tool's tables in Postgres, unused.

### D6. How a loaded tool is wired, with no hand edits

| Surface | Today | With tools |
|---|---|---|
| Django app | `INSTALLED_APPS` list | Loader appends `LOADED` tools in dependency order |
| API | `config/urls.py` include | `api_prefix` (legacy) or `api/tools/<name>/` |
| Celery tasks / Beat | `settings.py` dict | `Tool.beat`; tasks autodiscovered from `tools.<name>.tasks` |
| Nightly stages | `CONTAINER_STAGES` list | `Tool.stages` with `phase` + `after`/`before`. The platform declares its own stages the same way |
| Host stages | `ops/scrapers/…` | `web/tools/<name>/host/`, declared as `Stage(host=True)` |
| Config | `instance.py` key + `settings.py` re-export | `Tool.settings` |
| UI routes | folder under `(workspace)/` | `ui/index.ts`, served by one catch-all route `(workspace)/t/[tool]/[[...slug]]` |
| Nav | `nav.ts` | `ui/index.ts` `nav`, shown when `LOADED` |
| Old URLs | — | `ui/index.ts` `aliases` become Next redirects, so emailed and bookmarked links keep working |
| Tests | `apps/<x>/tests` | `web/tools/<name>/tests`, collected by `make test` |

**Nightly phases**, in order: `collect`, `resolve`, `rank`, `remind`, `prune`,
`alert`, `announce`, `brief`, `deliver`, `weekly`. They reproduce today's
`CONTAINER_STAGES` order exactly, including the reminder-before-prune rule,
which becomes an explicit `after=`. A golden test (Phase 0) holds the assembled
plan identical to today's list.

**Frontend build.** `web/tools/_framework/ui/codegen.mjs` runs in `predev` and
`prebuild`. It globs `web/tools/*/ui/index.ts` and writes the gitignored
`web/app/src/generated/tools.ts` with static `next/dynamic` imports, since the
bundler needs static paths. Deleting a folder removes the tool from the next
build. A `@tools/*` tsconfig alias points at `../tools/*`.

### D7. Boundary rules, enforced by AST and lint

One generalized test, `web/tools/_framework/tests/test_boundaries.py`, replaces
the per-app patterns and runs in `make test`:

1. `tool.py` imports only the stdlib and `tools._framework.spec`.
2. A tool imports only: the stdlib and third-party packages; `tools._framework`;
   its own package; the `read` / `service` / `events` modules of tools in its
   `depends_on`; and the platform doors it lists in `platform` (a fixed
   registry: `core.llm`, `core.db`, `core.mail`, `accounts.read` (new, built over
   the interests contract), `billing.entitlements`,
   `integrations.services.outbox`, `knowledge.read`, …).
3. **Nothing outside a tool imports its internals** — only its doors.
4. **The platform imports no tool**, except the framework loader and the
   interim allowlist (D8).
5. Frontend: an ESLint `no-restricted-imports` rule limits `web/tools/*/ui` to
   its own folder, `@/components/ui`, `@/components/portal/primitives` and
   `@/lib/portal/client`. The platform UI may not import `@tools/*` except the
   generated registry.

The existing `knowledge`, `ambient` and `integrations` boundary tests stay; they
guard platform-internal rules.

### D8. Core tools and leaf tools

Deleting a **leaf** tool's folder is complete: preflight, Django, the nightly
plan and the UI all drop it, and nothing else breaks.

Retrieval and recommendation are **foundations**. Until delivery is extracted,
the platform still depends on them. Today's `content` models (`SavedOpportunity`,
`ContentDeadline`, `CollectionItem`, `ReminderSubscription`, `Announcement`, …)
hold foreign keys to `ContentItem`, and the briefings read slates. So:

- Both are declared `core = True`. A core tool that is not `LOADED` stops
  startup in every mode, because the platform cannot run without it. They are
  modular in structure, config, doors and tests, but not removable yet.
- The platform's remaining imports of them go through doors only. Each one is
  listed, by file, in `_framework/interim_platform_imports.py`, and the boundary
  test enforces it as a **ratchet**: the list may shrink, never grow.
- Making delivery a tool (Phase 4) empties the list. After that, `core` is
  dropped and the platform imports no tool at all.

## Phases

Each phase lands as its own series of commits. The full suite must pass at the
end of every phase. A phase that moves code changes **no behaviour**: the
golden files from Phase 0 must still match.

### Phase 0 — Baselines (no code moves)

Capture what "unchanged" means before anything moves:

- **URL resolver snapshot:** every pattern, name and view dotted path, as a
  golden file.
- **Nightly stage plan:** today's `CONTAINER_STAGES` plus the host stages, in
  order, as a golden file.
- **Beat schedule:** names, tasks and crontabs, as a golden file.
- **`config explain` output:** every key, default and env name, as a golden file.
- **Schema dump:** `pg_dump --schema-only` of a migrated compose database, saved
  to `data/tools-baseline/` (gitignored), plus `migrate --plan`.
- **Test results:** the backend suite's pass/fail list in JUnit format. The known
  pre-fails are recorded, not fixed: the synthesize résumé-merge test, the
  high-signal date flake, and the `collect_ingest` prune tests.
- **Eval run:** the eval harness on the production config, giving the
  byte-for-byte run files the ranking must reproduce. This is recorded as an
  experiment (`make new-experiment SLUG=tools-refactor-parity`), as
  `CLAUDE.md` requires.
- **Import graph:** a module-level graph of `apps/content` and `apps/scraper`.
  It decides the split into retrieval, recommendation and delivery so that no
  cycle crosses tool lines. The module lists in Phases 2 and 3 are a first cut;
  this graph is the authority.

*Validation:* golden files committed under `web/tools/_framework/tests/golden/`;
`make validate-research` passes.

### Phase 1 — The framework, proven on fixtures

Build the framework with no production code moved:

- `_framework/`: `spec`, the loader, preflight, config, events and UI codegen.
- `manage.py tools check|uninstall`, `ops/mycelium tools`, `make tools-check`,
  `make new-tool NAME=`.
- The `[tools]` keys in `instance.py`.
- The catch-all UI route and `GET /api/tools/`.
- The phase-based nightly planner. Platform stages are declared through the same
  `Stage` type; the planner reproduces the Phase 0 golden plan exactly.
- The generalized boundary test.

Fixture tools under `_framework/tests/fixtures/` cover every state:

- `ok_leaf`
- `ok_dependent` (depends on `ok_leaf`)
- `broken_import`
- `broken_health`
- `bad_config`
- `missing_secret`
- `cycle_a` / `cycle_b`
- `depends_on_absent`
- `ui_only`
- `forbidden_import` (must fail the boundary test)

*Validation:* `make test` (framework tests plus the full suite, unchanged);
`make tools-check` shows no tools; the nightly `--plan` output equals the golden
file; `next build` passes with a tool scaffolded by `make new-tool` and again
after it is deleted; the browser shows the scaffolded tool's nav entry and route,
and the "not available" state when it is disabled.

### Phase 2 — Extract retrieval

- **Move** `apps/scraper/*` and the corpus pieces of `apps/content` into
  `web/tools/retrieval/`: `ContentItem`, `embeddings.py`, `dedupe.py`,
  `liveness.py`, `query_embedding.py`, and the corpus half of `opportunities.py`.
  The final list comes from the Phase 0 graph. The host Playwright scrape moves
  from `ops/scrapers/` to `web/tools/retrieval/host/`, and the root
  `pyproject.toml` runner keeps working.
- **Move `ContentItem` without copying data.** `db_table = "content_contentitem"`
  is kept. `SeparateDatabaseAndState` migrations in `content` and `retrieval`
  move only Django's state, and state-only `AlterField`s repoint every foreign
  key. A data migration renames the `django_content_type` and `auth_permission`
  rows. The new initial migration depends on `core.0001_enable_pgvector`. The
  `search_vector` trigger and the trigram index are untouched, since the table
  name is unchanged.
- **Break the cycle.** Retrieval stops calling `rebuild_deadlines_for` and
  `liveness` in content. It publishes `items_ingested` / `items_pruned`, and
  content subscribes. Content, `research/views.py` and `collab` import only
  `tools.retrieval.read` / `service`, and each of those files goes into the
  interim allowlist.
- **Config.** Scraper and collector settings become `[tools.retrieval]` keys
  with their old env names.
- **Remove** `apps.scraper` from `INSTALLED_APPS`. No re-export shims are kept;
  the boundary test fails on any import of `apps.scraper`.

*Validation:*
- Schema diff against the Phase 0 dump is empty, apart from the
  `django_content_type` rows.
- Row counts are unchanged.
- `makemigrations --check` is clean.
- `migrate` from scratch and from the baseline both succeed.
- The URL, Beat, stage-plan and config-explain golden files match.
- The eval run files are byte-identical, recorded in the parity experiment.
- `collect_opportunities --dry-run` and a fellowship ingest on fixtures behave
  as before.
- The full suite matches the Phase 0 pass list.

### Phase 3 — Extract recommendation

- **Move** the ranking stack and its models into `web/tools/recommendation/`:
  `pipeline`, `retrieval` (the ranking-side one), `lexical`, `fusion`,
  `ranking`, `reranking`, `typesafe_rerank`, `clustering`, `cluster_fit`,
  `admission`, `slates`, `top_feed`, `matchers/`, `suggest`, `refitting`,
  `onboarding_match`, `interests_query`, `member_fit`, `lab_fit`, `dept_level`,
  `fellowship_bands`, the scoring half of `opportunities`, `opportunity_llm`,
  `comprehension`, `verdicts`, `search` / `search_service`, `protocols`, and
  `RelevanceScore`. The final cut comes from the Phase 0 graph.
- **Profiles through a door.** Recommendation reads user, lab and department
  profiles only through a new `apps/accounts/read.py` (interests, clusters,
  areas, targets). That door is a platform door, so the recommendation tool never
  imports `accounts` models.
- **Eval and ops.** `eval/` imports `tools.recommendation.read` plus a declared
  offline door (`tools.recommendation.offline`: `Retrievable`, `VectorIndex`, the
  pure ranking functions). The eval harness is the second consumer the boundary
  test allows. `ops/` and `mylo/` imports move to doors.
- **UI.** The feed pages (research papers, grants, conferences, fellowships,
  suggested, search) move into `recommendation/ui/`. Their old URLs are kept as
  `aliases`, because daily reports and emails link to them.

*Validation:* the same as Phase 2, plus the eval parity run again (the ranking
code moved, so `global.md` requires it). The nightly run executes end to end on
the compose stack (`make nightly`), and its analytics match a run on the Phase 0
commit with the same corpus snapshot. The browser checks every moved page and
every alias redirect.

### Phase 4 — Delivery as a tool (outline; a follow-on plan)

Move briefings, reports, weekly, announcements, reminders, notifications and the
Discord digest producers out of `apps/content` into `web/tools/delivery/`
(`depends_on: recommendation`). This empties the interim allowlist and drops
`core = True` from retrieval and recommendation. After this phase, the whole
stack can be removed tool by tool. Planned in detail once Phase 3 has landed.

## Verification

Each item below runs in `make test` unless it says otherwise.

| Check | What it proves |
|---|---|
| Framework unit tests | Discovery, spec validation, topological sort and cycle detection, the state cascade (`FAILED` → dependents `BLOCKED`), config merge (tool keys, absent-tool warning, unknown-key error, env names, profile keys), strict mode, fingerprint invalidation, the event bus (delivery to `LOADED` only, failure isolation) |
| Fixture states | Each fixture tool ends in exactly its expected state, and the server still boots |
| **Delete-each matrix** (`make tools-delete-matrix`) | For each tool, copies `web/tools/` without it into a temp dir and points `MYCELIUM_TOOLS_DIR` there. Then: the preflight states are as predicted, `manage.py check` passes for a leaf (for a core tool it refuses with the expected message), the nightly `--plan` drops exactly that tool's stages, codegen drops its routes, and `config explain` warns about its section |
| **Break-each matrix** | Injects an import error into each tool in turn: it is `FAILED`, its dependents are `BLOCKED`, a leaf's failure leaves the platform up, and the nightly plan skips and reports it |
| Boundary tests | D7 rules 1–5, the interim-allowlist ratchet, and foreign keys only into declared dependencies |
| Golden files | URLs, Beat, the nightly plan, and `config explain` are identical to Phase 0 except for listed, intended changes |
| Migration checks | `makemigrations --check`; `migrate` from scratch and from the baseline on compose Postgres; a schema diff against the baseline (pgvector tests need the compose Postgres, not SQLite) |
| Eval parity (Phases 2–3) | Byte-identical run files, recorded under `docs/research/experiments/` |
| Frontend | `next build` with and without a scaffolded tool; ESLint boundary rule; browser check of moved pages, aliases and the "not available" state |
| Docs check (`make check-docs`, new) | Every repo path cited in `CLAUDE.md`, `docs/*.md` and `docs/skills/*.md` exists (experiment folders excluded: they are historical records); every tool has a `README.md` and a `repo-map.md` row; every skill has both entrypoints |

## Documentation re-registration

Every phase updates the docs it makes wrong, in the same commit. The full
surface:

- **`CLAUDE.md`**
  - Navigating the code: tools live in `web/tools/`, and new non-platform
    features start from `make new-tool`.
  - Configuration: per-tool keys are declared in `tool.py`, not
    `config/instance.py`.
- **`docs/skills/tools.md` (new)**
  - How to build a tool: the class, doors, events, config, stages, UI, tests,
    and the delete and break checks.
  - Its two entrypoints: `.agents/skills/tools/` and `.claude/skills/tools/`.
  - A row in `docs/skills/index.md`.
- **`docs/skills/global.md`**
  - The grounding-layer default names the two foundation tools.
  - The ranking-change and nightly-audit rules point at the new paths and at
    stage declarations instead of `CONTAINER_STAGES`.
- **`docs/skills/repo-structure.md`** — layout, the service-boundary list, the
  Django app list, and the tool rules.
- **`docs/skills/planner.md`** — non-negotiable paths (`top_feed.py`), plus a new
  check: "which tool owns this, and which doors does it use?"
- **`docs/skills/configure.md`** — the `[tools]` and `[tools.<name>]` sections,
  and how to enable or disable a tool.
- **`docs/skills/website-architecture.md`** — the tool UI route and the alias
  rule.
- **`docs/architecture.md`**
  - Repository layout.
  - The backend app boundaries table: the `scraper` row goes, the `content` row
    shrinks, and a new Tools section is added.
  - The ranking-stack seams.
  - The nightly-run section: phases, preflight, and skipped-stage reporting.
- **`docs/repo-map.md`**
  - A Tools section, with every moved row repointed.
  - A **moved-paths table** (old path → new path), so experiment records that
    cite old paths still resolve. Records under `docs/research/experiments/`
    are never rewritten.
- **`docs/api-contract.md`** — `GET /api/tools/`; moved endpoints keep their
  paths, and their owner is noted.
- **`docs/evaluation.md`** — the protocols location and the offline door.
- **`docs/discord-integration.md`**, **`docs/research-audit.md`**,
  **`docs/research/CLAIMS.md`**, **`OPEN_QUESTIONS.md`** and
  **`literature/SYNTHESIS.md`** — repoint living path references.
- **`docs/goals.md`** — "Tools on the grounding layer" links to the tool skill.
  The framework moves to Built when shipped.
- **`docs/plans/*`** — repoint paths in plans that are still live.
- **`README.md`** and **`CONTRIBUTING.md`** — how to add a tool.
- **`Makefile`** help and `ops/mycelium` help — the new targets and subcommands.
- **Agent memory** — memory notes that cite moved paths are updated after each
  phase.

## Open questions

1. **Delivery.** Should delivery become a tool (Phase 4)? This plan assumes
   yes, as a follow-on plan, since it is what makes the foundations removable.
2. **Production failure mode.** Lenient (a broken leaf is isolated and reported)
   is the proposed default; strict is for CI and tests. Should production also
   be strict?
3. **UI URLs.** Should new tool pages live under `/app/t/<tool>/…` (proposed),
   or should a tool be able to claim a top-level workspace URL? Moved pages keep
   their old URLs as aliases either way.
4. **Location.** `web/tools/` (proposed, matching the repo rule) or a root
   `tools/`.

## Exclusions

- No third-party or pip-installed tools, marketplace, or runtime hot-loading. A
  restart picks up an added or removed tool.
- No per-tool databases or services. Tools share Postgres and Redis, and each
  owns its tables.
- No ranking, scoring or product behaviour changes. Parity is the acceptance
  bar for Phases 2–3.
- `accounts`, `billing`, `integrations`, `knowledge`, `ambient` and `collab` stay
  platform apps. Whether `collab` (a natural leaf tool) becomes a tool is
  decided after Phase 3.
