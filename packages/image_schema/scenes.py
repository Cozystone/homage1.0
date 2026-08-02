# -*- coding: utf-8 -*-
"""Two worlds, one schema. The adapters that make the basis domain-blind, and the proof that it is.

A schema is only a primitive if the same instance runs unchanged over a symbolic narrative world and
over pixels. If PROXIMITY needs one implementation for Sandra-in-the-office and another for a sprite in
a maze, it is not a primitive, it is two rules with a shared name.

So there are exactly two adapters here and no schema logic whatsoever. Each answers what its domain can
answer and returns None for the rest — `SymbolicScene` has no metric, `MetricScene` has no rooms — and
the schemas abstain accordingly instead of inventing a measurement.
"""
from __future__ import annotations

import math
from typing import Any


class SymbolicScene:
    """A narrative world: places, holders, adjacency. Wraps what StateTracker already tracks.

    No metric exists here, so `distance` answers only along the place graph, in hops."""

    def __init__(self, at: dict, holder: dict | None = None, adj: dict | None = None,
                 present: set | None = None):
        self._at = dict(at or {})
        self._holder = dict(holder or {})
        self._adj = {k: list(v) for k, v in (adj or {}).items()}
        self._present = set(present or self._at)

    def participants(self) -> list[str]:
        return sorted(set(self._at) | set(self._holder) | self._present)

    def at(self, entity: str) -> str | None:
        return self._at.get(entity)

    def holder(self, item: str) -> str | None:
        return self._holder.get(item)

    def exists(self, entity: str) -> bool | None:
        return entity in self._present

    def inside(self, figure: str, container: str) -> bool | None:
        a = self._at.get(figure)
        return None if a is None else (a == container)

    def touching(self, a: str, b: str) -> bool | None:
        x, y = self._at.get(a), self._at.get(b)
        return None if (x is None or y is None) else (x == y)

    def blocked(self, figure: str, goal: str) -> bool | None:
        return None                                   # a narrative world has no obstruction facts

    def scale(self) -> float:
        return 1.0                                    # one hop

    def distance(self, a: str, b: str) -> float | None:
        """Hops along the place graph. None when the two are not connected by known places."""
        s, g = self._at.get(a) or a, self._at.get(b) or b
        if s == g:
            return 0.0
        if not self._adj:
            return None
        seen, frontier, d = {s}, [s], 0
        while frontier and d < 24:
            d += 1
            nxt = []
            for p in frontier:
                for q in self._adj.get(p, []):
                    q = q[0] if isinstance(q, (tuple, list)) else q
                    if q == g:
                        return float(d)
                    if q not in seen:
                        seen.add(q)
                        nxt.append(q)
            frontier = nxt
        return None


