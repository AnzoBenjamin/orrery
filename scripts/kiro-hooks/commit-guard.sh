#!/usr/bin/env bash
# Kiro PreToolUse hook for the shell tool (requirement 16.4). When the agent is about to run a
# command that commits, it scans what the commit could include for placeholder markers and
# blocks the command (exit 2, reason on stderr) if any are found. Other commands pass untouched.
#
# The hook payload arrives as JSON on stdin. Only the presence of `git ... commit` in it matters,
# so it is matched as text rather than parsed, which needs no JSON tool on the host.
set -uo pipefail
cd "$(dirname "$0")/../.."

payload=$(cat)
if ! grep -Eq '\bgit\b[^"]*\bcommit\b' <<<"$payload"; then
  exit 0
fi
if ! report=$(bash scripts/check-placeholders.sh --pending 2>&1); then
  printf 'Commit blocked by the placeholder guard (.kiro/hooks/placeholder-commit-guard.json).\n%s\n' "$report" >&2
  exit 2
fi
exit 0
