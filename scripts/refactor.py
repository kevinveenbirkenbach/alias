#!/usr/bin/env python3
"""
refactor.py (Option B++)

Controlled 1-hop normalization + safe prefix rewrites.

Goals:
- Replace repeated command sequences with an existing canonical alias
  (shortest name, then lexicographic), including sequences spanning operators
  like &&, ||, |, ;.
- Additionally, normalize by expanding ONLY the FIRST TOKEN of EACH SEGMENT
  by ONE alias hop, without recursion and without expanding across operators.
- IMPORTANT: Also refactor within each segment by replacing the longest
  alias-body PREFIX. This enables:
    - "docker compose up" -> "dc up"
    - "d compose up"      -> "dc up"
    - "git commit -m x"   -> "gc -m x"

Non-goals:
- Never inline/expand helper aliases into other alias definitions.
- Never recursively expand aliases.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


NAME_CHARS = r"A-Za-z0-9._-"
NAME_RE = re.compile(rf"^[{NAME_CHARS}]+$")

# Split operators while keeping them (with surrounding spaces) as tokens.
OP_SPLIT_RE = re.compile(r"(\s*(?:&&|\|\||\||;)\s*)")

# Normalize operator spacing and whitespace.
OP_NORM_RE = re.compile(r"\s*(&&|\|\||\||;)\s*")
WS_RE = re.compile(r"\s+")


@dataclass
class AliasLine:
    original: str
    prefix: str
    name: str
    cmd_raw: str
    ws_before_hash: str
    comment: str


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
    """Return (leading_ws, quote, inner, trailing_ws)."""
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


def choose_canonical(names: List[str]) -> str:
    return sorted(names, key=lambda a: (len(a), a))[0]


def split_by_ops(inner: str) -> List[str]:
    """Split into [segment, op, segment, ...] keeping operator tokens."""
    parts = OP_SPLIT_RE.split(inner)
    return [p for p in parts if p != ""]


def first_token(s: str) -> str:
    s = s.strip()
    if not s:
        return ""
    return s.split()[0]


def strip_first_token(s: str) -> str:
    s = s.strip()
    if not s:
        return ""
    parts = s.split(maxsplit=1)
    return parts[1] if len(parts) == 2 else ""


def normalize_whitespace_ops(s: str) -> str:
    s = s.strip()
    if not s:
        return ""
    s = OP_NORM_RE.sub(r" \1 ", s)
    s = WS_RE.sub(" ", s)
    return s.strip()


def build_alias_body_1hop(raw_inner_for_alias: Dict[str, str]) -> Dict[str, str]:
    """
    alias -> body where body's FIRST TOKEN is expanded by one hop if it's an alias.
    No recursion.
    """
    out: Dict[str, str] = {}
    for name, raw in raw_inner_for_alias.items():
        raw = raw.strip()
        if not raw:
            out[name] = ""
            continue

        head = first_token(raw)
        rest = strip_first_token(raw)

        if head in raw_inner_for_alias:
            head_repl = raw_inner_for_alias[head].strip()
        else:
            head_repl = head

        out[name] = (f"{head_repl} {rest}".strip() if rest else head_repl).strip()
    return out


def normalize_for_match(s: str, alias_body_1hop: Dict[str, str]) -> str:
    """
    Normalize string for matching:
    - For each operator-delimited segment: if first token is an alias,
      replace that token with alias_body_1hop[alias] (one hop only).
    - Then normalize operator spacing and collapse whitespace.
    """
    s = s.strip()
    if not s:
        return ""

    tokens = split_by_ops(s)
    out: List[str] = []
    for t in tokens:
        if OP_SPLIT_RE.fullmatch(t):
            out.append(t)
            continue

        seg = t.strip()
        if not seg:
            out.append(seg)
            continue

        head = first_token(seg)
        rest = strip_first_token(seg)

        if head in alias_body_1hop:
            head_repl = alias_body_1hop[head]
            seg_norm = (f"{head_repl} {rest}".strip() if rest else head_repl).strip()
        else:
            seg_norm = seg

        out.append(seg_norm)

    return normalize_whitespace_ops("".join(out))


def build_norm_patterns(
    raw_inner_for_alias: Dict[str, str],
    alias_body_1hop: Dict[str, str],
) -> Tuple[Dict[str, str], List[str]]:
    """
    Build:
      canonical_for_norm: norm_pattern -> canonical_alias
      norm_patterns_sorted: patterns sorted by length desc
    """
    norm_to_aliases: Dict[str, List[str]] = {}
    for name, raw in raw_inner_for_alias.items():
        norm = normalize_for_match(raw, alias_body_1hop)
        if not norm:
            continue
        norm_to_aliases.setdefault(norm, []).append(name)

    canonical_for_norm = {norm: choose_canonical(names) for norm, names in norm_to_aliases.items()}
    norm_patterns_sorted = sorted(canonical_for_norm.keys(), key=lambda n: (-len(n), n))
    return canonical_for_norm, norm_patterns_sorted


def refactor_segment_prefix(
    seg: str,
    current_alias_name: str,
    alias_body_1hop: Dict[str, str],
    canonical_for_norm: Dict[str, str],
    norm_patterns_sorted: List[str],
) -> str:
    """
    Within a single operator-delimited segment, replace the longest matching
    alias-body prefix (under normalized form) with its canonical alias.

    Example:
      "docker compose up" -> "dc up"
      "d compose up"      -> "dc up" (d one-hop -> docker)
      "git commit -m x"   -> "gc -m x"
    """
    orig_ws = seg[: len(seg) - len(seg.lstrip())]
    seg_strip = seg.strip()
    if not seg_strip:
        return seg

    seg_norm = normalize_for_match(seg_strip, alias_body_1hop)

    for pat in norm_patterns_sorted:
        canon = canonical_for_norm[pat]

        # Never inject the current alias into its own body.
        if canon == current_alias_name:
            continue

        if seg_norm == pat:
            return orig_ws + canon

        if seg_norm.startswith(pat + " "):
            rest_norm = seg_norm[len(pat) :].lstrip()
            # Keep the rest as normalized; we don't try to preserve original micro-spacing.
            return orig_ws + (f"{canon} {rest_norm}".strip())

    return seg


def refactor_inner(
    inner: str,
    current_alias_name: str,
    alias_body_1hop: Dict[str, str],
    canonical_for_norm: Dict[str, str],
    norm_patterns_sorted: List[str],
) -> str:
    """
    1) Prefix rewrite per segment (handles docker compose up -> dc up, git commit -m -> gc -m)
    2) Then window rewrite across operator tokens (handles asort && au -> asu, etc.)
       with the IMPORTANT rule: if a window maps to the current alias, skip it and keep searching.
    """
    tokens = split_by_ops(inner)
    if not tokens:
        return inner

    # Step 1: prefix rewrite inside each segment
    for idx, t in enumerate(tokens):
        if OP_SPLIT_RE.fullmatch(t):
            continue
        tokens[idx] = refactor_segment_prefix(
            seg=t,
            current_alias_name=current_alias_name,
            alias_body_1hop=alias_body_1hop,
            canonical_for_norm=canonical_for_norm,
            norm_patterns_sorted=norm_patterns_sorted,
        )

    changed = False
    i = 0
    while i < len(tokens):
        did_replace = False

        for pat in norm_patterns_sorted:
            canon = canonical_for_norm[pat]

            for j in range(i + 1, len(tokens) + 1):
                window = "".join(tokens[i:j])
                win_norm = normalize_for_match(window, alias_body_1hop)

                if win_norm != pat:
                    continue

                # CRITICAL: do NOT "consume" self-matches; keep searching smaller matches.
                if canon == current_alias_name:
                    continue

                tokens = tokens[:i] + [canon] + tokens[j:]
                changed = True
                did_replace = True
                break

            if did_replace:
                break

        i += 1

    out = "".join(tokens)
    return out if changed else out  # keep prefix-rewrite changes regardless


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

    raw_inner_for_alias: Dict[str, str] = {}
    for al in parsed:
        _, _, inner, _ = unwrap_cmd(al.cmd_raw)
        raw_inner_for_alias[al.name] = inner.strip()

    alias_body_1hop = build_alias_body_1hop(raw_inner_for_alias)
    canonical_for_norm, norm_patterns_sorted = build_norm_patterns(raw_inner_for_alias, alias_body_1hop)

    changed_any = False
    out_lines: List[str] = []

    for line in lines:
        al = parse_alias_line(line)
        if not al:
            out_lines.append(line)
            continue

        leading_ws, quote, inner, trailing_ws = unwrap_cmd(al.cmd_raw)

        new_inner = refactor_inner(
            inner=inner,
            current_alias_name=al.name,
            alias_body_1hop=alias_body_1hop,
            canonical_for_norm=canonical_for_norm,
            norm_patterns_sorted=norm_patterns_sorted,
        )

        if new_inner != inner:
            changed_any = True

        new_cmd_raw = rewrap_cmd(leading_ws, quote, new_inner, trailing_ws)
        rebuilt = f"{al.prefix}{al.name}={new_cmd_raw}"
        if al.comment:
            rebuilt += al.ws_before_hash + al.comment
        out_lines.append(rebuilt)

    aliases_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    if changed_any:
        print(f"Refactor completed: updated {aliases_path}")
    else:
        print("No refactor changes were necessary.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
