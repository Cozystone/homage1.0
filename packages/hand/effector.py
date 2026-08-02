# -*- coding: utf-8 -*-
"""ATANOR's hand: one door for motor output, the way `packages.eye` is one door for light.

WHY THIS IS NOT `os_action_lane`. That lane acts on the OPERATOR'S REAL DESKTOP — it runs commands,
opens apps, deletes files — and its risk tiers exist because those acts are irreversible and reach
outside the machine. Motor output into a game window is a different kind of thing: the worst outcome
is a camera flying into a wall. Routing one through the other would either drag heavy gating onto
something harmless, or force the gate open on the lane that genuinely needs it. So they stay
separate, and the boundary is not stylistic: this organ cannot touch a file, a process or a socket.
It can press keys and move a mouse, and only while a named window is in front.

THE SYMMETRY WITH THE EYE IS THE POINT. The eye takes screen, window, video and camera and produces
one `Frame`, so nothing downstream can tell which door the light came through. The hand takes one
`Move` and sends it through whatever effector is present — synthetic keyboard/mouse today, a robot
actuator later — so nothing upstream has to know what body it is wearing. That is what makes
"ATANOR learns to move in a city" and "ATANOR learns to move a limb" the same problem rather than
two.

WHY SCANCODES AND NOT VIRTUAL KEYS. Games read the keyboard through DirectInput or Raw Input, which
see hardware scancodes. `SendInput` with a virtual-key code is delivered to the Windows message
queue and is simply not seen by most game input paths — the key appears to do nothing, and the
failure is silent. `KEYEVENTF_SCANCODE` is what makes a synthetic press indistinguishable from a
real one.

THE GUARD, and it is the only one this organ has. Synthetic input goes wherever the focus is. If the
target window loses focus mid-sequence — an alt-tab, a popup, the operator clicking something — the
keystrokes land in whatever is there instead. So the foreground window is checked BEFORE EVERY
injection, not once at the start, and a mismatch refuses rather than proceeds. That is the same
discipline the computer-use tooling applies, for the same reason.
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Any

# --- Win32 SendInput plumbing -------------------------------------------------------------------

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x0001, 0x0002, 0x0008
MOUSEEVENTF_MOVE, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0001, 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010

# Scancodes for the keys a body in a game world actually needs. Written out rather than computed
# from `MapVirtualKey`, because that call is layout-dependent and this table is not: a scancode is a
# physical key position, so `W` here is the key where W sits on a US layout regardless of what the
# operator's layout prints on it. For a body learning by babbling, position is the right identity —
# it is asking "what does pressing THIS spot do", not "what letter is this".
SCAN = {
    "w": 0x11, "a": 0x1E, "s": 0x1F, "d": 0x20,
    "q": 0x10, "e": 0x12, "r": 0x13, "f": 0x21, "c": 0x2E, "x": 0x2D, "z": 0x2C,
    "o": 0x18, "space": 0x39, "lshift": 0x2A, "lctrl": 0x1D, "tab": 0x0F, "esc": 0x01,
}


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _INPUTunion(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]


def _send(*inputs: _INPUT) -> int:
    n = len(inputs)
    arr = (_INPUT * n)(*inputs)
    return ctypes.windll.user32.SendInput(n, ctypes.byref(arr), ctypes.sizeof(_INPUT))


def _key_input(scan: int, up: bool) -> _INPUT:
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
    return _INPUT(type=INPUT_KEYBOARD,
                  u=_INPUTunion(ki=_KEYBDINPUT(wVk=0, wScan=scan, dwFlags=flags,
                                               time=0, dwExtraInfo=None)))


def _mouse_input(dx: int, dy: int, flags: int = MOUSEEVENTF_MOVE) -> _INPUT:
    return _INPUT(type=INPUT_MOUSE,
                  u=_INPUTunion(mi=_MOUSEINPUT(dx=dx, dy=dy, mouseData=0, dwFlags=flags,
                                               time=0, dwExtraInfo=None)))


# --- the move ------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Move:
    """One motor command. Deliberately primitive: a body that only knows `hold this key for this
    long` and `turn by this much` can be babbled with, and a body that knows `walk to the shop`
    cannot — the whole point is that the mapping from these to consequences is LEARNED, not given."""

    keys: tuple[str, ...] = ()          # held together for `seconds`
    seconds: float = 0.2
    mouse_dx: int = 0                   # relative, in raw mouse counts
    mouse_dy: int = 0
    label: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"keys": list(self.keys), "seconds": self.seconds,
                "mouse": [self.mouse_dx, self.mouse_dy], "label": self.label}


class Effector:
    """A door motor output goes through."""

    name = "effector"

    def available(self) -> tuple[bool, str]:
        raise NotImplementedError

    def do(self, move: Move) -> dict[str, Any]:
        raise NotImplementedError

    def release_all(self) -> None:
        return None


@dataclass
class WindowEffector(Effector):
    """Synthetic keyboard and mouse, scoped to one window by title."""

    title_contains: str = ""
    name: str = "window"
    max_seconds: float = 3.0            # a single hold is bounded; a stuck key is a runaway body
    _held: set = field(default_factory=set)

    # -------------------------------------------------------------- the guard
    def _foreground_ok(self) -> tuple[bool, str]:
        try:
            import win32gui
        except Exception as exc:
            return False, f"win32gui missing: {exc}"
        h = win32gui.GetForegroundWindow()
        title = (win32gui.GetWindowText(h) or "") if h else ""
        if self.title_contains.lower() in title.lower():
            return True, title
        return False, f"foreground is {title!r}, not {self.title_contains!r}"

    def available(self) -> tuple[bool, str]:
        try:
            import win32gui  # noqa: F401
        except Exception as exc:
            return False, f"win32gui missing: {exc}"[:120]
        try:
            ctypes.windll.user32  # noqa: B018
        except Exception as exc:
            return False, f"user32 unavailable: {exc}"[:120]
        return True, ""

    def focus(self) -> tuple[bool, str]:
        """Bring the target window forward. Separate from `do` on purpose: taking focus is an act
        with a visible effect on the operator's desktop, so it is something the caller asks for
        explicitly rather than something every move does silently."""
        try:
            import win32gui
        except Exception as exc:
            return False, str(exc)
        found = []

        def _cb(h, _):
            if win32gui.IsWindowVisible(h):
                t = win32gui.GetWindowText(h) or ""
                if self.title_contains.lower() in t.lower():
                    found.append((h, t))

        win32gui.EnumWindows(_cb, None)
        if not found:
            return False, f"no window matching {self.title_contains!r}"
        h, title = found[0]

        # VERIFY, DO NOT TRUST THE CALL. `SetForegroundWindow` is refused by Windows whenever the
        # calling process does not own the current foreground -- the anti-focus-stealing rule -- and
        # the refusal arrives as an exception carrying a stale, unrelated error code. Seen here as
        # `(126, 'SetForegroundWindow', 'the specified module could not be found')`, which describes
        # nothing about what went wrong. The earlier version returned False on that and the capture
        # gave up while the window was sitting there, awake and responding.
        #
        # This is the same mistake `engage()` was written to fix, one level up: a call returning
        # without error is not the state having changed. So the outcome is read back from
        # GetForegroundWindow, and the several ways of asking are tried before believing a refusal.
        for attempt in range(3):
            try:
                if win32gui.IsIconic(h):
                    win32gui.ShowWindow(h, 9)            # SW_RESTORE
                win32gui.BringWindowToTop(h)
                win32gui.SetForegroundWindow(h)
            except Exception:
                pass                                      # the refusal is not informative; look instead
            time.sleep(0.25)
            if win32gui.GetForegroundWindow() == h:
                return True, title
            if attempt == 1:
                # Attach to the foreground window's input queue, which is what lifts the lock. Done
                # only after two plain attempts, because it is the more invasive way to ask.
                try:
                    import win32process
                    cur = ctypes.windll.kernel32.GetCurrentThreadId()
                    fg = win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())[0]
                    ctypes.windll.user32.AttachThreadInput(fg, cur, True)
                    win32gui.SetForegroundWindow(h)
                    ctypes.windll.user32.AttachThreadInput(fg, cur, False)
                except Exception:
                    pass
        actual = win32gui.GetWindowText(win32gui.GetForegroundWindow()) or ""
        return False, f"asked for {title!r} but the foreground is still {actual!r}"

    def engage(self) -> dict[str, Any]:
        """Click into the window so it actually TAKES the input.

        Being the foreground window is not the same as receiving keystrokes, and the gap between
        those two facts cost a whole babbling session. Unreal's Play-In-Editor viewport captures
        input only once it has been clicked; until then `SetForegroundWindow` succeeds, `SendInput`
        succeeds, every key reports ok — and nothing in the world moves. The first body-schema run
        after this was noticed read a flat zero for every move, which is exactly what a body that is
        not attached to anything should read.

        So engagement is a separate, explicit act, and it is the difference between having a hand
        and having a hand ON something."""
        ok, why = self._foreground_ok()
        if not ok:
            got, detail = self.focus()
            if not got:
                return {"ok": False, "refused": "no_window", "detail": detail}
        try:
            import win32gui
            h = win32gui.GetForegroundWindow()
            l, t, r, b = win32gui.GetWindowRect(h)
        except Exception as exc:
            return {"ok": False, "refused": "no_rect", "detail": str(exc)}
        # Aim at the middle of the upper-left quadrant: the centre of an editor window is usually
        # the viewport, but the very centre can land on an on-screen widget, and the far edges are
        # panels. This is the part of the frame that is viewport in every layout seen so far.
        cx, cy = int(l + (r - l) * 0.35), int(t + (b - t) * 0.45)
        sw = ctypes.windll.user32.GetSystemMetrics(0)
        sh = ctypes.windll.user32.GetSystemMetrics(1)
        ax, ay = int(cx * 65535 / max(sw, 1)), int(cy * 65535 / max(sh, 1))
        MOUSEEVENTF_ABSOLUTE = 0x8000
        _send(_mouse_input(ax, ay, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE))
        time.sleep(0.05)
        _send(_mouse_input(0, 0, MOUSEEVENTF_LEFTDOWN))
        time.sleep(0.05)
        _send(_mouse_input(0, 0, MOUSEEVENTF_LEFTUP))
        time.sleep(0.3)
        return {"ok": True, "clicked": [cx, cy], "window": why}

    # -------------------------------------------------------------- moving
    def do(self, move: Move) -> dict[str, Any]:
        ok, why = self._foreground_ok()
        if not ok:
            # REFUSE rather than send. Keystrokes go wherever focus is, so acting when the target is
            # not in front means typing into whatever the operator happens to be using.
            return {"ok": False, "refused": "not_foreground", "detail": why, **move.as_dict()}

        unknown = [k for k in move.keys if k not in SCAN]
        if unknown:
            return {"ok": False, "refused": "unknown_key", "detail": str(unknown), **move.as_dict()}

        secs = max(0.0, min(float(move.seconds), self.max_seconds))
        t0 = time.perf_counter()
        try:
            for k in move.keys:
                _send(_key_input(SCAN[k], up=False))
                self._held.add(k)
            if move.mouse_dx or move.mouse_dy:
                _send(_mouse_input(int(move.mouse_dx), int(move.mouse_dy)))
            if secs:
                time.sleep(secs)
        finally:
            for k in reversed(move.keys):
                _send(_key_input(SCAN[k], up=True))
                self._held.discard(k)
        return {"ok": True, "held_s": round(time.perf_counter() - t0, 3),
                "window": why, **move.as_dict()}

    def release_all(self) -> None:
        """Let go of everything. Called on the way out of any session — a body that exits with a key
        still down keeps walking after the mind has stopped."""
        for k in list(self._held):
            try:
                _send(_key_input(SCAN[k], up=True))
            except Exception:
                pass
            self._held.discard(k)
