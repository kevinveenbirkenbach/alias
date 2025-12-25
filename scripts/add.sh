#!/usr/bin/env sh
set -eu

ALIASES_FILE="${1:-aliases}"

die() { echo "ERROR: $*" >&2; exit 1; }

# Escape single quotes for safe single-quoted alias definitions
escape_squotes() {
  # Turns:  foo'bar  ->  foo'"'"'bar
  printf "%s" "$1" | sed "s/'/'\"'\"'/g"
}

alias_exists() {
  name="$1"
  # match: alias NAME=
  grep -Eq "^[[:space:]]*alias[[:space:]]+$name=" "$ALIASES_FILE"
}

is_reserved_name() {
  name="$1"
  # If a binary/script/builtin exists with this name, treat it as reserved.
  # POSIX: command -v exits 0 if resolvable.
  if command -v "$name" >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

reserved_hint() {
  name="$1"
  command -v "$name" 2>/dev/null || true
}

# Build "alias<TAB>full_command" list using awk (prefix expansion like in aliases-table.awk)
alias_full_map() {
  awk '
  function trim(s){ gsub(/^[[:space:]]+|[[:space:]]+$/, "", s); return s }
  function strip_quotes(s){ s=trim(s); gsub(/^'\''|'\''$/, "", s); gsub(/^"|"$/, "", s); return s }

  function parse_alias(line,   l,name,cmd) {
    l=line
    sub(/[[:space:]]*#[[:space:]]*.*/, "", l)
    sub(/^[[:space:]]*alias[[:space:]]+/, "", l)
    name=l; sub(/=.*/, "", name); name=trim(name)
    cmd=l; sub(/^[^=]*=/, "", cmd); cmd=strip_quotes(cmd)
    if (name != "" && cmd != "") amap[name]=cmd
  }

  function resolve_first(cmd,   full,depth,arr,first,rest) {
    full=cmd
    for (depth=0; depth<10; depth++) {
      split(full, arr, /[[:space:]]+/)
      first=arr[1]
      rest=full
      sub("^[^[:space:]]+[[:space:]]*", "", rest)
      if (first in amap) {
        full = (rest != "") ? (amap[first] " " rest) : amap[first]
      } else break
    }
    return full
  }

  FNR==NR {
    if ($0 ~ /^[[:space:]]*alias[[:space:]]+/) parse_alias($0)
    next
  }

  $0 ~ /^[[:space:]]*alias[[:space:]]+/ {
    line=$0
    sub(/[[:space:]]*#[[:space:]]*.*/, "", line)
    sub(/^[[:space:]]*alias[[:space:]]+/, "", line)
    name=line; sub(/=.*/, "", name); name=trim(name)
    cmd=line; sub(/^[^=]*=/, "", cmd); cmd=strip_quotes(cmd)
    full=resolve_first(cmd)
    if (name != "" && full != "") printf "%s\t%s\n", name, full
  }
  ' "$ALIASES_FILE" "$ALIASES_FILE"
}

# Replace leading full commands with aliases (best match = longest full command)
refactor_command() {
  cmd="$1"

  # Repeat a few rounds to allow chaining: docker compose -> dc, etc.
  i=0
  while [ "$i" -lt 10 ]; do
    best_alias=""
    best_full=""
    best_len=0

    # Find the longest full-command prefix match
    while IFS="$(printf '\t')" read -r a full; do
      [ -n "$a" ] || continue
      [ -n "$full" ] || continue

      case "$cmd" in
        "$full"|"${full} "*)
          l=${#full}
          if [ "$l" -gt "$best_len" ]; then
            best_len="$l"
            best_alias="$a"
            best_full="$full"
          fi
          ;;
      esac
    done <<EOF
$(alias_full_map)
EOF

    [ -n "$best_alias" ] || break

    # Replace prefix
    rest="$cmd"
    rest="${rest#"$best_full"}"
    rest="$(printf "%s" "$rest" | sed 's/^[[:space:]]\+//')"

    if [ -n "$rest" ]; then
      cmd="$best_alias $rest"
    else
      cmd="$best_alias"
    fi

    i=$((i + 1))
  done

  printf "%s" "$cmd"
}

[ -f "$ALIASES_FILE" ] || die "aliases file not found: $ALIASES_FILE"

printf "Command to add: "
IFS= read -r raw_cmd
[ -n "$raw_cmd" ] || die "command must not be empty"

ref_cmd="$(refactor_command "$raw_cmd")"

echo "Refactored command:"
echo "  $ref_cmd"
echo

# Ask for alias name (loop until unique and not reserved)
while :; do
  printf "Alias name: "
  IFS= read -r name
  [ -n "$name" ] || { echo "Alias name must not be empty."; continue; }

  # Allow typical shell-ish names
  echo "$name" | grep -Eq '^[A-Za-z0-9._-]+$' || { echo "Invalid alias name. Use letters/numbers/._-"; continue; }

  if alias_exists "$name"; then
    echo "Alias '$name' already exists in $ALIASES_FILE. Choose another."
    continue
  fi

  if is_reserved_name "$name"; then
    resolved="$(reserved_hint "$name")"
    if [ -n "$resolved" ]; then
      echo "Name '$name' is reserved (already resolves to: $resolved). Choose another."
    else
      echo "Name '$name' is reserved (already exists as a command/builtin). Choose another."
    fi
    continue
  fi

  break
done

printf "Comment (optional): "
IFS= read -r comment || comment=""

escaped_cmd="$(escape_squotes "$ref_cmd")"

line="alias $name='$escaped_cmd'"
if [ -n "$comment" ]; then
  line="$line # $comment"
fi

# Ensure file ends with newline, then append
tail -c 1 "$ALIASES_FILE" 2>/dev/null | grep -q '^$' || printf "\n" >> "$ALIASES_FILE"
printf "%s\n" "$line" >> "$ALIASES_FILE"

echo "Added:"
echo "  $line"
