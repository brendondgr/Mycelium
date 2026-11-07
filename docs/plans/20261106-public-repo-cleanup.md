# Public repository cleanup and repositioning

**Objective.** Make the repository something a stranger (or their agent) can
clone and get running from one command. The root holds only the files a
reader expects there, and everything else lives in a folder named for what it
does. Along the way, reposition Mycelium as an **open-source academic
research assistant any lab can run on its own computers**, and rewrite the
README with the README skill (`/home/bdgr/Projects/bdgrClaudeSkills/README-Skill`).

Status: **proposed, not started.** Delete this plan once it ships (see
`docs/skills/planner.md`).

---

## 1. Where the root stands today

27 tracked files and 10 folders sit at the root. What each one is, and what
happens to it:

| Root item | What it is | Plan |
|---|---|---|
| `README.md`, `LICENSE`, `NOTICE`, `CONTRIBUTING.md`, `CLAUDE.md`, `.gitignore` | Expected root files | **Keep** |
| `compose.yaml` | The whole stack; every service bind-mounts `.:/app` | **Keep** (`docker compose` finds it at the root, and every relative path depends on it) |
| `package.json` | npm scripts that delegate into `web/` | **Keep** |
| `pyproject.toml`, `uv.lock`, `.python-version` | Host runner env for the nightly scripts and `mylo/` | **Keep** (moving it would change every `uv run` and the systemd `.venv` path for no visible gain) |
| `.env.example`, `.env-mylo.example` | Config templates | **Keep**, and reorder (Phase 4) |
| `Makefile` | Research-record targets only | **Keep**, and grow into the single front door (Phase 4) |
| `package-lock.json` | Empty lockfile; the root has no npm deps | **Delete**, gitignore `/package-lock.json` |
| `main.py` | `uv init` hello-world stub, referenced by nothing | **Delete** |
| `run.py` | A second Compose wrapper that duplicates `scripts/mycelium` | **Delete**; one stack manager is enough |
| `manual_all.py`, `manual_mylo.py` | Nightly run and on-demand re-score | **Move** → `ops/nightly/` |
| `utils/manual/` | Per-stage runners those two import via `sys.path` | **Move** → `ops/nightly/` (they belong with their caller) |
| `scrape_fellowships.py` | Host Playwright fellowship scrape | **Move** → `ops/scrapers/` |
| `utils/grants/` | Grants.gov / NIH / NSF API clients and CSV writers. Dormant, but `research-audit.md` calls it the most reusable dormant asset | **Move** → `ops/scrapers/grants/` |
| `create_admin.py` | First-admin bootstrap | **Move** → `ops/setup/` |
| `loadtest.py`, `loadtest_interests.py` | Onboarding load test | **Move** → `ops/loadtest/`; results go to `data/loadtest/` (gitignored) |
| `scripts/mycelium` | Stack manager CLI (systemd-aware) | **Move** → `ops/mycelium` |
| `scripts/research/` | Research-record tooling behind `make new-experiment` etc. | **Move** → `ops/research/` |
| `scripts/exp012_chain.sh` | One-off chain script for EXP-2026-08-012, with a hardcoded `/home/bdgr` path | **Move** into that experiment's `code/` folder (a record, not deleted) |
| `mycelium.service`, `mycelium-update.service`, `mylo-bot.service`, `mylo-daily.{service,timer}` | systemd unit templates | **Move** → `ops/systemd/` |
| `compose.gpu.yaml` | GPU override | **Move** → `ops/compose.gpu.yaml` (override paths resolve against the base file, so nothing inside changes) |
| `data/grants/*.csv` | Three 10-row sample CSVs, the only tracked thing in `data/` | **Untrack**, and gitignore all of `/data/`. Locally `data/` stays the runtime store (`collect/` 556 MB, `eval-cache/` 30 GB, `logs/`, `outbox/`), so `data/` disappears from GitHub only |
| `models/` | Only `README.md` is tracked; the real content is a downloaded FastEmbed cache | **Remove from the repo.** Point `FASTEMBED_CACHE_PATH` at `/app/data/models/fastembed` (both services in `compose.yaml`) and `mv models/fastembed data/models/` on the host so nothing re-downloads. The README's GPU/warm-up notes move into `docs/architecture.md`. It also names a `pivot.py` that no longer exists |
| `mylo/` | The Discord bot | **Keep** at the root (`python -m mylo.bot`, and the backend tests import `mylo.linking`) |
| `eval/` | Retrieval evaluation harness (its own uv project) | **Keep** |
| `docs/`, `web/` | Docs and the app | **Keep** (`web/` is untouched by this plan) |
| `.agents/`, `.claude/`, `.cursor/` | Agent entrypoint stubs pointing at `docs/skills/` | **Keep** |
| `AGENTS.md` | Added today in commit `a78fb08`. It is a find-and-replace copy of `CLAUDE.md` that now reads "`AGENTS.md` is the only agent-instruction file. There is no `AGENTS.md`", and it points at a `web/AGENTS.md` that does not exist. `CLAUDE.md` forbids an `AGENTS.md` | **Decision needed** (see Open questions) |

