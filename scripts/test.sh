#!/usr/bin/env bash
# `pnpm test`: unit and integration tests for TypeScript, Rust, and Python.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== typescript"
pnpm exec turbo run test

echo "== rust"
bash scripts/rust.sh test

echo "== python"
bash scripts/python.sh test