class MetricScene:
    """A world with positions. Pixels, metres, joint angles — the adapter does not care which.

    `scale` is MEASURED from the scene rather than chosen, so a degree means the same thing in a
    160-pixel maze and in a room in metres."""

    def __init__(self, pos: dict[str, Any], carried: dict | None = None,
                 radius: float | None = None, walls=None, scale: float | None = None):
        self._pos = {k: (float(v[0]), float(v[1])) for k, v in pos.items() if v is not None}
        self._carried = dict(carried or {})
        self._walls = walls
        self._radius = radius
        self._scale = scale

    def participants(self) -> list[str]:
        return sorted(self._pos)

    def distance(self, a: str, b: str) -> float | None:
        p, q = self._pos.get(a), self._pos.get(b)
        if p is None or q is None:
            return None
        return math.hypot(p[0] - q[0], p[1] - q[1])

    def scale(self) -> float:
        """The typical separation, DERIVED once and then carried.

        Recomputing it per scene silently cancelled the thing being measured: with two participants
        the scale equals their distance, so `degree` came out 0.5 whichever way the figure moved, and
        with five it drifted as the scene did -- so predicted futures were being compared under
        DIFFERENT normalisations. A comparison needs one ruler. `choose()` fixes it from the present
        scene and hands it to every rollout."""
        if self._scale is not None:
            return self._scale
        ps = list(self._pos.values())
        if len(ps) < 2:
            return 1.0
        ds = [math.hypot(a[0] - b[0], a[1] - b[1])
              for i, a in enumerate(ps) for b in ps[i + 1:]]
        ds.sort()
        return max(ds[len(ds) // 2], 1e-6)

    def inside(self, figure: str, container: str) -> bool | None:
        if self._radius is None:
            return None
        d = self.distance(figure, container)
        return None if d is None else (d <= self._radius)

    def touching(self, a: str, b: str) -> bool | None:
        if self._radius is None:
            return None
        d = self.distance(a, b)
        return None if d is None else (d <= self._radius)

    def holder(self, item: str) -> str | None:
        return self._carried.get(item)

    def at(self, entity: str) -> str | None:
        return None                                   # no named places in a metric world

    def exists(self, entity: str) -> bool | None:
        return entity in self._pos

    def blocked(self, figure: str, goal: str) -> bool | None:
        if self._walls is None:
            return None
        p, q = self._pos.get(figure), self._pos.get(goal)
        if p is None or q is None:
            return None
        H, W = self._walls.shape
        for t in range(1, 9):                          # sample the straight line between them
            x = int(round(p[0] + (q[0] - p[0]) * t / 9.0))
            y = int(round(p[1] + (q[1] - p[1]) * t / 9.0))
            if 0 <= y < H and 0 <= x < W and not self._walls[y, x]:
                return True
        return False

class RegionScene:
    """A world of REGIONS rather than points: elements with extent, which is what a designed surface is.

    The third adapter, and it earns its place by answering a question the other two cannot. SymbolicScene
    has places and no metric; MetricScene has positions and no extent; a nav item is part of a nav bar
    because of AREA overlap, and neither of the others can express that.

    Boxes are (x0, y0, x1, y1). Nothing here knows what a nav bar is, or that this is a web page: the
    adapter answers geometry and the schemas do the rest."""

    def __init__(self, boxes: dict, attrs: dict | None = None):
        self._box = {k: tuple(float(v) for v in b) for k, b in boxes.items()}
        self._attrs = dict(attrs or {})

    # ---------------------------------------------------------------- geometry
    def _centre(self, k):
        b = self._box.get(k)
        return None if b is None else ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)

    def _area(self, k) -> float:
        b = self._box.get(k)
        return 0.0 if b is None else max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])

    def _overlap(self, a, b) -> float:
        p, q = self._box.get(a), self._box.get(b)
        if p is None or q is None:
            return 0.0
        w = max(0.0, min(p[2], q[2]) - max(p[0], q[0]))
        h = max(0.0, min(p[3], q[3]) - max(p[1], q[1]))
        return w * h

    def subsumption(self, part: str, whole: str) -> float | None:
        """Fraction of the PART's area that lies inside the WHOLE's. The PART_WHOLE gradient."""
        if part not in self._box or whole not in self._box:
            return None
        if part == whole:
            return 1.0
        a = self._area(part)
        return 0.0 if a <= 0 else self._overlap(part, whole) / a

    # ---------------------------------------------------------------- the Scene protocol
    def participants(self) -> list[str]:
        return sorted(self._box)

    def distance(self, a: str, b: str) -> float | None:
        p, q = self._centre(a), self._centre(b)
        if p is None or q is None:
            return None
        return math.hypot(p[0] - q[0], p[1] - q[1])

    def scale(self) -> float:
        """The typical element size, so a degree means the same thing on a phone and on a billboard."""
        sizes = [math.sqrt(self._area(k)) for k in self._box if self._area(k) > 0]
        if not sizes:
            return 1.0
        sizes.sort()
        return max(sizes[len(sizes) // 2], 1e-6)

    def inside(self, figure: str, container: str) -> bool | None:
        v = self.subsumption(figure, container)
        return None if v is None else v > 0.9

    def touching(self, a: str, b: str) -> bool | None:
        if a not in self._box or b not in self._box:
            return None
        return self._overlap(a, b) > 0.0

    def holder(self, item: str) -> str | None:
        return self._attrs.get(item, {}).get("holder")

    def at(self, entity: str) -> str | None:
        return None

    def exists(self, entity: str) -> bool | None:
        return entity in self._box

    def blocked(self, figure: str, goal: str) -> bool | None:
        return None
