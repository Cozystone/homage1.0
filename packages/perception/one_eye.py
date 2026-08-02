# -*- coding: utf-8 -*-
"""One eye. One residual. Two readings. Nothing selected by hand.

Owner, 2026-07-29: 인간은 그 두가지를 하는 눈이 똑같지 않나? 사람 눈이 보는 방식을 모방한
아키텍처로 해. 지금 그런 상태인가?

It was not, and this file is the repair. Three signals had accumulated — raw change, prediction
error, replacement — and each testbed was reported with whichever of them did best on it. Divisive
normalisation was applied where it helped (CARLA) and not where it hurt (explainer pans), with no
principle saying which. That is a mode switch assembled one measurement at a time, and it is the
thing this project keeps refusing to build.

THEY WERE NEVER THREE RULES. Each is a residual against a different prediction, read in one of two
ways:

    raw change         prediction: nothing changes        reading: magnitude
    prediction error   prediction: change continues       reading: magnitude
    replacement        prediction: nothing changes        reading: directionality

So the architecture is one prediction and one residual, read two ways — and both readings are
always produced, because they answer different questions and neither is a better version of the
other. Magnitude says HOW MUCH was unexplained. Directionality says whether what was left is
one-sided (something arrived and everything stayed) or two-sided (something went AND something
came), which is the difference between a thing appearing and a scene being replaced.

THE PREDICTION USES WHATEVER IS AVAILABLE, WHICH IS NOT A SWITCH. In order:

    0  the previous view                       always available
    1  extrapolated by how it has been moving  once there are two views
    2  and displaced by what MY OWN command    only when a command was issued and its effect
       is known to do                          has been felt before

Level 2 is not another mode. It is an input that is sometimes zero, and when it is zero the
computation degrades to level 1 with nothing rearranged — exactly as an animal does. A person
watching a film has no efference copy for the CAMERA's motion either, which is why sitting still in a
cinema can feel like moving. That failure of the panning case is not a shortfall against human
vision; it is the same limitation human vision has, and people resolve it with cues this does not
have yet — scene rigidity, recognising objects, knowing it is a screen.

GAIN CONTROL IS ALWAYS ON, not applied where it flatters. The residual is divided by how much
actually changed, so it reads as the FRACTION that was unexpected. Measured, that removed a confound
worth removing (correlation with sheer speed fell from +0.685 to +0.091) and cost accuracy elsewhere
(explainer pans, 0.808 to 0.692). Both readings are reported so the cost is visible rather than
hidden by turning it off where it hurts.

WHAT WOULD FALSIFY THE UNIFICATION. If one always-on rule scores materially worse than the
hand-picked best on each testbed, then the three were doing different jobs and merging them lost
something. `scripts/one_eye_check.py` measures exactly that, on every testbed at once.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .attention import frame_signature


@dataclass
class Reading:
    """What one moment gave, after the best available prediction was subtracted."""

    magnitude: float          # how much was unexplained, as a fraction of what changed
    directionality: float     # how much of the residual was two-sided — replaced rather than added
    change: float             # how much the view changed at all
    self_explained: float     # how much of the change the body's own command accounted for
    level: int                # which prediction was available: 0, 1 or 2

    def as_dict(self) -> dict[str, Any]:
        return {"magnitude": round(self.magnitude, 5),
                "directionality": round(self.directionality, 5),
                "change": round(self.change, 5),
                "self_explained": round(self.self_explained, 4), "level": self.level}


@dataclass
class OneEye:
    """The whole of it. Feed frames; optionally say what command was being held."""

    efference: Any = None                 # packages.perception.efference.Efference, or None
    _prev: np.ndarray | None = None       # previous raw frame (for the efference warp)
    _codes: list[np.ndarray] = field(default_factory=list)
    log: list[Reading] = field(default_factory=list)

    def look(self, rgb: np.ndarray, command: str | None = None) -> Reading:
        code = frame_signature(rgb)

        # --- the prediction, at the best level available -----------------------------------------
        level = 0
        pred = code if not self._codes else self._codes[-1]
        if len(self._codes) >= 2:
            level = 1
            pred = self._codes[-1] + (self._codes[-1] - self._codes[-2])
        if (self.efference is not None and command and self._prev is not None
                and self.efference.body.expects(command) is not None):
            # Level 2 replaces the prediction rather than adjusting it: the body's forward model
            # already says where everything went, so extrapolating on top would count the motion
            # twice.
            level = 2
            pred = frame_signature(self.efference.predict(self._prev, command))

        d = code - pred
        arrived = float(np.maximum(d, 0).mean())
        departed = float(np.maximum(-d, 0).mean())
        residual = float(np.abs(d).mean())

        last = self._codes[-1] if self._codes else code
        change = float(np.abs(code - last).mean())
        # gain control, always on: the fraction of the change that was not expected
        magnitude = residual / (change + 1e-4)
        directionality = min(arrived, departed) / (change + 1e-4)

        self_explained = 0.0
        if level == 2:
            naive = float(np.abs(code - last).mean())
            self_explained = max(0.0, 1.0 - residual / (naive + 1e-9))

        self._codes.append(code)
        if len(self._codes) > 4:
            self._codes.pop(0)
        self._prev = rgb

        r = Reading(magnitude=magnitude, directionality=directionality, change=change,
                    self_explained=self_explained, level=level)
        self.log.append(r)
        return r

    # --- the two readings, as sequences ------------------------------------------------------------
    def magnitudes(self) -> list[float]:
        return [r.magnitude for r in self.log]

    def directionalities(self) -> list[float]:
        return [r.directionality for r in self.log]

    def combined(self) -> list[float]:
        """One number per moment, for callers that want a single boundary signal.

        The PRODUCT, not a weighted sum. A weighting would be another dial with no principle behind
        it, and the two readings are not substitutes: a boundary is where a lot was unexplained AND
        what was left was a replacement rather than an addition. Either alone fires on things that
        are not boundaries — magnitude on any fast moment, directionality on any flicker — and the
        product is high only when both hold."""
        return [r.magnitude * r.directionality for r in self.log]
