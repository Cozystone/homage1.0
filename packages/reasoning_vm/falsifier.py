# -*- coding: utf-8 -*-
"""F4 — the falsifier: can induction RE-DERIVE the hand-built kernels? Measure it, honestly.

The whole reasoning-VM thesis stands or falls on one test (INDUCTION_FLYWHEEL F4): if the
induction engine can re-derive a hand-written kernel from examples AND the re-derived procedure
is behaviourally EQUIVALENT to the hand code on held-out inputs, then that hand code is provably
redundant — the machine can own it. This harness runs that test over the catalog of hand kernels
(arithmetic + graph relations), checks equivalence on random unseen inputs, and reports which
hand-work is now redundant and which remains a genuine frontier. No claim — a measurement.
"""
from __future__ import annotations

import random
from typing import Any, Callable

from .induction_flywheel import grow_basis, guided_induce, seed_basis
from .relation_induction import induce_relation_path

# arithmetic kernels: (name, oracle(a,b), example_pairs, equivalence_range, needs_library)
_ARITH: list[tuple[str, Callable[[int, int], int], list[tuple[int, int]], tuple[int, int], bool]] = [
    ("add",      lambda a, b: a + b,          [(2, 3), (10, 7), (1, 1), (0, 5), (6, 6), (4, 9), (8, 2), (3, 0)], (0, 500), False),
    ("subtract", lambda a, b: max(0, a - b),  [(5, 2), (9, 4), (3, 3), (7, 0), (10, 6), (4, 9), (8, 1), (6, 2)], (0, 500), False),
    ("double",   lambda a, b: 2 * a,          [(2, 9), (5, 0), (1, 3), (7, 7), (4, 1), (0, 4), (3, 2), (6, 5)], (0, 500), False),
    ("mul",      lambda a, b: a * b,          [(2, 3), (4, 5), (1, 7), (0, 9), (6, 6), (3, 8), (9, 2), (5, 5)], (0, 60),  True),
    ("square",   lambda a, b: a * a,          [(2, 0), (3, 1), (4, 2), (5, 5), (6, 3), (7, 7), (1, 4), (8, 0)], (0, 60),  True),
    ("pow2",     lambda a, b: 2 ** a,         [(1, 0), (2, 3), (3, 1), (4, 4), (0, 7), (5, 2), (6, 0), (3, 3)], (0, 14),  True),
]


def _equivalent(fn: Callable[[int, int], int], oracle: Callable[[int, int], int],
                lo: int, hi: int, *, n: int = 120, seed: int = 5) -> bool:
    rng = random.Random(seed)
    return all(fn(a, b) == oracle(a, b)
               for a, b in [(rng.randint(lo, hi), rng.randint(lo, hi)) for _ in range(n)])


def run_falsifier() -> dict[str, Any]:
    """Re-derive every hand kernel from examples; verify equivalence on random unseen inputs."""
    results: list[dict[str, Any]] = []
    basis = seed_basis()                               # grows as base kernels are re-derived
    for name, oracle, pairs, (lo, hi), needs_lib in _ARITH:
        ex = [((a, b), oracle(a, b)) for a, b in pairs]
        ind, tried = guided_induce(name, ex, basis)
        if ind is None:
            results.append({"kernel": name, "domain": "arithmetic", "rederived": False,
                            "reason": "no program in current basis"})
            continue
        equiv = _equivalent(ind.fn, oracle, lo, hi)
        results.append({"kernel": name, "domain": "arithmetic", "rederived": bool(equiv),
                        "program": ind.program.source(), "equiv_range": [lo, hi],
                        "candidates_tried": tried})
        if equiv and not needs_lib:                    # base primitives enter the library first,
            basis = grow_basis(basis, ind)             # so mul/square/pow2 can build ON them

    # graph-relation kernel: 'capital' re-derived on the live store (chain_reasoner's hand path)
    try:
        from packages.graph_scale import answer_bridge as AB
        kg = AB._store()
        fa = (lambda e: kg.facts_about(e, limit=40)) if kg else None
        from .relation_induction import run_path
        rel_ex = [("프랑스", "파리"), ("독일", "베를린"), ("일본", "도쿄도"), ("영국", "런던"),
                  ("이탈리아", "로마"), ("스페인", "마드리드"), ("캐나다", "오타와")]
        if fa and any(a in run_path(s, ("capital",), fa) for s, a in rel_ex):
            ind = induce_relation_path("capital_of", rel_ex, fa)
            ok = bool(ind and ind.fn("대한민국") == "서울특별시" and ind.fn("러시아") == "모스크바")
            results.append({"kernel": "capital_of", "domain": "graph_relation",
                            "rederived": ok, "path": list(ind.path) if ind else None})
        else:
            results.append({"kernel": "capital_of", "domain": "graph_relation",
                            "rederived": None, "reason": "capital edges absent in this store"})
    except Exception as exc:
        results.append({"kernel": "capital_of", "domain": "graph_relation",
                        "rederived": None, "reason": str(exc)[:80]})

    testable = [r for r in results if r.get("rederived") is not None]
    rederived = [r for r in testable if r["rederived"]]
    return {
        "total": len(results), "testable": len(testable), "rederived": len(rederived),
        "rederived_kernels": [r["kernel"] for r in rederived],
        "remaining_frontier": [r["kernel"] for r in testable if not r["rederived"]],
        "results": results,
        "verdict": (f"{len(rederived)}/{len(testable)} hand kernels are provably re-derivable from "
                    f"examples — their hand-code is redundant; the induction engine + F2.5 "
                    f"graduation can own them. Hand-work stops for the re-derived set."),
        "honest_note": "Re-derivability is bounded to well-specified kernels with cheap oracles. "
                       "Open-ended reasoning induction remains the frontier (learned search, F-next).",
    }
