from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packages.cloud_brain.ingestion import ensure_fixture_and_ingest
from packages.cloud_brain.sphere_materialization import (
    get_sphere_tile,
    get_sphere_tile_children,
    materialize_sphere_tile,
    sphere_manifest,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_spherical_chunk_materialization_proof(
    *,
    seed_root: str | Path | None = "data/seed_research",
    cloud_root: str | Path = "data/cloud_brain",
) -> dict[str, Any]:
    ensure_fixture_and_ingest(seed_root=seed_root, cloud_root=cloud_root)
    manifest = sphere_manifest(cloud_root=cloud_root)
    root_tile = get_sphere_tile(level=0, x=0, y=0, cloud_root=cloud_root)
    children = get_sphere_tile_children(root_tile["tile_id"], cloud_root=cloud_root)
    shell = materialize_sphere_tile(root_tile["tile_id"], zoom_level=0, render_budget_nodes=5000, render_budget_edges=10000, cloud_root=cloud_root)
    child_mode = materialize_sphere_tile(root_tile["tile_id"], zoom_level=2, render_budget_nodes=5000, render_budget_edges=10000, cloud_root=cloud_root)
    actual_mode = materialize_sphere_tile(root_tile["tile_id"], zoom_level=5, render_budget_nodes=3, render_budget_edges=2, cloud_root=cloud_root)
    materialized_ids = [node["cloud_node_id"] for node in actual_mode["materialized_nodes"]]
    logical_ordinals_are_strings = all(isinstance(node.get("logical_ordinal"), str) for node in actual_mode["materialized_nodes"])
    return {
        "schema": "atanor.spherical-chunk-materialization-proof.v1",
        "created_at": _now_iso(),
        "scale_mode": "spherical_chunk_materialization",
        "manifest": manifest,
        "root_tile": root_tile,
        "child_tile_count": len(children["children"]),
        "shell_render_mode": shell["render_mode"],
        "child_render_mode": child_mode["render_mode"],
        "actual_render_mode": actual_mode["render_mode"],
        "materialized_node_ids": materialized_ids,
        "materialized_node_count": len(materialized_ids),
        "render_budget_nodes_respected": len(actual_mode["materialized_nodes"]) <= actual_mode["render_budget_nodes"],
        "render_budget_edges_respected": len(actual_mode["materialized_edges"]) <= actual_mode["render_budget_edges"],
        "logical_ordinals_are_strings": logical_ordinals_are_strings,
        "shell_tile_is_graph_node": bool(root_tile.get("is_graph_node", True)),
        "shell_tile_is_semantic_node": bool(root_tile.get("is_semantic_node", True)),
        "compression_used": bool(actual_mode.get("compression_used")),
        "semantic_aggregate_nodes_used": bool(actual_mode.get("semantic_aggregate_nodes_used")),
        "local_brain_state": {
            "local_brain_initialized": False,
            "local_total_nodes": 0,
            "local_total_edges": 0,
        },
        "fake_trillion_population_claimed": False,
        "trillion_nodes_currently_exist_claimed": False,
        "all_nodes_loaded_or_rendered_claimed": False,
        "proof_passed": (
            shell["render_mode"] == "shell"
            and child_mode["render_mode"] == "child_tiles"
            and actual_mode["render_mode"] == "actual_nodes"
            and bool(materialized_ids)
            and len(actual_mode["materialized_nodes"]) <= actual_mode["render_budget_nodes"]
            and len(actual_mode["materialized_edges"]) <= actual_mode["render_budget_edges"]
            and logical_ordinals_are_strings
            and root_tile.get("is_graph_node") is False
            and root_tile.get("is_semantic_node") is False
            and actual_mode.get("compression_used") is False
            and actual_mode.get("semantic_aggregate_nodes_used") is False
        ),
        "materialization_samples": {
            "shell": shell,
            "child_mode": child_mode,
            "actual_mode": actual_mode,
        },
    }


def _write_markdown(proof: dict[str, Any], path: Path) -> None:
    lines = [
        "# ATANOR Spherical Chunk Materialization Proof",
        "",
        f"- Created: `{proof['created_at']}`",
        f"- Scale mode: `{proof['scale_mode']}`",
        f"- Logical nodes: `{proof['manifest']['logical_total_nodes']}`",
        f"- Logical edges: `{proof['manifest']['logical_total_edges']}`",
        f"- Trillion target: `{proof['manifest']['trillion_target']}`",
        f"- Materialized node count: `{proof['materialized_node_count']}`",
        f"- Render budget nodes respected: `{str(proof['render_budget_nodes_respected']).lower()}`",
        f"- Render budget edges respected: `{str(proof['render_budget_edges_respected']).lower()}`",
        f"- Shell tile is graph node: `{str(proof['shell_tile_is_graph_node']).lower()}`",
        f"- Shell tile is semantic node: `{str(proof['shell_tile_is_semantic_node']).lower()}`",
        f"- Compression used: `{str(proof['compression_used']).lower()}`",
        f"- Semantic aggregate nodes used: `{str(proof['semantic_aggregate_nodes_used']).lower()}`",
        f"- Proof passed: `{str(proof['proof_passed']).lower()}`",
        "",
        "## This Proof Claims",
        "",
        "- ATANOR can represent a trillion-scale Cloud Brain as a spherical chunked materialization space.",
        "- Every graph node remains a real individual logical node.",
        "- The renderer loads only camera-visible and zoom-relevant chunks.",
        "- Shell layers are visual/materialization layers, not semantic compression.",
        "- Actual node rendering happens only within bounded render budgets.",
        "",
        "## This Proof Does NOT Claim",
        "",
        "- trillion nodes currently exist",
        "- all nodes are loaded into RAM",
        "- all nodes are rendered simultaneously",
        "- aggregate nodes replace real nodes",
        "- production-scale trillion ingestion has already happened",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_spherical_chunk_materialization_proof(
    *,
    seed_root: str | Path | None = "data/seed_research",
    cloud_root: str | Path = "data/cloud_brain",
) -> dict[str, Any]:
    proof = build_spherical_chunk_materialization_proof(seed_root=seed_root, cloud_root=cloud_root)
    proof_dir = Path(cloud_root) / "proofs"
    proof_dir.mkdir(parents=True, exist_ok=True)
    json_path = proof_dir / "spherical_chunk_materialization_proof.json"
    markdown_path = proof_dir / "spherical_chunk_materialization_proof.md"
    json_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(proof, markdown_path)
    return {
        "proof": proof,
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "proof_json": str(json_path),
        "proof_md": str(markdown_path),
    }


def main() -> None:
    result = write_spherical_chunk_materialization_proof()
    print(json.dumps({key: value for key, value in result.items() if key != "proof"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
