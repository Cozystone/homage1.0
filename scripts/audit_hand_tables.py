"""AST census of module-level string-collection constants across packages/.

Regex naming heuristics only find tables that happen to be called _*_TOKENS/_*_WORDS. This walks
every module's AST instead, so a hand table is found regardless of what it was named.

Emitted per hit: file, line, name, container kind, arity, and a sample of members -- enough to
classify each one as WORLD-KNOWLEDGE (belongs in the ontology) or OWN-SHAPE (legitimately code).
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
MIN_MEMBERS = 3          # two-element pairs are almost never a lexicon


def _strings(node: ast.AST) -> list[str] | None:
    """Return the string members if `node` is a flat collection of string literals."""
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        elts = node.elts
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id in {"frozenset", "set", "tuple", "list"} and node.args:
        inner = node.args[0]
        if not isinstance(inner, (ast.Set, ast.List, ast.Tuple)):
            return None
        elts = inner.elts
    elif isinstance(node, ast.Dict):
        elts = list(node.keys)
    else:
        return None
    out = []
    for e in elts:
        if isinstance(e, ast.Constant) and isinstance(e.value, str):
            out.append(e.value)
        elif isinstance(e, ast.Tuple) and e.elts and isinstance(e.elts[0], ast.Constant) \
                and isinstance(e.elts[0].value, str):
            out.append(e.elts[0].value)          # ("marker", "meaning") pair tables
        else:
            return None                          # not a flat string collection
    return out or None


def kind(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        return getattr(node.func, "id", "call")
    return type(node).__name__.lower()


hits = []
for path in sorted(ROOT.glob("packages/**/*.py")):
    if "__pycache__" in path.parts:
        continue
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        continue
    for node in tree.body:                       # MODULE level only -- locals aren't shared state
        targets, value = [], None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        for t in targets:
            if not isinstance(t, ast.Name):
                continue
            members = _strings(value)
            if members and len(members) >= MIN_MEMBERS:
                hits.append({
                    "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                    "line": node.lineno,
                    "name": t.id,
                    "kind": kind(value),
                    "n": len(members),
                    "sample": members[:6],
                })

Path(sys.argv[2]).write_text(json.dumps(hits, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"{len(hits)} module-level string tables written")


# --- classification + answer-path reachability ---------------------------------------------------
# A census alone does not say which tables are dangerous. Two further questions decide that:
#   1. does the table assert something about the WORLD (a claim a fresh input can falsify), or does
#      it DEFINE something we own (a schema field order, our own enum)?  Only the first can be wrong.
#   2. is it reachable from an entry point whose output an honesty gate grades?  Only then can a
#      wrong answer escape.
# The intersection is the actionable set. Re-run this after any migration to measure progress.
