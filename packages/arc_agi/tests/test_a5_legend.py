# -*- coding: utf-8 -*-
"""A5 gate (a): LEGEND / in-grid-table reading is correct on CONSTRUCTED fixtures (never the eval split).

Proves the front-end DECODES a key region from each grid and applies it to the body, propose-verified EXACT
(reproduce ALL train exactly or ABSTAIN):
  * COLOUR-PERMUTATION  — a separable 2x2 corner block whose rows are swap pairs; DERIVED per grid and
                          generalising to a TEST whose palette the train pairs never show (a fixed colour
                          TABLE could not — the map is READ from the grid's own legend);
  * SHAPE->COLOUR DICT  — a marker colour's connected shape names the colour the body becomes; DERIVED across
                          train and applied to the SAME shape at an UNSEEN placement;
  * NO-LEGEND           — a grid with no key region abstains (None), never guesses;
  * INCONSISTENT-LEGEND — a legend whose reading contradicts a train pair abstains (None).
Each fixture's TEST grid uses colours/positions the train pairs never show, so only the derived reading (not
a memorised table) can be right.
"""
from packages.arc_agi import legend as L
from packages.arc_agi import objects as O


# ================================================================ key-region detection helpers
def test_corner_block_detects_separable_2x2():
    g = [[4, 2, 0, 0, 0],
         [3, 7, 0, 0, 0],
         [0, 0, 0, 0, 0],
         [0, 0, 0, 3, 0],
         [0, 0, 0, 0, 0]]
    assert L._corner_block(g, "tl", 0) == (0, 0, 1, 1)     # the 2x2 corner key block
    assert L._corner_block(g, "br", 0) is None             # br corner cell is background


def test_corner_block_rejects_nonseparable():
    # a body cell sits in the ring just outside the block's bbox (not 8-connected across the bg gap at (1,1))
    # -> the key is NOT walled off from the body -> None
    g = [[4, 4, 0, 0],
         [4, 0, 0, 0],
         [0, 0, 2, 0],
         [0, 0, 0, 0]]
    assert L._corner_block(g, "tl", 0) is None


def test_corner_block_rejects_when_too_large():
    # a big non-bg corner region is not a small self-contained key block -> None (area cap)
    g = [[4] * 6 for _ in range(6)]
    assert L._corner_block(g, "tl", 0) is None


def test_read_pairs_rows():
    assert L._read_pairs([[4, 2], [3, 7]], 0, "rows") == [(4, 2), (3, 7)]
    assert L._read_pairs([[4, 0, 2]], 0, "rows") == [(4, 2)]      # background between pair members is skipped


def test_framed_corner_detects_bordered_cell():
    # a colour-5 L-frame (col 2 rows 0-2, row 2 cols 0-2) walls off the tl 2x2; the named colour is the 3
    g = [[3, 0, 5, 0, 0],
         [0, 0, 5, 0, 0],
         [5, 5, 5, 0, 0],
         [0, 0, 0, 3, 0],
         [0, 0, 0, 0, 0]]
    got = L._framed_corner(g, "tl", 0)
    assert got is not None
    region, border, inner = got
    assert region == (0, 0, 2, 2)      # full L-cornered rectangle (kept region)
    assert border == 5 and inner == [3]


def test_framed_corner_none_when_unframed():
    g = [[3, 0, 0], [0, 0, 0], [0, 0, 3]]     # no border colour walls off the corner
    assert L._framed_corner(g, "tl", 0) is None


# ================================================================ COLOUR-PERMUTATION legend
def _perm_task():
    """Legend = top-left 2x2, rows are swap pairs; the body cells are swapped; the legend is kept."""
    def build(a, b, c, d):
        gi = [[a, b, 0, 0, 0, 0],
              [c, d, 0, 0, 0, 0],
              [0, 0, 0, 0, 0, 0],
              [0, 0, 0, a, c, 0],
              [0, 0, 0, b, d, 0],
              [0, 0, 0, 0, 0, 0]]
        go = [row[:] for row in gi]
        go[3][3], go[3][4] = b, d       # body row: a->b, c->d
        go[4][3], go[4][4] = a, c       # body row: b->a, d->c
        return gi, go
    train = [build(4, 2, 3, 7), build(1, 3, 8, 9)]
    test_in, test_out = build(5, 6, 2, 4)    # HELD-OUT palette 5,6,2,4 (never in train)
    return train, test_in, test_out


def test_colormap_legend_derives_and_generalises():
    train, test_in, test_out = _perm_task()
    prog = L.strat_legend_colormap(train)
    assert prog is not None
    assert prog(test_in) == test_out         # decoded per grid -> generalises to the unseen palette


def test_colormap_legend_beats_fixed_table():
    # a whole-grid colour TABLE cannot solve it (the legend block is KEPT, not remapped) -> it must abstain
    # or be wrong on the held-out palette; only the per-grid legend reading is right.
    from packages.arc_agi import solver as S
    train, test_in, test_out = _perm_task()
    cm = S._learn_colormap(train)
    assert cm is None or [[cm.get(v, v) for v in row] for row in test_in] != test_out


