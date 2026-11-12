#!/usr/bin/env bash
# Creates or updates .env from .env.example. Keys missing from .env are appended. A key whose
# comment line starts with "# secret:" and whose example value is empty gets a random value, so no
# shared credential is ever committed. Existing values in .env are never changed.
set -euo pipefail
cd "$(dirname "$0")/.."

hex() { head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'; }

touch .env
chmod 600 .env

secret_kind=""
added=0
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    "# secret:"*) secret_kind="$line"; continue ;;
    "#"* | "") secret_kind=""; continue ;;
  esac
  key=${line%%=*}
  value=${line#*=}
  if ! grep -q "^${key}=" .env; then
    if [ -n "$secret_kind" ] && [ -z "$value" ]; then
      case "$secret_kind" in
        *'"GK"'*) value="GK$(hex 12)" ;;
        *) value=$(hex 32) ;;
      esac
    fi
    printf '%s=%s\n' "$key" "$value" >> .env
    added=$((added + 1))
  fi
  secret_kind=""
done < .env.example

if [ "$added" -gt 0 ]; then
  echo "env: added ${added} key(s) to .env"
fi
