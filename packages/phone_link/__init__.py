# -*- coding: utf-8 -*-
"""Phone Link — a phone becomes this machine's microphone.

Until the real app exists, the flow is: the OS shows a pairing code; the phone
opens the public /link page (Vercel), enters the code, and holds-to-talk; the
audio hops through OUR relay (the always-on cloud VM — never a third party) and
this daemon pulls it, transcribes LOCALLY with the same whisper the orb uses,
and routes the text through the exact voice lane (OS action first, knowledge
answer second). The relay deletes audio on pull; nothing is retained off-device.
"""
from __future__ import annotations

import base64
import json
import secrets
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
_STATE_PATH = _REPO / "data" / "phone_link" / "state.json"
RELAY_BASE = "https://136.114.69.152.sslip.io"

_state: dict[str, Any] = {"code": None, "enabled": False, "last_text": "", "last_answer": "", "last_at": ""}
_lock = threading.Lock()
_thread: threading.Thread | None = None


def _save() -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(_state, ensure_ascii=False), encoding="utf-8")


def get_state() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def ensure_code() -> str:
    """The pairing code is generated once and persists across restarts —
    the phone should not need re-pairing every boot."""
    with _lock:
        if not _state["code"]:
            if _STATE_PATH.exists():
                try:
                    _state.update(json.loads(_STATE_PATH.read_text(encoding="utf-8")))
                except Exception:
                    pass
        if not _state["code"]:
            # 9 chars, unambiguous alphabet — speakable and typeable on a phone
            alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
            _state["code"] = "".join(secrets.choice(alphabet) for _ in range(9))
            _save()
        return str(_state["code"])


def _handle_utterance(audio: bytes) -> None:
    from packages.voice_io import transcribe_wav_bytes

    text = (transcribe_wav_bytes(audio) or "").strip()
    if not text:
        return
    answer = ""
    try:  # OS action first — the phone can drive the desktop
        from packages.os_action_lane import default_lane  # noqa: F401  (import check)
        from apps.api.app.routers.os_action import _LANE  # same lane instance as the orb
        from packages.os_action_lane.intent import parse_intent

        action = parse_intent(text)
        if action is not None:
            res = _LANE.propose(action)
            answer = getattr(res, "detail", "") or "실행했습니다."
        else:
            raise LookupError("not an os action")
    except Exception:
        try:  # knowledge answer, same engine the orb asks
            data = json.dumps({"query": text, "language": "ko"}).encode()
            req = urllib.request.Request("http://127.0.0.1:8502/api/base-brain/answer",
                                         data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                answer = str(json.loads(r.read().decode("utf-8")).get("answer") or "")
        except Exception:
            answer = ""
    with _lock:
        _state["last_text"] = text
        _state["last_answer"] = answer[:400]
        _state["last_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _save()


def _poll_loop() -> None:
    code = ensure_code()
    url = f"{RELAY_BASE}/api/link/{code}/pull"
    while True:
        with _lock:
            enabled = _state["enabled"]
        if not enabled:
            time.sleep(3)
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ATANOR-PhoneLink/1.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                if r.status == 200:
                    payload = json.loads(r.read().decode("utf-8"))
                    audio = base64.b64decode(payload.get("audio_b64") or "")
                    if audio:
                        _handle_utterance(audio)
                    continue  # drain the queue without sleeping
        except Exception:
            pass
        time.sleep(2)


def start(enabled: bool = True) -> dict[str, Any]:
    global _thread
    ensure_code()
    with _lock:
        _state["enabled"] = enabled
        _save()
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_poll_loop, name="phone-link-poller", daemon=True)
        _thread.start()
    return get_state()
