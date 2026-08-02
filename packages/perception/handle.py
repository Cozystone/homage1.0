# -*- coding: utf-8 -*-
"""The handle — the whole of what vision owes the rest of the mind.

Owner, 2026-07-29, on why a person seeing a parked car reads intent and ownership from it: vision
does not do that in people either. "Someone left it there" comes from already knowing about people,
streets and intention. What vision delivers is *a persisting thing, over there, that I have or have
not met before* — and everything else attaches from the knowledge side.

So this is not a summary of the perception work; it is its OUTPUT TYPE, and naming it is what
dissolved most of the engineering trouble. Three fields, and a boundary is not among them:

    persistence      this is the same thing it was a moment ago      -> a track
    location         where it is relative to me                      -> ordinal depth + image position
    identity         have I met this before                          -> re-identification

NO MASK. A whole session was spent building masks and scoring them against semantic segmentation,
and that is why cell size became a problem (a handle has no cell size), why horizon length became a
problem (a track's lifetime IS its horizon) and why an eleven-pixel car became a problem (one
feature point is enough to hold onto). None of those are limits of the machine; they were symptoms
of asking vision to do the graph's job.

WHY THIS FILE IS WIRING AND NOT INVENTION. Every part already existed and none of them were joined:
`coherence.tracks` follows things, the depth net orders them, `object_recognition.recognize_object`
remembers instances, and `inner_voice` says what is happening. Nine cases of built-but-unwired are
catalogued in this repository; this closes two of them rather than adding a tenth.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class Handle:
    """One thing vision is holding onto."""

    track_ids: list[int]
    xy: tuple[float, float]                 # where it is now, in image coordinates
    depth_rank: float                       # smaller = nearer; ordinal, never metres
    first_seen: float
    last_seen: float
    frames_held: int
    instance_id: str = ""                   # from re-identification; "" while unrecognised
    known: bool = False
    signature: list[float] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"at": [round(v, 1) for v in self.xy], "depth_rank": round(self.depth_rank, 3),
                "held_frames": self.frames_held, "known": self.known,
                "instance": self.instance_id, "tracks": len(self.track_ids)}


def _signature(rgb: np.ndarray, xy: tuple[float, float], r: int = 24) -> list[float]:
    """A gradient-orientation code around a point — what re-identification matches on.

    GRADIENTS, NOT PIXELS, AND THAT IS NOT A REFINEMENT. The first version normalised a raw 8x8
    patch, and the wiring "worked": 264 handles across three looks, every one reported as recognised,
    every one matched to the SAME instance id. ATANOR would have concluded that everything it had
    ever seen was one object.

    The pre-flight I had just written into the constants and then failed to run says why. Two natural
    image patches are alike almost by definition — both are middling brightness with a smooth
    gradient — so raw cosine sits above 0.96 for ANY pair, while the matcher's threshold is 0.75:

        signature   same p10   different p90   overlap
        raw           0.982        0.995         35%    everything matches everything
        zero-DC       0.268        0.401         18%    better, still not separable
        gradient      0.733        0.624          3%    SEPARABLE

    Only the last has a gap between "the same thing again" and "a different thing", and the gap is
    where a threshold can live. 4 spatial cells x 8 orientation bins, magnitude-weighted; brightness
    cancels because only the direction of change is kept, which is also why it survives a shadow.

    The existing matcher's 0.75 sits just above the measured same-thing p10 of 0.733, so it errs
    toward calling a familiar thing new. That is the right direction to err — a false "I know this"
    corrupts memory, a false "this is new" only costs an entry."""
    import cv2
    h, w = rgb.shape[:2]
    x, y = int(xy[0]), int(xy[1])
    p = rgb[max(0, y - r):min(h, y + r), max(0, x - r):min(w, x + r)]
    if p.size == 0:
        return []
    p = cv2.resize(p.astype(np.float32), (12, 12), interpolation=cv2.INTER_AREA)
    g = p.mean(axis=2) if p.ndim == 3 else p
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(gx ** 2 + gy ** 2)
    ang = (np.arctan2(gy, gx) + np.pi) / (2 * np.pi)
    hist = np.zeros(32, np.float32)
    quads = [(slice(0, 6), slice(0, 6)), (slice(0, 6), slice(6, 12)),
             (slice(6, 12), slice(0, 6)), (slice(6, 12), slice(6, 12))]
    for bi, (ys, xs) in enumerate(quads):
        h8, _ = np.histogram(ang[ys, xs], bins=8, range=(0.0, 1.0), weights=mag[ys, xs])
        hist[bi * 8:(bi + 1) * 8] = h8
    n = float(np.linalg.norm(hist)) or 1.0
    return [round(float(v), 5) for v in (hist / n)]


def handles(frames: list[np.ndarray], depth: np.ndarray | None = None, *,
            min_life: int = 6, merge_px: float = 28.0, remember: bool = True) -> list[Handle]:
    """Watch a stretch and return what vision is holding onto.

    Tracks that stayed close to each other for their whole shared life are held as ONE handle. That
    is a weak grouping and deliberately so: getting the extent wrong costs nothing here, because the
    handle's job is to be grabbable, not to be an outline. The previous versions failed at exactly
    the point where they were asked to be right about extent."""
    from .coherence import tracks

    tr = tracks(frames)
    xy, alive = tr["xy"], tr["alive"]
    T, N = alive.shape
    if N == 0:
        return []
    life = alive.sum(axis=0)
    live = [int(n) for n in np.where(life >= min_life)[0]]
    if not live:
        return []

    last = T - 1
    while last > 0 and not alive[last].any():
        last -= 1

    groups: list[list[int]] = []
    used: set = set()
    for n in sorted(live, key=lambda k: -life[k]):
        if n in used:
            continue
        g = [n]
        used.add(n)
        for m in live:
            if m in used:
                continue
            both = alive[:, n] & alive[:, m]
            if both.sum() < min_life:
                continue
            if float(np.linalg.norm(xy[both, n] - xy[both, m], axis=1).mean()) < merge_px:
                g.append(m)
                used.add(m)
        groups.append(g)

    now = time.time()
    out: list[Handle] = []
    for g in groups:
        at_last = [xy[last, k] for k in g if alive[last, k]]
        if not at_last:
            continue
        p = np.mean(at_last, axis=0)
        d = float("nan")
        if depth is not None:
            ys = np.clip(int(p[1]), 0, depth.shape[0] - 1)
            xs = np.clip(int(p[0]), 0, depth.shape[1] - 1)
            d = float(depth[ys, xs])
        sig = _signature(frames[last], (float(p[0]), float(p[1])))
        h = Handle(track_ids=g, xy=(float(p[0]), float(p[1])), depth_rank=d,
                   first_seen=now, last_seen=now,
                   frames_held=int(max(alive[:, k].sum() for k in g)), signature=sig)
        if remember and sig:
            # THE WIRING. `recognize_object` has existed and nothing in perception ever called it,
            # so ATANOR could see the same thing twice and have no way to notice.
            try:
                from .object_recognition import recognize_object
                r = recognize_object(sig, update=True)
                h.known = bool(r.get("matched"))
                h.instance_id = str(r.get("instance_id") or r.get("id") or "")
            except Exception:
                pass
        out.append(h)
    out.sort(key=lambda x: -x.frames_held)
    return out


def say(hs: list[Handle], *, command: str | None = None) -> str:
    """What vision reports, in one sentence, from measured values only.

    Every clause is traceable to a field of a Handle. There is no branch that produces a confident
    sentence when the numbers are thin — a narration that could say more than the measurement
    supports is worse than none, because it reads as understanding."""
    if not hs:
        return "I am not holding onto anything — nothing stayed still enough to follow."
    known = [h for h in hs if h.known]
    near = min(hs, key=lambda h: h.depth_rank if h.depth_rank == h.depth_rank else 1e9)
    bits = [f"holding {len(hs)} thing{'s' if len(hs) != 1 else ''}"]
    if known:
        bits.append(f"{len(known)} of which I have met before")
    else:
        bits.append("none of which I have met before")
    if near.depth_rank == near.depth_rank:
        bits.append(f"the nearest at ({near.xy[0]:.0f}, {near.xy[1]:.0f})")
    if command:
        bits.append(f"while I was doing '{command}'")
    return ", ".join(bits) + "."


def to_inner_voice(hs: list[Handle], *, command: str | None = None,
                   emotion: dict[str, Any] | None = None) -> Any:
    """Hand what vision is holding to the voice that already exists.

    `packages/inner_voice` has its constructions, its safety flags and its forbidden-phrase list, and
    was wired to none of the perception organs. Adding a second narrator here would have been the
    tenth built-but-unwired case in a repository that has catalogued nine."""
    try:
        from packages.inner_voice import emit_inner_voice_from_state
    except Exception:
        return None
    return emit_inner_voice_from_state(
        source_event_id=f"vision_{int(time.time())}",
        mode="lab_visible",
        emotion_snapshot=emotion or {},
        agent_loop_state={"organ": "vision", "handles": [h.as_dict() for h in hs],
                          "summary": say(hs, command=command)},
        latest_action_result={"command": command or ""},
        permission_tier="OBSERVE_ONLY",
        language="en")
