# -*- coding: utf-8 -*-
"""Object-centric front-end: segmentation, object attributes, generic ops, and the propose-verify
object strategies — all on CONSTRUCTED fixtures (never the eval split). Gate (a)."""
from packages.arc_agi.objects import (
    Obj, segment, mode_color, crop_bbox, render_mask, gravity, erase_objects, solid_rect,
    sel_largest, sel_smallest, sel_unique_color, sel_odd_shape,
    strat_select_crop, strat_filter, strat_recolor, strat_gravity, synthesize_objectwise,
)
from packages.arc_agi.solver import solve_task


# ---------------------------------------------------------------- segmentation
def test_segment_4conn_two_blobs():
    g = [[0, 0, 0], [1, 1, 0], [0, 0, 2]]
    objs = segment(g, connectivity=4, by_color=True, background=0)
    assert len(objs) == 2
    sizes = sorted(o.size for o in objs)
    assert sizes == [1, 2]


def test_segment_diagonal_connectivity_merges():
    g = [[1, 0], [0, 1]]                       # two cells touching only at a corner
    assert len(segment(g, connectivity=4, by_color=True, background=0)) == 2   # 4-conn: separate
    assert len(segment(g, connectivity=8, by_color=True, background=0)) == 1   # 8-conn: one object


def test_segment_by_color_vs_mixed():
    g = [[1, 2], [0, 0]]                       # adjacent cells, different colours
    assert len(segment(g, connectivity=4, by_color=True, background=0)) == 2   # split by colour
    assert len(segment(g, connectivity=4, by_color=False, background=0)) == 1  # one mixed-colour object


def test_segment_background_mode_vs_zero():
    g = [[5, 5], [5, 3]]                       # 5 is the mode (background), 3 is the object
    assert len(segment(g, connectivity=4, by_color=True, background=None)) == 1   # bg = mode(5) -> 1 obj
    assert mode_color(g) == 5
    assert len(segment(g, connectivity=4, by_color=True, background=0)) == 2      # bg = 0 -> 5s and 3 are objects


# ---------------------------------------------------------------- object attributes
def test_obj_attributes_bbox_size_shape():
    g = [[0, 0, 0, 0], [0, 7, 7, 0], [0, 7, 7, 0]]
    (o,) = segment(g, connectivity=4, by_color=True, background=0)
    assert o.size == 4 and o.primary_color == 7
    assert (o.top, o.left, o.bottom, o.right) == (1, 1, 2, 2)
    assert o.height == 2 and o.width == 2 and o.bbox_area == 4
    assert o.norm_shape == frozenset({(0, 0), (0, 1), (1, 0), (1, 1)})


def test_obj_symmetry():
    sym = Obj.from_pixels([(0, 0, 3), (0, 2, 3), (0, 1, 3)])   # horizontal bar -> h & v symmetric
    assert sym.is_h_symmetric and sym.is_symmetric
    asym = Obj.from_pixels([(0, 0, 3), (0, 1, 3), (1, 0, 3)])  # L-tromino -> not symmetric
    assert not asym.is_symmetric


# ---------------------------------------------------------------- selectors
def test_selectors_pick_the_right_object():
    g = [[1, 0, 0, 0], [1, 1, 0, 2], [1, 0, 0, 0], [0, 0, 3, 3]]
    objs = segment(g, connectivity=4, by_color=True, background=0)   # sizes: {1:3, 2:1, 3:2}
    assert sel_largest(objs).primary_color == 1     # the 3-cell object
    assert sel_smallest(objs).primary_color == 2    # the singleton (unique smallest)
    assert sel_unique_color(objs) is None           # all three colours are unique -> ambiguous -> None (never guesses)


def test_selector_ties_return_none():
    g = [[1, 0, 2]]                                   # two singletons, both size 1 -> tie
    objs = segment(g, connectivity=4, by_color=True, background=0)
    assert sel_largest(objs) is None                 # no UNIQUE largest -> None (never guesses)


def test_selector_odd_shape_out():
    # three identical 1x1 dots and one 1x2 bar -> the bar is the odd shape
    g = [[1, 0, 2, 0, 3, 0, 4, 4]]
    objs = segment(g, connectivity=4, by_color=True, background=0)
    odd = sel_odd_shape(objs)
    assert odd is not None and odd.size == 2


# ---------------------------------------------------------------- renderers + generic ops
def test_crop_bbox_and_render_mask():
    g = [[0, 0, 0], [0, 9, 8], [0, 8, 9]]
    (o,) = segment(g, connectivity=8, by_color=False, background=0)   # the 2x2 mixed block
    assert crop_bbox(g, o) == [[9, 8], [8, 9]]
    assert render_mask(o, 0) == [[9, 8], [8, 9]]


def test_gravity_all_directions():
    g = [[1, 0, 2], [0, 0, 0], [0, 3, 0]]
    assert gravity(g, 0, "down") == [[0, 0, 0], [0, 0, 0], [1, 3, 2]]
    assert gravity(g, 0, "up") == [[1, 3, 2], [0, 0, 0], [0, 0, 0]]
    g2 = [[1, 0, 0], [0, 2, 0], [0, 0, 3]]
    assert gravity(g2, 0, "left") == [[1, 0, 0], [2, 0, 0], [3, 0, 0]]
    assert gravity(g2, 0, "right") == [[0, 0, 1], [0, 0, 2], [0, 0, 3]]


