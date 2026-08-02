from __future__ import annotations

from dataclasses import asdict, dataclass

from .models import DeficitSignal


@dataclass(frozen=True)
class PatchProposal:
    proposal_id: str
    target_area: str
    diff_summary: str
    pseudo_diff: str
    risk_level: str
    tests_required: list[str]
    approval_required: bool = True
    executed: bool = False

    def __post_init__(self) -> None:
        if not self.proposal_id:
            raise ValueError("proposal_id is required")
        if self.executed:
            raise ValueError("proof-only patch proposals must not be executed")

    def to_dict(self) -> dict:
        return asdict(self)


def create_patch_proposal(deficit: DeficitSignal) -> PatchProposal:
    return PatchProposal(
        proposal_id=f"patch_{deficit.signal_id}",
        target_area=deficit.deficit_type,
        diff_summary=f"Proposal-only response for {deficit.deficit_type}",
        pseudo_diff=f"# pseudo diff only\n# address {deficit.source}\n",
        risk_level="medium" if deficit.severity >= 0.7 else "low",
        tests_required=["unit_tests", "sandbox_review", "human_approval"],
        approval_required=True,
        executed=False,
    )


def validate_patch_proposal_safety(proposal: PatchProposal) -> bool:
    return proposal.approval_required is True and proposal.executed is False


def never_apply_patch(proposal: PatchProposal) -> PatchProposal:
    """Return the proposal unchanged; proof package never applies patches."""

    return proposal

