# -*- coding: utf-8 -*-
"""A6 gate (a): the APPLICATION-GRAMMAR primitives are correct on CONSTRUCTED fixtures (never the eval split).

Proves each primitive DERIVES its rule from the task's OWN train pairs and applies it, propose-verified EXACT
(reproduce ALL train or ABSTAIN):
  * D4 SYMMETRY          — the orientation-canonical key groups a shape's 8 orientations and separates
                           genuinely different shapes (the parameter-free primitive both dictionaries rest on);
  * ORIENTATION SHAPE-DICT — a per-grid template dictionary keyed on the D4-canonical shape; applied to a
                           REFLECTED body at an unseen placement AND to a TEST whose template colour the train
                           never show (per-grid reading, not a memorised table);
  * PERIODIC-TILING      — a P x Q lattice of one motif recoloured by a P x Q legend block; applied to a TEST
                           whose legend palette the train never show;
  * ATTACHED MARKER      — each body's OWN adjacent marker shape sets its recolour; markers consumed; the
                           dictionary learned across train and applied to unseen placements;
  * ABSTAIN-ON-INCONSISTENT — a dictionary collision (one shape -> two colours) yields None, never a guess.
Each fixture's TEST grid uses colours/placements the train never show, so only the derived reading can be right.
"""
from packages.arc_agi import application as A


# ================================================================ D4 symmetry primitive
def test_d4_canon_groups_orientations_and_separates_shapes():
    L = frozenset({(0, 0), (1, 0), (1, 1)})           # a bent tromino
    L_rot = frozenset({(0, 0), (0, 1), (1, 1)})       # the same tromino, rotated
    L_refl = frozenset({(0, 1), (1, 0), (1, 1)})      # the same tromino, reflected
    I3 = frozenset({(0, 0), (0, 1), (0, 2)})          # a straight tromino (different orbit)
    assert A._d4_canon(L) == A._d4_canon(L_rot) == A._d4_canon(L_refl)   # one D4 orbit -> one key
    assert A._d4_canon(L) != A._d4_canon(I3)                             # bent != straight
    # translation invariance: shifting the cells does not change the key
    L_shift = frozenset({(5, 7), (6, 7), (6, 8)})
    assert A._d4_canon(L_shift) == A._d4_canon(L)


# ================================================================ orientation-invariant shape dictionary
_L = [(0, 0), (1, 0), (1, 1)]           # bent tromino template
_Lrot = [(0, 0), (0, 1), (1, 1)]        # a rotation of it (a body appears rotated)
_Lrefl = [(1, 0), (0, 0), (0, 1)]       # a reflection of it
_I3 = [(0, 0), (0, 1), (0, 2)]          # straight tromino template
_I3v = [(0, 0), (1, 0), (2, 0)]         # its 90-degree rotation
_BODY = 4


def _orient_build(cA, cB, body_specs):
    """cA=bent-template colour, cB=straight-template colour; body_specs=[(shape, r0, c0, out_colour)].
    Templates are stamped top-left/top-mid; bodies (colour _BODY) are recoloured to their template colour."""
    g = [[0] * 11 for _ in range(9)]
    for r, c in _L:
        g[0 + r][0 + c] = cA
    for r, c in _I3:
        g[0 + r][5 + c] = cB
    out = [row[:] for row in g]
    for shape, r0, c0, tcol in body_specs:
        for r, c in shape:
            g[r0 + r][c0 + c] = _BODY
            out[r0 + r][c0 + c] = tcol
    return g, out


def test_orient_shape_dict_derives_and_applies_to_reflected_unseen_placement():
    # train: bodies are ROTATIONS of the templates (orientation genuinely used)
    t1 = _orient_build(2, 3, [(_Lrot, 4, 0, 2), (_I3v, 4, 6, 3)])
    t2 = _orient_build(2, 3, [(_Lrot, 5, 2, 2), (_I3v, 4, 8, 3)])
    train = [t1, t2]
    prog = A.strat_orient_shape_dict(train)
    assert prog is not None
    # TEST: template colour 8 the train never show + a REFLECTED body at an unseen spot -> per-grid reading
    test_in, test_out = _orient_build(8, 3, [(_Lrefl, 6, 1, 8), (_I3v, 4, 7, 3)])
    assert prog(test_in) == test_out


def test_orient_shape_dict_niche_guard_ignores_exact_only_dicts():
    # if every body EXACTLY equals its template (no rotation/reflection), orientation is not needed -> the
    # orientation strategy defers (None), leaving the plain shape-dict / recolour closers to handle it.
    t1 = _orient_build(2, 3, [(_L, 4, 0, 2), (_I3, 4, 7, 3)])
    t2 = _orient_build(2, 3, [(_L, 5, 2, 2), (_I3, 4, 7, 3)])
    assert A.strat_orient_shape_dict([t1, t2]) is None


