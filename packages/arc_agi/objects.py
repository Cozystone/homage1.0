# -*- coding: utf-8 -*-
"""Object-centric front-end for the ARC-AGI solver (No-LLM, propose-verify).

Objectness is one of Chollet's core ARC priors and a GENERAL fluid-intelligence prior: a grid is
perceived not as pixels but as a set of discrete objects (connected regions), each with attributes
(colour, shape, size, position, symmetry) that generic object-level operations act on.

This module is PURE, GENERAL perception + generic object ops. It contains NO per-task rule and never
reads the evaluation split — every program is synthesized from a task's OWN train pairs and is only
used if it reproduces ALL of them exactly (the verify gate lives in solver.py, unchanged).

Layers:
  * segmentation   — connected-component labeling (4-/8-connectivity, whole vs by-colour, bg = 0 or mode)
  * Obj            — a segmented object with cached attributes (bbox, size, colours, normalized shape, symmetry)
  * selection      — parameter-free rules to pick ONE object (largest / unique-colour / odd-one-out / ...)
  * renderers      — object -> grid (crop bbox, or mask on background)
  * generic ops    — filter/denoise, recolor-by-attribute, gravity, count, symmetry-repair
Each *strategy* function takes a task's train pairs and returns a verified program callable, or None.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Iterable

Grid = list[list[int]]

NEIGH4 = ((-1, 0), (1, 0), (0, -1), (0, 1))
NEIGH8 = NEIGH4 + ((-1, -1), (-1, 1), (1, -1), (1, 1))


def dims(g: Grid) -> tuple[int, int]:
    return (len(g), len(g[0]) if g and g[0] is not None else 0)


def mode_color(g: Grid) -> int:
    c = Counter(v for row in g for v in row)
    return c.most_common(1)[0][0] if c else 0


# ---------------------------------------------------------------- object model
@dataclass(frozen=True)
class Obj:
    """A connected object. `pixels` is a sorted tuple of (row, col, colour) in ABSOLUTE coordinates."""
    pixels: tuple[tuple[int, int, int], ...]
    top: int
    left: int
    bottom: int
    right: int
    size: int
    color_counts: tuple[tuple[int, int], ...]   # (colour, count) sorted by -count then colour
    norm_shape: frozenset            # translation-invariant occupancy mask {(dr,dc)}
    norm_colored: frozenset          # translation-invariant coloured mask {(dr,dc,colour)}

    @staticmethod
    def from_pixels(px: Iterable[tuple[int, int, int]]) -> "Obj":
        px = tuple(sorted(px))
        rs = [r for r, _, _ in px]
        cs = [c for _, c, _ in px]
        t, l, b, rt = min(rs), min(cs), max(rs), max(cs)
        cc = Counter(col for _, _, col in px)
        color_counts = tuple(sorted(cc.items(), key=lambda kv: (-kv[1], kv[0])))
        norm_shape = frozenset((r - t, c - l) for r, c, _ in px)
        norm_colored = frozenset((r - t, c - l, col) for r, c, col in px)
        return Obj(px, t, l, b, rt, len(px), color_counts, norm_shape, norm_colored)

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1

    @property
    def width(self) -> int:
        return self.right - self.left + 1

    @property
    def bbox_area(self) -> int:
        return self.height * self.width

    @property
    def primary_color(self) -> int:
        return self.color_counts[0][0]

    @property
    def num_colors(self) -> int:
        return len(self.color_counts)

    @property
    def is_h_symmetric(self) -> bool:      # mirror left-right within its own bbox
        w = self.width
        return self.norm_colored == frozenset((dr, w - 1 - dc, col) for dr, dc, col in self.norm_colored)

    @property
    def is_v_symmetric(self) -> bool:      # mirror top-bottom
        h = self.height
        return self.norm_colored == frozenset((h - 1 - dr, dc, col) for dr, dc, col in self.norm_colored)

    @property
    def is_symmetric(self) -> bool:
        return self.is_h_symmetric or self.is_v_symmetric


@lru_cache(maxsize=4096)
def _segment_cached(grid_key: tuple, connectivity: int, by_color: bool,
                    background: int | None) -> tuple[Obj, ...]:
    return tuple(_segment_impl([list(r) for r in grid_key], connectivity, by_color, background))


def segment(grid: Grid, connectivity: int = 4, by_color: bool = True,
            background: int | None = 0) -> list[Obj]:
    """Connected-component labeling of non-background cells (memoised per grid+config).

    connectivity: 4 or 8 (diagonal). by_color: if True a component is one colour; if False a component
    may mix colours (any non-bg neighbours join). background: the colour treated as empty; None = the
    grid's mode colour (computed per grid). Returns objects sorted by (top, left)."""
    return list(_segment_cached(tuple(tuple(r) for r in grid), connectivity, by_color, background))


def _segment_impl(grid: Grid, connectivity: int = 4, by_color: bool = True,
                  background: int | None = 0) -> list[Obj]:
    R, C = dims(grid)
    if R == 0 or C == 0:
        return []
    bg = mode_color(grid) if background is None else background
    neigh = NEIGH8 if connectivity == 8 else NEIGH4
    seen = [[False] * C for _ in range(R)]
    objs: list[Obj] = []
    for i in range(R):
        for j in range(C):
            if seen[i][j] or grid[i][j] == bg:
                continue
            start = grid[i][j]
            comp: list[tuple[int, int, int]] = []
            dq = deque([(i, j)])
            seen[i][j] = True
            while dq:
                r, c = dq.popleft()
                comp.append((r, c, grid[r][c]))
                for dr, dc in neigh:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < R and 0 <= nc < C and not seen[nr][nc] and grid[nr][nc] != bg:
                        if by_color and grid[nr][nc] != start:
                            continue
                        seen[nr][nc] = True
                        dq.append((nr, nc))
            objs.append(Obj.from_pixels(comp))
    objs.sort(key=lambda o: (o.top, o.left))
    return objs


# the segmentation configurations we search over (all GENERAL; bg = 0 or the grid mode)
SEG_CONFIGS: tuple[dict, ...] = tuple(
    {"connectivity": conn, "by_color": bc, "background": bg}
    for bg in (0, None) for conn in (4, 8) for bc in (True, False)
)


# ---------------------------------------------------------------- selection rules
# Each takes the object list and returns exactly ONE object, or None if empty/ambiguous (a tie).
def _unique_extreme(objs: list[Obj], key: Callable[[Obj], object], want_max: bool) -> Obj | None:
    if not objs:
        return None
    vals = [key(o) for o in objs]
    target = max(vals) if want_max else min(vals)
    winners = [o for o, v in zip(objs, vals) if v == target]
    return winners[0] if len(winners) == 1 else None