def test_erase_and_solid_rect():
    g = [[1, 1, 5], [1, 1, 0]]
    objs = segment(g, connectivity=4, by_color=True, background=0)
    singleton = [o for o in objs if o.size == 1]
    assert erase_objects(g, singleton, 0) == [[1, 1, 0], [1, 1, 0]]
    assert solid_rect(2, 3, 4) == [[4, 4, 4], [4, 4, 4]]


# ---------------------------------------------------------------- propose-verify object strategies
def test_strat_select_crop_learns_largest_and_extracts():
    # every train output = bbox crop of the largest object; the rule generalises to a fresh input
    t1_in = [[3, 3, 0, 0], [3, 3, 0, 0], [0, 0, 0, 4]]
    t2_in = [[4, 0, 0], [0, 3, 3], [0, 3, 3]]
    train = [(t1_in, [[3, 3], [3, 3]]), (t2_in, [[3, 3], [3, 3]])]
    prog = strat_select_crop(train)
    assert prog is not None
    assert prog([[0, 4, 0], [3, 3, 0], [3, 3, 0]]) == [[3, 3], [3, 3]]


def test_strat_filter_denoises_singletons():
    # output = input with singleton 'noise' cells erased, big object kept in place
    t1_in = [[2, 2, 0, 0], [2, 2, 0, 5], [0, 0, 0, 0]]
    t1_out = [[2, 2, 0, 0], [2, 2, 0, 0], [0, 0, 0, 0]]
    t2_in = [[0, 6, 0], [7, 7, 0], [7, 7, 0]]
    t2_out = [[0, 0, 0], [7, 7, 0], [7, 7, 0]]
    prog = strat_filter([(t1_in, t1_out), (t2_in, t2_out)])
    assert prog is not None
    assert prog([[9, 0, 0], [0, 8, 8], [0, 8, 8]]) == [[0, 0, 0], [0, 8, 8], [0, 8, 8]]


def test_strat_recolor_learns_size_to_color_map():
    # objects recoloured by size: size-4 -> 8, size-1 -> 7 (consistent across train)
    t1_in = [[1, 1, 0], [1, 1, 0], [0, 0, 3]]
    t1_out = [[8, 8, 0], [8, 8, 0], [0, 0, 7]]
    t2_in = [[0, 2, 2], [0, 2, 2], [5, 0, 0]]
    t2_out = [[0, 8, 8], [0, 8, 8], [7, 0, 0]]
    prog = strat_recolor([(t1_in, t1_out), (t2_in, t2_out)])
    assert prog is not None
    assert prog([[4, 4, 0], [4, 4, 0], [0, 0, 9]]) == [[8, 8, 0], [8, 8, 0], [0, 0, 7]]


def test_strat_gravity_learns_fall():
    t1_in = [[1, 0, 2], [0, 0, 0], [0, 3, 0]]
    t1_out = [[0, 0, 0], [0, 0, 0], [1, 3, 2]]
    t2_in = [[5, 0], [0, 6], [0, 0]]
    t2_out = [[0, 0], [0, 0], [5, 6]]
    prog = strat_gravity([(t1_in, t1_out), (t2_in, t2_out)])
    assert prog is not None
    assert prog([[7, 0], [0, 0], [0, 8]]) == [[0, 0], [0, 0], [7, 8]]


# ---------------------------------------------------------------- the verify gate stays intact
def test_objectwise_abstains_on_contradictory_train():
    # same input mapped to two different outputs -> no object program can reproduce both -> None
    train = [([[1, 1]], [[2, 2]]), ([[1, 1]], [[3, 3]])]
    assert synthesize_objectwise(train) is None


def test_solver_abstains_when_program_undefined_on_test_input():
    # A genuinely OBJECT-level recolour: same colour (1) but recoloured by SIZE (size-4 -> 8, size-1 ->
    # 7). Because one input colour maps to two output colours, NO global cell colour-map can fit -> the
    # object recolour strategy is what fires. The TEST input has an object of a NOVEL size (5), so the
    # learned map is undefined on it -> the solver ABSTAINS, never emitting a degenerate/empty grid as a
    # guess (0 fabrication). This exercises the object front-end's honesty gate specifically.
    task = {
        "train": [
            {"input": [[1, 1, 0], [1, 1, 0], [0, 0, 1]], "output": [[8, 8, 0], [8, 8, 0], [0, 0, 7]]},
            {"input": [[0, 1, 1], [0, 1, 1], [1, 0, 0]], "output": [[0, 8, 8], [0, 8, 8], [7, 0, 0]]},
        ],
        "test": [{"input": [[1, 1, 1], [1, 1, 0], [0, 0, 0]], "output": [[0, 0, 0], [0, 0, 0], [0, 0, 0]]}],
    }
    pred, solved = solve_task(task)
    assert pred is None and solved is False        # undefined-on-test -> honest abstention, not a guess
