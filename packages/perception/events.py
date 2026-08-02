# -*- coding: utf-8 -*-
"""Cut time where prediction breaks. The unit abstraction works over.

Owner, 2026-07-29: 인간의 가장 놀라운 능력은 영상을 보는 것이 아니라, 몇 분짜리 영상에서 얻은 정보를
바탕으로 눈앞에 없는 세계의 작동 원리를 머릿속에 시뮬레이션할 수 있다는 점 ... 핵심은 구체적인 사례 →
일반 원리로 압축하는 추상화 능력일까?

Abstraction is the right target and it needs a unit to abstract OVER. "Concrete instance -> general
principle" requires instances, and a video is not a sequence of instances, it is a sequence of
frames. Frames are the wrong grain: at 30fps a five-minute video is nine thousand of them and almost
every one is its neighbour. Nothing general can be found by comparing near-duplicates.

WHAT PEOPLE ACTUALLY DO, and it is measurable rather than metaphorical. Continuous activity is parsed
into discrete EVENTS automatically and involuntarily, and the boundaries fall where the viewer's
ongoing prediction fails (Zacks & Tversky's event segmentation theory; boundary judgements are
reliable across observers, and prediction-error spikes precede them). "He picks up the cup" is one
event because throughout it the next moment follows from the last; the boundary is where that stops
being true.

That gives the unit. An event is a stretch over which one description keeps working, so events are
exactly the things that CAN be compared to each other, and comparing them is where a general
principle would come from.

THE SAME MACHINERY THE EYE ALREADY HAS. `packages/eye/fovea.py` moves the fixation to where its
prediction failed. This is that signal integrated over time instead of space, which is the reason to
build it here rather than as a separate video organ: attention and event segmentation are one
quantity read at two scales, and a system with two unrelated surprise measures would have to keep
them consistent by hand.

WHAT THIS IS NOT. It does not name events, group them, or say what happened. It says WHERE the
description had to change. Naming and generalising come after, and both need this first.

WHERE THIS STANDS, MEASURED ON CARLA AGAINST THE VEHICLE'S OWN POSE — real event boundaries being
where the motion regime changes, derived from pose and never from the image:

                              raw residual      normalised
    correlation with SPEED    +0.685 (97%)      +0.091 (60%)     <- the confound, removed
    boundary recall           0.171             0.243
    chance recall             0.129             0.090
    beat chance in            32% of episodes   55% of episodes

So the normalisation did its job on the confound and only part of its job on the target: recall went
from 1.3x chance to 2.7x, and still only half of episodes beat chance. The correlation with
acceleration also went NEGATIVE (-0.234), which says the division over-corrects — acceleration
enlarges the denominator as well as the residual, so some genuine signal leaves with the confound.
A predictor that models acceleration rather than dividing it out is the obvious next form.

ON A PROPER TESTBED IT IS STILL WEAK, and that replaced the 40-frame excuse rather than confirming
it. `scripts/citysample_long_capture.py` records minutes of footage while ATANOR itself issues the
motor commands, so the frame each regime change happened on is WRITTEN DOWN rather than inferred from
pose by thresholding -- 21,032 frames, 240 seconds, 67 boundaries, no parameters in the answer key.
On the first 9,000 frames, 30 true boundaries:

    raw change          recall 0.733   chance 0.572   1.3x    82 found
    prediction error    recall 0.933   chance 0.659   1.4x   103 found
    replacement         recall 0.867   chance 0.587   1.5x    87 found

All three around 1.4x chance, all firing three times too often. High recall with three times too many
boundaries is not segmentation, it is a low threshold, and the chance column is what makes that
visible.

GENERATED EXPLAINER FOOTAGE IS MUCH EASIER AND I SHOULD NOT HAVE GENERALISED FROM IT. On
`scripts/make_explainer_testbed.py` the same code scores 5.4-5.5x chance with EXACTLY the right
number of boundaries. Real footage of a body moving through a 3D city is a different problem: a
command changing from travel to still does not produce a sharp visual change, because momentum
carries the view on and the scene keeps rendering. The visual signature of an intention changing is
faint, and that is the honest reason this is hard rather than a threshold not yet found.

THE PREDICTOR IS DELIBERATELY WEAK. A constant-velocity model on the retinal code: expect the scene
to keep changing the way it has been. Weak on purpose, because a strong learned predictor would make
the boundaries depend on what it happened to be trained on, and the first question is whether
prediction failure marks boundaries AT ALL. It also sets the floor a learned predictor has to beat.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class Boundary:
    """A moment where the description stopped working."""

    index: int
    surprise: float
    ratio: float            # how far above the running level it stood

    def as_dict(self) -> dict[str, Any]:
        return {"index": self.index, "surprise": round(self.surprise, 5),
                "ratio": round(self.ratio, 3)}


@dataclass
class EventStream:
    """Running segmentation of a sequence into events."""

    codes: list[np.ndarray] = field(default_factory=list)
    errors: list[float] = field(default_factory=list)
    replaced: list[float] = field(default_factory=list)   # how much of the old view GAVE WAY

    def push(self, code: np.ndarray) -> float:
        """Feed the next frame's code; return how surprising it was.

        CONSTANT VELOCITY, not constant state. Predicting "the next frame looks like this one" makes
        every moment of steady motion a surprise, so a camera panning smoothly would be chopped into
        boundaries all the way along — which is precisely the failure that would make the measure
        useless on video, where something is nearly always moving. Extrapolating the change instead
        means smooth motion is EXPECTED and costs nothing, and the surprise falls where the motion
        itself changes."""
        if len(self.codes) < 2:
            self.codes.append(code)
            self.errors.append(0.0)
            self.replaced.append(0.0)
            return 0.0
        a, b = self.codes[-2], self.codes[-1]
        pred = b + (b - a)
        raw = float(np.abs(code - pred).mean())

        # DIVIDED BY HOW MUCH ACTUALLY HAPPENED, and this is the difference between measuring events
        # and measuring speed. The raw residual scales with the amount of motion, so a fast steady
        # stretch produces a large error throughout while being entirely predictable. Measured on
        # CARLA against the vehicle's own pose, the raw version correlated with SPEED at rho +0.685,
        # positive in 97% of episodes, and with the change of motion regime at only +0.254 — it was
        # a speedometer wearing the name `surprise`.
        #
        # The quantity that means "unexpected" is the FRACTION of the change that was not predicted.
        # Steady motion, however fast, is mostly predicted and scores low; a turn beginning is not,
        # and scores high regardless of how fast it was going. This is divisive normalisation, which
        # is a canonical cortical computation and is here for the reason it is there: a residual is
        # only interpretable relative to the expectation it departs from.
        change = float(np.abs(code - b).mean())
        err = raw / (change + 1e-4)

        # REPLACEMENT, NOT ADDITION — the cue that separates a new topic from a new bullet point.
        #
        # An explainer builds a slide up element by element, and every arrival is a large pixel
        # change that is NOT a boundary. Measured on generated explainer footage, prediction error
        # alone fired 38.5 times against 13 true boundaries: it found every sub-step and could not
        # tell them from the topic changes.
        #
        # What distinguishes them is direction. While a topic is being built, content only ARRIVES:
        # the code moves one way and what was already there stays. When the topic changes, the old
        # content GOES and new content arrives, so the code moves both ways at once. So the quantity
        # is the smaller of the two directions — near zero for anything additive, large only when
        # something was genuinely replaced.
        #
        # This is not a heuristic about slides. Occlusion, a cut, a scene change and a page turn are
        # all replacements; a thing appearing, growing or being pointed at are all additions. The
        # distinction is about whether the previous description survives.
        d = code - b
        arrived = float(np.maximum(d, 0).mean())
        departed = float(np.maximum(-d, 0).mean())
        self.replaced.append(min(arrived, departed))

        self.codes.append(code)
        self.errors.append(err)
        if len(self.codes) > 8:                 # only the last two are used; do not hold a video
            self.codes.pop(0)
        return err


def boundaries(errors: list[float] | np.ndarray, *, window: int = 15,
               ratio: float = 1.8, min_gap: int = 8) -> list[Boundary]:
    """Local peaks in prediction error, judged against the LOCAL level rather than a global one.

    Against a global threshold, a busy stretch of video produces boundaries continuously and a quiet
    stretch produces none, so the segmentation would track how eventful the footage is rather than
    where its events begin. A running median makes the question "did prediction get worse than it has
    been around here", which is the question that means something.

    `min_gap` enforces that events have duration. Without it a single hard moment yields a burst of
    adjacent boundaries and the same instant is counted several times."""
    e = np.asarray(errors, dtype=np.float64)
    if len(e) < window + 2:
        return []

    # A FLOOR UNDER THE BASELINE, and its absence made this blind to the easiest case there is.
    # A slide held still gives literally identical frames, so the running median is exactly zero —
    # and the first version skipped whenever that happened, on the reasoning that a ratio needs a
    # denominator. But a zero baseline is not missing information, it is the strongest possible
    # information: prediction was perfect, so ANY error is a departure. Skipping it meant the
    # detector found zero boundaries in a slide deck with hard cuts between slides, which is the
    # case it should be most certain about. It reported nothing at all and looked like it had simply
    # been run on unsuitable data.
    #
    # The floor is a fraction of the sequence's own typical error, so it carries no absolute scale
    # and means the same thing on any footage.
    nz = e[e > 1e-12]
    floor = float(np.median(nz)) * 0.05 if len(nz) else 1e-9

    out: list[Boundary] = []
    last = -10 ** 9
    for i in range(window, len(e)):
        local = e[max(0, i - window):i]
        base = max(float(np.median(local)), floor, 1e-12)
        r = e[i] / base
        if r < ratio or i - last < min_gap:
            continue
        # a peak, not a rising edge: the point itself must be the local maximum
        hi = min(len(e), i + min_gap // 2)
        if e[i] < e[i:hi].max():
            continue
        out.append(Boundary(index=i, surprise=float(e[i]), ratio=float(r)))
        last = i
    return out


def alignment(found: list[int], truth: list[int], tol: int = 6,
              n_frames: int = 0, rng=None, trials: int = 200) -> dict[str, Any]:
    """Do the found boundaries land on the real ones — more than the same number would by chance?

    THE CONTROL IS THE MEASUREMENT. Any set of boundaries hits some true ones if there are enough of
    both, so a raw hit rate says nothing. The same COUNT of boundaries, placed at random in the same
    sequence, is what the real ones must beat, and this reports both plus how often the real set won
    across repeated draws."""
    if not found or not truth:
        return {"recall": None, "reason": "nothing to compare"}
    t = np.asarray(sorted(truth))

    def _recall(bs) -> float:
        if not len(bs):
            return 0.0
        hit = sum(1 for x in t if np.min(np.abs(np.asarray(bs) - x)) <= tol)
        return hit / len(t)

    real = _recall(found)
    n_frames = n_frames or int(max(max(found), t.max()) + 1)
    rng = rng or np.random.default_rng(0)
    null = [_recall(rng.integers(0, n_frames, size=len(found))) for _ in range(trials)]
    null = np.asarray(null)
    return {"recall": round(real, 4),
            "chance_recall": round(float(null.mean()), 4),
            "beats_chance_p": round(float((null >= real).mean()), 4),
            "found": len(found), "true": len(t), "tol_frames": tol}
