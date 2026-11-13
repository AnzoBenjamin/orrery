#!/usr/bin/env bash
# `pnpm codegen`: builds crates/kinematics-wasm into pkg/ with wasm-pack (a web target, loaded by
# the solver worker). The output is committed and checked for staleness like other generated code.
set -euo pipefail
cd "$(dirname "$0")/.."
root="$(cd ../.. && pwd)"
wasm-pack build "$root/crates/kinematics-wasm" --release --target web --no-pack \
  --out-dir "$root/packages/kinematics-wasm/pkg" --out-name kinematics >/dev/null 2>&1 \
  || wasm-pack build "$root/crates/kinematics-wasm" --release --target web --no-pack \
    --out-dir "$root/packages/kinematics-wasm/pkg" --out-name kinematics
# wasm-pack ignores its own output; this package commits it.
rm -f pkg/.gitignore
