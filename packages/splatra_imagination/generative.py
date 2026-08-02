# -*- coding: utf-8 -*-
"""Generative particle synthesis — ANY concept gets its OWN form, unlimited.

Replaces the old path (hash(concept) -> pick 1 of 9 hand-coded archetypes) with
true generation: a concept's form is SYNTHESISED from its own signature — the
shape of its knowledge (graph degree, is-a hierarchy, part-of clustering,
relation diversity) plus, when available, its phase-space vector. The signature
drives a 3D Gielis SUPERSHAPE (superformula), a continuous space of endlessly
varied organic/geometric forms, so there is no fixed vocabulary of shapes: every
concept maps to a distinct, reproducible, animated particle body.

No LLM, no image model. Pure math from the concept's structure. Deterministic per
concept (same concept -> same form) yet unbounded across concepts.
"""
from __future__ import annotations

import colorsys
import hashlib
import math
import random
from typing import Any

from packages.splatra_turbovec.models import Particle

from .generator import deterministic_seed

_BOX = 1.7  # fit forms inside the imagination box


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def concept_signature(concept: str, graph_features: dict[str, Any] | None = None,
                      phase_vec: list[float] | None = None) -> list[float]:
    """A stable 8-float signature in [0,1] for a concept. Deterministic from the
    concept string, then BENT by the concept's real knowledge structure so the
    form reflects meaning, not just a hash."""
    digest = hashlib.sha256(concept.strip().lower().encode("utf-8")).digest()
    sig = [digest[i] / 255.0 for i in range(8)]
    gf = graph_features or {}
    degree = _clamp(float(gf.get("degree", 0)) / 40.0, 0.0, 1.0)          # richness
    parts = _clamp(float(gf.get("part_of", 0)) / 12.0, 0.0, 1.0)          # lobes/clusters
    rel_div = _clamp(float(gf.get("relation_types", 0)) / 10.0, 0.0, 1.0) # symmetry variety
    is_a = 1.0 if gf.get("is_a") else 0.0                                 # verticality
    # fold structure in (keep determinism; structure only shifts the hash base)
    sig[0] = 0.5 * sig[0] + 0.5 * rel_div     # -> m1 (primary lobe count)
    sig[3] = 0.5 * sig[3] + 0.5 * degree      # -> form complexity
    sig[4] = 0.5 * sig[4] + 0.5 * parts       # -> m2 (secondary lobes)
    sig[6] = 0.5 * sig[6] + 0.5 * is_a        # -> verticality bias
    if phase_vec:  # optional learned semantic coordinates
        for i, v in enumerate(phase_vec[:8]):
            sig[i] = 0.6 * sig[i] + 0.4 * ((math.tanh(float(v)) + 1.0) / 2.0)
    return [_clamp(s, 0.0, 1.0) for s in sig]


def _superformula(angle: float, m: float, n1: float, n2: float, n3: float) -> float:
    """Gielis superformula radius at `angle`. The continuous knob of form."""
    t = m * angle / 4.0
    a = abs(math.cos(t)) ** n2
    b = abs(math.sin(t)) ** n3
    s = a + b
    if s <= 1e-9:
        return 0.0
    return s ** (-1.0 / n1)


def _params(sig: list[float]) -> tuple[float, ...]:
    """Signature -> two superformula profiles (latitude, longitude)."""
    m1 = 2.0 + round(sig[0] * 10.0)          # 2..12 primary lobes
    n11 = 0.3 + sig[1] * 6.0
    n12 = 0.3 + sig[2] * 6.0
    n13 = 0.3 + sig[3] * 6.0
    m2 = 1.0 + round(sig[4] * 8.0)           # 1..9 secondary lobes
    n21 = 0.3 + sig[5] * 6.0
    n22 = 0.3 + sig[6] * 6.0
    n23 = 0.3 + sig[7] * 6.0
    return (m1, n11, n12, n13, m2, n21, n22, n23)


