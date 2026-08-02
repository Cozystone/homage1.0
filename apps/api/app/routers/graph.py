from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from app.services.alpha_services import alpha_service
from app.services.ingestion_stream import format_sse, graph_event_hub
from packages.cloud_brain.cloud_node_attachment import graph_overlay


router = APIRouter(prefix="/api/graph", tags=["graph"])
MAX_GRAPH_STREAM_LIMIT = 50_000


def _local_brain_initialized() -> bool:
    return os.getenv("ATANOR_LOCAL_BRAIN_INITIALIZED", "").strip().lower() in {"1", "true", "yes", "on"}


@router.get("/subgraph")
def graph_subgraph(
    limit: int = Query(default=900, ge=1, le=MAX_GRAPH_STREAM_LIMIT),
    query: str | None = Query(default=None, min_length=1, max_length=240),
    max_depth: int = Query(default=3, ge=1, le=6),
    max_nodes: int = Query(default=900, ge=1, le=MAX_GRAPH_STREAM_LIMIT),
    center_x: float | None = Query(default=None),
    center_y: float | None = Query(default=None),
    center_z: float | None = Query(default=None),
    radius: float | None = Query(default=None, gt=0),
    include_cloud_attached: bool = Query(default=False),
) -> dict:
    """Live graph view for the web UI.

    Without a query this returns the current long-term memory graph. With a
    query it returns a bounded activation subgraph. Both paths stay behind the
    same `/api/graph/subgraph` contract used by the production web proxy.
    """

    if query:
        result = alpha_service.activate_memory(query, max_nodes=min(max_nodes, limit), max_depth=max_depth)
        return {
            "state": result.get("state", "completed"),
            "source": "activation_subgraph",
            "query": query,
            "nodes": result.get("active_nodes", []),
            "edges": result.get("active_edges", []),
            "trace": result,
        }
    result = alpha_service.memory_graph(limit=limit)
    if include_cloud_attached:
        overlay = graph_overlay()
        mirror_nodes = list(result.get("nodes") or [])
        mirror_edges = list(result.get("edges") or [])
        local_nodes = mirror_nodes if _local_brain_initialized() else []
        local_edges = mirror_edges if _local_brain_initialized() else []
        seed_anchor_nodes = list(overlay.get("seed_anchor_nodes") or [])
        cloud_nodes = list(overlay.get("cloud_attached_nodes") or [])
        cloud_edges = list(overlay.get("cloud_attached_edges") or [])
        result = {
            **result,
            "nodes": [*local_nodes, *seed_anchor_nodes, *cloud_nodes],
            "edges": [*local_edges, *cloud_edges],
            "local_nodes": local_nodes,
            "local_edges": local_edges,
            "local_brain_initialized": _local_brain_initialized(),
            "local_brain_empty": not _local_brain_initialized(),
            "cloud_mirror_excluded_from_local_brain": not _local_brain_initialized(),
            "cloud_mirror_snapshot": {
                "nodes": len(mirror_nodes),
                "edges": len(mirror_edges),
                "source": result.get("source") or result.get("store") or "ghost_shell_mirror",
            },
            "seed_anchor_nodes": seed_anchor_nodes,
            "cloud_attached_nodes": cloud_nodes,
            "cloud_attached_edges": cloud_edges,
            "working_memory_overlay": overlay["working_memory_overlay"],
            "counts": {
                "local_nodes": len(local_nodes),
                "local_edges": len(local_edges),
                "seed_anchor_nodes": len(seed_anchor_nodes),
                "cloud_attached_nodes": len(cloud_nodes),
                "cloud_attached_edges": len(cloud_edges),
            },
        }
    if radius is not None and center_x is not None and center_y is not None and center_z is not None:
        radius_sq = float(radius) * float(radius)
        source_nodes = list(result.get("nodes") or [])
        selected_nodes = []
        for node in source_nodes:
            dx = float(node.get("x") or 0.0) - float(center_x)
            dy = float(node.get("y") or 0.0) - float(center_y)
            dz = float(node.get("z") or 0.0) - float(center_z)
            distance_sq = dx * dx + dy * dy + dz * dz
            if distance_sq <= radius_sq:
                selected_nodes.append((distance_sq, node))
        selected_nodes.sort(key=lambda item: item[0])
        hot_nodes = [node for _distance, node in selected_nodes[:max_nodes]]
        hot_ids = {str(node.get("id") or node.get("node_hash") or "") for node in hot_nodes}
        hot_edges = [
            edge
            for edge in list(result.get("edges") or [])
            if str(edge.get("source") or edge.get("source_hash") or "") in hot_ids
            and str(edge.get("target") or edge.get("target_hash") or "") in hot_ids
        ][: max_nodes * 8]
        result = {
            **result,
            "nodes": hot_nodes,
            "edges": hot_edges,
            "chunk": {
                "mode": "camera_radius",
                "center": {"x": center_x, "y": center_y, "z": center_z},
                "radius": radius,
                "active_node_ceiling": max_nodes,
                "source_node_count": len(source_nodes),
                "culled_node_count": max(0, len(source_nodes) - len(hot_nodes)),
            },
        }
    return {
        **result,
        "state": result.get("state", "completed"),
        "source": "camera_radius_chunk" if radius is not None else "long_term_memory_graph",
    }


