from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_ROOT = REPO_ROOT / "packages" / "seed_research"
if str(SEED_ROOT) not in sys.path:
    sys.path.insert(0, str(SEED_ROOT))

from packages.cloud_brain.ingestion import (  # noqa: E402
    cloud_store_status,
    ensure_fixture_and_ingest,
    ingest_aligned_cloud_fragment,
    query_ingested_fragments,
)
from packages.cloud_brain.prove_controlled_self_growth import write_controlled_self_growth_proof  # noqa: E402
from seed_research import run_seed_iteration  # noqa: E402
from seed_research.cloud_fragment_alignment import deterministic_fixture, ensure_deterministic_fixture  # noqa: E402


def test_controlled_fixture_ingestion_updates_cloud_store_only(tmp_path: Path) -> None:
    seed_root = tmp_path / "seed_research"
    cloud_root = tmp_path / "cloud_brain"
    run_seed_iteration(seed_root)
    ensure_deterministic_fixture(cloud_root / "inbox" / "fixture.json")

    before = cloud_store_status(cloud_root)
    result = ensure_fixture_and_ingest(seed_root=seed_root, cloud_root=cloud_root)
    after = cloud_store_status(cloud_root)
    readback = query_ingested_fragments("Evidence supports claim", cloud_root=cloud_root)

    assert before["cloud_total_nodes"] == 0
    assert before["cloud_total_edges"] == 0
    assert result["ingestion_success"] is True
    assert result["ingestion_state"] == "ingested"
    assert result["verification_state"] == "seed_aligned_pending_verification"
    assert result["trust_state"] == "seed_aligned"
    assert result["writes_to_local_brain"] is False
    assert result["external_llm_used"] is False
    assert result["external_sllm_used"] is False
    assert result["rule_based_answer_engine"] is False
    assert result["final_answer_generation_claimed"] is False
    assert result["nodes_added"] >= 3
    assert result["edges_added"] >= 1
    assert after["cloud_total_nodes"] == result["new_cloud_nodes"]
    assert after["cloud_total_edges"] == result["new_cloud_edges"]
    assert after["proof_ingested_fragments"] == 1
    assert readback["query_readback_success"] is True
    assert readback["results"][0]["fragment_id"] == "candidate_seed_alignment_001"
    assert not (tmp_path / "data" / "memory").exists()


def test_pending_inbox_and_seed_graph_do_not_count_as_cloud_growth(tmp_path: Path) -> None:
    seed_root = tmp_path / "seed_research"
    cloud_root = tmp_path / "cloud_brain"
    run_seed_iteration(seed_root)
    ensure_deterministic_fixture(cloud_root / "inbox" / "pending_fixture.json")

    status = cloud_store_status(cloud_root)

    assert status["cloud_total_nodes"] == 0
    assert status["cloud_total_edges"] == 0
    assert status["proof_ingested_fragments"] == 0


def test_duplicate_cloud_fragment_does_not_inflate_counts(tmp_path: Path) -> None:
    seed_root = tmp_path / "seed_research"
    cloud_root = tmp_path / "cloud_brain"
    run_seed_iteration(seed_root)
    fragment = deterministic_fixture()

    first = ingest_aligned_cloud_fragment(fragment, seed_root=seed_root, cloud_root=cloud_root)
    second = ingest_aligned_cloud_fragment(fragment, seed_root=seed_root, cloud_root=cloud_root)

    assert first["ingestion_success"] is True
    assert second["ingestion_success"] is True
    assert second["duplicate_fragment"] is True
    assert second["nodes_added"] == 0
    assert second["edges_added"] == 0
    assert second["new_cloud_nodes"] == first["new_cloud_nodes"]
    assert second["new_cloud_edges"] == first["new_cloud_edges"]
    assert cloud_store_status(cloud_root)["proof_ingested_fragments"] == 1


def test_private_or_unaligned_fragments_are_rejected(tmp_path: Path) -> None:
    seed_root = tmp_path / "seed_research"
    cloud_root = tmp_path / "cloud_brain"
    run_seed_iteration(seed_root)

    private_fragment = {**deterministic_fixture(), "content_hash": "private_001", "text": "C:\\Users\\private\\payload.md"}
    unaligned_fragment = {
        **deterministic_fixture(),
        "fragment_id": "unaligned_001",
        "content_hash": "unaligned_001",
        "title": "Unrelated",
        "text": "Zyxw qvorn blimtak nalopex undecoded glyph stream.",
    }

    private_result = ingest_aligned_cloud_fragment(private_fragment, seed_root=seed_root, cloud_root=cloud_root)
    unaligned_result = ingest_aligned_cloud_fragment(unaligned_fragment, seed_root=seed_root, cloud_root=cloud_root)

    assert private_result["ingestion_success"] is False
    assert private_result["ingestion_state"] == "rejected"
    assert unaligned_result["ingestion_success"] is False
    assert unaligned_result["ingestion_state"] == "rejected"
    assert cloud_store_status(cloud_root)["cloud_total_nodes"] == 0


def test_proof_artifacts_are_written_with_honest_claim_boundaries(tmp_path: Path) -> None:
    seed_root = tmp_path / "seed_research"
    cloud_root = tmp_path / "cloud_brain"
    run_seed_iteration(seed_root)

    result = write_controlled_self_growth_proof(seed_root=seed_root, cloud_root=cloud_root)
    proof = result["proof"]
    proof_json = Path(result["proof_json"])
    proof_md = Path(result["proof_md"])

    assert proof["controlled_self_growth"] is True
    assert proof["local_brain_state"]["local_total_nodes"] == 0
    assert proof["autonomous_broad_crawling"] is False
    assert proof["external_llm_used"] is False
    assert proof["external_sllm_used"] is False
    assert proof["rule_based_answer_engine"] is False
    assert proof["final_answer_generation_claimed"] is False
    assert proof_json.exists()
    assert proof_md.exists()
    assert json.loads(proof_json.read_text(encoding="utf-8"))["query_readback_success"] is True
    assert "Broad autonomous web crawling" in proof_md.read_text(encoding="utf-8")
