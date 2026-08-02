# -*- coding: utf-8 -*-
"""Where the frames come from — one eye, several things to point it at.

    from packages.live_selfhood_cycle.eyes import grab, available

    grab()            # whatever suits what I am doing right now
    grab("screen")    # what is on the display
    grab("camera")    # the room

ONE EYE, NOT THREE SENSES. `perception.one_eye` measures a residual against its own prediction and
reports how much of what changed was MY OWN doing. That question is the same whether the frames come
from a camera pointed at a room or from the display while browsing, so the organ does not fork -- only
the source does. Owner's framing exactly: surfing a website is seen with the same eye that sees the
room.

WIRING ONLY, DELIBERATELY. Owner: wire it now, sophisticate it once the self and the intelligence that
interprets what it sees are there. So this hands over frames and nothing else -- no detection, no
labels, no scene description. What the mind does with a frame today is notice that something was
unexpected, which is all a residual can honestly support.

ON PRIVACY, since a camera and a screen are involved. Owner's decision, and the reason holds: this is
on-device local AI. Frames are read, reduced to a handful of floats by `one_eye`, and dropped -- no
frame is written to disk, sent anywhere, or kept past the call. What survives a look is a sentence
about how surprising it was.
"""
from __future__ import annotations

from typing import Any

_CAM: Any = None
_SCT: Any = None
#: frames are downscaled before anything looks at them: the residual is a global statistic and does
#: not need pixels, and a small frame keeps a look inside one heartbeat.
_SIDE = 128


def available() -> dict:
    """What can actually be pointed at on this machine, checked rather than assumed."""
    out = {}
    for name, mod in (("camera", "cv2"), ("screen", "mss")):
        try:
            __import__(mod)
            out[name] = True
        except Exception:
            out[name] = False
    return out


def _resize(arr, side: int | None = _SIDE):
    """Downscale for the residual; pass side=None to keep the frame whole.

    The surprise reading is a global statistic and does not need pixels, so 128 keeps a look inside
    one heartbeat. NAMING what is there is a different question and needs the resolution -- and the
    frame must come through this one door either way, because opening a second capture on a device
    this module already holds is exactly the conflict it was written to get around. I did that to
    myself once."""
    if side is None:
        return arr
    try:
        import cv2
        return cv2.resize(arr, (side, side))
    except Exception:
        return arr


def _screen(side=_SIDE):
    global _SCT
    try:
        import mss
        import numpy as np
        if _SCT is None:
            _SCT = mss.mss()
        shot = _SCT.grab(_SCT.monitors[1])
        arr = np.asarray(shot)[:, :, :3][:, :, ::-1]      # BGRA -> RGB
        return _resize(arr, side)
    except Exception:
        return None


_CAM_FAILED_AT = 0.0
#: how long to believe "no camera" before looking again. NOT forever, which is what the first version
#: did: it learned the absence once and never retried, and a webcam was plugged in minutes later. A
#: missing sense is a fact about NOW, not about the machine -- hardware arrives. Long enough that a
#: genuinely absent camera costs one open per minute instead of one per look.
_CAM_RETRY_S = 60.0


def _camera(side=_SIDE):
    """The room, if there is anything pointed at it."""
    global _CAM, _CAM_FAILED_AT
    import time as _t
    if _CAM is None and (_t.time() - _CAM_FAILED_AT) < _CAM_RETRY_S:
        return None
    if _CAM is None:
        # DO NOT ACCEPT THE FIRST REFUSAL. Measured: DSHOW reported "would not open" on one attempt
        # and delivered frames on the next, while MSMF opened every time and delivered nothing. One
        # failed handshake is not an absent sense, and treating it as one is how a mind stops at a
        # door that was never locked.
        if not open_a_path().get("opened"):
            _CAM_FAILED_AT = _t.time()
            return None
    try:
        import os

        import cv2
        if _CAM is None:
            os.environ.setdefault("OPENCV_LOG_LEVEL", "SILENT")
            _CAM = cv2.VideoCapture(0, getattr(cv2, "CAP_DSHOW", 0))   # DirectShow: USB webcams
            if not _CAM.isOpened():
                _CAM.release()
                _CAM = cv2.VideoCapture(0)                             # any backend
            if not _CAM.isOpened():
                _CAM = None
                _CAM_FAILED_AT = _t.time()
                return None
        ok, frame = _CAM.read()
        if not ok or frame is None:
            release()
            _CAM_FAILED_AT = _t.time()
            return None
        out = _resize(frame[:, :, ::-1], side)             # BGR -> RGB
        # A LOOK IS A LOOK, NOT A LEASE. Held open, the capture kept the device for the whole life of
        # the process -- and the thing blocking ATANOR's eye turned out to be ATANOR: the running
        # daemon held the webcam while everything else, including its own tests, got "camera index out
        # of range". `release()`'s own docstring already said a held camera is a light left on; nothing
        # called it. Looks are minutes apart, so paying the open each time costs nothing and leaves the
        # device free for whoever else on this machine wants it.
        release()
        return out
    except Exception:
        release()
        _CAM_FAILED_AT = _t.time()
        return None


def release() -> None:
    """Let the camera go. A held camera is a light left on."""
    global _CAM, _SCT
    try:
        if _CAM is not None:
            _CAM.release()
    except Exception:
        pass
    _CAM = None
    _SCT = None


