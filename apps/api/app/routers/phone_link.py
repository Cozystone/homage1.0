# -*- coding: utf-8 -*-
"""Phone Link API — pairing state for the shell, on/off switch.

GET  /api/phone-link/status  -> {code, enabled, last_text, last_answer, link_url}
POST /api/phone-link/enable  -> start the relay poller
POST /api/phone-link/disable
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from packages import phone_link

router = APIRouter(prefix="/api/phone-link", tags=["phone-link"])

LINK_URL = "https://atanor-liard.vercel.app/link"


@router.get("/status")
def status() -> dict[str, Any]:
    st = phone_link.get_state()
    st["code"] = phone_link.ensure_code()
    st["link_url"] = LINK_URL
    return st


@router.post("/enable")
def enable() -> dict[str, Any]:
    st = phone_link.start(True)
    st["link_url"] = LINK_URL
    return st


@router.post("/disable")
def disable() -> dict[str, Any]:
    st = phone_link.start(False)
    st["link_url"] = LINK_URL
    return st


# ---- device continuity v0 (Phase 5): the session follows the person ----
@router.post("/continuity/snapshot")
def continuity_snapshot(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    from packages.phone_link.continuity import make_snapshot

    device = str((payload or {}).get("device") or "desktop")[:40]
    return make_snapshot(device)


@router.get("/continuity")
def continuity_read() -> dict[str, Any]:
    from packages.phone_link.continuity import read_snapshot

    snap = read_snapshot()
    return snap or {"snapshot": None, "reason": "no session snapshot taken yet"}


@router.post("/continuity/adopt")
def continuity_adopt(payload: dict[str, Any]) -> dict[str, Any]:
    from packages.phone_link.continuity import adopt_snapshot

    return adopt_snapshot(str(payload.get("token") or ""),
                          str(payload.get("device") or "phone")[:40])