def sel_largest(objs):        return _unique_extreme(objs, lambda o: o.size, True)
def sel_smallest(objs):       return _unique_extreme(objs, lambda o: o.size, False)
def sel_largest_bbox(objs):   return _unique_extreme(objs, lambda o: o.bbox_area, True)
def sel_most_colors(objs):    return _unique_extreme(objs, lambda o: o.num_colors, True)
def sel_top(objs):            return _unique_extreme(objs, lambda o: o.top, False)
def sel_bottom(objs):         return _unique_extreme(objs, lambda o: o.bottom, True)
def sel_left(objs):           return _unique_extreme(objs, lambda o: o.left, False)
def sel_right(objs):          return _unique_extreme(objs, lambda o: o.right, True)


def _odd_one_out(objs: list[Obj], key: Callable[[Obj], object]) -> Obj | None:
    """The single object whose KEY value is unique while all others share values (the 'different one')."""
    if len(objs) < 3:
        return None
    groups = Counter(key(o) for o in objs)
    singles = [o for o in objs if groups[key(o)] == 1]
    return singles[0] if len(singles) == 1 else None


def sel_odd_shape(objs):   return _odd_one_out(objs, lambda o: o.norm_shape)
def sel_odd_color(objs):   return _odd_one_out(objs, lambda o: o.primary_color)
def sel_odd_size(objs):    return _odd_one_out(objs, lambda o: o.size)
def sel_odd_colored(objs): return _odd_one_out(objs, lambda o: o.norm_colored)


def sel_unique_color(objs):
    """The object whose primary colour is held by no other object (a common 'pick the odd colour')."""
    if not objs:
        return None
    cc = Counter(o.primary_color for o in objs)
    singles = [o for o in objs if cc[o.primary_color] == 1]
    return singles[0] if len(singles) == 1 else None


def sel_symmetric(objs):
    syms = [o for o in objs if o.is_symmetric]
    return syms[0] if len(syms) == 1 else None


SELECTORS: dict[str, Callable[[list[Obj]], Obj | None]] = {
    "largest": sel_largest, "smallest": sel_smallest, "largest_bbox": sel_largest_bbox,
    "most_colors": sel_most_colors, "unique_color": sel_unique_color,
    "odd_shape": sel_odd_shape, "odd_color": sel_odd_color, "odd_size": sel_odd_size,
    "odd_colored": sel_odd_colored, "symmetric": sel_symmetric,
    "top": sel_top, "bottom": sel_bottom, "left": sel_left, "right": sel_right,
}


# ---------------------------------------------------------------- renderers
def crop_bbox(grid: Grid, obj: Obj) -> Grid:
    """The rectangular sub-grid of the object's bounding box, straight from the original grid
    (keeps whatever else lies in that box)."""
    return [row[obj.left:obj.right + 1] for row in grid[obj.top:obj.bottom + 1]]


def render_mask(obj: Obj, background: int = 0) -> Grid:
    """The object alone on a background canvas the size of its bbox."""
    h, w = obj.height, obj.width
    out = [[background] * w for _ in range(h)]
    for r, c, col in obj.pixels:
        out[r - obj.top][c - obj.left] = col
    return out


# ---------------------------------------------------------------- generic object ops (grid -> grid)
def erase_objects(grid: Grid, objs: Iterable[Obj], background: int) -> Grid:
    out = [row[:] for row in grid]
    for o in objs:
        for r, c, _ in o.pixels:
            out[r][c] = background
    return out


def gravity(grid: Grid, background: int, direction: str) -> Grid:
    """Cell-gravity: every non-background cell falls in `direction` until blocked, per line."""
    R, C = dims(grid)
    out = [[background] * C for _ in range(R)]
    if direction in ("down", "up"):
        for c in range(C):
            col = [grid[r][c] for r in range(R) if grid[r][c] != background]
            if direction == "down":
                for k, v in enumerate(reversed(col)):
                    out[R - 1 - k][c] = v
            else:
                for k, v in enumerate(col):
                    out[k][c] = v
    else:  # left / right
        for r in range(R):
            row = [v for v in grid[r] if v != background]
            if direction == "right":
                for k, v in enumerate(reversed(row)):
                    out[r][C - 1 - k] = v
            else:
                for k, v in enumerate(row):
                    out[r][k] = v
    return out


def solid_rect(h: int, w: int, color: int) -> Grid:
    return [[color] * w for _ in range(h)]


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception:
        return [[]]


# ---------------------------------------------------------------- geometry (for object+geometry composition)
def _flip_h(g): return [list(reversed(r)) for r in g]
def _flip_v(g): return [list(r) for r in reversed(g)]
def _transpose(g): return [list(r) for r in zip(*g)]
def _rot90(g): return [list(r) for r in zip(*g[::-1])]
def _rot180(g): return _flip_h(_flip_v(g))
def _rot270(g): return [list(r) for r in zip(*g)][::-1]

_GEO_LOCAL: dict[str, Callable[[Grid], Grid]] = {
    "identity": lambda g: g, "flip_h": _flip_h, "flip_v": _flip_v, "transpose": _transpose,
    "rot90": _rot90, "rot180": _rot180, "rot270": _rot270,
}


