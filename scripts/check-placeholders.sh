#!/usr/bin/env bash
# Fails when code outside test directories carries a placeholder marker (requirement 16.4,
# quality.md): TODO, FIXME, lorem, or mock.
#
#   check-placeholders.sh            every tracked file (pnpm check, CI)
#   check-placeholders.sh --pending  only what a commit could include: changed lines in tracked
#                                    files and untracked files (the Kiro commit guard)
#
# A line that must keep such a word for a real reason (an API named `mock`, say) carries
# `placeholder-check: allow` and the reason in a comment on the same line.
set -euo pipefail
cd "$(dirname "$0")/.."

pattern='\b(TODO|FIXME)\b|\b[Ll]orem\b|\b[Mm]ock'

# Tests may mock what we cannot run (quality.md). Steering and specs state the rule itself.
excluded='(^|/)(test|tests|e2e|testing|fixtures|__tests__)/|\.(test|spec)\.[a-z]+$|^\.kiro/|^scripts/check-placeholders\.sh$|(^|/)(pnpm-lock\.yaml|uv\.lock|Cargo\.lock)$'

hits=$(mktemp)
trap 'rm -f "$hits"' EXIT

scan_file() {
  [ -f "$1" ] || return 0
  grep -n -I -E "$pattern" "$1" 2>/dev/null | grep -v 'placeholder-check: allow' | sed "s|^|$1:|" >>"$hits" || true
}

if [ "${1:-}" = "--pending" ]; then
  # Added lines in tracked files, with their new line numbers.
  # awk lists them as file:line:text; grep then matches the text part only.
  git diff HEAD --unified=0 --no-color --no-ext-diff | EXCLUDED="$excluded" awk '
    /^\+\+\+ / { file = substr($0, 7); skip = (file ~ ENVIRON["EXCLUDED"]); next }
    /^@@ / { split($3, a, ","); line = substr(a[1], 2) + 0; next }
    /^\+/ { if (!skip) print file ":" line ":" substr($0, 2); line++; next }
  ' | grep -E "^[^:]+:[0-9]+:.*(${pattern})" | grep -v 'placeholder-check: allow' >>"$hits" || true
  while IFS= read -r f; do
    [[ "$f" =~ $excluded ]] || scan_file "$f"
  done < <(git ls-files --others --exclude-standard)
else
  while IFS= read -r f; do
    [[ "$f" =~ $excluded ]] || scan_file "$f"
  done < <(git ls-files)
fi

if [ -s "$hits" ]; then
  echo "check-placeholders: placeholder markers outside test directories:" >&2
  sed 's/^/  /' "$hits" >&2
  echo "Write the finished code instead (quality.md). If the word is genuinely needed, end the" >&2
  echo "line with a comment containing 'placeholder-check: allow' and the reason." >&2
  exit 1
fi
echo "check-placeholders: no placeholder markers"
