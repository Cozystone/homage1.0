from __future__ import annotations

import json
from pathlib import Path

from packages.cloud_brain.candidate_promotion_merge import (
    PROMOTED_SHARD_ID,
    merge_candidates_to_production,
)
from packages.cloud_brain.read_model import build_cloud_read_model


def _candidate_store(tmp_path: Path) -> Path:
    store = tmp_path / "candidate_runs" / "run_x"
    store.mkdir(parents=True)
    (store / "manifest.json").write_text("{}", encoding="utf-8")
    (store / "concepts.jsonl").write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {"concept_id": "c1", "canonical_name": "Docker", "language": "en"},
                {"concept_id": "c2", "canonical_name": "Container", "language": "en"},
            ]
        ),
        encoding="utf-8",
    )
    (store / "relations.jsonl").write_text(
        json.dumps({"relation_id": "r1", "source_concept_id": "c1", "target_concept_id": "c2", "relation": "produces"}),
        encoding="utf-8",
    )
    return store


def test_merge_appends_a_reversible_production_shard(tmp_path):
    store = _candidate_store(tmp_path)
    prod = tmp_path / "prod_cloud"
    result = merge_candidates_to_production(store, production_root=prod)

    assert result["merged"] is True
    assert result["concepts"] == 2
    assert result["relations"] == 1
    assert result["production_store_mutated"] is True
    assert result["shard_id"] == PROMOTED_SHARD_ID
    # the shard files exist somewhere under the production root (reversible)
    assert any(prod.rglob(f"{PROMOTED_SHARD_ID}*concepts.json"))

    # production read model now counts the merged concepts
    read = build_cloud_read_model(prod)
    assert int(read["status"]["concepts"]) >= 2


def test_merge_is_idempotent(tmp_path):
    store = _candidate_store(tmp_path)
    prod = tmp_path / "prod_cloud"
    first = merge_candidates_to_production(store, production_root=prod)
    second = merge_candidates_to_production(store, production_root=prod)
    assert first["concepts"] == second["concepts"] == 2
    read = build_cloud_read_model(prod)
    # re-merging the same shard must not double-count
    assert int(read["status"]["concepts"]) == 2


def test_merge_missing_store_is_safe(tmp_path):
    result = merge_candidates_to_production(tmp_path / "nope", production_root=tmp_path / "prod")
    assert result["merged"] is False
    assert result["concepts"] == 0
