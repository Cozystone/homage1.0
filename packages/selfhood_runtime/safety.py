from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .models import SelfhoodRuntimeProposal


OVERCLAIM_TERMS = (
    "real consciousness",
    "agi achieved",
    "iit proof",
    "privacy risk is zero",
    "privacy 0%",
)


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    blocked_reason: str | None = None
    downgraded_to_review: bool = False
    required_user_approval: bool = True
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _contains_overclaim(proposal: SelfhoodRuntimeProposal) -> bool:
    joined = " ".join(
        part
        for part in (proposal.title, proposal.summary, proposal.text_response or "")
        if part
    ).lower()
    return any(term in joined for term in OVERCLAIM_TERMS)


def validate_selfhood_proposal(proposal: SelfhoodRuntimeProposal) -> SafetyDecision:
    """Validate one proposal without executing it."""

    flags: list[str] = []
    if proposal.mutates_production or bool(proposal.metadata.get("actual_promotion_performed")):
        flags.append("production_or_promotion_mutation_blocked")
    if proposal.mutates_local_brain:
        flags.append("local_brain_write_blocked")
    if proposal.uses_real_p2p:
        flags.append("real_p2p_blocked")
    if bool(proposal.metadata.get("real_cloud_upload")):
        flags.append("real_cloud_upload_blocked")
    if proposal.executes_code or bool(proposal.metadata.get("generated_code_executed")):
        flags.append("generated_code_execution_blocked")
    if bool(proposal.metadata.get("real_hot_swap_performed")):
        flags.append("real_hot_swap_blocked")
    if bool(proposal.metadata.get("always_listening_enabled")):
        flags.append("always_listening_blocked")
    if bool(proposal.metadata.get("stores_raw_voice_transcript")):
        flags.append("raw_voice_transcript_storage_blocked")
    if _contains_overclaim(proposal):
        flags.append("agi_or_consciousness_overclaim_blocked")
    if flags:
        return SafetyDecision(False, flags[0], False, True, flags)
    if not proposal.requires_user_approval:
        return SafetyDecision(True, None, True, True, ["approval_required_for_nontrivial_proposal"])
    return SafetyDecision(True, None, False, True, ["requires_user_approval"])