@router.get("/stream")
def graph_stream(
    limit: int = Query(default=900, ge=1, le=MAX_GRAPH_STREAM_LIMIT),
    include_cloud_attached: bool = Query(default=False),
) -> dict:
    """JSON snapshot endpoint kept intentionally lightweight for polling clients."""

    result = alpha_service.memory_graph(limit=limit)
    if include_cloud_attached:
        overlay = graph_overlay()
        mirror_nodes = list(result.get("nodes") or [])
        mirror_edges = list(result.get("edges") or [])
        local_nodes = mirror_nodes if _local_brain_initialized() else []
        local_edges = mirror_edges if _local_brain_initialized() else []
        seed_anchor_nodes = list(overlay.get("seed_anchor_nodes") or [])
        cloud_nodes = list(overlay.get("cloud_attached_nodes") or [])
        cloud_edges = list(overlay.get("cloud_attached_edges") or [])
        result = {
            **result,
            "nodes": [*local_nodes, *seed_anchor_nodes, *cloud_nodes],
            "edges": [*local_edges, *cloud_edges],
            "local_nodes": local_nodes,
            "local_edges": local_edges,
            "local_brain_initialized": _local_brain_initialized(),
            "local_brain_empty": not _local_brain_initialized(),
            "cloud_mirror_excluded_from_local_brain": not _local_brain_initialized(),
            "cloud_mirror_snapshot": {
                "nodes": len(mirror_nodes),
                "edges": len(mirror_edges),
                "source": result.get("source") or result.get("store") or "ghost_shell_mirror",
            },
            "seed_anchor_nodes": seed_anchor_nodes,
            "cloud_attached_nodes": cloud_nodes,
            "cloud_attached_edges": cloud_edges,
            "working_memory_overlay": overlay["working_memory_overlay"],
            "counts": {
                "local_nodes": len(local_nodes),
                "local_edges": len(local_edges),
                "seed_anchor_nodes": len(seed_anchor_nodes),
                "cloud_attached_nodes": len(cloud_nodes),
                "cloud_attached_edges": len(cloud_edges),
            },
        }
    return {
        **result,
        "state": result.get("state", "completed"),
        "source": "live_graph_poll_snapshot",
        "stream": "polling_json_v1",
    }


@router.get("/events")
async def graph_events(
    request: Request,
    limit: int = Query(default=5000, ge=1, le=MAX_GRAPH_STREAM_LIMIT),
    metadata_only: bool = Query(default=False),
) -> StreamingResponse:
    """Persistent graph event stream for operator consoles.

    The stream emits an initial graph snapshot, graph build lifecycle events,
    and graph_delta payloads whenever the cleaned-directory watcher rebuilds
    memory. It keeps the graph transport server-sent-event based so the web UI
    can render topology growth without polling.
    """

    async def event_source():
        subscriber_id, queue = await graph_event_hub.subscribe(limit=limit)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    event = await graph_event_hub.heartbeat()
                if metadata_only:
                    event = {
                        **event,
                        "nodes": [],
                        "edges": [],
                        "metadata_only": True,
                    }
                event_type = str(event.get("event_type") or "message")
                yield format_sse(event_type, event)
        finally:
            await graph_event_hub.unsubscribe(subscriber_id)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
