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
.PHONY: help setup config up down restart build status logs migrate admin gpu-up \
	test test-mylo lint nightly \
	new-experiment validate-research research-index figures figures-check research-ci

help: ## Show these targets
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Setup and the stack ──────────────────────────────────────────────────────

setup: ## First run: pick a profile, write .env, build, create the first admin [PROFILE=lab]
	@$(PYTHON) ops/setup/bootstrap.py $(if $(PROFILE),--profile $(PROFILE))

config: ## Read or change mycelium.toml: make config ARGS="show" (see `make config ARGS=-h`)
	@$(PYTHON) ops/setup/config_cli.py $(or $(ARGS),show)

up: ## Start the stack (detached) and apply migrations
	@$(STACK) start

down: ## Stop the stack
	@$(STACK) stop

restart: ## Stop, then start the stack
	@$(STACK) restart

build: ## Rebuild the images, then start the stack
	@$(STACK) build

status: ## Show containers, Mylo, and endpoint health
	@$(STACK) status

logs: ## Follow the stack's logs
	@$(STACK) logs

migrate: ## Apply database migrations against the running stack
	@$(STACK) migrate

admin: ## Create or promote an admin: make admin NAME=alice [EMAIL=alice@example.org]
ifndef NAME
	$(error NAME is required, e.g. make admin NAME=alice)
endif
	@$(PYTHON) ops/setup/create_admin.py "$(NAME)" $(if $(EMAIL),--email "$(EMAIL)")

gpu-up: ## Start the stack with CUDA embedding (needs nvidia-container-toolkit)
	docker compose -f compose.yaml -f ops/compose.gpu.yaml up -d

# ── Development ──────────────────────────────────────────────────────────────

test: ## Backend test suite
	uv run --directory web/backend pytest

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

nightly: ## Run the nightly research pipeline once, now, against the running stack
	uv run ops/nightly/manual_all.py

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
