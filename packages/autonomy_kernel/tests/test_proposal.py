from __future__ import annotations

from pathlib import Path

from packages.autonomy_kernel.models import DeficitSignal
from packages.autonomy_kernel.proposal import create_patch_proposal, never_apply_patch, validate_patch_proposal_safety


def test_patch_proposal_never_executes(tmp_path: Path) -> None:
    before = set(tmp_path.iterdir())
    deficit = DeficitSignal("d", "missing_skill", 0.5, 0.5, "test", [])
    proposal = create_patch_proposal(deficit)
    unchanged = never_apply_patch(proposal)
    after = set(tmp_path.iterdir())
    assert unchanged.executed is False
    assert unchanged.approval_required is True
    assert validate_patch_proposal_safety(unchanged) is True
    assert before == after

