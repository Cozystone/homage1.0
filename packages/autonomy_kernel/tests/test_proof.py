from __future__ import annotations

import sys
from pathlib import Path

from packages.autonomy_kernel.proof import run_proof


def test_proof_writes_report(tmp_path: Path) -> None:
    result = run_proof(output_dir=tmp_path)
    assert all(result["summary"].values())
    assert list(tmp_path.glob("autonomy_kernel_proof_*.json"))
    assert list(tmp_path.glob("autonomy_kernel_proof_*.md"))


def test_package_does_not_import_active_cloud_brain_daemon() -> None:
    sys.modules.pop("packages.cloud_brain.candidate_learning_daemon", None)
    import packages.autonomy_kernel  # noqa: F401

    assert "packages.cloud_brain.candidate_learning_daemon" not in sys.modules


def test_required_invariants_are_false(tmp_path: Path) -> None:
    result = run_proof(output_dir=tmp_path)
    assert result["congress_proposal"]["network_used"] is False
    assert result["hot_swap_proposal_only"]["patch"]["executed"] is False
    assert result["safety_block"]["pass"] is True