# ================================================================ periodic-tiling legend-indexed recolour
_MOTIF = [(0, 0), (0, 1), (1, 0), (1, 1)]        # a 2x2 block motif
_POS = [(0, 0), (0, 3), (3, 0), (3, 3)]          # a 2x2 arrangement of tiles
_TILE = {(0, 0): (0, 0), (0, 3): (0, 1), (3, 0): (1, 0), (3, 3): (1, 1)}
_LATT = 5


def _periodic_build(legend):
    """A 2x2 lattice of the colour-_LATT motif + a 2x2 legend block (rows 6-7, kept); each motif at tile
    (i,j) is recoloured to legend[i][j]."""
    g = [[0] * 7 for _ in range(8)]
    for r0, c0 in _POS:
        for r, c in _MOTIF:
            g[r0 + r][c0 + c] = _LATT
    out = [row[:] for row in g]
    for i in range(2):
        for j in range(2):
            g[6 + i][0 + j] = legend[i][j]
            out[6 + i][0 + j] = legend[i][j]           # legend kept
    for r0, c0 in _POS:
        i, j = _TILE[(r0, c0)]
        for r, c in _MOTIF:
            out[r0 + r][c0 + c] = legend[i][j]
    return g, out


def test_periodic_legend_recolour_derives_and_generalises():
    train = [_periodic_build([[1, 2], [3, 6]]), _periodic_build([[2, 6], [3, 1]])]
    prog = A.strat_periodic_legend(train)
    assert prog is not None
    # TEST: a legend palette (7,8) the train never show -> tile-indexed reading, not a memorised table
    test_in, test_out = _periodic_build([[7, 8], [6, 1]])
    assert prog(test_in) == test_out


# ================================================================ per-object attached marker
_DOT = [(0, 0)]                     # marker shape A
_LMARK = [(0, 0), (1, 0), (1, 1)]   # marker shape B (a corner)
_BODYC = 1
_MARKC = 7


def _marker_build(specs):
    """specs = [(body_r0, body_c0, marker_shape, marker_r0, marker_c0, out_colour)]. Body = a 2x2 colour-1
    block; each body's own adjacent marker (colour 7) shape sets its recolour; markers consumed."""
    g = [[0] * 12 for _ in range(9)]
    out = [[0] * 12 for _ in range(9)]
    for br, bc, mshape, mr, mc, oc in specs:
        for r in range(2):
            for c in range(2):
                g[br + r][bc + c] = _BODYC
                out[br + r][bc + c] = oc            # body recoloured
        for r, c in mshape:
            g[mr + r][mc + c] = _MARKC              # marker present in input, consumed (-> 0) in output
    return g, out


def test_attached_marker_derives_dict_and_applies_to_unseen_placements():
    # dot-marker -> 3, corner-marker -> 6; two body+marker pairs per grid, each marker sits just ABOVE its
    # body (adjacent, disjoint). A 2x2 body at (br,bc); the corner marker at (br-2,bc) so its bottom row is
    # one cell above the body's top; the dot marker at (br-1,bc).
    t1 = _marker_build([(3, 1, _DOT, 2, 1, 3), (3, 8, _LMARK, 1, 8, 6)])
    t2 = _marker_build([(5, 2, _DOT, 4, 2, 3), (5, 8, _LMARK, 3, 8, 6)])
    train = [t1, t2]
    prog = A.strat_attached_marker(train)
    assert prog is not None
    # TEST: same marker shapes at UNSEEN placements -> looked up by local marker shape, markers consumed
    test_in, test_out = _marker_build([(6, 0, _DOT, 5, 0, 3), (3, 6, _LMARK, 1, 6, 6)])
    assert prog(test_in) == test_out
    # honesty: markers are consumed to background, not left in the output
    assert all(7 not in row for row in prog(test_in))


# ================================================================ abstain on inconsistent / no-legend
def test_orient_shape_dict_abstains_on_collision():
    # the SAME canonical body shape (bent tromino) maps to DIFFERENT colours across pairs -> no single dict
    t1 = _orient_build(2, 3, [(_Lrot, 4, 0, 2)])
    t2 = _orient_build(2, 3, [(_Lrot, 4, 0, 3)])       # same shape, different demanded colour -> inconsistent
    assert A.strat_orient_shape_dict([t1, t2]) is None


def test_attached_marker_abstains_on_collision():
    # the SAME marker shape (dot) demands two different body colours across pairs -> dictionary collision
    a = _marker_build([(3, 1, _DOT, 2, 1, 3)])
    b = _marker_build([(3, 1, _DOT, 2, 1, 6)])
    assert A.strat_attached_marker([a, b]) is None


def test_periodic_legend_abstains_without_lattice():
    # a lone recolour with no repeated-motif lattice -> the periodicity reader abstains
    task = [([[0, 5, 0], [0, 0, 0], [0, 0, 0]], [[0, 2, 0], [0, 0, 0], [0, 0, 0]])]
    assert A.strat_periodic_legend(task) is None
