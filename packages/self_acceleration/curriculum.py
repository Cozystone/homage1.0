# -*- coding: utf-8 -*-
"""H4 — the WALL CURRICULUM (signal-4 substrate).

A curriculum of target functions of INCREASING structural complexity that the BASE vocabulary (the X4.4
identity scalar fold) CANNOT synthesise — each needs a scheme the prior inventions can compose toward.
The spine is the ORDER-STATISTIC ladder (2nd..5th largest): each rung needs an accumulator one component
wider than the last, and — critically — the invented "next order statistic" step of rung k is exactly the
auxiliary rung k+1 needs, so the ladder is a genuine COMPOUNDING chain. One breadth wall (range = max-min)
uses a different scheme shape (a computed projection over two generic auxiliaries) to show the proposer is
not a one-trick pony.

Each wall is specified ONLY by its REFERENCE FUNCTION in plain Python (never seen by the synthesiser) —
the external-verification discipline of `external_corpus`: the engine sees only I/O examples and must
rediscover a grammar program that reproduces them. References are clamped to the interpreter's bounds.

`needs` is a human note on the scheme a wall requires (documentation only — never handed to the proposer).
Deterministic, No-LLM, stdlib.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable

from packages.evolution import scheme_synthesis as ss


def _kth_desc(xs: tuple, k: int) -> int:
    a = sorted(xs, reverse=True)
    return a[k] if len(a) > k else 0


def _range(xs: tuple) -> int:
    return (max(xs) - min(xs)) if xs else 0


@dataclass(frozen=True)
class Wall:
    name: str
    ref: Callable[[dict], Any]         # plain-Python semantics (never seen by the synthesiser)
    needs: str                         # the scheme it requires (documentation only)
    listvar: str = "xs"
    lo: int = 0
    hi: int = 9
    max_len: int = 7

    def outer(self, n_lists: int, rng: random.Random) -> list:
        """Prefix-closed oracle I/O for the lambda^2 deduction (reuses ss.prefix_closed_io)."""
        return ss.prefix_closed_io(self.ref, self.listvar, n_lists=n_lists, max_len=self.max_len,
                                   rng=rng, lo=self.lo, hi=self.hi)

    def samples(self, n: int, rng: random.Random) -> list:
        """Independent full-length (env, out) examples for verification / holdout."""
        out, seen = [], set()
        tries = 0
        while len(out) < n and tries < n * 10:
            tries += 1
            xs = tuple(rng.randint(self.lo, self.hi) for _ in range(rng.randint(0, self.max_len)))
            if xs in seen:
                continue
            seen.add(xs)
            env = {self.listvar: xs}
            out.append((env, self.ref(env)))
        return out


# THE CURRICULUM — order-statistic spine (compounding) + one computed-projection breadth wall.
CURRICULUM: list[Wall] = [
    Wall("second_max", lambda e: _kth_desc(tuple(e["xs"]), 1),
         needs="grow to k=2 projection chain; INVENT the 'next order statistic' step (running_max aux)"),
    Wall("range", lambda e: _range(tuple(e["xs"])),
         needs="computed projection over {running_max, running_min} (LIFT+PROJECT; breadth)"),
    Wall("third_max", lambda e: _kth_desc(tuple(e["xs"]), 2),
         needs="grow to k=3; COMPOUNDS on second_max's promoted order-stat template"),
    Wall("fourth_max", lambda e: _kth_desc(tuple(e["xs"]), 3),
         needs="grow to k=4; COMPOUNDS on third_max"),
    Wall("fifth_max", lambda e: _kth_desc(tuple(e["xs"]), 4),
         needs="grow to k=5; COMPOUNDS on fourth_max"),
]


def by_name(name: str) -> Wall:
    return next(w for w in CURRICULUM if w.name == name)
