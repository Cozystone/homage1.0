# -*- coding: utf-8 -*-
"""Visual-KG anchoring + instance matching (Phase 4-4).

Anchoring: a MEASURED visual signature becomes knowledge-graph triples the
moment it exists — ()→[]→(), ()→[_]→(/),
()→[_]→( /) — each sourced to the photos that were
actually measured. The subject anchor is the concept the measurement was FOR,
so the wrong-page class of noise cannot enter here.

Instance matching: two signatures compared on what was actually measured
(bands/palette/luminance/edge). v0 verdicts are honest about their ceiling:
·· = " ", never " " (instance-level
identity needs the Ultimate depth/geometry track — 4-3).
"""
from __future__ import annotations

from typing import Any

_BRIGHT_HI, _BRIGHT_LO = 0.6, 0.35
_TEXTURE_HI = 0.5

# verdict thresholds on the 0..1 similarity (calibrated coarse — v0)
_SAME_KIND, _SIMILAR = 0.86, 0.70


def _color_word(rgb: list[float]) -> str:
    """Nearest coarse Korean color word (data rendered into words)."""
    palette = [
        ((0.85, 0.15, 0.15), "빨강"), ((0.9, 0.55, 0.1), "주황"), ((0.9, 0.85, 0.2), "노랑"),
        ((0.2, 0.7, 0.25), "초록"), ((0.15, 0.65, 0.65), "청록"), ((0.2, 0.35, 0.85), "파랑"),
        ((0.55, 0.25, 0.75), "보라"), ((0.9, 0.6, 0.7), "분홍"), ((0.5, 0.33, 0.2), "갈색"),
        ((0.55, 0.55, 0.55), "회색"), ((0.08, 0.08, 0.08), "검정"), ((0.95, 0.95, 0.95), "흰색"),
    ]
    best, name = 10.0, "무채색"
    for (r, g, b), n in palette:
        d = (r - rgb[0]) ** 2 + (g - rgb[1]) ** 2 + (b - rgb[2]) ** 2
        if d < best:
            best, name = d, n
    return name


def anchor_visual_triples(concept: str, scene: dict[str, Any] | None = None,
                          store: Any = None) -> dict[str, Any]:
    """Weave the measured signature into the KG as sourced triples. Returns the
    triples written (empty when there is no real measurement — nothing invented)."""
    if scene is None:
        from .visual_memory import recall_scene

        scene = recall_scene(concept)
    if not scene or not scene.get("bands"):
        return {"stored": 0, "triples": []}

    lum = float(scene.get("luminance") or 0.5)
    drift = float(scene.get("drift") or 0.0)
    palette = scene.get("palette") or []
    triples: list[tuple[str, str, str]] = []
    if palette:
        triples.append((concept, "주조색", _color_word(palette[0])))
    if lum > _BRIGHT_HI:
        triples.append((concept, "시각_밝기", "밝음"))
    elif lum < _BRIGHT_LO:
        triples.append((concept, "시각_밝기", "어두움"))
    triples.append((concept, "시각_질감", "결 많음" if drift > _TEXTURE_HI else "매끈함"))

    stored = 0
    try:
        if store is None:
            from packages.graph_scale.graph_paths import (
                VISUAL_PROPOSAL_FRAGMENT_ROOT,
            )
            from packages.graph_scale.triple_store import TripleStore

            store = TripleStore(VISUAL_PROPOSAL_FRAGMENT_ROOT)
        sid = store.intern_source("visual_measurement",
                                  ";".join((scene.get("sources") or [])[:3]))
        for s, p, o in triples:
            if store.add(s, p, o, source=sid):
                stored += 1
        store.flush()
    except Exception:
        return {"stored": 0, "triples": triples, "error": "store_unavailable"}
    return {"stored": stored, "triples": triples,
            "sources": (scene.get("sources") or [])[:3]}


def signature_similarity(sig_a: dict[str, Any], sig_b: dict[str, Any]) -> float:
    """0..1 similarity over what was MEASURED: band colors (composition),
    luminance, edge energy. Symmetric, bounded, no learned weights."""
    try:
        bands_a = [c for band in sig_a["bands"] for c in band]
        bands_b = [c for band in sig_b["bands"] for c in band]
        band_d = sum((a - b) ** 2 for a, b in zip(bands_a, bands_b)) / max(1, len(bands_a))
        lum_d = abs(float(sig_a.get("luminance", 0.5)) - float(sig_b.get("luminance", 0.5)))
        edge_d = abs(float(sig_a.get("edge_energy", 0.0)) - float(sig_b.get("edge_energy", 0.0)))
        # weighted distances -> similarity; bands dominate (composition identity)
        dist = band_d * 4.0 + lum_d * 0.5 + min(1.0, edge_d * 4.0) * 0.3
        return round(max(0.0, 1.0 - dist), 4)
    except Exception:
        return 0.0


def match_instance(concept_a: str, concept_b: str) -> dict[str, Any]:
    """The primitive's perception half: are these two visual memories the
 same KIND of thing? Honest verdict tiers; None-signature -> unknown."""
    from .visual_memory import _load

    rec_a, rec_b = _load(concept_a), _load(concept_b)
    if not rec_a or not rec_b:
        return {"verdict": "unknown", "score": None,
                "reason": "one or both concepts have no visual memory (측정 없음 — 판단 없음)"}
    score = signature_similarity(rec_a["signature"], rec_b["signature"])
    if score >= _SAME_KIND:
        verdict = "same_kind"
    elif score >= _SIMILAR:
        verdict = "similar"
    else:
        verdict = "different"
    return {
        "verdict": verdict, "score": score,
        "basis": {"a_photos": rec_a.get("images_measured"), "b_photos": rec_b.get("images_measured")},
        "honest_scope": "kind-level match from color/composition/texture; "
                        "instance identity needs depth geometry (Phase 4-3, Ultimate)",
    }
