# -*- coding: utf-8 -*-
"""A6 — APPLICATION-GRAMMAR extensions for the ARC legend/dictionary front-end (No-LLM, propose-verify).

WHY THIS FILE EXISTS (the A5 measured cap)
------------------------------------------
A5 built legend/dictionary DETECTION (corner colour-map, framed cell, marker shape->colour) and MEASURED that
detection is NOT the residual blocker: the surviving legend-family tasks resist because their APPLICATION
grammar is richer than "one global colour-map / one global shape-dict". A6 adds three GENERAL application
primitives — each a Chollet ARC prior (symmetry, locality, periodicity), parameter-free, synthesised from the
task's OWN train pairs and propose-verified EXACT (reproduce ALL train pairs or ABSTAIN — attempted-but-wrong
stays 0):

  (1) ORIENTATION-INVARIANT shape dictionary (strat_orient_shape_dict). The in-grid legend names a
      shape->colour dictionary, but the body objects are ROTATIONS/REFLECTIONS of the legend templates, so an
      exact shape key misses. A D4 (8-orientation) CANONICAL form (_d4_canon) makes the key orientation-
      invariant; each body object is recoloured to the template whose canonical shape it matches. The
      dictionary is READ from each grid's OWN templates (per-grid legend), so a test whose template colours
      the train never showed is still handled. (targets 845d6e51.)

  (2) PER-OBJECT ATTACHED MARKER (strat_attached_marker). Not a global legend: each body object carries its
      OWN nearby marker sub-shape, and that LOCAL marker's shape sets the object's recolour. Associate each
      body to its nearest marker (unique-nearest or abstain), learn the marker-shape->colour dictionary ACROSS
      train, consume the markers. (targets 604001fa.)

  (3) PERIODIC-LATTICE legend-indexed recolour (strat_periodic_legend). The grid is a P x Q lattice of one
      repeated motif; a compact P x Q legend block elsewhere drives a TILE-INDEXED recolour (motif at tile
      (i,j) -> legend[i][j]). General grid-periodicity induction (_lattice) detects the motif period and the
      P x Q arrangement, EXPOSING the tile index as the feature the legend keys on. (targets 33b52de3.)

DEDUCTION discipline (scheme_synthesis / A5 pattern): PROPOSE {which colour is body, which is the marker/
lattice, how the dictionary keys, where the legend sits}, VERIFY the resulting application reproduces ALL
train pairs EXACTLY, ABSTAIN otherwise. MDL-order candidates. Every program is synthesised from the task's OWN
train pairs; the eval test output is never read here. Each primitive carries a NICHE guard (orientation
actually used / >=2 distinct local markers / a genuine P x Q lattice with a UNIQUE legend block) so it fires
only where its grammar is truly needed — it never shadows a simpler closer, keeping attempted-but-wrong at 0.
"""
from __future__ import annotations

from packages.arc_agi import objects as O

Grid = list[list[int]]
Program = "Callable[[Grid], Grid]"

_MAX_VANISH = 6      # cost cap: skip tasks with a huge consumed-colour set (marker enumeration is O(k^2))
_MIN_LATTICE = 4     # a lattice needs >=4 motifs to be a real periodic tiling (P,Q >= 2)


# ================================================================ D4 symmetry primitive (Chollet prior)
def _norm(cells) -> frozenset:
    """Translation-invariant occupancy: shift a cell set to its bbox origin."""
    rs = [r for r, _ in cells]
    cs = [c for _, c in cells]
    t, l = min(rs), min(cs)
    return frozenset((r - t, c - l) for r, c in cells)


def _d4_variants(cells) -> list:
    """The 8 orientations of a shape under the dihedral group D4 (4 rotations x optional reflection), each
    RE-NORMALISED to the bbox origin. Parameter-free; the general symmetry prior over object shapes."""
    outs = []
    cur = set(cells)
    for _ in range(4):
        cur = {(c, -r) for r, c in cur}                 # rot90
        outs.append(_norm(cur))
        outs.append(_norm({(r, -c) for r, c in cur}))   # + horizontal reflection
    return outs


def _d4_canon(cells) -> tuple:
    """Orientation-INVARIANT key: the lexicographically-minimal orientation of the shape (a canonical
    representative of its D4 orbit). Two shapes are D4-equal iff their canon keys are equal."""
    best = None
    for v in _d4_variants(cells):
        k = tuple(sorted(v))
        if best is None or k < best:
            best = k
    return best


# ================================================================ shared: background + consumed colours
def _bg_of(g: Grid, bgspec) -> int:
    return O.mode_color(g) if bgspec is None else bgspec


