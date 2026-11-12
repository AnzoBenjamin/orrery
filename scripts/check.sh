#!/usr/bin/env bash
# `pnpm check`: formatting, lint, and type checks for TypeScript, Rust, and Python.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== repository rules"
bash scripts/check-kiro.sh
bash scripts/check-generated.sh

echo "== typescript"
pnpm exec biome ci .
pnpm exec turbo run typecheck

echo "== rust"
bash scripts/rust.sh fmt-check
bash scripts/rust.sh clippy

echo "== python"
bash scripts/python.sh lint
