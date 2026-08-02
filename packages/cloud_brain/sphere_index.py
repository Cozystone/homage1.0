from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from packages.cloud_brain.ingestion import DEFAULT_CLOUD_ROOT, _read_jsonl, _store_paths, cloud_store_status


TRILLION_TARGET = "1000000000000"
MAX_LOGICAL_NODES = "9999999999999999"
SPHERE_RADIUS = 1.0


def stable_sphere_position(cloud_node_id: str, *, radial_layer: int = 0) -> dict[str, float | int]:
    """Map a stable logical node ID to deterministic spherical coordinates."""

    digest = hashlib.sha256(cloud_node_id.encode("utf-8", errors="ignore")).digest()
    theta_unit = int.from_bytes(digest[0:8], "big") / ((1 << 64) - 1)
    phi_unit = int.from_bytes(digest[8:16], "big") / ((1 << 64) - 1)
    theta = theta_unit * (2.0 * math.pi)
    phi = math.acos(1.0 - 2.0 * phi_unit)
    radius = SPHERE_RADIUS - min(max(radial_layer, 0), 8) * 0.055
    sin_phi = math.sin(phi)
    return {
        "theta": theta,
        "phi": phi,
        "radius": radius,
        "x": radius * sin_phi * math.cos(theta),
        "y": radius * math.cos(phi),
        "z": radius * sin_phi * math.sin(theta),
        "radial_layer": radial_layer,
    }


def logical_ordinal_for_node(cloud_node_id: str) -> str:
    digest = hashlib.sha256(f"ordinal:{cloud_node_id}".encode("utf-8", errors="ignore")).hexdigest()
    return str(int(digest[:16], 16))


def _node_from_proof_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    concept_id = str(row.get("concept_id") or row.get("label") or f"proof-node-{index}")
    content_hash = str(row.get("content_hash") or "proof")
    cloud_node_id = f"cbn_{hashlib.sha256(f'{content_hash}:{concept_id}'.encode('utf-8')).hexdigest()[:32]}"
    position = stable_sphere_position(cloud_node_id)
    return {
        "cloud_node_id": cloud_node_id,
        "logical_ordinal": logical_ordinal_for_node(cloud_node_id),
        "label": str(row.get("label") or concept_id),
        "concept_id": concept_id,
        "source_scope": "cloud",
        "trust_state": "seed_aligned",
        "verification_state": "seed_aligned_pending_verification",
        "content_hash": content_hash,
        **position,
    }


def _edge_from_proof_row(row: dict[str, Any]) -> dict[str, Any]:
    source = str(row.get("source") or "")
    target = str(row.get("target") or "")
    content_hash = str(row.get("content_hash") or "proof")
    source_id = f"cbn_{hashlib.sha256(f'{content_hash}:{source}'.encode('utf-8')).hexdigest()[:32]}"
    target_id = f"cbn_{hashlib.sha256(f'{content_hash}:{target}'.encode('utf-8')).hexdigest()[:32]}"
    return {
        "source": source_id,
        "target": target_id,
        "relation": str(row.get("relation") or "related"),
        "weight": float(row.get("confidence") or 1.0),
        "source_scope": "cloud",
    }


