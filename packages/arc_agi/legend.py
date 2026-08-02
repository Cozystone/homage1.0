# -*- coding: utf-8 -*-
"""A5 — LEGEND / IN-GRID-TABLE reading front-end for the ARC-AGI solver (No-LLM, propose-verify).

WHY THIS FILE EXISTS (the A4 measured cap)
------------------------------------------
A4 added relational per-object colour deduction and then INSPECTED the residual relational-recolor family.
The bulk do NOT need richer per-object features — they need to READ AN IN-GRID LEGEND: a small key region
embedded in the input that DEFINES a mapping (a colour permutation, or a shape->colour dictionary), which is
then applied to the REST of the grid. This is a "read the instructions embedded in the input" capability,
categorically different from per-object attributes: the transform is not fixed across the task, it is
DECODED per grid from that grid's own key region.

THE GENERAL PRIOR (parameter-free, read against each grid; no per-task rule, no eval fitting)
--------------------------------------------------------------------------------------------
Two legend KINDS, each detected+parsed generally and propose-verified EXACT (reproduce ALL train pairs or
ABSTAIN — attempted-but-wrong stays 0):

  (1) COLOUR-PERMUTATION legend (strat_legend_colormap). A small SEPARABLE key block in a grid corner encodes
      a colour<->colour map (its cells, read in pairs, are the map entries). The map is applied to the BODY
      (the grid minus the key block); the key block itself is kept (or blanked). The map is DECODED FRESH from
      each grid's own corner block, so a grid whose key names a permutation the train grids never showed is
      still handled — the rule is the READING, not a fixed table. (cracks 0becf7df: a 2x2 block whose two rows
      are the swap pairs.)

  (2) SHAPE->COLOUR dictionary (strat_shape_dict_recolor). A distinguished MARKER colour's connected shape is
      a KEY that names the colour the BODY is recoloured to; the marker is consumed (-> background). The
      shape->colour dictionary is learned ACROSS the task's train pairs (each pair contributes one entry) and
      applied by shape lookup; a novel marker shape -> abstain. (cracks 009d5c81: a colour-1 marker whose
      +/L/T shape selects which colour the colour-8 body becomes.)

DEDUCTION discipline (scheme_synthesis pattern): PROPOSE {which region is the legend, how it parses}, then
VERIFY the resulting map + application reproduces ALL train pairs EXACTLY; ABSTAIN if no candidate legend
yields an exact-consistent map. MDL-order candidates (smallest key region / simplest reading first). Every
program is synthesised from the task's OWN train pairs; the eval test output is never read here.
"""
from __future__ import annotations

from collections import Counter, deque

from packages.arc_agi import objects as O

Grid = list[list[int]]
Program = "Callable[[Grid], Grid]"

_LEGEND_MAX_AREA = 16      # a key block bigger than this is not a plausible small legend (cost + generality cap)
_NEIGH8 = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


# ================================================================ candidate key-region priors
def _corner_block(grid: Grid, corner: str, bg: int):
    """Prior (a): the SEPARABLE small key block anchored at a grid corner. Flood the 8-connected non-bg
    component touching the corner; return its bounding box (t,l,b,rt) IFF the block is (i) small, and
    (ii) SEPARABLE — every in-grid cell on the ring just outside the bbox is background, so the block is a
    self-contained key walled off from the body. None otherwise. General: no size/colour is hardcoded, the
    block's extent is DETECTED per grid."""
    R, C = O.dims(grid)
    if R == 0 or C == 0:
        return None
    r0 = 0 if corner in ("tl", "tr") else R - 1
    c0 = 0 if corner in ("tl", "bl") else C - 1
    if grid[r0][c0] == bg:
        return None
    seen = {(r0, c0)}
    dq = deque([(r0, c0)])
    while dq:
        r, c = dq.popleft()
        for dr, dc in _NEIGH8:
            nr, nc = r + dr, c + dc
            if 0 <= nr < R and 0 <= nc < C and (nr, nc) not in seen and grid[nr][nc] != bg:
                seen.add((nr, nc))
                dq.append((nr, nc))
    rs = [r for r, _ in seen]
    cs = [c for _, c in seen]
    t, l, b, rt = min(rs), min(cs), max(rs), max(cs)
    if (b - t + 1) * (rt - l + 1) > _LEGEND_MAX_AREA:
        return None
    # separability: the ring of in-grid cells immediately outside the bbox must be all background
    for c in range(l - 1, rt + 2):
        for r in (t - 1, b + 1):
            if 0 <= r < R and 0 <= c < C and grid[r][c] != bg:
                return None
    for r in range(t - 1, b + 2):
        for c in (l - 1, rt + 1):
            if 0 <= r < R and 0 <= c < C and grid[r][c] != bg:
                return None
    return (t, l, b, rt)


