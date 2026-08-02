# -*- coding: utf-8 -*-
"""A2 — the INVENTION ENGINE'S SEARCH, ported to the ARC object DSL (heart -> ARC).

WHY THIS FILE EXISTS (the B0.1 measured gap)
--------------------------------------------
B0.1 wired PERCEPTION into the ARC solver (objects.py: segmentation + attributes + selectors + a set of
DEPTH-1 object strategies) and lifted the sealed ARC-1 eval 0.5% -> 1.75% (7/400, 0 fabricated). Its own
reachability probe then localised the NEXT cap precisely: it is SEARCH, not perception.
  * 6 tasks are crop-reachable but need RELATIONAL / MULTI-PROPERTY selection ("densest", "2nd-largest");
  * 23 recolor tasks need richer attribute rules;
  * the bulk need DEEPER, MULTI-STEP composition — the old object ops were depth-1 (one selector, one
    renderer, at most one trailing geometry), so a rule that is "select-by-relational-attribute THEN crop
    THEN rotate" or "erase-noise THEN gravity" was simply unreachable.

That "enumerate deeper programs, prune the explosion, prefer the simplest" IS the invention engine's search
(packages/evolution/scheme_synthesis.oe_enumerate): BOTTOM-UP, SIZE-LAYERED enumeration with
OBSERVATIONAL-EQUIVALENCE dedup and MDL/size priority. oe_enumerate itself is typed to open_domain's
int|str|tuple value space (the sequence grammar) and cannot express grids/objects, so — exactly as the A2
brief anticipates — we implement a MINIMAL OE LOOP OVER THE OBJECT DSL here, citing and reusing the same
principle and the SAME MDL codelength machinery (packages.evolution.compression_progress.raw_len ==
abstraction.size). This is the heart's search wired into ARC, not a re-derivation.

THE SEARCH (same three ideas as oe_enumerate, on the object-op value space {GRID, OBJ, OBJLIST})
-----------------------------------------------------------------------------------------------
  * BOTTOM-UP, SIZE-LAYERED. Leaves (size 1) = the input grid + each segmentation configuration. Layer s is
    built from layer s-1 by every type-applicable UNARY object op (every op in this DSL is unary), so
    construction size == raw_len(tree) == number of op-nodes exactly (all ops add 1). The FIRST grid-typed
    program whose outputs equal every train output is returned — the smallest, i.e. the MDL/Occam choice.
  * OBSERVATIONAL-EQUIVALENCE dedup. A node's behaviour SIGNATURE = its value on every train INPUT grid.
    Two sub-programs with the same signature are interchangeable for anything built on them, so only the
    first (== smallest, since we go size-ascending) is kept. branching^depth collapses to "number of
    distinct behaviours on the train inputs" — the same pruning that lets oe_enumerate reach depth.
  * MDL / SIZE PRIORITY == the propose-verify generaliser. Among all train-exact programs the smallest is
    returned; small train-consistent programs are the ones that generalise (Occam), which is also the
    honesty margin — see the propose-verify note below.

PROPOSE-VERIFY / HONESTY (unchanged, EXACT). A program is returned ONLY if it reproduces ALL train pairs of
the task EXACTLY; otherwise the search abstains (None) and the task is a miss, never a guess. The signature
IS the train-output check for grid nodes, so "verify" and "search" are the same pass. Everything is
synthesised from the task's OWN train pairs; the eval test output is never read here. A node that is
UNDEFINED on any train input (an ambiguous selector -> None, an op that yields a non-rectangular grid) is
pruned, so it can never be part of a returned program. The final program is re-guarded at test time by
solver.solve_task (undefined-on-test -> abstain), keeping attempted-but-wrong at 0.

GENERALITY (owner's BINDING). Objectness + general relational selection are legitimate fluid-intelligence
priors (Chollet). Every op here is task-INDEPENDENT and parameter-free (or parameterised only by stats of
the CURRENT grid's own objects); there is no per-task selector, no eval-split fitting, no hardcoded answer.
The search is bounded (max size, node budget, wall-clock deadline) so the deeper DSL cannot blow up cost.
"""
from __future__ import annotations

