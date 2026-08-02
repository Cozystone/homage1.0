# -*- coding: utf-8 -*-
"""Unwired-organ audit — the built-but-never-called failure class.

`audit_wiring.py` already covers unwired DATA assets, dead parameters, env flags and lane drift.
It does not cover the class that keeps surfacing in review: a whole organ is built, tested, and
then nothing on any live path ever calls it. Measured instances (2026-07-26..28):

  * `DoubtGate` — constructed in `RealTimeThinker.__init__`, never called in the answer flow.
  * `RELATION_VOCAB` — 70 hand-listed relations gating a store that uses 46; 73M edges unreachable.
  * CO-C0 F1.1–F4 — ~6,000 lines built, adversarially RED, left in stashes with no result document.

A caution this tool earned on its first run: two organs the author was sure were dead
(`promote_verified`, the `harvester` seam) came back WIRED, because the belief rested on a grep
that had searched `packages/` and `apps/` but not `scripts/`. Trust the scan over the memory.

Two checks, both read-only:

  A. UNCALLED ORGANS — a public module-level class/def in `packages/` whose name is never used
     outside its own defining module, ignoring tests. Re-export in an `__init__` does not count as
     use. These are candidates: dynamic dispatch (registries, getattr, entry points) produces false
     positives, so every hit needs eyes before it means anything.

  B. UNFILLED INJECTION POINTS — a parameter whose default is None or a `_null_*`/`_noop_*` stub,
     where no call site anywhere passes a non-None value for it. This is the `harvester` shape: the
     seam exists, the organ exists, and the two were never joined.

Informational, never a gate. Usage: python scripts/audit_unwired_organs.py [repo_root] [out.json]
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else None

NULL_DEFAULT_HINTS = ("_null", "_noop", "_stub", "_dummy")


def is_test(p: Path) -> bool:
    return "test" in p.name.lower() or "tests" in p.parts


def py_files() -> list[Path]:
    return [p for p in sorted(ROOT.glob("packages/**/*.py")) if "__pycache__" not in p.parts]


def all_py() -> list[Path]:
    out = []
    for sub in ("packages", "scripts", "apps"):
        out += [p for p in sorted(ROOT.glob(f"{sub}/**/*.py")) if "__pycache__" not in p.parts]
    return out


trees: dict[Path, ast.Module] = {}
for p in all_py():
    try:
        trees[p] = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        continue

# ---- A. organs defined vs names referenced anywhere else -----------------------------------------
defined: dict[str, list[tuple[str, int]]] = {}
for p in py_files():
    if is_test(p) or p not in trees:
        continue
    rel = str(p.relative_to(ROOT)).replace("\\", "/")
    for node in trees[p].body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                and not node.name.startswith("_"):
            defined.setdefault(node.name, []).append((rel, node.lineno))
        if isinstance(node, ast.ClassDef):
            # public METHODS count too: promote_verified() was a whole organ nobody could reach,
            # and it lives inside a class, so a module-level-only scan cannot see it.
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and not sub.name.startswith("_"):
                    defined.setdefault(sub.name, []).append((rel, sub.lineno))

used_outside: dict[str, set[str]] = {}
for p, tree in trees.items():
    rel = str(p.relative_to(ROOT)).replace("\\", "/")
    if is_test(p):
        continue                                   # a test exercising it is not a live wire
    is_reexport = p.name == "__init__.py"
    for node in ast.walk(tree):
        name = None
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if is_reexport:
                continue                           # re-export is plumbing, not use
            for a in node.names:
                if a.name in defined:
                    used_outside.setdefault(a.name, set()).add(rel)
            continue
        if name and name in defined:
            used_outside.setdefault(name, set()).add(rel)

uncalled = []
for name, sites in sorted(defined.items()):
    own = {f for f, _ in sites}
    elsewhere = used_outside.get(name, set()) - own
    if not elsewhere:
        uncalled.append({"name": name, "defined_at": sites})

# ---- B. injection seams whose only callers pass nothing -------------------------------------------
seams: dict[str, dict] = {}
for p in py_files():
    if is_test(p) or p not in trees:
        continue
    rel = str(p.relative_to(ROOT)).replace("\\", "/")
    for node in ast.walk(trees[p]):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args
        params = args.args[-len(args.defaults):] if args.defaults else []
        for arg, dflt in list(zip(params, args.defaults)) + list(
                zip(args.kwonlyargs, args.kw_defaults or [])):
            if dflt is None:
                continue
            nullish = (isinstance(dflt, ast.Constant) and dflt.value is None) or (
                isinstance(dflt, ast.Name) and dflt.id.startswith(NULL_DEFAULT_HINTS))
            if nullish and not arg.arg.startswith("_"):
                seams.setdefault(arg.arg, {"param": arg.arg, "seams": [], "filled_at": []})
                seams[arg.arg]["seams"].append(f"{rel}:{node.lineno} {node.name}()")

for p, tree in trees.items():
    if is_test(p):
        continue
    rel = str(p.relative_to(ROOT)).replace("\\", "/")
    # Names bound to a literal None in this file. `harvester = None` then `f(harvester=harvester)`
    # reads as a fill but delivers nothing -- that is exactly how the curiosity seam stayed empty.
    none_bound = {t.id for n in ast.walk(tree) if isinstance(n, ast.Assign)
                  for t in n.targets
                  if isinstance(t, ast.Name) and isinstance(n.value, ast.Constant)
                  and n.value.value is None}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg in seams:
                if isinstance(kw.value, ast.Constant) and kw.value.value is None:
                    continue                      # passing None does not fill the seam
                if isinstance(kw.value, ast.Name) and (
                        kw.value.id.startswith(NULL_DEFAULT_HINTS)
                        or kw.value.id in none_bound):
                    continue                      # a variable that is None fills nothing either
                seams[kw.arg]["filled_at"].append(f"{rel}:{node.lineno}")

unfilled = [s for s in seams.values() if not s["filled_at"]]

report = {"uncalled_organs": uncalled, "unfilled_seams": unfilled}
if OUT:
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

print(f"public organs defined in packages/: {len(defined)}")
print(f"  never referenced outside their own module (candidates): {len(uncalled)}")
print(f"injection seams (null-defaulted params): {len(seams)}")
print(f"  never filled by any non-test caller: {len(unfilled)}")
