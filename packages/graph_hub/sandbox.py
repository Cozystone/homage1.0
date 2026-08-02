from __future__ import annotations

from typing import Any

from packages.cloud_brain.semantic_store import SEMANTIC_STORE_TRUST_STATE

from .cartridge_format import validate_cartridge_schema
from .entitlement import check_entitlement
from .installer import get_installed_cartridge
from .models import read_json
from .registry import find_cartridge_file


def sandbox_preview(cartridge_id: str) -> dict[str, Any]:
    path = find_cartridge_file(cartridge_id)
    if not path:
        raise FileNotFoundError(cartridge_id)
    cartridge = read_json(path, {})
    validation = validate_cartridge_schema(cartridge)
    permissions = cartridge.get("permissions") or {}
    safety = cartridge.get("safety") or {}
    provenance = cartridge.get("provenance") or {}
    source_type = str(provenance.get("source_type") or "")
    source_authoritative = source_type not in {
        SEMANTIC_STORE_TRUST_STATE,
        "semantic_cloud_proof_store",
    } or (
        provenance.get("independent_source_attestation") is True
        and provenance.get("authoritative_for_answer") is True
    )
    attach_allowed_by_cartridge = permissions.get("attach_to_working_memory") is not False
    pricing_model = str((cartridge.get("pricing") or {}).get("model") or "free")
    entitlement = check_entitlement(cartridge_id, pricing_model)
    contents = cartridge.get("contents") or {}
    semantic = contents.get("semantic_graph") or {}
    surface = contents.get("surface_graph") or {}
    warnings: list[str] = []
    if not validation["valid"]:
        warnings.extend(validation["errors"])
    if permissions.get("write_local_brain"):
        warnings.append("local_write_requires_explicit_user_approval")
    if safety.get("risk_level") in {"high", "unknown"}:
        warnings.append("risk_review_required")
    if not source_authoritative:
        warnings.append("source_attestation_required")
    if not attach_allowed_by_cartridge:
        warnings.append("working_memory_attach_not_permitted")
    if not entitlement.get("attach_allowed"):
        warnings.append(f"entitlement_not_active:{entitlement.get('status')}")
    return {
        "cartridge_id": cartridge_id,
        "safe_to_attach": (
            validation["valid"]
            and not permissions.get("write_local_brain")
            and bool(entitlement.get("attach_allowed"))
            and attach_allowed_by_cartridge
            and source_authoritative
        ),
        "risk_level": safety.get("risk_level", "unknown"),
        "source_authoritative": source_authoritative,
        "warnings": warnings,
        "semantic_preview": (semantic.get("nodes") or [])[:6],
        "surface_preview": (surface.get("constructions") or [])[:6],
        "permissions": permissions,
        "estimated_nodes": len(semantic.get("nodes") or []),
        "estimated_edges": len(semantic.get("edges") or []),
        "installed": bool(get_installed_cartridge(cartridge_id)),
        "entitlement_status": entitlement.get("status"),
    }