def _vanishing_colors(train, bgspec) -> set:
    """Colours present (non-bg) in EVERY train input yet ABSENT from the corresponding output — the colours
    the transform CONSUMES (recolours away / erases). Intersected across pairs -> a stable candidate set for
    'body' / 'marker' / 'lattice' colours. A learned-from-train parameter, never hardcoded."""
    common = None
    for gi, go in train:
        b = _bg_of(gi, bgspec)
        ci = {v for row in gi for v in row if v != b}
        co = {v for row in go for v in row}
        van = ci - co
        common = van if common is None else (common & van)
    return common or set()


def _verify(prog, train) -> bool:
    """The honesty gate: reproduce ALL train outputs exactly, else reject (-> abstain)."""
    for gi, go in train:
        try:
            if prog(gi) != go:
                return False
        except Exception:
            return False
    return True


# ================================================================ (1) ORIENTATION-INVARIANT shape dictionary
def _apply_orient(g: Grid, body: int, cfg: dict, bgspec):
    """Read THIS grid's own legend (every non-body object is a template canon_shape->colour entry) and
    recolour each body object to the template whose D4-canonical shape it matches. Returns (grid, used_orient)
    or (None, False) to abstain: a template collision, no body objects, or a body whose canon matches no
    template. `used_orient` flags whether any body needed a NON-identity orientation (the niche guard)."""
    objs = O.segment(g, **cfg)
    templates: dict = {}                         # D4 canon -> colour
    tnorm: dict = {}                             # D4 canon -> the template's own norm_shape (exact vs oriented)
    for o in objs:
        if o.primary_color == body:
            continue
        k = _d4_canon(o.norm_shape)
        if k in templates and templates[k] != o.primary_color:
            return None, False                   # two colours share a canonical shape -> ambiguous legend
        templates[k] = o.primary_color
        tnorm[k] = o.norm_shape
    bodies = [o for o in objs if o.primary_color == body]
    if not bodies:
        return None, False
    out = [row[:] for row in g]
    used = False
    for o in bodies:
        k = _d4_canon(o.norm_shape)
        if k not in templates:
            return None, False
        if o.norm_shape != tnorm[k]:
            used = True                          # this body is a real rotation/reflection of its template
        v = templates[k]
        for r, c, _ in o.pixels:
            out[r][c] = v
    return out, used


def strat_orient_shape_dict(train) -> "Program | None":
    """SAME-DIMS. An IN-GRID legend names a shape->colour dictionary; each body object is a D4 (8-orientation)
    variant of a legend template and is recoloured to that template's colour. The dictionary is READ per grid
    (the templates live in the grid), so it generalises to a test whose template colours the train never show.
    Body colour = the colour CONSUMED in every train pair (learned). Niche guard: orientation must be GENUINELY
    used (>=1 body whose exact shape differs from its template) so this never shadows the plain shape-dict /
    recolour closers. Propose-verify EXACT, else ABSTAIN ([[ ]])."""
    if not all(O.dims(gi) == O.dims(go) for gi, go in train):
        return None
    for bgspec in (0, None):
        for body in sorted(_vanishing_colors(train, bgspec)):
            for conn in (8, 4):
                cfg = {"connectivity": conn, "by_color": True, "background": bgspec}
                ok, used_any = True, False
                for gi, go in train:
                    pred, used = _apply_orient(gi, body, cfg, bgspec)
                    if pred != go:
                        ok = False
                        break
                    used_any = used_any or used
                if ok and used_any:
                    def prog(g, _b=body, _c=cfg, _bg=bgspec):
                        out, _ = _apply_orient(g, _b, _c, _bg)
                        return out if out is not None else [[]]
                    if _verify(prog, train):
                        return prog
    return None


# ================================================================ (2) PER-OBJECT ATTACHED MARKER
def _chebyshev(a_cells, b_cells) -> int:
    """Min Chebyshev (8-neighbour) distance between two pixel sets — 'how attached' a marker is to a body."""
    return min(max(abs(r1 - r2), abs(c1 - c2)) for r1, c1 in a_cells for r2, c2 in b_cells)


def _marker_key(mk, oriented: bool):
    return _d4_canon(mk.norm_shape) if oriented else tuple(sorted(mk.norm_shape))


def _nearest_marker(bcells, markers, mcells):
    """The unique marker nearest to a body (min Chebyshev). Returns its index, or None on a distance TIE
    (ambiguous attachment -> abstain, never a guess)."""
    dists = sorted((_chebyshev(bcells, mc), mi) for mi, mc in enumerate(mcells))
    if len(dists) > 1 and dists[0][0] == dists[1][0]:
        return None
    return dists[0][1]


