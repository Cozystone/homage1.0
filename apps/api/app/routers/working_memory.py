from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from packages.cloud_brain.cloud_node_attachment import (
    attach_bundle,
    cleanup_expired_bundles,
    create_cloud_node_bundle,
    detach_bundle,
    graph_overlay,
    list_bundles,
)
from packages.cloud_brain.graph_exchange import run_local_cloud_exchange
from packages.cortex_g2.pipeline import run_cortex_cycle, summarize_cortex_cycle


router = APIRouter(prefix="/api/working-memory", tags=["working-memory"])


class CloudAttachmentCreateRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400)


class CloudAttachmentBundleRequest(BaseModel):
    bundle_id: str = Field(min_length=1, max_length=80)


class LocalCloudExchangeRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400)
    pin_context: bool = False
    allow_web: bool = False
    max_chunks: int = Field(default=1, ge=1, le=4)
    max_latency_ms: int = Field(default=800, ge=100, le=5000)


@router.post("/cloud-attachments/create")
def create_cloud_attachment(request: CloudAttachmentCreateRequest) -> dict:
    bundle = create_cloud_node_bundle(request.query)
    if not bundle.get("nodes"):
        return {
            "state": "no_attachment_available",
            "reason": "No public contributor shard nodes are available.",
            "writes_to_local_brain": False,
        }
    return {"state": "cloud_node_bundle_created", "bundle": bundle}


@router.post("/cloud-attachments/attach")
def attach_cloud_attachment(request: CloudAttachmentBundleRequest) -> dict:
    try:
        bundle = attach_bundle(request.bundle_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    overlay = graph_overlay()
    cortex = run_cortex_cycle(
        str(bundle.get("query") or "GraphRAG evidence"),
        {
            "local_nodes": [],
            "local_edges": [],
            "seed_anchor_nodes": overlay.get("seed_anchor_nodes", []),
            "cloud_attached_nodes": overlay.get("cloud_attached_nodes", []),
            "cloud_attached_edges": overlay.get("cloud_attached_edges", []),
            "working_memory_overlay": overlay.get("working_memory_overlay", {}),
        },
    )
    return {
        "state": "attached",
        "bundle": bundle,
        **overlay,
        "cortex_g2": summarize_cortex_cycle(cortex),
        "retrieval_trace": cortex["retrieval_trace"],
    }


@router.post("/cloud-attachments/detach")
def detach_cloud_attachment(request: CloudAttachmentBundleRequest) -> dict:
    result = detach_bundle(request.bundle_id)
    return {"state": "detached", "result": result, **graph_overlay()}


@router.get("/cloud-attachments")
def cloud_attachments() -> dict:
    cleanup_expired_bundles()
    return list_bundles()


@router.post("/cloud-attachments/clear")
def clear_cloud_attachments() -> dict:
    listed = list_bundles()
    detached = [detach_bundle(bundle_id) for bundle_id in listed.get("active_bundle_ids", [])]
    return {"state": "cleared", "detached": detached, **graph_overlay()}


@router.post("/local-cloud-exchange")
def local_cloud_exchange(request: LocalCloudExchangeRequest) -> dict:
    return run_local_cloud_exchange(
        request.query,
        pin_context=request.pin_context,
        allow_web=request.allow_web,
        max_chunks=request.max_chunks,
        max_latency_ms=request.max_latency_ms,
    )
