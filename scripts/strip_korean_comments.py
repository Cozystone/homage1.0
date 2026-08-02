# -*- coding: utf-8 -*-
"""Safe bulk Korean removal — COMMENTS ONLY (the half that can be nuked at once).

Owner asked (2026-07-19): "can't we just delete all 16,932 Korean remnants at once?" Honest
split: comments and docstrings never execute, so removing their Korean cannot change behavior —
that half is safe to bulk-strip NOW. The other half (regexes, dict keys, user-facing strings)
DOES execute: a blank alternation matches everything, a missing key crashes mid-answer, a blanked
message returns empty. Those need the governed per-file pass. This tool does the safe half.

Method (byte-precise, never touches code): tokenize each file, find COMMENT tokens containing
Hangul, and cut the comment at its start column (rstrip). Only comment spans are edited; every
executing character is left byte-identical. Each rewritten file is compile-checked in memory and
skipped (never written) if compilation fails or the Hangul count did not actually drop.

Docstrings are deliberately EXCLUDED (they are runtime objects some code introspects) — handled
in the governed pass. Usage: python scripts/strip_korean_comments.py [--apply]  (dry-run default)
"""
from __future__ import annotations

import io
import re
import sys
import tokenize
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HAN = re.compile(r"[가-힣㄰-㆏ᄀ-ᇿ]")
ROOTS = ["packages", "scripts", "apps/api"]
APPLY = "--apply" in sys.argv


def strip_file(path: Path) -> tuple[int, int, bool]:
    """Return (hangul_before, hangul_after, changed_ok). Writes only when --apply and safe."""
    src = path.read_text(encoding="utf-8", errors="ignore")
    before = len(HAN.findall(src))
    if not before:
        return 0, 0, False
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except Exception:
        return before, before, False
    cuts: dict[int, int] = {}
    for t in toks:
        if t.type == tokenize.COMMENT and HAN.search(t.string):
            cuts[t.start[0]] = min(cuts.get(t.start[0], 10**9), t.start[1])
    if not cuts:
        return before, before, False
    lines = src.splitlines(keepends=True)
    for lineno, col in cuts.items():
        line = lines[lineno - 1]
        nl = "\n" if line.endswith("\n") else ""
        lines[lineno - 1] = line[:col].rstrip() + nl
    new = "".join(lines)
    after = len(HAN.findall(new))
    try:
        compile(new, str(path), "exec")
    except SyntaxError:
        return before, before, False          # corruption guard: never write a non-compiling file
    if after >= before:
        return before, before, False
    if APPLY:
        path.write_text(new, encoding="utf-8")
    return before, after, True


def main() -> int:
    files = 0
    removed = 0
    touched = 0
    for root in ROOTS:
        for p in (REPO / root).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            b, a, ok = strip_file(p)
            if b:
                files += 1
            if ok:
                touched += 1
                removed += (b - a)
    verb = "removed from" if APPLY else "removable from (dry-run)"
    print(f"comment Korean {verb} {touched} files: {removed} Hangul chars")
    print(f"(files with any Hangul scanned: {files})")
    if not APPLY:
        print("\nrun with --apply to write. Code literals are NOT touched — governed pass owns those.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