def _nodes_from_memory_db(db_path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT node_hash, dim0, dim1, dim2
            FROM ghost_nodes
            ORDER BY node_hash
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass
    nodes: list[dict[str, Any]] = []
    for row in rows:
        node_hash = str(row["node_hash"])
        cloud_node_id = f"cbn_{node_hash}"
        fallback = stable_sphere_position(cloud_node_id)
        x = float(row["dim0"] or fallback["x"])
        y = float(row["dim1"] or fallback["y"])
        z = float(row["dim2"] or fallback["z"])
        radius = math.sqrt(x * x + y * y + z * z) or 1.0
        theta = math.atan2(z, x) % (2.0 * math.pi)
        phi = math.acos(max(-1.0, min(1.0, y / radius)))
        nodes.append(
            {
                "cloud_node_id": cloud_node_id,
                "logical_ordinal": logical_ordinal_for_node(cloud_node_id),
                "label": f"ghost:{node_hash[:12]}",
                "source_scope": "cloud",
                "trust_state": "local_mirror",
                "verification_state": "working_memory",
                "theta": theta,
                "phi": phi,
                "radius": min(1.0, max(0.35, radius)),
                "x": x / radius,
                "y": y / radius,
                "z": z / radius,
                "radial_layer": 0,
            }
        )
    return nodes


def _edges_from_memory_db(db_path: Path, *, node_ids: set[str], limit: int) -> list[dict[str, Any]]:
    if not db_path.exists() or not node_ids:
        return []
    ghost_hashes = [node_id.removeprefix("cbn_") for node_id in node_ids]
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        marks = ",".join("?" for _ in ghost_hashes)
        rows = conn.execute(
            f"""
            SELECT source_hash, target_hash, weight
            FROM ghost_edges
            WHERE source_hash IN ({marks}) AND target_hash IN ({marks})
            ORDER BY weight DESC
            LIMIT ?
            """,
            (*ghost_hashes, *ghost_hashes, limit),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return [
        {
            "source": f"cbn_{str(row['source_hash'])}",
            "target": f"cbn_{str(row['target_hash'])}",
            "relation": "ghost_edge",
            "weight": float(row["weight"] or 0.0),
            "source_scope": "cloud",
        }
        for row in rows
    ]


def load_logical_cloud_nodes(
    *,
    cloud_root: str | Path = DEFAULT_CLOUD_ROOT,
    memory_db_path: str | Path = "data/memory/homage.db",
    limit: int = 50_000,
) -> list[dict[str, Any]]:
    paths = _store_paths(cloud_root)
    proof_nodes = [_node_from_proof_row(row, index) for index, row in enumerate(_read_jsonl(paths["nodes"]))]
    remaining = max(0, limit - len(proof_nodes))
    memory_nodes = _nodes_from_memory_db(Path(memory_db_path), limit=remaining)
    merged: dict[str, dict[str, Any]] = {}
    for node in [*proof_nodes, *memory_nodes]:
        merged.setdefault(str(node["cloud_node_id"]), node)
    return list(merged.values())[:limit]


def load_logical_cloud_edges(
    nodes: list[dict[str, Any]],
    *,
    cloud_root: str | Path = DEFAULT_CLOUD_ROOT,
    memory_db_path: str | Path = "data/memory/homage.db",
    limit: int = 100_000,
) -> list[dict[str, Any]]:
    paths = _store_paths(cloud_root)
    proof_edges = [_edge_from_proof_row(row) for row in _read_jsonl(paths["edges"])]
    node_ids = {str(node["cloud_node_id"]) for node in nodes}
    remaining = max(0, limit - len(proof_edges))
    memory_edges = _edges_from_memory_db(Path(memory_db_path), node_ids=node_ids, limit=remaining)
    return [edge for edge in [*proof_edges, *memory_edges] if edge["source"] in node_ids and edge["target"] in node_ids][:limit]


def logical_cloud_manifest(*, cloud_root: str | Path = DEFAULT_CLOUD_ROOT) -> dict[str, Any]:
    status = cloud_store_status(cloud_root)
    proof_nodes = int(status.get("cloud_total_nodes") or 0)
    proof_edges = int(status.get("cloud_total_edges") or 0)
    return {
        "scale_mode": "spherical_chunk_materialization",
        "logical_total_nodes": str(proof_nodes),
        "logical_total_edges": str(proof_edges),
        "max_logical_nodes": MAX_LOGICAL_NODES,
        "trillion_target": TRILLION_TARGET,
        "actual_materialized_nodes": proof_nodes,
        "rendered_nodes": 0,
        "compression_used": False,
        "semantic_aggregate_nodes_used": False,
        "claim": "Every logical node remains individually addressable. The renderer materializes only visible spherical chunks.",
    }


def safe_json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
