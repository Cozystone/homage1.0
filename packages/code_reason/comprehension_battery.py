# -*- coding: utf-8 -*-
"""Code comprehension battery — mine REAL functions from our own repo (license-clean, 1599 commits
of authorship), generate questions whose GROUND TRUTH is an INDEPENDENT ast walk, and measure the
code_situation organ. This is the measurable floor of code mastery (bAbI-for-code).

Non-circular by construction: ground truth here is computed by direct ast queries; the organ answers
from its own CodeSituation summary. If the summary misses something (calls in nested scopes, ternary
returns, walrus assigns), the two diverge and the battery catches it.

  python -m packages.code_reason.comprehension_battery   (or import run())
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from packages.code_reason.code_situation import answer, build

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "data" / "code_reason" / "comprehension_battery.json"
# sample from stable, self-authored packages (avoid tests/vendored/generated)
SCAN_DIRS = ["packages/situation_model", "packages/brain_link", "packages/advisor_loop",
             "packages/continuous_self", "packages/code_reason"]


def _extract_functions(py: Path) -> list[tuple[str, ast.FunctionDef]]:
    try:
        src = py.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except Exception:
        return []
    out = []
    for node in tree.body:                      # top-level funcs only (clean, self-contained src)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            try:
                out.append((ast.get_source_segment(src, node), node))
            except Exception:
                pass
    return out


def _truth(node: ast.FunctionDef) -> dict[str, Any]:
    """Ground truth by DIRECT ast walk — independent of the organ's summary."""
    params = [a.arg for a in node.args.args] + [a.arg for a in node.args.kwonlyargs]
    if node.args.vararg:
        params.append(node.args.vararg.arg)
    if node.args.kwarg:
        params.append(node.args.kwarg.arg)
    returns = any(isinstance(n, ast.Return) and n.value is not None for n in ast.walk(node))
    raises = any(isinstance(n, ast.Raise) for n in ast.walk(node))
    loop = any(isinstance(n, (ast.For, ast.While, ast.AsyncFor)) for n in ast.walk(node))
    branch = any(isinstance(n, ast.If) for n in ast.walk(node))
    recursive = any(isinstance(n, ast.Call) and (
        (isinstance(n.func, ast.Name) and n.func.id == node.name) or
        (isinstance(n.func, ast.Attribute) and n.func.attr == node.name)) for n in ast.walk(node))
    return {"n_params": len(params), "returns": returns, "raises": raises, "loop": loop,
            "branch": branch, "recursive": recursive}


def _questions(t: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        ("How many parameters does it take?", str(t["n_params"])),
        ("Does it return a value?", "yes" if t["returns"] else "no"),
        ("Does it raise an exception?", "yes" if t["raises"] else "no"),
        ("Does it contain a loop?", "yes" if t["loop"] else "no"),
        ("Does it have a conditional branch?", "yes" if t["branch"] else "no"),
        ("Is it recursive?", "yes" if t["recursive"] else "no"),
    ]


def run(max_funcs: int = 300, write_metric: bool = True) -> dict[str, Any]:
    correct = total = abstain = 0
    per_type: dict[str, list[int]] = {}
    funcs = 0
    for d in SCAN_DIRS:
        for py in sorted((REPO / d).rglob("*.py")):
            if "__pycache__" in str(py):
                continue
            for src, node in _extract_functions(py):
                if funcs >= max_funcs or not src:
                    continue
                sit = build(src)
                if sit is None:
                    continue
                funcs += 1
                truth = _truth(node)
                for q, gold in _questions(truth):
                    got = answer(q, sit)
                    total += 1
                    key = q.split()[1] if q.startswith("How") else q.split()[2]
                    per_type.setdefault(q, [0, 0])
                    per_type[q][1] += 1
                    if got is None:
                        abstain += 1
                    elif got == gold:
                        correct += 1
                        per_type[q][0] += 1
    result = {
        "pool": f"{funcs} functions from own repo ({', '.join(SCAN_DIRS)})",
        "n_questions": total,
        "strict_acc": round(correct / max(1, total), 4),
        "abstain_rate": round(abstain / max(1, total), 4),
        "by_question": {q: {"acc": round(c / max(1, n), 3), "n": n} for q, (c, n) in per_type.items()},
    }
    if write_metric:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    r = run()
    print(f"code comprehension strict {r['strict_acc']}  ({r['n_questions']} Qs over "
          f"{r['pool']}); abstain {r['abstain_rate']}")
    for q, s in r["by_question"].items():
        print(f"  {s['acc']:.3f}  {q}  (n={s['n']})")
