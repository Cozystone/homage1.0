from __future__ import annotations

from rag_engine.fusion import LocalBrainSignals, compute_adaptive_fusion_ratio, weighted_rrf


def _ratio_for_strength(value: float):
    return compute_adaptive_fusion_ratio(
        LocalBrainSignals(
            local_density_score=value,
            evidence_score=value,
            edge_confidence_score=value,
            repeated_use_score=value,
            lexical_overlap_score=value,
            temporal_freshness_score=value,
            matched_local_nodes=1,
        )
    )


def test_adaptive_ratio_tracks_local_strength_continuously() -> None:
    assert 0.88 <= _ratio_for_strength(0.1).cloud_weight <= 0.9
    assert 0.78 <= _ratio_for_strength(0.2).cloud_weight <= 0.82
    assert 0.48 <= _ratio_for_strength(0.5).cloud_weight <= 0.52
    assert 0.18 <= _ratio_for_strength(0.8).cloud_weight <= 0.22


def test_high_local_confidence_caps_or_removes_cloud_weight() -> None:
    capped = compute_adaptive_fusion_ratio(
        LocalBrainSignals(local_density_score=0.4, local_answer_confidence=0.91)
    )
    sovereign = compute_adaptive_fusion_ratio(
        LocalBrainSignals(local_density_score=0.4, local_answer_confidence=0.971)
    )

    assert capped.cloud_weight <= 0.1
    assert sovereign.cloud_weight == 0.0
    assert sovereign.local_weight == 1.0


def test_private_query_and_invalid_cloud_fragment_force_local_only() -> None:
    private_ratio = compute_adaptive_fusion_ratio(
        LocalBrainSignals(local_density_score=0.1, query_is_private=True)
    )
    invalid_ratio = compute_adaptive_fusion_ratio(
        LocalBrainSignals(local_density_score=0.1, cloud_fragment_valid=False)
    )

    assert private_ratio.cloud_weight == 0.0
    assert private_ratio.reason == "private_query_local_only"
    assert invalid_ratio.cloud_weight == 0.0
    assert invalid_ratio.reason == "cloud_fragment_validation_failed"


def test_low_memory_brain_clamps_cloud_fragment_size() -> None:
    ratio = compute_adaptive_fusion_ratio(
        LocalBrainSignals(local_density_score=0.1, runtime_mode="low_memory_brain")
    )

    assert ratio.cloud_fragment_limits.cloud_max_nodes <= 64
    assert ratio.cloud_fragment_limits.cloud_max_edges <= 192
    assert ratio.cloud_fragment_limits.max_bytes <= 256 * 1024
    assert ratio.cloud_fragment_policy == "bounded_low_memory_fragments_only"


def test_cloud_context_never_outranks_local_private_context() -> None:
    result = weighted_rrf(
        [{"chunk_id": "local-private", "text": "private local memory", "private": True, "confidence": 0.3}],
        [{"chunk_id": "cloud-verified", "text": "verified cloud fact", "validated": True, "confidence": 1.0}],
        {"local_weight": 0.1, "cloud_weight": 0.9},
    )

    assert result[0]["chunk_id"] == "local-private"
    assert result[0]["fusion_source"] == "local"
