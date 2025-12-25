#!/usr/bin/env sh
set -eu

NAME="${1:-}"
ALIASES_FILE="${2:-aliases}"

if [ -z "$NAME" ]; then
  echo "ERROR: missing alias name."
  echo "Usage: scripts/export.sh <alias> [aliases-file]"
  exit 2
fi

[ -f "$ALIASES_FILE" ] || { echo "ERROR: aliases file not found: $ALIASES_FILE" >&2; exit 2; }

awk -v target="$NAME" '
function trim(s){ gsub(/^[[:space:]]+|[[:space:]]+$/, "", s); return s }
function strip_quotes(s){
  s=trim(s)
  gsub(/^'\''|'\''$/, "", s)
  gsub(/^"|"$/, "", s)
  return s
}

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
  for (depth=0; depth<50; depth++) {
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

function export_command(cmd,   out,seg,op,resolved) {
  out=""
  while (cmd != "") {
    # operator scan: &&  ||  |  ;
    if (match(cmd, /[[:space:]]*(&&|\|\||\||;)[[:space:]]*/)) {
      seg = substr(cmd, 1, RSTART-1)
      op  = substr(cmd, RSTART, RLENGTH)
      cmd = substr(cmd, RSTART+RLENGTH)

      seg = trim(seg)
      resolved = resolve_first(seg)
      out = out (out=="" ? "" : " ") resolved " " trim(op)
    } else {
      seg = trim(cmd)
      resolved = resolve_first(seg)
      out = out (out=="" ? "" : " ") resolved
      break
    }
  }

  # normalize whitespace
  gsub(/[[:space:]]+/, " ", out)
  out = trim(out)
  return out
}

{
  if ($0 ~ /^[[:space:]]*alias[[:space:]]+/) parse_alias($0)
}

END {
  if (!(target in amap)) {
    print "ERROR: alias not found: " target > "/dev/stderr"
    exit 2
  }
  print export_command(amap[target])
}
' "$ALIASES_FILE"
