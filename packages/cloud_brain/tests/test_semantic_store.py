from pathlib import Path

from packages.cloud_brain.semantic_store import SemanticCloudStore


def test_semantic_store_starts_empty_and_reports_status(tmp_path: Path):
    store = SemanticCloudStore(tmp_path / "cloud")
    status = store.status()
    assert status["concepts"] == 0
    assert status["relations"] == 0
    assert status["proof_store_only"] is True
