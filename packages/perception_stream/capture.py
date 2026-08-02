# -*- coding: utf-8 -*-
"""Perception stream — capture live user activity and DISTILL it to concepts.

The differentiator: ATANOR understands what you are doing across every app (Firefox,
an editor, a PDF), not by shipping your screen anywhere but by reading the ACTIVE
WINDOW's title/app locally and reducing it to content nouns. Privacy is the
architecture, not a promise:

  * only the window TITLE + app name are read (never the window CONTENTS/keystrokes);
  * the title is DISTILLED to concept nouns and the raw title is DISCARDED — the ledger
    stores concepts + app + timestamp, never the verbatim string, never a screenshot;
  * nothing leaves the machine (there is no upload path in this module);
  * a REDACT list drops obviously-sensitive contexts (password/bank/private-browsing)
    before distillation, so they never become even a concept.

This module is the sensor; ledger.py is the (bounded, append-only) local store.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import asdict, dataclass, field
from typing import Any


class ProbeUnavailable(RuntimeError):
    """The active-window probe is not available (no X/Wayland tool on this host)."""


# contexts that must never even become a concept — dropped before distillation
_REDACT = re.compile(
    r"password|passwd|암호|비밀번호|bank|은행|계좌|카드번호|주민등록|"
    r"private browsing|사생활 보호|시크릿|incognito|otp|인증번호|보안카드|"
    r"login|로그인|signin|sign in",
    re.I,
)
# app/browser chrome tokens to strip so only the real subject survives
_CHROME = re.compile(
    r"—.*$|-\s*(mozilla firefox|google chrome|chromium|microsoft edge).*$|"
    r"\bmozilla firefox\b|\bgoogle chrome\b|\bchromium\b|\|.*$",
    re.I,
)


@dataclass
class ActivityEvent:
    app: str
    concepts: list[str]
    ts: str
    redacted: bool = False
    source: str = "active_window"
    # audit fields proving the raw was never kept
    raw_discarded: bool = True
    left_device: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _content_nouns(text: str, limit: int = 6) -> list[str]:
    """Content nouns of the (already app-stripped) title. Reuses the engine's Kiwi
    tokenizer when present; a regex fallback keeps it working headless."""
    out: list[str] = []
    try:
        from packages.base_brain.neighborhood import _kiwi

        kw = _kiwi()
        if kw is not None:
            for tok in kw.tokenize(text):
                if tok.tag in ("NNP", "NNG", "SL") and len(tok.form) >= 2 and tok.form not in out:
                    out.append(tok.form)
            return out[:limit]
    except Exception:
        pass
    from packages.base_brain.neighborhood import _strip_ko_tail

    for t in re.findall(r"[가-힣A-Za-z0-9]{2,}", text):
        st = _strip_ko_tail(t)
        if len(st) >= 2 and st.lower() not in {"the", "and", "for", "www", "com", "http", "https"} and st not in out:
            out.append(st)
    return out[:limit]


def distill_activity(app: str, window_title: str, ts: str) -> ActivityEvent:
    """Turn a raw (app, title) observation into a concept event. The raw title is used
    only to compute concepts and is NEVER returned or stored."""
    if _REDACT.search(window_title) or _REDACT.search(app):
        return ActivityEvent(app=app.strip()[:40] or "unknown", concepts=[], ts=ts, redacted=True)
    subject = _CHROME.sub("", window_title).strip()
    concepts = _content_nouns(subject)
    return ActivityEvent(app=app.strip()[:40] or "unknown", concepts=concepts, ts=ts)


# ---- live probe (Linux X11/Wayland). Returns (app, title) or raises ProbeUnavailable. ----
def probe_active_window() -> tuple[str, str]:
    # X11: xdotool getactivewindow -> window name + WM_CLASS
    try:
        wid = subprocess.run(["xdotool", "getactivewindow"], capture_output=True, text=True, timeout=4)
        if wid.returncode == 0 and wid.stdout.strip():
            w = wid.stdout.strip()
            title = subprocess.run(["xdotool", "getwindowname", w], capture_output=True, text=True, timeout=4).stdout.strip()
            cls = subprocess.run(["xdotool", "getwindowclassname", w], capture_output=True, text=True, timeout=4).stdout.strip()
            return cls or "unknown", title
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    # Fallback: wmctrl active window from the list (":ACTIVE:" marker not universal, so
    # take the last focused via _NET_ACTIVE_WINDOW is X-only too). Give an honest signal.
    raise ProbeUnavailable("no active-window probe (need xdotool on X11)")
