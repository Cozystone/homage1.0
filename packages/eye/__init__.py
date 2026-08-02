# -*- coding: utf-8 -*-
"""ATANOR's eye — one door for every kind of light.

The binding principle it exists to enforce (owner, standing): the eye that looks at the physical
world and the eye that looks at the pixels of a browser or a window are THE SAME EYE. A screen, a
window, a video file and a camera all produce `Frame`, and `packages.perception` — which already
speaks HxWx3 uint8 — cannot tell which one it received.

    from packages.eye import open_eye, WindowSource
    eye = open_eye(WindowSource(title_contains="RealCity"))
    for look in eye.watch(hz=5, attended_only=True):
        ...   # look.frame.rgb goes straight into perception.*

Capability is reported, never assumed: `Source.available()` tries the backend and returns a reason
when it cannot run here.
"""
from .eye import Eye, Look, open_eye
from .frame import Frame, as_rgb, bgr_to_rgb, now_utc
from .sources import (CameraSource, EpisodeSource, ScreenSource, Source, VideoSource,
                      WindowSource)

ATANOR_TIER = "perception"

__all__ = ["Eye", "Look", "open_eye", "Frame", "as_rgb", "bgr_to_rgb", "now_utc",
           "Source", "ScreenSource", "WindowSource", "VideoSource", "CameraSource",
           "EpisodeSource",
           "ATANOR_TIER"]
