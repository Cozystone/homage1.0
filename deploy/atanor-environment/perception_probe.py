#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Perception probe — runs INSIDE the user's graphical session (the only place the
active window is visible) and posts app+title to the LOCAL engine, which distills
to concepts and discards the raw. The sensor lives in-session; the brain stays a
system service. Nothing leaves 127.0.0.1.

Xorg only for now (xdotool); on Wayland the honest path is the atanor-orb GNOME
extension reporting focus — not faked here.
"""
import json
import subprocess
import time
import urllib.request

ENGINE = "http://127.0.0.1:8502/api/perception/ingest"
POLL_S = 5


def probe():
    wid = subprocess.run(["xdotool", "getactivewindow"], capture_output=True, text=True, timeout=5)
    if wid.returncode != 0 or not wid.stdout.strip():
        return None
    w = wid.stdout.strip()
    title = subprocess.run(["xdotool", "getwindowname", w], capture_output=True, text=True, timeout=5)
    app = subprocess.run(["xdotool", "getwindowclassname", w], capture_output=True, text=True, timeout=5)
    return (app.stdout.strip() or "unknown", title.stdout.strip())


def post(app, title):
    body = json.dumps({"app": app, "window_title": title}).encode("utf-8")
    req = urllib.request.Request(ENGINE, data=body, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=5).read()


def main():
    last = None
    while True:
        try:
            got = probe()
            if got and got != last:  # only report changes — less noise, same context
                post(*got)
                last = got
        except Exception:
            pass  # engine down / no window — keep quietly sensing
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