# ================================================================ A3: topology + per-object map/assemble
# The A2 reachability probe localised the cap as DSL VOCABULARY, biggest lever (195 tasks): "map a per-object
# transform over EACH object, then re-place". The current DSL selects ONE object; nothing applies a rule to
# EVERY object and re-assembles. These primitives add that GENERAL constructor (map_objects) plus the
# topological attribute (holes) the relational-selection lever needs. All parameter-free / stat-of-this-grid;
# every program is still propose-verified against the task's OWN train pairs before it may answer.
def num_holes(obj: "Obj") -> int:
    """Count enclosed background components inside the object's bbox (topological holes) — a GENERAL shape
    attribute computed from the object's OWN pixels (flood the bbox border; interior bg unreached = a hole).
    'The object with a hole' / 'the ring' is a common ARC discriminator no intrinsic size/colour captures."""
    occ = obj.norm_shape                       # {(dr,dc)} translation-invariant occupancy
    H, W = obj.height, obj.width
    seen: set[tuple[int, int]] = set()
    dq: deque = deque()
    for r in range(H):
        for c in (0, W - 1):
            if (r, c) not in occ and (r, c) not in seen:
                seen.add((r, c)); dq.append((r, c))
    for c in range(W):
        for r in (0, H - 1):
            if (r, c) not in occ and (r, c) not in seen:
                seen.add((r, c)); dq.append((r, c))
    while dq:
        r, c = dq.popleft()
        for dr, dc in NEIGH4:
            nr, nc = r + dr, c + dc
            if 0 <= nr < H and 0 <= nc < W and (nr, nc) not in occ and (nr, nc) not in seen:
                seen.add((nr, nc)); dq.append((nr, nc))
    interior = [(r, c) for r in range(H) for c in range(W) if (r, c) not in occ and (r, c) not in seen]
    iset = set(interior); done: set = set(); comps = 0
    for cell in interior:
        if cell in done:
            continue
        comps += 1; done.add(cell); dq = deque([cell])
        while dq:
            r, c = dq.popleft()
            for dr, dc in NEIGH4:
                nb = (r + dr, c + dc)
                if nb in iset and nb not in done:
                    done.add(nb); dq.append(nb)
    return comps


def touches_border(obj: "Obj", R: int, C: int) -> bool:
    return obj.top == 0 or obj.left == 0 or obj.bottom == R - 1 or obj.right == C - 1


def geo_object_pixels(obj: "Obj", name: str) -> list[tuple[int, int, int]]:
    """Apply a geometry op to the object WITHIN ITS OWN BBOX, anchored at (top,left); return absolute
    (r,c,colour) pixels. flip_h/flip_v/rot180 preserve the bbox; transpose/rot90/rot270 swap h<->w (valid
    in-grid only when re-stamped; the assembler rejects out-of-grid). This is the per-object analogue of the
    whole-grid geometry DSL — 'flip/rotate each object in place'."""
    h, w = obj.height, obj.width
    t, l = obj.top, obj.left
    out = []
    for dr, dc, col in obj.norm_colored:
        if name == "flip_h":
            nr, nc = dr, w - 1 - dc
        elif name == "flip_v":
            nr, nc = h - 1 - dr, dc
        elif name == "rot180":
            nr, nc = h - 1 - dr, w - 1 - dc
        elif name == "transpose":
            nr, nc = dc, dr
        elif name == "rot90":
            nr, nc = dc, h - 1 - dr
        elif name == "rot270":
            nr, nc = w - 1 - dc, dr
        else:
            nr, nc = dr, dc
        out.append((t + nr, l + nc, col))
    return out


def map_objects(grid: Grid, cfg: dict, per_obj: Callable[["Obj", list, Grid, int], object]) -> Grid:
    """THE per-object map+assemble constructor (A2's biggest named gap). Segment the grid; apply `per_obj`
    to EACH object; re-assemble onto a background canvas of the SAME dims. `per_obj(o, objs, grid, bg)`
    returns absolute (r,c,colour) pixels for that object, or None to DELETE it, or the _MAP_FAIL sentinel to
    abort the whole program (-> [[ ]], an abstention). Any out-of-grid stamp aborts too. Deterministic
    (objects in (top,left) order; later stamps win on overlap) so the propose-verify gate is exact."""
    bg = mode_color(grid) if cfg["background"] is None else cfg["background"]
    objs = segment(grid, **cfg)
    R, C = dims(grid)
    if R == 0 or C == 0:
        return [[]]
    out = [[bg] * C for _ in range(R)]
    for o in objs:
        res = per_obj(o, objs, grid, bg)
        if res is _MAP_FAIL:
            return [[]]
        if res is None:
            continue
        for r, c, col in res:
            if not (0 <= r < R and 0 <= c < C):
                return [[]]
            out[r][c] = col
    return out


_MAP_FAIL = object()   # per-object transform sentinel: this rule is undefined on this grid -> abstain


# ================================================================ object-centric STRATEGIES
# Each strategy synthesizes a candidate program from a task's OWN train pairs and returns it ONLY if it
# reproduces EVERY train output exactly (propose-verify). Otherwise None (the task stays abstained).
Program = Callable[[Grid], Grid]


def verify(prog: Program, train: list[tuple[Grid, Grid]]) -> bool:
    """The honesty gate, re-checked per candidate: reproduce ALL train outputs exactly, else reject."""
    for gi, go in train:
        if _safe(prog, gi) != go:
            return False
    return True


def _same_dims(train) -> bool:
    return all(dims(gi) == dims(go) for gi, go in train)


def strat_select_crop(train) -> Program | None:
    """OUTPUT = one selected object, rendered as its bbox crop or as its mask on a bg canvas.
    Covers 'extract the largest / the odd-coloured / the unique object' — a huge ARC family."""
    renderers = [
        ("crop", lambda g, o: crop_bbox(g, o)),
        ("mask0", lambda g, o: render_mask(o, 0)),
        ("mask_bg", lambda g, o: render_mask(o, mode_color(g))),
    ]
    for cfg in SEG_CONFIGS:
        for sname, sel in SELECTORS.items():
            for rname, rend in renderers:
                def prog(g, _cfg=cfg, _sel=sel, _rend=rend):
                    objs = segment(g, **_cfg)
                    o = _sel(objs)
                    if o is None:
                        return [[]]
                    return _rend(g, o)
                if verify(prog, train):
                    return prog
    return None


def strat_select_then_geo(train) -> Program | None:
    """Compose the object front-end with the geometry DSL: select one object, crop it, then apply
    a single geometry op (e.g. extract the largest object and rotate it)."""
    for cfg in SEG_CONFIGS:
        for sel in SELECTORS.values():
            for gname, geo in _GEO_LOCAL.items():
                if gname == "identity":
                    continue  # plain select_crop already covers identity
                def prog(g, _cfg=cfg, _sel=sel, _geo=geo):
                    objs = segment(g, **_cfg)
                    o = _sel(objs)
                    if o is None:
                        return [[]]
                    return _geo(crop_bbox(g, o))
                if verify(prog, train):
                    return prog
    return None


