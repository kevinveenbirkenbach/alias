#!/usr/bin/env sh
set -eu

q="${1:-}"
ALIAS_FILE="${2:-aliases}"

if [ -z "$q" ]; then
  echo "ERROR: missing query."
  echo "Usage: scripts/search.sh <query> [aliases-file]"
  exit 2
fi

awk -v mode=search -v q="$q" -f scripts/aliases-table.awk "$ALIAS_FILE" "$ALIAS_FILE"
