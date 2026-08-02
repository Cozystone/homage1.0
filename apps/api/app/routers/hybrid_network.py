from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from knowledge_bakery import memory_status

from app.services.alpha_services import alpha_service
from app.services.edge_compute_broker import default_edge_compute_broker
from app.services.hybrid_network_manager import default_hybrid_network_manager, resolve_cloud_knowledge
from packages.atlas_p2p_sandbox.brain_link import brain_link_status


router = APIRouter(prefix="/api/network", tags=["hybrid-network"])


@router.get("/brain-link")
def brain_link() -> dict[str, Any]:
    """Brain Link status graph + compute-share operation over the local P2P sandbox.
    Shares idle compute only with eligible (online, public, trusted) peers; excludes
    low-trust and private peers by the real gates. Local-only, no WAN path."""
    cap = default_edge_compute_broker.current_capacity()
    return brain_link_status(self_peer_id=cap.peer_id, idle=cap.idle, task_types=list(cap.task_types))


class ResolveNetworkRequest(BaseModel):
    query: str


@router.get("/status")
def hybrid_network_status() -> dict[str, Any]:
    return {
        "state": "ready",
        **default_hybrid_network_manager.status(),
        "track_1": "metadata_signaling_server_optional",
        "track_2": "edge_payload_p2p_or_signed_fragment",
        "uploads_raw_query": False,
        "uploads_private_payload": False,
    }


@router.post("/resolve")
async def hybrid_network_resolve(request: ResolveNetworkRequest) -> dict[str, Any]:
    return await resolve_cloud_knowledge(request.query)


@router.get("/edge/status")
def edge_compute_status() -> dict[str, Any]:
    capacity = default_edge_compute_broker.current_capacity()
    memory = memory_status()
    ghost_shell = memory.get("ghost_shell") or {
        "system_state": "GHOST SHELL EMPTY",
        "control_plane_hashes": 0,
        "payload_vault_records": 0,
    }
    graphrag = alpha_service.graphrag_status().get("result") or {}
    fetch_sequence = graphrag.get("fetch_sequence") or graphrag.get("retrieval_trace", {}).get("fetch_sequence") or []
    return {
        "state": "ready",
        "architecture": "edge_compute_broker",
        "cloud_required": False,
        "capacity": capacity.to_metadata(),
        "ghost_shell": {
            **ghost_shell,
            "logs": [
                "SYSTEM STATE: GHOST SHELL ACTIVE" if ghost_shell.get("system_state") == "GHOST SHELL ACTIVE" else "SYSTEM STATE: GHOST SHELL EMPTY",
                f"CONTROL PLANE: Loaded {ghost_shell.get('control_plane_hashes', 0)} Schematic Hashes (Memory: Minimal)",
                "DATA PLANE: Vaulting Payloads to Edge Storage",
                *fetch_sequence,
            ],
        },
    }


@router.post("/edge/advertise")
async def edge_compute_advertise() -> dict[str, Any]:
    return await default_edge_compute_broker.advertise_if_idle()
