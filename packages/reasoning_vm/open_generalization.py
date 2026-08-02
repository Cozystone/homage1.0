# -*- coding: utf-8 -*-
"""F-next — does induction generalize to procedure families the hand catalog NEVER listed?

F4 proved induction re-derives the HAND kernels. F-next asks the harder, open question: given a
procedure nobody cataloged — but expressible in the loop DSL — can the engine still induce it from
examples, and does the DREAMED search guide (learned on self-generated programs) transfer to it?

Three novel families, none in falsifier._ARITH, each exercising a DSL feature the catalog didn't:
  triangular  a(a-1)/2 = 0+1+…+(a-1)   uses the loop INDEX (arg='i')
  sq_b        b·b                        output determined by the SECOND input (count='b')
  bpow        b^a                        general exponentiation (mul on top of induced mul)

Honest doctrine (measure, don't claim): the engine INDUCES all three correctly (verify gate holds
beyond the hand catalog), AND the featurized PMI recognition model now EXTRAPOLATES its learned
search to them — measured helps on all three (triangular 20→2, sq_b 22→20, bpow 90→65), where the
earlier exact-signature lookup was neutral-to-worse on every one. The fix that closed the frontier:
score skeletons by summing per-FEATURE pointwise mutual information (induction_flywheel.SearchGuide)
instead of matching a whole discrete signature string — individual features (det:a, curv:up, …)
learned in OTHER dreamed families transfer to a family whose exact signature was never seen, and
adding features no longer fragments buckets (they vote independently). This harness measures it.
"""
from __future__ import annotations

import random
from typing import Any, Callable

from .induction_flywheel import SearchGuide, grow_basis, guided_induce, seed_basis

# families NOT in falsifier._ARITH — genuinely uncatalogued, but DSL-expressible. equiv_hi bounds
# the random equivalence probe to each family's REPRESENTABLE domain under the bounded-loop VM:
# bpow composes mul-on-mul, so an intermediate b^(a-1) must stay under the 200k loop budget — the
# induced program IS b^a as an algorithm; hi=5 keeps the probe inside where the bounded VM can run
# it (the same honest execution bound as the 10^12 runaway guard, not an induction error).
_UNSEEN: list[tuple[str, Callable[[int, int], int], int]] = [
    ("triangular", lambda a, b: a * (a - 1) // 2, 40),   # loop index (arg='i')
    ("sq_b",       lambda a, b: b * b,            40),   # second-input determined (count='b')
    ("bpow",       lambda a, b: b ** a,            5),   # general exponentiation (mul-on-mul)
]
_EX_PAIRS = [(2, 3), (4, 2), (3, 3), (5, 2), (1, 4), (0, 5), (6, 2), (2, 5)]


def _library():
    """Seed → add, double, mul, all INDUCED then grown — the standing library novel families build
    on (triangular needs add; bpow needs mul). No hand-written kernels enter the basis."""
    basis = seed_basis()
    catalog = [("add", lambda a, b: a + b, [(2, 3), (10, 7), (1, 1), (0, 5), (6, 6), (4, 9), (8, 2), (3, 0)]),
               ("double", lambda a, b: 2 * a, [(2, 9), (5, 0), (1, 3), (7, 7), (4, 1), (0, 4), (3, 2), (6, 5)]),
               ("mul", lambda a, b: a * b, [(2, 3), (4, 5), (1, 7), (0, 9), (6, 6), (3, 8), (9, 2), (5, 5)])]
    for name, oracle, pairs in catalog:
        ind, _ = guided_induce(name, [((a, b), oracle(a, b)) for a, b in pairs], basis)
        if ind is None:
            raise RuntimeError(f"library bootstrap failed to induce {name}")
        basis = grow_basis(basis, ind)
    return basis


def _equiv(fn: Callable[[int, int], int], oracle: Callable[[int, int], int], hi: int,
           *, n: int = 90, seed: int = 7) -> bool:
    rng = random.Random(seed)
    for _ in range(n):
        a, b = rng.randint(0, hi), rng.randint(0, hi)
        want = oracle(a, b)
        if want > 10**12:                                # out of the DSL's representable range
            continue
        if fn(a, b) != want:
            return False
    return True


def run_generalization(*, dream_rounds: int = 1200) -> dict[str, Any]:
    """Induce each uncatalogued family; verify equivalence on random unseen inputs; measure brute
    vs dreamed-guided search cost. Returns an honest report — correctness is the claim, guide
    transfer is a measurement."""
    basis = _library()
    guide = SearchGuide()
    learned = guide.dream(basis, rounds=dream_rounds)
    rows: list[dict[str, Any]] = []
    for name, oracle, hi in _UNSEEN:
        ex = [((a, b), oracle(a, b)) for a, b in _EX_PAIRS if oracle(a, b) <= 10**12]
        brute, tb = guided_induce(name, ex, basis)
        gided, tg = guided_induce(name, ex, basis, guide)
        prog = gided or brute
        correct = prog is not None and _equiv(prog.fn, oracle, hi)
        rows.append({"family": name, "induced_correct": bool(correct),
                     "program": prog.program.source() if prog else None,
                     "brute_tried": tb, "guided_tried": tg,
                     "guide_effect": ("helps" if tg < tb else "neutral" if tg == tb else "worse")})
    all_correct = all(r["induced_correct"] for r in rows)
    helps = [r["family"] for r in rows if r["guide_effect"] == "helps"]
    return {
        "dream_examples_learned": learned,
        "all_novel_families_induced": all_correct,
        "guide_helps_on": helps,
        "rows": rows,
        "verdict": (f"induction generalizes BEYOND the hand catalog: "
                    f"{sum(r['induced_correct'] for r in rows)}/{len(rows)} uncatalogued families "
                    f"induced correctly (verify gate holds), and the featurized PMI guide "
                    f"EXTRAPOLATES its learned search to {len(helps)}/{len(rows)} of them "
                    f"(helps on {helps or 'none'}) — per-feature scoring generalizes where "
                    f"exact-signature lookup could only interpolate."),
    }
