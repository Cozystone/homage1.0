from __future__ import annotations

from pathlib import Path
from typing import Any

from packages.cloud_brain.ingestion import DEFAULT_CLOUD_ROOT
from packages.cloud_brain.sphere_index import (
    MAX_LOGICAL_NODES,
    TRILLION_TARGET,
    load_logical_cloud_edges,
    load_logical_cloud_nodes,
    logical_cloud_manifest,
)
from packages.cloud_brain.sphere_tiles import (
    SphereTileAddress,
    build_tile,
    build_tile_from_id,
    child_addresses,
    node_in_tile,
    parse_tile_id,
)


def sphere_manifest(
    *,
    cloud_root: str | Path = DEFAULT_CLOUD_ROOT,
    memory_db_path: str | Path = "data/memory/homage.db",
) -> dict[str, Any]:
    nodes = load_logical_cloud_nodes(cloud_root=cloud_root, memory_db_path=memory_db_path, limit=50_000)
    edges = load_logical_cloud_edges(nodes, cloud_root=cloud_root, memory_db_path=memory_db_path, limit=100_000)
    manifest = logical_cloud_manifest(cloud_root=cloud_root)
    manifest.update(
        {
            "logical_total_nodes": str(len(nodes)),
            "logical_total_edges": str(len(edges)),
            "actual_materialized_nodes": len(nodes),
            "rendered_nodes": 0,
            "max_logical_nodes": MAX_LOGICAL_NODES,
            "trillion_target": TRILLION_TARGET,
        }
    )
    return manifest


def get_sphere_tile(
    *,
    level: int = 0,
    x: int = 0,
    y: int = 0,
    tile_id: str | None = None,
    cloud_root: str | Path = DEFAULT_CLOUD_ROOT,
    memory_db_path: str | Path = "data/memory/homage.db",
) -> dict[str, Any]:
    nodes = load_logical_cloud_nodes(cloud_root=cloud_root, memory_db_path=memory_db_path, limit=50_000)
    if tile_id:
        return build_tile_from_id(tile_id, nodes=nodes)
    return build_tile(SphereTileAddress(level=level, x=x, y=y), nodes=nodes)


def get_sphere_tile_children(
    tile_id: str,
    *,
    cloud_root: str | Path = DEFAULT_CLOUD_ROOT,
    memory_db_path: str | Path = "data/memory/homage.db",
) -> dict[str, Any]:
    nodes = load_logical_cloud_nodes(cloud_root=cloud_root, memory_db_path=memory_db_path, limit=50_000)
    address = parse_tile_id(tile_id)
    children = [build_tile(child, nodes=nodes) for child in child_addresses(address)]
    return {
        "tile_id": tile_id,
        "children": children,
        "compression_used": False,
        "semantic_aggregate_nodes_used": False,
    }


def _node_payload(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "cloud_node_id": str(node["cloud_node_id"]),
        "logical_ordinal": str(node["logical_ordinal"]),
        "label": str(node.get("label") or node["cloud_node_id"]),
        "x": float(node.get("x") or 0.0),
        "y": float(node.get("y") or 0.0),
        "z": float(node.get("z") or 0.0),
        "source_scope": str(node.get("source_scope") or "cloud"),
        "trust_state": str(node.get("trust_state") or "unverified"),
        "verification_state": str(node.get("verification_state") or "web_seed_pending"),
    }


def materialize_sphere_tile(
    tile_id: str,
    *,
    zoom_level: int,
    render_budget_nodes: int,
    render_budget_edges: int,
    cloud_root: str | Path = DEFAULT_CLOUD_ROOT,
    memory_db_path: str | Path = "data/memory/homage.db",
) -> dict[str, Any]:
    budget_nodes = max(0, min(int(render_budget_nodes), 50_000))
    budget_edges = max(0, min(int(render_budget_edges), 100_000))
    address = parse_tile_id(tile_id)
    nodes = load_logical_cloud_nodes(cloud_root=cloud_root, memory_db_path=memory_db_path, limit=50_000)
    contained = [node for node in nodes if node_in_tile(node, address)]
    tile = build_tile(address, nodes=nodes)
    child_tiles = [build_tile(child, nodes=nodes) for child in child_addresses(address)]

    if zoom_level <= 0:
        render_mode = "shell"
        materialized_nodes: list[dict[str, Any]] = []
        materialized_edges: list[dict[str, Any]] = []
        visible_children: list[dict[str, Any]] = []
    elif zoom_level < 4 and child_tiles:
        render_mode = "child_tiles"
        materialized_nodes = []
        materialized_edges = []
        visible_children = child_tiles
    else:
        render_mode = "actual_nodes"
        selected_nodes = contained[:budget_nodes]
        node_ids = {str(node["cloud_node_id"]) for node in selected_nodes}
        edges = load_logical_cloud_edges(nodes, cloud_root=cloud_root, memory_db_path=memory_db_path, limit=budget_edges)
        materialized_nodes = [_node_payload(node) for node in selected_nodes]
        materialized_edges = [
            edge for edge in edges
            if str(edge.get("source")) in node_ids and str(edge.get("target")) in node_ids
        ][:budget_edges]
        visible_children = []

    return {
        "tile_id": tile_id,
        "zoom_level": zoom_level,
        "render_mode": render_mode,
        "logical_nodes_addressable": str(len(contained)),
        "materialized_nodes": materialized_nodes,
        "materialized_edges": materialized_edges,
        "child_tiles": visible_children,
        "tile": tile,
        "render_budget_nodes": budget_nodes,
        "render_budget_edges": budget_edges,
        "rendered_nodes": len(materialized_nodes),
        "rendered_edges": len(materialized_edges),
        "all_nodes_rendered": len(materialized_nodes) == len(contained) and len(contained) <= budget_nodes,
        "compression_used": False,
        "semantic_aggregate_nodes_used": False,
    }


def get_cloud_node(
    cloud_node_id: str,
    *,
    cloud_root: str | Path = DEFAULT_CLOUD_ROOT,
    memory_db_path: str | Path = "data/memory/homage.db",
) -> dict[str, Any]:
    nodes = load_logical_cloud_nodes(cloud_root=cloud_root, memory_db_path=memory_db_path, limit=50_000)
    for node in nodes:
        if str(node.get("cloud_node_id")) == cloud_node_id:
            return {"found": True, "node": _node_payload(node), "compression_used": False}
    return {"found": False, "node": None, "compression_used": False}
