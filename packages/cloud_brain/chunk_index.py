from __future__ import annotations

from collections import Counter
import math
import os
import re
from typing import Any

DEFAULT_SHELL_CHUNK_TARGET = 128
MAX_SHELL_CHUNK_TARGET = 384
ONION_LAYER_RADII = (0.38, 0.58, 0.78, 1.0)
ONION_LAYER_NAMES = ("inner", "middle", "outer", "surface")


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return cleaned[:28] or "default"


def _distribute_count(total: int, weights: list[int]) -> list[int]:
    if not weights:
        return []
    total = max(0, int(total))
    weight_total = max(1, sum(max(1, weight) for weight in weights))
    values = [max(0, int(total * max(1, weight) / weight_total)) for weight in weights]
    remainder = total - sum(values)
    for index in range(max(0, remainder)):
        values[index % len(values)] += 1
    return values


def _shell_chunk_target(node_total: int, base_chunk_count: int, requested: int | None) -> int:
    raw_target = requested
    if raw_target is None:
        try:
            raw_target = int(os.environ.get("ATANOR_CLOUD_SHELL_CHUNK_TARGET", DEFAULT_SHELL_CHUNK_TARGET))
        except ValueError:
            raw_target = DEFAULT_SHELL_CHUNK_TARGET
    target = max(1, min(MAX_SHELL_CHUNK_TARGET, int(raw_target)))
    if node_total >= target:
        return target
    return max(1, min(target, max(base_chunk_count, node_total)))


def _fibonacci_shell_angles(index: int, total: int) -> tuple[float, float]:
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    z = 1.0 - (2.0 * (index + 0.5) / max(1, total))
    z = max(-1.0, min(1.0, z))
    theta = (index * golden_angle) % (math.pi * 2.0)
    phi = math.acos(z)
    return math.degrees(theta), math.degrees(phi)


def _fibonacci_shell_point(index: int, total: int, radius: float) -> tuple[float, float, float, float, float]:
    theta_degrees, phi_degrees = _fibonacci_shell_angles(index, total)
    theta = math.radians(theta_degrees)
    phi = math.radians(phi_degrees)
    x = math.sin(phi) * math.cos(theta) * radius
    y = math.cos(phi) * radius
    z = math.sin(phi) * math.sin(theta) * radius
    return x, y, z, theta_degrees, phi_degrees