import time
from fractions import Fraction
from typing import Any, Callable

from packages.arc_agi import objects as O
# REUSE (read-only) the invention engine's MDL codelength — the same size function scheme_synthesis /
# compression_progress rank by. raw_len(t) == abstraction.size(t): +1 per structural op-node.
from packages.evolution.compression_progress import raw_len as mdl_size

Grid = list[list[int]]
_FAIL = object()                     # undefined value (ambiguous selector / invalid grid / raised op)

# value-type tags for type-directed production gating
GRID, OBJ, OBJLIST = "GRID", "OBJ", "OBJLIST"


# ---------------------------------------------------------------- grid validity + local geometry
def _valid_grid(g: Any) -> bool:
    if not g or not isinstance(g, list):
        return False
    if not isinstance(g[0], list):
        return False
    w = len(g[0])
    if w <= 0:
        return False
    return all(isinstance(r, list) and len(r) == w for r in g)


def _crop_content(g: Grid) -> Grid:
    """Bounding box of non-background (mode) cells — the whole-grid content crop, as a GENERAL op."""
    bg = O.mode_color(g)
    R, C = O.dims(g)
    rows = [i for i in range(R) if any(g[i][j] != bg for j in range(C))]
    cols = [j for j in range(C) if any(g[i][j] != bg for i in range(R))]
    if not rows or not cols:
        return [[]]
    return [[g[i][j] for j in range(cols[0], cols[-1] + 1)] for i in range(rows[0], rows[-1] + 1)]


# ---------------------------------------------------------------- extended relational selectors
# The B0.1 crop-reachable-6 lever: general relational / rank / density selectors, each returning EXACTLY
# one object or None (a tie -> None -> abstain, never a guess). All are pure functions of the object list.
def _unique_extreme(objs, key, want_max):
    if not objs:
        return None
    vals = [key(o) for o in objs]
    target = max(vals) if want_max else min(vals)
    winners = [o for o, v in zip(objs, vals) if v == target]
    return winners[0] if len(winners) == 1 else None


def _unique_rank(objs, key, k, want_max):
    """The object at the k-th (0-based) DISTINCT value of `key` — 'the 2nd largest' etc. Unique or None."""
    if len(objs) <= k:
        return None
    vals = sorted({key(o) for o in objs}, reverse=want_max)
    if len(vals) <= k:
        return None
    target = vals[k]
    winners = [o for o in objs if key(o) == target]
    return winners[0] if len(winners) == 1 else None


def _fill_ratio(o) -> Fraction:
    return Fraction(o.size, o.bbox_area)                 # exact density (no float equality hazard)


# ---------------------------------------------------------------- A3 relational / reference-relative selectors
# The A2 probe's 2nd lever: the discriminator is OBJECT-TO-OBJECT ("the one WITH a hole", "the one touching
# the border") or REFERENCE-RELATIVE ("the object whose colour matches a marker cell"), not any single
# intrinsic attribute. Each returns EXACTLY one object or None (a tie/ambiguity -> None -> abstain).
def _sel_has_holes(objs, grid=None):
    hs = [o for o in objs if O.num_holes(o) > 0]
    return hs[0] if len(hs) == 1 else None


def _sel_color_matches_marker(objs, grid=None):
    """Reference-relative: a unique size-1 'marker' cell names a colour; select the unique OTHER object of
    that colour (the classic 'the marker points at which object to keep')."""
    singles = [o for o in objs if o.size == 1]
    if len(singles) != 1:
        return None
    m = singles[0]
    cands = [o for o in objs if o is not m and o.primary_color == m.primary_color]
    return cands[0] if len(cands) == 1 else None


def _sel_touches_border(objs, grid=None):
    if grid is None or not objs:
        return None
    R, C = O.dims(grid)
    ts = [o for o in objs if O.touches_border(o, R, C)]
    return ts[0] if len(ts) == 1 else None


def _sel_interior(objs, grid=None):
    if grid is None or not objs:
        return None
    R, C = O.dims(grid)
    its = [o for o in objs if not O.touches_border(o, R, C)]
    return its[0] if len(its) == 1 else None