def _learn_marker_pair(gi, go, body, marker, cfg, bgspec, oriented, mapping) -> bool:
    """Accumulate the marker-shape->colour dictionary from ONE train pair, checking the full local-marker
    grammar: markers consumed (-> bg), each body recoloured uniformly to dict[nearest-marker shape], every
    other cell unchanged. False if this pair does not fit (dictionary collision, ambiguous attachment, a body
    that vanishes, or an unexplained changed cell)."""
    b = _bg_of(gi, bgspec)
    objs = O.segment(gi, **cfg)
    bodies = [o for o in objs if o.primary_color == body]
    markers = [o for o in objs if o.primary_color == marker]
    if not bodies or not markers:
        return False
    mcells = [frozenset((r, c) for r, c, _ in o.pixels) for o in markers]
    for mc in mcells:                              # markers must be consumed to background
        if any(go[r][c] != b for r, c in mc):
            return False
    bodyset, markset = set(), set()
    for o in bodies:
        bcells = frozenset((r, c) for r, c, _ in o.pixels)
        mi = _nearest_marker(bcells, markers, mcells)
        if mi is None:
            return False
        k = _marker_key(markers[mi], oriented)
        ov = {go[r][c] for r, c in bcells}
        if len(ov) != 1:
            return False
        v = ov.pop()
        if v == b:                                 # body vanished entirely -> not a recolour dictionary
            return False
        if k in mapping and mapping[k] != v:
            return False
        mapping[k] = v
        bodyset |= bcells
    for mc in mcells:
        markset |= mc
    R, C = O.dims(gi)
    for r in range(R):                             # every non-body non-marker cell must be unchanged
        for c in range(C):
            if (r, c) in bodyset or (r, c) in markset:
                continue
            if go[r][c] != gi[r][c]:
                return False
    return True


def _apply_marker(g: Grid, body, marker, cfg, bgspec, mapping, oriented):
    """Apply a learned marker dictionary to a fresh grid: consume markers, recolour each body by its nearest
    marker's shape. Abstain (None) on an unseen marker shape or an ambiguous attachment."""
    b = _bg_of(g, bgspec)
    objs = O.segment(g, **cfg)
    bodies = [o for o in objs if o.primary_color == body]
    markers = [o for o in objs if o.primary_color == marker]
    if not bodies or not markers:
        return None
    mcells = [frozenset((r, c) for r, c, _ in o.pixels) for o in markers]
    out = [row[:] for row in g]
    for mc in mcells:
        for r, c in mc:
            out[r][c] = b
    for o in bodies:
        bcells = frozenset((r, c) for r, c, _ in o.pixels)
        mi = _nearest_marker(bcells, markers, mcells)
        if mi is None:
            return None
        k = _marker_key(markers[mi], oriented)
        if k not in mapping:
            return None
        for r, c, _ in o.pixels:
            out[r][c] = mapping[k]
    return out


def strat_attached_marker(train) -> "Program | None":
    """SAME-DIMS. Each body object carries its OWN nearby marker (a LOCAL legend, not a global one); the
    marker's shape names the object's recolour. Body + marker colours are the two CONSUMED colours (learned);
    the marker-shape->colour dictionary is learned ACROSS train and applied by nearest-marker lookup, markers
    consumed. Requires >=2 distinct marker keys (genuine shape-dependence, not a constant recolour). A novel
    marker shape or an ambiguous attachment at test -> ABSTAIN ([[ ]]). Propose-verify EXACT. No fabrication."""
    if not all(O.dims(gi) == O.dims(go) for gi, go in train):
        return None
    for bgspec in (0, None):
        van = sorted(_vanishing_colors(train, bgspec))
        if not (2 <= len(van) <= _MAX_VANISH):
            continue
        for body in van:
            for marker in van:
                if marker == body:
                    continue
                for conn in (8, 4):
                    for oriented in (False, True):     # exact-shape key (MDL-simpler) before D4-canonical
                        cfg = {"connectivity": conn, "by_color": True, "background": bgspec}
                        mapping: dict = {}
                        ok = True
                        for gi, go in train:
                            if not _learn_marker_pair(gi, go, body, marker, cfg, bgspec, oriented, mapping):
                                ok = False
                                break
                        if ok and len(mapping) >= 2:
                            def prog(g, _b=body, _m=marker, _c=cfg, _bg=bgspec,
                                     _map=dict(mapping), _o=oriented):
                                out = _apply_marker(g, _b, _m, _c, _bg, _map, _o)
                                return out if out is not None else [[]]
                            if _verify(prog, train):
                                return prog
    return None


