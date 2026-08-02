from __future__ import annotations

from typing import Any

from packages.cloud_brain.semantic_store import (
    SEMANTIC_STORE_TRUST_STATE,
    SEMANTIC_STORE_VERIFICATION_STATE,
)

from .audit import append_graph_hub_audit_event
from .entitlement import check_entitlement
from .installer import get_installed_cartridge
from .models import GRAPH_HUB_ROOT, read_json, stable_id, utc_now_iso, write_json
from .sandbox import sandbox_preview


ATTACHMENTS_PATH = GRAPH_HUB_ROOT / "attachments" / "active_attachments.json"


def _cartridge_authority(cartridge: dict[str, Any]) -> dict[str, Any]:
    provenance = (
        cartridge.get("provenance")
        if isinstance(cartridge.get("provenance"), dict)
        else {}
    )
    source_type = str(provenance.get("source_type") or "")
    candidate_origin = source_type in {
        SEMANTIC_STORE_TRUST_STATE,
        "semantic_cloud_proof_store",
    }
    independently_attested = (
        provenance.get("independent_source_attestation") is True
        and provenance.get("authoritative_for_answer") is True
    )
    if candidate_origin and not independently_attested:
        return {
            "trust_state": SEMANTIC_STORE_TRUST_STATE,
            "verification_state": SEMANTIC_STORE_VERIFICATION_STATE,
            "independent_source_attestation": False,
            "authoritative_for_answer": False,
        }
    return {
        "trust_state": "cartridge_attached",
        "verification_state": "read_only_working_memory",
        "independent_source_attestation": independently_attested,
        "authoritative_for_answer": independently_attested,
    }


def _load() -> dict[str, dict[str, Any]]:
    payload = read_json(ATTACHMENTS_PATH, {})
    return payload if isinstance(payload, dict) else {}


def _save(payload: dict[str, dict[str, Any]]) -> None:
    write_json(ATTACHMENTS_PATH, payload)


def _load_installed_cartridge(cartridge_id: str) -> dict[str, Any]:
    installed = get_installed_cartridge(cartridge_id)
    if not installed:
        raise FileNotFoundError(f"not_installed:{cartridge_id}")
    return read_json(__import__("pathlib").Path(installed["path"]), {})


def attach_cartridge(cartridge_id: str, scope: str = "session", read_only: bool = True) -> dict[str, Any]:
    if scope not in {"session", "workspace", "global"}:
        raise ValueError("invalid_scope")
    if not read_only:
        raise PermissionError("local_write_requires_explicit_user_approval")
    cartridge = _load_installed_cartridge(cartridge_id)
    pricing_model = str((cartridge.get("pricing") or {}).get("model") or "free")
    entitlement = check_entitlement(cartridge_id, pricing_model)
    if not entitlement.get("attach_allowed"):
        raise PermissionError(f"entitlement_not_active:{entitlement.get('status')}")
    preview = sandbox_preview(cartridge_id)
    if not preview["safe_to_attach"]:
        raise PermissionError("sandbox_not_safe_to_attach")
    semantic = ((cartridge.get("contents") or {}).get("semantic_graph") or {})
    attachment = {
        "attachment_id": stable_id("gha", f"{cartridge_id}:{scope}"),
        "cartridge_id": cartridge_id,
        "scope": scope,
        "attached_at": utc_now_iso(),
        "read_only": True,
        "local_brain_write": False,
        "temporary": True,
        "working_memory_nodes": len(semantic.get("nodes") or []),
        "working_memory_edges": len(semantic.get("edges") or []),
        "status": "attached",
    }
    attachments = _load()
    attachments[cartridge_id] = attachment
    _save(attachments)
    append_graph_hub_audit_event("attached", cartridge_id, {"scope": scope, "read_only": True})
    return attachment


def detach_cartridge(cartridge_id: str) -> dict[str, Any]:
    attachments = _load()
    removed = attachments.pop(cartridge_id, None)
    _save(attachments)
    append_graph_hub_audit_event("detached", cartridge_id, {"had_attachment": bool(removed)})
    return {"cartridge_id": cartridge_id, "status": "detached", "local_brain_write": False}


def list_active_attachments() -> list[dict[str, Any]]:
    refreshed: dict[str, dict[str, Any]] = {}
    for cartridge_id, attachment in _load().items():
        installed = get_installed_cartridge(cartridge_id)
        if not installed:
            attachment = {**attachment, "status": "disabled"}
        else:
            cartridge = read_json(__import__("pathlib").Path(installed["path"]), {})
            entitlement = check_entitlement(cartridge_id, str((cartridge.get("pricing") or {}).get("model") or "free"))
            if not entitlement.get("attach_allowed"):
                attachment = {**attachment, "status": "expired"}
        refreshed[cartridge_id] = attachment
    _save(refreshed)
    return list(refreshed.values())


def get_attachment_status(cartridge_id: str) -> dict[str, Any] | None:
    for attachment in list_active_attachments():
        if attachment.get("cartridge_id") == cartridge_id:
            return attachment
    return None


def attachment_graph_payload() -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for attachment in list_active_attachments():
        if attachment.get("status") != "attached":
            continue
        cartridge_id = str(attachment["cartridge_id"])
        installed = get_installed_cartridge(cartridge_id)
        if not installed:
            continue
        cartridge = read_json(__import__("pathlib").Path(installed["path"]), {})
        authority = _cartridge_authority(cartridge)
        semantic = ((cartridge.get("contents") or {}).get("semantic_graph") or {})
        for node in semantic.get("nodes") or []:
            nodes.append({
                **node,
                "id": f"graph-cartridge:{cartridge_id}:{node.get('id')}",
                "layer": "graph_cartridge",
                "temporary": True,
                "persistent": False,
                "source_cartridge_id": cartridge_id,
                "local_brain_write": False,
                **authority,
            })
        for edge in semantic.get("edges") or []:
            edges.append({
                **edge,
                "id": f"graph-cartridge-edge:{cartridge_id}:{edge.get('id')}",
                "source": f"graph-cartridge:{cartridge_id}:{edge.get('source')}",
                "target": f"graph-cartridge:{cartridge_id}:{edge.get('target')}",
                "layer": "graph_cartridge",
                "temporary": True,
                "persistent": False,
                "source_cartridge_id": cartridge_id,
                "local_brain_write": False,
                **authority,
            })
    return {"nodes": nodes, "edges": edges}