Untracked local clutter that only shows on this machine:

- `__pycache__/` (left behind by the root scripts; goes away once they move)
- `.ruff_cache/`
- `.pytest_cache/` (root-owned, needs `sudo rm -rf`)
- `loadtest_results/`

Phase 1 clears all of these.

## 2. Target layout

```text
Mycelium/
├── README.md  LICENSE  NOTICE  CONTRIBUTING.md  CLAUDE.md
├── Makefile                 # the front door: make setup / up / down / test / nightly / help
├── compose.yaml
├── package.json             # npm scripts → web/
├── pyproject.toml  uv.lock  .python-version
├── .env.example  .env-mylo.example
├── docs/                    # all documentation, plans, the research record
├── web/                     # the app: landing, app, backend, infra
├── mylo/                    # the Mylo Discord bot
├── eval/                    # retrieval evaluation harness
└── ops/                     # everything that runs on the host, outside the containers
    ├── mycelium             # stack manager CLI
    ├── compose.gpu.yaml
    ├── setup/               # create_admin.py, bootstrap.py (new)
    ├── nightly/             # manual_all.py, manual_mylo.py, _runner.py, manual_{opportunities,refitting,search}.py
    ├── scrapers/            # scrape_fellowships.py, grants/
    ├── systemd/             # the five unit templates
    ├── loadtest/            # loadtest.py, loadtest_interests.py
    └── research/            # research-record tooling (was scripts/research)
```

That leaves 15 visible root entries, down from 37, and `scripts/`, `utils/`,
`data/` and `models/` no longer exist on GitHub. The name `ops/` is a proposal;
`tools/` would work just as well.

## 3. Phases

### Phase 1: move files and fix the wiring they depend on

Do this in a dedicated `git worktree` and merge it as one change, because other
sessions share the main checkout. Do **not** run the nightly pipeline inside the
worktree: `data/collect` is anchored to the checkout, so it would see an empty
store and re-crawl.

1. `git mv` every row marked Move above. Delete `main.py`, `run.py` and
   `package-lock.json`. `git rm --cached data/grants/*.csv` and
   `models/README.md`.
2. Fix path resolution in the moved scripts. Each one now sits one or two
   levels deeper:
   - `manual_all.py:183,199` and `manual_mylo.py:58`: `ROOT` and the
     `sys.path` insert for `utils/manual` (now a sibling)
   - `create_admin.py:29`
   - `scrape_fellowships.py:44`
   - `loadtest.py:76`, plus its results directory
   - `_runner.py:21` (`parents[2]` still lands on the root from
     `ops/nightly/`; confirm it)
   - `ops/mycelium` (`parent.parent` stays correct)
   - `ops/research/record.py` (`parents[2]` stays correct)
3. Point everything that names an old path at the new one:
   - `Makefile` (`SCRIPTS := ops/research`)
   - the `ExecStart`/`WorkingDirectory` lines in `ops/systemd/*` (e.g.
     `__MYCELIUM_ROOT__/ops/nightly/manual_all.py`)
   - the `install-service` step in `ops/mycelium`
   - `compose.yaml` (`FASTEMBED_CACHE_PATH`)
   - `.gitignore`: add `/data/`, `/package-lock.json`, `loadtest` results; drop
     the now-redundant `data/...` lines
   - `docs/research/templates/experiment/manifest.yaml`
   - `.env.example` comments
   - the three `web/backend/apps/scraper/collect/*/__init__.py` docstrings
     that cite `utils/grants`
4. Sweep docs, excluding `docs/changelog.md` and existing experiment folders,
   which are history. Start from
   `git grep -l -E "manual_all|manual_mylo|scrape_fellowships|create_admin|loadtest|utils/|scripts/|run\.py|\.service|\.timer|compose\.gpu|models/"`.
   The main hits are:
   - `docs/repo-map.md` (the Operations rows at ~326–337) and
     `docs/skills/repo-structure.md` (its "Actual layout" tree)
   - `docs/architecture.md`, `docs/discord-integration.md`,
     `docs/loadtest.md`, `docs/evaluation.md`
   - `docs/skills/{global,planner,website-architecture}.md`
   - `README.md`, `CONTRIBUTING.md`
   - `mylo/__init__.py`, `web/backend/config/settings.py`

   Change `docs/discord-integration.md` so `uv export` writes
   `data/mylo-requirements.txt` rather than a root dotfile.
