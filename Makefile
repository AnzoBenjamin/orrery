# Single entry point for Orrery development. Needs only Docker Engine and Docker Compose v2.
# Every recipe runs inside the toolbox container; nothing is installed on the host.

SHELL := /bin/bash
.DEFAULT_GOAL := help

export HOST_UID := $(shell id -u)
export HOST_GID := $(shell id -g)

COMPOSE := docker compose -f infra/compose.yaml
# -T when there is no terminal (CI, agents), so output is not mangled by a pseudo-TTY.
TOOLBOX := $(COMPOSE) run --rm $(if $(shell [ -t 0 ] && echo tty),,-T) toolbox

.PHONY: help toolbox shell install check test format

help: ## List recipes
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

toolbox: ## Build the toolbox image with your UID and GID
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
