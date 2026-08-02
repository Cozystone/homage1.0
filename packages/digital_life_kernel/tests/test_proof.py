from __future__ import annotations

from packages.digital_life_kernel.proof import run_proof


def test_digital_life_kernel_proof(tmp_path):
    result = run_proof(tmp_path)

    assert all(result["summary"].values())
    assert result["invariants"]["production_store_mutated"] is False
    assert result["invariants"]["local_brain_write"] is False
    assert result["invariants"]["real_p2p_used"] is False
    assert "outputs" in result