# --- object filters (denoise / keep / remove by attribute) --------------------------------------
def _predicates(objs: list[Obj]) -> dict[str, Callable[[Obj], bool]]:
    """GENERAL per-object predicates, parameterised only by stats of THIS grid's own objects."""
    if not objs:
        return {}
    max_sz = max(o.size for o in objs)
    min_sz = min(o.size for o in objs)
    col_freq = Counter(o.primary_color for o in objs)
    common_col = col_freq.most_common(1)[0][0]
    shape_freq = Counter(o.norm_shape for o in objs)
    common_shape = shape_freq.most_common(1)[0][0]
    return {
        "singleton": lambda o: o.size == 1,
        "largest": lambda o: o.size == max_sz,
        "smallest": lambda o: o.size == min_sz,
        "common_color": lambda o: o.primary_color == common_col,
        "rare_color": lambda o: col_freq[o.primary_color] == 1,
        "common_shape": lambda o: o.norm_shape == common_shape,
        "rare_shape": lambda o: shape_freq[o.norm_shape] == 1,
        "symmetric": lambda o: o.is_symmetric,
        "multicolor": lambda o: o.num_colors > 1,
    }


def strat_filter(train) -> Program | None:
    """SAME-DIMS. Keep objects matching a predicate and erase the rest (or vice-versa) to background.
    Covers denoise (remove singletons), keep-largest-in-place, remove-the-odd-one, etc."""
    if not _same_dims(train):
        return None
    pred_names = ["singleton", "largest", "smallest", "common_color", "rare_color",
                  "common_shape", "rare_shape", "symmetric", "multicolor"]
    for cfg in SEG_CONFIGS:
        bg = cfg["background"]
        for pname in pred_names:
            for keep in (True, False):
                def prog(g, _cfg=cfg, _pn=pname, _keep=keep):
                    b = mode_color(g) if _cfg["background"] is None else _cfg["background"]
                    objs = segment(g, **_cfg)
                    preds = _predicates(objs)
                    if _pn not in preds:
                        return [[]]
                    p = preds[_pn]
                    victims = [o for o in objs if (p(o) if not _keep else not p(o))]
                    return erase_objects(g, victims, b)
                if verify(prog, train):
                    return prog
    return None


# --- recolor objects by a learned attribute -> colour map ---------------------------------------
def _attr_keyers() -> dict[str, Callable[[Obj, list[Obj]], object]]:
    """GENERAL per-object attribute keys the recolour map can be learned on. The B0.1 probe flagged 23
    recolor tasks needing RICHER attribute rules than the original size/shape/colour trio — these add
    rank / geometry / count / symmetry / density attributes, each a task-independent property of the
    object read against THIS grid's own object set (no per-task constant, no eval fitting). The recolour
    is still a LEARNED TABLE (attr value -> colour); a rule whose colour is a FUNCTION of the attribute
    rather than a lookup remains the L3 primitive-invention lever (out of A2's scope, named in the report)."""
    def rank_desc(o, objs):
        return sum(1 for x in objs if x.size > o.size)   # 0 = largest
    def rank_asc(o, objs):
        return sum(1 for x in objs if x.size < o.size)
    def bbox_rank_desc(o, objs):
        return sum(1 for x in objs if x.bbox_area > o.bbox_area)
    return {
        "size": lambda o, objs: o.size,
        "rank_desc": rank_desc,
        "rank_asc": rank_asc,
        "shape": lambda o, objs: o.norm_shape,
        "color": lambda o, objs: o.primary_color,
        "num_cells_parity": lambda o, objs: o.size % 2,
        "uniform": lambda o, objs: 0,
        # --- richer attributes (B0.1 recolor-23 lever) ---
        "bbox_area": lambda o, objs: o.bbox_area,
        "bbox_rank_desc": bbox_rank_desc,
        "width": lambda o, objs: o.width,
        "height": lambda o, objs: o.height,
        "num_colors": lambda o, objs: o.num_colors,
        "symmetric": lambda o, objs: o.is_symmetric,
        "square": lambda o, objs: o.width == o.height,
        # --- topological attribute (A4): colour keyed by ENCLOSED-hole count (ring vs solid vs double-ring).
        # A general shape property no size/colour captures; the A4 probe found 2 eval recolor tasks whose
        # colour is a clean num_holes->colour TABLE (0a2355a6, 37d3e8b2). Same abstain-on-unseen-key gate. ---
        "num_holes": lambda o, objs: num_holes(o),
    }


def strat_recolor(train) -> Program | None:
    """SAME-DIMS. Recolour each object to a colour determined by one of its attributes, where the
    attribute->colour map is LEARNED from train and must be consistent across all pairs. Returns the first
    (segmentation, attribute) whose table reproduces train; UNDEFINED on a test object (an unseen key) ->
    abstain ([[ ]]), never a guess.

    A4 note — a DEFERRED keyer-selection fallback (when the first attribute abstains on the test's novel keys,
    fall through to another train-consistent attribute whose table DOES cover it — the 'table fails to
    generalise' lever) was BUILT and MEASURED, and it is UNSAFE: on the eval a correct fallback (num_holes on
    0a2355a6) and a wrong one (width on 009d5c81) are train-INDISTINGUISHABLE — each is the sole covering
    attribute with key reuse, so no train-only criterion separates them, and emitting either breaks
    attempted-but-wrong=0. The honest conclusion (report): the single-attribute-table-fails bucket is not
    safely closable by keyer selection — the train pairs underdetermine which attribute is the rule."""
    if not _same_dims(train):
        return None
    for cfg in SEG_CONFIGS:
        for kname, keyer in _attr_keyers().items():
            mapping: dict = {}
            ok = True
            for gi, go in train:
                objs = segment(gi, **cfg)
                for o in objs:
                    out_cols = {go[r][c] for r, c, _ in o.pixels}
                    if len(out_cols) != 1:       # object not recoloured uniformly -> this attr fails
                        ok = False
                        break
                    oc = out_cols.pop()
                    k = keyer(o, objs)
                    if k in mapping and mapping[k] != oc:
                        ok = False
                        break
                    mapping[k] = oc
                if not ok:
                    break
            if not ok or not mapping:
                continue

            def prog(g, _cfg=cfg, _keyer=keyer, _m=dict(mapping)):
                objs = segment(g, **_cfg)
                out = [row[:] for row in g]
                for o in objs:
                    k = _keyer(o, objs)
                    if k not in _m:
                        return [[]]
                    for r, c, _ in o.pixels:
                        out[r][c] = _m[k]
                return out
            if verify(prog, train):
                return prog
    return None


# --- gravity ------------------------------------------------------------------------------------
def strat_gravity(train) -> Program | None:
    """SAME-DIMS. Non-background cells fall in one of four directions until blocked."""
    if not _same_dims(train):
        return None
    for bg in (0, None):
        for direction in ("down", "up", "left", "right"):
            def prog(g, _bg=bg, _d=direction):
                b = mode_color(g) if _bg is None else _bg
                return gravity(g, b, _d)
            if verify(prog, train):
                return prog
    return None


