from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from packages.graph_hub.attachment import attach_cartridge, detach_cartridge, list_active_attachments
from packages.graph_hub.audit import list_graph_hub_audit_events
from packages.graph_hub.catalog import get_catalog_item, list_catalog_items, refresh_catalog
from packages.graph_hub.cartridge_exporter import export_semantic_cloud_to_cartridge
from packages.graph_hub.cartridge_mount import (
    attach_cartridge_namespace,
    detach_cartridge_namespace,
    list_mounted_cartridges,
    materialize_cartridge_chunk,
    select_cartridge_chunks,
)
from packages.graph_hub.cartridge_profiler import profile_cartridge_payload, profile_installed_cartridge
from packages.graph_hub.entitlement import (
    expire_subscription,
    grant_free_entitlement,
    grant_local_one_time_entitlement,
    grant_local_subscription_entitlement,
    list_entitlements,
)
from packages.graph_hub.installer import install_cartridge, install_cartridge_from_path, list_installed_cartridges, uninstall_cartridge
from packages.graph_hub.proof import graph_hub_status, run_graph_hub_proof
from packages.graph_hub.sandbox import sandbox_preview
from packages.graph_hub.sandbox_trial import detach_sandbox_trial, get_sandbox_trial, run_sandbox_trial_query, start_sandbox_trial
from packages.graph_hub.synergy import score_cartridge_synergy


router = APIRouter(prefix="/api/graph-hub", tags=["graph-hub"])


class ExportSemanticCloudRequest(BaseModel):
    cartridge_id: str = Field(default="semantic_cloud_kubernetes_demo", min_length=1, max_length=120)
    name: str = Field(default="Semantic Cloud Kubernetes Demo", min_length=1, max_length=200)
    description: str = Field(default="A small real proof-store export from the Semantic Cloud Growth Loop.", max_length=1000)
    pricing_model: Literal["free", "one_time", "subscription"] = "free"
    query: str | None = Field(default=None, max_length=240)
    limit_nodes: int = Field(default=100, ge=1, le=1000)
    limit_edges: int = Field(default=300, ge=0, le=3000)


class InstallFromPathRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1200)


class AttachRequest(BaseModel):
    scope: Literal["session", "workspace", "global"] = "session"
    read_only: bool = True


class CartridgeSelectChunksRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    max_chunks: int = Field(default=4, ge=1, le=16)


class CartridgeMountRequest(BaseModel):
    cartridge_id: str = Field(min_length=1, max_length=160)


class CartridgeMaterializeChunkRequest(BaseModel):
    cartridge_id: str = Field(min_length=1, max_length=160)
    chunk_id: str = Field(min_length=1, max_length=260)
    max_nodes: int = Field(default=1000, ge=1, le=2000)
    max_edges: int = Field(default=2000, ge=0, le=4000)


class CartridgeProfileRequest(BaseModel):
    cartridge: dict[str, Any] | None = None
    offline_inspection: bool = False


class CartridgeSynergyRequest(BaseModel):
    active_context: str | None = Field(default=None, max_length=500)


class TrialStartRequest(BaseModel):
    intent: str | None = Field(default=None, max_length=500)


class TrialQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)


@router.get("/status")
def status() -> dict[str, Any]:
    return graph_hub_status()


@router.get("/plugins")
def capability_plugins() -> dict[str, Any]:
    """Custom Hub device/ato capability plugins with LIVE install status + real disk cost.
    Heavy abilities (face recognition ~1GB, realistic 3D) stay out of the lean base and are
    added by capacity — this endpoint is the honest catalog the Custom Hub renders."""
    from packages.custom_hub.capability_plugins import plugin_status

    return plugin_status()


