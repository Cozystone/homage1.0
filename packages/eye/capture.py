# -*- coding: utf-8 -*-
"""What actually pulls pixels off the machine, and why there are three of them.

Owner, 2026-07-29: "눈은 더 눈다워야해. 프레임수가 너무 낮은데 사람 눈은 아니잖아." The first eye ran on
PIL's `ImageGrab` and measured 8-14 fps — and shrinking the region made it SLOWER (360p at 124ms
against 1080p at 70ms), because ImageGrab captures the whole desktop and crops. That is not a
sampling rate a visual system can be built on, and the cause was the backend, not the design.

Measured on this machine, same screen, same moment:

    dxcam  (Desktop Duplication)   120.5 fps at the full 5120x2160
    mss    (X/GDI blit)             59.9 fps at 1080p
    PIL    (ImageGrab)               8-14 fps at any size

So the backend is chosen, not fixed, and it is chosen by ASKING each one whether it can run here
rather than by assuming. Callers never pick: `ScreenSource` and `WindowSource` take the fastest
available and record which one answered in the frame's meta, so a slow reading can always be traced
to the door it came through.

THE NULL RETURN IS A FEATURE, NOT AN ERROR. `dxcam.grab()` returns None when the desktop has not
changed since the last call — the Desktop Duplication API knows this at the hardware level. On a
static screen that was 4 new frames out of 120 calls. So the fast path gets a free, exact change
detector that costs nothing to compute, which is a better version of what the attention gate does in
software. `grab()` here preserves that None; `stream()` uses the backend's own video mode, which
repeats the last frame instead, for callers that need a steady beat.
"""
from __future__ import annotations

from typing import Any

import numpy as np

Region = tuple[int, int, int, int] | None       # (left, top, right, bottom)


class Backend:
    """One way of getting pixels. Answers whether it can run before it is used."""

    name = "backend"
    fresh = True        # backends that always read STATE always return a new frame

    def available(self) -> tuple[bool, str]:
        raise NotImplementedError

    def grab(self, region: Region = None) -> np.ndarray | None:
        """RGB HxWx3, or None when the source has no NEW frame to give."""
        raise NotImplementedError

    def start(self, target_fps: int = 120, region: Region = None) -> None:
        return None

    def latest(self, region: Region = None) -> np.ndarray | None:
        """The most recent frame, repeating the last one rather than returning None."""
        return self.grab(region)

    def stop(self) -> None:
        return None


