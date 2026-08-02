from packages.graph_hub.cartridge_exporter import export_semantic_cloud_to_cartridge


def test_semantic_cloud_export_stays_candidate_and_does_not_use_mirror():
    exported = export_semantic_cloud_to_cartridge(
        "semantic_cloud_kubernetes_demo_test",
        "Semantic Cloud Kubernetes Demo Test",
        "test export",
        "free",
        limit_nodes=20,
        limit_edges=40,
    )
    assert exported["provenance"]["source_type"] == "semantic_candidate_store"
    assert exported["provenance"]["verification_state"] == "caller_unverified_v0"
    assert exported["provenance"]["independent_source_attestation"] is False
    assert exported["provenance"]["authoritative_for_answer"] is False
    assert exported["provenance"]["old_mirror_snapshot_used"] is False
    assert exported["permissions"]["write_local_brain"] is False
    assert exported["permissions"]["attach_to_working_memory"] is False
    assert exported["safety"]["trusted"] is False
    assert exported["metadata"]["checksum"]
