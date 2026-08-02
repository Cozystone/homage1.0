"""Unique AI-model / device identity endpoint.

`GET  /api/identity`          → this install's stable id (minted on first call, then idempotent).
`POST /api/identity/register` → append a registration record to the local device registry.

Backed by `packages.ego_network.device_identity` (did-like proof identity; not a security
credential, not hardware fingerprinting — see that module's contract).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

from packages.ego_network.device_identity import (
    get_or_create_device_identity,
    register_device,
)

router = APIRouter(prefix="/api/identity", tags=["identity"])


@router.get("")
def identity() -> dict[str, Any]:
    """Return the install's AI-model id, minting + persisting it on first access."""
    return get_or_create_device_identity()


@router.post("/register")
def register(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Register this device to the local registry (the seam P2P/Atlas + licensing read)."""
    note = str(body.get("note", ""))[:200] if isinstance(body, dict) else ""
    return register_device(note=note)