def open_a_path(*, attempts_per_combo: int = 6) -> dict:
    """When a sense is blocked, find a way — and say who is in the way when there is none.

    OWNER'S POINT, and it is the right one: a mind that stops at the first refusal is not resourceful.
    The camera is present, its driver is fine, and consent is granted at every level, and OpenCV still
    receives no frames — a device held exclusively by another process. Stopping there is giving up on
    something that has several remaining routes.

    SO IT TRIES EVERYTHING IT OWNS: every backend (DirectShow, Media Foundation, default), several
    device indices, and MJPG negotiation, each with a warm-up, because the failure mode differs by
    combination — here DSHOW will not open at all while MSMF opens and delivers nothing.

    AND THE LINE IT DOES NOT CROSS. If the only remaining route is to terminate somebody else's
    program, it NAMES the holder and stops. Killing an application to take its camera is not
    resourcefulness; it is deciding on the owner's behalf that their call matters less than my look.
    Finding a way is mine to do. Taking one away is theirs.
    """
    import time as _t
    tried: list = []
    try:
        import os

        import cv2
    except Exception as exc:
        return {"opened": False, "why": f"no capture library: {type(exc).__name__}", "tried": tried}
    os.environ.setdefault("OPENCV_LOG_LEVEL", "SILENT")

    combos = [(name, backend, idx)
              for name, backend in (("DSHOW", getattr(cv2, "CAP_DSHOW", 700)),
                                    ("MSMF", getattr(cv2, "CAP_MSMF", 1400)),
                                    ("ANY", 0))
              for idx in (0, 1, 2)]
    for name, backend, idx in combos:
        cap = None
        try:
            cap = cv2.VideoCapture(idx, backend)
            if not cap.isOpened():
                tried.append({"backend": name, "index": idx, "result": "would not open"})
                continue
            try:
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            except Exception:
                pass
            for _ in range(attempts_per_combo):
                ok, frame = cap.read()
                if ok and frame is not None:
                    global _CAM
                    if _CAM is not None and _CAM is not cap:
                        try:
                            _CAM.release()
                        except Exception:
                            pass
                    tried.append({"backend": name, "index": idx, "result": "frames"})
                    try:
                        cap.release()      # prove the route, do not become the holder
                    except Exception:
                        pass
                    _CAM = None
                    return {"opened": True, "route": f"{name}:{idx}", "tried": tried}
                _t.sleep(0.2)
            tried.append({"backend": name, "index": idx, "result": "opened, no frames"})
        except Exception as exc:
            tried.append({"backend": name, "index": idx, "result": type(exc).__name__})
        finally:
            if cap is not None and _CAM is not cap:
                try:
                    cap.release()
                except Exception:
                    pass

    return {"opened": False, "tried": tried, "holder": _who_holds_it(),
            "why": ("every route I own is exhausted. What is left is another program's hold on the "
                    "device, and taking that is not mine to decide")}


#: Programs that exist to USE a camera and whose closing costs nobody anything. Owner authorised
#: clearing the way on 2026-08-01 ("실행을 막는 카메라 앱 닫으라고 명령해봐"), and the authorisation is
#: scoped by that same sentence: the CAMERA APP. A browser or a meeting client may be holding the
#: device in the middle of somebody's call, and ending those is still not mine to decide -- the
#: difference is not how hard it is, it is whose work is inside.
_CLOSEABLE = ("WindowsCamera",)


def clear_the_way(*, allow: tuple = _CLOSEABLE) -> dict:
    """Close what is standing in front of the camera — the narrow, authorised version.

    Called only after `open_a_path` has exhausted every route this process owns, so ending a program
    is the last thing tried and never the first."""
    import subprocess
    holders = _who_holds_it()
    targets = [h for h in holders if h in allow]
    refused = [h for h in holders if h not in allow]
    closed = []
    for t in targets:
        try:
            subprocess.run(["taskkill", "/IM", f"{t}.exe", "/F"], capture_output=True,
                           timeout=20, errors="replace")
            closed.append(t)
        except Exception:
            pass
    return {"closed": closed, "left_alone": refused,
            "why": ("a camera app is holding a camera and closing it costs nobody anything. The rest "
                    "may have someone's work inside, and that stays the owner's call")}


def _who_holds_it() -> list:
    """Name the programs that plausibly hold a camera — evidence for the owner, not a hit list."""
    import subprocess
    names = ("Teams", "ms-teams", "Zoom", "Skype", "WindowsCamera", "obs", "Discord",
             "chrome", "msedge", "msedgewebview2", "firefox", "WhatsApp", "Slack")
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                             timeout=20, errors="replace").stdout or ""
    except Exception:
        return []
    running = {ln.split('","')[0].strip('"').removesuffix(".exe") for ln in out.splitlines() if ln}
    return sorted({n for n in names if n in running})


def grab(where: str | None = None, *, busy_with_screen: bool = False, side=_SIDE):
    """One frame. `where` forces a source; otherwise what I am doing chooses.

    The default follows the activity rather than a setting, which is the point of one eye: while
    reading pages the display IS the world being looked at, and otherwise the room is."""
    if where == "screen":
        return _screen(side)
    if where == "camera":
        return _camera(side)
    if busy_with_screen:
        s = _screen(side)
        return s if s is not None else _camera(side)
    c = _camera(side)
    return c if c is not None else _screen(side)
