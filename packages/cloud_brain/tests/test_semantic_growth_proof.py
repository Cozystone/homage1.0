from pathlib import Path

from packages.cloud_brain.proof_semantic_growth import run_semantic_cloud_growth_proof


def test_semantic_growth_proof_passes_on_temp_store(tmp_path: Path):
    proof = run_semantic_cloud_growth_proof(cloud_root=tmp_path / "cloud")
    assert proof["passed"] is True
    assert proof["checks"]["fresh_ingest_created_concepts"] is True
    assert proof["checks"]["duplicate_strengthened_relations"] is True
