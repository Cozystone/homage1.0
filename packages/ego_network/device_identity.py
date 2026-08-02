# -*- coding: utf-8 -*-
"""Unique AI-model / device identity — minted ONCE at first launch, persisted locally.

Owner (device registration + unique AI-model id): every ATANOR install gets a stable,
human-readable identifier — for device identification, the P2P/Atlas compute registry, and
so a user can point at *their* instance ("this is my ATANOR"). It is NOT a security credential
and NOT hardware fingerprinting (privacy: we never read the machine's serials/MAC — the id is
minted from a random genesis phrase, so two installs on the same machine differ and nothing
personal is captured).

Design — reuse the existing did-like proof identity (`ego_network.seed_identity`):
  * at genesis we draw a random 12-word phrase, derive a `did:atanor:proof:<fingerprint>`,
    persist ONLY the derived identity (the raw phrase is shown once, never stored), and format
    a product-serial-style **AI-ID**:  ATANOR-XXXX-XXXX-XXXX-XXXX
  * every later call reads the persisted file — idempotent, the id never changes.
  * `created_at` is the instance's genesis/birthday (ties to the autobiographical self-model).

Deterministic, offline, No-LLM. `proof_only=True` is carried through honestly — this is an
identifier, not custody.
"""
from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any

from .seed_identity import create_seed_identity

# A compact, pronounceable word pool for the genesis phrase (BIP39-flavoured subset). Only used
# to mint the one-time phrase; the words themselves are never persisted.
_WORDS = (
    "atom orbit ember cinder forge quartz cobalt argon helix vector lattice photon "
    "cipher beacon harbor meadow cedar willow raven falcon otter lynx heron bison "
    "amber ivory indigo crimson azure jade onyx pearl coral basalt granite marble "
    "north summit river canyon prairie tundra delta fjord mesa dune glacier reef "
    "signal anchor lantern compass rudder keel mast tide current comet nova pulsar"
).split()

# Model line this identity belongs to (the "AI MODEL" in "unique AI-model id").
_MODEL_LINE = "atanor-graph-native"
_SCHEMA = "atanor.device-identity/v1"


def _default_root() -> Path:
    # packages/ego_network/device_identity.py -> repo root is parents[2]
    return Path(__file__).resolve().parents[2]


def _store_path(root: Path) -> Path:
    return root / "data" / "identity" / "device_identity.json"


def _genesis_phrase() -> str:
    return " ".join(secrets.choice(_WORDS) for _ in range(12))


def _format_ai_id(fingerprint: str) -> str:
    """ATANOR-XXXX-XXXX-XXXX-XXXX from the first 16 hex chars of the fingerprint."""
    h = fingerprint.upper()[:16].ljust(16, "0")
    return "ATANOR-" + "-".join(h[i : i + 4] for i in range(0, 16, 4))


def mint_device_identity(root: Path | None = None) -> dict[str, Any]:
    """Create a fresh identity payload (does NOT persist). Exposed for tests / re-mint tooling."""
    phrase = _genesis_phrase()
    ident = create_seed_identity(phrase)
    return {
        "schema": _SCHEMA,
        "ai_id": _format_ai_id(ident.public_fingerprint),
        "did": ident.did,
        "fingerprint": ident.public_fingerprint,
        "model": _MODEL_LINE,
        "created_at": ident.created_at,
        "proof_only": True,
    }


def get_or_create_device_identity(root: Path | None = None) -> dict[str, Any]:
    """Return this install's identity, minting + persisting it on the first call.

    Idempotent: after genesis the same id is returned forever (read from disk).
    """
    root = root or _default_root()
    path = _store_path(root)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("ai_id"):
                return data
        except (json.JSONDecodeError, OSError):
            pass  # corrupt/unreadable → re-mint below (rare; genesis is cheap)
    payload = mint_device_identity(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)  # atomic — a crash mid-write never leaves a half id
    return payload


def register_device(root: Path | None = None, *, note: str = "") -> dict[str, Any]:
    """Append a registration record to the local device registry (the seam the P2P/Atlas
    registry and licensing read). Returns the identity + registration count."""
    root = root or _default_root()
    ident = get_or_create_device_identity(root)
    reg = root / "data" / "identity" / "registry.jsonl"
    reg.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone

    row = {
        "ai_id": ident["ai_id"],
        "did": ident["did"],
        "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "note": note[:200],
    }
    with reg.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    count = sum(1 for _ in reg.open(encoding="utf-8"))
    return {"identity": ident, "registrations": count, "registered": True}
