# -*- coding: utf-8 -*-
"""Safe bulk Korean removal — DOCSTRINGS (the second half of the safe set).

Docstrings are string statements; __doc__ is almost never introspected for logic (verified: no
code in packages/ or apps/api matches Korean against __doc__). Removing Korean glyphs from a
docstring leaves a valid string and cannot change behavior — so this is safe to bulk-apply, unlike
code literals (regexes/keys/user-text) which the governed per-file surgery owns.

Method: tokenize each file; for STRING tokens that are docstrings (a string appearing as its own
statement, i.e. the previous significant token was NEWLINE/INDENT/DEDENT/ENCODING), delete only the
Hangul glyphs (syllables + jamo) from the token, splicing by absolute char offset so every other
byte is untouched. Triple quotes, English prose, punctuation and structure all survive. Each file
is compile-checked in memory; never written if it fails to compile or the Hangul count did not drop.

Usage: python scripts/strip_korean_docstrings.py [--apply]   (dry-run default)
"""
from __future__ import annotations

import io
import re
import sys
import token
import tokenize
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HAN = re.compile(r"[가-힣㄰-㆏ᄀ-ᇿ]")
ROOTS = ["packages", "scripts", "apps/api"]
APPLY = "--apply" in sys.argv
_DOC_PREV = {token.NEWLINE, token.INDENT, token.DEDENT, token.NL, token.ENCODING}


def _line_starts(src: str) -> list[int]:
    offs, pos = [0], 0
    for line in src.splitlines(keepends=True):
        pos += len(line)
        offs.append(pos)
    return offs


def strip_file(path: Path) -> tuple[int, int, bool]:
    src = path.read_text(encoding="utf-8", errors="ignore")
    before = len(HAN.findall(src))
    if not before:
        return 0, 0, False
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except Exception:
        return before, before, False
    starts = _line_starts(src)
    edits: list[tuple[int, int, str]] = []       # (abs_start, abs_end, new_text)
    prev = token.ENCODING
    for t in toks:
        if t.type == tokenize.STRING and HAN.search(t.string) and prev in _DOC_PREV:
            a = starts[t.start[0] - 1] + t.start[1]
            b = starts[t.end[0] - 1] + t.end[1]
            new = HAN.sub("", t.string)
            new = re.sub(r"[ \t]{2,}", " ", new)     # tidy the gaps the glyphs left
            edits.append((a, b, new))
        if t.type not in (token.NL, tokenize.COMMENT):
            prev = t.type
    if not edits:
        return before, before, False
    chars = list(src)
    for a, b, new in reversed(edits):            # back-to-front keeps offsets valid
        chars[a:b] = new
    out = "".join(chars)
    after = len(HAN.findall(out))
    try:
        compile(out, str(path), "exec")
    except SyntaxError:
        return before, before, False
    if after >= before:
        return before, before, False
    if APPLY:
        path.write_text(out, encoding="utf-8")
    return before, after, True


def main() -> int:
    touched = removed = files = 0
    for root in ROOTS:
        for p in (REPO / root).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            b, a, ok = strip_file(p)
            if b:
                files += 1
            if ok:
                touched += 1
                removed += b - a
    verb = "removed from" if APPLY else "removable from (dry-run)"
    print(f"docstring Korean {verb} {touched} files: {removed} Hangul chars (scanned {files})")
    if not APPLY:
        print("run with --apply to write. Code literals are NOT touched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
