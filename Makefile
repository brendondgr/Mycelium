# Root targets for the research record (`docs/research/`).
#
# Scoped deliberately: this Makefile does not wrap the app's build, test, or
# lint commands, which live in `package.json` and `uv run --project web/backend`.
# It exists so that recording an experiment costs one command, because a
# convention that costs more than that is a convention people skip.

RESEARCH_RUN := uv run --project scripts/research
SCRIPTS := scripts/research

.DEFAULT_GOAL := help
.PHONY: help new-experiment validate-research research-index figures figures-check research-ci

help: ## Show these targets
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

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
