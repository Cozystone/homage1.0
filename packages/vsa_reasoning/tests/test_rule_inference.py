# -*- coding: utf-8 -*-
"""Gate (b): algebraic rule inference — ONE-pass T, generalizes to held-out, ABSTAINS with no rule.

The point the lookup table cannot match: the shift is inferred from a couple of pairs and then
applies to values NEVER seen in training. And the honest boundary: a function that is not a group
action (an arbitrary permutation) is refused, not fabricated.
"""
from packages.vsa_reasoning.fhrr_core import RingCodebook
from packages.vsa_reasoning.rule_inference import (
    infer_shift_rule, infer_colormap_rule, infer_position_shift_rule,
)


# ---------------------------------------------------------------- cyclic attribute shift
def test_cyclic_shift_inferred_in_one_pass_and_generalizes():
    cb = RingCodebook(10, dim=2048, seed=7, tag="color")
    k = 3
    train = [(c, (c + k) % 10) for c in (1, 2, 4)]     # 0,3,5,6,7,8,9 never seen as inputs
    rule = infer_shift_rule(train, cb)
    assert rule is not None and rule.k == 3
    assert rule.consensus > 0.999                        # a single T from every pair
    # generalizes to held-out values the lookup never saw
    for c in (7, 8, 9, 0):
        assert rule.apply(c) == (c + k) % 10


def test_shift_abstains_on_noncyclic_permutation():
    # a valid FUNCTION but not a ring translation (swaps) -> per-pair T disagree -> abstain
    cb = RingCodebook(10, dim=2048, seed=7, tag="color")
    perm = {0: 0, 1: 2, 2: 1, 3: 5, 4: 4, 5: 3, 6: 6, 7: 9, 8: 8, 9: 7}
    train = [(c, perm[c]) for c in (1, 3, 7)]
    assert infer_shift_rule(train, cb) is None


def test_shift_abstains_on_inconsistent_data():
    # same input -> two different outputs across pairs (not even a function)
    cb = RingCodebook(10, dim=2048, seed=7, tag="color")
    assert infer_shift_rule([(1, 2), (1, 5)], cb) is None


def test_identity_shift_is_a_valid_rule():
    cb = RingCodebook(10, dim=2048, seed=7, tag="color")
    rule = infer_shift_rule([(2, 2), (5, 5)], cb)
    assert rule is not None and rule.k == 0
    assert rule.apply(9) == 9


# ---------------------------------------------------------------- colour-map on grids
def test_colormap_rotation_applies_to_unseen_colours():
    # a pure +2 colour rotation on grids; the inferred rule recolours colours absent from train
    g_in = [[0, 1, 2], [3, 4, 5]]
    g_out = [[(v + 2) % 10 for v in row] for row in g_in]
    rule = infer_colormap_rule([(g_in, g_out)])
    assert rule is not None and rule.shift.k == 2
    # 7,8,9 never appear in training; a lookup table would abstain, the algebra extrapolates
    assert rule.apply_grid([[7, 8, 9]]) == [[9, 0, 1]]


def test_colormap_abstains_on_non_shift_recolor():
    # an arbitrary object-ish recolor (1->3 but 2->3 too, and 3->1) is not a ring rotation
    g_in = [[1, 2, 3]]
    g_out = [[3, 3, 1]]
    assert infer_colormap_rule([(g_in, g_out)]) is None


def test_colormap_abstains_on_different_dims():
    assert infer_colormap_rule([([[1, 2]], [[1], [2]])]) is None


# ---------------------------------------------------------------- 2-D translation
def test_position_shift_inferred_and_generalizes():
    # translation (dr,dc) = (1,2) on a 5x5 torus, from 3 observations, generalizes to a new position
    train = [((0, 0), (1, 2)), ((1, 1), (2, 3)), ((3, 4), (4, 1))]
    rule = infer_position_shift_rule(train, n_rows=5, n_cols=5)
    assert rule is not None and (rule.dr, rule.dc) == (1, 2)
    assert rule.apply((2, 2)) == (3, 4)                  # unseen position
    assert rule.apply((4, 4)) == (0, 1)                  # wraps on the torus


def test_position_shift_abstains_when_no_single_translation():
    # each object moves by a DIFFERENT delta -> no single T -> abstain
    train = [((0, 0), (1, 0)), ((1, 1), (1, 3))]
    assert infer_position_shift_rule(train, n_rows=5, n_cols=5) is None
