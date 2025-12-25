#!/usr/bin/env sh
set -eu

ALIAS_FILE="${1:-aliases}"
awk -f scripts/aliases-table.awk "$ALIAS_FILE" "$ALIAS_FILE"
