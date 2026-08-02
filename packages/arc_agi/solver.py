# -*- coding: utf-8 -*-
"""ARC-AGI solver — No-LLM program synthesis over grid transformations, verified before it answers.

Owner (2026-07-20): try ARC-AGI. ARC is the abstraction-and-reasoning benchmark; it is HARD (frontier
LLMs score modestly, and it is designed to resist memorisation). Our approach is the honest No-LLM one
and the same shape as the rest of ATANOR's reasoning: a library of candidate transformation PROGRAMS,
each VERIFIED against every train pair of a task; a program is only used to answer the test input if it
reproduced ALL train outputs exactly. No fabrication — if no program verifies, the task is abstained
(counted a miss, never a guess).

This is a v0 DSL: a modest set of primitives (geometry, colour-map, tiling, crop, symmetry) plus depth-2
compositions. It will solve only the fraction of tasks whose rule lies in this DSL — the point is a
MEASURED baseline and a real, extensible synthesis harness, not a claim of general solving.
"""
from __future__ import annotations

import time
from collections import Counter
from itertools import product
from typing import Callable

from packages.arc_agi.objects import synthesize_objectwise

Grid = list[list[int]]


# ---------------------------------------------------------------- grid helpers
def dims(g: Grid) -> tuple[int, int]:
    return (len(g), len(g[0]) if g else 0)


def eq(a: Grid, b: Grid) -> bool:
    return a == b


def transpose(g: Grid) -> Grid:
    return [list(r) for r in zip(*g)]


def flip_h(g: Grid) -> Grid:
    return [list(reversed(r)) for r in g]


def flip_v(g: Grid) -> Grid:
    return list(reversed([list(r) for r in g]))


def rot90(g: Grid) -> Grid:
    return [list(r) for r in zip(*g[::-1])]


def rot180(g: Grid) -> Grid:
    return flip_h(flip_v(g))


def rot270(g: Grid) -> Grid:
    return [list(r) for r in zip(*g)][::-1]


def _bg(g: Grid) -> int:
    """Most common colour = background (ARC convention, measured per grid)."""
    c = Counter(v for row in g for v in row)
    return c.most_common(1)[0][0] if c else 0


def crop_content(g: Grid) -> Grid:
    """Bounding box of non-background cells."""
    bg = _bg(g)
    rows = [i for i, r in enumerate(g) if any(v != bg for v in r)]
    cols = [j for j in range(dims(g)[1]) if any(g[i][j] != bg for i in range(dims(g)[0]))]
    if not rows or not cols:
        return g
    return [[g[i][j] for j in range(cols[0], cols[-1] + 1)] for i in range(rows[0], rows[-1] + 1)]


