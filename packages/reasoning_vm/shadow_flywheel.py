# -*- coding: utf-8 -*-
"""F2 — answer-path SHADOW mode: the induced library meets the real world.

Every arithmetic-shaped question that flows through the live engine gets a SHADOW prediction
from the self-built procedure library (persisted by sleep_abstraction). The prediction is
verified against the exact-arithmetic oracle; a mismatch writes a prediction-error receipt AND
attempts auto-repair through the same verify-gated re-induction — the owner's flywheel running
in production. The spoken answer is NEVER touched: fire-and-forget, time-bounded, exception-
swallowed. Shadow rows land in the hypothesis ledger for audit.

Why arithmetic first: it has a computable oracle, so verification is free and safe. The same
hook shape extends to graph-verifiable predictions later (F3).
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable

from .induction_flywheel import (_append_ledger, check_and_repair, guided_induce,
                                 load_library, record_error, seed_basis, sleep_abstraction)
from .procedure_induction import Induced, Program

_LIB_CACHE: dict[str, Any] = {"basis": None, "at": 0.0}
_LIB_TTL_S = 300.0

# question → (procedure, a, b, oracle) mappers. Small and Korean-first; symbolic forms included.
_PAT_ADD = re.compile(r"(\d{1,9})\s*(?:더하기|플러스|\+)\s*(\d{1,9})")
_PAT_MUL = re.compile(r"(\d{1,9})\s*(?:곱하기|곱셈|[x×*])\s*(\d{1,9})")
_PAT_DBL = re.compile(r"(\d{1,9})\s*의?\s*(?:두\s*배|2배)")
_PAT_POW2 = re.compile(r"2\s*의\s*(\d{1,2})\s*(?:승|제곱)")


def _library() -> dict:
    now = time.monotonic()
    if _LIB_CACHE["basis"] is None or now - _LIB_CACHE["at"] > _LIB_TTL_S:
        try:
            _LIB_CACHE["basis"] = load_library()
        except Exception:
            _LIB_CACHE["basis"] = seed_basis()
        _LIB_CACHE["at"] = now
    return _LIB_CACHE["basis"]


def _match(question: str) -> tuple[str, int, int, int] | None:
    """(procedure_name, a, b, oracle_truth) for an arithmetic-shaped question, else None."""
    q = str(question or "")
    m = _PAT_POW2.search(q)
    if m:
        a = int(m.group(1))
        return ("pow2", a, 0, 2 ** a) if a <= 30 else None
    m = _PAT_DBL.search(q)
    if m:
        a = int(m.group(1))
        return ("double", a, 0, 2 * a)
    m = _PAT_MUL.search(q)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return ("mul", a, b, a * b)
    m = _PAT_ADD.search(q)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return ("add", a, b, a + b)
    return None


def _seed_examples(name: str, truth: Callable[[int, int], int]) -> list:
    """Bootstrap examples for a missing procedure — generated from the ORACLE (safe: arithmetic
    has a computable oracle; this is how a first-seen operation gets induced on demand)."""
    pairs = [(2, 3), (10, 7), (1, 1), (0, 5), (6, 6), (4, 9), (8, 2), (3, 0)]
    return [((a, b), truth(a, b)) for a, b in pairs]


_TRUTHS: dict[str, Callable[[int, int], int]] = {
    "add": lambda a, b: a + b, "mul": lambda a, b: a * b,
    "double": lambda a, b: 2 * a, "pow2": lambda a, b: 2 ** a,
}


def shadow_observe(question: str) -> dict[str, Any] | None:
    """One shadow pass. Returns a small report (for tests/ops) or None if not arithmetic-shaped.
    NEVER raises; never affects the caller's answer."""
    try:
        hit = _match(question)
        if not hit:
            return None
        name, a, b, oracle = hit
        basis = _library()
        truth = _TRUTHS[name]
        repaired = False
        if name not in basis:
            # first encounter: induce ON DEMAND from oracle-generated examples, then persist
            ind, _tried = guided_induce(name, _seed_examples(name, truth), basis)
            if ind is None:
                _append_ledger({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "shadow_miss",
                                "name": name, "note": "not inducible with current library"})
                return {"name": name, "status": "not_inducible"}
            sleep_abstraction()
            _LIB_CACHE["basis"] = None                 # reload with the new procedure
            basis = _library()
        fn = basis[name][0]
        try:
            got = fn(a, b)
        except Exception:
            got = None
        ok = (got == oracle)
        _append_ledger({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "shadow_prediction",
                        "name": name, "input": [a, b], "predicted": got, "oracle": oracle,
                        "correct": ok})
        if not ok:
            # the flywheel, live: receipt → verify-gated re-induction → persist → reload
            prog = Program("0", "a", "S", "_", name=name)     # ledger context only
            record_error(name, prog, ((a, b), oracle), oracle, got)
            ind, _tried = guided_induce(name, _seed_examples(name, truth) + [((a, b), oracle)],
                                        seed_basis() if name in ("add", "double") else _library())
            if ind is not None:
                sleep_abstraction()
                _LIB_CACHE["basis"] = None
                repaired = True
        return {"name": name, "input": [a, b], "predicted": got, "oracle": oracle,
                "correct": ok, "repaired": repaired}
    except Exception:
        return None


