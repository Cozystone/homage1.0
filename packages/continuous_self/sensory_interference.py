# -*- coding: utf-8 -*-
"""Multi-sensory interference reception (Phase 3-7, Qualia seed 2).

The owner's frame: a subjective impression is what happens when a raw sensory
wave hits the accumulated knowledge field and INTERFERES with it. This v0
receives a MEASURED visual signature (color/luminance/texture from real
photos) and lets it strike the trained phase space:

 impression("") ->
 tone/brightness/texture — read off the measured signature (the wave)
 evoked — what the knowledge field resonates back
 (cross-domain phase neighbors = )
 felt — one grounded sentence of inner speech
 arousal — a bounded dopamine nudge when the encounter
 resonates strongly (aesthetic pleasure seed)

Nothing here fabricates: no measurement -> no impression; no resonance -> the
evoked list is simply empty.
"""
from __future__ import annotations

from typing import Any

_AROUSAL_RESONANCE = 0.6   # evoked resonance above this counts as a "strike"
_AROUSAL_PULSE = 0.15      # bounded dopamine nudge per aesthetic strike


def _tone(palette: list[list[float]]) -> str:
    """warm/cool from the measured dominant color — data into words."""
    if not palette:
        return "무채"
    r, g, b = palette[0]
    if r > b + 0.08:
        return "따뜻한"
    if b > r + 0.08:
        return "차가운"
    return "중성의"


def impression_from_visual(concept: str, state: Any = None) -> dict[str, Any] | None:
    """One felt moment: the measured look of the concept striking the knowledge
    field. Optionally nudges the homeostasis dopamine level on a strong strike
    (controlled trembling — sensory channel only, per the Qualia principle)."""
    try:
        from packages.perception.visual_memory import recall_scene
    except Exception:
        return None
    scene = recall_scene(concept)
    if not scene or not scene.get("bands"):
        return None  # no measurement -> no impression

    lum = float(scene.get("luminance") or 0.5)
    drift = float(scene.get("drift") or 0.0)
    tone = _tone(scene.get("palette") or [])
    brightness = "밝은" if lum > 0.6 else ("어두운" if lum < 0.35 else "은은한")
    texture = "결이 많은" if drift > 0.5 else "매끈한"


    evoked: list[dict[str, Any]] = []
    try:
        from packages.graph_scale.phase_space import neighbors

        for term, res in neighbors(concept, k=20):
            if res < _AROUSAL_RESONANCE or term == concept:
                continue
            if concept in term or term in concept:
                continue
            evoked.append({"term": term, "resonance": round(res, 3)})
            if len(evoked) >= 3:
                break
    except Exception:
        evoked = []

    felt = f"{concept}의 인상 — {tone} 빛, {brightness} {texture} 결."
    if evoked:
        felt += f" 마음속에서 {evoked[0]['term']}이(가) 함께 울린다."

    arousal = 0.0
    if evoked and state is not None:
        # aesthetic strike: a real measured encounter that the field answers —
        # a small dopamine pulse through the SENSORY channel only
        try:
            from .homeostasis import _levels

            h = _levels(state)
            arousal = _AROUSAL_PULSE
            h["dopamine"] = round(min(1.0, float(h.get("dopamine", 0.0)) + arousal), 5)
        except Exception:
            arousal = 0.0

    return {
        "concept": concept,
        "tone": tone, "brightness": brightness, "texture": texture,
        "evoked": evoked,
        "felt": felt,
        "arousal": arousal,
        "measured_from": scene.get("measured_from"),
        "sources": (scene.get("sources") or [])[:3],
        "basis": "measured_signature x trained_phase_field",
    }