# --- count -> solid rectangle -------------------------------------------------------------------
def _count_features(objs: list[Obj]) -> dict[str, int]:
    if not objs:
        return {"n_obj": 0, "n_colors": 0, "max_size": 0, "n_common_shape": 0}
    shape_freq = Counter(o.norm_shape for o in objs)
    return {
        "n_obj": len(objs),
        "n_colors": len({o.primary_color for o in objs}),
        "max_size": max(o.size for o in objs),
        "n_common_shape": shape_freq.most_common(1)[0][1],
    }


def strat_count(train) -> Program | None:
    """OUTPUT = a solid monochrome rectangle whose size encodes a COUNT feature of the input's objects
    (n objects / n colours / ...). Shape maps N->(N,N)|(N,1)|(1,N); colour is constant across train."""
    if not all(len({v for row in go for v in row}) == 1 for _, go in train):
        return None  # every train output must be monochrome
    out_colors = {go[0][0] for _, go in train}
    shape_maps = {"square": lambda n: (n, n), "col": lambda n: (n, 1), "row": lambda n: (1, n)}
    for cfg in SEG_CONFIGS:
        for feat in ("n_obj", "n_colors", "max_size", "n_common_shape"):
            for smap in shape_maps.values():
                # constant-colour model
                if len(out_colors) == 1:
                    c = next(iter(out_colors))
                    def prog(g, _cfg=cfg, _feat=feat, _smap=smap, _c=c):
                        n = _count_features(segment(g, **_cfg))[_feat]
                        if n <= 0:
                            return [[]]
                        h, w = _smap(n)
                        return solid_rect(h, w, _c)
                    if verify(prog, train):
                        return prog
    return None


# --- symmetry repair ----------------------------------------------------------------------------
def _sym_coord(name: str, r: int, c: int, R: int, C: int) -> tuple[int, int] | None:
    if name == "flip_h":
        return (r, C - 1 - c)
    if name == "flip_v":
        return (R - 1 - r, c)
    if name == "rot180":
        return (R - 1 - r, C - 1 - c)
    if name == "transpose" and R == C:
        return (c, r)
    return None


def strat_symmetry_repair(train) -> Program | None:
    """SAME-DIMS. The grid is a symmetric pattern with an occluded patch (a single 'hole' colour);
    reconstruct each hole cell from its symmetric partner. Hole colour + symmetry learned from train."""
    if not _same_dims(train):
        return None
    hole_candidates = sorted({v for gi, _ in train for row in gi for v in row})
    for sym in ("flip_h", "flip_v", "rot180", "transpose"):
        for hole in hole_candidates:
            def prog(g, _sym=sym, _hole=hole):
                R, C = dims(g)
                out = [row[:] for row in g]
                changed = False
                for r in range(R):
                    for c in range(C):
                        if g[r][c] != _hole:
                            continue
                        p = _sym_coord(_sym, r, c, R, C)
                        if p is None:
                            return [[]]
                        pr, pc = p
                        if g[pr][pc] != _hole:
                            out[r][c] = g[pr][pc]
                            changed = True
                return out if changed else [[]]
            if verify(prog, train):
                return prog
    return None


# --- A3: per-object map+assemble FIT closers -----------------------------------------------------
# These learn a per-object transform from train and re-execute it over EVERY object (map_objects). The
# geometry variant (flip/rotate each object in place) is parameter-free and lives in the OE enumerator
# (oe_search: "mapgeo"); the two below need a train-learned parameter (a slide direction, or a colour
# FUNCTION) that a pure input-only enumeration cannot express, so they are closers like strat_recolor.
def _numeric_keyers() -> dict[str, Callable[["Obj", list], int]]:
    """Per-object INTEGER attributes a colour FUNCTION can be derived over (all task-independent, read
    against THIS grid's own object set). Ranks/positions give the 'colour = f(rank/position)' family."""
    def rank_desc(o, objs):   return sum(1 for x in objs if x.size > o.size)         # 0 = largest
    def rank_asc(o, objs):    return sum(1 for x in objs if x.size < o.size)
    def row_rank(o, objs):    return sum(1 for x in objs if (x.top, x.left) < (o.top, o.left))
    def col_rank(o, objs):    return sum(1 for x in objs if (x.left, x.top) < (o.left, o.top))
    return {
        "size": lambda o, objs: o.size, "width": lambda o, objs: o.width,
        "height": lambda o, objs: o.height, "bbox_area": lambda o, objs: o.bbox_area,
        "num_colors": lambda o, objs: o.num_colors, "num_holes": lambda o, objs: num_holes(o),
        "rank_desc": rank_desc, "rank_asc": rank_asc, "row_rank": row_rank, "col_rank": col_rank,
    }


def _fit_affine(pairs: list[tuple[int, int]]) -> tuple[int, int] | None:
    """Derive colour = (a*x + b) mod 10 consistent with EVERY (x, colour) example, smallest |a|,|b| first
    (MDL/Occam). Returns (a, b) or None (no consistent closed form -> this keyer abstains). This is the
    scheme_synthesis 'derive the sub-function from its own I/O then verify' idea on the colour value space:
    a lookup TABLE (strat_recolor) memorises seen keys; a derived FUNCTION generalises to unseen ones."""
    xs = {x for x, _ in pairs}
    if len(xs) < 2:
        return None                              # 1 distinct key is a table entry, not evidence of a function
    for a in range(0, 10):
        for b in range(0, 10):
            if all((a * x + b) % 10 == y for x, y in pairs):
                if a == 0:
                    return None                  # constant colour is a degenerate 'function' -> leave to table
                return (a, b)
    return None


