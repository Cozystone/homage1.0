# -*- coding: utf-8 -*-
"""M-track DSL admission gate — the language and its search grow TOGETHER, or not at all.

Measured design law (2026-07-14 receipt): adding the `i1` expressiveness to the DSL unlocked
factorial but regressed guided search on `square` from 17 → 31 candidates — expressiveness growth
without matching search growth is NET NEGATIVE (a bigger language is a bigger haystack unless the
needle-finder grows with it). It was reverted BY HAND. This gate makes that judgment automatic,
deterministic, and receipt-bearing, so DSL growth can be autonomous WITHOUT re-running that failure.

A candidate primitive is ADMITTED into the basis only if ALL THREE hold:
  1. BATTERY GREEN   every already-solved kernel (falsifier's arithmetic battery) still re-derives
                     and stays behaviourally equivalent on held-out inputs;
  2. NO REGRESSION   search cost on the battery does not regress beyond tolerance — measured BOTH
                     ways, brute candidate-order AND a freshly-dreamed guide (both seeded, so the
                     whole gate is deterministic and re-runnable);
  3. UNLOCKS         at least one previously-UNSOLVABLE task becomes solvable and verified —
                     expressiveness must buy something, or the haystack grew for nothing.
Anything else → REJECT with the failing check named and the numbers attached. The gate never
mutates the caller's basis: on ADMIT it returns a GROWN COPY; on REJECT nothing changed anywhere
(auto-revert is structural, not an action).

Scope honesty: this governs BASIS growth (new primitives = data for the sandboxed VM). It does not
and must not govern engine-code self-modification — that stays behind the human gate (RSI doctrine).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Callable

from .falsifier import _ARITH, _equivalent
from .induction_flywheel import Basis, Example, SearchGuide, grow_basis, guided_induce, seed_basis

DEFAULT_TOLERANCE = 0.25          # ≤25% median search-cost growth tolerated (measured headroom)
_DREAM_ROUNDS = 400
_DREAM_SEED = 11                  # same seed as the flywheel's own dreaming → reproducible verdicts


@dataclass
class DslCandidate:
    """A proposed new primitive: name + callable + arity, plus the frontier tasks it claims to
    unlock (each an example set that the CURRENT basis cannot solve)."""
    name: str
    fn: Callable[..., int]
    arity: int
    unlock_tasks: dict[str, list[Example]] = field(default_factory=dict)


@dataclass
class GateVerdict:
    admitted: bool
    reason: str
    receipts: dict[str, Any]
    basis: Basis | None = None    # the grown basis, ONLY when admitted

    def certificate(self) -> dict[str, Any]:
        return {"admitted": self.admitted, "reason": self.reason, **self.receipts}


def _battery_basis() -> tuple[Basis, dict[str, list[Example]]]:
    """Rebuild the falsifier's arithmetic world deterministically: induce each base kernel and grow
    the basis exactly as run_falsifier does (base primitives enter the library; mul/square/pow2 are
    induced ON them but not added). Returns (grown_basis, task→examples)."""
    basis = seed_basis()
    tasks: dict[str, list[Example]] = {}
    for name, oracle, pairs, (_lo, _hi), needs_lib in _ARITH:
        ex = [((a, b), oracle(a, b)) for a, b in pairs]
        tasks[name] = ex
        ind, _tried = guided_induce(name, ex, basis)
        if ind is not None and not needs_lib:
            basis = grow_basis(basis, ind)
    return basis, tasks


def _battery_costs(basis: Basis, tasks: dict[str, list[Example]],
                   guide: SearchGuide | None) -> dict[str, int]:
    """Search cost (candidates tried) per battery task on the given basis, brute or guided."""
    costs: dict[str, int] = {}
    for name, ex in tasks.items():
        ind, tried = guided_induce(name, ex, basis, guide)
        costs[name] = tried if ind is not None else -1     # -1 = no longer solvable (breakage)
    return costs


def _dreamed_guide(basis: Basis) -> SearchGuide:
    g = SearchGuide()
    g.dream(basis, rounds=_DREAM_ROUNDS, seed=_DREAM_SEED)
    return g


def _oracle_check(basis: Basis) -> list[str]:
    """Battery-green check, GUIDED (production-real): every kernel must re-derive under the
    candidate-carrying guide AND stay equivalent on random held-out inputs (the falsifier's bar).
    This is the un-hallucinatable-algorithm guard: a candidate whose dreamed skeletons seduce the
    guide into returning an example-fitting-but-WRONG program for an already-solved kernel fails
    equivalence here and is rejected. Returns the list of kernels that FAIL."""
    failing: list[str] = []
    guide = _dreamed_guide(basis)                          # dreams INCLUDE the candidate's skeletons
    b = seed_basis()
    # rebuild growth path on the CANDIDATE-CARRYING seed so growth order matches _battery_basis
    for extra in basis:
        if extra not in b and extra not in {r[0] for r in _ARITH}:
            b[extra] = basis[extra]                        # carry candidate primitive(s) through
    for name, oracle, pairs, (lo, hi), needs_lib in _ARITH:
        ex = [((a, b_), oracle(a, b_)) for a, b_ in pairs]
        ind, _ = guided_induce(name, ex, b, guide)
        if ind is None or not _equivalent(ind.fn, oracle, lo, hi):
            failing.append(name)
            continue
        if not needs_lib:
            b = grow_basis(b, ind)
    return failing


def evaluate(candidate: DslCandidate, *, tolerance: float = DEFAULT_TOLERANCE) -> GateVerdict:
    """Run the full admission protocol. Deterministic; side-effect free (pure verdict + receipts)."""
    baseline, tasks = _battery_basis()

    # 0 — structural: name collisions shadow existing meaning → reject before anything runs
    if candidate.name in baseline:
        return GateVerdict(False, f"name_collision: '{candidate.name}' already in basis",
                           {"basis": sorted(baseline)})

    cand_basis: Basis = dict(baseline)
    cand_basis[candidate.name] = (candidate.fn, candidate.arity)

    # 1 — battery must stay green (re-derivable + equivalent) with the candidate present
    broken = _oracle_check(cand_basis)
    if broken:
        return GateVerdict(False, f"battery_broken: {broken}", {"failing_kernels": broken})

    # 2 — search-cost regression, measured BOTH ways (brute order + freshly-dreamed guide)
    brute_base = _battery_costs(baseline, tasks, None)
    brute_cand = _battery_costs(cand_basis, tasks, None)
    guided_base = _battery_costs(baseline, tasks, _dreamed_guide(baseline))
    guided_cand = _battery_costs(cand_basis, tasks, _dreamed_guide(cand_basis))

    def _median_delta(base: dict[str, int], cand: dict[str, int]) -> float:
        rel = [(cand[k] - base[k]) / max(1, base[k]) for k in base if base[k] > 0 and cand[k] > 0]
        return statistics.median(rel) if rel else 0.0

    def _max_significant_delta(base: dict[str, int], cand: dict[str, int], floor: int = 10) -> float:
        """Worst per-task regression among tasks whose BASE cost is non-trivial (>= floor tried).
        The median is robust to noise but blind to a single deep regression — and the historical
        i1 failure was exactly that shape (square 17 -> 31, +82%, while small tasks stayed small).
        The floor exempts noise-scale jitter (1 -> 4 tried is not a haystack problem)."""
        rel = [(cand[k] - base[k]) / base[k] for k in base if base[k] >= floor and cand[k] > 0]
        return max(rel) if rel else 0.0

    d_brute, d_guided = _median_delta(brute_base, brute_cand), _median_delta(guided_base, guided_cand)
    dx_brute = _max_significant_delta(brute_base, brute_cand)
    dx_guided = _max_significant_delta(guided_base, guided_cand)
    worst = max(d_brute, d_guided, dx_brute, dx_guided)
    cost_receipts = {"brute_base": brute_base, "brute_cand": brute_cand,
                     "guided_base": guided_base, "guided_cand": guided_cand,
                     "median_delta_brute": round(d_brute, 3),
                     "median_delta_guided": round(d_guided, 3),
                     "max_significant_delta_brute": round(dx_brute, 3),
                     "max_significant_delta_guided": round(dx_guided, 3), "tolerance": tolerance}
    if worst > tolerance:
        return GateVerdict(False,
                           f"search_regression: median cost delta {worst:.1%} exceeds "
                           f"tolerance {tolerance:.0%} (the i1 lesson — bigger language, "
                           f"bigger haystack, no matching search growth)", cost_receipts)

    # 3 — must unlock: at least one frontier task unsolvable before, solvable+verified after
    unlocked: list[str] = []
    for tname, ex in candidate.unlock_tasks.items():
        before, _ = guided_induce(tname, ex, baseline)
        if before is not None:
            continue                                        # not a frontier task — no credit
        after, _ = guided_induce(tname, ex, cand_basis)
        if after is not None:
            unlocked.append(tname)
    if not unlocked:
        return GateVerdict(False, "no_unlock: candidate adds search surface but solves nothing new",
                           {**cost_receipts, "claimed": sorted(candidate.unlock_tasks)})

    grown = dict(baseline)
    grown[candidate.name] = (candidate.fn, candidate.arity)
    return GateVerdict(True,
                       f"admitted: unlocks {unlocked}, battery green, "
                       f"worst median cost delta {worst:.1%} ≤ {tolerance:.0%}",
                       {**cost_receipts, "unlocked": unlocked}, basis=grown)
