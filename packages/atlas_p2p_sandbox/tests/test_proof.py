from __future__ import annotations

from packages.atlas_p2p_sandbox.proof import run_proof


def test_atlas_p2p_sandbox_proof(tmp_path):
    result = run_proof(tmp_path)

    assert all(result["summary"].values())
    assert result["invariants"]["real_p2p_used"] is False
    assert result["invariants"]["raw_private_data_exported"] is False
    assert result["invariants"]["local_brain_write"] is False