def strat_map_recolor_fn(train) -> Program | None:
    """SAME-DIMS function-not-table recolour (A2's L3 lever). Every object is recoloured uniformly to a
    colour that is a COMPUTED FUNCTION of one integer attribute, colour=(a*x+b) mod 10, DERIVED from train
    and verified. Fires only when a genuine affine (a!=0) fits AND the plain table (strat_recolor) did not
    already close it; abstains otherwise (no fabrication)."""
    if not _same_dims(train):
        return None
    for cfg in SEG_CONFIGS:
        # every object must map to a single colour under this segmentation (else not a recolour task)
        uniform = True
        for gi, go in train:
            for o in segment(gi, **cfg):
                if len({go[r][c] for r, c, _ in o.pixels}) != 1:
                    uniform = False; break
            if not uniform:
                break
        if not uniform:
            continue
        for kname, keyer in _numeric_keyers().items():
            pairs: list[tuple[int, int]] = []
            ok = True
            for gi, go in train:
                objs = segment(gi, **cfg)
                for o in objs:
                    y = next(iter({go[r][c] for r, c, _ in o.pixels}))
                    pairs.append((keyer(o, objs), y))
            ab = _fit_affine(pairs)
            if ab is None:
                continue
            a, b = ab

            def prog(g, _cfg=cfg, _keyer=keyer, _a=a, _b=b):
                def per(o, objs, grid, bg):
                    col = (_a * _keyer(o, objs) + _b) % 10
                    return [(r, c, col) for r, c, _ in o.pixels]
                return map_objects(g, _cfg, per)
            if verify(prog, train):
                return prog
    return None


def strat_map_slide(train) -> Program | None:
    """SAME-DIMS. Each object slides as a RIGID body to a wall (down/up/left/right) — 'push every object to
    the edge'. Unlike cell-gravity (strat_gravity) the object moves ATOMICALLY, so shape is preserved. The
    direction is learned from train and the whole program re-executed to verify (collisions/overlap that
    contradict train fail the gate -> abstain)."""
    if not _same_dims(train):
        return None
    for cfg in SEG_CONFIGS:
        for d in ("down", "up", "left", "right"):
            def prog(g, _cfg=cfg, _d=d):
                R, C = dims(g)

                def per(o, objs, grid, bg):
                    if _d == "down":
                        sh = (R - 1 - o.bottom, 0)
                    elif _d == "up":
                        sh = (-o.top, 0)
                    elif _d == "left":
                        sh = (0, -o.left)
                    else:
                        sh = (0, C - 1 - o.right)
                    return [(r + sh[0], c + sh[1], col) for r, c, col in o.pixels]
                return map_objects(g, _cfg, per)
            if verify(prog, train):
                return prog
    return None


# ================================================================ A4: RELATIONAL colour-function recolour (L3)
# The A3 probe relocated the per-object-recolor cap. Of the recolor-shaped family, the residual needs colour
# as a GENERALISING FUNCTION of a RELATIONAL object context — containment ("recolour to the frame that
# encloses me"), adjacency ("take my neighbour's colour"), shape-match, palette-permutation — not any single
# INTRINSIC attribute (strat_recolor's table already covers those) nor an affine of one (strat_map_recolor_fn).
# These helpers compute that context; all are GENERAL Chollet priors, parameter-free, read against THIS grid's
# own object set (no per-task constant, no eval fitting). The strategy synthesises colour = f(context) by
# DEDUCTION and propose-verifies against the task's OWN train pairs (reproduce ALL exactly or ABSTAIN), so
# attempted-but-wrong stays 0. Two families, MDL-ordered (a pure copy-function is simpler than a learned table):
#   B) relational colour-COPY function  — colour = a referenced object's colour (palette-agnostic; generalises)
#   A) relational KEY -> colour table    — key has a CLOSED relational domain fully seen in train
def enclosing_object(idx: int, objs: list, grid: Grid, bg: int):
    """The object that ENCLOSES objs[idx] (walls it off from the grid border), or None. BFS from the
    object's OWN cells through every cell that is NOT candidate A; if the grid border stays unreachable, A
    encloses it. The general 'inside-of' relation (Chollet containment prior)."""
    B = objs[idx]
    R, C = dims(grid)
    Bcells = frozenset((r, c) for r, c, _ in B.pixels)
    for A in objs:
        if A is B:
            continue
        Acells = frozenset((r, c) for r, c, _ in A.pixels)
        seen = set(Bcells)
        dq = deque(Bcells)
        escaped = False
        while dq:
            r, c = dq.popleft()
            if r == 0 or c == 0 or r == R - 1 or c == C - 1:
                escaped = True
                break
            for dr, dc in NEIGH4:
                nr, nc = r + dr, c + dc
                if 0 <= nr < R and 0 <= nc < C and (nr, nc) not in seen and (nr, nc) not in Acells:
                    seen.add((nr, nc)); dq.append((nr, nc))
        if not escaped:
            return A
    return None


def _cell_owner_map(objs: list) -> dict:
    return {(r, c): j for j, o in enumerate(objs) for r, c, _ in o.pixels}


def object_neighbor_colors(idx: int, objs: list, grid: Grid, bg: int) -> set:
    """Colours 4-adjacent to objs[idx], excluding bg and its OWN colour — the adjacency-context colours."""
    B = objs[idx]
    R, C = dims(grid)
    Bcells = frozenset((r, c) for r, c, _ in B.pixels)
    own = B.primary_color
    cols = set()
    for r, c, _ in B.pixels:
        for dr, dc in NEIGH4:
            nr, nc = r + dr, c + dc
            if 0 <= nr < R and 0 <= nc < C and (nr, nc) not in Bcells:
                v = grid[nr][nc]
                if v != bg and v != own:
                    cols.add(v)
    return cols


def adjacent_object_indices(idx: int, objs: list, grid: Grid, bg: int, owner: dict | None = None) -> set:
    """Indices of OTHER objects 4-adjacent to objs[idx] (the neighbour-count context)."""
    owner = owner if owner is not None else _cell_owner_map(objs)
    R, C = dims(grid)
    adj = set()
    for r, c, _ in objs[idx].pixels:
        for dr, dc in NEIGH4:
            nb = (r + dr, c + dc)
            j = owner.get(nb)
            if j is not None and j != idx:
                adj.add(j)
    return adj


def grid_palette(grid: Grid, bg: int) -> list:
    """Sorted distinct non-background colours — the palette basis for a palette-index key/permutation."""
    return sorted({v for row in grid for v in row if v != bg})


# --- relational COLOUR functions (Family B): colour = a referenced object's colour; None -> abstain --------
def _col_container(idx, objs, grid, bg, ctx):
    a = ctx["encloser"][idx]
    return objs[a].primary_color if a >= 0 else None


def _col_shape_twin(idx, objs, grid, bg, ctx):
    o = objs[idx]
    twins = [k for k in range(len(objs)) if k != idx and objs[k].norm_shape == o.norm_shape]
    return objs[twins[0]].primary_color if len(twins) == 1 else None


def _col_adjacent_unique(idx, objs, grid, bg, ctx):
    cols = object_neighbor_colors(idx, objs, grid, bg)
    return next(iter(cols)) if len(cols) == 1 else None


