# -*- coding: utf-8 -*-
"""Natural-language intent -> Action. The orb hears ' ' and this maps it to
Action('open_app', {'app': 'gnome-terminal'}). Deterministic cue matching (No-LLM), with
an explicit ESCAPE: a request that doesn't match a known safe verb becomes a `run`
Action carrying the literal command the user dictated — so 'no task is impossible', but
that raw path is exactly what the trust gate scrutinizes hardest.
"""
from __future__ import annotations

import re

from .models import Action

import shutil


def _first_available(*candidates: str) -> str:
    """Environment-appropriate app resolution: the same intent (' ')
 must work on the GNOME stage-1 VM (gnome-terminal) AND on ATANOR Linux
 (lxterminal) — resolve to whatever this machine actually has."""
    for c in candidates:
        if shutil.which(c):
            return c
    return candidates[0]


_APP_ALIASES = {
    "터미널": _first_available("gnome-terminal", "lxterminal", "x-terminal-emulator", "xterm"),
    "terminal": _first_available("gnome-terminal", "lxterminal", "x-terminal-emulator", "xterm"),
    "브라우저": _first_available("chromium-browser", "chromium", "firefox-esr", "firefox"),
    "browser": _first_available("chromium-browser", "chromium", "firefox-esr", "firefox"),
    "크롬": _first_available("chromium-browser", "chromium", "firefox-esr", "firefox"),
    "파일": _first_available("nautilus", "pcmanfm"),
    "파일탐색기": _first_available("nautilus", "pcmanfm"),
    "파일 관리자": _first_available("nautilus", "pcmanfm"),
    "files": _first_available("nautilus", "pcmanfm"),
    "설정": "gnome-control-center", "settings": "gnome-control-center",
    "계산기": "gnome-calculator", "메모": "gedit", "텍스트": "gedit",
    "대시보드": "atanor-dashboard", "dashboard": "atanor-dashboard",
    # the machine's own name is a launch target ('open atanor app' fell through
    # to the knowledge engine, which defined the WORD open — measured)
    "atanor": "atanor-dashboard", "아타노르": "atanor-dashboard",
}


def parse_intent(text: str) -> Action | None:
    """Return the Action a natural request maps to, or None when it is not an OS command
    (a plain question — the orb answers that with the knowledge engine instead)."""
    t = text.strip()
    tl = t.lower()

    # volume
    m = re.search(r"(?:볼륨|소리|음량|volume)\D*(\d{1,3})\s*(?:%|퍼센트|percent)?", tl)
    if m:
        return Action("set_volume", {"percent": min(100, int(m.group(1)))}, intent=t)
    if re.search(r"(?:볼륨|소리|음량)\s*(?:올려|키워|높여|up)", tl):
        return Action("run", {"command": "pactl set-sink-volume @DEFAULT_SINK@ +10%"}, intent=t)
    if re.search(r"(?:볼륨|소리|음량)\s*(?:내려|줄여|낮춰|down)", tl):
        return Action("run", {"command": "pactl set-sink-volume @DEFAULT_SINK@ -10%"}, intent=t)

    # open app
    if re.search(r"(열어|켜|실행|open|launch|start)", tl):
        for alias, app in _APP_ALIASES.items():
            if alias in tl:
                return Action("open_app", {"app": app}, intent=t)

    # close / focus window
    m = re.search(r"(.+?)\s*(?:창)?\s*(?:닫아|닫기|close)", t)
    if m and re.search(r"닫|close", tl):
        title = m.group(1).strip()
        return Action("close_window", {"title": title}, intent=t)
    m = re.search(r"(.+?)\s*(?:창)?\s*(?:로 이동|focus|앞으로|띄워)", t)
    if m:
        return Action("focus_window", {"title": m.group(1).strip()}, intent=t)

    # list windows / screenshot
    if re.search(r"(창\s*목록|열린 창|list windows|뭐가 열려)", tl):
        return Action("list_windows", {}, intent=t)
    if re.search(r"(스크린샷|화면 캡처|screenshot)", tl):
        return Action("screenshot", {"path": "/tmp/atanor-shot.png"}, intent=t)


    m = re.search(r"(?:명령(?:어)?\s*(?:실행)?\s*[:：]|run\s*[:：]|쉘\s*[:：])\s*(.+)$", t)
    if m:
        return Action("run", {"command": m.group(1).strip()}, intent=t)

    return None  # not an OS command
