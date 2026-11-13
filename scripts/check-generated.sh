#!/usr/bin/env bash
# Fails when committed generated code is out of date with its source (requirement 1.6).
# Each generator runs, and any artifact whose content changed is named. Regenerated files are left
# in place so the fix is to review and commit them.
set -euo pipefail
cd "$(dirname "$0")/.."

# Artifacts produced by `pnpm codegen`. Add new generated paths here as generators land.
artifacts=(
  packages/db/src/schema/auth.ts
  packages/engine-contract/schema/engine-contract.json
  packages/schema/schema/mechanism.json
  crates/kinematics/src/generated/mechanism.rs
  services/engine/src/orrery_engine/generated/mechanism.py
  packages/kinematics-wasm/pkg/kinematics.js
  packages/kinematics-wasm/pkg/kinematics.d.ts
  packages/kinematics-wasm/pkg/kinematics_bg.wasm
  packages/kinematics-wasm/pkg/kinematics_bg.wasm.d.ts
  crates/kinematics-py/python/orrery_kinematics/_native/__init__.pyi
  services/engine/src/orrery_engine/generated/contract.py
  services/engine/src/orrery_engine/generated/__init__.py
)

declare -A before
for f in "${artifacts[@]}"; do before[$f]=$(sha256sum "$f" 2>/dev/null | cut -c1-64 || echo missing); done

pnpm exec turbo run codegen --output-logs=errors-only

stale=()
for f in "${artifacts[@]}"; do
  after=$(sha256sum "$f" 2>/dev/null | cut -c1-64 || echo missing)
  [ "${before[$f]}" = "$after" ] || stale+=("$f")
done

# Drizzle migrations: generating against a copy of the migration folder must produce nothing new.
# drizzle-kit needs a path relative to the package, so the scratch copy lives inside it.
scratch=packages/db/.migrations-check
rm -rf "$scratch"
trap 'rm -rf "$scratch"' EXIT
cp -r packages/db/migrations "$scratch"
(cd packages/db && pnpm exec drizzle-kit generate --dialect postgresql \
  --schema src/schema/index.ts --out .migrations-check >/dev/null)
if [ -n "$(diff -rq packages/db/migrations "$scratch" || true)" ]; then
  stale+=("packages/db/migrations (schema changed without a migration: run pnpm --filter @orrery/db generate)")
fi

if [ ${#stale[@]} -gt 0 ]; then
  echo "check-generated: stale generated code:" >&2
  printf '  %s\n' "${stale[@]}" >&2
  exit 1
fi
echo "check-generated: generated code is current"
