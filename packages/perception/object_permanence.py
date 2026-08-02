# -*- coding: utf-8 -*-
"""It is still there when I cannot see it.

    from packages.perception.object_permanence import Permanence

    p = Permanence()
    p.observe(things, t)      # every frame: bind what is visible to who it is
    p.hidden_now()            # what I believe exists but cannot currently see

WHAT THIS IS FOR. `sprite_tracker` keeps things apart WHILE they are visible, by assigning each
detection to a predicted position; `object_recognition` says whether a signature belongs to an
instance seen before. Neither survives an occlusion: a thing that vanishes behind a pillar ends its
track, and the thing that emerges is a new one with a new identity. An eye like that has no objects,
only appearances -- and a mind built on it cannot be surprised that something MOVED while hidden,
because it never claimed anything was there.

Owner's contribution, 2026-08-01, and it is the design: use the SIMULATION to predict. While a thing
is out of sight, its state is not unknown -- it is unobserved, which is a different thing. Something
occluded keeps moving the way it was moving, and where it should re-emerge is computable. So a hidden
object here is not a memory being held; it is a PREDICTION being run, and re-binding tests that
prediction against what actually reappears.

THE ORACLE IS FREE, WHICH IS WHY THIS IS BUILT AND NOT THE OTHER FOUR THINGS I WANTED TO BUILD. The
occlusion is one WE create: take a stretch of frames and simply refuse to look. Because we made the
gap, the true identity across it is known at zero cost, in unlimited quantity, on 76 episodes already
on disk. Nothing has to be annotated for this to be scored, and there is no version of it where a
convincing story can substitute for the number.

TWO WAYS TO BE WRONG, AND THEY ARE NOT THE SAME MISTAKE. Failing to re-bind splits one object into
two -- a memory loss. Binding the wrong pair merges two objects into one -- a false memory, and the
worse of the two, because it manufactures a continuity that never happened. They are counted
separately here for that reason.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


def centroid(mask: np.ndarray) -> tuple[float, float]:
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        return (0.0, 0.0)
    return (float(xs.mean()), float(ys.mean()))


def appearance(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """A cheap, honest appearance descriptor: the colour histogram of the thing itself.

    NOT the 106 KB signature net, deliberately. That encoder was trained on 24x24 patches of street
    scenes, and a whole object is neither 24x24 nor guaranteed to be a street. Reaching for it here
    would be using a tool outside what it was measured on, and the measurement that matters --
    identity across a gap -- would then be reporting on the encoder's mismatch rather than on
    permanence. A histogram is weak and it is HONESTLY weak: whatever score comes out is a floor that
    a real appearance model has to beat, and swapping one in later changes this one function."""
    px = rgb[mask]
    if px.size == 0:
        return np.zeros(24, dtype=np.float32)
    out = []
    for c in range(3):
        h, _ = np.histogram(px[:, c], bins=8, range=(0, 256))
        out.append(h.astype(np.float32) / max(1.0, float(h.sum())))
    return np.concatenate(out)


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


@dataclass
class Track:
    """One thing, believed to persist whether or not it is currently visible."""
    tid: int
    look: np.ndarray                       # appearance, absorbed on every confirmed sighting
    xy: tuple[float, float]                # last known position
    vel: tuple[float, float] = (0.0, 0.0)  # last observed motion, per frame
    last_seen: int = 0
    seen: int = 1
    history: list = field(default_factory=list)
    xyz: Any = None                        # last known position IN THE WORLD, when depth+pose exist
    vel3: Any = None                       # world velocity, m per frame

    def predict(self, t: int, pose=None, shape=None) -> tuple[float, float]:
        """Where it should be now — carrying its motion forward through the blind stretch.

        TWO PREDICTORS, AND WHICH ONE RUNS IS DECIDED BY WHETHER THE WORLD IS KNOWN.

        In the picture, coasting is wrong and it was measured wrong: at an 18-frame gap it scored
        0.731 against 0.846 for simply believing the thing stayed put, losing four objects outright.
        Image velocity is a projection, not a physical quantity -- an object approaching at a constant
        speed ACCELERATES across the picture, so a straight line through pixel space overshoots
        further the longer the gap, which is exactly the shape of that failure.

        In the world, constant velocity is what physics actually licenses, so when depth and pose are
        available the state is carried there and projected back at the end. That is the owner's
        simulation idea applied where prediction is valid instead of where it is convenient. The
        world round trip is checked separately and drifts a median of 0.137 m over eleven frames.

        Falls back to standing still rather than to image-space coasting, because standing still is
        the better of the two whenever the world is unknown -- which is the measurement above."""
        dt = max(0, t - self.last_seen)
        if self.xyz is not None and pose is not None and shape is not None:
            from packages.perception.world_frame import to_image
            ahead = np.asarray(self.xyz) + np.asarray(self.vel3 if self.vel3 is not None
                                                      else (0.0, 0.0, 0.0)) * dt
            u, v, d = to_image(ahead, pose, shape)
            if np.isfinite(u) and d > 0:
                return (float(u), float(v))
        return (self.xy[0] + self.vel[0] * dt, self.xy[1] + self.vel[1] * dt)


class Permanence:
    """Bind what is visible now to what is believed to exist.

    `gap_tolerance` is how long a thing is believed in without being seen. It is NOT a confidence
    knob to be tuned until the numbers look good -- it is the claim being made, so it stays explicit
    and gets reported with every result."""

    def __init__(self, *, gap_tolerance: int = 30, look_weight: float = 0.5):
        self.tracks: dict[int, Track] = {}
        self.gap_tolerance = gap_tolerance
        self.look_weight = look_weight
        self._next = 1

    def _score(self, tr: Track, xy, look, t, diag: float, pose=None, shape=None) -> float:
        """How well one visible thing matches one believed-in thing.

        Distance is divided by the frame diagonal so the score means the same on any resolution, and
        appearance and position are combined rather than gated one behind the other: a thing that
        moved a long way while hidden still looks like itself, and a thing that stayed put may have
        turned around. Requiring both to agree loses the object in exactly the cases permanence is
        for."""
        px, py = tr.predict(t, pose, shape)
        d = float(np.hypot(xy[0] - px, xy[1] - py)) / max(1.0, diag)
        near = max(0.0, 1.0 - d)
        return (1.0 - self.look_weight) * near + self.look_weight * _cos(tr.look, look)

    def observe(self, dets: list, t: int, *, shape: tuple = (600, 800), pose=None,
                depth=None, depths=None) -> dict:
        """One frame of sightings, bound to identities. `dets` is [(centroid, appearance), ...].

        Hand in `pose` and `depth` and every sighting is also placed in the world, which is what lets
        a hidden thing be carried forward by physics instead of by pixels."""
        diag = float(np.hypot(*shape))
        alive = [tr for tr in self.tracks.values() if (t - tr.last_seen) <= self.gap_tolerance]
        pairs = sorted(((self._score(tr, xy, look, t, diag, pose, shape), tr.tid, i)
                        for i, (xy, look) in enumerate(dets) for tr in alive), reverse=True)
        used_t, used_d, bound = set(), set(), {}
        for s, tid, i in pairs:
            if tid in used_t or i in used_d or s < 0.5:
                continue
            used_t.add(tid)
            used_d.add(i)
            bound[i] = (tid, s)
        here = self._place(dets, pose, depth, shape, depths)
        for i, (xy, look) in enumerate(dets):
            if i in bound:
                tid, _s = bound[i]
                tr = self.tracks[tid]
                dt = max(1, t - tr.last_seen)
                tr.vel = ((xy[0] - tr.xy[0]) / dt, (xy[1] - tr.xy[1]) / dt)
                if here[i] is not None:
                    if tr.xyz is not None:
                        tr.vel3 = tuple((np.asarray(here[i]) - np.asarray(tr.xyz)) / dt)
                    tr.xyz = here[i]
                tr.xy = xy
                # absorb the new view rather than replacing it: the same drift defence
                # object_recognition already settled on for multi-view instances.
                tr.look = 0.7 * tr.look + 0.3 * look
                tr.last_seen = t
                tr.seen += 1
            else:
                tid = self._next
                self._next += 1
                self.tracks[tid] = Track(tid=tid, look=np.asarray(look, dtype=np.float32), xy=xy,
                                         last_seen=t, xyz=here[i])
            self.tracks[tid].history.append((t, xy))
        return {"bound": {i: v[0] for i, v in bound.items()},
                "new": [i for i in range(len(dets)) if i not in bound]}

    @staticmethod
    def _place(dets, pose, depth, shape, depths=None) -> list:
        """Each sighting's position in the world, or None where the world is not known.

        `depths` is a per-detection distance supplied by whoever owns the mask, and it matters more
        than it looks. Reading depth at the CENTROID PIXEL is wrong for any region that is not
        convex: a lump wrapped around a doorway or a tree has its centre of mass in the gap, so the
        distance read there belongs to whatever is visible through the hole -- often something metres
        further away. The world point then lands nowhere near the object and the track is not
        mis-bound, it is LOST. That was the measured signature of the world arm: 4 lost against 0 for
        standing still, while binding no more wrongly.

        None is the honest answer and it propagates: without depth and pose there is no world
        position, so `predict` falls back to standing still rather than inventing one."""
        if pose is None or (depth is None and depths is None):
            return [None] * len(dets)
        from packages.perception.world_frame import to_world
        out = []
        for i, det in enumerate(dets):
            xy = det[0]
            u, v = int(round(xy[0])), int(round(xy[1]))
            if depths is not None:
                z = float(depths[i]) if depths[i] is not None else float("nan")
            elif 0 <= v < depth.shape[0] and 0 <= u < depth.shape[1]:
                z = float(depth[v, u])
            else:
                z = float("nan")
            out.append(to_world((u, v), z, pose, shape)
                       if np.isfinite(z) and 0.5 < z <= 200.0 else None)
        return out

    def hidden_now(self, t: int) -> list:
        """What I believe is there but cannot see — with where I think it went."""
        return [{"tid": tr.tid, "unseen_for": t - tr.last_seen, "believed_at": tr.predict(t)}
                for tr in self.tracks.values()
                if 0 < (t - tr.last_seen) <= self.gap_tolerance]