def shadow_stats(last: int = 200) -> dict[str, Any]:
    """Ops view: recent shadow accuracy from the ledger."""
    import json
    from .induction_flywheel import _LEDGER
    rows = []
    try:
        for ln in _LEDGER.read_text(encoding="utf-8").splitlines()[-last * 3:]:
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if r.get("kind") == "shadow_prediction":
                rows.append(r)
    except Exception:
        pass
    rows = rows[-last:]
    n = len(rows)
    correct = sum(1 for r in rows if r.get("correct"))
    return {"n": n, "correct": correct, "accuracy": round(correct / n, 4) if n else None,
            "by_proc": {p: sum(1 for r in rows if r.get("name") == p)
                        for p in {r.get("name") for r in rows}}}


# ---------------------------------------------------------------- F2.5: graduation gate
# An induced procedure EARNS the right to speak: only after sustained shadow accuracy on real
# traffic (default-deny), and even then every spoken answer is cross-checked against the oracle
# at answer time — a graduated procedure that ever disagrees is not spoken and gets a receipt.
GRAD_MIN_N = 5            # minimum shadow predictions observed


def graduated(name: str, *, min_n: int = GRAD_MIN_N, window: int = 50) -> bool:
    """True when the last `window` shadow predictions for `name` number >= min_n and are ALL
    correct. Conservative by design: one shadow miss un-graduates until re-earned."""
    import json as _json
    from .induction_flywheel import _LEDGER
    rows = []
    try:
        for ln in _LEDGER.read_text(encoding="utf-8").splitlines():
            try:
                r = _json.loads(ln)
            except Exception:
                continue
            if r.get("kind") == "shadow_prediction" and r.get("name") == name:
                rows.append(r)
    except Exception:
        return False
    rows = rows[-window:]
    return len(rows) >= min_n and all(r.get("correct") for r in rows)


def graduated_answer(question: str) -> dict[str, Any] | None:
    """Spoken answer from a GRADUATED induced procedure — solve_reasoning-shaped dict, or None.
    Belt and suspenders: the library's output is cross-checked against the exact oracle at
    answer time; any disagreement is a receipt, never speech."""
    try:
        hit = _match(question)
        if not hit:
            return None
        name, a, b, oracle = hit
        if not graduated(name):
            return None                               # not yet earned — shadow keeps observing
        basis = _library()
        if name not in basis:
            return None
        got = basis[name][0](a, b)
        if got != oracle:                             # never speak a wrong induced answer
            prog = Program("0", "a", "S", "_", name=name)
            record_error(name, prog, ((a, b), oracle), oracle, got)
            return None
        shown = {"add": f"{a} + {b}", "mul": f"{a} × {b}",
                 "double": f"{a} × 2", "pow2": f"2^{a}"}[name]
        _append_ledger({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "graduated_spoken",
                        "name": name, "input": [a, b], "value": got})
        return {
            "answer": f"{shown} = {got} 입니다. (제가 예시에서 스스로 유도해 검증한 절차로 계산했어요)",
            "reasoning_certificate": {
                "derivation_kind": "induced_procedure_graduated",
                "anchor_concept": name,
                "steps": [
                    {"type": "induced_program", "fact": f"procedure '{name}' — self-induced, "
                                                        f"verified on held-out examples"},
                    {"type": "evaluate", "fact": f"{shown} = {got}"},
                    {"type": "oracle_crosscheck", "fact": "exact-arithmetic re-check passed"},
                ],
                "evidence_concepts": [name], "confidence": 0.96,
                "confidence_basis": "graduated_shadow_accuracy_plus_oracle_crosscheck",
                "guarantees": {"external_llm": False, "fabricated_facts": False,
                               "web_used": False, "self_induced": True},
            },
            "confidence": 0.96,
            "result_value": got,
        }
    except Exception:
        return None