def _col_enclosed_content(idx, objs, grid, bg, ctx):
    inner = [k for k in range(len(objs)) if ctx["encloser"][k] == idx]
    return objs[inner[0]].primary_color if len(inner) == 1 else None


def _col_container_or_self(idx, objs, grid, bg, ctx):
    """The enclosing frame's colour if this object is contained, else its OWN colour — the common
    'recolour each object to the box that holds it; frames keep their colour' rule (a CONDITIONAL copy,
    which a pure container-copy — abstaining on the un-contained frames — cannot express)."""
    a = ctx["encloser"][idx]
    return objs[a].primary_color if a >= 0 else objs[idx].primary_color


_REL_COLFUNCS: tuple = (
    ("adjacent_color", _col_adjacent_unique),
    ("container_color", _col_container),
    ("container_or_self", _col_container_or_self),
    ("shape_twin_color", _col_shape_twin),
    ("enclosed_content_color", _col_enclosed_content),
)


# --- relational KEY functions (Family A): hashable key with a CLOSED relational domain --------------------
def _rel_keyers() -> tuple:
    return (
        ("contained",       lambda i, objs, g, bg, ctx: ctx["encloser"][i] >= 0),
        ("container_color", lambda i, objs, g, bg, ctx: (objs[ctx["encloser"][i]].primary_color if ctx["encloser"][i] >= 0 else -1)),
        ("n_adjacent",      lambda i, objs, g, bg, ctx: len(ctx["adj"][i])),
        ("palette_idx",     lambda i, objs, g, bg, ctx: (ctx["pal"].index(objs[i].primary_color) if objs[i].primary_color in ctx["pal"] else -1)),
        ("color_mult",      lambda i, objs, g, bg, ctx: ctx["colmult"][objs[i].primary_color]),
        ("shape_mult",      lambda i, objs, g, bg, ctx: ctx["shapemult"][objs[i].norm_shape]),
    )


def _relational_context(objs: list, grid: Grid, bg: int) -> dict:
    """Precompute the (expensive-once) relational features for EVERY object so each candidate rule is cheap."""
    owner = _cell_owner_map(objs)
    return {
        "encloser":   [(lambda a: objs.index(a) if a is not None else -1)(enclosing_object(i, objs, grid, bg))
                       for i in range(len(objs))],
        "adj":        [adjacent_object_indices(i, objs, grid, bg, owner) for i in range(len(objs))],
        "pal":        grid_palette(grid, bg),
        "colmult":    Counter(o.primary_color for o in objs),
        "shapemult":  Counter(o.norm_shape for o in objs),
    }


def _pure_recolor(gi: Grid, go: Grid, cfg: dict) -> bool:
    """gi->go is a pure per-object recolour under cfg: same dims, every object's out-cells uniform, and every
    non-object (background) cell unchanged. (map_objects repaints bg, so bg-preservation is required.)"""
    if dims(gi) != dims(go):
        return False
    objs = segment(gi, **cfg)
    cells = set()
    for o in objs:
        if len({go[r][c] for r, c, _ in o.pixels}) != 1:
            return False
        for r, c, _ in o.pixels:
            cells.add((r, c))
    R, C = dims(gi)
    for r in range(R):
        for c in range(C):
            if (r, c) not in cells and gi[r][c] != go[r][c]:
                return False
    return True


_REL_MAX_OBJS = 60      # cost cap: relational features (O(n^2*grid) containment) skip huge object sets


def _build_relational_prog(cfg: dict, colour_of: Callable) -> Program:
    """colour_of(objs, grid, bg, ctx) -> {idx: colour|None}. Compile into a bg-preserving recolour program."""
    def prog(g, _cfg=cfg, _co=colour_of):
        objs = segment(g, **_cfg)
        if not objs or len(objs) > _REL_MAX_OBJS:
            return [[]]
        bg = mode_color(g) if _cfg["background"] is None else _cfg["background"]
        ctx = _relational_context(objs, g, bg)
        cmap = _co(objs, g, bg, ctx)
        if cmap is None:
            return [[]]
        idx_of = {o: i for i, o in enumerate(objs)}

        def per(o, os_, grid, b):
            col = cmap.get(idx_of[o])
            return [(r, c, col) for r, c, _ in o.pixels] if col is not None else _MAP_FAIL
        return map_objects(g, _cfg, per)
    return prog


def strat_relational_recolor(train) -> Program | None:
    """SAME-DIMS. Recolour each object to a colour that is a FUNCTION of its RELATIONAL context, DERIVED from
    train and propose-verified EXACT (reproduce ALL train pairs or ABSTAIN). MDL-ordered: colour-COPY
    functions (description length ~1, palette-agnostic) before learned KEY tables. A rule that is undefined on
    a test object (no unique reference / an unseen key) abstains ([[ ]]) — attempted-but-wrong stays 0."""
    if not _same_dims(train):
        return None
    # candidate segmentations: those under which EVERY train pair is a pure per-object recolour (bg preserved)
    cfgs = [c for c in SEG_CONFIGS if all(_pure_recolor(gi, go, c) for gi, go in train)]
    if not cfgs:
        return None
    # precompute per-(pair,cfg) objects/ctx once, guarding the object-count cap
    for cfg in cfgs:
        prep = []
        too_big = False
        for gi, go in train:
            objs = segment(gi, **cfg)
            if len(objs) > _REL_MAX_OBJS:
                too_big = True
                break
            bg = mode_color(gi) if cfg["background"] is None else cfg["background"]
            prep.append((gi, go, objs, bg, _relational_context(objs, gi, bg)))
        if too_big or not prep:
            continue

        # ---- Family B: relational colour-COPY functions (simplest first) ----
        for fname, func in _REL_COLFUNCS:
            ok = True
            changed = 0
            for gi, go, objs, bg, ctx in prep:
                for i, o in enumerate(objs):
                    col = func(i, objs, gi, bg, ctx)
                    if col is None:
                        ok = False; break
                    want = next(iter({go[r][c] for r, c, _ in o.pixels}))
                    if col != want:
                        ok = False; break
                    if col != o.primary_color:
                        changed += 1
                if not ok:
                    break
            if ok and changed >= 1:
                colour_of = (lambda objs, g, bg, ctx, _f=func:
                             {i: _f(i, objs, g, bg, ctx) for i in range(len(objs))})
                prog = _build_relational_prog(cfg, colour_of)
                if verify(prog, train):
                    return prog

        # ---- Family A: relational KEY -> colour tables (>=2 distinct keys = real evidence of a function) ----
        for kname, keyer in _rel_keyers():
            mapping: dict = {}
            ok = True
            for gi, go, objs, bg, ctx in prep:
                for i, o in enumerate(objs):
                    want = next(iter({go[r][c] for r, c, _ in o.pixels}))
                    k = keyer(i, objs, gi, bg, ctx)
                    if k in mapping and mapping[k] != want:
                        ok = False; break
                    mapping[k] = want
                if not ok:
                    break
            if not ok or len(mapping) < 2:
                continue
            changed = any(next(iter({go[r][c] for r, c, _ in o.pixels})) != o.primary_color
                          for gi, go, objs, bg, ctx in prep for o in objs)
            if not changed:
                continue
            colour_of = (lambda objs, g, bg, ctx, _k=keyer, _m=dict(mapping):
                         ({i: _m[_k(i, objs, g, bg, ctx)] for i in range(len(objs))}
                          if all(_k(i, objs, g, bg, ctx) in _m for i in range(len(objs))) else None))
            prog = _build_relational_prog(cfg, colour_of)
            if verify(prog, train):
                return prog
    return None


