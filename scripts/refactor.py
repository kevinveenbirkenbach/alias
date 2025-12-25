#!/usr/bin/env python3
"""
refactor.py

Refactors shell aliases by:
1) Detecting duplicate commands (same expanded "full command") and replacing usages
   with a canonical alias (shortest name, then lexicographic).
2) Auto-generating aliases for repeated plain command segments that currently have
   no alias representation, replacing those segments with `auto_<sanitized>` aliases.

Important safety rules:
- Never refactor an alias definition into itself (prevents recursion like: alias ad='ad').
- Only auto-alias "plain commands" (skip shell function syntax, braces, etc.).
- Auto-alias only when the segment is not already using an alias (segment == expanded full).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


NAME_CHARS = r"A-Za-z0-9._-"
NAME_RE = re.compile(rf"^[{NAME_CHARS}]+$")

# Conservative operator split (keeps operators as tokens)
OP_SPLIT_RE = re.compile(r"(\s*(?:&&|\|\||\||;)\s*)")

# For sanitizing auto alias names
AUTO_SAFE_RE = re.compile(r"[^a-z0-9_-]+")
MULTI_UNDERSCORE_RE = re.compile(r"_+")

# "command-ish" first token (keeps it conservative)
CMDISH_FIRST_TOKEN_RE = re.compile(r"^[A-Za-z0-9._/-]+$")

# Things we treat as "not a plain command segment"
SHELL_SYNTAX_CHARS = set("{}()")


@dataclass
class AliasLine:
    original: str
    prefix: str          # includes indentation + "alias "
    name: str
    cmd_raw: str         # text after '=' (as-is, without comment)
    ws_before_hash: str  # exact whitespace before '#'
    comment: str         # '# ...' exact, or ''


def split_comment_unquoted(line: str) -> Tuple[str, str, str]:
    """Preserve whitespace before '#', treat # as comment only outside quotes."""
    in_s = False
    in_d = False
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


def parse_alias_line(line: str) -> AliasLine | None:
    if not line.lstrip().startswith("alias "):
        return None

    code, ws, comment = split_comment_unquoted(line)
    m = re.match(r"^(\s*alias\s+)([^=]+)=(.*)$", code)
    if not m:
        return None

    prefix, name, cmd_raw = m.groups()
    name = name.strip()
    if not NAME_RE.match(name):
        return None

    return AliasLine(
        original=line,
        prefix=prefix,
        name=name,
        cmd_raw=cmd_raw,
        ws_before_hash=ws,
        comment=comment,
    )


def unwrap_cmd(cmd_raw: str) -> Tuple[str, str, str, str]:
    """Return (leading_ws, quote, inner, trailing_ws). Unwrap full-string quotes if present."""
    m = re.match(r"^(\s*)(.*?)(\s*)$", cmd_raw, flags=re.DOTALL)
    leading_ws, body, trailing_ws = m.group(1), m.group(2), m.group(3)

    if len(body) >= 2 and body[0] == body[-1] and body[0] in ("'", '"'):
        quote = body[0]
        inner = body[1:-1]
        return leading_ws, quote, inner, trailing_ws

    return leading_ws, "", body, trailing_ws


def rewrap_cmd(leading_ws: str, quote: str, inner: str, trailing_ws: str) -> str:
    if quote:
        return f"{leading_ws}{quote}{inner}{quote}{trailing_ws}"
    return f"{leading_ws}{inner}{trailing_ws}"


def first_token(s: str) -> str:
    s = s.lstrip()
    if not s:
        return ""
    return re.split(r"\s+", s, maxsplit=1)[0]


def strip_first_token(s: str) -> str:
    s2 = s.lstrip()
    if not s2:
        return ""
    parts = re.split(r"\s+", s2, maxsplit=1)
    if len(parts) == 1:
        return ""
    return parts[1]


def expand_prefix_aliases(cmd: str, alias_to_cmd: Dict[str, str], depth: int = 10) -> str:
    """Expand only the leading token via alias map, repeated for chaining."""
    cur = cmd
    for _ in range(depth):
        tok = first_token(cur)
        if tok and tok in alias_to_cmd:
            rest = strip_first_token(cur)
            repl = alias_to_cmd[tok]
            cur = f"{repl} {rest}".rstrip() if rest else repl
        else:
            break
    return cur


def choose_canonical(aliases: List[str]) -> str:
    return sorted(aliases, key=lambda a: (len(a), a))[0]


def sanitize_auto_name(command_segment: str, max_len: int = 48) -> str:
    s = command_segment.strip().lower()
    s = AUTO_SAFE_RE.sub("_", s)
    s = MULTI_UNDERSCORE_RE.sub("_", s).strip("_")
    if not s:
        s = "cmd"
    if len(s) > max_len:
        s = s[:max_len].rstrip("_")
    return f"auto_{s}"


def split_by_ops(inner: str) -> List[str]:
    parts = OP_SPLIT_RE.split(inner)
    return [p for p in parts if p]


