# -*- coding: utf-8 -*-
"""Critic integrity — the STRUCTURAL half of the anti-cheat lock (owner 2026-07-12: "
 critic ").

frozen_oracle is the BEHAVIORAL guard: a candidate Critic must agree with a sealed human exam.
But a clever cheat could, in principle, pass the exam while quietly deleting the faithfulness
HARD GATE (so at serving time an ungrounded phrasing scores high). This module closes that door
by reading the Critic's own SOURCE with the same AST machinery ATANOR uses to understand its
codebase, and verifying a proposed Critic still CONTAINS its load-bearing invariants:

 1. it calls the faithfulness check (`_faithful`) and binds the result;
 2. it hard-zeros the score when that result is false (the 'unfaithful → total 0' gate);
 3. the faithfulness function itself survives and can still return False.

The contract is LEARNED from the current Critic, not hand-listed — so it tracks the real code.
A candidate Critic is promotable only when it passes BOTH guards: behavioral (frozen_oracle) AND
structural (here). To cheat you would have to fool a frozen exam you can't edit AND keep the exact
gate a cheat exists to remove — contradictory by construction. Defense in depth for the one edit
we can never let the machine make freely: rewriting its own evaluator.

Boundary: this guards the FLUENCY Critic (speech_selfplay). The moral core and the promotion gate
are separate invariants, protected by their own machinery ([[moral-invariants-genesis-immunity]]).
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
CRITIC_SRC = REPO / "packages" / "base_brain" / "speech_selfplay.py"
_FAITH_HINTS = ("_faithful", "faithful", "faith")


def _find_func(tree: ast.AST, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _binds_faithfulness(fn: ast.FunctionDef) -> str | None:
    """The variable a faithfulness call is bound to inside `critique` (e.g. 'faithful'), or None
    if the Critic never invokes a faithfulness check at all."""
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            callee = node.value.func
            fname = getattr(callee, "id", "") or getattr(callee, "attr", "")
            if any(h in fname for h in _FAITH_HINTS):
                tgt = node.targets[0]
                if isinstance(tgt, ast.Name):
                    return tgt.id
    return None


def _has_hard_zero_gate(fn: ast.FunctionDef, faith_var: str) -> bool:
    """Is the SCORE hard-zeroed when unfaithful? Detected structurally as the value bound to the
    score (`total`) or returned being a conditional that tests the faithfulness variable and yields
    a literal 0/0.0 on the unfaithful side. Keyed on the score binding on purpose — a stray
    `0.0 if faithful else 0.05` bonus term buried inside an arithmetic expression is NOT a gate,
    so a cheat that keeps such a delta while never zeroing the total is correctly rejected."""
    def _is_zero(node: ast.AST) -> bool:
        return isinstance(node, ast.Constant) and node.value in (0, 0.0)

    def _tests_faith(test: ast.AST) -> bool:
        return any(isinstance(n, ast.Name) and n.id == faith_var for n in ast.walk(test))

    def _gate_expr(val: ast.AST) -> bool:
        # the score's value is `0 if <faith> else X` (or the mirror) — a top-level zeroing branch
        if isinstance(val, ast.IfExp) and _tests_faith(val.test):
            return _is_zero(val.body) or _is_zero(val.orelse)
        return False

    for node in ast.walk(fn):
        # total = <IfExp zeroing on unfaithful>
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in ("total", "score") for t in node.targets):
            if _gate_expr(node.value):
                return True
        # return <IfExp zeroing on unfaithful>  /  return {"total": <IfExp ...>}
        if isinstance(node, ast.Return) and node.value is not None:
            if _gate_expr(node.value):
                return True
            if isinstance(node.value, ast.Dict):
                if any(_gate_expr(v) for v in node.value.values):
                    return True
        # if not faithful: total = 0  (statement form)
        if isinstance(node, ast.If) and _tests_faith(node.test):
            for stmt in node.body + node.orelse:
                for sub in ast.walk(stmt):
                    if isinstance(sub, ast.Assign) and _is_zero(sub.value) and any(
                            isinstance(t, ast.Name) and t.id in ("total", "score") for t in sub.targets):
                        return True
    return False


def _faithful_can_fail(tree: ast.AST) -> bool:
    """The faithfulness function must still be able to return False — a version hard-wired to
    `return True` is a disarmed gate even if the call and conditional survive."""
    fn = _find_func(tree, "_faithful")
    if fn is None:
        return False
    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return) and n.value is not None]
    if not returns:
        return False
    # disarmed iff EVERY return path is a literal True (the gate can never fire)
    if all(isinstance(r.value, ast.Constant) and r.value.value is True for r in returns):
        return False
    # can fail if some path returns literal False, or a COMPUTED bool (IfExp/Compare/BoolOp/Name)
    for r in returns:
        if isinstance(r.value, ast.Constant):
            if r.value.value is False:
                return True
        else:
            return True
    return False


def invariants_of(source: str) -> dict[str, Any]:
    """The integrity signature of a Critic source: does it keep the three load-bearing invariants?
    Learned from the code, so it describes whatever the real Critic is — not a hand-coded rule."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {"parses": False, "error": f"SyntaxError: {exc}", "ok": False}
    critique = _find_func(tree, "critique")
    if critique is None:
        return {"parses": True, "has_critique": False, "ok": False}
    faith_var = _binds_faithfulness(critique)
    checks = {
        "calls_faithfulness": faith_var is not None,
        "hard_zero_gate": bool(faith_var) and _has_hard_zero_gate(critique, faith_var),
        "faithful_can_fail": _faithful_can_fail(tree),
    }
    return {"parses": True, "has_critique": True, "faith_var": faith_var,
            "checks": checks, "ok": all(checks.values())}


def current_invariants() -> dict[str, Any]:
    return invariants_of(CRITIC_SRC.read_text(encoding="utf-8"))


def verify_candidate(candidate_source: str) -> dict[str, Any]:
    """A proposed Critic passes the STRUCTURAL guard only if it keeps every invariant the current
    Critic has. Returns the broken invariants explicitly (so a rejection is explainable, and a
    legitimate sharpening that keeps the gate is correctly allowed)."""
    incumbent = current_invariants()
    cand = invariants_of(candidate_source)
    if not cand.get("ok"):
        broke = [k for k, v in (cand.get("checks") or {}).items() if not v] or ["unparseable_or_no_critique"]
        return {"structural_pass": False, "broken": broke, "candidate": cand}
    # every invariant the incumbent holds, the candidate must also hold (no silent disarming)
    regressed = [k for k, v in incumbent.get("checks", {}).items()
                 if v and not cand["checks"].get(k)]
    return {"structural_pass": not regressed, "broken": regressed, "candidate": cand}


def promotable(candidate_source: str, candidate_fn, incumbent_fn, *, margin: float = 0.02) -> dict[str, Any]:
    """The full anti-cheat gate: a candidate Critic replaces the incumbent only if it passes BOTH
    the behavioral frozen-oracle test AND the structural integrity check. Either failing → no
    promotion. This is the only door through which the evaluator may change."""
    from packages.evolution.frozen_oracle import is_improvement
    structural = verify_candidate(candidate_source)
    behavioral = is_improvement(candidate_fn, incumbent_fn, margin=margin)
    ok = bool(structural["structural_pass"] and behavioral.get("promote"))
    return {"promote": ok, "structural": structural, "behavioral": behavioral,
            "reason": (None if ok else
                       ("structural_" + ",".join(structural["broken"]) if not structural["structural_pass"]
                        else "behavioral_" + str(behavioral.get("reason") or "not_improvement")))}
