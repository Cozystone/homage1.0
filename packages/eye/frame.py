# -*- coding: utf-8 -*-
"""The one thing every source produces, and the one thing every visual organ receives.

THE BINDING PRINCIPLE (owner, standing): the eye that looks at the physical world and the eye that
looks at the pixels of a browser or a window MUST BE THE SAME EYE. This module is where that stops
being a slogan and becomes a type.

It is a constraint, not a convenience. If a screen frame and a camera frame arrived as different
kinds of thing, every organ downstream would branch on which one it got, and whatever ATANOR learned
about motion in Realcity could not be applied to a camera — the two would be different subjects that
happen to share a cortex. The same argument was measured on 2026-07-29 in the symbolic direction:
`decisive_kind`, unchanged, scored graph entities and continuous trajectories and correctly refused
on the one with no signal. One rule spanning two modalities is worth more than two tuned rules.

WHY THE CONTRACT IS `rgb: np.ndarray` AND NOT SOMETHING NEW. It was not chosen here. The visual
cortex already speaks it: `perception.attention.frame_signature(rgb)`, `face_cortex.perceive(rgb)`,
`open_vocab`, `scene_graph`, `vjepa_harness` all take an HxWx3 uint8 array. The organ that was
missing was never the representation — it was FRAME ACQUISITION. So this package adds the door, not
a new language, and nothing downstream has to change to accept it.

`source` IS PROVENANCE, NOT A SWITCH. It exists so a receipt can say where a frame came from and so
a source can be rate-limited or revoked. No perception organ may branch on it — the moment one does,
the single eye has silently become two. `tests/test_source_blindness.py` is the check on that.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np


@dataclass(frozen=True)
class Frame:
    """One look. Pixels, when they were taken, and where from — nothing else.

    `t_utc` is an absolute UTC timestamp rather than a frame counter, because every other event in
    this system lands on the one UTC timeline and a frame that only knows its index cannot be placed
    beside a hormone reading or a graph edit. `t_mono` is the monotonic clock for measuring
    intervals, which a wall clock cannot do safely across a time adjustment."""

    rgb: np.ndarray                      # HxWx3, uint8 — the contract the visual cortex already uses
    t_utc: str                           # ISO-8601 UTC, for the one timeline
    t_mono: float                        # monotonic seconds, for intervals
    source: str                          # provenance ONLY — never branch on this
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def size(self) -> tuple[int, int]:
        return (int(self.rgb.shape[1]), int(self.rgb.shape[0]))   # (w, h)

    def __repr__(self) -> str:          # arrays do not belong in a log line
        w, h = self.size
        return f"Frame({w}x{h} from {self.source!r} at {self.t_utc})"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def as_rgb(pixels: Any) -> np.ndarray:
    """Coerce whatever a backend handed back into the HxWx3 uint8 the cortex expects.

    Backends disagree in exactly three ways and each is handled once here rather than in every
    source: PIL hands back an image object, OpenCV hands back BGR, and screen grabs on Windows carry
    a fourth alpha channel. A source that got any of these wrong would produce frames that look
    valid and are colour-swapped, which is the kind of defect that survives a long time because
    nothing crashes."""
    arr = np.asarray(pixels)
    if arr.ndim == 2:                                   # greyscale -> 3 channels
        arr = np.stack([arr] * 3, axis=-1)
    if arr.ndim != 3:
        raise ValueError(f"expected an image, got shape {arr.shape}")
    if arr.shape[2] == 4:                               # RGBA/BGRA -> drop alpha
        arr = arr[:, :, :3]
    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    return np.ascontiguousarray(arr)


def bgr_to_rgb(arr: np.ndarray) -> np.ndarray:
    """OpenCV's channel order, reversed. Separate from `as_rgb` on purpose: only the caller knows
    whether its backend is BGR, and guessing from the pixels is not possible."""
    return np.ascontiguousarray(np.asarray(arr)[:, :, ::-1])
