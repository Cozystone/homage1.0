# -*- coding: utf-8 -*-
"""A3 gate (a): the new object-DSL constructors are CORRECT on CONSTRUCTED fixtures (never the eval split).

Proves the three A2-named vocabulary levers, each propose-verified:
  * PER-OBJECT MAP+ASSEMBLE — map a per-object transform over EVERY object and re-assemble (the biggest gap):
      - geometry-in-place (flip/rotate each object within its bbox) is reachable UNDER the OE+MDL search;
      - a per-object recolour by a DERIVED colour FUNCTION (a*x+b mod 10) generalises to UNSEEN attribute
        values where a lookup TABLE must abstain (the function-not-table lever), and ABSTAINS with no fit.
  * RELATIONAL / REFERENCE-RELATIVE SELECTION — has-holes, touches-border, colour-matches-a-marker select an
    object no single intrinsic attribute identifies.
  * HONESTY (unchanged, EXACT) — contradictory train abstains (None), never guesses.
"""
from packages.arc_agi import objects as O
from packages.arc_agi.oe_search import (oe_object_search, _SEL_EXT,
                                        _sel_has_holes, _sel_color_matches_marker,
                                        _sel_touches_border, _sel_interior)

SEG0 = {"connectivity": 4, "by_color": True, "background": 0}


def _seg0(g):
    return O.segment(g, **SEG0)


# ================================================================ perception primitives
def test_num_holes_counts_enclosed_background():
    ring = O.Obj.from_pixels([(0, 0, 5), (0, 1, 5), (0, 2, 5),
                              (1, 0, 5), (1, 2, 5),
                              (2, 0, 5), (2, 1, 5), (2, 2, 5)])         # 3x3 ring -> one hole
    solid = O.Obj.from_pixels([(0, 0, 5), (0, 1, 5), (1, 0, 5), (1, 1, 5)])
    two = O.Obj.from_pixels([(0, 0, 5), (0, 1, 5), (0, 2, 5), (0, 3, 5), (0, 4, 5),
                             (1, 0, 5), (1, 2, 5), (1, 4, 5),
                             (2, 0, 5), (2, 1, 5), (2, 2, 5), (2, 3, 5), (2, 4, 5)])  # two holes
    assert O.num_holes(ring) == 1
    assert O.num_holes(solid) == 0
    assert O.num_holes(two) == 2


def test_geo_object_pixels_flips_within_bbox():
    o = O.Obj.from_pixels([(1, 1, 7), (2, 1, 7), (2, 2, 7)])            # L, bbox top-left (1,1)
    flipped = set(O.geo_object_pixels(o, "flip_h"))
    # bbox is 2x2 at (1,1): flip_h maps col-offset 0<->1; anchored at same top-left
    assert flipped == {(1, 2, 7), (2, 2, 7), (2, 1, 7)}


def test_map_objects_assembles_same_dims():
    g = [[2, 0, 0], [0, 0, 3], [0, 0, 0]]
    out = O.map_objects(g, SEG0, lambda o, objs, grid, bg: [(r, c, 9) for r, c, _ in o.pixels])
    assert out == [[9, 0, 0], [0, 0, 9], [0, 0, 0]]                     # every object recoloured to 9, in place


# ================================================================ per-object geometry (biggest lever, param-free)
def test_per_object_geometry_reachable_under_oe():
    # Output = each object flipped HORIZONTALLY within its own bbox. Objects sit at different places, so a
    # WHOLE-GRID flip cannot reproduce it (that would also move the objects) -> genuinely per-object.
    def build(g):
        return O.map_objects(g, SEG0, lambda o, objs, grid, bg: O.geo_object_pixels(o, "flip_h"))
    t1 = [[2, 0, 0, 0, 3, 0],
          [2, 2, 0, 0, 3, 3],
          [0, 0, 0, 0, 0, 0]]
    t2 = [[0, 4, 4, 0],
          [0, 0, 4, 0],
          [5, 5, 0, 0]]
    train = [(t1, build(t1)), (t2, build(t2))]
    prog, st = oe_object_search(train, return_stats=True)
    assert prog is not None
    assert st["solver_tree"][0] == "mapgeo" and st["solver_tree"][1] == "flip_h"
    # a plain whole-grid flip does NOT reproduce train (proves the per-object map is required)
    assert [list(reversed(r)) for r in t1] != build(t1)
    # generalises to a fresh grid
    t3 = [[6, 0, 0], [6, 6, 0], [0, 0, 0]]
    assert prog(t3) == build(t3)


# ================================================================ function-not-table recolor (the L3 lever)
def test_function_recolor_generalises_where_a_table_must_abstain():
    # colour = (2*size + 1) mod 10, a GENUINE function of size. Train shows sizes {3,1} and {4,2}.
    def build(g):
        return O.map_objects(g, SEG0, lambda o, objs, grid, bg: [(r, c, (2 * o.size + 1) % 10) for r, c, _ in o.pixels])
    r1 = [[1, 0, 0], [1, 1, 0], [0, 0, 3]]           # sizes 3, 1
    r2 = [[2, 2, 2, 2], [0, 0, 0, 0], [7, 7, 0, 0]]  # sizes 4, 2
    train = [(r1, build(r1)), (r2, build(r2))]
    prog = O.strat_map_recolor_fn(train)
    assert prog is not None
    # a NOVEL size (5) the train never showed: the derived function extrapolates 2*5+1=11%10=1 ...
    test = [[8, 8, 8, 8, 8], [0, 0, 0, 0, 0]]
    assert prog(test) == build(test)
    # ... whereas the TABLE recolour (strat_recolor) has no entry for size 5 -> abstains ([[ ]]), by design
    table = O.strat_recolor(train)
    assert table is not None                                   # the table fits the TRAIN sizes
    assert table(test) == [[]]                                 # but is undefined on the unseen size -> abstain


