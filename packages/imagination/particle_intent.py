# -*- coding: utf-8 -*-
"""Particle intent — the AI's OWN hands on the particle space (owner's binding directive).

" ( ) AI ." So beyond compiling a
concept into a scene, ATANOR has a RAW expressive channel over the whole field: it can set the mood,
energy, colour, motion, density and focus of the particles directly — an inner state made visible,
not a preset. The aquarium polls this and applies it over whatever it is showing.

This is a control surface, not knowledge: valence→hue, energy→speed/motion is presentation mapping
(the same license the physics-motion renderer has). The AI may also set any field DIRECTLY (full
manual control) — `from_state` is just one convenience producer. Stale intent fades (TTL), so the
field returns to rest when the mind goes quiet — expression, not a stuck filter.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_PATH = Path(__file__).resolve().parents[2] / "data" / "imagination" / "particle_intent.json"

_MOTIONS = ("gather", "disperse", "spiral", "pulse", "drift", "rise", "fall", "orbit")


def _clamp(v: float, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except Exception:
        return lo


def set_particle_intent(*, valence: float = 0.0, energy: float = 0.5, hue: float | None = None,
                        motion: str | None = None, density: float = 0.6,
                        focus: list[float] | None = None, note: str = "",
                        source: str = "ai") -> dict[str, Any]:
    """The AI drives the field. Every field is optional and clamped; the AI can express through the
    affective coordinates (valence/energy) or seize any channel directly (hue, motion, focus)."""
    intent: dict[str, Any] = {
        "valence": _clamp(valence, -1.0, 1.0),
        "energy": _clamp(energy, 0.0, 1.0),
        "density": _clamp(density, 0.0, 1.0),
        "note": str(note or "")[:200],
        "source": str(source or "ai")[:40],
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "ts": time.time(),
    }
    if hue is not None:
        intent["hue"] = _clamp(hue, 0.0, 360.0)
    if motion in _MOTIONS:
        intent["motion"] = motion
    if focus and len(focus) == 2:
        intent["focus"] = [_clamp(focus[0], -1.0, 1.0), _clamp(focus[1], -1.0, 1.0)]
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(intent, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return intent


def get_particle_intent(max_age_s: float = 30.0) -> dict[str, Any] | None:
    """The aquarium polls this. None when there is no fresh intent — the field rests."""
    try:
        intent = json.loads(_PATH.read_text(encoding="utf-8"))
        if time.time() - float(intent.get("ts", 0)) <= max_age_s:
            return intent
    except Exception:
        pass
    return None


def clear_particle_intent() -> None:
    try:
        _PATH.unlink()
    except Exception:
        pass


def from_state(concepts: list[str], *, valence: float = 0.0, energy: float = 0.5,
               note: str = "", source: str = "state") -> dict[str, Any]:
    """One convenience producer: turn an affective read of a perceived state into a field intent.
    Presentation mapping only — valence warms the hue (cool blue → the warm ATANOR amber), energy
    picks the field's motion and speed. The AI can always override any of these directly."""
    v = _clamp(valence, -1.0, 1.0)
    e = _clamp(energy, 0.0, 1.0)
    hue = 210.0 - (v + 1.0) / 2.0 * (210.0 - 35.0)       # −1→blue(210)  +1→amber(35)
    if e >= 0.7:
        motion = "pulse" if v >= 0 else "disperse"
    elif e <= 0.3:
        motion = "gather" if v >= 0 else "drift"
    else:
        motion = "spiral"
    density = 0.4 + 0.5 * e
    return set_particle_intent(valence=v, energy=e, hue=hue, motion=motion, density=density,
                               note=note or ("·".join(concepts[:4])), source=source)