def _framed_corner(grid: Grid, corner: str, bg: int):
    """Prior (b): a corner cell WALLED OFF by a uniform BORDER colour. For the tl corner: the border is an L
    at (r_b, c_b) — column c_b is one border colour B for rows 0..r_b AND row r_b is B for cols 0..c_b — so
    B (with the two grid edges) frames the rectangle rows 0..r_b-1 x cols 0..c_b-1. Returns
    (region_bbox, border_colour, inner_colours) with inner = the non-bg non-border colours inside the frame,
    or None. General: the border colour and frame extent are DETECTED per grid, not hardcoded. This is the
    'framed/bordered cell' key-region the corner-block detector (which needs a non-bg corner CELL) misses."""
    R, C = O.dims(grid)
    if R < 2 or C < 2:
        return None
    rdir = 1 if corner in ("tl", "tr") else -1
    cdir = 1 if corner in ("tl", "bl") else -1
    r_anchor = 0 if rdir == 1 else R - 1
    c_anchor = 0 if cdir == 1 else C - 1
    # the border colour B = the first non-bg cell walking IN along the anchor row from the corner
    cb = None
    B = None
    for step in range(1, C):
        c = c_anchor + cdir * step
        if not (0 <= c < C):
            break
        if grid[r_anchor][c] != bg:
            cb, B = c, grid[r_anchor][c]
            break
    if cb is None:
        return None
    # r_b = first non-bg cell walking IN along the anchor column; must be the SAME border colour B
    rb = None
    for step in range(1, R):
        r = r_anchor + rdir * step
        if not (0 <= r < R):
            break
        if grid[r][c_anchor] != bg:
            if grid[r][c_anchor] != B:
                return None
            rb = r
            break
    if rb is None:
        return None
    r0, r1 = sorted((r_anchor, rb))
    c0, c1 = sorted((c_anchor, cb))
    # verify the full L border is the uniform colour B
    for r in range(r0, r1 + 1):
        if grid[r][cb] != B:
            return None
    for c in range(c0, c1 + 1):
        if grid[rb][c] != B:
            return None
    # the framed region is the rectangle strictly inside the L (excluding the border row/col)
    ir0, ir1 = (r0, r1 - 1) if rdir == 1 else (r0 + 1, r1)
    ic0, ic1 = (c0, c1 - 1) if cdir == 1 else (c0 + 1, c1)
    if ir1 < ir0 or ic1 < ic0:
        return None
    if (ir1 - ir0 + 1) * (ic1 - ic0 + 1) > _LEGEND_MAX_AREA:
        return None
    inner = sorted({grid[r][c] for r in range(ir0, ir1 + 1) for c in range(ic0, ic1 + 1)
                    if grid[r][c] != bg and grid[r][c] != B})
    if not inner:
        return None
    # the KEEP region is the FULL L-cornered rectangle (inner cells + the border), preserved in the output
    return (r0, c0, r1, c1), B, inner


# ================================================================ (1) COLOUR-PERMUTATION legend
def _read_pairs(block: Grid, bg: int, reading: str) -> list[tuple[int, int]]:
    """Parse a key block into colour PAIRS by one of a few GENERAL readings. Each pair (a,b) is a map entry.
    'rows'/'cols': within each row/column, consecutive non-bg cells pair up. Returns [] if the block does not
    factor into clean pairs under this reading (an odd count in a line -> reject)."""
    pairs: list[tuple[int, int]] = []
    if reading == "rows":
        lines = block
    elif reading == "cols":
        lines = [list(col) for col in zip(*block)]
    else:
        return []
    for line in lines:
        vals = [v for v in line if v != bg]
        if len(vals) % 2 != 0:
            return []
        for i in range(0, len(vals), 2):
            pairs.append((vals[i], vals[i + 1]))
    return pairs