def _wrap1(f: Callable[[list], Any]) -> Callable[[list, Any], Any]:
    """Adapt an intrinsic (objs-only) selector to the grid-aware (objs, grid) calling convention."""
    return lambda objs, grid=None, _f=f: _f(objs)


# All selectors now share the (objs, grid) signature so the reference/border-relative ones can see the grid.
_SEL_EXT: dict[str, Callable[[list, Any], Any]] = {n: _wrap1(f) for n, f in O.SELECTORS.items()}
_SEL_EXT.update({
    "2nd_largest":  _wrap1(lambda objs: _unique_rank(objs, lambda o: o.size, 1, True)),
    "3rd_largest":  _wrap1(lambda objs: _unique_rank(objs, lambda o: o.size, 2, True)),
    "2nd_smallest": _wrap1(lambda objs: _unique_rank(objs, lambda o: o.size, 1, False)),
    "densest":      _wrap1(lambda objs: _unique_extreme(objs, _fill_ratio, True)),
    "sparsest":     _wrap1(lambda objs: _unique_extreme(objs, _fill_ratio, False)),
    "widest":       _wrap1(lambda objs: _unique_extreme(objs, lambda o: o.width, True)),
    "tallest":      _wrap1(lambda objs: _unique_extreme(objs, lambda o: o.height, True)),
    "most_pixels":  _wrap1(lambda objs: _unique_extreme(objs, lambda o: o.size, True)),   # alias of largest (dedup folds)
    # A3 relational / reference-relative
    "has_holes":    _wrap1(_sel_has_holes),
    "most_holes":   _wrap1(lambda objs: _unique_extreme(objs, lambda o: O.num_holes(o), True)),
    "color_matches_marker": _wrap1(_sel_color_matches_marker),
    "touches_border": _sel_touches_border,      # needs the grid (bbox vs grid edge)
    "interior":       _sel_interior,            # needs the grid
})
_SEL_NAMES: tuple[str, ...] = tuple(_SEL_EXT)

_GEO_NAMES: tuple[str, ...] = tuple(k for k in O._GEO_LOCAL if k != "identity")    # 6 non-identity geometries
_GRAV_DIRS: tuple[str, ...] = ("down", "up", "left", "right")
_FILT_PREDS: tuple[str, ...] = ("singleton", "largest", "smallest", "common_color", "rare_color",
                                "common_shape", "rare_shape", "symmetric", "multicolor")


# ---------------------------------------------------------------- op semantics (single value + ambient grid)
def _seg(cfg_i: int, grid: Grid):
    return tuple(O.segment(grid, **O.SEG_CONFIGS[cfg_i]))


def _sel(name: str, objs, grid: Grid) -> Any:
    o = _SEL_EXT[name](list(objs), grid)
    return o if o is not None else _FAIL


def _mapgeo(name: str, seg_child, objs, grid: Grid) -> Any:
    """Per-object geometry in place: flip/rotate EACH object within its own bbox and re-assemble (A2's
    biggest lever, the parameter-free member). `seg_child` == ("seg", cfg_i) supplies the bg/segmentation."""
    cfg = O.SEG_CONFIGS[seg_child[1]]
    g = O.map_objects(grid, cfg, lambda o, objs_, grid_, bg: O.geo_object_pixels(o, name))
    return g if _valid_grid(g) else _FAIL


def _crop(obj, grid: Grid) -> Any:
    g = O.crop_bbox(grid, obj)
    return g if _valid_grid(g) else _FAIL


def _mask(bg_choice: str, obj, grid: Grid) -> Any:
    bg = 0 if bg_choice == "0" else O.mode_color(grid)
    g = O.render_mask(obj, bg)
    return g if _valid_grid(g) else _FAIL


def _geo(name: str, grid: Grid) -> Any:
    g = O._GEO_LOCAL[name](grid)
    return g if _valid_grid(g) else _FAIL


def _grav(direction: str, bg_choice: str, grid: Grid) -> Any:
    bg = 0 if bg_choice == "0" else O.mode_color(grid)
    g = O.gravity(grid, bg, direction)
    return g if _valid_grid(g) else _FAIL


