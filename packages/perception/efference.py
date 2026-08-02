# -*- coding: utf-8 -*-
"""Know that you moved, so you can tell your own motion from the world's.

Owner, 2026-07-29: pan 문제 계속 파봐. 몸이 움직인 걸 아는 쪽으로. 최대한 스스로 깨우치는 쪽으로.

The `pan` case is where the event segmenter breaks, and the reason is precise. When the view drifts
across a scene, content enters at the leading edge and leaves at the trailing edge — which is
exactly the two-directional signature that means "this was replaced". So the cue cannot tell "the
world changed" from "I moved across it", and no threshold repairs that, because the two produce the
same measurement.

Nothing IN THE IMAGE separates them. What separates them is knowing whether you moved, and that is
information the image does not contain and the body does.

CORRELLARY DISCHARGE, which is what animals do about this. A copy of every motor command is sent to
the sensory side, which uses it to cancel the sensory change the command was going to cause. It is
why the world does not appear to lurch when the eyes saccade, and why one cannot tickle oneself: the
self-caused part of the sensation is predicted away, and only the unpredicted remainder is felt.
Here it is the same computation for the same reason.

THE PREDICTION IS THE ONE ATANOR LEARNED BY MOVING, not one written down. `packages/hand/babble.py`
already measured what each command does to the image — `w` expands the view, `mouse+x` slides it
left, `space` does nothing — by pressing keys and watching, with nobody supplying the meanings. That
record IS the forward model. So this reads the body schema and uses it, and if the game were rebound
tomorrow, babbling again would repair this too, with no line here changing.

THE GATE IS THE COMMAND, NOT THE IMAGE, and that is the whole of what the first attempt got wrong.
Estimating the shift from the picture and subtracting it improved the panning case a little (1.7x to
2.0x chance) and WRECKED the case with no motion in it (1.000 to 0.692), because a shift estimated
where there is none is a shift invented. Compensating only when the body reports having moved cannot
do that: no command, no correction, and the still case is untouched by construction.

IT IS UNTESTED, NOT VALIDATED, AND THE REASON IS IN THE FOOTAGE RATHER THAN THE IDEA. Two captures
were made to test it and neither produced self-motion a shift model can follow. Measured global shift
over 0.45 seconds, by regime:

    capture 1 (mouse 260 per 50ms)   still 0.00   travel 0.01   turn_left +0.02   turn_right +0.01
    capture 2 (mouse 45 per 100ms)   still 0.00   travel -0.04  turn_left +0.07   turn_right -0.02

Turning left and turning right should be large and opposite. They are neither, and phase-correlation
confidence during turns is 0.25-0.29 against 0.99 while standing still. Meanwhile the raw pixel
difference during a turn is 27.6 against 1.2 for standing still — so a great deal changed and none of
it was a translation. That is what a camera spinning far enough to leave the scene entirely looks
like: 0.45s at one turn command per 0.10s is roughly 200 mouse counts, and the two views have almost
nothing in common. No shift model bridges unrelated images, which is why every gain calibrated to
zero, and a `mouse+x` gain of 8.0 — the top of the grid, so it wanted more still — made the residual
WORSE (0.0217 -> 0.0247).

So the standing verdict is that the mechanism is built and its calibration is honest, and the footage
to test it on does not exist yet. Saying it does not work would overclaim in the other direction.

A DEFECT IN THE EYE, FOUND HERE AND LARGER THAN THIS EXPERIMENT. The second capture dropped 21,156
duplicate frames out of roughly 24,800 the eye reported as FRESH — 85%. Desktop Duplication reports
that the desktop changed, not that the watched window did, so the freshness flag has been counting
frames that carry no new content. Every rate this session has quoted through that flag is inflated by
it: the first long capture's "87 fps" was about 20 fps of actual content.

WHAT IS NOT CLAIMED. This is a subtraction using a measured forward model. It is the mechanism
behind a well-known perceptual fact, and having the mechanism is not having the fact — nothing here
licenses any claim about what anything is like from the inside.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class BodyModel:
    """What ATANOR found out its own commands do to what it sees.

    Loaded from the babbling record. `dx`, `dy` and `div` are the measured optical-flow signature of
    holding that command, in the units `flow_signature` reports."""

    effects: dict[str, dict[str, float]] = field(default_factory=dict)

    @classmethod
    def from_schema(cls, path: str | Path) -> "BodyModel":
        s = json.loads(Path(path).read_text(encoding="utf-8"))
        eff = {}
        for key, v in (s.get("moves") or {}).items():
            if v.get("mag", 0) < 0.5:
                continue                       # measured to do nothing; nothing to cancel
            eff[key] = {"dx": float(v.get("dx", 0.0)), "dy": float(v.get("dy", 0.0)),
                        "div": float(v.get("div", 0.0)), "mag": float(v.get("mag", 0.0))}
        return cls(effects=eff)

    def expects(self, command: str) -> dict[str, float] | None:
        """What the image should do if this command is being held. None when it has never been felt."""
        return self.effects.get(command)

    def knows(self) -> list[str]:
        return sorted(self.effects)


def _shift(img: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """Move an image by a sub-pixel amount, replicating at the edge."""
    import cv2
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), borderMode=cv2.BORDER_REPLICATE)


def _scale(img: np.ndarray, k: float) -> np.ndarray:
    """Zoom about the centre — what moving along the view axis does."""
    import cv2
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), 0.0, k)
    return cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REPLICATE)


@dataclass
class Efference:
    """Cancel the sensory change a command was going to cause, and report what is left."""

    body: BodyModel
    gain: float = 1.0                 # how much of the schema's flow to apply, per unit hold
    _cal: dict[str, float] = field(default_factory=dict)

    def predict(self, prev: np.ndarray, command: str | None) -> np.ndarray:
        """What the previous view should look like AFTER this command, if the world stayed still."""
        if not command:
            return prev
        e = self.body.expects(command)
        if e is None:
            return prev                        # never felt this command; predict nothing, cancel nothing
        g = self.gain * self._cal.get(command, 1.0)
        out = prev
        if abs(e["dx"]) > 0.05 or abs(e["dy"]) > 0.05:
            out = _shift(out, e["dx"] * g, e["dy"] * g)
        if abs(e["div"]) > 0.05:
            # expansion means things closed in: the previous frame magnified slightly
            out = _scale(out, 1.0 + 0.01 * e["div"] * g)
        return out

    def residual(self, prev: np.ndarray, cur: np.ndarray, command: str | None) -> dict[str, float]:
        """What the world did, once what the body did has been taken out.

        `replaced` is the two-directional part — content gone AND content arrived — measured against
        the PREDICTED previous view rather than the actual one. That is the whole point: under a
        pure pan the prediction already contains the new leading edge, so nothing reads as replaced.
        """
        from packages.perception.attention import frame_signature

        pred = self.predict(prev, command)
        a, b = frame_signature(pred), frame_signature(cur)
        d = b - a
        arrived = float(np.maximum(d, 0).mean())
        departed = float(np.maximum(-d, 0).mean())

        raw = frame_signature(prev)
        rd = b - raw
        return {"replaced": min(arrived, departed),
                "replaced_uncompensated": min(float(np.maximum(rd, 0).mean()),
                                              float(np.maximum(-rd, 0).mean())),
                "residual": float(np.abs(d).mean()),
                "self_caused": float(np.abs(a - raw).mean()),
                "commanded": bool(command and self.body.expects(command))}

    def calibrate(self, samples: list[tuple[np.ndarray, np.ndarray, str]],
                  grid: tuple[float, ...] = (0.0, 0.5, 1.0, 2.0, 4.0, 8.0)) -> dict[str, float]:
        """Find, per command, how strongly to apply the schema — BY TRYING IT AND LOOKING.

        The body schema records flow in the units of a 96x72 block search over a particular hold
        time; the frames here are a different size and the commands are held for however long they
        were held. Rather than convert between those by arithmetic that would encode assumptions,
        each command's gain is the one that MINIMISES the leftover residual on frames where that
        command was actually being held. If cancelling helps, the best gain is above zero and this
        finds it; if it does not, the best gain is zero and the correction switches itself off —
        which is the honest outcome and needs no separate decision.
        """
        from packages.perception.attention import frame_signature
        by_cmd: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {}
        for prev, cur, cmd in samples:
            if cmd and self.body.expects(cmd):
                by_cmd.setdefault(cmd, []).append((prev, cur))

        cal: dict[str, float] = {}
        for cmd, pairs in by_cmd.items():
            best_g, best_err = 0.0, None
            for g in grid:
                self._cal[cmd] = g
                errs = []
                for prev, cur in pairs[:60]:
                    p = self.predict(prev, cmd)
                    errs.append(float(np.abs(frame_signature(cur) - frame_signature(p)).mean()))
                e = float(np.mean(errs)) if errs else float("inf")
                if best_err is None or e < best_err:
                    best_g, best_err = g, e
            cal[cmd] = best_g
            self._cal[cmd] = best_g
        return cal


def narrate(res: dict[str, Any], command: str | None, body: BodyModel) -> str:
    """One sentence about what just happened, built only from numbers that were measured.

    THIS SHOULD FEED `packages/inner_voice` RATHER THAN BE A SECOND VOICE. That organ already exists,
    with its construction inventory, its safety flags and its forbidden-phrase list, and it is not
    wired to any of the perception organs — the built-but-unwired pathology this repository has
    catalogued nine times. This function is the perceptual state rendered as a sentence; the wiring
    to the existing voice is owed and is named here so it is not quietly forgotten.

    Every clause is traceable to a value in `res`. Nothing is composed for effect, and there is no
    branch that produces a confident sentence when the numbers are uncertain — the abstaining case
    says so. A narration that could say something the measurements do not support would be theatre,
    and would be worse than no narration because it would read as understanding."""
    if not res.get("commanded"):
        if command:
            return f"I did '{command}' but I have never felt what that does, so I cannot tell what was me."
        return ("Nothing of mine moved, so all of this change is the world's: "
                f"{res['replaced']:.4f} replaced.")
    kept = res["replaced"]
    before = res["replaced_uncompensated"]
    drop = 1.0 - (kept / before) if before > 1e-9 else 0.0
    if drop > 0.25:
        return (f"I did '{command}'. That accounts for {drop:.0%} of what looked like the world "
                f"changing ({before:.4f} -> {kept:.4f} after taking my own motion out).")
    # NOT "so this change was not mine". Failing to cancel has two causes that this measurement
    # cannot tell apart: the change really was the world's, or the forward model for this command is
    # wrong at this timescale. The first live run said "so this change was not mine" while ATANOR was
    # turning — the change was entirely its own and the model was simply failing. A narration that
    # draws a conclusion the numbers do not support is worse than none, because it reads as
    # understanding.
    return (f"I did '{command}' and taking it out did not help ({before:.4f} -> {kept:.4f}). "
            f"Either that change was the world's, or I do not yet know what '{command}' does over "
            f"this long a moment.")
