# -*- coding: utf-8 -*-
"""Patch protocol — the machine-applicable form a repair must take, and every safety check it must
survive BEFORE a single byte is written.

Owner (2026-07-21): close the self-repair loop. The night proved the open loop's limit — GPT-5.4
flagged 'a german physicist' three separate times and nothing changed, because a critique in prose
cannot be applied by a machine. So the advisor is asked for an EDIT, not an essay.

Why search/replace and not a diff: a diff applies fuzzily (offsets, context drift, partial hunks). A
search/replace either matches EXACTLY ONCE or it is refused — there is no ambiguous middle where a
patch lands somewhere it was not meant to. Refusing is always safe; applying blindly is not.

Doctrine (BINDING): the advisor DRAFTS (body-advice, which is permitted); ATANOR JUDGES by
constitution + measurement, and the judgement is its own. Nothing here decides to keep a change —
that is auto_self_modification's job. This module only decides whether a proposal is well-formed and
eligible to be tried at all.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from packages.continuous_self.auto_self_modification import touches_constitution

REPO = Path(__file__).resolve().parents[2]

# Self-repair is NARROWER than self-modification in general: it may touch body code under these
# roots only. Data, models, configs, scripts that launch daemons, and anything outside the repo are
# out of scope — a repair fixes how ATANOR works, never what it has measured or recorded.
REPAIR_ROOTS = ("packages/",)
# ...and never these, on top of the constitution (which already covers the moral core, the gates,
# and — since the loop closed — the whole test suite).
REPAIR_FORBIDDEN = (
    "packages/self_repair/",          # the repair organ may not repair itself into a new shape
    "packages/graph_scale/",          # the store layer: data integrity, not behaviour
)
MAX_EDIT_BYTES = 4000                 # a repair is a fix, not a rewrite


@dataclass
class Edit:
    path: str
    old: str
    new: str

    def target(self) -> Path:
        return REPO / self.path


# The advisor must answer in exactly this shape. Fenced markers (not indentation) so whitespace in
# the code being edited survives transport intact.
#
# '@@@' and not '<<<': the advisor transport sanitizes cmd.exe metacharacters, and '<' / '>' are
# among them — so a first live patch came back fenced in '‹‹‹' and the parser rejected a perfectly
# good edit. The format markers must themselves be transport-safe. The parser still accepts the
# angle forms, raw or sanitized, so no well-formed proposal is lost to a delimiter.
PATCH_FORMAT = (
    "FILE: <repo-relative path>\n"
    "OLD:\n@@@\nthe exact current line, copied verbatim\n@@@\n"
    "NEW:\n@@@\nthe replacement line\n@@@"
)

_FENCE = r"(?:@@@|<<<|>>>|‹‹‹|›››)"
_PATCH_RE = re.compile(
    rf"FILE:\s*(?P<path>[\w./\\-]+\.py)\s*"
    rf"OLD:\s*{_FENCE}\n(?P<old>.*?)\n?{_FENCE}\s*"
    rf"NEW:\s*{_FENCE}\n(?P<new>.*?)\n?{_FENCE}",
    re.S)


def parse_patch(reply: str) -> tuple[Edit | None, str]:
    """Parse the advisor's reply into an Edit. Returns (edit, reason) — edit is None when the reply
    is not a well-formed patch, and `reason` says why (journaled, never guessed at)."""
    m = _PATCH_RE.search(reply or "")
    if not m:
        return None, "reply is not in the patch format (no FILE/OLD/NEW block)"
    path = m.group("path").replace("\\", "/").lstrip("./")
    old, new = m.group("old"), m.group("new")
    if not old.strip():
        return None, "OLD block is empty — an anchorless edit could match anywhere"
    if old == new:
        return None, "OLD and NEW are identical — no change proposed"
    if len(old) > MAX_EDIT_BYTES or len(new) > MAX_EDIT_BYTES:
        return None, f"edit exceeds {MAX_EDIT_BYTES} bytes — a repair is a fix, not a rewrite"
    if "\n" in old.strip():
        # Single-line anchors only. The advisor transport flattens newlines (the openclaw .cmd shim
        # ends a batch line at '\n'), so a multi-line anchor cannot survive the round trip verbatim
        # and would never match. One line also keeps the blast radius of a repair small.
        return None, "OLD spans multiple lines — anchors must be a single line"
    return Edit(path=path, old=old, new=new), ""


def check_eligible(edit: Edit) -> str:
    """Constitution + scope + applicability. Returns '' when the edit may be TRIED, else the refusal.
    Every check here is a hard stop; none of them can be argued out of by the advisor's wording."""
    p = edit.path
    hits = touches_constitution([p])
    if hits:
        return (f"refused: {p} is constitutionally immutable (moral core / a gate / the test suite) "
                f"— never self-modifiable, regardless of who drafted it")
    if not any(p.startswith(r) for r in REPAIR_ROOTS):
        return f"refused: {p} is outside the repair scope {REPAIR_ROOTS}"
    if any(p.startswith(f) for f in REPAIR_FORBIDDEN):
        return f"refused: {p} is in the no-repair set {REPAIR_FORBIDDEN}"
    target = edit.target()
    try:                                     # containment: no traversal outside the repo
        target.resolve().relative_to(REPO.resolve())
    except Exception:
        return f"refused: {p} resolves outside the repository"
    if not target.is_file():
        return f"refused: {p} does not exist"
    text = target.read_text(encoding="utf-8")
    n = text.count(edit.old)
    if n == 0:
        return "refused: the OLD text does not appear in the file (stale or hallucinated anchor)"
    if n > 1:
        return f"refused: the OLD text appears {n} times — an ambiguous anchor could patch the wrong site"
    patched = text.replace(edit.old, edit.new, 1)
    try:                                     # never write a file that cannot even parse
        ast.parse(patched)
    except SyntaxError as e:
        return f"refused: the patched file would not parse ({e.msg} at line {e.lineno})"
    return ""


def apply_text(edit: Edit) -> tuple[str, str]:
    """Return (original_text, patched_text). Pure — writes nothing."""
    text = edit.target().read_text(encoding="utf-8")
    return text, text.replace(edit.old, edit.new, 1)