def synthesize_form(concept: str, *, count: int = 2200,
                    controls: dict[str, float] | None = None,
                    graph_features: dict[str, Any] | None = None,
                    phase_vec: list[float] | None = None) -> list[Particle]:
    """Synthesise a concept's particle body on a 3D supershape surface. Colours
    come from the signature; velocities give a live rotation + breathing so the
    form is animated, not static."""
    controls = controls or {}
    sig = concept_signature(concept, graph_features, phase_vec)
    m1, n11, n12, n13, m2, n21, n22, n23 = _params(sig)
    rng = random.Random(deterministic_seed(f"generative:{concept}"))

    count = max(200, min(6000, int(count)))
    lat = max(14, int(math.sqrt(count / 1.7)))
    lon = max(14, int(count / lat))

    raw: list[tuple[float, float, float]] = []
    max_ext = 1e-6
    for i in range(lat):
        theta = -math.pi / 2.0 + math.pi * (i / (lat - 1))
        r1 = _superformula(theta, m1, n11, n12, n13)
        for j in range(lon):
            phi = -math.pi + 2.0 * math.pi * (j / (lon - 1))
            r2 = _superformula(phi, m2, n21, n22, n23)
            x = r1 * math.cos(theta) * r2 * math.cos(phi)
            y = r1 * math.sin(theta)
            z = r1 * math.cos(theta) * r2 * math.sin(phi)
            raw.append((x, y, z))
            max_ext = max(max_ext, abs(x), abs(y), abs(z))

    scale = _BOX / max_ext
    base_hue = sig[0]
    sat = 0.45 + 0.4 * sig[2]
    spin = 0.006 + 0.01 * float(controls.get("arousal", sig[5]))
    breathe = 0.004 + 0.008 * float(controls.get("curiosity", sig[3]))
    emotion = float(controls.get("valence", 0.0)) * 0.5 + 0.5

    particles: list[Particle] = []
    for (x, y, z) in raw:
        x *= scale; y *= scale; z *= scale
        # colour: hue drifts with height so the body reads as a gradient
        h = (base_hue + 0.16 * (y / _BOX) + 0.08 * sig[4]) % 1.0
        val = 0.55 + 0.4 * _clamp(0.5 + 0.5 * (y / _BOX), 0.0, 1.0)
        r, g, b = colorsys.hsv_to_rgb(h, sat, val)
        # velocity: rotate about Y + gentle radial breathing (alive)
        vx = -z * spin + x * breathe * 0.4
        vz = x * spin + z * breathe * 0.4
        vy = y * breathe * 0.4
        jitter = 0.01
        particles.append(Particle(
            x=_clamp(x + (rng.random() - 0.5) * jitter, -1.95, 1.95),
            y=_clamp(y + (rng.random() - 0.5) * jitter, -1.95, 1.95),
            z=_clamp(z + (rng.random() - 0.5) * jitter, -1.95, 1.95),
            vx=vx, vy=vy, vz=vz,
            r=_clamp(r, 0, 1), g=_clamp(g, 0, 1), b=_clamp(b, 0, 1),
            a=0.82, radius=0.011, material_id="generative_form",
            emotion_weight=_clamp(emotion, 0, 1),
            audio_reactive_weight=_clamp(float(controls.get("speaking_energy", 0.0)), 0, 1),
        ))
    return particles


def form_descriptor(concept: str, graph_features: dict[str, Any] | None = None,
                    phase_vec: list[float] | None = None) -> dict[str, Any]:
    """Honest metadata: what drove this form (so the render is explainable, not
    a black box)."""
    sig = concept_signature(concept, graph_features, phase_vec)
    m1, n11, n12, n13, m2, n21, n22, n23 = _params(sig)
    return {
        "concept": concept,
        "grounded": bool(graph_features) or bool(phase_vec),
        "primary_lobes": int(m1),
        "secondary_lobes": int(m2),
        "complexity": round(sig[3], 3),
        "signature": [round(s, 3) for s in sig],
        "note": "supershape synthesised from the concept's own graph signature; "
                "no LLM, no image model — deterministic + unlimited",
    }
