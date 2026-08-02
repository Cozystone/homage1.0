from pathlib import Path

from packages.cloud_brain import semantic_growth
from packages.cloud_brain.semantic_growth import MAX_ACCELERATION_BATCH_SIZE, ingest_semantic_acceleration_batch, ingest_semantic_source
from packages.cloud_brain.semantic_store import SemanticCloudStore


SAMPLE_KO = "쿠버네티스는 컨테이너화된 애플리케이션을 자동으로 배포하고 관리하는 오픈소스 플랫폼입니다."
SAMPLE_EN = "Kubernetes is an open-source platform that manages containerized applications and automates deployment."


def test_semantic_ingest_creates_store_records(tmp_path: Path):
    root = tmp_path / "cloud"
    result = ingest_semantic_source(SAMPLE_KO, "sample-ko", "ko", cloud_root=root)
    status = SemanticCloudStore(root).status()
    assert result["concepts_created"] > 0
    assert result["relations_created"] > 0
    assert status["concepts"] > 0
    assert result["honesty"]["local_brain_write"] is False


def test_duplicate_ingest_strengthens_not_explodes(tmp_path: Path):
    root = tmp_path / "cloud"
    first = ingest_semantic_source(SAMPLE_KO, "sample-ko", "ko", cloud_root=root)
    second = ingest_semantic_source(SAMPLE_KO, "sample-ko", "ko", cloud_root=root)
    status = SemanticCloudStore(root).status()
    assert second["concepts_merged"] > 0
    assert second["relations_strengthened"] > 0
    assert status["concepts"] == first["status"]["concepts"]


def test_cross_language_alias_strengthens_existing_concept(tmp_path: Path):
    root = tmp_path / "cloud"
    ingest_semantic_source(SAMPLE_KO, "sample-ko", "ko", cloud_root=root)
    result = ingest_semantic_source(SAMPLE_EN, "sample-en", "en", cloud_root=root)
    assert result["concepts_merged"] > 0


def test_semantic_acceleration_batch_adds_real_store_records(tmp_path: Path):
    root = tmp_path / "cloud"
    result = ingest_semantic_acceleration_batch(1000, cloud_root=root)
    status = SemanticCloudStore(root).status()
    assert result["batch_size_applied"] == 1000
    assert result["concepts_created"] >= 1000
    assert result["relations_created"] >= 1000
    assert status["concepts"] >= 1000
    assert status["relations"] >= 1000
    assert result["fake_counter"] is False
    assert result["honesty"]["local_brain_write"] is False
    assert result["honesty"]["external_llm_used"] is False


def test_semantic_acceleration_batch_accepts_larger_real_batches(tmp_path: Path):
    root = tmp_path / "cloud"
    requested = min(2500, MAX_ACCELERATION_BATCH_SIZE)
    result = ingest_semantic_acceleration_batch(requested, cloud_root=root)
    status = SemanticCloudStore(root).status()
    assert result["batch_size_applied"] == requested
    assert result["concepts_created"] >= requested
    assert status["concepts"] >= requested
    assert result["fake_counter"] is False
    assert result["max_safe_batch_size"] >= requested


def test_semantic_acceleration_batch_partitions_shards(tmp_path: Path, monkeypatch):
    root = tmp_path / "cloud"
    monkeypatch.setattr(semantic_growth, "CLOUD_GROWTH_SUB_BATCH_SIZE", 250)
    result = ingest_semantic_acceleration_batch(750, cloud_root=root)
    status = SemanticCloudStore(root).status()
    assert result["batch_size_applied"] == 750
    assert result["internal_sub_batches"] == 3
    assert result["growth_shards_written"] == 3
    assert result["candidate_pair_edges_sent"] == 0
    assert result["full_store_scan_during_status_request"] is False
    assert result["index_rebuild_during_request"] is False
    assert status["concepts"] >= 750
