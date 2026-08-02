# -*- coding: utf-8 -*-
"""H4 v2 — the CROSS-FAMILY wall curriculum (the honest signal-4 substrate).

v1's curriculum is ONE compounding family (the order-statistic spine) plus a single off-family wall
(`range`). Enough to measure WITHIN-family self-acceleration, not CROSS-family transfer. v2 needs SEVERAL
structurally-distinct families, each requiring a DIFFERENT move-composition, so we can ask the real
question: as the ledger accumulates recipes across families, does a LEARNED recogniser make a NOVEL
family's walls cheaper (open-ended acceleration), or does each new family still cost a fresh search?

Only GENUINE WALLS are included — targets the base identity scalar fold CANNOT express (a functional
conflict: the accumulator must hold richer-than-scalar state). Empirically (verified): sum, count, max,
min are plain scalar folds (NOT walls); the composites below each need a 2+-component accumulator.

FOUR FAMILIES, indexed by the LIFT-op AUX-SET their computed projection needs (a subset of {max2,min2,
add}), so the "compose moves" question is crisp — every op appears in TWO families, and a held-out
family's aux-set is a CO-OCCURRENCE the recogniser must compose from per-op signals seen elsewhere:
  * order   — projection_chain (GROW to depth k): 2nd..5th largest. The compounding spine (driver max2).
  * extent  — computed_projection over {max2, min2}: range = max-min, maxmin_sum = max+min.
  * summin  — computed_projection over {add, min2}:  sum_minus_min = sum-min.
  * summax  — computed_projection over {add, max2}:  sum_minus_max = sum-max.

Each wall is specified ONLY by its plain-Python REFERENCE (never seen by the synthesiser — external
verification). `needs` is documentation only, NEVER handed to the recogniser/proposer. No-LLM, stdlib.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Callable

from packages.evolution import open_domain as od
from packages.evolution import scheme_synthesis as ss

C = od._clamp_int


def _kth_desc(xs: tuple, k: int) -> int:
    a = sorted(xs, reverse=True)
    return a[k] if len(a) > k else 0


@dataclass(frozen=True)
class CFWall:
    """A cross-family wall. Mirrors v1's `curriculum.Wall` but carries `family` (for held-out splitting;
    NEVER a model input) and `min_len` (computed families use non-empty lists to avoid the empty-list/
    CLAMP sentinel wart). `true_aux` is the aux-set that crosses it — documentation / oracle-scoring only,
    NEVER handed to the recogniser."""
    name: str
    family: str
    ref: Callable[[dict], Any]
    needs: str
    true_family: str = "computed_projection"   # the move family that crosses it (scoring only)
    true_aux: tuple[str, ...] = ()              # the aux-set that crosses it (scoring only)
    listvar: str = "xs"
    lo: int = 0
    hi: int = 9
    max_len: int = 7
    min_len: int = 0

    def oracle(self, xs: tuple) -> Any:
        return self.ref({self.listvar: xs})

    def outer(self, n_lists: int, rng: random.Random) -> list:
        return ss.prefix_closed_io(self.ref, self.listvar, n_lists=n_lists, max_len=self.max_len,
                                   rng=rng, lo=self.lo, hi=self.hi, min_len=self.min_len)

    def samples(self, n: int, rng: random.Random) -> list:
        out, seen = [], set()
        tries = 0
        while len(out) < n and tries < n * 12:
            tries += 1
            xs = tuple(rng.randint(self.lo, self.hi) for _ in range(rng.randint(self.min_len, self.max_len)))
            if xs in seen:
                continue
            seen.add(xs)
            env = {self.listvar: xs}
            out.append((env, self.ref(env)))
        return out


def _range(xs: tuple) -> int:
    return (max(xs) - min(xs)) if xs else 0


def _maxmin_sum(xs: tuple) -> int:
    return C(max(xs) + min(xs)) if xs else 0


def _sum_minus_min(xs: tuple) -> int:
    return C(sum(xs) - min(xs)) if xs else 0


def _sum_minus_max(xs: tuple) -> int:
    return C(sum(xs) - max(xs)) if xs else 0


# THE CURRICULUM — four families, presented family-by-family (the order the flywheel accumulates in).
FAMILIES: dict[str, list[CFWall]] = {
    "order": [
        CFWall("second_max", "order", lambda e: _kth_desc(tuple(e["xs"]), 1),
               "projection_chain depth 2; INVENT next-order-statistic step (max2 driver)",
               true_family="projection_chain", true_aux=("max2",)),
        CFWall("third_max", "order", lambda e: _kth_desc(tuple(e["xs"]), 2),
               "projection_chain depth 3; COMPOUNDS on second_max template",
               true_family="projection_chain", true_aux=("max2",)),
        CFWall("fourth_max", "order", lambda e: _kth_desc(tuple(e["xs"]), 3),
               "projection_chain depth 4; COMPOUNDS on third_max",
               true_family="projection_chain", true_aux=("max2",)),
        CFWall("fifth_max", "order", lambda e: _kth_desc(tuple(e["xs"]), 4),
               "projection_chain depth 5; COMPOUNDS on fourth_max",
               true_family="projection_chain", true_aux=("max2",)),
    ],
    "extent": [
        CFWall("range", "extent", lambda e: _range(tuple(e["xs"])),
               "computed_projection over {max2,min2}, pi=sub", true_aux=("max2", "min2"), min_len=1),
        CFWall("maxmin_sum", "extent", lambda e: _maxmin_sum(tuple(e["xs"])),
               "computed_projection over {max2,min2}, pi=add", true_aux=("max2", "min2"), min_len=1),
    ],
    "summin": [
        CFWall("sum_minus_min", "summin", lambda e: _sum_minus_min(tuple(e["xs"])),
               "computed_projection over {add,min2}, pi=sub", true_aux=("add", "min2"), min_len=1),
    ],
    "summax": [
        CFWall("sum_minus_max", "summax", lambda e: _sum_minus_max(tuple(e["xs"])),
               "computed_projection over {add,max2}, pi=sub", true_aux=("add", "max2"), min_len=1),
    ],
}

FAMILY_ORDER: tuple[str, ...] = ("order", "extent", "summin", "summax")


def all_walls() -> list[CFWall]:
    return [w for fam in FAMILY_ORDER for w in FAMILIES[fam]]


def walls_of(family: str) -> list[CFWall]:
    return list(FAMILIES[family])


def by_name(name: str) -> CFWall:
    return next(w for w in all_walls() if w.name == name)
