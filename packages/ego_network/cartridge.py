from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from .models import EgoCartridge


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash_json(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_ego_cartridge(
    *,
    cartridge_id: str,
    owner_did: str,
    version: int,
    world_model_hash: str,
    self_model_hash: str,
    privacy_grade: str = "synthetic",
    raw_private_data_included: bool = False,
    metadata: dict[str, Any] | None = None,
    size_bytes: int | None = None,
) -> EgoCartridge:
    """Build a metadata-only ego cartridge for proof scenarios.

    This does not implement SGF binary cartridges. A compact SGF-like cartridge
    remains a future target represented only by metadata in this proof.
    """

    meta = dict(metadata or {})
    meta.setdefault("format", "ego-cartridge-proof-json")
    meta.setdefault("sgf_binary_future_target", "not_implemented")
    content_hash = _hash_json(
        {
            "cartridge_id": cartridge_id,
            "owner_did": owner_did,
            "version": version,
            "world_model_hash": world_model_hash,
            "self_model_hash": self_model_hash,
            "privacy_grade": privacy_grade,
            "metadata": meta,
        }
    )
    simulated_size = size_bytes if size_bytes is not None else len(json.dumps(meta, sort_keys=True).encode("utf-8"))
    cartridge = EgoCartridge(
        cartridge_id=cartridge_id,
        owner_did=owner_did,
        content_hash=content_hash,
        version=version,
        size_bytes=simulated_size,
        created_at=_utc_now(),
        world_model_hash=world_model_hash,
        self_model_hash=self_model_hash,
        privacy_grade=privacy_grade,
        raw_private_data_included=raw_private_data_included,
        metadata=meta,
    )
    validate_cartridge_privacy(cartridge)
    return cartridge


def validate_cartridge_privacy(cartridge: EgoCartridge) -> dict[str, Any]:
    """Validate proof cartridge privacy boundaries."""

    relay_allowed = cartridge.privacy_grade in {"public", "synthetic"} and not cartridge.raw_private_data_included
    return {
        "valid": not (cartridge.privacy_grade == "private_local_only" and cartridge.raw_private_data_included),
        "relay_allowed": relay_allowed,
        "raw_private_data_exported": False,
        "reason": "private_local_only_not_relayable" if not relay_allowed else "relay_candidate",
    }


def compare_cartridge_versions(local: EgoCartridge, remote: EgoCartridge) -> dict[str, Any]:
    """Compare two cartridge versions without selecting an automatic winner."""

    return {
        "same_owner": local.owner_did == remote.owner_did,
        "local_version": local.version,
        "remote_version": remote.version,
        "remote_newer": remote.version > local.version,
        "same_content": local.content_hash == remote.content_hash,
        "proposal_only": True,
    }


def detect_conflict(local: EgoCartridge, remote: EgoCartridge) -> dict[str, Any]:
    """Detect metadata conflicts. Conflicts require user approval."""

    conflict = (
        local.owner_did == remote.owner_did
        and local.cartridge_id == remote.cartridge_id
        and local.content_hash != remote.content_hash
    )
    return {
        "conflict": conflict,
        "requires_user_approval": conflict,
        "automatic_overwrite": False,
        "fields": ["content_hash"] if conflict else [],
    }
