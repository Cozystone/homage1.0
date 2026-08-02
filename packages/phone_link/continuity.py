# -*- coding: utf-8 -*-
"""Device continuity v0 (Phase 5) — the session follows the person, not the box.

Contract: any device on the local network can ask "where were we?" and get a
SNAPSHOT — the live selfhood moment, the current conversation focus, and the
freshest episodic events — then ADOPT it, which records the handoff as an event
on the same timeline (continuity is itself remembered).

v0 scope (honest): one snapshot slot, local-first (data/continuity/), no
account system. The phone-link relay is the transport; this is the state.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = _REPO / "data" / "continuity" / "session_snapshot.json"


def make_snapshot(device: str = "desktop") -> dict[str, Any]:
    """Capture the CURRENT session moment from the live subsystems. Every field
    is read from a real store; absent subsystems are absent, not faked."""
    snap: dict[str, Any] = {
        "token": uuid.uuid4().hex[:16],
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "device": device,
        "adopted_by": None,
    }
    try:  # the self's live moment (mode/thought) — the feel of "same mind"
        from app.routers.continuous_self import _SELF  # type: ignore

        if _SELF.running:
            s = _SELF.snapshot()
            snap["self_moment"] = {
                "mode": s.get("mode"), "current_thought": s.get("current_thought"),
                "self_question": s.get("self_question"),
            }
    except Exception:
        pass
    try:  # freshest episodic events — what was HAPPENING
        from packages.episodic_memory.timeline import _rows

        snap["recent_events"] = _rows()[-5:]
    except Exception:
        pass
    try:  # user context line — who this is for
        from packages.user_model import user_context_line

        snap["user_context"] = user_context_line()
    except Exception:
        pass
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    return snap


def read_snapshot() -> dict[str, Any] | None:
    if not SNAPSHOT_PATH.exists():
        return None
    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def adopt_snapshot(token: str, device: str) -> dict[str, Any]:
    """A second device claims the session. The handoff lands on the episodic
    timeline — continuity is an EVENT the life remembers, not silent magic."""
    snap = read_snapshot()
    if not snap or snap.get("token") != token:
        return {"adopted": False, "reason": "no matching snapshot (token mismatch or none taken)"}
    if snap.get("adopted_by"):
        return {"adopted": False, "reason": f"already adopted by {snap['adopted_by']}"}
    snap["adopted_by"] = device
    snap["adopted_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    SNAPSHOT_PATH.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    try:
        from packages.episodic_memory.timeline import record_event

        record_event("사용자", "세션이동", f"{snap.get('device')}→{device}",
                     note=f"token={token[:8]}", source="continuity")
    except Exception:
        pass
    return {"adopted": True, "snapshot": snap}