def _build_colormap(pairs: list[tuple[int, int]], directed: bool) -> dict | None:
    """Compile pairs into a colour->colour map. swap: a<->b (an involution); directed: a->b only. Reject a
    map with a key collision (the same source colour forced to two targets) -> not a clean permutation."""
    m: dict[int, int] = {}
    for a, b in pairs:
        if a == b:
            continue
        if a in m and m[a] != b:
            return None
        m[a] = b
        if not directed:
            if b in m and m[b] != a:
                return None
            m[b] = a
    return m or None


def _apply_colormap(grid: Grid, region, m: dict, keep_legend: bool, bg: int) -> Grid:
    """Recolour every BODY cell (outside `region`) by m; the legend region is kept unchanged (keep_legend)
    or blanked to bg. General bg-preserving application."""
    t, l, b, rt = region
    out = [row[:] for row in grid]
    R, C = O.dims(grid)
    for r in range(R):
        for c in range(C):
            in_region = t <= r <= b and l <= c <= rt
            if in_region:
                if not keep_legend:
                    out[r][c] = bg
            else:
                v = grid[r][c]
                if v in m:
                    out[r][c] = m[v]
    return out


def strat_legend_colormap(train) -> "Program | None":
    """SAME-DIMS. Decode a COLOUR-PERMUTATION from a separable corner key block and apply it to the body,
    DERIVED per grid and propose-verified EXACT. MDL-ordered (each corner's block is small-by-construction;
    swap readings before directed; keep-legend before blank-legend). A grid with no separable corner block,
    or whose decoded map does not reproduce train, ABSTAINS ([[ ]])."""
    if not all(O.dims(gi) == O.dims(go) for gi, go in train):
        return None
    for bg in (0, None):
        for corner in ("tl", "tr", "bl", "br"):
            for reading in ("rows", "cols"):
                for directed in (False, True):
                    for keep in (True, False):
                        def prog(g, _bg=bg, _cn=corner, _rd=reading, _di=directed, _kp=keep):
                            b = O.mode_color(g) if _bg is None else _bg
                            region = _corner_block(g, _cn, b)
                            if region is None:
                                return [[]]
                            t, l, bb, rt = region
                            block = [row[l:rt + 1] for row in g[t:bb + 1]]
                            pairs = _read_pairs(block, b, _rd)
                            if not pairs:
                                return [[]]
                            m = _build_colormap(pairs, _di)
                            if m is None:
                                return [[]]
                            return _apply_colormap(g, region, m, _kp, b)
                        if _verify(prog, train):
                            return prog
    return None


def strat_legend_framed(train) -> "Program | None":
    """SAME-DIMS. A FRAMED corner cell (walled off by a uniform border colour, prior b) names colour(s); the
    named colour is a colour-MAP applied to the body while the framed region is KEPT. Two readings, MDL-order:
    a SINGLE inner colour C -> the removal map {C -> bg} ('the highlighted colour is erased from the field');
    or inner colours read as PAIRS -> a permutation. DERIVED per grid (the border colour and framed colour are
    read from each grid), propose-verified EXACT. No framed cell, or a reading that misses a train pair ->
    ABSTAIN ([[ ]])."""
    if not all(O.dims(gi) == O.dims(go) for gi, go in train):
        return None
    for bg in (0, None):
        for corner in ("tl", "tr", "bl", "br"):
            for reading in ("remove", "rows", "cols"):
                def prog(g, _bg=bg, _cn=corner, _rd=reading):
                    b = O.mode_color(g) if _bg is None else _bg
                    got = _framed_corner(g, _cn, b)
                    if got is None:
                        return [[]]
                    region, border, inner = got
                    if _rd == "remove":
                        if len(inner) != 1:
                            return [[]]
                        m = {inner[0]: b}
                    else:
                        t, l, bb, rt = region
                        block = [row[l:rt + 1] for row in g[t:bb + 1]]
                        pairs = _read_pairs(block, b, _rd)
                        m = _build_colormap(pairs, False) if pairs else None
                        if not m:
                            return [[]]
                    return _apply_colormap(g, region, m, True, b)
                if _verify(prog, train):
                    return prog
    return None