# ================================================================ FRAMED cell names a victim colour
def _framed_victim_task():
    """A colour-5 L-frame walls off a corner cell naming colour C; every BODY cell of colour C is erased
    (-> bg); the frame and the named cell are kept. The named colour is DECODED per grid."""
    def build(C, body_cells):
        gi = [[0] * 6 for _ in range(6)]
        for r in range(3):
            gi[r][2] = 5                       # vertical frame segment
        for c in range(3):
            gi[2][c] = 5                       # horizontal frame segment
        gi[0][0] = C                           # the framed (named) cell
        for (r, c) in body_cells:
            gi[r][c] = C
        go = [row[:] for row in gi]
        for (r, c) in body_cells:
            go[r][c] = 0                        # named colour erased from the body
        return gi, go
    train = [build(3, [(3, 3), (3, 5), (4, 1)]),
             build(4, [(4, 4), (5, 0), (3, 4), (5, 5)])]
    test_in, test_out = build(7, [(3, 0), (4, 5), (5, 3)])   # HELD-OUT named colour 7
    return train, test_in, test_out


def test_framed_legend_names_victim_and_generalises():
    train, test_in, test_out = _framed_victim_task()
    prog = L.strat_legend_framed(train)
    assert prog is not None
    assert prog(test_in) == test_out            # the named colour is read from the grid, so 7 generalises


# ================================================================ SHAPE->COLOUR dictionary
def _shape_dict_task():
    """Marker colour 4; its connected shape names the colour the colour-8 body becomes; marker -> bg."""
    def build(marker_cells, body_cells, out_color):
        gi = [[0] * 6 for _ in range(6)]
        for (r, c) in marker_cells:
            gi[r][c] = 4
        for (r, c) in body_cells:
            gi[r][c] = 8
        go = [row[:] for row in gi]
        for (r, c) in marker_cells:
            go[r][c] = 0                      # marker consumed
        for (r, c) in body_cells:
            go[r][c] = out_color              # body recoloured to the dict value
        return gi, go
    L_shape = [(0, 0), (1, 0), (1, 1)]        # an L (-> colour 2)
    bar = [(0, 0), (0, 1)]                     # a bar (-> colour 3)
    train = [build(L_shape, [(2, 3), (2, 4), (3, 3)], 2),
             build(bar, [(4, 1), (4, 2), (5, 2)], 3)]
    # TEST: the L shape at an UNSEEN placement, a different body -> body must become 2
    test_in, test_out = build([(0, 4), (1, 4), (1, 5)], [(3, 0), (3, 1), (4, 1)], 2)
    return train, test_in, test_out


def test_shape_dict_derives_and_applies_to_unseen_placement():
    train, test_in, test_out = _shape_dict_task()
    prog = L.strat_shape_dict_recolor(train)
    assert prog is not None
    assert prog(test_in) == test_out          # looked up by SHAPE, independent of placement


# ================================================================ honesty: abstain on no / inconsistent legend
def test_abstains_when_no_legend():
    # a lone recolour with no corner key block and no marker dictionary -> both readers abstain
    task = [([[0, 0, 0], [0, 5, 0], [0, 0, 0]], [[0, 0, 0], [0, 7, 0], [0, 0, 0]])]
    assert L.strat_legend_colormap(task) is None
    assert L.strat_shape_dict_recolor(task) is None


def test_colormap_abstains_when_inconsistent():
    # both grids carry a 2-colour corner legend, but one body SWAPS and the other does NOT -> no single
    # reading reproduces both -> abstain (never a guess).
    a = ([[3, 4, 0, 0], [0, 0, 0, 0], [0, 0, 3, 0], [0, 0, 0, 0]],
         [[3, 4, 0, 0], [0, 0, 0, 0], [0, 0, 4, 0], [0, 0, 0, 0]])   # body 3->4 (swap)
    b = ([[5, 6, 0, 0], [0, 0, 0, 0], [0, 0, 5, 0], [0, 0, 0, 0]],
         [[5, 6, 0, 0], [0, 0, 0, 0], [0, 0, 5, 0], [0, 0, 0, 0]])   # body 5->5 (no swap)
    assert L.strat_legend_colormap([a, b]) is None


def test_shape_dict_abstains_when_inconsistent():
    # the SAME marker shape maps to two DIFFERENT body colours across pairs -> dictionary collision -> abstain
    def build(out_color):
        gi = [[4, 0, 0, 0], [4, 4, 0, 0], [0, 0, 8, 0], [0, 0, 8, 8]]
        go = [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, out_color, 0], [0, 0, out_color, out_color]]
        return gi, go
    assert L.strat_shape_dict_recolor([build(2), build(3)]) is None
