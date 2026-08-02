# -*- coding: utf-8 -*-
"""Backends — the REAL actuators. 'Actually use the desktop, not just call a tool':
the LinuxDesktopBackend synthesizes real input (ydotool), drives GNOME (gdbus), and
runs real commands (subprocess). MockBackend records calls for tests without touching
the machine, so the lane's gating logic is provable in CI.

Each backend exposes ONE method: execute(action) -> (ok, stdout, stderr). The lane
decides WHETHER to call it; the backend only knows HOW.
"""
from __future__ import annotations

import shlex
import subprocess
from typing import Any

from .models import Action


class MockBackend:
    """Records executed actions; never touches the system. Deterministic for tests."""

    def __init__(self) -> None:
        self.executed: list[Action] = []

    def execute(self, action: Action) -> tuple[bool, str, str]:
        self.executed.append(action)
        return True, f"[mock] {action.kind} {action.args}", ""


class LinuxDesktopBackend:
    """Drives the actual GNOME/Wayland desktop. Requires ydotool (input), gdbus/wmctrl
    (windows), pactl (audio) — all standard on the ATANOR OS. On a host missing a tool,
    that specific verb returns a clear error rather than pretending success."""

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    def _run(self, argv: list[str] | str, shell: bool = False) -> tuple[bool, str, str]:
        try:
            p = subprocess.run(argv if not shell else argv, shell=shell, capture_output=True,
                               text=True, timeout=self.timeout)
            return p.returncode == 0, (p.stdout or "")[:4000], (p.stderr or "")[:2000]
        except subprocess.TimeoutExpired:
            return False, "", "timeout"
        except FileNotFoundError as exc:
            return False, "", f"tool missing: {exc}"
        except Exception as exc:  # noqa: BLE001
            return False, "", str(exc)[:500]

    def execute(self, action: Action) -> tuple[bool, str, str]:
        k, a = action.kind, action.args
        if k == "run":
            return self._run(str(a.get("command", "")), shell=True)
        if k == "open_app":
            app = str(a.get("app", ""))
            # DETACH, never wait: gtk-launch stays attached to the app it opens, so
            # the lane's timeout killed the very window it had just launched
            # (measured: detail='timeout', app dead). A launch is fire-and-forget —
            # its success is the window appearing, not the launcher exiting.
            try:
                subprocess.Popen(
                    ["sh", "-c", f"gtk-launch {shlex.quote(app)} 2>/dev/null || exec {shlex.quote(app)}"],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                return True, f"launched {app}", ""
            except Exception as exc:  # noqa: BLE001
                return False, "", str(exc)[:500]
        if k == "list_windows":
            return self._run(["wmctrl", "-l"])
        if k == "focus_window":
            return self._run(["wmctrl", "-a", str(a.get("title", ""))])
        if k == "close_window":
            return self._run(["wmctrl", "-c", str(a.get("title", ""))])
        if k == "type_text":
            return self._run(["ydotool", "type", str(a.get("text", ""))])
        if k == "key":
            return self._run(["ydotool", "key", str(a.get("keys", ""))])
        if k == "set_volume":
            pct = int(a.get("percent", 50))
            return self._run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{pct}%"])
        if k == "get_volume":
            return self._run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
        if k == "screenshot":
            out = str(a.get("path", "/tmp/atanor-shot.png"))
            return self._run(["gnome-screenshot", "-f", out])
        if k == "read_file":
            path = str(a.get("path", ""))
            return self._run(["cat", path])
        if k == "write_file":
            path, content = str(a.get("path", "")), str(a.get("content", ""))
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(content)
                return True, f"wrote {len(content)} bytes to {path}", ""
            except Exception as exc:  # noqa: BLE001
                return False, "", str(exc)[:300]
        if k == "delete_file":
            return self._run(["rm", "-f", str(a.get("path", ""))])
        if k == "move_file":
            return self._run(["mv", str(a.get("src", "")), str(a.get("dst", ""))])
        if k == "kill_process":
            return self._run(["kill", str(a.get("pid", ""))])
        return False, "", f"unknown action kind: {k}"
