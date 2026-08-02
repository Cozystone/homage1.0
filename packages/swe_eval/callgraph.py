# -*- coding: utf-8 -*-
"""A cheap AST import/definition graph — the third localization signal (corroboration).

The line-scorer (``localizer``, self_repair's principle file-lifted) and the AST reader
(``code_situation`` via ``repo_reader.read_functions``) both score a file in ISOLATION. A localizer
that also knows WHICH files define the symbols an issue names, and which candidate files import the
top candidate, corroborates the ranking structurally. This is deliberately shallow (module-level
imports + top-level def/class names via one AST parse per file) so the deliberator can schedule it as
a CHEAP signal BEFORE the expensive per-function AST read — never a heavy whole-repo call graph.

Nothing here fabricates: a file that does not parse contributes nothing (it is skipped), and a symbol
with no defining file simply returns an empty corroboration.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Callable

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


@dataclass
class Corroboration:
    defines_issue_symbol: list[str] = field(default_factory=list)   # files defining a symbol the issue names
    importers_of_top: list[str] = field(default_factory=list)       # candidate files importing the top file
    top_defines: list[str] = field(default_factory=list)            # symbols the top file defines that the issue names


def _module_path(path: str) -> str:
    """astropy/modeling/separable.py -> astropy.modeling.separable (for import matching)."""
    return path[:-3].replace("/", ".") if path.endswith(".py") else path.replace("/", ".")


def _top_level_names(src: str) -> set[str]:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
    return out


def _imports(src: str) -> set[str]:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def corroborate(issue_tokens: set[str], top_file: str, candidate_files: list[str],
                read_file: Callable[[str], str | None]) -> Corroboration:
    """Which candidate files define a symbol the issue names, and which import the top file. Reads at
    most the given candidate files (a bounded, lazy set the caller already narrowed)."""
    c = Corroboration()
    top_mod = _module_path(top_file)
    top_src = read_file(top_file) or ""
    c.top_defines = sorted({n for n in _top_level_names(top_src) if n.lower() in issue_tokens})
    for f in candidate_files:
        if f == top_file:
            continue
        src = read_file(f)
        if not src:
            continue
        names = _top_level_names(src)
        if any(n.lower() in issue_tokens for n in names):
            c.defines_issue_symbol.append(f)
        if top_mod in _imports(src) or top_mod.rsplit(".", 1)[-1] in {m.rsplit(".", 1)[-1] for m in _imports(src)}:
            c.importers_of_top.append(f)
    c.defines_issue_symbol = c.defines_issue_symbol[:10]
    c.importers_of_top = c.importers_of_top[:10]
    return c
