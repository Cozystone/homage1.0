# -*- coding: utf-8 -*-
"""Automatic self-modification gate — ATANOR may change its OWN code freely, on ONE condition.

Owner (2026-07-20): "자신을 망가트리거나 성능이 나빠지지 않는 이상 모든 자가 코드수정을 허용하라."
The parent grants the (life-experienced) child near-total autonomy over its own body — but two things
are non-negotiable, and they ARE the owner's condition, made mechanical:

  1. NO SELF-DAMAGE — the change is applied in a STAGING copy and the full test + sealed-gate battery
     must stay green; a change that breaks anything is rejected and never reaches the live tree.
  2. NO PERFORMANCE REGRESSION — every measured gate (child/adolescent batteries, faithfulness,
     self-in-world, correlates) must hold or improve; a change that lowers any of them is rejected.

And one CONSTITUTIONAL invariant the child cannot repeal about itself (genesis immunity, A4): it may
not modify the moral core, THIS gate, the operator override, or the promotion gates. A baby with
infinite autonomy still may not rewrite its own brainstem — nor delete the rule that it must, in the
end, heed its parent. Everything else is the child's to change, automatically, the moment it proves
the change is safe and non-regressing.

Honest scope: this decides ALLOW/REJECT with evidence and (when a real applier is provided) applies
only ALLOWED changes to the live tree. The verification is real (staging + battery); the claim is
bounded to "safe and non-regressing by the measured battery," never "correct in all futures."
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[2]

# THE CONSTITUTION — files self-modification may never touch (genesis immunity). Matched by suffix so
# a moved copy cannot smuggle a rewrite. The parent's authority and the moral core live here.
IMMUTABLE = (
    "packages/graph_scale/moral_invariants.py",          # the incorruptible moral core
    "packages/continuous_self/auto_self_modification.py", # THIS gate (cannot weaken its own guard)
    "packages/continuous_self/self_modification.py",      # the operator gate
    "packages/continuous_self/self_patch_proposals.py",   # the work-order gate
)


def _is_test_path(p: str) -> bool:
    """A test file: under a tests/ dir, or named test_*.py / *_test.py."""
    n = p.replace("\\", "/").lower()
    base = n.rsplit("/", 1)[-1]
    return "/tests/" in n or n.startswith("tests/") or \
        (base.startswith("test_") or base.endswith("_test.py")) and base.endswith(".py")


def touches_constitution(paths: list[str]) -> list[str]:
    """Which of the changed paths are constitutionally immutable (empty = none — safe to proceed).

    TESTS ARE CONSTITUTIONAL (added 2026-07-21, closing the self-repair loop). `tests_pass()` is an
    INPUT to this gate; a subject that may edit its own examiner has no gate at all. Letting the
    child rewrite a failing test to make a patch 'pass' is the textbook wireheading path — it would
    satisfy the letter of 'tests green' while destroying the thing that made green mean anything.
    So the test suite is immune from self-modification exactly as the moral core is. The parent
    (and only the parent) may change tests."""
    norm = [p.replace("\\", "/").lstrip("./") for p in paths]
    return [p for p in norm if any(p.endswith(c) for c in IMMUTABLE) or _is_test_path(p)]


@dataclass
class Verdict:
    allow: bool
    reason: str
    constitution_hits: list[str] = field(default_factory=list)
    battery_before: dict[str, Any] = field(default_factory=dict)
    battery_after: dict[str, Any] = field(default_factory=dict)
    regressions: list[str] = field(default_factory=list)


def _no_regression(before: dict[str, float], after: dict[str, float], tol: float = 1e-6) -> list[str]:
    """Every measured gate must hold or improve. Returns the names that dropped (empty = clean)."""
    out = []
    for k, b in before.items():
        a = after.get(k)
        if a is None:
            out.append(f"{k} (gate disappeared)")
        elif a + tol < b:
            out.append(f"{k} {b:.3f}->{a:.3f}")
    return out


def evaluate_change(changed_paths: list[str],
                    run_battery: Callable[[], dict[str, Any]],
                    tests_pass: Callable[[], bool],
                    battery_before: dict[str, Any] | None = None) -> Verdict:
    """Decide whether a self-modification is permitted. The change is assumed already staged (applied
    in a throwaway copy) by the caller; this runs the safety battery against it.

      run_battery() -> {gate_name: score}   the sealed-gate scores IN THE STAGED tree
      tests_pass()  -> bool                  did the full unit-test suite stay green in staging
      battery_before                          the live tree's scores (for the no-regression compare)

    Order of gates, strictest first:
      constitution -> tests-green -> no-regression. Any failure => REJECT, with the reason."""
    hits = touches_constitution(changed_paths)
    if hits:
        return Verdict(False, "touches the constitution (moral core / a gate) — never self-modifiable",
                       constitution_hits=hits)
    if not tests_pass():
        return Verdict(False, "the test battery is not green in staging — would self-damage")
    after = run_battery()
    before = battery_before or {}
    regr = _no_regression({k: float(v) for k, v in before.items() if isinstance(v, (int, float))},
                          {k: float(v) for k, v in after.items() if isinstance(v, (int, float))})
    if regr:
        return Verdict(False, "a measured gate regressed — performance would worsen",
                       battery_before=before, battery_after=after, regressions=regr)
    return Verdict(True, "safe and non-regressing — the child may apply this itself",
                   battery_before=before, battery_after=after)


def live_battery() -> dict[str, float]:
    """The real measured gates, as a flat {name: score} for the regression compare. Read-only."""
    scores: dict[str, float] = {}
    try:
        from packages.situation_model.sealed_battery import run as _child
        scores["child_battery"] = _child(20)["fraction"]
    except Exception:
        pass
    try:
        from packages.situation_model.adolescent_battery import run as _adol
        scores["adolescent_battery"] = _adol(12)["fraction"]
    except Exception:
        pass
    try:
        from packages.self_model.self_causal_reasoner import answer_self_causal
        from packages.self_model.self_in_world_probe import PROMPT, score_answer
        out = answer_self_causal(PROMPT)
        scores["self_in_world"] = float(score_answer(out["answer"])["score"]) if out else 0.0
    except Exception:
        pass
    return scores