def test_function_recolor_abstains_when_no_consistent_function():
    # same attribute value maps to two different colours -> not a function -> abstain (no fabrication)
    bad = [([[1, 0], [0, 3]], [[5, 0], [0, 9]]),
           ([[2, 0], [0, 4]], [[6, 0], [0, 2]])]
    assert O.strat_map_recolor_fn(bad) is None


# ================================================================ atomic per-object slide
def test_atomic_slide_moves_each_object_as_a_rigid_body():
    def build(g):
        R, C = O.dims(g)
        return O.map_objects(g, SEG0, lambda o, objs, grid, bg: [(r + (R - 1 - o.bottom), c, col) for r, c, col in o.pixels])
    s1 = [[1, 1, 0], [0, 0, 0], [0, 0, 2]]
    s2 = [[3, 0, 0], [0, 4, 0], [0, 0, 0]]
    train = [(s1, build(s1)), (s2, build(s2))]
    prog = O.strat_map_slide(train)
    assert prog is not None
    t3 = [[5, 5, 5], [0, 0, 0], [0, 0, 0]]
    assert prog(t3) == build(t3)


# ================================================================ relational / reference-relative selection
def test_selector_has_holes_picks_the_ring():
    # a solid square (largest), an L-tromino (sparse but NO hole), and a ring (the target) -> ONLY has_holes
    # isolates the ring; largest/smallest/sparsest/densest each pick a different object.
    ring = O.Obj.from_pixels([(0, 0, 3), (0, 1, 3), (0, 2, 3), (1, 0, 3), (1, 2, 3), (2, 0, 3), (2, 1, 3), (2, 2, 3)])
    square = O.Obj.from_pixels([(r, c, 2) for r in range(4) for c in range(10, 14)])   # 16 cells, largest
    ell = O.Obj.from_pixels([(6, 6, 4), (7, 6, 4), (7, 7, 4)])                          # sparse, no hole
    objs = [ring, square, ell]
    assert _sel_has_holes(objs) is ring


def test_selector_color_matches_marker_is_reference_relative():
    # a size-1 marker cell of colour 4 and two objects; select the object whose colour == the marker's
    marker = O.Obj.from_pixels([(0, 5, 4)])
    target = O.Obj.from_pixels([(2, 0, 4), (2, 1, 4), (3, 0, 4), (3, 1, 4)])
    other = O.Obj.from_pixels([(0, 0, 7), (0, 1, 7)])
    assert _sel_color_matches_marker([marker, target, other]) is target
    # no marker (no unique singleton) -> None (never guesses)
    assert _sel_color_matches_marker([target, other]) is None


def test_selector_touches_border_needs_the_grid():
    g = [[0, 0, 0, 0, 0],
         [0, 8, 8, 0, 0],       # interior object
         [0, 8, 8, 0, 0],
         [0, 0, 0, 0, 6],       # object on the right border
         [0, 0, 0, 0, 6]]
    objs = _seg0(g)
    picked = _sel_touches_border(objs, g)
    assert picked is not None and picked.primary_color == 6
    inside = _sel_interior(objs, g)
    assert inside is not None and inside.primary_color == 8


def test_relational_selection_solves_a_task_only_holes_discriminates():
    # Across BOTH pairs the target is the ONLY holed object; every intrinsic selector is INCONSISTENT: the
    # ring is the 2ND-largest in pair 1 but the LARGEST in pair 2 (so no size/rank selector is stable), and
    # an L-tromino decoy (fill 0.75 < the ring's 0.89) denies 'sparsest' in both. Only has_holes reproduces
    # train -> the OE search must reach the relational selector.
    #   pair 1: ring(8, holed) + solid(12, largest) + L(3, sparsest)
    g1 = [[3, 3, 3, 0, 2, 2, 2, 2],
          [3, 0, 3, 0, 2, 2, 2, 2],
          [3, 3, 3, 0, 2, 2, 2, 2],
          [0, 0, 0, 0, 0, 0, 0, 0],
          [4, 0, 0, 0, 0, 0, 0, 0],
          [4, 4, 0, 0, 0, 0, 0, 0]]
    #   pair 2: ring(8, LARGEST) + solid row(5) + L(3, sparsest)
    g2 = [[3, 3, 3, 0, 0, 4, 0],
          [3, 0, 3, 0, 0, 4, 4],
          [3, 3, 3, 0, 0, 0, 0],
          [0, 0, 0, 0, 0, 0, 0],
          [0, 0, 0, 0, 0, 0, 0],
          [2, 2, 2, 2, 2, 0, 0]]
    o1 = O.crop_bbox(g1, [o for o in _seg0(g1) if O.num_holes(o) > 0][0])
    o2 = O.crop_bbox(g2, [o for o in _seg0(g2) if O.num_holes(o) > 0][0])
    train = [(g1, o1), (g2, o2)]
    prog, st = oe_object_search(train, return_stats=True)
    assert prog is not None
    assert st["solver_tree"][0] == "crop"                 # output = crop of the selected object
    assert st["solver_tree"][1][:2] == ("sel", "has_holes")   # the relational selector is what cracked it


# ================================================================ honesty gate (unchanged, EXACT)
def test_contradictory_train_abstains_through_map_path():
    assert oe_object_search([([[1, 1]], [[2, 2]]), ([[1, 1]], [[3, 3]])]) is None
    assert O.strat_map_recolor_fn([([[1, 1]], [[2, 2]]), ([[1, 1]], [[3, 3]])]) is None
    assert O.strat_map_slide([([[1, 1]], [[2, 2]]), ([[1, 1]], [[3, 3]])]) is None
