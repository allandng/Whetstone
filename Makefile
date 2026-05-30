# Whetstone — top-level developer tasks.
#
# Most day-to-day work is one command:  make dev
# See RUNNING.md for the full bring-up story and model setup.

ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
DESKTOP := $(ROOT)apps/desktop
PSIRVER_SRC := $(ROOT)services/psirver/src

# Pass extra flags through to the launcher, e.g.  make dev ARGS="--skip-llm"
ARGS ?=

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: dev
dev: ## Start all four local services (backend, Psirver, llama-server, whisper-server).
	@bash scripts/dev.sh $(ARGS)

.PHONY: dev-backend
dev-backend: ## Start only the backend + Psirver (skip the model servers).
	@bash scripts/dev.sh --skip-llm --skip-stt

.PHONY: psirver
psirver: ## Build the Psirver C++ binary.
	@$(MAKE) -C $(PSIRVER_SRC)

.PHONY: backend-venv
backend-venv: ## Create the backend virtualenv and install deps.
	@cd apps/backend && python3 -m venv .venv && .venv/bin/python -m pip install -e .

.PHONY: bundle
bundle: ## Build the macOS Tauri release bundle (.app + .dmg).
	@cd $(DESKTOP) && npm install && npm run tauri build

.PHONY: clean
clean: ## Remove dev scratch (logs, run dir). Leaves the venv and models.
	@rm -rf $(ROOT).dev-logs $(ROOT).dev-run
	@echo "removed .dev-logs/ and .dev-run/"