def scale(g: Grid, fr: int, fc: int) -> Grid:
    return [[g[i // fr][j // fc] for j in range(dims(g)[1] * fc)] for i in range(dims(g)[0] * fr)]


def tile(g: Grid, nr: int, nc: int) -> Grid:
    return [row * nc for _ in range(nr) for row in g]


def fractal(g: Grid) -> Grid:
    """Each non-background cell becomes a copy of the whole grid; background cells become blank
    (the classic 007bbfb7 rule) — self-similar tiling by the non-zero mask."""
    R, C = dims(g)
    if R * C > 100:                     # guard: R*R x C*C would explode; ARC fractals are small grids
        return [[]]
    bg = 0                              # ARC convention: 0 is the blank/black background (NOT the most
                                        # common colour — 007bbfb7 has more 7s than 0s, yet 0 is blank)
    out = [[bg] * (C * C) for _ in range(R * R)]
    for i in range(R):
        for j in range(C):
            if g[i][j] != bg:
                for a in range(R):
                    for b in range(C):
                        out[i * R + a][j * C + b] = g[a][b]
    return out


# ---------------------------------------------------------------- parameter-free programs
_GEO: dict[str, Callable[[Grid], Grid]] = {
    "identity": lambda g: g, "flip_h": flip_h, "flip_v": flip_v, "transpose": transpose,
    "rot90": rot90, "rot180": rot180, "rot270": rot270, "crop": crop_content, "fractal": fractal,
}


def _learn_colormap(pairs: list[tuple[Grid, Grid]]) -> dict[int, int] | None:
    """A consistent cell-wise colour substitution across all train pairs (same shape required)."""
    m: dict[int, int] = {}
    for gi, go in pairs:
        if dims(gi) != dims(go):
            return None
        for ri, ro in zip(gi, go):
            for a, b in zip(ri, ro):
                if a in m and m[a] != b:
                    return None
                m[a] = b
    return m


def _learn_tile(pairs: list[tuple[Grid, Grid]]) -> tuple[int, int] | None:
    """A consistent (nr, nc) whole-grid repeat across all pairs."""
    facs = None
    for gi, go in pairs:
        (ri, ci), (ro, co) = dims(gi), dims(go)
        if ri == 0 or ci == 0 or ro % ri or co % ci:
            return None
        f = (ro // ri, co // ci)
        if facs is None:
            facs = f
        elif facs != f:
            return None
    return facs


def synthesize(train: list[tuple[Grid, Grid]],
               deadline: float | None = None) -> Callable[[Grid], Grid] | None:
    """Find a program that reproduces EVERY train output exactly. Cheap-first (an implicit MDL prior):
    parameter-free geometry, learned colour-map, learned tiling/scaling, depth-2 geometry, then the
    OBJECT-CENTRIC DSL (segmentation + generic object ops). None if nothing verifies (then the task is
    abstained — never guessed). `deadline` (time.monotonic value) bounds the search cost per task."""
    # 1) single parameter-free op
    for fn in _GEO.values():
        if all(_safe(fn, gi) == go for gi, go in train):
            return fn
    # 2) learned colour map
    cm = _learn_colormap(train)
    if cm is not None:
        fn = lambda g, _m=cm: [[_m.get(v, v) for v in row] for row in g]
        if all(fn(gi) == go for gi, go in train):
            return fn
    # 3) learned whole-grid tiling / scaling
    tf = _learn_tile(train)
    if tf is not None:
        nr, nc = tf
        for fn in (lambda g: tile(g, nr, nc), lambda g: scale(g, nr, nc)):
            if all(_safe(fn, gi) == go for gi, go in train):
                return fn
    # 4) depth-2 compositions — CHEAP geometry only (no fractal/expensive ops, which explode grid
    #    size and cost; those stay single-op). crop-then-transform is the common ARC idiom.
    cheap = {k: v for k, v in _GEO.items() if k != "fractal"}
    for f1, f2 in product(cheap.values(), repeat=2):
        comp = lambda g, a=f1, b=f2: _safe(b, _safe(a, g))
        if all(comp(gi) == go for gi, go in train):
            return comp
    # 5) OBJECT-CENTRIC DSL — segmentation + generic object ops (select/filter/recolor/gravity/
    #    count/symmetry-repair/compose). Runs after the cheap whole-grid ops so it never changes an
    #    existing solve; same propose-verify gate (verified inside synthesize_objectwise).
    prog = synthesize_objectwise(train, deadline=deadline)
    if prog is not None:
        return prog
    return None


def _safe(fn: Callable[[Grid], Grid], g: Grid) -> Grid:
    try:
        return fn(g)
    except Exception:
        return [[]]


def _valid_grid(g: Grid) -> bool:
    """A real ARC grid is a non-empty rectangle of cells. `[[]]`/`[]`/ragged is the internal
    'program not applicable to this input' sentinel — never a legitimate ARC output."""
    if not g or not isinstance(g, list):
        return False
    w = len(g[0]) if isinstance(g[0], list) else -1
    if w <= 0:
        return False
    return all(isinstance(r, list) and len(r) == w for r in g)


def solve_task(task: dict, time_budget: float | None = 8.0) -> tuple[Grid | None, bool]:
    """Synthesize on train pairs ONLY, apply to the (first) test input. Returns (prediction|None,
    solved) where solved = prediction matches the held-out test output exactly (when present). The
    test output is read ONLY to score; synthesis never sees it. `time_budget` (seconds) bounds the
    per-task search so the larger DSL cannot blow up (None = unbounded)."""
    train = [(p["input"], p["output"]) for p in task.get("train", [])]
    deadline = (time.monotonic() + time_budget) if time_budget is not None else None
    prog = synthesize(train, deadline=deadline)
    if prog is None:
        return None, False
    test = task.get("test", [{}])[0]
    pred = _safe(prog, test["input"])
    if not _valid_grid(pred):
        return None, False   # the verified program is UNDEFINED on this test input -> abstain, never emit a degenerate guess
    solved = "output" in test and pred == test["output"]
    return pred, solved
