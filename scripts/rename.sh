#!/usr/bin/env sh
set -eu

ALIASES_FILE="${1:-aliases}"
OLD="${2:-}"
NEW="${3:-}"

die() { echo "ERROR: $*" >&2; exit 1; }

[ -f "$ALIASES_FILE" ] || die "aliases file not found: $ALIASES_FILE"
[ -n "$OLD" ] || die "missing old name"
[ -n "$NEW" ] || die "missing new name"

# basic validation
echo "$OLD" | grep -Eq '^[A-Za-z0-9._-]+$' || die "invalid old name: $OLD"
echo "$NEW" | grep -Eq '^[A-Za-z0-9._-]+$' || die "invalid new name: $NEW"
[ "$OLD" = "$NEW" ] && die "old and new are the same"

alias_exists() {
  grep -Eq "^[[:space:]]*alias[[:space:]]+$1=" "$ALIASES_FILE"
}

is_reserved_name() {
  command -v "$1" >/dev/null 2>&1
}

reserved_hint() {
  command -v "$1" 2>/dev/null || true
}

alias_exists "$OLD" || die "alias '$OLD' not found in $ALIASES_FILE"

if alias_exists "$NEW"; then
  die "new name '$NEW' already exists as an alias"
fi

if is_reserved_name "$NEW"; then
  r="$(reserved_hint "$NEW")"
  [ -n "$r" ] && die "new name '$NEW' is reserved (resolves to: $r)"
  die "new name '$NEW' is reserved (command/builtin)"
fi

python3 - "$ALIASES_FILE" "$OLD" "$NEW" <<'PY'
import re
import sys
from pathlib import Path

aliases_path = Path(sys.argv[1])
old = sys.argv[2]
new = sys.argv[3]

name_chars = r"A-Za-z0-9._-"
boundary = re.compile(rf"(?<![{name_chars}]){re.escape(old)}(?![{name_chars}])")

def split_comment_unquoted(line: str):
    """
    Split a line into:
      code_without_trailing_ws,
      whitespace_before_hash,
      comment_starting_with_hash
    preserving whitespace exactly.
    """
    in_s = in_d = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            code = line[:i]
            comment = line[i:]
            m = re.search(r"(\s*)$", code)
            ws = m.group(1) if m else ""
            code_wo_ws = code[:-len(ws)] if ws else code
            return code_wo_ws, ws, comment
    return line, "", ""

lines = aliases_path.read_text(encoding="utf-8").splitlines()
out = []
changed = False

for line in lines:
    if not line.lstrip().startswith("alias "):
        out.append(line)
        continue

    code, ws, comment = split_comment_unquoted(line)

    m = re.match(r"^(\s*alias\s+)([^=]+)=(.*)$", code)
    if not m:
        out.append(line)
        continue

    prefix, name, cmd = m.groups()
    name = name.strip()

    if name == old:
        name = new
        changed = True

    new_cmd = boundary.sub(new, cmd)
    if new_cmd != cmd:
        changed = True

    rebuilt = f"{prefix}{name}={new_cmd}"
    if comment:
        rebuilt += ws + comment

    out.append(rebuilt)

aliases_path.write_text("\n".join(out) + "\n", encoding="utf-8")

if changed:
    print(f"Renamed '{old}' -> '{new}' in {aliases_path}")
else:
    print(f"No changes made (alias '{old}' not referenced)")
PY

echo "Tip: run 'make sort' afterwards if you keep aliases sorted."
