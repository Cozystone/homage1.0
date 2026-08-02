from __future__ import annotations

import sys
from pathlib import Path

from packages.tabularis_privacy.proof import run_proof


def test_proof_command_writes_report(tmp_path: Path) -> None:
    result = run_proof(output_dir=tmp_path)
    assert all(result["summary"].values())
    assert list(tmp_path.glob("tabularis_proof_*.json"))
    assert list(tmp_path.glob("tabularis_proof_*.md"))


def test_package_does_not_import_active_cloud_brain_daemon_module() -> None:
    sys.modules.pop("packages.cloud_brain.candidate_learning_daemon", None)
    import packages.tabularis_privacy  # noqa: F401

    assert "packages.cloud_brain.candidate_learning_daemon" not in sys.modules


def test_no_local_brain_write_symbol() -> None:
    import packages.tabularis_privacy as tabularis

    assert not hasattr(tabularis, "write_local_brain")

