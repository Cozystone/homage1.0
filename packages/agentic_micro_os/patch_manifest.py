from __future__ import annotations

from .models import PatchProposal


def make_patch_proposal(proposal_id: str, target_cell: str, allowed_paths: list[str], diff_summary: str) -> PatchProposal:
    return PatchProposal(
        proposal_id=proposal_id,
        target_cell=target_cell,
        allowed_paths=allowed_paths,
        diff_summary=diff_summary,
        risk_level="medium",
        expected_tests=["python -m pytest packages/splatra_turbovec/tests -q"],
        rollback_plan="discard proposal manifest; no source mutation without review",
        requires_human_approval=True,
    )
