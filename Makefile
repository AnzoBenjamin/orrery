# Single entry point for Orrery development. Needs only Docker Engine and Docker Compose v2.
# Every recipe runs inside containers; nothing is installed on the host.

SHELL := /bin/bash
.DEFAULT_GOAL := help

export HOST_UID := $(shell id -u)
export HOST_GID := $(shell id -g)

COMPOSE := docker compose --env-file .env -f infra/compose.yaml
# -T when there is no terminal (CI, agents), so output is not mangled by a pseudo-TTY.
TTY_FLAG := $(if $(shell [ -t 0 ] && echo tty),,-T)
TOOLBOX := $(COMPOSE) run --rm $(TTY_FLAG) toolbox

# Volumes holding project data. `reset` recreates these and keeps the dependency caches.
DATA_VOLUMES := orrery_pg-data orrery_garage-meta orrery_garage-data

.PHONY: help env up down reset logs ps db-shell migrate migrate-only toolbox shell install check test format

help: ## List recipes
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

env: ## Create or update .env from .env.example, generating local secrets
	@bash scripts/env.sh

# Startup order: infrastructure, then one-shot setup (Garage bootstrap, migrations), then the app.
# The web app and worker refuse to run against an unmigrated database, so migrate comes first.
INFRA := postgres garage mailpit otel-collector
APP := web worker

up: install ## Start the full stack and wait until every service is healthy
	$(COMPOSE) up --detach --build --wait --wait-timeout 180 $(INFRA)
	$(COMPOSE) run --rm $(TTY_FLAG) garage-init
	$(MAKE) --no-print-directory migrate-only
	$(COMPOSE) up --detach --wait --wait-timeout 300 $(APP)

down: env ## Stop the stack (data is kept)
	$(COMPOSE) down --remove-orphans

reset: env ## Destroy and recreate the database and object storage (CONFIRM=1 skips the prompt)
	@if [ "$(CONFIRM)" != "1" ]; then \
	  read -r -p "This deletes all local Postgres and Garage data. Type 'reset' to continue: " answer; \
	  [ "$$answer" = "reset" ] || { echo "Aborted."; exit 1; }; \
	fi
	$(COMPOSE) down --remove-orphans
	docker volume rm --force $(DATA_VOLUMES)
	$(MAKE) up

logs: env ## Follow logs (s=<service> for one service)
	$(COMPOSE) logs --follow --tail 200 $(s)

ps: env ## Show service status and health
	$(COMPOSE) ps --all

db-shell: env ## Open psql on the local database
	$(COMPOSE) exec $(TTY_FLAG) postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

migrate: install migrate-only ## Apply database migrations to the local stack

migrate-only:
	$(TOOLBOX) bash -c 'DATABASE_URL="postgres://$$POSTGRES_USER:$$POSTGRES_PASSWORD@postgres:5432/$$POSTGRES_DB" pnpm --filter @orrery/worker migrate'

toolbox: env ## Build the toolbox image with your UID and GID
ifndef TOOLBOX_PREBUILT
	$(COMPOSE) build toolbox
endif

shell: toolbox ## Open a shell in the toolbox
	$(TOOLBOX) bash

install: toolbox ## Install JavaScript and Python dependencies from the lockfiles
	$(TOOLBOX) bash -c 'pnpm install --frozen-lockfile && uv sync --frozen --all-packages'

check: install ## Formatting, lint, and type checks for all languages
	$(TOOLBOX) pnpm check

test: install ## Unit and integration tests for all languages
	$(TOOLBOX) pnpm test

format: install ## Apply formatters for all languages
	$(TOOLBOX) pnpm format