# The same-dims / whole-grid TRAIN-FIT closers: each fits a parameter (a learned attr->colour map, a
# count->rectangle model, an occlusion symmetry) from train that a pure input-only enumeration cannot
# express. Kept cheap-first (MDL: simplest local edits before count/repair). strat_select_crop and
# strat_select_then_geo are DELIBERATELY NOT here — they are SUBSUMED and DEEPENED by the OE enumerator
# below (A2): the enumerator reaches select->render, select->crop->geo AND deeper (select->crop->geo->geo,
# filter->gravity, relational-select->crop, ...), with the richer relational selectors, all under one
# bounded OE+MDL search. (Both functions remain defined and unit-tested as the depth-1 primitives.)
OBJECT_FIT_STRATEGIES: tuple[Callable[[list], Program | None], ...] = (
    strat_filter,            # same-dims, local erase (denoise / keep)
    strat_relational_recolor,  # A4: recolour by a RELATIONAL colour FUNCTION (containment/adjacency/palette). A pure
                             # copy-function is MDL ~1 — simpler than a learned table — so it precedes strat_recolor;
                             # it fires on only 3/400 eval tasks (0 wrong) and abstains unless the relation reproduces
                             # ALL train, so it never shadows an intrinsic-table solve (measured: no baseline regression).
    strat_recolor,           # same-dims, local recolour by a LEARNED attribute->colour table
    strat_map_recolor_fn,    # A3: same-dims, per-object recolour by a DERIVED colour FUNCTION (a*x+b mod 10)
    strat_map_slide,         # A3: same-dims, each object slides atomically to a wall
    strat_gravity,           # same-dims, deterministic fall
    strat_count,             # count -> rectangle
    strat_symmetry_repair,   # reconstruct occlusion
)


def synthesize_objectwise(train: list[tuple[Grid, Grid]], deadline: float | None = None) -> Program | None:
    """Object-centric synthesis, propose-verify. Three stages, each returning ONLY a program that reproduces
    EVERY train pair exactly (else None -> abstain):

      (1) the TRAIN-FIT closers (recolour-table / count / gravity / filter / symmetry-repair) — the ops
          whose behaviour is a parameter learned from train, which a pure input-only search cannot express;
      (2) the A5 LEGEND readers (legend.LEGEND_STRATEGIES) — decode an IN-GRID key region (a colour-
          permutation corner block, or a marker shape->colour dictionary) FRESH per grid and apply it to the
          body; the transform is not fixed across the task, it is READ from each grid's own legend;
      (3) the OE + MDL ENUMERATOR (oe_search.oe_object_search) — the invention engine's bottom-up,
          observational-equivalence, size-layered search over the object DSL, which composes DEEPER than the
          old depth-1 strategies (relational selection + multi-step select/crop/render/geometry/gravity).

    The LEGEND stage runs BEFORE the intrinsic-table closers and the OE enumerator: a legend/shape-dictionary
    is a MORE GENERAL hypothesis than an intrinsic per-object attribute->colour TABLE, which can also verify
    the train of a legend task but as a NARROW table that then abstains on the test's novel key (measured:
    strat_recolor shadows 009d5c81 that way). Trying the legend readers first lets the general reading win
    when both verify; each legend program is still propose-verified EXACT before it may answer, and the legend
    readers were measured NOT to fire on any of the existing baseline solves (so they never shadow a real
    closer solve). The OE enumerator's object DSL cannot express legend reading, so it abstains on these
    tasks anyway.

    `deadline` (time.monotonic() value) bounds the whole search so the bigger DSL cannot blow up per-task
    cost; the enumerator additionally honours a node budget and max size."""
    import time
    from packages.arc_agi.oe_search import oe_object_search
    from packages.arc_agi.legend import LEGEND_STRATEGIES
    from packages.arc_agi.application import APPLICATION_STRATEGIES
    for strat in LEGEND_STRATEGIES:
        if deadline is not None and time.monotonic() > deadline:
            return None
        prog = strat(train)
        if prog is not None:
            return prog
    # A6 APPLICATION-GRAMMAR readers (orientation-invariant shape dict / per-object attached marker / periodic-
    # lattice legend-indexed recolour). Like the A5 legend readers, these are MORE GENERAL hypotheses than an
    # intrinsic per-object attribute->colour TABLE, which can verify a legend task's train as a NARROW table
    # then abstain on the test's novel key (measured: strat_recolor shadows 604001fa that way -> undef-on-test).
    # So they run BEFORE the intrinsic-table closers; each is still propose-verified EXACT and carries a niche
    # guard (orientation genuinely used / >=2 local markers / a real unique-legend P x Q lattice), so they were
    # measured NOT to fire on any existing baseline solve (no shadowing) and keep attempted-but-wrong at 0.
    for strat in APPLICATION_STRATEGIES:
        if deadline is not None and time.monotonic() > deadline:
            return None
        prog = strat(train)
        if prog is not None:
            return prog
    for strat in OBJECT_FIT_STRATEGIES:
        if deadline is not None and time.monotonic() > deadline:
            return None
        prog = strat(train)
        if prog is not None:
            return prog
    if deadline is not None and time.monotonic() > deadline:
        return None
    return oe_object_search(train, deadline=deadline)

