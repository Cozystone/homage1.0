# -*- coding: utf-8 -*-
"""A2 gate (a): the OE + MDL object search is correct on CONSTRUCTED fixtures (never the eval split).

Proves the three invention-engine properties on the object-op value space:
  * it finds a KNOWN MULTI-STEP object program (deeper than B0.1's depth-1 strategies);
  * relational / rank selection ("2nd largest", "densest") is reachable — the B0.1 crop-reachable lever;
  * OBSERVATIONAL-EQUIVALENCE dedup PRUNES (bank << considered);
  * MDL ORDERS — the smallest verified program is the one returned;
  * propose-verify EXACT — a contradictory task abstains (None), never guesses.
"""
from packages.arc_agi import objects as O
from packages.arc_agi.oe_search import oe_object_search, evaluate_tree, mdl_size, _unique_rank


def _rot90(g):  return [list(r) for r in zip(*g[::-1])]
def _seg0(g):   return O.segment(g, connectivity=4, by_color=True, background=0)


# ---------------------------------------------------------------- relational selection (crop-reachable-6)
def test_relational_selection_second_largest_is_reachable():
    # Three objects of DISTINCT sizes and DISTINCT colours; output = crop of the 2ND-LARGEST. None of the
    # B0.1 selectors (largest/smallest/odd_*/unique_color/...) picks the middle object, so this was
    # UNREACHABLE before; the relational selector makes it a size-3 program.
    def build(g):
        return O.crop_bbox(g, _unique_rank(_seg0(g), lambda o: o.size, 1, True))
    t1 = [[1, 1, 1, 0, 0, 0],
          [1, 1, 1, 0, 2, 2],      # colour1 size3 (largest), colour2 size2 (2nd)
          [0, 0, 0, 0, 0, 3]]      # colour3 size1 (smallest)
    t2 = [[4, 4, 4, 4, 0],
          [0, 0, 0, 0, 0],         # colour4 size4 (largest)
          [5, 5, 0, 0, 6]]         # colour5 size2 (2nd), colour6 size1 (smallest)
    train = [(t1, build(t1)), (t2, build(t2))]
    prog, st = oe_object_search(train, return_stats=True)
    assert prog is not None
    assert st["solver_tree"][0] == "crop"                                  # crop( ... )
    assert st["solver_tree"][1][:2] == ("sel", "2nd_largest")             # ...of the 2nd-largest selector
    assert st["solver_size"] == 3
    # generalises to a fresh grid the search never saw
    t3 = [[7, 7, 7, 0], [0, 0, 0, 0], [8, 8, 0, 9]]
    assert prog(t3) == build(t3)


# ---------------------------------------------------------------- multi-step composition (deeper than depth-1)
def test_multistep_select_crop_geometry_composition():
    # A 4-op program: geometry( crop( selected object ) ). The 2nd-largest object is an ASYMMETRIC shape
    # so a geometry op is genuinely required (size-3 select+crop alone cannot reproduce train).
    def build(g):
        o = _unique_rank(_seg0(g), lambda o: o.size, 1, True)
        return _rot90(O.crop_bbox(g, o))
    # object shapes chosen asymmetric (L-trominoes) so crop != rot90(crop)
    t1 = [[1, 1, 1, 1, 0, 0],
          [1, 1, 1, 1, 0, 0],     # size-8 block (largest)
          [0, 0, 0, 0, 0, 0],
          [2, 0, 0, 0, 0, 0],
          [2, 2, 0, 0, 0, 3]]     # L-tromino colour2 size3 (2nd), singleton colour3 (smallest)
    t2 = [[4, 4, 4, 0, 0],
          [4, 4, 4, 0, 0],        # size-6 block (largest)
          [5, 0, 0, 0, 0],
          [5, 5, 0, 0, 6]]        # L-tromino colour5 size3 (2nd), singleton colour6
    train = [(t1, build(t1)), (t2, build(t2))]
    prog, st = oe_object_search(train, return_stats=True)
    assert prog is not None
    assert st["solver_size"] == 4                              # a genuine 4-op composition
    # the returned program is size-4 because NO size<=3 program reproduces train:
    assert oe_object_search(train, max_size=3) is None
    # and it generalises
    t3 = [[7, 7, 7, 7], [7, 7, 7, 7], [8, 0, 0, 0], [8, 8, 0, 9]]
    assert prog(t3) == build(t3)


# ---------------------------------------------------------------- OE dedup PRUNES
def test_observational_equivalence_prunes_the_bank():
    # A simple extract-largest-crop task. Many segmentation configs and many selectors coincide on these
    # small train inputs, so OE dedup must collapse them: the kept bank is far smaller than considered.
    t1 = [[3, 3, 0], [3, 3, 0], [0, 0, 4]]
    t2 = [[4, 0, 0], [0, 3, 3], [0, 3, 3]]
    train = [(t1, [[3, 3], [3, 3]]), (t2, [[3, 3], [3, 3]])]
    prog, st = oe_object_search(train, return_stats=True)
    assert prog is not None
    assert st["oe_pruned"] > 0                                 # dedup actually fired
    assert st["bank"] < st["considered"]                      # kept << generated (the OE collapse)
    assert st["bank"] <= st["considered"] - st["oe_pruned"]   # bank excludes every pruned/failed node


# ---------------------------------------------------------------- MDL ORDERS (smallest returned)
def test_mdl_orders_returns_the_smallest_program():
    # The rule is a plain horizontal flip of the whole grid — reachable as the size-2 program geo(in).
    # A size-4 program (flip; then two ops that cancel) would ALSO verify, but MDL/size-ascending must
    # return the size-2 one. (We assert via the returned tree's mdl_size.)
    t1 = [[1, 2, 3], [4, 5, 6]]
    t2 = [[7, 8], [9, 1]]
    train = [(t1, [list(reversed(r)) for r in t1]), (t2, [list(reversed(r)) for r in t2])]
    prog, st = oe_object_search(train, return_stats=True)
    assert prog is not None
    assert st["solver_size"] == 2                              # geo(flip_h, in): the minimal program
    assert mdl_size(st["solver_tree"]) == st["solver_size"]    # size == the invention engine's raw_len
    assert prog([[1, 2], [3, 4]]) == [[2, 1], [4, 3]]


# ---------------------------------------------------------------- propose-verify EXACT (abstains, never guesses)
def test_contradictory_train_abstains():
    # Same input mapped to two different outputs -> no deterministic object program reproduces both -> None.
    train = [([[1, 1]], [[2, 2]]), ([[1, 1]], [[3, 3]])]
    assert oe_object_search(train) is None


def test_no_verified_program_abstains_not_guesses():
    # A task whose rule is outside the object DSL (arbitrary unlearnable recolour differing per pair) ->
    # the search must return None (abstain), never a partial/guess grid.
    train = [([[1, 0], [0, 1]], [[5, 9], [2, 7]]),
             ([[1, 0], [0, 1]], [[3, 4], [8, 6]])]
    assert oe_object_search(train) is None


# ---------------------------------------------------------------- evaluator round-trips a hand-built program
def test_evaluate_tree_matches_hand_computation():
    g = [[0, 2, 2, 0], [0, 2, 2, 0], [5, 0, 0, 0]]
    tree = ("crop", ("sel", "largest", ("seg", 0)))           # extract the largest object's bbox
    assert evaluate_tree(tree, g) == [[2, 2], [2, 2]]
    assert mdl_size(tree) == 3