def _cropc(grid: Grid) -> Any:
    g = _crop_content(grid)
    return g if _valid_grid(g) else _FAIL


def _filt(pred_name: str, keep: bool, cfg_i: int, objs, grid: Grid) -> Any:
    cfg = O.SEG_CONFIGS[cfg_i]
    bg = O.mode_color(grid) if cfg["background"] is None else cfg["background"]
    preds = O._predicates(list(objs))
    if pred_name not in preds:
        return _FAIL
    p = preds[pred_name]
    victims = [o for o in objs if (p(o) if not keep else not p(o))]
    g = O.erase_objects(grid, victims, bg)
    return g if _valid_grid(g) else _FAIL


# ---------------------------------------------------------------- the recursive tree evaluator
# Node layout: leaves ("in",) / ("seg", cfg_i); unary ops carry params first and the child subtree LAST.
def evaluate_tree(tree: Any, grid: Grid, memo: dict | None = None, gi: int = 0) -> Any:
    """Evaluate an object-DSL program on `grid`, returning a typed value or _FAIL. `memo` (keyed by
    (tree, grid-index)) makes the bottom-up enumeration reuse child values in O(1); the compiled program
    calls it fresh on the test grid."""
    if memo is not None:
        k = (tree, gi)
        if k in memo:
            return memo[k]
    v = _eval_node(tree, grid, memo, gi)
    if memo is not None:
        memo[(tree, gi)] = v
    return v


def _eval_node(tree: Any, grid: Grid, memo, gi) -> Any:
    tag = tree[0]
    if tag == "in":
        return grid
    if tag == "seg":
        return _seg(tree[1], grid)
    child = tree[-1]
    cv = evaluate_tree(child, grid, memo, gi)
    if cv is _FAIL:
        return _FAIL
    if tag == "sel":
        return _sel(tree[1], cv, grid)
    if tag == "mapgeo":
        return _mapgeo(tree[1], child, cv, grid)          # child == ("seg", cfg_i)
    if tag == "crop":
        return _crop(cv, grid)
    if tag == "mask":
        return _mask(tree[1], cv, grid)
    if tag == "geo":
        return _geo(tree[1], cv)
    if tag == "grav":
        return _grav(tree[1], tree[2], cv)
    if tag == "cropc":
        return _cropc(cv)
    if tag == "filt":
        return _filt(tree[1], tree[2], child[1], cv, grid)   # child == ("seg", cfg_i)
    return _FAIL


# ---------------------------------------------------------------- OE signature canonicalisation
def _canon(v: Any) -> Any:
    if v is _FAIL:
        return _FAIL
    if isinstance(v, list):                              # a grid
        return tuple(tuple(r) for r in v)
    if isinstance(v, tuple) and v and isinstance(v[0], O.Obj):   # an object list
        return tuple(o.pixels for o in v)
    if isinstance(v, O.Obj):
        return v.pixels
    return v


def compile_program(tree: Any) -> Callable[[Grid], Grid]:
    """Turn a discovered tree into the Program callable solver.solve_task applies to the test input.
    Undefined (_FAIL) -> the [[ ]] sentinel, which solve_task's validity guard turns into an abstention."""
    def prog(g: Grid, _t=tree) -> Grid:
        v = evaluate_tree(_t, g, None, 0)
        return v if (v is not _FAIL and _valid_grid(v)) else [[]]
    return prog