5. Clear the local clutter: `sudo rm -rf .pytest_cache`, and remove
   `.ruff_cache`, `__pycache__` and `loadtest_results`.

**Validate:**
- `make validate-research`
- `uv run --project web/backend pytest web/backend`
- `uv run --no-sync pytest mylo/tests`
- `uv run --no-sync python ops/nightly/manual_all.py --help`
- `ops/mycelium status`
- `git grep` for each old path returns only changelog and experiment history

### Phase 2: host cutover (sudo, done once on each machine that runs Mycelium)

This is the one step that can break production silently. The installed units
substitute an absolute path to `manual_all.py`, so after the move the nightly
timer would fire at a file that no longer exists.

- Re-link the CLI:
  `sudo ln -sfn "$PWD/ops/mycelium" /usr/local/bin/mycelium`. It currently
  points at `scripts/mycelium`.
- Re-install the units with `mycelium install-service`, then confirm
  `systemctl cat mylo-daily.service` shows `ops/nightly/manual_all.py` and
  `systemctl list-timers mylo-daily.timer` still lists the timer. On this
  machine `systemctl cat mylo-daily.service` currently finds nothing, so
  check whichever host actually runs the nightly.
- `mv models/fastembed data/models/fastembed` (may need sudo: `data/` has
  root-owned subfolders), then recreate the backend and worker containers.
- Don't do the cutover in the hour before the timer fires.

### Phase 3: reposition the product

New one-liner, used everywhere a tagline appears:

> **Mycelium is an open-source academic research assistant that any lab can run on its own computers.**

Then explain what Mycelium is underneath. It is the **grounding layer**: the
corpus, lab and member profiles, the knowledge graph, opportunity feeds, and
the evaluation harness. Research tools are built on top of it, and what ships
today is the first of those tools: the paper, grant, fellowship and conference
feeds, daily reports, reminders, and Mylo in Discord.

The next tools go into `docs/goals.md` → *Next* as **planned, not built**, each
with the public benchmark that would prove it:

| Planned tool | Proven against |
|---|---|
| Claim and citation-stance engine, built with the hypothesis engine (finds contested or unresolved claims to seed hypotheses) | SciCite, MultiCite |
| Systematic-review screening (a ranking problem, so it reuses the ranking stack and `eval/`) | CLEF TAR, SYNERGY, scored as work saved at 95% recall |
| Expertise finder | Recovering held-out collaborations or funded teams |
| Literature-mined domain databases (the grants schema extraction, pointed at a field) | Precision against a curated database |
| Internal funding and limited-submission matching | Low compute; reuses the grant feed and eligibility engine |

The hypothesis engine is evaluated with a time split: freeze the corpus at a
date, generate hypotheses, then score them against what was published after.
Record it under `docs/research/` like any other experiment.

Kept **out** of the public repo:
- the FSU budget and licence-savings argument
- competitor pricing
- the compute request

These belong in the gitignored `docs/grants/` proposal material.

Surfaces to change:

- **Canonical docs first** (CLAUDE.md requires it):
  - `docs/purpose.md` (opening)
  - `docs/goals.md:36` and *Next*
  - `docs/skills/global.md:17`
  - `docs/skills/index.md:30`
- **Public site and app copy:**
  - `web/landing/src/components/landing/HomeHero.astro:49` (kicker "Open-source lab intelligence")
  - `web/landing/src/pages/product.astro:16` ("Evidence-backed lab intelligence")
  - `web/app/src/app/layout.tsx:38`
  - `web/app/src/app/app/(workspace)/layout.tsx:7`
