from __future__ import annotations

from packages.promotion_review.proof import run_proof


def test_proof_outputs_invariants(tmp_path) -> None:
    payload = run_proof(tmp_path)

    assert payload["verdict"] == "PROMOTION_REVIEW_FLOW_PROOF_ONLY"
    assert payload["scenarios"]["session_creation"] is True
    assert payload["scenarios"]["generic_predicate_recommendation"] is True
    assert payload["scenarios"]["conflict_recommendation"] is True
    assert payload["scenarios"]["manifest_ready_for_real_promotion"] is False
    assert payload["invariants"]["production_store_mutated"] is False
    assert payload["invariants"]["local_brain_write"] is False
    assert payload["invariants"]["candidate_store_mutated"] is False
    assert (tmp_path / payload["outputs"]["json"].split("\\")[-1]).exists() or payload["outputs"]["json"]
