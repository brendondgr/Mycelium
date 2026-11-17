# Mycelium's front door. `make help` lists every target.
#
# Stack targets delegate to `ops/mycelium`, the stack manager; app build, lint
# and test commands match `package.json`. The research targets exist so that
# recording an experiment costs one command, because a convention that costs
# more than that is a convention people skip.

PYTHON ?= python3
STACK := $(PYTHON) ops/mycelium
RESEARCH_RUN := uv run --project ops/research
SCRIPTS := ops/research

.DEFAULT_GOAL := help
.PHONY: help setup config up dev down restart build status doctor logs migrate admin \
	backup restore gpu-up test test-fast test-changed test-mylo lint nightly \
	new-experiment validate-research research-index figures figures-check research-ci

help: ## Show these targets
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Setup and the stack ──────────────────────────────────────────────────────

setup: ## First run: asks hostname + model, writes .env, builds, first admin [PROFILE=lab] [YES=1]
	@$(PYTHON) ops/setup/bootstrap.py $(if $(PROFILE),--profile $(PROFILE)) $(if $(YES),--yes)

config: ## Read or change mycelium.toml: make config ARGS="show" (see `make config ARGS=-h`)
	@$(PYTHON) ops/setup/config_cli.py $(or $(ARGS),show)

up: ## Start the production stack (gunicorn, next start, static site) and migrate
	@$(STACK) start --prod

dev: ## Start the hot-reload stack instead (next dev, astro dev, runserver, DEBUG on)
	@$(STACK) start --dev

down: ## Stop the stack
	@$(STACK) stop

restart: ## Stop, then start the stack in the mode it last ran in
	@$(STACK) restart

build: ## Rebuild the images, then start the stack
	@$(STACK) build

status: ## Containers, endpoints, Mylo, and the steps still to run by hand
	@$(STACK) status

doctor: ## Check the instance end to end (stack, model, corpus, exposure); exit 1 on a problem
	@$(STACK) doctor

logs: ## Follow the stack's logs
	@$(STACK) logs

migrate: ## Apply database migrations against the running stack
	@$(STACK) migrate

admin: ## Create or promote an admin (prompts for, or generates, the password): make admin NAME=alice
ifndef NAME
	$(error NAME is required, e.g. make admin NAME=alice)
endif
	@$(PYTHON) ops/setup/create_admin.py "$(NAME)" $(if $(EMAIL),--email "$(EMAIL)")

backup: ## Database dump + uploaded files + mycelium.toml into data/backups/ (mode 0600)
	@$(STACK) backup

restore: ## Put a backup back: make restore FILE=data/backups/mycelium-<stamp>.tar.gz
ifndef FILE
	$(error FILE is required, e.g. make restore FILE=data/backups/mycelium-20261112-030000.tar.gz)
endif
	@$(STACK) restore "$(FILE)"

gpu-up: ## Start the stack with CUDA embedding (needs nvidia-container-toolkit)
	docker compose -f compose.yaml -f ops/compose.gpu.yaml up -d

# ── Development ──────────────────────────────────────────────────────────────

test: ## Backend test suite
	uv run --directory web/backend pytest

test-fast: ## The same tests split over several processes (a few minutes); SHARDS=8
	@ops/test-fast.sh

test-changed: ## Only the test directories a change touches (since origin/main, or uncommitted)
	@ops/test-fast.sh --changed

test-mylo: ## Mylo bot and daily-run tests
	uv run python -m unittest discover -s mylo/tests -t .

tools-check: ## The tools import script in the running stack: every tool's load state
	@$(STACK) tools check

tools-plan: ## The nightly stage plan the loaded tools produce, in run order
	@$(STACK) tools plan

tools-matrix: ## Delete-each / break-each: remove or break every tool in turn, check the rest
	uv run --directory web/backend pytest -c pyproject.toml ../../tools/_framework/tests/test_delete_matrix.py

new-tool: ## Scaffold a tool from the template: make new-tool NAME=my_tool
ifndef NAME
	$(error NAME is required, e.g. make new-tool NAME=screening)
endif
	@$(PYTHON) tools/_framework/scaffold.py "$(NAME)"

lint: ## Astro check, Next.js eslint, backend ruff
	npm run lint

# Every stage runs inside the backend container (docker compose exec); the
# host side is a standard-library orchestrator, so plain python3 runs it when
# uv is not installed. Only the fellowship browser scrape needs the host's uv.
nightly: ## Run the collection and ranking pipeline once, now (the first collection, too)
	@$(if $(shell command -v uv 2>/dev/null),uv run,$(PYTHON)) ops/nightly/manual_all.py

# ── Research record (docs/research/) ─────────────────────────────────────────

new-experiment: ## Scaffold an experiment: make new-experiment SLUG=my-slug [TITLE="..."]
ifndef SLUG
	$(error SLUG is required, e.g. make new-experiment SLUG=cluster-scoping-ablation)
endif
	@$(RESEARCH_RUN) $(SCRIPTS)/new_experiment.py "$(SLUG)" --title "$(TITLE)"

validate-research: ## Validate every experiment folder and the index
	@$(RESEARCH_RUN) $(SCRIPTS)/validate_research.py

research-index: ## Regenerate docs/research/INDEX.md
	@$(RESEARCH_RUN) $(SCRIPTS)/generate_index.py

figures: ## Regenerate every experiment figure and re-promote paper figures
	@$(RESEARCH_RUN) $(SCRIPTS)/build_figures.py

figures-check: ## Regenerate figures and fail if anything drifted
	@$(RESEARCH_RUN) $(SCRIPTS)/build_figures.py --check

research-ci: research-index validate-research figures-check ## The full research-record check
	@git diff --quiet -- docs/research || { \
		echo "docs/research/ is out of date — run 'make research-index figures' and commit."; \
		git --no-pager diff --stat -- docs/research; \
		exit 1; \
	}
	@echo "Research record is current."
