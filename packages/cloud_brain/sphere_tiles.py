from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from packages.cloud_brain.sphere_index import load_logical_cloud_nodes


MAX_TILE_LEVEL = 6


@dataclass(frozen=True)
class SphereTileAddress:
    level: int
    x: int
    y: int
    radial_layer: int = 0

    @property
    def tile_id(self) -> str:
        return f"sphere_l{self.level}_x{self.x:04d}_y{self.y:04d}_r{self.radial_layer}"


def parse_tile_id(tile_id: str) -> SphereTileAddress:
    parts = tile_id.split("_")
    if len(parts) < 4 or not parts[0].startswith("sphere"):
        raise ValueError(f"Invalid sphere tile id: {tile_id}")
    level = int(parts[1].removeprefix("l"))
    x = int(parts[2].removeprefix("x"))
    y = int(parts[3].removeprefix("y"))
    radial_layer = int(parts[4].removeprefix("r")) if len(parts) > 4 else 0
    return SphereTileAddress(level=level, x=x, y=y, radial_layer=radial_layer)


def tile_divisions(level: int) -> tuple[int, int]:
    level = max(0, min(MAX_TILE_LEVEL, int(level)))
    if level == 0:
        return 1, 1
    return 2 ** level, 2 ** max(0, level - 1)


def tile_bounds(address: SphereTileAddress) -> dict[str, float]:
    theta_count, phi_count = tile_divisions(address.level)
    theta_step = (2.0 * math.pi) / theta_count
    phi_step = math.pi / phi_count
    return {
        "theta_min": address.x * theta_step,
        "theta_max": (address.x + 1) * theta_step,
        "phi_min": address.y * phi_step,
        "phi_max": (address.y + 1) * phi_step,
    }


def tile_for_node(node: dict[str, Any], level: int) -> SphereTileAddress:
    theta_count, phi_count = tile_divisions(level)
    theta = float(node.get("theta") or 0.0) % (2.0 * math.pi)
    phi = max(0.0, min(math.pi, float(node.get("phi") or 0.0)))
    x = min(theta_count - 1, int(theta / (2.0 * math.pi) * theta_count))
    y = min(phi_count - 1, int(phi / math.pi * phi_count))
    return SphereTileAddress(level=level, x=x, y=y, radial_layer=int(node.get("radial_layer") or 0))


def node_in_tile(node: dict[str, Any], address: SphereTileAddress) -> bool:
    return tile_for_node(node, address.level) == address


def child_addresses(address: SphereTileAddress) -> list[SphereTileAddress]:
    next_level = min(MAX_TILE_LEVEL, address.level + 1)
    if next_level == address.level:
        return []
    children: dict[str, SphereTileAddress] = {}
    for dx in (0, 1):
        for dy in (0, 1):
            child = SphereTileAddress(
                level=next_level,
                x=address.x * 2 + dx,
                y=address.y * 2 + dy if next_level > 1 else 0,
                radial_layer=address.radial_layer,
            )
            children[child.tile_id] = child
    theta_count, phi_count = tile_divisions(next_level)
    return [child for child in children.values() if child.x < theta_count and child.y < phi_count]


def build_tile(
    address: SphereTileAddress,
    *,
    nodes: list[dict[str, Any]] | None = None,
    sample_limit: int = 16,
) -> dict[str, Any]:
    nodes = nodes if nodes is not None else load_logical_cloud_nodes()
    contained = [node for node in nodes if node_in_tile(node, address)]
    bounds = tile_bounds(address)
    return {
        "tile_id": address.tile_id,
        "level": address.level,
        "theta_min": f"{bounds['theta_min']:.12f}",
        "theta_max": f"{bounds['theta_max']:.12f}",
        "phi_min": f"{bounds['phi_min']:.12f}",
        "phi_max": f"{bounds['phi_max']:.12f}",
        "radial_layer": address.radial_layer,
        "real_node_refs_count": str(len(contained)),
        "materialized_node_count": 0,
        "child_tile_ids": [child.tile_id for child in child_addresses(address)],
        "sample_node_ids": [str(node["cloud_node_id"]) for node in contained[:sample_limit]],
        "is_visual_shell_tile": True,
        "is_semantic_node": False,
        "is_graph_node": False,
    }


def build_tile_from_id(tile_id: str, *, nodes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return build_tile(parse_tile_id(tile_id), nodes=nodes)
