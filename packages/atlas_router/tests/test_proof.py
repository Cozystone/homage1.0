from __future__ import annotations

import sys
from pathlib import Path

from packages.atlas_router.proof import run_proof


def test_proof_command_writes_report(tmp_path: Path) -> None:
    result = run_proof(output_dir=tmp_path)
    assert result["summary"]["local_first_pass"] is True
    assert result["summary"]["privacy_block_pass"] is True
    assert result["summary"]["license_block_pass"] is True
    assert result["summary"]["no_route_pass"] is True
    assert result["summary"]["trust_vs_latency_pass"] is True
    assert list(tmp_path.glob("atlas_router_proof_*.json"))
    assert list(tmp_path.glob("atlas_router_proof_*.md"))


def test_package_does_not_import_active_cloud_brain_daemon_module() -> None:
    sys.modules.pop("packages.cloud_brain.candidate_learning_daemon", None)
    import packages.atlas_router  # noqa: F401

    assert "packages.cloud_brain.candidate_learning_daemon" not in sys.modules

