from pathlib import Path

from packages.cloud_brain.semantic_dedupe import normalize_concept_name, resolve_or_create_concept, upsert_semantic_relation
from packages.cloud_brain.semantic_store import SemanticCloudStore


def test_alias_map_merges_kubernetes_and_korean(tmp_path: Path):
    store = SemanticCloudStore(tmp_path / "cloud")
    first, created_first = resolve_or_create_concept({"name": "쿠버네티스"}, store, source_hash="a")
    second, created_second = resolve_or_create_concept({"name": "Kubernetes"}, store, source_hash="b")
    assert created_first is True
    assert created_second is False
    assert first["concept_id"] == second["concept_id"]
    assert normalize_concept_name("Kubernetes") == normalize_concept_name("쿠버네티스")


def test_upsert_relation_strengthens_duplicate(tmp_path: Path):
    store = SemanticCloudStore(tmp_path / "cloud")
    first, created_first = upsert_semantic_relation("a", "manages", "b", "s1", 0.7, store)
    second, created_second = upsert_semantic_relation("a", "manages", "b", "s2", 0.9, store)
    assert created_first is True
    assert created_second is False
    assert second["seen_count"] == first["seen_count"] + 1
    assert second["weight"] > first["weight"]
