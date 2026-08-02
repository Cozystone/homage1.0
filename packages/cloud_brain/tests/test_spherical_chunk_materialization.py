from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_ROOT = REPO_ROOT / "packages" / "seed_research"
if str(SEED_ROOT) not in sys.path:
    sys.path.insert(0, str(SEED_ROOT))

from packages.cloud_brain.ingestion import ensure_fixture_and_ingest  # noqa: E402
from packages.cloud_brain.prove_spherical_chunk_materialization import write_spherical_chunk_materialization_proof  # noqa: E402
from packages.cloud_brain.sphere_index import stable_sphere_position  # noqa: E402
from packages.cloud_brain.sphere_materialization import (  # noqa: E402
    get_sphere_tile,
    get_sphere_tile_children,
    materialize_sphere_tile,
    sphere_manifest,
)
from seed_research import run_seed_iteration  # noqa: E402


def _prepared_roots(tmp_path: Path) -> tuple[Path, Path]:
    seed_root = tmp_path / "seed_research"
    cloud_root = tmp_path / "cloud_brain"
    run_seed_iteration(seed_root)
    ensure_fixture_and_ingest(seed_root=seed_root, cloud_root=cloud_root)
    return seed_root, cloud_root


def test_stable_sphere_position_is_deterministic() -> None:
    first = stable_sphere_position("cbn_test_node_001")
    second = stable_sphere_position("cbn_test_node_001")
    assert first == second


def test_shell_tile_is_not_a_graph_or_semantic_node(tmp_path: Path) -> None:
    _, cloud_root = _prepared_roots(tmp_path)
    tile = get_sphere_tile(level=0, x=0, y=0, cloud_root=cloud_root)

    assert tile["is_visual_shell_tile"] is True
    assert tile["is_graph_node"] is False
    assert tile["is_semantic_node"] is False
    assert isinstance(tile["real_node_refs_count"], str)


def test_materialization_modes_and_budgets(tmp_path: Path) -> None:
    _, cloud_root = _prepared_roots(tmp_path)
    tile_id = "sphere_l0_x0000_y0000_r0"
    shell = materialize_sphere_tile(tile_id, zoom_level=0, render_budget_nodes=2, render_budget_edges=1, cloud_root=cloud_root)
    child = materialize_sphere_tile(tile_id, zoom_level=2, render_budget_nodes=2, render_budget_edges=1, cloud_root=cloud_root)
    actual = materialize_sphere_tile(tile_id, zoom_level=5, render_budget_nodes=2, render_budget_edges=1, cloud_root=cloud_root)

    assert shell["render_mode"] == "shell"
    assert shell["materialized_nodes"] == []
    assert child["render_mode"] == "child_tiles"
    assert child["child_tiles"]
    assert actual["render_mode"] == "actual_nodes"
    assert actual["rendered_nodes"] <= 2
    assert actual["rendered_edges"] <= 1
    assert actual["compression_used"] is False
    assert actual["semantic_aggregate_nodes_used"] is False
    assert actual["materialized_nodes"][0]["cloud_node_id"].startswith("cbn_")
    assert isinstance(actual["materialized_nodes"][0]["logical_ordinal"], str)


def test_manifest_uses_string_safe_large_counts(tmp_path: Path) -> None:
    _, cloud_root = _prepared_roots(tmp_path)
    manifest = sphere_manifest(cloud_root=cloud_root)

    assert manifest["scale_mode"] == "spherical_chunk_materialization"
    assert isinstance(manifest["logical_total_nodes"], str)
    assert isinstance(manifest["max_logical_nodes"], str)
    assert isinstance(manifest["trillion_target"], str)
    assert manifest["compression_used"] is False
    assert manifest["semantic_aggregate_nodes_used"] is False
    assert manifest["rendered_nodes"] == 0


def test_child_tiles_are_containers_not_aggregate_nodes(tmp_path: Path) -> None:
    _, cloud_root = _prepared_roots(tmp_path)
    children = get_sphere_tile_children("sphere_l0_x0000_y0000_r0", cloud_root=cloud_root)

    assert children["compression_used"] is False
    assert children["semantic_aggregate_nodes_used"] is False
    assert children["children"]
    assert all(child["is_semantic_node"] is False for child in children["children"])
    assert all(child["is_graph_node"] is False for child in children["children"])


def test_spherical_chunk_proof_artifacts_are_created(tmp_path: Path) -> None:
    seed_root, cloud_root = _prepared_roots(tmp_path)
    result = write_spherical_chunk_materialization_proof(seed_root=seed_root, cloud_root=cloud_root)
    proof = result["proof"]

    assert proof["proof_passed"] is True
    assert proof["local_brain_state"]["local_total_nodes"] == 0
    assert proof["fake_trillion_population_claimed"] is False
    assert Path(result["proof_json"]).exists()
    assert Path(result["proof_md"]).exists()
    assert json.loads(Path(result["proof_json"]).read_text(encoding="utf-8"))["compression_used"] is False
