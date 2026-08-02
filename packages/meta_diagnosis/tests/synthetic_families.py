# -*- coding: utf-8 -*-
"""Two synthetic ARC-style failure families used by the gates.

Family A — COLOUR-ONLY: a fixed foreground mask is recoloured (positions unchanged, only the colour
changes). Structural delta: shape preserved, mask identical, only colours differ.

Family C — OBJECT-REMOVAL: two well-separated objects; one is erased to background. Structural
delta: shape preserved, foreground cells and component count DROP.

Each generator returns ``(train_pairs, test_pair)`` where a pair is ``(input_grid, output_grid)``.
The specific positions/colours vary per task, but the STRUCTURE (what these gates cluster on) is
constant within a family, so two tasks in one family produce the same delta features."""
from __future__ import annotations

import random

Grid = list[list[int]]


def _colour_only_pair(rng: random.Random) -> tuple[Grid, Grid]:
    R, C = 4, 4
    gi = [[0] * C for _ in range(R)]
    positions = [(r, c) for r in range(R) for c in range(C)]
    rng.shuffle(positions)
    k = rng.randint(2, 4)
    cells = positions[:k]
    c_in = rng.choice([1, 2, 3])
    c_out = rng.choice([4, 5, 6])          # disjoint from c_in -> always a real recolour
    for (r, c) in cells:
        gi[r][c] = c_in
    go = [row[:] for row in gi]
    for (r, c) in cells:
        go[r][c] = c_out
    return gi, go


def _object_removal_pair(rng: random.Random) -> tuple[Grid, Grid]:
    R, C = 5, 5
    gi = [[0] * C for _ in range(R)]
    c1 = rng.choice([1, 2, 3])
    c2 = rng.choice([4, 5, 6])
    # object 1: horizontal 1x2 block top-left; object 2: horizontal 1x2 block bottom-right.
    # They are far apart (4-connectivity) -> exactly two components.
    gi[0][0] = c1
    gi[0][1] = c1
    gi[R - 1][C - 1] = c2
    gi[R - 1][C - 2] = c2
    go = [row[:] for row in gi]
    go[R - 1][C - 1] = 0                     # erase object 2 -> one object remains
    go[R - 1][C - 2] = 0
    return gi, go


def colour_only_task(rng: random.Random, n_train: int = 3):
    pairs = [_colour_only_pair(rng) for _ in range(n_train + 1)]
    return pairs[:n_train], pairs[n_train]


def object_removal_task(rng: random.Random, n_train: int = 3):
    pairs = [_object_removal_pair(rng) for _ in range(n_train + 1)]
    return pairs[:n_train], pairs[n_train]
