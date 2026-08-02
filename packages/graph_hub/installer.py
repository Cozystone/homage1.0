from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .audit import append_graph_hub_audit_event
from .cartridge_format import validate_cartridge_schema, verify_cartridge_checksum
from .entitlement import check_entitlement
from .models import GRAPH_HUB_ROOT, cartridge_path, read_json, utc_now_iso, write_json
from .registry import find_cartridge_file, refresh_local_catalog


INSTALLED_REGISTRY_PATH = GRAPH_HUB_ROOT / "installed" / "installed_registry.json"


def _load_registry() -> dict[str, dict[str, Any]]:
    payload = read_json(INSTALLED_REGISTRY_PATH, {})
    return payload if isinstance(payload, dict) else {}


def _save_registry(payload: dict[str, dict[str, Any]]) -> None:
    write_json(INSTALLED_REGISTRY_PATH, payload)


def _installed_stats(cartridge: dict[str, Any]) -> dict[str, int]:
    contents = cartridge.get("contents") or {}
    semantic = contents.get("semantic_graph") or {}
    surface = contents.get("surface_graph") or {}
    return {
        "semantic_nodes": len(semantic.get("nodes") or []),
        "semantic_edges": len(semantic.get("edges") or []),
        "surface_constructions": len(surface.get("constructions") or []),
        "reasoning_patterns": len(contents.get("reasoning_patterns") or []),
    }


def install_cartridge(cartridge_id: str) -> dict[str, Any]:
    refresh_local_catalog()
    source = find_cartridge_file(cartridge_id)
    if not source:
        raise FileNotFoundError(cartridge_id)
    return install_cartridge_from_path(str(source))


def install_cartridge_from_path(path: str) -> dict[str, Any]:
    source = Path(path)
    cartridge = read_json(source, {})
    validation = validate_cartridge_schema(cartridge)
    if not validation["valid"]:
        raise ValueError(";".join(validation["errors"]))
    pricing_model = str((cartridge.get("pricing") or {}).get("model") or "free")
    entitlement = check_entitlement(str(cartridge["cartridge_id"]), pricing_model)
    if not entitlement.get("install_allowed"):
        raise PermissionError(f"entitlement_required:{entitlement.get('status')}")
    destination = cartridge_path(str(cartridge["cartridge_id"]), "installed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    registry = _load_registry()
    installed = {
        "cartridge_id": cartridge["cartridge_id"],
        "installed_at": utc_now_iso(),
        "version": cartridge.get("version", "0.1.0"),
        "path": str(destination),
        "enabled": True,
        "entitlement_status": entitlement.get("status"),
        "permissions": cartridge.get("permissions") or {},
        "safety": cartridge.get("safety") or {},
        "stats": _installed_stats(cartridge),
        "checksum_valid": verify_cartridge_checksum(destination),
        "local_brain_write": False,
    }
    registry[str(cartridge["cartridge_id"])] = installed
    _save_registry(registry)
    append_graph_hub_audit_event("installed", str(cartridge["cartridge_id"]), {"path": str(destination)})
    return installed


def uninstall_cartridge(cartridge_id: str) -> dict[str, Any]:
    from .attachment import detach_cartridge

    detach_cartridge(cartridge_id)
    registry = _load_registry()
    installed = registry.pop(cartridge_id, None)
    _save_registry(registry)
    path = cartridge_path(cartridge_id, "installed")
    if path.exists():
        path.unlink()
    append_graph_hub_audit_event("uninstalled", cartridge_id, {"had_install": bool(installed)})
    return {"cartridge_id": cartridge_id, "uninstalled": True, "detached_first": True, "local_brain_write": False}


def list_installed_cartridges() -> list[dict[str, Any]]:
    return list(_load_registry().values())


def get_installed_cartridge(cartridge_id: str) -> dict[str, Any] | None:
    return _load_registry().get(cartridge_id)