@router.get("/catalog")
def catalog(
    category: str | None = Query(default=None),
    pricing_model: str | None = Query(default=None),
    query: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    return list_catalog_items(category=category, pricing_model=pricing_model, query=query)


@router.get("/catalog/{cartridge_id}")
def catalog_item(cartridge_id: str) -> dict[str, Any]:
    try:
        return get_catalog_item(cartridge_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/catalog/refresh")
def refresh() -> dict[str, Any]:
    return refresh_catalog()


@router.post("/export/semantic-cloud")
def export_semantic_cloud(request: ExportSemanticCloudRequest) -> dict[str, Any]:
    return export_semantic_cloud_to_cartridge(
        request.cartridge_id,
        request.name,
        request.description,
        request.pricing_model,
        query=request.query,
        limit_nodes=request.limit_nodes,
        limit_edges=request.limit_edges,
    )


@router.post("/entitlements/free/{cartridge_id}")
def entitlement_free(cartridge_id: str) -> dict[str, Any]:
    return grant_free_entitlement(cartridge_id)


@router.post("/entitlements/local-one-time-simulation/{cartridge_id}")
def entitlement_purchase(cartridge_id: str) -> dict[str, Any]:
    return grant_local_one_time_entitlement(cartridge_id)


@router.post("/entitlements/local-subscription-simulation/{cartridge_id}")
def entitlement_subscribe(cartridge_id: str) -> dict[str, Any]:
    return grant_local_subscription_entitlement(cartridge_id)


@router.post("/entitlements/expire/{cartridge_id}")
def entitlement_expire(cartridge_id: str) -> dict[str, Any]:
    return expire_subscription(cartridge_id)


@router.get("/entitlements")
def entitlements() -> list[dict[str, Any]]:
    return list_entitlements()


@router.post("/install/{cartridge_id}")
def install(cartridge_id: str) -> dict[str, Any]:
    try:
        return install_cartridge(cartridge_id)
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/install-from-path")
def install_path(request: InstallFromPathRequest) -> dict[str, Any]:
    try:
        return install_cartridge_from_path(request.path)
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/uninstall/{cartridge_id}")
def uninstall(cartridge_id: str) -> dict[str, Any]:
    return uninstall_cartridge(cartridge_id)


@router.get("/installed")
def installed() -> list[dict[str, Any]]:
    return list_installed_cartridges()


@router.post("/sandbox-preview/{cartridge_id}")
def sandbox(cartridge_id: str) -> dict[str, Any]:
    try:
        return sandbox_preview(cartridge_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/attach/{cartridge_id}")
def attach(cartridge_id: str, request: AttachRequest) -> dict[str, Any]:
    try:
        return attach_cartridge(cartridge_id, request.scope, request.read_only)
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/detach/{cartridge_id}")
def detach(cartridge_id: str) -> dict[str, Any]:
    return detach_cartridge(cartridge_id)


@router.get("/attachments")
def attachments() -> list[dict[str, Any]]:
    return list_active_attachments()


@router.post("/cartridges/attach/{cartridge_id}")
def cartridge_mount_attach(cartridge_id: str) -> dict[str, Any]:
    return attach_cartridge_namespace(cartridge_id)


@router.post("/cartridges/attach")
def cartridge_mount_attach_body(request: CartridgeMountRequest) -> dict[str, Any]:
    return attach_cartridge_namespace(request.cartridge_id)


@router.post("/cartridges/detach/{cartridge_id}")
def cartridge_mount_detach(cartridge_id: str) -> dict[str, Any]:
    return detach_cartridge_namespace(cartridge_id)


@router.post("/cartridges/detach")
def cartridge_mount_detach_body(request: CartridgeMountRequest) -> dict[str, Any]:
    return detach_cartridge_namespace(request.cartridge_id)


@router.get("/cartridges/mounted")
def cartridge_mounts() -> list[dict[str, Any]]:
    return list_mounted_cartridges()


@router.post("/cartridges/select-chunks")
def cartridge_select_chunks(request: CartridgeSelectChunksRequest) -> dict[str, Any]:
    return select_cartridge_chunks(request.query, max_chunks=request.max_chunks)


@router.post("/cartridges/materialize-chunk")
def cartridge_materialize_chunk(request: CartridgeMaterializeChunkRequest) -> dict[str, Any]:
    try:
        return materialize_cartridge_chunk(
            request.cartridge_id,
            request.chunk_id,
            max_nodes=request.max_nodes,
            max_edges=request.max_edges,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/cartridges/profile")
def cartridge_profile_payload(request: CartridgeProfileRequest) -> dict[str, Any]:
    if request.cartridge is None:
        raise HTTPException(status_code=400, detail="cartridge_payload_required")
    return profile_cartridge_payload(request.cartridge, full_load_performed=True)


@router.get("/cartridges/{cartridge_id}/profile")
def cartridge_profile(cartridge_id: str, offline_inspection: bool = Query(default=False)) -> dict[str, Any]:
    try:
        return profile_installed_cartridge(cartridge_id, offline_inspection=offline_inspection)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/cartridges/{cartridge_id}/synergy")
def cartridge_synergy(cartridge_id: str, request: CartridgeSynergyRequest | None = None) -> dict[str, Any]:
    try:
        return score_cartridge_synergy(cartridge_id, active_context=(request.active_context if request else None))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/cartridges/{cartridge_id}/trial/start")
def trial_start(cartridge_id: str, request: TrialStartRequest | None = None) -> dict[str, Any]:
    try:
        return start_sandbox_trial(cartridge_id, intent=(request.intent if request else None))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/trials/{session_id}")
def trial_get(session_id: str) -> dict[str, Any]:
    try:
        return get_sandbox_trial(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/trials/{session_id}/query")
def trial_query(session_id: str, request: TrialQueryRequest) -> dict[str, Any]:
    try:
        return run_sandbox_trial_query(session_id, request.query)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/trials/{session_id}/detach")
def trial_detach(session_id: str) -> dict[str, Any]:
    try:
        return detach_sandbox_trial(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/audit")
def audit(limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
    return list_graph_hub_audit_events(limit)


@router.post("/proof")
def proof() -> dict[str, Any]:
    return run_graph_hub_proof()