def _chunk_geometry_metrics(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    coordinates: list[tuple[float, float, float]] = []
    for chunk in chunks:
        try:
            x = float(chunk.get("x"))
            y = float(chunk.get("y"))
            z = float(chunk.get("z"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(x) and math.isfinite(y) and math.isfinite(z):
            coordinates.append((x, y, z))
    if not coordinates:
        return {
            "x_span": 0.0,
            "y_span": 0.0,
            "z_span": 0.0,
            "radius_min": 0.0,
            "radius_max": 0.0,
            "radius_span": 0.0,
            "spherical_uniformity_score": 0.0,
            "planar_collapse_score": 1.0,
        }
    xs = [point[0] for point in coordinates]
    ys = [point[1] for point in coordinates]
    zs = [point[2] for point in coordinates]
    radii = [math.sqrt((x * x) + (y * y) + (z * z)) for x, y, z in coordinates]
    spans = [max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)]
    max_span = max(spans)
    min_span = min(spans)
    axis_balance = min_span / max(max_span, 0.0001)
    radius_min = min(radii)
    radius_max = max(radii)
    radius_span = radius_max - radius_min
    radial_depth = min(1.0, radius_span / max(radius_max, 0.0001))
    return {
        "x_span": round(spans[0], 5),
        "y_span": round(spans[1], 5),
        "z_span": round(spans[2], 5),
        "radius_min": round(radius_min, 5),
        "radius_max": round(radius_max, 5),
        "radius_span": round(radius_span, 5),
        "spherical_uniformity_score": round(max(0.0, min(1.0, axis_balance * 0.72 + radial_depth * 0.28)), 5),
        "planar_collapse_score": round(max(0.0, min(1.0, 1.0 - axis_balance)), 5),
    }


def build_chunk_index(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    logical_node_count: int | None = None,
    logical_relation_count: int | None = None,
    max_shell_chunks: int | None = None,
) -> dict[str, Any]:
    """Build a tiny viewport index from already materialized sample nodes.

    Chunks are render/read containers only. They are not semantic aggregate
    nodes and are never counted as Cloud Brain graph nodes.
    """
    chunk_counts: Counter[str] = Counter()
    edge_counts: Counter[str] = Counter()
    node_to_chunk: dict[str, str] = {}

    for node in nodes:
        metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
        chunk_id = str(
            metadata.get("domain_cluster_id")
            or metadata.get("cluster_id")
            or node.get("cluster_id")
            or metadata.get("planetary_domain")
            or node.get("planetary_domain")
            or metadata.get("chunk_id")
            or "cloud_chunk_default"
        )
        node_id = str(node.get("id") or node.get("concept_id") or "")
        if node_id:
            node_to_chunk[node_id] = chunk_id
        chunk_counts[chunk_id] += 1

    for edge in edges:
        source_chunk = node_to_chunk.get(str(edge.get("source")))
        target_chunk = node_to_chunk.get(str(edge.get("target")))
        if source_chunk and source_chunk == target_chunk:
            edge_counts[source_chunk] += 1

    sorted_chunks = sorted(chunk_counts.items(), key=lambda item: (-item[1], item[0]))
    if not sorted_chunks and logical_node_count:
        sorted_chunks = [("cloud_chunk_default", 1)]
    if not sorted_chunks:
        return {
            "chunks": [],
            "density_chunks": [],
            "active_chunk_count": 0,
            "visible_scale_chunk_count": 0,
            "logical_node_count": 0,
            "stored_relation_count": 0,
            "materialized_node_count": len(nodes),
            "materialized_relation_count": len(edges),
            "render_mode": "spherical_lod_shell",
            "semantic_aggregate_nodes_used": False,
            "compression_used": False,
            "all_nodes_rendered": False,
        }

    node_total = max(int(logical_node_count or 0), sum(chunk_counts.values()))
    relation_total = max(int(logical_relation_count or 0), sum(edge_counts.values()))
    shell_target = _shell_chunk_target(node_total, len(sorted_chunks), max_shell_chunks)
    shell_inputs: list[tuple[str, int]] = []
    for index in range(shell_target):
        chunk_id, count = sorted_chunks[index % len(sorted_chunks)]
        shell_inputs.append((chunk_id, count))
    node_weights = [max(1, count) for _, count in shell_inputs]
    relation_weights = [max(1, int(edge_counts.get(chunk_id, 0)) or count) for chunk_id, count in shell_inputs]
    distributed_nodes = _distribute_count(node_total, node_weights)
    distributed_relations = _distribute_count(relation_total, relation_weights)

    chunks: list[dict[str, Any]] = []
    density_chunks: list[dict[str, Any]] = []
    max_nodes_in_chunk = max(distributed_nodes or [1])
    for index, (chunk_id, count) in enumerate(shell_inputs):
        represented_nodes = int(distributed_nodes[index] if index < len(distributed_nodes) else count)
        represented_relations = int(distributed_relations[index] if index < len(distributed_relations) else edge_counts.get(chunk_id, 0))
        lod_level = 1 if represented_nodes < 1_000 else 2 if represented_nodes < 25_000 else 3
        density = min(1.0, math.log1p(max(1, represented_nodes)) / math.log1p(max(2, max_nodes_in_chunk)))
        onion_layer_index = index % len(ONION_LAYER_RADII)
        onion_radius = ONION_LAYER_RADII[onion_layer_index]
        x, y, z, theta_center, phi_center = _fibonacci_shell_point(index, len(shell_inputs), onion_radius)
        angular_scale = math.sqrt(max(1, len(shell_inputs)))
        theta_width = max(3.0, min(18.0, 360.0 / angular_scale * 0.42))
        phi_width = max(2.5, min(14.0, 180.0 / angular_scale * 0.42))
        theta_min = round(theta_center - (theta_width / 2.0), 3)
        theta_max = round(theta_center + (theta_width / 2.0), 3)
        phi_min = round(max(1.0, phi_center - (phi_width / 2.0)), 3)
        phi_max = round(min(179.0, phi_center + (phi_width / 2.0)), 3)
        shell_chunk = {
            "chunk_id": f"cloud.shell.{lod_level:02d}.sector.{_slug(str(chunk_id))}.{index:03d}",
            "source_chunk_id": chunk_id,
            "type": "density_chunk",
            "is_semantic_node": False,
            "is_visual_shell_tile": True,
            "is_materialization_container": True,
            "semantic_aggregate_node": False,
            "semantic_aggregate_nodes_used": False,
            "compression_used": False,
            "all_nodes_rendered": False,
            "represents_node_count": represented_nodes,
            "represents_relation_count": represented_relations,
            "logical_node_count": represented_nodes,
            "materialized_node_count": 0,
            "stored_relation_count": represented_relations,
            "lod_level": lod_level,
            "onion_layer": ONION_LAYER_NAMES[onion_layer_index],
            "onion_layer_index": onion_layer_index,
            "radius": round(onion_radius, 5),
            "x": round(x, 5),
            "y": round(y, 5),
            "z": round(z, 5),
            "shell_center": {
                "x": round(x, 5),
                "y": round(y, 5),
                "z": round(z, 5),
            },
            "radius_range": [round(max(0.18, onion_radius - 0.055), 3), round(min(1.08, onion_radius + 0.055), 3)],
            "theta_range": [theta_min, theta_max],
            "phi_range": [phi_min, phi_max],
            "density": round(density, 4),
            "loaded": False,
        }
        chunks.append(shell_chunk)
        density_chunks.append(shell_chunk)

    return {
        "chunks": chunks,
        "density_chunks": density_chunks,
        "active_chunk_count": len(chunks),
        "visible_scale_chunk_count": len(density_chunks),
        "logical_node_count": node_total,
        "stored_relation_count": relation_total,
        "materialized_node_count": len(nodes),
        "materialized_relation_count": len(edges),
        "render_mode": "spherical_lod_shell",
        "onion_layers": list(ONION_LAYER_NAMES),
        "geometry_metrics": _chunk_geometry_metrics(density_chunks),
        "semantic_aggregate_nodes_used": False,
        "compression_used": False,
        "all_nodes_rendered": False,
    }
