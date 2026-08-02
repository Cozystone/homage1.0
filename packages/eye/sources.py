# -*- coding: utf-8 -*-
"""The doors light comes in through. Every one of them produces the same `Frame`.

Four sources today, and the list is meant to grow without anything downstream noticing:

  ScreenSource   the whole desktop, or a rectangle of it
  WindowSource   one window found by title — how ATANOR looks at a browser, a preview, a city
  VideoSource    a file on disk, played at its own frame rate or as fast as asked
  CameraSource   a physical camera

The point of the list is that it has no privileged member. A frame of Realcity arriving through
WindowSource and a frame of a room arriving through CameraSource are the same type, carry the same
fields, and reach the same cortex. That is the owner's standing principle expressed as code rather
than as intention.

CAPABILITY IS REPORTED, NEVER ASSUMED. Each source answers `available()` by actually trying its
backend, and a missing backend is a fact returned rather than an exception raised at import. This
repository has eight recorded instances of an organ that existed and was never wired; a ninth was
found the same day this was written (`intrinsic_drive`, runtime callers: zero). The defence is that
nothing here claims to work until it has been asked and has said yes.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterator

from .frame import Frame, as_rgb, bgr_to_rgb, now_utc


class Source:
    """A door. Open it, take looks through it, close it."""

    name: str = "source"

    def available(self) -> tuple[bool, str]:
        """(can this run here, why not). Asked, not assumed."""
        raise NotImplementedError

    def grab(self) -> Frame:
        raise NotImplementedError

    def close(self) -> None:
        return None

    def stream(self, *, hz: float = 5.0, limit: int | None = None) -> Iterator[Frame]:
        """Frames at a bounded rate. The rate is here rather than in the caller because an
        unthrottled screen grab will happily consume a core, and a source that can starve the rest
        of the mind is not a sense organ."""
        period = 1.0 / max(hz, 0.01)
        n = 0
        nxt = time.monotonic()
        while limit is None or n < limit:
            yield self.grab()
            n += 1
            nxt += period
            slack = nxt - time.monotonic()
            if slack > 0:
                time.sleep(slack)
            else:
                nxt = time.monotonic()          # fell behind; do not accumulate debt


# ---------------------------------------------------------------- screen and windows

@dataclass
class ScreenSource(Source):
    """The desktop, or a rectangle of it. `bbox` is (left, top, right, bottom) in screen pixels.

    The capture backend is chosen by `capture.best_backend()` — dxcam where it runs (120 fps at full
    resolution here), mss next, PIL as the floor. The caller does not choose and cannot: a source
    whose speed depended on which class you instantiated would push a performance decision out to
    every call site, and the decision is a property of the machine, not of the task."""

    bbox: tuple[int, int, int, int] | None = None
    name: str = "screen"
    _backend: Any = None
    _tried: Any = None
    _streaming: bool = False

    def _b(self):
        if self._backend is None:
            from .capture import best_backend
            self._backend, self._tried = best_backend()
        return self._backend

    def available(self) -> tuple[bool, str]:
        try:
            self._b()
            return True, ""
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"[:160]

    def _wrap(self, rgb) -> Frame:
        return Frame(rgb=as_rgb(rgb), t_utc=now_utc(), t_mono=time.monotonic(),
                     source=self.name,
                     meta={"bbox": self.bbox, "backend": self._b().name,
                           # Whether the display actually had something new. Reporting a cached
                           # repeat as if it were a fresh capture would turn "34,500 looks/s at a
                           # motionless screen" into a frame-rate claim, which it is not.
                           "fresh": bool(getattr(self._b(), "fresh", True))})

    def grab(self) -> Frame:
        """A Frame every time. `latest()` repeats the cached frame when the desktop has not
        changed, so an unchanging screen is cheap rather than an error — and never a block."""
        rgb = self._b().latest(self.bbox)
        if rgb is None:
            raise RuntimeError(f"{self._b().name} produced no frame")
        return self._wrap(rgb)

    def open_stream(self, target_fps: int = 120) -> None:
        """Kept for callers that ask; there is no separate streaming mode any more. `grab()`
        already runs at the backend's full rate without a capture thread."""
        self._b()

    def close(self) -> None:
        if self._backend is not None:
            self._backend.stop()
            self._streaming = False


