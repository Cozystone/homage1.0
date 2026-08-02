from __future__ import annotations

from typing import Any

from .models import ConstellationState


def compute_constellation_diff(local_state: ConstellationState, remote_state: ConstellationState) -> dict[str, Any]:
    """Compute a proof-only constellation diff without mutating either state."""

    local_hash = local_state.latest_cartridge_hash
    remote_hash = remote_state.latest_cartridge_hash
    local_devices = {device.device_id: device for device in local_state.devices}
    remote_devices = {device.device_id: device for device in remote_state.devices}
    stale_devices = [
        device_id
        for device_id, device in local_devices.items()
        if device_id not in remote_devices or device.last_seen_at != remote_devices[device_id].last_seen_at
    ]
    conflict = bool(local_hash and remote_hash and local_hash != remote_hash)
    return {
        "owner_did": local_state.owner_did,
        "local_hash": local_hash,
        "remote_hash": remote_hash,
        "remote_newer": remote_state.metadata.get("version", 0) > local_state.metadata.get("version", 0),
        "stale_devices": stale_devices,
        "conflict": conflict,
        "conflicts": [{"field": "latest_cartridge_hash", "local": local_hash, "remote": remote_hash}] if conflict else [],
        "dry_run": True,
    }


def plan_sync_actions(diff: dict[str, Any]) -> dict[str, Any]:
    """Plan sync actions. All actions are proposal-only."""

    if diff["conflict"]:
        actions = ["create_user_approval_event", "do_not_overwrite"]
        status = "conflict"
    elif diff["remote_newer"]:
        actions = ["fetch_remote_metadata", "create_merge_proposal"]
        status = "checkin_available"
    else:
        actions = ["no_op"]
        status = "idle"
    return {
        "owner_did": diff["owner_did"],
        "status": status,
        "actions": actions,
        "requires_user_approval": status in {"conflict", "checkin_available"},
        "automatic_overwrite": False,
        "dry_run": True,
        "local_brain_mutated": False,
        "production_mutated": False,
    }


def apply_sync_plan_dry_run(plan: dict[str, Any]) -> dict[str, Any]:
    """Apply a sync plan as a dry run only."""

    return {
        "applied": False,
        "dry_run": True,
        "planned_actions": list(plan["actions"]),
        "local_brain_mutated": False,
        "production_mutated": False,
        "automatic_overwrite": False,
        "requires_user_approval": plan["requires_user_approval"],
    }
