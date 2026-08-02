# -*- coding: utf-8 -*-
"""A4 gate (a): RELATIONAL colour-function recolour is correct on CONSTRUCTED fixtures (never the eval split).

Proves colour = f(RELATIONAL object context) synthesised by DEDUCTION and generalising where a per-value
TABLE must abstain, each propose-verified (reproduce ALL train exactly or abstain):
  * CONTAINMENT   — colour = the enclosing frame's colour ('recolour each dot to the box that holds it');
  * ADJACENCY     — colour = the adjacent object's colour (a colour swap), palette-agnostic;
  * PALETTE-PERM  — colour = a learned permutation keyed by the object's palette INDEX (rank), so a held-out
                    object whose colour is NOVEL but whose rank recurs is coloured correctly;
  * HONESTY       — an inconsistent relational task abstains (None), never guesses.
Each fixture's TEST grid uses colours the train pairs never show, so a colour->colour lookup TABLE would
abstain; only the derived FUNCTION generalises.
"""
from packages.arc_agi import objects as O

SEG0 = {"connectivity": 4, "by_color": True, "background": 0}


# ================================================================ relational feature helpers
def test_enclosing_object_finds_the_frame():
    g = [[3, 3, 3, 0],
         [3, 5, 3, 0],
         [3, 3, 3, 0],
         [0, 0, 0, 0]]
    objs = O.segment(g, **SEG0)
    dot = next(i for i, o in enumerate(objs) if o.primary_color == 5)
    frame = next(i for i, o in enumerate(objs) if o.primary_color == 3)
    assert O.enclosing_object(dot, objs, g, 0) is objs[frame]      # the dot is walled in by the frame
    assert O.enclosing_object(frame, objs, g, 0) is None           # the frame reaches the border


def test_object_neighbor_colors_reads_adjacency():
    g = [[2, 2, 8, 8],
         [2, 2, 8, 8]]
    objs = O.segment(g, **SEG0)
    two = next(i for i, o in enumerate(objs) if o.primary_color == 2)
    assert O.object_neighbor_colors(two, objs, g, 0) == {8}        # object 2's only neighbour colour is 8


def test_grid_palette_is_sorted_nonbg():
    assert O.grid_palette([[0, 4, 2], [7, 0, 4]], 0) == [2, 4, 7]


# ================================================================ CONTAINMENT-keyed recolour (copy function)
def _contain_task():
    # two framed regions per grid; each inner dot (5) takes ITS frame's colour; frames keep their colour.
    def build(frames):
        (fa, fb) = frames
        gi = [[fa, fa, fa, 0, 0, 0, 0],
              [fa, 5,  fa, 0, fb, fb, fb],
              [fa, fa, fa, 0, fb, 5,  fb],
              [0,  0,  0,  0, fb, fb, fb]]
        go = [row[:] for row in gi]
        go[1][1] = fa                          # dot -> its frame colour
        go[2][5] = fb
        return gi, go
    train = [build((3, 6)), build((8, 2))]     # frame colours 3,6 and 8,2
    test_in, test_out = build((4, 7))          # HELD-OUT frame colours 4,7 (never in train)
    return train, test_in, test_out


def test_containment_recolor_derives_and_generalises():
    train, test_in, test_out = _contain_task()
    prog = O.strat_relational_recolor(train)
    assert prog is not None
    assert prog(test_in) == test_out           # generalises to unseen frame colours (a copy function)


# ================================================================ ADJACENCY-keyed recolour (colour swap)
def _adj_task():
    def build(a, b):
        gi = [[a, a, b, b], [a, a, b, b]]
        go = [[b, b, a, a], [b, b, a, a]]      # each object takes its neighbour's colour (a swap)
        return gi, go
    train = [build(2, 8), build(3, 6)]
    return train, *build(1, 4)                 # HELD-OUT colours 1,4


def test_adjacency_recolor_derives_and_generalises():
    train, test_in, test_out = _adj_task()
    prog = O.strat_relational_recolor(train)
    assert prog is not None
    assert prog(test_in) == test_out           # swap generalises to any adjacent pair


# ================================================================ PALETTE-PERMUTATION (rank-keyed table)
def _palette_task():
    # output colour is fixed by the object's PALETTE RANK (0->2, 1->3, 2->4), independent of its input colour.
    def build(cols):
        gi = [[cols[0], 0, cols[1], 0, cols[2]]]
        go = [[2, 0, 3, 0, 4]]
        return gi, go
    train = [build((1, 5, 9)), build((6, 7, 8))]
    test_in, test_out = build((4, 6, 9))       # colour 6 is rank-0 in train B but rank-1 here -> a colour
    return train, test_in, test_out            # table gives the wrong answer; the palette-rank table is right


def test_palette_permutation_derives_and_generalises():
    train, test_in, test_out = _palette_task()
    prog = O.strat_relational_recolor(train)
    assert prog is not None
    assert prog(test_in) == test_out
    # a per-COLOUR table would map 6->2 (its train-B rank-0 colour), which is WRONG here (6 is rank-1 -> 3)
    colour_table = O.strat_recolor(train)
    assert colour_table is None or colour_table(test_in) != test_out


# ================================================================ honesty: inconsistent relational -> abstain
def test_relational_abstains_when_inconsistent():
    # identical adjacency context, contradictory outputs (swap vs no-swap) -> no relational function fits
    bad = [([[2, 2, 8, 8], [2, 2, 8, 8]], [[8, 8, 2, 2], [8, 8, 2, 2]]),
           ([[2, 2, 8, 8], [2, 2, 8, 8]], [[2, 2, 8, 8], [2, 2, 8, 8]])]
    assert O.strat_relational_recolor(bad) is None


def test_relational_abstains_when_reference_absent():
    # a lone object with no adjacency / no container -> every relational colour-function is undefined -> None
    lone = [([[0, 0, 0], [0, 5, 0], [0, 0, 0]], [[0, 0, 0], [0, 7, 0], [0, 0, 0]])]
    assert O.strat_relational_recolor(lone) is None