# ---------------------------------------------------------------- the bottom-up OE + MDL enumerator
def oe_object_search(train: list[tuple[Grid, Grid]], *, deadline: float | None = None,
                     max_size: int = 4, max_bank: int = 6000, node_budget: int = 120000,
                     return_stats: bool = False):
    """Bottom-up, size-layered synthesis over the object DSL with observational-equivalence dedup and MDL
    (smallest-first) priority — the invention engine's search on the grid/object value space.

    Returns the smallest verified Program (reproduces EVERY train output exactly) or None. With
    return_stats=True returns (program, stats) where stats exposes the OE metrics the sealed gate asserts:
    nodes considered, OE-pruned (dedup), bank size, solver tree + its MDL size.
    """
    grids = [gi for gi, _ in train]
    wants = [tuple(tuple(r) for r in go) for _, go in train]      # canonical train outputs (the solve target)
    memo: dict = {}
    seen: set = set()                                            # OE: behaviour signatures already represented
    bank: dict[int, list] = {}                                  # size -> [(tree, type)]
    stats = {"considered": 0, "oe_pruned": 0, "failed": 0, "bank": 0,
             "max_size": 0, "solver_tree": None, "solver_size": None, "evals": 0}

    def finish(win):
        stats["bank"] = len(seen)
        return (win, stats) if return_stats else win

    def vals_of(tree: Any) -> list:
        stats["evals"] += 1
        return [evaluate_tree(tree, grids[j], memo, j) for j in range(len(grids))]

    def consider(tree: Any, typ: str):
        """Evaluate on train inputs; prune undefined; OE-dedup; solve-check grid nodes. Returns a compiled
        solver Program if this node reproduces every train output, else None."""
        stats["considered"] += 1
        vl = vals_of(tree)
        if any(v is _FAIL for v in vl):
            stats["failed"] += 1
            return None
        if typ == GRID and [tuple(tuple(r) for r in v) for v in vl] == wants:
            stats["solver_tree"] = tree
            stats["solver_size"] = mdl_size(tree)
            return compile_program(tree)                        # smallest verified program (MDL/Occam)
        sig = (typ, tuple(_canon(v) for v in vl))
        if sig in seen or len(seen) >= max_bank:
            stats["oe_pruned"] += 1                             # observationally equivalent -> keep the smaller
            return None
        seen.add(sig)
        bank.setdefault(mdl_size(tree), []).append((tree, typ))
        return None

    # ---- size-1 leaves: the input grid + each segmentation configuration ----
    win = consider(("in",), GRID)
    if win is not None:
        return finish(win)
    for cfg_i in range(len(O.SEG_CONFIGS)):
        consider(("seg", cfg_i), OBJLIST)

    # ---- grow layer by layer; layer s built from layer s-1 by every type-applicable unary op ----
    for size in range(2, max_size + 1):
        stats["max_size"] = size
        prev = list(bank.get(size - 1, []))
        for tree, typ in prev:
            if deadline is not None and time.monotonic() > deadline:
                return finish(None)
            if stats["evals"] > node_budget:
                return finish(None)
            if typ == OBJLIST:
                for name in _SEL_NAMES:                          # OBJLIST -> OBJ (relational selection)
                    w = consider(("sel", name, tree), OBJ)
                    if w is not None:
                        return finish(w)
                if tree[0] == "seg":                             # OBJLIST -> GRID (filter/erase by attribute)
                    for pred in _FILT_PREDS:
                        for keep in (True, False):
                            w = consider(("filt", pred, keep, tree), GRID)
                            if w is not None:
                                return finish(w)
                    for gname in _GEO_NAMES:                      # OBJLIST -> GRID (per-object geometry + reassemble)
                        w = consider(("mapgeo", gname, tree), GRID)
                        if w is not None:
                            return finish(w)
            elif typ == OBJ:                                     # OBJ -> GRID (render)
                for r in (("crop", tree), ("mask", "0", tree), ("mask", "bg", tree)):
                    w = consider(r, GRID)
                    if w is not None:
                        return finish(w)
            elif typ == GRID:                                    # GRID -> GRID (geometry / gravity / content crop)
                for name in _GEO_NAMES:
                    w = consider(("geo", name, tree), GRID)
                    if w is not None:
                        return finish(w)
                w = consider(("cropc", tree), GRID)
                if w is not None:
                    return finish(w)
                for d in _GRAV_DIRS:                          # bg=0 only in composition (the mode-bg fall is
                    w = consider(("grav", d, "0", tree), GRID)  # covered depth-1 by strat_gravity)
                    if w is not None:
                        return finish(w)
    return finish(None)


def finish(win):
    stats["bank"] = sum(len(v) for v in ()) if False else len(_flatten_seen(stats))
    stats["bank"] = None  # (bank size is tracked via seen; recomputed in caller tests if needed)
    return (win, stats) if return_stats else win


def _flatten_seen(_stats):
    return ()

