#!/usr/bin/env bash
# `pnpm test`: unit and integration tests for TypeScript, Rust, and Python.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== typescript"
# Most suites start their own Postgres, Garage, or Mailpit containers. Running every package at
# once made container start-up slow enough to time out hooks, so two packages run at a time.
pnpm exec turbo run test --concurrency=2

echo "== rust"
bash scripts/rust.sh test

echo "== python"
bash scripts/python.sh test
