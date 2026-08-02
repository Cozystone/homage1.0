# -*- coding: utf-8 -*-
"""Waitlist () — the landing's download section now collects intent
instead of shipping builds.

Design constraints, in order:
 * PII stays OURS: entries append to data/waitlist/waitlist.jsonl on the VM's
 data volume (survives rebuilds) — no third-party form service ever sees an
 address. Deletion on request = the right-to-be-forgotten lane.
 * Abuse-bounded: light per-IP bucket + global daily cap, and the payload is
 clamped to the three fields we actually need.
 * Honest UX contract: the endpoint answers {ok, position} so the landing can
 show a real queue position, not a fake counter.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/waitlist", tags=["waitlist"])

_DATA = Path(__file__).resolve().parents[4] / "data" / "waitlist"
_FILE = _DATA / "waitlist.jsonl"
_LOCK = threading.Lock()
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s.]{2,24}$")

# light abuse bounds (in-memory; the VM restarts rarely and this is not auth)
_BUCKET: dict[str, list[float]] = {}
_PER_IP_PER_HOUR = 6
_GLOBAL_PER_DAY = 2000
_day = {"stamp": "", "count": 0}


class WaitlistEntry(BaseModel):
    email: str
    name: str = ""
    locale: str = ""


def _emails() -> set[str]:
    try:
        with _FILE.open(encoding="utf-8") as fh:
            return {json.loads(line).get("email", "") for line in fh if line.strip()}
    except FileNotFoundError:
        return set()
    except Exception:
        return set()


@router.post("")
@router.post("/")
def join(entry: WaitlistEntry, request: Request):
    email = entry.email.strip().lower()
    if not _EMAIL_RE.match(email):
        return {"ok": False, "error": "invalid_email"}
    ip = (request.client.host if request.client else "?")
    now = time.time()
    with _LOCK:
        hits = [t for t in _BUCKET.get(ip, []) if now - t < 3600]
        if len(hits) >= _PER_IP_PER_HOUR:
            return {"ok": False, "error": "rate_limited"}
        hits.append(now)
        _BUCKET[ip] = hits
        today = time.strftime("%Y-%m-%d")
        if _day["stamp"] != today:
            _day["stamp"], _day["count"] = today, 0
        if _day["count"] >= _GLOBAL_PER_DAY:
            return {"ok": False, "error": "daily_cap"}
        existing = _emails()
        if email in existing:
            return {"ok": True, "position": len(existing), "already": True}
        _day["count"] += 1
        _DATA.mkdir(parents=True, exist_ok=True)
        with _FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "email": email,
                "name": entry.name.strip()[:80],
                "locale": entry.locale.strip()[:8],
                "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }, ensure_ascii=False) + "\n")
        return {"ok": True, "position": len(existing) + 1, "already": False}


@router.get("/count")
def count():
    return {"count": len(_emails())}