# ================================================================ (2) SHAPE->COLOUR dictionary (marker)
def _single_component(cells: set) -> bool:
    """True iff the cell set is one 8-connected component (so its shape is a well-defined key)."""
    if not cells:
        return False
    start = next(iter(cells))
    seen = {start}
    dq = deque([start])
    while dq:
        r, c = dq.popleft()
        for dr, dc in _NEIGH8:
            nb = (r + dr, c + dc)
            if nb in cells and nb not in seen:
                seen.add(nb)
                dq.append(nb)
    return len(seen) == len(cells)


def _norm_shape(cells) -> frozenset:
    rs = [r for r, _ in cells]
    cs = [c for _, c in cells]
    t, l = min(rs), min(cs)
    return frozenset((r - t, c - l) for r, c in cells)


def strat_shape_dict_recolor(train) -> "Program | None":
    """SAME-DIMS. A MARKER colour's connected SHAPE is a KEY naming the colour the BODY becomes; the marker is
    consumed (-> bg). The shape->colour dictionary is learned ACROSS the train pairs and applied by shape
    lookup. Requires >=2 distinct shape keys (genuine shape-dependence, not a constant recolour), the marker
    to be one connected component per grid, and EXACT train reproduction. A novel marker shape at test ->
    ABSTAIN ([[ ]]). No fabrication."""
    if not all(O.dims(gi) == O.dims(go) for gi, go in train):
        return None
    for bg in (0, None):
        # marker candidates: colours present (non-bg) in EVERY train input
        common = None
        for gi, _ in train:
            b = O.mode_color(gi) if bg is None else bg
            cols = {v for row in gi for v in row if v != b}
            common = cols if common is None else (common & cols)
        if not common:
            continue
        for mc in sorted(common):
            mapping: dict = {}
            ok = True
            for gi, go in train:
                b = O.mode_color(gi) if bg is None else bg
                R, C = O.dims(gi)
                marker = {(r, c) for r in range(R) for c in range(C) if gi[r][c] == mc}
                body = {(r, c) for r in range(R) for c in range(C) if gi[r][c] != b and (r, c) not in marker}
                if not marker or not body or not _single_component(marker):
                    ok = False
                    break
                # marker must be consumed (-> bg); body must become ONE uniform colour; bg preserved
                if any(go[r][c] != b for r, c in marker):
                    ok = False
                    break
                body_out = {go[r][c] for r, c in body}
                if len(body_out) != 1:
                    ok = False
                    break
                v = body_out.pop()
                if v == b:                       # body vanished too -> not a recolour dictionary
                    ok = False
                    break
                # every non-marker/non-body cell (pure background) must be unchanged
                for r in range(R):
                    for c in range(C):
                        if (r, c) in marker or (r, c) in body:
                            continue
                        if go[r][c] != gi[r][c]:
                            ok = False
                            break
                    if not ok:
                        break
                if not ok:
                    break
                key = _norm_shape(marker)
                if key in mapping and mapping[key] != v:
                    ok = False
                    break
                mapping[key] = v
            if not ok or len(mapping) < 2:
                continue

            def prog(g, _bg=bg, _mc=mc, _m=dict(mapping)):
                b = O.mode_color(g) if _bg is None else _bg
                R, C = O.dims(g)
                marker = {(r, c) for r in range(R) for c in range(C) if g[r][c] == _mc}
                if not marker or not _single_component(marker):
                    return [[]]
                key = _norm_shape(marker)
                if key not in _m:
                    return [[]]
                v = _m[key]
                out = [row[:] for row in g]
                for r in range(R):
                    for c in range(C):
                        if (r, c) in marker:
                            out[r][c] = b
                        elif g[r][c] != b:
                            out[r][c] = v
                return out
            if _verify(prog, train):
                return prog
    return None


# ================================================================ verify gate + registry
def _verify(prog, train) -> bool:
    """The honesty gate: reproduce ALL train outputs exactly, else reject."""
    for gi, go in train:
        try:
            if prog(gi) != go:
                return False
        except Exception:
            return False
    return True


# MDL-ordered: the colour-permutation reading (a self-contained in-grid map) before the cross-pair shape
# dictionary (which needs >=2 pairs of evidence). Both propose-verify EXACT.
LEGEND_STRATEGIES = (
    strat_legend_colormap,
    strat_legend_framed,
    strat_shape_dict_recolor,
)
