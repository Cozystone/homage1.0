from __future__ import annotations

from packages.promotion_manifest.proof import run_proof


def test_run_proof_outputs_non_applying_manifest(tmp_path) -> None:
    payload = run_proof(tmp_path)

    assert payload["verdict"] == "SIGNED_PROMOTION_MANIFEST_GATE_PROOF_ONLY"
    assert all(value is True for key, value in payload["scenarios"].items() if key not in {"apply_enabled", "production_store_mutated", "local_brain_write", "candidate_store_mutated"})
    assert payload["scenarios"]["apply_enabled"] is False
    assert payload["scenarios"]["production_store_mutated"] is False
    assert payload["scenarios"]["local_brain_write"] is False
    assert payload["scenarios"]["candidate_store_mutated"] is False
    assert payload["invariants"]["requires_user_approval"] is True
    assert (tmp_path / next(path.name for path in tmp_path.glob("promotion_manifest_proof_*.json"))).exists()
