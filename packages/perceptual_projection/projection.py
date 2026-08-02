# -*- coding: utf-8 -*-
"""Perceptual projection — the Scalability Wall's cornerstone.

The owner's diagnosis (2026-07-09): our 25.9M clean triples are still closer to
a great encyclopedia than to the ocean of commonsense a brain or a frontier LLM
compresses. Scaling the graph is one axis; the OTHER is PROJECTION — mapping
the world's micro-nuances and non-text modalities (vision, audio) INTO this
single rigid geometry so they become the same kind of citable knowledge.

This module is the contract + a working v0 of that projection. It does NOT try
to learn perception from scratch; it PROJECTS an external feature vector
(produced by any encoder — a vision model, an audio model, or our own visual_kg
signature) onto the graph's concept manifold, and — critically — it OBEYS the
house law: a projection is only accepted when it ANCHORS to a verified concept
above a similarity floor. Below the floor, it abstains ("perceived something I
cannot ground") instead of hallucinating a label. Perception thus enters the
graph as a CANDIDATE observation with its anchor and confidence, gated exactly
like every other new knowledge — never as a silent fact.

Two projection backends, same interface:
  * embedding projection — cosine to concept anchor vectors (learned or given);
  * symbolic-signature projection — reuses perception.visual_kg's color/shape
    signature match, so it works today with zero trained weights.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

Vector = Sequence[float]


@dataclass
class Projection:
    """The result of grounding a percept into the graph."""
    anchored: bool
    concept: str | None
    confidence: float
    modality: str
    candidates: list[tuple[str, float]] = field(default_factory=list)

    def as_observation(self, source: str = "perception") -> dict[str, Any] | None:
        """A CANDIDATE observation triple for the evidence gate — or None when
        unanchored (honest abstention). Perception never writes a fact directly."""
        if not self.anchored or not self.concept:
            return None
        return {"triple": ("percept", "instance_of", self.concept),
                "confidence": round(self.confidence, 4),
                "modality": self.modality, "source": f"{source}:{self.modality}",
                "status": "candidate",
                "note": "perceptual projection — must pass the evidence gate "
                        "before promotion, like any candidate"}


def _cos(a: Vector, b: Vector) -> float:
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def project_embedding(feature: Vector, anchors: dict[str, Vector], *,
                      modality: str = "vision", floor: float = 0.55,
                      margin: float = 0.04) -> Projection:
    """Project a feature vector onto concept ANCHOR vectors by cosine.
    ANCHORS THEN VERIFIES: accept the top concept only if it clears the floor
    AND beats the runner-up by `margin` (an ambiguous percept between two
    concepts abstains rather than guessing one). `anchors` maps concept ->
    vector; in production these are the phase-space vectors of grounded
    concepts, so vision lands in the SAME geometry as text."""
    if not anchors:
        return Projection(False, None, 0.0, modality)
    scored = sorted(((c, _cos(feature, v)) for c, v in anchors.items()),
                    key=lambda t: -t[1])
    top_c, top_s = scored[0]
    second_s = scored[1][1] if len(scored) > 1 else -1.0
    anchored = top_s >= floor and (top_s - second_s) >= margin
    return Projection(anchored, top_c if anchored else None,
                      float(top_s), modality, scored[:5])


def project_signature(scene: dict[str, Any], concept_signatures: dict[str, dict],
                      *, modality: str = "vision", floor: float = 0.6) -> Projection:
    """Zero-weight projection: reuse visual_kg's symbolic signature similarity
    (color + shape + size) to anchor a perceived scene to a known concept.
    Works today without any trained embedding."""
    try:
        from packages.perception.visual_kg import signature_similarity
    except Exception:
        return Projection(False, None, 0.0, modality)
    scored = sorted(((c, signature_similarity(scene, sig))
                     for c, sig in concept_signatures.items()),
                    key=lambda t: -t[1])
    if not scored:
        return Projection(False, None, 0.0, modality)
    top_c, top_s = scored[0]
    anchored = top_s >= floor
    return Projection(anchored, top_c if anchored else None,
                      float(top_s), modality, scored[:5])


def phase_space_anchors(concepts: Sequence[str],
                        vector_of: Callable[[str], Vector | None]) -> dict[str, Vector]:
    """Build the anchor table from the trained phase space: the concept's own
    RotatE-lite vector IS its anchor, so a projected percept lands next to the
    text concepts it resonates with — one geometry for symbols and senses."""
    anchors: dict[str, Vector] = {}
    for c in concepts:
        v = vector_of(c)
        if v is not None:
            anchors[c] = v
    return anchors