class DXCamBackend(Backend):
    """Desktop Duplication API. Fastest here by an order of magnitude, and the only one that can
    tell us for free that nothing changed."""

    name = "dxcam"

    def __init__(self) -> None:
        self._cam: Any = None
        self._last: np.ndarray | None = None

    def _camera(self) -> Any:
        if self._cam is None:
            import dxcam
            self._cam = dxcam.create(output_color="RGB")
            if self._cam is None:
                raise RuntimeError("dxcam.create returned None (no capturable output)")
        return self._cam

    def _prime(self, region: Region = None) -> np.ndarray | None:
        """The FIRST frame, which dxcam alone cannot be relied on to give.

        Desktop Duplication reports CHANGES, not state. On a genuinely static desktop — the exact
        condition an idle machine is in — `grab()` returns None forever, including the very first
        call, because there is no change to report. Measured here at 04:25 with the screen still:
        dxcam answered `available()` False after two seconds of polling, and the eye fell all the
        way back to mss at 10 fps on a 5K desktop.

        So the two backends are used for what each actually is. mss reads STATE and always answers;
        dxcam reads CHANGE and answers in microseconds when there is one. Priming from mss and then
        updating from dxcam is not a workaround stacked on a limitation — it is each API doing the
        job it was built for, and it is why the eye is both instant to open and fast to run."""
        f = self._camera().grab(region=region)
        if f is not None:
            self._last = f
            return f
        try:
            fallback = MSSBackend()
            ok, _ = fallback.available()
            if ok:
                f = fallback.grab(self._clamp(region))
                fallback.stop()
                if f is not None:
                    self._last = f
                    return f
        except Exception:
            pass
        return None

    def available(self) -> tuple[bool, str]:
        try:
            self._camera()
            if self._prime() is None:
                return False, "neither dxcam nor the mss primer produced a frame"
            return True, ""
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"[:160]

    fresh = False        # did the LAST latest() call return a genuinely new frame?

    def _clamp(self, region: Region) -> Region:
        """Keep the requested rectangle inside the output dxcam is actually duplicating.

        Desktop Duplication captures ONE output. A window rectangle from `win32gui` is in virtual
        desktop coordinates, so on a multi-monitor machine — or simply when a window is dragged so
        an edge crosses a monitor boundary — it can fall partly outside, and dxcam refuses the whole
        call with `Invalid Region: Region should be in 5120x2160`.

        That refusal killed a 75-second City Sample capture 1,703 frames in: the run was fine until
        a drag moved the window, and then every subsequent grab raised. Clamping turns a fatal error
        into a slightly cropped frame, which is the right trade for a sense organ — an eye whose
        field of view is partly off-screen should see the part that is on-screen, not go blind."""
        if region is None:
            return None
        cam = self._camera()
        l, t, r, b = (int(v) for v in region)
        l = max(0, min(l, cam.width - 1))
        t = max(0, min(t, cam.height - 1))
        r = max(l + 1, min(r, cam.width))
        b = max(t + 1, min(b, cam.height))
        return (l, t, r, b)

    def grab(self, region: Region = None) -> np.ndarray | None:
        f = self._camera().grab(region=self._clamp(region))
        if f is not None:
            self._last = f
        return f

    def latest(self, region: Region = None) -> np.ndarray | None:
        """A frame every time — the new one if the desktop changed, otherwise the last one again.

        NO BACKGROUND THREAD, and that is the fix for a real hang. dxcam's `video_mode=True` plus
        `get_latest_frame()` looked like the right way to hold a steady beat, and it BLOCKS FOREVER
        on a genuinely static desktop: the capture thread waits on Desktop Duplication, which has
        nothing to hand over, so the event it signals never fires. The first benchmark of it read
        120 fps only because the terminal printing the benchmark was itself changing the screen —
        the measurement created the condition it was measuring.

        Repeating the cached frame gives the same steady beat with none of that: `grab()` never
        blocks, returns None in microseconds when nothing changed, and that None IS the change
        signal, computed by the display hardware for free."""
        f = self.grab(region)
        self.fresh = f is not None
        if f is not None:
            return f
        return self._last if self._last is not None else self._prime(region)

    def stop(self) -> None:
        self._last = None
        if self._cam is not None:
            try:
                self._cam.release()
            except Exception:
                pass
            self._cam = None


class MSSBackend(Backend):
    """Cross-platform blit. Half of dxcam's rate, and it works where dxcam does not."""

    name = "mss"

    def __init__(self) -> None:
        self._sct: Any = None

    def _handle(self) -> Any:
        if self._sct is None:
            import mss
            self._sct = mss.mss()
        return self._sct

    def available(self) -> tuple[bool, str]:
        try:
            self._handle().grab({"top": 0, "left": 0, "width": 8, "height": 8})
            return True, ""
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"[:160]

    def grab(self, region: Region = None) -> np.ndarray | None:
        sct = self._handle()
        mon = sct.monitors[0] if region is None else {
            "left": region[0], "top": region[1],
            "width": region[2] - region[0], "height": region[3] - region[1]}
        shot = sct.grab(mon)
        return np.ascontiguousarray(np.asarray(shot)[:, :, :3][:, :, ::-1])   # BGRA -> RGB

    def stop(self) -> None:
        if self._sct is not None:
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = None


class PILBackend(Backend):
    """The floor. Slow, and present almost everywhere — kept so the eye still opens on a machine
    with neither of the others."""

    name = "pil"

    def available(self) -> tuple[bool, str]:
        try:
            from PIL import ImageGrab
            ImageGrab.grab(bbox=(0, 0, 8, 8))
            return True, ""
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"[:160]

    def grab(self, region: Region = None) -> np.ndarray | None:
        from PIL import ImageGrab
        from .frame import as_rgb
        return as_rgb(ImageGrab.grab(bbox=region))


_ORDER = (DXCamBackend, MSSBackend, PILBackend)          # fastest measured first


def best_backend() -> tuple[Backend, list[tuple[str, bool, str]]]:
    """The fastest backend that says it can run here, plus what every candidate answered.

    The rejects are returned rather than discarded: when the eye is slow, the first question is
    which door it came through and why the faster ones declined."""
    tried: list[tuple[str, bool, str]] = []
    chosen: Backend | None = None
    for cls in _ORDER:
        b = cls()
        ok, why = b.available()
        tried.append((b.name, ok, why))
        if ok and chosen is None:
            chosen = b
        else:
            b.stop()
    if chosen is None:
        raise RuntimeError(f"no capture backend available: {tried}")
    return chosen, tried
