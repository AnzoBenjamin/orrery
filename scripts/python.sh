#!/usr/bin/env bash
# Runs a Python workspace step through uv. Tests run only once a member project exists.
set -euo pipefail
cd "$(dirname "$0")/.."

uv sync --frozen --all-packages --quiet

shopt -s nullglob
members=(services/*/pyproject.toml tools/*/pyproject.toml)

case "$1" in
  lint)
    uv run --frozen ruff format --check .
    uv run --frozen ruff check .
    if [ ${#members[@]} -eq 0 ]; then
      echo "python: no projects under services/ or tools/, skipping pyright"
    else
      uv run --frozen pyright
    fi
    ;;
  test)
    if [ ${#members[@]} -eq 0 ]; then
      echo "python: no projects under services/ or tools/, skipping pytest"
    else
      uv run --frozen pytest
    fi
    ;;
  *) echo "python.sh: unknown step '$1'" >&2; exit 2 ;;
esac
