# -*- coding: utf-8 -*-
"""V7-1 — does behaviour-derived geometry SURVIVE projection into the hyperdimensional space?

Axis v7 §3, rung two, and the first rung where FHRR itself is the claim rather than the setting.
V7-0 showed the geometry exists in a sparse named-predicate basis. That basis is not a substrate:
its dimensions are predicate names, so two domains with different predicates share nothing. The
whole point of a hyperdimensional space is that everything lands in the SAME fixed-width vector,
which is what gives transfer a channel at all.

THE PROJECTION, and why it is the natural one rather than a choice. An entity's behaviour is a
distribution over predicates; FHRR's own primitive for "a bundle of weighted parts" is superposition
of role atoms. So the entity's hypervector is the share-weighted superposition of its predicate
atoms. No binding partner is invented, no role vocabulary is authored -- the predicate IS the role,
which is exactly the occupancy condition §6 fixed before any of this was built.

THE CONTROL IS WHAT `fhrr_core` DOES TODAY: the same atoms, superposed WITHOUT the behaviour
weights. That is not an arbitrary bad baseline -- it is the current system, an entity reduced to
which predicates it has and not how it distributes over them. If the unweighted version scores as
well, the weights carried nothing and the axis gained nothing by moving to hyperdimensions.

PRE-REGISTERED BEFORE THE FIRST RUN: mean top-3 neighbour overlap >= 0.5 against the sparse-basis
ranking, AND strictly above the unweighted control. Written here so it cannot be adjusted to
whatever the measurement returns.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from packages.substrate.behaviour import Behaviour, distance

OVERLAP_GATE = 0.5
TOP_K = 3


def project(b: Behaviour, basis: Sequence[str], *, weighted: bool = True):
    """Share-weighted superposition of the entity's predicate atoms.

    `weighted=False` is the control: the current `fhrr_core` behaviour, where an entity is the set
    of predicates it has and the distribution over them is discarded."""
    import numpy as np

    from packages.vsa_reasoning.fhrr_core import atom

    acc = None
    for p in basis:
        w = b.shares.get(p, 0.0)
        if w <= 0.0:
            continue
        v = atom(p) * (w if weighted else 1.0)
        acc = v if acc is None else acc + v
    if acc is None:
        return None
    norm = np.linalg.norm(acc)
    return acc / norm if norm > 0 else acc


def holo_distance(a, b) -> float:
    """1 - similarity, on the real part of the Hermitian inner product. Phasor atoms are complex,
    so the plain dot product is not a similarity and taking its magnitude would discard the sign
    that makes opposition different from orthogonality."""
    import numpy as np

    if a is None or b is None:
        return 1.0
    return float(1.0 - np.real(np.vdot(a, b)))


def _rank(items: Sequence[str], dists: dict[tuple[str, str], float], k: int) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for x in items:
        others = sorted((y for y in items if y != x),
                        key=lambda y: dists[(x, y)] if (x, y) in dists else dists[(y, x)])
        out[x] = others[:k]
    return out


@dataclass(frozen=True)
class ProjectionReading:
    entities: int
    basis_size: int
    overlap: float
    control_overlap: float
    top_k: int = TOP_K
    gate: float = OVERLAP_GATE
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        """Both halves. The absolute bar says the projection preserved the structure; beating the
        control says the BEHAVIOUR WEIGHTS are what preserved it, rather than the predicate set
        alone -- which the current system already has and which produced no generality."""
        return self.overlap >= self.gate and self.overlap > self.control_overlap

    def as_dict(self) -> dict[str, Any]:
        return {"entities": self.entities, "basis": self.basis_size, "top_k": self.top_k,
                "overlap": round(self.overlap, 4), "control_overlap": round(self.control_overlap, 4),
                "gate": self.gate, "passed": self.passed, "notes": list(self.notes)}


def read_projection(behaviours: Sequence[Behaviour], basis: Sequence[str], *,
                    k: int = TOP_K) -> ProjectionReading:
    """Compare nearest-neighbour rankings: sparse basis against the hyperdimensional projection."""
    names = [b.entity for b in behaviours]
    by = {b.entity: b for b in behaviours}

    sparse = {(x, y): distance(by[x], by[y], basis)
              for i, x in enumerate(names) for y in names[i + 1:]}
    sparse_rank = _rank(names, sparse, k)

    def _overlap(weighted: bool) -> float:
        vecs = {n: project(by[n], basis, weighted=weighted) for n in names}
        hd = {(x, y): holo_distance(vecs[x], vecs[y])
              for i, x in enumerate(names) for y in names[i + 1:]}
        hd_rank = _rank(names, hd, k)
        hits = [len(set(sparse_rank[n]) & set(hd_rank[n])) / float(k) for n in names]
        return sum(hits) / len(hits) if hits else 0.0

    return ProjectionReading(
        entities=len(names), basis_size=len(basis),
        overlap=_overlap(True), control_overlap=_overlap(False), top_k=k,
        notes=("control is the current fhrr_core behaviour: same atoms, no behaviour weights",))