@dataclass
class WindowSource(Source):
    """One window, found by a substring of its title.

    Re-resolves the rectangle on every grab on purpose: a window the user moves or resizes is still
    the same window, and a source that cached the rectangle would quietly start returning a slice of
    the desktop next to it — a failure that produces plausible frames and no error."""

    title_contains: str = ""
    name: str = "window"

    def _rect(self) -> tuple[int, int, int, int] | None:
        try:
            import win32gui
        except Exception:
            return None
        found: list[tuple[int, int, int, int]] = []
        needle = self.title_contains.lower()

        def _cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd) or ""
            if needle and needle not in title.lower():
                return
            l, t, r, b = win32gui.GetWindowRect(hwnd)
            if r - l > 32 and b - t > 32:
                found.append((l, t, r, b))

        win32gui.EnumWindows(_cb, None)
        return found[0] if found else None

    _screen: Any = None

    def _s(self) -> "ScreenSource":
        if self._screen is None:
            self._screen = ScreenSource(name=self.name)
        return self._screen

    def available(self) -> tuple[bool, str]:
        ok, why = self._s().available()
        if not ok:
            return False, why
        try:
            import win32gui  # noqa: F401
        except Exception as exc:
            return False, f"win32gui missing: {exc}"[:160]
        return (True, "") if self._rect() else (False, f"no visible window matching {self.title_contains!r}")


    def _handle(self):
        """The window handle for the title we are aimed at, or None."""
        try:
            import win32gui
        except Exception:
            return None
        needle = self.title_contains.lower()
        hits = []

        def _cb(h, _):
            if not win32gui.IsWindowVisible(h):
                return
            ttl = win32gui.GetWindowText(h) or ""
            if needle and needle not in ttl.lower():
                return
            l, tp, r, b = win32gui.GetWindowRect(h)
            if r - l > 32 and b - tp > 32:
                hits.append(h)

        win32gui.EnumWindows(_cb, None)
        return hits[0] if hits else None

    def _occlusion(self, rect) -> dict:
        """Is anything covering the window we think we are looking at?

        A SCREEN GRAB OF A WINDOW'S RECTANGLE IS NOT THE WINDOW. Desktop Duplication copies whatever
        is on screen at those coordinates, so when another window sits on top the eye returns ITS
        pixels and labels them with our title — silently, and flagged fresh.

        That cost four captures. City Sample was buried under a browser, and the runs read
        `travel dx 0.00 at confidence 0.999` (a static overlay), 2.9 fps of unique content, and a
        toolbar crop that came back solid black. Every one of those was diagnosed as the turn rate
        being wrong, and the turn rate was never the problem.

        The check samples a grid of points inside the rectangle and asks the window manager which
        window actually owns each one. It is cheap, it is exact, and an eye that cannot tell it is
        looking at the wrong thing will keep confidently measuring the wrong thing."""
        try:
            import win32gui
        except Exception:
            return {"occluded": False, "by": "", "visible_frac": 1.0}
        hwnd = self._handle()
        if not hwnd:
            return {"occluded": False, "by": "", "visible_frac": 1.0}
        l, t_, r, b = rect
        pts, mine, other = 0, 0, {}
        for fy in (0.2, 0.4, 0.6, 0.8):
            for fx in (0.2, 0.4, 0.6, 0.8):
                x, y = int(l + (r - l) * fx), int(t_ + (b - t_) * fy)
                try:
                    h = win32gui.WindowFromPoint((x, y))
                    top = win32gui.GetAncestor(h, 2) if h else 0     # GA_ROOT
                except Exception:
                    continue
                pts += 1
                if top == hwnd:
                    mine += 1
                else:
                    nm = (win32gui.GetWindowText(top) or "?")[:40] if top else "?"
                    other[nm] = other.get(nm, 0) + 1
        if not pts:
            return {"occluded": False, "by": "", "visible_frac": 1.0}
        frac = mine / pts
        by = max(other, key=other.get) if other else ""
        return {"occluded": frac < 0.9, "by": by, "visible_frac": round(frac, 3)}

    def grab(self) -> Frame:
        rect = self._rect()
        if rect is None:
            raise RuntimeError(f"no window matching {self.title_contains!r}")
        s = self._s()
        if s.bbox != rect:
            # The window moved or resized. Re-aim, and drop any stream bound to the old rectangle —
            # a cached region would keep returning a slice of whatever is now in that place, which
            # produces valid-looking frames of the wrong thing and raises nothing.
            s.close()
            s.bbox = rect
        f = s.grab()
        # CARRY THE WHOLE META FORWARD, then add this door's own fields. The first version rebuilt
        # meta from scratch and copied only `backend`, which silently DROPPED `fresh` -- the flag
        # added specifically so a cached repeat could never be miscounted as a capture. Every frame
        # through this door therefore reported no freshness at all, and two measurements of "the
        # eye against a live window" read 0 new frames while the attention gate was simultaneously
        # reporting `moving_wait` on 103 of 314 looks. The gate could see the pixels changing; the
        # counter could not. A guard that is dropped on one path is worse than no guard, because the
        # zero it produces looks like a measurement.
        occ = self._occlusion(rect)
        meta = dict(f.meta)
        meta.update({"title_contains": self.title_contains, "rect": rect,
                     "occluded": occ["occluded"], "occluded_by": occ["by"],
                     "visible_frac": occ["visible_frac"]})
        return Frame(rgb=f.rgb, t_utc=f.t_utc, t_mono=f.t_mono, source=self.name, meta=meta)

    def open_stream(self, target_fps: int = 120) -> None:
        rect = self._rect()
        if rect is None:
            raise RuntimeError(f"no window matching {self.title_contains!r}")
        s = self._s()
        s.bbox = rect
        s.open_stream(target_fps=target_fps)

    def close(self) -> None:
        if self._screen is not None:
            self._screen.close()