- **GitHub "About" description.** It currently reads "…powered by Agentic
  Knowledge Graphs", which overclaims. Change it with `gh repo edit
  --description`; it's outward-facing, so confirm the wording first.
- **Leave as they are:**
  - `docs/research/paper/*`, where "laptop-scale" is a measured hardware claim
    for the SIGIR demo and US-RSE paper
  - `docs/Resources/Mycelium Project Brief.md`, a historical brief

### Phase 4: one-command setup for people and agents

- **`ops/setup/bootstrap.py`** (stdlib only), behind `make setup`. It is
  idempotent and safe to re-run. In order:
  1. Copies `.env.example` → `.env` and `.env-mylo.example` → `.env-mylo` if
     missing.
  2. Fills the `change-me` secrets (`DJANGO_SECRET_KEY`, `NEO4J_PASSWORD`,
     `S3_SECRET_ACCESS_KEY`, the Fernet key) with generated values.
  3. Prompts for, or reads from the environment, the one thing it cannot
     invent: `LLM_BASE_URL` and `LLM_API_KEY`.
  4. Runs `docker compose up -d --build` and waits for `/api/health/`.
  5. Applies migrations, then runs `create_admin`.
  6. Prints the URLs.
- **Makefile becomes the front door,** listed by `make help`:
  - `setup`, `up`, `down`, `restart`, `status`, `logs` (the last four delegate
    to `ops/mycelium`)
  - `test`, `lint` (same commands as `package.json`)
  - `nightly` (`ops/nightly/manual_all.py`)
  - `gpu-up`
  - the existing research targets

  `package.json` keeps the npm dev-server scripts.
- **`.env.example`:** move the handful of required variables into a short
  "Required" block at the top. The other ~150 stay below as "Optional, safe
  defaults".
- **`CLAUDE.md`:** add a three-line "First-time setup" section (`make setup`,
  then `make test`) so a cloning agent finds it without reading the README.

**Validate:** in a fresh `git clone` into the scratchpad, with a throwaway
`.env`, `make setup && make status` brings the stack up and the gateway
answers on :11050. Do this on a second port set, or with the main stack
stopped.

### Phase 5: README, written with the README skill

The skill's rule is **propose, then write**, so this phase starts from the
proposal below and waits for approval before writing a line.

**Profile:** hybrid (application/tool first, research second). Strangers
arrive wanting to run it; reviewers arrive wanting the evaluation.

**Current state:** the README opens with a "This is a research repository"
banner, before saying what Mycelium is. Its "What is running today" list
still claims a percent match on every card, which the app no longer shows,
and lists billing tiers on a site that has removed pricing. The run
instructions split three ways (`docker compose up`, `python run.py`,
`scripts/mycelium`).

| # | Section | Action | What it will contain | Needs from you |
|---|---|---|---|---|
| 1 | Title + one-liner | Rewrite | The Phase 3 line, plus one sentence on the grounding layer | Approve wording |
| 2 | What it does today | Rewrite | Feeds, daily report, reminders, Mylo in Discord, search. Each verified against code; stale claims dropped | — |
| 3 | Screenshot | Add | One feed card or the morning report | A screenshot, or permission to take one from the dev stack |
| 4 | Quickstart | Rewrite | `git clone` → `make setup` → open :11050. Requirements: Docker, uv, Node; Python 3.13 from `.python-version` | — |
| 5 | Configuration | Add (short) | The required env block, with a link to `.env.example` for the rest | — |
| 6 | Running it day to day | Merge | One `make` table that replaces the three run paths | — |
| 7 | How it's built | Keep, trim | The stack table | — |
| 8 | Repository layout | Add | The Phase 2 tree, one line per folder | — |
| 9 | Research and evaluation | Move down | The research-record banner becomes a section: `docs/research/`, `eval/`, `make validate-research` | — |
| 10 | Roadmap | Add | The five planned tools, marked planned | — |
| 11 | Contributing, License | Keep | Apache 2.0, NOTICE, link to `CONTRIBUTING.md` | — |

**Deliberately omitted:** badges (no CI to report), FAQ, a features list that
repeats section 2.

**Banner:** offered, not assumed. `docs/Resources/Logos.png` exists, but the
skill wants a square SVG.

## 4. Open questions

1. **`AGENTS.md`.** Delete it, as `CLAUDE.md` requires? Or keep it as a
   two-line pointer to `CLAUDE.md` for Codex and similar agents, and change
   the rule? Either way, today's copy is broken.
2. **"Laptop-scale Lab Intelligence".** That exact phrase is not in any
   tracked file or in the GitHub description. The closest are the landing
   kicker "Open-source lab intelligence" and "lab intelligence platform" in
   the README and canonical docs, all listed in Phase 3. If you saw it on the
   live site, that deploy is older than `main`.
3. **"Academic Research Assistance".** The plan reads this as *academic
   research assistant*. Confirm.
4. **`docs/chats/` and `docs/Resources/`.** These are raw chat transcripts and
   the original project brief, sitting in a public repo. Recommendation:
   - delete `docs/chats/` and fold the one line `ui-frontend.md` cites into
     `styles.md`
   - move the two images to `web/art/` and update the Mylo trace scripts'
     paths
   - drop the brief, since `purpose.md` supersedes it

   Not done without a yes.
5. **The folder name.** `ops/` or `tools/`?

## 5. Explicitly excluded

- Anything inside `web/`, apart from the four copy lines in Phase 3.
- Rewriting history to purge the old CSVs.
- Renaming `manual_all.py` itself (memories, docs and the research record all
  use the name).
- Converting the root scripts into Django management commands.
- Adding CI.