def is_plain_segment(seg_strip: str) -> bool:
    """
    We only consider 'plain command segments' for auto-aliasing.
    Skip function bodies, braces, and other shell-ish syntax.
    """
    if not seg_strip:
        return False

    # avoid tiny garbage like "}" or "f"
    if len(seg_strip) < 2:
        return False

    # braces/parentheses often indicate shell syntax/functions/subshell
    if any(ch in SHELL_SYNTAX_CHARS for ch in seg_strip):
        return False

    tok = first_token(seg_strip)
    if not tok:
        return False

    # reject obvious shell keywords/prefixes
    if tok in {"if", "then", "fi", "for", "do", "done", "while", "case", "esac", "function"}:
        return False

    # token should look like a command name/path
    if not CMDISH_FIRST_TOKEN_RE.match(tok):
        return False

    return True


def refactor_segment(
    seg: str,
    alias_to_cmd: Dict[str, str],
    canonical_for_full: Dict[str, str],
    current_alias_name: str,
    full_for_alias: Dict[str, str],
) -> str:
    """
    Replace the longest full-command prefix with canonical alias,
    but NEVER rewrite the defining alias into itself (prevents recursion).
    """
    original = seg
    seg_strip = seg.lstrip()
    if not seg_strip:
        return original

    full = expand_prefix_aliases(seg_strip, alias_to_cmd)

    for full_prefix in sorted(canonical_for_full.keys(), key=len, reverse=True):
        if full == full_prefix or full.startswith(full_prefix + " "):
            alias = canonical_for_full[full_prefix]
            # prevent: alias X='<full_of_X>' -> alias X='X'
            if (
                alias == current_alias_name
                and current_alias_name in full_for_alias
                and full_prefix == full_for_alias[current_alias_name]
            ):
                return original

            rest = full[len(full_prefix):].lstrip()
            new_seg = f"{alias} {rest}".rstrip() if rest else alias
            replaced = seg[: len(seg) - len(seg.lstrip())] + new_seg
            return replaced if replaced != original else original

    return original


