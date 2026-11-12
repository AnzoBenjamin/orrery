#!/usr/bin/env bash
# Runs a Rust workspace step. The Cargo workspace is declared before its first crate lands,
# and cargo refuses to run on a workspace with no members, so the step is skipped until then.
set -euo pipefail
cd "$(dirname "$0")/.."

shopt -s nullglob
crates=(crates/*/Cargo.toml)
if [ ${#crates[@]} -eq 0 ]; then
  echo "rust: no crates under crates/, skipping $1"
  exit 0
fi

case "$1" in
  fmt) cargo fmt --all ;;
  fmt-check) cargo fmt --all --check ;;
  clippy) cargo clippy --workspace --all-targets --locked -- -D warnings ;;
  test) cargo test --workspace --locked ;;
  *) echo "rust.sh: unknown step '$1'" >&2; exit 2 ;;
esac