# ---------------------------------------------------------------- video files and cameras

@dataclass
class VideoSource(Source):
    """A video file. OpenCV hands back BGR, which is converted here — the one place that knows."""

    path: str = ""
    loop: bool = False
    name: str = "video"
    _cap: Any = None

    def _open(self) -> Any:
        import cv2
        if self._cap is None:
            self._cap = cv2.VideoCapture(self.path)
        return self._cap

    def available(self) -> tuple[bool, str]:
        try:
            cap = self._open()
            return (True, "") if cap.isOpened() else (False, f"cannot open {self.path!r}")
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"[:160]

    def grab(self) -> Frame:
        cap = self._open()
        ok, bgr = cap.read()
        if not ok and self.loop:
            import cv2
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, bgr = cap.read()
        if not ok:
            raise RuntimeError(f"video exhausted: {self.path!r}")
        return Frame(rgb=as_rgb(bgr_to_rgb(bgr)), t_utc=now_utc(), t_mono=time.monotonic(),
                     source=self.name, meta={"path": self.path})

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


@dataclass
class CameraSource(VideoSource):
    """A physical camera. Deliberately a VideoSource with a device index instead of a path — the
    difference between a camera and a file is which handle OpenCV opens, and pretending it is a
    deeper difference is exactly the split this package exists to prevent."""

    index: int = 0
    name: str = "camera"

    def _open(self) -> Any:
        import cv2
        if self._cap is None:
            self._cap = cv2.VideoCapture(self.index)
        return self._cap

    def available(self) -> tuple[bool, str]:
        try:
            cap = self._open()
            return (True, "") if cap.isOpened() else (False, f"no camera at index {self.index}")
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"[:160]


@dataclass
class EpisodeSource(Source):
    """Recorded frames on disk — CARLA episodes today, any recorder tomorrow.

    This is the door that makes the CARLA work part of the same eye rather than a parallel pipeline.
    A recorded frame arrives as the same `Frame` a live screen does, so anything that learns from
    CARLA is, by construction, learning from something a camera or a game window could also deliver.
    If instead the depth work had its own loader, the transfer question ("does what it learned in
    CARLA apply to City Sample?") would be confounded by the two paths differing before any model
    saw them.

    The ground truth rides in `meta`, not in `rgb`: depth and semantics are things known ABOUT the
    frame, and putting them in the pixels would make this a different kind of thing from a camera
    frame — which is exactly what must not happen."""

    root: str = ""
    with_truth: bool = True
    loop: bool = False
    name: str = "episode"
    _files: Any = None
    _i: int = 0

    def _list(self) -> list:
        if self._files is None:
            from pathlib import Path
            p = Path(self.root)
            self._files = sorted(p.rglob("*.npz")) if p.exists() else []
        return self._files

    def available(self) -> tuple[bool, str]:
        n = len(self._list())
        return (True, "") if n else (False, f"no .npz frames under {self.root!r}")

    def grab(self) -> Frame:
        import numpy as np
        files = self._list()
        if not files:
            raise RuntimeError(f"no frames under {self.root!r}")
        if self._i >= len(files):
            if not self.loop:
                raise RuntimeError("episode exhausted")
            self._i = 0
        f = files[self._i]
        self._i += 1
        z = np.load(f)
        meta: dict[str, Any] = {"path": str(f), "index": self._i - 1, "total": len(files)}
        if self.with_truth:
            for k in ("depth_m", "semantic", "pose", "sim_time"):
                if k in z:
                    meta[k] = z[k]
        return Frame(rgb=as_rgb(z["rgb"]), t_utc=now_utc(), t_mono=time.monotonic(),
                     source=self.name, meta=meta)

    def close(self) -> None:
        self._files = None
        self._i = 0