def refactor_command(
    inner: str,
    alias_to_cmd: Dict[str, str],
    canonical_for_full: Dict[str, str],
    current_alias_name: str,
    full_for_alias: Dict[str, str],
) -> str:
    parts = split_by_ops(inner)
    out: List[str] = []
    for p in parts:
        if OP_SPLIT_RE.fullmatch(p):
            out.append(p)
        else:
            out.append(refactor_segment(p, alias_to_cmd, canonical_for_full, current_alias_name, full_for_alias))
    return "".join(out)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: refactor.py <aliases-file>", file=sys.stderr)
        return 2

    aliases_path = Path(sys.argv[1])
    if not aliases_path.exists():
        print(f"ERROR: aliases file not found: {aliases_path}", file=sys.stderr)
        return 2

    lines = aliases_path.read_text(encoding="utf-8").splitlines()

    parsed: List[AliasLine] = []
    for line in lines:
        al = parse_alias_line(line)
        if al:
            parsed.append(al)

    # alias -> inner command (unwrapped)
    alias_to_cmd_inner: Dict[str, str] = {}
    for al in parsed:
        _, _, inner, _ = unwrap_cmd(al.cmd_raw)
        alias_to_cmd_inner[al.name] = inner

    # full command for each alias (used for recursion prevention)
    full_for_alias: Dict[str, str] = {
        name: expand_prefix_aliases(inner, alias_to_cmd_inner)
        for name, inner in alias_to_cmd_inner.items()
    }

    # duplicates: full -> [aliases]
    dupes: Dict[str, List[str]] = {}
    for a, full in full_for_alias.items():
        dupes.setdefault(full, []).append(a)

    canonical_for_full: Dict[str, str] = {full: choose_canonical(names) for full, names in dupes.items()}

    # ---------- Phase 1: refactor existing usages to canonical aliases ----------
    phase1_changed = False
    phase1_lines: List[str] = []

    for line in lines:
        al = parse_alias_line(line)
        if not al:
            phase1_lines.append(line)
            continue

        leading_ws, quote, inner, trailing_ws = unwrap_cmd(al.cmd_raw)
        new_inner = refactor_command(
            inner,
            alias_to_cmd_inner,
            canonical_for_full,
            current_alias_name=al.name,
            full_for_alias=full_for_alias,
        )
        if new_inner != inner:
            phase1_changed = True

        new_cmd_raw = rewrap_cmd(leading_ws, quote, new_inner, trailing_ws)
        rebuilt = f"{al.prefix}{al.name}={new_cmd_raw}"
        if al.comment:
            rebuilt += al.ws_before_hash + al.comment
        phase1_lines.append(rebuilt)

    # Re-parse after phase1 (for auto-alias stage)
    phase2_parsed: List[AliasLine] = []
    for line in phase1_lines:
        al = parse_alias_line(line)
        if al:
            phase2_parsed.append(al)

    phase2_alias_to_inner: Dict[str, str] = {}
    for al in phase2_parsed:
        _, _, inner, _ = unwrap_cmd(al.cmd_raw)
        phase2_alias_to_inner[al.name] = inner

    # Existing alias coverage (full -> canonical existing alias)
    phase2_full_for_alias: Dict[str, str] = {
        name: expand_prefix_aliases(inner, phase2_alias_to_inner)
        for name, inner in phase2_alias_to_inner.items()
    }
    full_to_some_alias: Dict[str, List[str]] = {}
    for name, full in phase2_full_for_alias.items():
        full_to_some_alias.setdefault(full, []).append(name)
    full_to_canonical_existing = {full: choose_canonical(names) for full, names in full_to_some_alias.items()}

    # ---------- Phase 2: auto-alias repeated *plain* segments with no alias ----------
    seg_full_counts: Dict[str, int] = {}

    # Only count segments that are plain AND not already using an alias (segment == expanded full)
    for al in phase2_parsed:
        _, _, inner, _ = unwrap_cmd(al.cmd_raw)
        for part in split_by_ops(inner):
            if OP_SPLIT_RE.fullmatch(part):
                continue
            seg_strip = part.lstrip()
            if not is_plain_segment(seg_strip):
                continue
            seg_full = expand_prefix_aliases(seg_strip, phase2_alias_to_inner)
            if seg_strip != seg_full:
                # already using an alias chain -> do not auto-alias
                continue
            seg_full_counts[seg_full] = seg_full_counts.get(seg_full, 0) + 1

    auto_targets = sorted(
        [
            full
            for full, cnt in seg_full_counts.items()
            if cnt >= 2 and full not in full_to_canonical_existing
        ],
        key=lambda s: (-seg_full_counts[s], s),
    )

    existing_names = set(phase2_alias_to_inner.keys())
    auto_map: Dict[str, str] = {}  # full_command -> auto_alias_name

    for full in auto_targets:
        base = sanitize_auto_name(full)
        name = base
        i = 2
        while name in existing_names:
            name = f"{base}_{i}"
            i += 1
        existing_names.add(name)
        auto_map[full] = name

    phase2_changed = False
    final_lines: List[str] = []

    for line in phase1_lines:
        al = parse_alias_line(line)
        if not al:
            final_lines.append(line)
            continue

        leading_ws, quote, inner, trailing_ws = unwrap_cmd(al.cmd_raw)
        parts = split_by_ops(inner)
        new_parts: List[str] = []

        for p in parts:
            if OP_SPLIT_RE.fullmatch(p):
                new_parts.append(p)
                continue

            seg = p
            seg_strip = seg.lstrip()
            if not seg_strip:
                new_parts.append(seg)
                continue

            if not is_plain_segment(seg_strip):
                new_parts.append(seg)
                continue

            seg_full = expand_prefix_aliases(seg_strip, phase2_alias_to_inner)

            # only replace if it truly has no alias use yet (segment == full)
            if seg_strip == seg_full and seg_full in auto_map:
                auto_name = auto_map[seg_full]
                new_seg = seg[: len(seg) - len(seg.lstrip())] + auto_name
                if new_seg != seg:
                    phase2_changed = True
                new_parts.append(new_seg)
            else:
                new_parts.append(seg)

        new_inner = "".join(new_parts)
        if new_inner != inner:
            phase2_changed = True

        new_cmd_raw = rewrap_cmd(leading_ws, quote, new_inner, trailing_ws)
        rebuilt = f"{al.prefix}{al.name}={new_cmd_raw}"
        if al.comment:
            rebuilt += al.ws_before_hash + al.comment
        final_lines.append(rebuilt)

    appended_any = False
    if auto_map:
        final_lines.append("")
        final_lines.append("# --- auto-generated aliases (refactor.py) ---")
        appended_any = True
        for full, name in sorted(auto_map.items(), key=lambda kv: kv[1]):
            escaped = full.replace("'", "'\"'\"'")
            final_lines.append(f"alias {name}='{escaped}' # auto-generated")

    aliases_path.write_text("\n".join(final_lines) + "\n", encoding="utf-8")

    # Report
    dupe_groups = [(full, names) for full, names in dupes.items() if len(names) > 1]
    if dupe_groups:
        print("Duplicate commands detected:")
        for full, names in sorted(dupe_groups, key=lambda x: (len(x[1]), x[0]), reverse=True):
            canon = canonical_for_full[full]
            others = [n for n in names if n != canon]
            print(f"  - canonical: {canon} | duplicates: {', '.join(others)} | full: {full}")

    if auto_map:
        print("Auto-generated aliases:")
        for full, name in sorted(auto_map.items(), key=lambda kv: kv[1]):
            print(f"  - {name} = {full} (seen {seg_full_counts[full]}x)")

    if phase1_changed or phase2_changed or appended_any:
        print(f"Refactor completed: updated {aliases_path}")
    else:
        print("No refactor changes were necessary.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