# ================================================================ (3) PERIODIC-LATTICE legend-indexed recolour
def _lattice(g: Grid, latt: int, bg: int):
    """GRID-PERIODICITY INDUCTION. Detect a P x Q lattice of ONE repeated motif in colour `latt`: segment the
    lattice colour into connected motifs and require (i) >=4 motifs, (ii) all identical norm_shape, and (iii)
    their bbox origins forming a PERFECT P x Q grid (P,Q >= 2, distinct origins, P*Q == #motifs). Returns
    (motifs, tops, lefts) exposing the TILE INDEX (i,j)=(tops.index(top), lefts.index(left)) as a feature, or
    None. General exact-tile check (parameter-free); no period is hardcoded."""
    objs = [o for o in O.segment(g, connectivity=8, by_color=True, background=bg) if o.primary_color == latt]
    if len(objs) < _MIN_LATTICE:
        return None
    if len({o.norm_shape for o in objs}) != 1:
        return None
    tops = sorted({o.top for o in objs})
    lefts = sorted({o.left for o in objs})
    P, Q = len(tops), len(lefts)
    if P < 2 or Q < 2 or P * Q != len(objs):
        return None
    if len({(o.top, o.left) for o in objs}) != len(objs):
        return None
    return objs, tops, lefts


def _apply_periodic(g: Grid, latt: int, bgspec):
    """Recolour each lattice motif by a legend: the UNIQUE solid P x Q block sitting OUTSIDE the lattice bbox
    (non-bg, non-latt cells) is read as a P x Q colour table; motif at tile (i,j) -> block[i][j]. Abstain
    (None) if the lattice is not found or the legend block is not unique."""
    bg = _bg_of(g, bgspec)
    got = _lattice(g, latt, bg)
    if got is None:
        return None
    objs, tops, lefts = got
    P, Q = len(tops), len(lefts)
    R, C = O.dims(g)
    lt, ll = min(tops), min(lefts)
    lb = max(o.bottom for o in objs)
    lr = max(o.right for o in objs)
    blocks = []
    for r0 in range(R - P + 1):
        for c0 in range(C - Q + 1):
            if not (r0 > lb or r0 + P - 1 < lt or c0 > lr or c0 + Q - 1 < ll):   # overlaps lattice bbox
                continue
            cand, solid = [], True
            for i in range(P):
                row = []
                for j in range(Q):
                    v = g[r0 + i][c0 + j]
                    if v == bg or v == latt:
                        solid = False
                        break
                    row.append(v)
                if not solid:
                    break
                cand.append(row)
            if solid:
                blocks.append(cand)
                if len(blocks) > 1:
                    return None                    # legend must be UNIQUE (guards test false-fire)
    if len(blocks) != 1:
        return None
    block = blocks[0]
    out = [row[:] for row in g]
    for o in objs:
        i = tops.index(o.top)
        j = lefts.index(o.left)
        for r, c, _ in o.pixels:
            out[r][c] = block[i][j]
    return out


def strat_periodic_legend(train) -> "Program | None":
    """SAME-DIMS. The grid is a P x Q lattice of one repeated motif (colour = a CONSUMED colour, learned); a
    unique compact P x Q legend block elsewhere drives a TILE-INDEXED recolour (motif at tile (i,j) ->
    legend[i][j]). Grid-periodicity is induced per grid (_lattice), the legend located per grid, so the tiling
    and legend can differ in size/position between train and test. Propose-verify EXACT, else ABSTAIN ([[ ]])."""
    if not all(O.dims(gi) == O.dims(go) for gi, go in train):
        return None
    for bgspec in (0, None):
        for latt in sorted(_vanishing_colors(train, bgspec)):
            ok = True
            for gi, go in train:
                if _apply_periodic(gi, latt, bgspec) != go:
                    ok = False
                    break
            if ok:
                def prog(g, _l=latt, _bg=bgspec):
                    out = _apply_periodic(g, _l, _bg)
                    return out if out is not None else [[]]
                if _verify(prog, train):
                    return prog
    return None


# ================================================================ registry (MDL-ordered)
# Orientation dictionary (per-grid read, no cross-pair state) before the marker dictionary (cross-train
# learned) before the periodic-lattice recolour (most structural machinery). Each propose-verifies EXACT and
# abstains on its niche being absent, so ordering only affects which fires first when two somehow both verify.
APPLICATION_STRATEGIES = (
    strat_orient_shape_dict,
    strat_attached_marker,
    strat_periodic_legend,
)
