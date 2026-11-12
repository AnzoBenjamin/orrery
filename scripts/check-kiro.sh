#!/usr/bin/env bash
# Kiroween submission rule: /.kiro must exist at the repository root, be tracked, and never be ignored.
set -euo pipefail
cd "$(dirname "$0")/.."

fail() { echo "check-kiro: $1" >&2; exit 1; }

[ -d .kiro ] || fail ".kiro directory is missing at the repository root"
[ -d .kiro/steering ] || fail ".kiro/steering is missing"
[ -d .kiro/specs ] || fail ".kiro/specs is missing"

# Ask git directly, so every ignore source counts: .gitignore files, .git/info/exclude, core.excludesFile.
while IFS= read -r path; do
  if git check-ignore --no-index -q "$path"; then
    fail "$path is ignored by git ($(git check-ignore --no-index -v "$path"))"
  fi
done < <(find .kiro -print)

# Other ignore files that could drop .kiro from a build context or a package.
for f in $(git ls-files --cached --others --exclude-standard -- '*.dockerignore' '.dockerignore' '*.npmignore' '.npmignore'); do
  if grep -Eq '^[[:space:]]*/?\.kiro(/|$)' "$f"; then
    fail "$f lists .kiro"
  fi
done

echo "check-kiro: .kiro present and not ignored"
