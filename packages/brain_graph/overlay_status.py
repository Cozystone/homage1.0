from __future__ import annotations

from typing import Any

from packages.cloud_brain.cloud_node_attachment import graph_overlay, list_bundles


def get_overlay_status() -> dict[str, Any]:
    overlay = graph_overlay()
    listed = list_bundles(include_detached=True)
    active_bundles = [bundle for bundle in listed.get("bundles", []) if bundle.get("attached")]
    latest = active_bundles[-1] if active_bundles else None
    working = overlay.get("working_memory_overlay", {})
    return {
        "latest_query_id": latest.get("bundle_id") if latest else None,
        "working_memory_active": bool(working.get("active")),
        "local_active_nodes": 0,
        "cloud_attached_nodes": int(working.get("cloud_attached_nodes") or 0),
        "cloud_attached_edges": int(working.get("cloud_attached_edges") or 0),
        "seed_anchor_nodes": int(working.get("seed_anchor_nodes") or 0),
        "surface_summary_available": False,
        "local_brain_write": False,
        "cloud_attached_counts_as_local": False,
        "last_attach_time": latest.get("attached_at") if latest else None,
        "last_detach_time": None,
        "trace_available": bool(active_bundles),
        "honesty": {
            "cloud_attached_is_temporary": True,
            "cloud_attached_counts_as_local": False,
            "local_brain_write": False,
            "surface_graph_full_render_disabled": True,
        },
    }
