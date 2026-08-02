# -*- coding: utf-8 -*-
"""User-state distiller — perception ONLY (owner's 2026-07-12 personalization directive).

The webcam is for the SELF, not the room: read how the user IS — glad, tired, changed — and turn
it into a distilled Observation (state concepts + an affective read). This module chooses NO action;
it only perceives. The context-affordance engine decides which path resonates. Nothing here stores
a frame — it takes an already-distilled face perception (or raw signals) and emits concepts.

The emotion→concept lines below are the layer (a surface translation of the recognition model's
own label, like the COCO→ map), plus affective coordinates for the particle channel — NOT a
behavioural condition. Fatigue/appearance signals come pre-distilled from the browser (eye-openness,
blink, a persistent signature drift on the SAME identity); we read them, never a frame.
"""
from __future__ import annotations

from typing import Any

from packages.affordance.context_affordance import Observation

# emotion label → (state concepts, valence, energy). Surface distillation of the model's output.
_EMOTION: dict[str, tuple[list[str], float, float]] = {
    "happy":    (["기쁨", "웃음", "밝음"], 0.8, 0.7),
    "surprise": (["놀람", "설렘"], 0.4, 0.8),
    "neutral":  (["평온", "차분"], 0.0, 0.4),
    "sad":      (["슬픔", "가라앉음"], -0.7, 0.3),
    "angry":    (["화남", "격앙"], -0.6, 0.8),
    "fear":     (["불안", "긴장"], -0.6, 0.7),
    "disgust":  (["불쾌"], -0.5, 0.5),
    "기쁨": (["기쁨", "웃음", "밝음"], 0.8, 0.7), "슬픔": (["슬픔", "가라앉음"], -0.7, 0.3),
}


def observe(*, emotion: str | None = None, eye_openness: float | None = None,
            blink_rate: float | None = None, yawning: bool = False,
            appearance_changed: bool = False, extra_concepts: list[str] | None = None,
            source: str = "face") -> Observation:
    """Distil raw/pre-distilled signals into one Observation. Every input is optional — perception
    is partial and honest (an unseen signal simply isn't claimed)."""
    concepts: list[str] = []
    valence, energy, n = 0.0, 0.5, 0

    emo = str(emotion or "").strip().lower()
    if emo in _EMOTION:
        cs, v, e = _EMOTION[emo]
        concepts += cs
        valence, energy, n = valence + v, e, 1

    # fatigue — from browser FaceLandmarker (eye aspect ratio / blink / yawn), never a frame
    tired = bool(yawning) or (eye_openness is not None and eye_openness < 0.45) or \
        (blink_rate is not None and blink_rate > 26)
    if tired:
        concepts += ["피곤", "졸림"]
        if eye_openness is not None and eye_openness < 0.45:
            concepts.append("눈감김")
        energy = min(energy, 0.25)
        valence -= 0.1

    # appearance drift on the SAME recognized person (re-recognition kernel applied to the self)
    if appearance_changed:
        concepts.append("외형변화")

    for c in (extra_concepts or []):
        if c and c not in concepts:
            concepts.append(str(c))

    return Observation(concepts=concepts, source=source,
                       valence=max(-1.0, min(1.0, valence)), energy=max(0.0, min(1.0, energy)),
                       note=emo or "")


def observe_from_faces(perception: dict[str, Any], *, extra_concepts: list[str] | None = None
                       ) -> Observation | None:
    """Bridge face_cortex.perceive() → an Observation about the (first recognized) user. Returns
    None when no face is present — nothing perceived, nothing claimed. Appearance-change is a
    conservative candidate: the person is KNOWN yet their familiarity is mid-band (recognized but
    notably drifted from their sharp signature) — a soft 'something's different', never a verdict."""
    faces = perception.get("faces") or []
    if not faces:
        return None
    f = next((x for x in faces if x.get("identity")), faces[0])
    fam = float(f.get("familiarity") or 0.0)
    changed = bool(f.get("identity")) and 0.62 <= fam < 0.74     # known, but drifted — a soft flag
    return observe(emotion=f.get("emotion"), appearance_changed=changed,
                   extra_concepts=extra_concepts, source="face")
